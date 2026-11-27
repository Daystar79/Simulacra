"""Resident character hydration, realm-data cache, runtime config, and setup."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import golem  # noqa: E402
import relationship_memory  # noqa: E402
from golem_loop_modules.db import (  # noqa: E402
    check_character_files,
    clear_activity_and_archive,
    ensure_activity_schema,
    read_object,
)
from golem_loop_modules.projection import message_text  # noqa: E402

_REALM_CACHE: dict[str, Any] = {}

# Resident character instances. The hydrated character survives between
# cognitive wakes inside one host process; the persistent database remains
# the authoritative identity and health record. Memo hit does not copy:
# Golem's tick reads the shared instance and never writes into it, so a
# resident host avoids both the YAML parse and the deep-copy round trip.
_RESIDENT_CHARACTERS: dict[tuple, dict] = {}


def load_cached_realm_data() -> dict[str, Any]:
    mtime = golem.REALM_DATA_PATH.stat().st_mtime_ns
    if _REALM_CACHE.get("mtime") != mtime:
        _REALM_CACHE["data"] = yaml.safe_load(golem.REALM_DATA_PATH.read_text(encoding="utf-8"))
        _REALM_CACHE["mtime"] = mtime
    return _REALM_CACHE["data"]


def _character_cache_key(config, card_mtime, log_mtime):
    card_path = Path(config["card"])
    log_path = Path(config["log"]) if config.get("log") else None
    goal_changes = config.get("goal_changes") or {}
    return (
        str(card_path.resolve()), str(log_path.resolve()) if log_path else None,
        config.get("slug"), config.get("character_id"), card_mtime, log_mtime,
        json.dumps(goal_changes, sort_keys=True, default=str),
    )


def _ensure_character_cache_table(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS character_cache (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        data TEXT NOT NULL
    )""")


def _stored_character_cache(connection, key):
    """Read the persisted hydrate for cross-process CLI hosts; None when stale."""
    try:
        row = connection.execute("SELECT data FROM character_cache WHERE id = 1").fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    stored = json.loads(row["data"])
    if not isinstance(stored, dict):
        return None
    if (stored.get("key") != list(key)):
        return None
    inner = stored.get("entry") or {}
    state, card, durable = inner.get("state"), inner.get("card"), inner.get("durable")
    if not isinstance(state, dict) or not isinstance(card, dict):
        return None
    entry = {"state": state, "card": card, "durable": durable}
    _RESIDENT_CHARACTERS[key] = entry
    return entry


def _store_character_cache(connection, key, entry):
    _ensure_character_cache_table(connection)
    connection.execute(
        "INSERT OR REPLACE INTO character_cache (id, data) VALUES (1, ?)",
        (json.dumps({"key": list(key), "entry": entry}, separators=(",", ":")),),
    )


def load_cached_character(config, connection=None):
    """Return the resident hydrated character, hydrating once and reusing thereafter.

    The returned (state, card, durable) objects are shared between calls for as
    long as the character files, character id, slug, and pending goal changes
    stay unchanged. Treat them as read-only: Golem ticks read the instance and
    never write into it. The persistent database, not the cache, is
    authoritative, and any change to the card or log mtime rehydrates.
    """
    card_path = Path(config["card"])
    log_path = Path(config["log"]) if config.get("log") else None
    card_mtime = card_path.stat().st_mtime_ns
    log_mtime = log_path.stat().st_mtime_ns if log_path and log_path.exists() else None
    key = _character_cache_key(config, card_mtime, log_mtime)
    entry = _RESIDENT_CHARACTERS.get(key)
    if entry is not None:
        return entry["state"], entry["card"], entry["durable"]
    if connection is not None:
        entry = _stored_character_cache(connection, key)
        if entry is not None:
            return entry["state"], entry["card"], entry["durable"]
    card = golem.load_character(card_path, config.get("slug"))
    state, durable = golem.overlay_log(card, log_path, goal_changes=config.get("goal_changes") or {})
    check_character_files(config, card, durable)
    if config.get("character_id"):
        state["character_id"] = config["character_id"]
    entry = {"card": card, "state": state, "durable": durable}
    _RESIDENT_CHARACTERS[key] = entry
    if connection is not None:
        _store_character_cache(connection, key, entry)
    return state, card, durable


def cached_identity(connection):
    """Owner fallback for legacy databases without a character id on the runtime row."""
    entry = None
    try:
        row = connection.execute("SELECT data FROM character_cache WHERE id = 1").fetchone()
        entry = json.loads(row["data"]) if row else None
    except sqlite3.OperationalError:
        entry = None
    if isinstance(entry, dict):
        inner = entry.get("entry") or {}
        state = inner.get("state") or {}
        if isinstance(state, dict) and state.get("character_id"):
            return state["character_id"]
    return None


def migrate_runtime_row(connection, config):
    """Move a legacy embedded character cache out of the runtime row (one-time)."""
    if "cached_character" not in config:
        return config
    legacy = config.pop("cached_character")
    _ensure_character_cache_table(connection)
    card_path = Path(config["card"])
    log_path = Path(config["log"]) if config.get("log") else None
    key = _character_cache_key(
        config,
        card_path.stat().st_mtime_ns if card_path.exists() else None,
        log_path.stat().st_mtime_ns if log_path and log_path.exists() else None,
    )
    stored = {
        "card_mtime": legacy.get("card_mtime"), "log_mtime": legacy.get("log_mtime"),
        "goal_changes": legacy.get("goal_changes"),
        "card": legacy.get("card"), "state": legacy.get("state"),
        "durable": legacy.get("durable"),
    }
    connection.execute("INSERT OR REPLACE INTO character_cache (id, data) VALUES (1, ?)",
                       (json.dumps({"key": list(key), "entry": stored}, separators=(",", ":")),))
    connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    return config


