"""Per-character SQLite relationship records and their scene-time projections."""

import json
import math
from datetime import datetime


def initialize(connection, config):
    """Move embedded records and mark the runtime in the caller's transaction."""
    connection.execute("""CREATE TABLE IF NOT EXISTS relationships (
        target TEXT PRIMARY KEY NOT NULL, data TEXT NOT NULL
    )""")

    for target, entry in config.pop("relationships", {}).items():
        connection.execute("INSERT INTO relationships(target, data) VALUES (?, ?)",
                           (target, json.dumps(entry)))
    config["relationship_store_version"] = 1


def validate_target(target):
    if not isinstance(target, str) or not target.strip() or len(target) > 160:
        raise ValueError("relationship target must be a nonempty identifier of at most 160 characters")
    return target


def state_at(connection, target, at, baselines):
    """Read only this speaker, projecting drift from the last recorded change."""
    validate_target(target)
    row = connection.execute("SELECT data FROM relationships WHERE target=?", (target,)).fetchone()
    if row is None:
        authored = baselines.get(target) or {}
        if not isinstance(authored, dict):
            authored = {}
        base = {k: v for k, v in authored.items() if type(v) in (int, float) and 0 <= v <= 100}
        if "emotional_safety" in base:
            base.setdefault("trust", base["emotional_safety"])
        return {"baseline": base, "values": dict(base), "drift_per_day": {}, "updated_at": at}
    entry = json.loads(row[0])
    last = entry.get("updated_at")
    if last and at and entry.get("drift_per_day"):
        days = max(0, (datetime.fromisoformat(at) - datetime.fromisoformat(last)).total_seconds() / 86400)
        for key, rate in entry["drift_per_day"].items():
            value = entry["values"].get(key)
            baseline = entry.get("baseline", {}).get(key, 50)
            if type(value) in (int, float) and type(baseline) in (int, float):
                step = abs(rate) * days
                projected = min(baseline, value + step) if value < baseline else max(baseline, value - step)
                entry["values"][key] = round(projected, 2)
    if at:
        entry["updated_at"] = at
    return entry


def apply_change(connection, change, at, baselines, *, speaker=None):
    if not isinstance(change, dict):
        raise ValueError("relationship_change must be a mapping")
    target = validate_target(change.get("target", speaker))
    if speaker is not None and target != speaker:
        raise ValueError("Incoming relationship change must refer to the current speaker")
    deltas = change.get("delta")
    if not isinstance(deltas, dict) or not 1 <= len(deltas) <= 16:
        raise ValueError("relationship_change.delta must contain 1-16 dimensions")
    entry = state_at(connection, target, at, baselines)
    values = entry["values"]
    for key, amount in deltas.items():
        if (not isinstance(key, str) or not 1 <= len(key) <= 60 or type(amount) not in (int, float)
                or (isinstance(amount, float) and not math.isfinite(amount))):
            raise ValueError("relationship dimensions and finite numeric deltas required")
        prior = values.get(key, entry.get("baseline", {}).get(key, 50))
        values[key] = round(max(0, min(100, prior + amount)), 2)
    drift = change.get("drift_per_day")
    if drift is not None:
        if not isinstance(drift, dict) or any(
            k not in values or type(v) not in (int, float) or not 0 <= v <= 100 for k, v in drift.items()
        ):
            raise ValueError("drift_per_day must contain nonnegative numeric rates for known dimensions")
        entry["drift_per_day"].update(drift)
    connection.execute("""INSERT INTO relationships(target, data) VALUES (?, ?)
        ON CONFLICT(target) DO UPDATE SET data=excluded.data""", (target, json.dumps(entry)))
    return entry
