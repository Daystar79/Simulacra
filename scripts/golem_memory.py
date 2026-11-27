"""Memory recall and conversation-intent helpers over durable log data."""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from datetime import datetime, timezone
from typing import Any


def cue_keys(cues: Any) -> set[str]:
    if not isinstance(cues, list) or any(not isinstance(cue, str) or not cue.strip() for cue in cues):
        raise ValueError("Memory cues must be a list of nonempty strings")
    return {cue.strip().casefold() for cue in cues}


def recall_memories(memories: dict[str, Any], cues: Any) -> list[dict[str, Any]]:
    keys = cue_keys(cues)
    return [
        {"id": entry["id"], "summary": entry["summary"], "kind": kind}
        for kind in ("detailed", "footnote", "dream")
        for entry in memories.get(kind, [])
        if isinstance(entry, dict) and {"id", "summary"} <= entry.keys()
        and keys.intersection(cue_keys(entry.get("cues", [])))
    ]


def add_memory(log_data: dict[str, Any], memory: dict[str, Any]) -> bool:
    fields = ("id", "kind", "summary", "reason")
    if not isinstance(memory, dict) or any(
        not isinstance(memory.get(key), str) or not memory[key].strip() for key in fields
    ):
        raise ValueError("An approved memory requires nonempty id, kind, summary, and reason strings")
    kind = memory["kind"].strip()
    if kind not in ("detailed", "footnote", "dream"):
        raise ValueError("Memory kind must be detailed, footnote, or dream")
    cues = sorted(cue_keys(memory.get("cues")))
    if not cues:
        raise ValueError("An approved memory requires at least one recall cue")
    entry = {key: memory[key].strip() for key in ("id", "summary", "reason")}
    entry["cues"] = cues
    memories = log_data.setdefault("memories", {})
    for bucket in ("detailed", "footnote", "dream"):
        for existing in memories.get(bucket, []):
            if isinstance(existing, dict) and existing.get("id") == entry["id"]:
                if bucket == kind and existing == entry:
                    return False
                raise ValueError(f"Memory ID already exists: {entry['id']}")
    memories.setdefault(kind, []).append(entry)
    log_data["revision"] = log_data.get("revision", 0) + 1
    log_data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_data["last_commit_id"] = entry["id"]
    return True


def conversation_intent(
    conversation: dict[str, Any], interest: float, guarded: bool, activated: bool,
    target: str, recent_inquiries: list[list[str]],
) -> dict[str, str] | None:
    if not isinstance(conversation, dict):
        raise ValueError("Conversation must be a JSON object")
    conflict = conversation.get("conflict")
    topic = conversation.get("open_topic", "")
    if conflict not in (None, "boundary", "goal", "claim") or not isinstance(topic, str):
        raise ValueError("Conversation accepts a boundary, goal, or claim conflict and a text open_topic")
    if "willing_to_help" in conversation:
        willing = conversation["willing_to_help"]
        if not isinstance(willing, bool):
            raise ValueError("willing_to_help must be a boolean")
        if not willing:
            return {"intent": "decline", "delivery": "brief" if activated else "deliberate"}
    if conflict:
        return {"intent": "push_back", "conflict": conflict, "delivery": "brief" if activated else "deliberate"}
    topic = topic.strip()
    if topic and interest >= 60 and not guarded and [target, topic.casefold()] not in recent_inquiries:
        return {"intent": "ask", "topic": topic}
    return None

