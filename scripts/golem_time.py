"""The event clock: timestamp parsing and elapsed-time computation."""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from datetime import datetime, timezone
from typing import Any


def parse_event_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("event_at must be an ISO 8601 timestamp with a timezone")
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise ValueError("event_at must include a timezone")
    return timestamp.astimezone(timezone.utc)


def event_clock(stimulus: dict[str, Any], history: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    previous = history.get("last_event_at")
    if "event_at" in stimulus:
        if {"elapsed_ms", "elapsed_minutes"} & stimulus.keys():
            raise ValueError("event_at cannot be combined with explicit elapsed time")
        current = parse_event_time(stimulus["event_at"])
        elapsed_ms = (current - parse_event_time(previous)).total_seconds() * 1_000 if previous else 0.0
        if elapsed_ms < 0:
            raise ValueError("event_at is earlier than the last processed event")
        return elapsed_ms, {
            "last_event_at": current.isoformat(),
            "event_sequence": history.get("event_sequence", 0) + 1,
        }
    if previous:
        raise ValueError("event_at is required when continuing timestamped history")
    if "elapsed_ms" in stimulus:
        return float(stimulus["elapsed_ms"]), {}
    return float(stimulus.get("elapsed_minutes", 1)) * 60_000, {}