def build_identity_anchor(card, state):
    """Extract core identity and voice constraints without dumping full memories or history."""
    anchor = {
        key: card[key]
        for key in ("name", "call_name", "character_id", "cognitive_bias", "cognitive_gift", "voice",
                    "pleasure_sources", "physical_pleasure_sources")
        if key in card
    }
    if golem.canon_adult(state) and card.get("sexual_pleasure_sources"):
        anchor["sexual_pleasure_sources"] = card["sexual_pleasure_sources"]
    for key in ("active_focus", "defense_posture", "social_facade"):
        if key in state:
            anchor[key] = state[key]
    return anchor


def extract_memory_cues(event, stimulus, memories):
    """Match stored memory cues against incoming event text for on-demand recall."""
    explicit = stimulus.get("memory_cues", [])
    seen = golem.cue_keys(explicit)
    conversation = stimulus.get("conversation", {})
    if not isinstance(conversation, dict):
        raise ValueError("Conversation must be an object")
    texts = [
        message_text(event),
        event.get("context"),
        event.get("topic"),
        conversation.get("open_topic"),
    ]
    haystack = " ".join(str(t) for t in texts if isinstance(t, str) and t.strip()).casefold()
    if not haystack or not isinstance(memories, dict):
        return explicit
    matched = list(explicit)
    for bucket in ("detailed", "footnote", "dream"):
        for entry in memories.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            for cue in entry.get("cues") or []:
                cue_text = str(cue).strip()
                if not cue_text or cue_text.casefold() in seen:
                    continue
                if re.search(rf"(?<!\w){re.escape(cue_text.casefold())}(?!\w)", haystack):
                    matched.append(cue_text)
                    seen.add(cue_text.casefold())
    return matched


def runtime_config(connection, character_id=None):
    config = json.loads(connection.execute("SELECT data FROM runtime WHERE id = 1").fetchone()["data"])
    config = migrate_runtime_row(connection, config)
    if config.get("profile"):
        directory = Path(connection.execute("PRAGMA database_list").fetchone()["file"]).parent
        if directory.name != config["character_id"]:
            raise ValueError("Profile database must stay in its character's directory")
        for field, filename in (("card", "character.yaml"), ("log", "character_log.yaml")):
            path = directory / filename
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError(f"Profile requires a private {filename} in {directory}")
            config[field] = str(path)
    if character_id is not None and config.get("character_id") != character_id:
        if config.get("character_id") or config.get("lifecycle"):
            raise ValueError("Character ID does not match the selected database")
        # Adopt an existing single-character database in place. Verify the
        # stored identity and current files before enabling scoped decisions.
        config["character_id"] = character_id
        load_cached_character(config, connection)
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    if config.get("lifecycle") == "deleted":
        # Older tombstones can still have rows in the two newer ledger tables.
        clear_activity_and_archive(connection)
    elif "relationship_store_version" not in config:
        relationship_memory.initialize(connection, config)
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    return config


def setup(connection, args, now):
    ensure_activity_schema(connection)
    card = args.card.resolve(strict=True)
    log = args.log.resolve(strict=True) if args.log else None
    owner = getattr(args, "character_id", None)
    slug = args.slug
    if owner and not slug:
        # Select by route for a shared pack. Single-card files retain their own identity.
        data = yaml.safe_load(card.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("characters"), dict):
            slug = owner
    history = read_object(args.import_history) if args.import_history else {}
    if args.history_at:
        if history.get("last_event_at"):
            raise ValueError("Imported history already has a timestamp")
        history["last_event_at"] = golem.parse_event_time(args.history_at).isoformat()
    elif history.get("last_event_at"):
        history["last_event_at"] = golem.parse_event_time(history["last_event_at"]).isoformat()
    else:
        history["last_event_at"] = now.isoformat()
    if args.idle_seconds < 1:
        raise ValueError("--idle-seconds must be at least 1")
    config = {
        "card": str(card), "log": str(log) if log else None, "slug": slug,
        **({"character_id": owner} if owner else {}),
        "idle_seconds": args.idle_seconds, "history": history,
        "idle_at": (now + timedelta(seconds=args.idle_seconds)).timestamp(),
    }
    load_cached_character(config, connection)
    connection.execute("CREATE TABLE runtime (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)")
    connection.execute("""
        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            due REAL NOT NULL,
            input TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            request TEXT,
            decision TEXT
        )
    """)
    connection.execute("CREATE INDEX due_events ON events (status, due)")
    connection.execute("CREATE TABLE observations (event_id TEXT PRIMARY KEY, topic TEXT NOT NULL, data TEXT NOT NULL)")
    connection.execute("CREATE INDEX observation_topics ON observations (topic)")
    relationship_memory.initialize(connection, config)
    connection.execute("INSERT INTO runtime VALUES (1, ?)", (json.dumps(config),))
    return {"initialized": True}
