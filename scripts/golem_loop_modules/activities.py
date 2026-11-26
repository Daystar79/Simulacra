"""Duration-based activity lifecycle (start, complete, interrupt, resume, extend)."""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import golem  # noqa: E402


def active_activity(connection):
    row = connection.execute(
        "SELECT * FROM activities WHERE status IN ('active','due') ORDER BY started_at LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return dict(row) | {"data": json.loads(row["data"])}


def schedule_activity_due(connection, activity_id, kind, at, revision):
    due_id = f"activity:{activity_id}:due:{revision}"
    event = {"id": due_id, "kind": "plan", "at": at,
             "activity_due": activity_id,
             "context": f"The planned {kind} period has reached its scheduled end."}
    row = connection.execute("SELECT input FROM events WHERE id=?", (due_id,)).fetchone()
    if row:
        if json.loads(row["input"]) != event:
            raise ValueError(f"Activity due event ID collision: {due_id}")
    else:
        connection.execute("INSERT INTO events (id,due,input) VALUES (?,?,?)",
                           (due_id, golem.parse_event_time(at).timestamp(), json.dumps(event)))
    connection.execute("UPDATE activities SET due_event_id=? WHERE id=?", (due_id, activity_id))
    return due_id


def apply_activity_decision(connection, activity, event_id, at):
    """Persist a selected duration activity and its scheduled transition atomically."""
    if not isinstance(activity, dict):
        raise ValueError("Decision activity must be an object")
    op = activity.get("op")
    allowed_ops = {"start", "complete", "interrupt", "resume", "extend"}
    if op not in allowed_ops:
        raise ValueError("Activity op must be start, complete, interrupt, resume, or extend")
    at_dt = golem.parse_event_time(at)
    if op == "start":
        activity_id, kind = activity.get("id"), activity.get("kind")
        state, seconds = activity.get("state"), activity.get("duration_seconds")
        if not isinstance(activity_id, str) or not activity_id.strip() or not isinstance(kind, str) or not kind.strip():
            raise ValueError("Starting an activity requires stable id and kind strings")
        if state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        if type(seconds) is not int or seconds < 1:
            raise ValueError("Activity duration_seconds must be a positive integer")
        if connection.execute("SELECT 1 FROM activities WHERE status IN ('active','due')").fetchone():
            raise ValueError("An activity is already active; interrupt or complete it first")
        due_at = (at_dt + timedelta(seconds=seconds)).isoformat()
        data = activity.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("Activity data must be an object")
        effects = data.get("effects", {})
        if not isinstance(effects, dict):
            raise ValueError("Activity effects must be an object")
        if set(effects) - {"food_intake"}:
            raise ValueError("Activity effects currently support food_intake only")
        if "food_intake" in effects and (type(effects["food_intake"]) is not int
                                          or not 0 <= effects["food_intake"] <= 100):
            raise ValueError("Activity food_intake must be an integer from 0 to 100")
        connection.execute("""INSERT INTO activities
            (id,kind,status,state,started_at,due_at,duration_seconds,start_event_id,revision,data)
            VALUES (?,?, 'active', ?,?,?,?,?,1,?)""",
                           (activity_id, kind, state, at_dt.isoformat(), due_at, seconds, event_id,
                            json.dumps(data)))
        schedule_activity_due(connection, activity_id, kind, due_at, 1)
        return {"state": state, "op": op, "activity_id": activity_id}

    activity_id = activity.get("id")
    row = connection.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    if not row:
        raise ValueError("Unknown activity id")
    if op == "complete":
        if row["status"] != "due":
            raise ValueError("An activity can be completed only after its due event")
        next_state = activity.get("state", "awake")
        if next_state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE activities SET status='completed',ended_at=?,end_event_id=? WHERE id=?",
                           (at_dt.isoformat(), event_id, activity_id))
        return {"state": next_state, "op": op, "activity_id": activity_id,
                "effects": json.loads(row["data"]).get("effects", {})}
    if op == "interrupt":
        if row["status"] not in ("active", "due"):
            raise ValueError("Only an active activity can be interrupted")
        next_state = activity.get("state", "awake")
        if next_state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE events SET status='cancelled' WHERE id=? AND status='queued'",
                           (row["due_event_id"],))
        connection.execute("UPDATE activities SET status='interrupted',ended_at=?,end_event_id=? WHERE id=?",
                           (at_dt.isoformat(), event_id, activity_id))
        return {"state": next_state, "op": op, "activity_id": activity_id}
    if op in ("resume", "extend"):
        permitted = "interrupted" if op == "resume" else "due"
        if row["status"] != permitted:
            raise ValueError(f"Activity {op} requires status {permitted}")
        seconds = activity.get("duration_seconds")
        if type(seconds) is not int or seconds < 1:
            raise ValueError(f"Activity {op} requires positive duration_seconds")
        state = activity.get("state", row["state"])
        if state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE events SET status='cancelled' WHERE id=? AND status='queued'",
                           (row["due_event_id"],))
        due_at = (at_dt + timedelta(seconds=seconds)).isoformat()
        revision = row["revision"] + 1
        connection.execute("""UPDATE activities SET status='active',state=?,due_at=?,duration_seconds=?,
            ended_at=NULL,end_event_id=NULL,revision=? WHERE id=?""",
                           (state, due_at, seconds, revision, activity_id))
        schedule_activity_due(connection, activity_id, row["kind"], due_at, revision)
        return {"state": state, "op": op, "activity_id": activity_id}
