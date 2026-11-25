"""Persistent event loop and host handoff for the Golem CLI."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import zlib
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from . import golem, goal_evolution, relationship_memory
else:
    import golem
    import goal_evolution
    import relationship_memory

RECENT_LIMIT = 12
ACTIVE_MEMORY_WINDOW_SECONDS = 2 * 60 * 60
_REALM_CACHE: dict[str, Any] = {}


def load_cached_realm_data() -> dict[str, Any]:
    mtime = golem.REALM_DATA_PATH.stat().st_mtime_ns
    if _REALM_CACHE.get("mtime") != mtime:
        _REALM_CACHE["data"] = yaml.safe_load(golem.REALM_DATA_PATH.read_text(encoding="utf-8"))
        _REALM_CACHE["mtime"] = mtime
    return _REALM_CACHE["data"]


@contextmanager
def file_lock(lock_path: Path):
    """Cross-platform exclusive file lock released on exit or process termination."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.01)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)



def _runtime_connection(db: Path):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    # WAL persists in the database file once set; repeated statements are
    # cheap. synchronous=NORMAL is durable under WAL and removes the
    # per-commit rollback-journal fsync from the hot path.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


@contextmanager
def staged_transaction(connection):
    """One committed transaction on an already-open runtime connection."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        yield connection


@contextmanager
def transaction(db: Path):
    connection = _runtime_connection(db)
    try:
        with staged_transaction(connection):
            yield connection
    finally:
        connection.close()


_SCHEMA_ENSURED: dict[str, int] = {}


def ensure_activity_schema(connection):
    """Non-destructive migration for persistent runtimes created before activities."""
    db_file = connection.execute("PRAGMA database_list").fetchone()["file"]
    if db_file:
        try:
            stamp = os.stat(db_file).st_mtime_ns
        except OSError:
            stamp = None
        if stamp is not None and _SCHEMA_ENSURED.get(db_file) == stamp:
            return
    connection.execute("""CREATE TABLE IF NOT EXISTS activities (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        state TEXT NOT NULL,
        started_at TEXT NOT NULL,
        due_at TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL,
        ended_at TEXT,
        start_event_id TEXT NOT NULL,
        due_event_id TEXT,
        end_event_id TEXT,
        revision INTEGER NOT NULL DEFAULT 1,
        data TEXT NOT NULL DEFAULT '{}'
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(activities)")}
    if "duration_seconds" not in columns:
        connection.execute("ALTER TABLE activities ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0")
    connection.execute("CREATE INDEX IF NOT EXISTS activity_status_due ON activities(status, due_at)")
    if db_file and stamp is not None:
        _SCHEMA_ENSURED[db_file] = stamp


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


def character_database(characters_dir, character_id):
    """Locate a character under a shared state root without any process-wide active character."""
    if not isinstance(character_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", character_id):
        raise ValueError("Use a lowercase character ID containing letters, digits, underscores or hyphens")
    root = Path(characters_dir).resolve()
    path = root / character_id / "runtime.sqlite3"
    if path.resolve() != path or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("Character runtime directories and databases must have distinct physical paths")
    return path


def check_character_files(config, card, durable):
    owner = config.get("character_id")
    if owner is None:
        return
    identity = card.get("character_id") or config.get("slug") or (card.get("call_name") or card.get("name") or "").lower()
    if identity != owner:
        raise ValueError(f"Card identity {identity!r} does not match character ID {owner!r}")
    if config.get("log") and (durable or {}).get("character_id") != owner:
        raise ValueError(f"Durable log must declare character_id: {owner}")
    if config["history"].get("character_id") not in (None, owner):
        raise ValueError("Character ID mismatch in runtime history")


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


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def enqueue(connection, event, history, now, *, actor_id=None):
    if "character_id" in event:
        config = runtime_config(connection)
        owner = config.get("character_id") or cached_identity(connection)
        if event["character_id"] != owner:
            raise ValueError("Event character ID does not match the selected database")
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip() or event_id.startswith("idle:"):
        raise ValueError("Event id must be nonempty and cannot begin with idle:")
    if event.get("kind") not in ("incoming", "plan", "world"):
        raise ValueError("Event kind must be incoming, plan, or world")
    stimulus = event.get("stimulus", {})
    if not isinstance(stimulus, dict) or {"event_at", "elapsed_ms", "elapsed_minutes"} & stimulus.keys():
        raise ValueError("Use the event's at field for timing, outside stimulus")
    if not isinstance(event.get("context", ""), str):
        raise ValueError("Event context must be text")
    if "host_notes" in event and not isinstance(event["host_notes"], str):
        raise ValueError("Event host_notes must be text")
    if "expectation" in event:
        topic_key(event.get("topic"))
        scores(event["expectation"])
    if "topic" in event:
        topic_key(event["topic"])
    existing = connection.execute("SELECT input FROM events WHERE id = ?", (event_id,)).fetchone()
    saved = json.loads(existing["input"]) if existing is not None else None
    # An exact replay of a pre-migration event retains its original speaker routing.
    if saved != event and actor_id is not None and event["kind"] == "incoming" and not resolve_relationship_target(event):
        event = {**event, "relationship_target": relationship_memory.validate_target(actor_id)}
    if existing is not None:
        if saved != event:
            raise ValueError(f"Event ID already exists with different contents: {event_id}")
        return {"id": event_id, "queued": False}
    if "expectation_context" in event:
        expectation_dimensions(event)
    if event["kind"] == "plan" and "at" not in event:
        raise ValueError("A plan requires an at timestamp")
    due = golem.parse_event_time(event["at"]) if "at" in event else now
    last = history.get("last_event_at")
    if last and due < golem.parse_event_time(last):
        raise ValueError("Event is earlier than the last processed tick")
    connection.execute(
        "INSERT INTO events (id, due, input) VALUES (?, ?, ?)",
        (event_id, due.timestamp(), json.dumps(event)),
    )
    return {"id": event_id, "queued": True}


def recent_events(connection, limit=RECENT_LIMIT, since_timestamp=None):
    query = """SELECT input, due, decision, status, json_extract(request, '$.assessment') AS assessment,
                  json_extract(request, '$.body_response') AS body_response FROM events
           WHERE status IN ('resolved', 'failed')"""
    params: list[Any] = []
    if since_timestamp is not None:
        query += " AND due >= ?"
        params.append(since_timestamp)
    query += " ORDER BY due DESC, rowid DESC LIMIT ?"
    params.append(limit)
    rows = connection.execute(query, params).fetchall()
    return [
        {
            "event": json.loads(row["input"]), "at": datetime.fromtimestamp(row["due"], timezone.utc).isoformat(),
            "decision": json.loads(row["decision"]), "status": row["status"],
            **({"assessment": json.loads(row["assessment"])} if row["assessment"] else {}),
            **({"body_response": json.loads(row["body_response"])} if row["body_response"] else {}),
        }
        for row in reversed(rows)
    ]


def message_text(event):
    """Read the utterance from the current transport field or an older alias."""
    for value in (event.get("text"), event.get("message"), (event.get("stimulus") or {}).get("text"),
                  event.get("context")):
        if isinstance(value, str) and value.strip():
            return value
    return ""


def compact_recent_events(events, older_limit=None):
    """Decision-context projection; the complete event ledger remains in SQLite.

    With ``older_limit``, every entry except the most recent one has its
    history-bearing text (context, text, action, outcome, reply) capped at that
    many characters, since the projection already flags verbatim repetition
    separately and the current turn is the one the host must read in full.
    """
    compact = []
    for index, entry in enumerate(events):
        event, decision = entry.get("event") or {}, entry.get("decision") or {}
        item = {"id": event.get("id"), "kind": event.get("kind"), "at": entry.get("at"),
                "status": entry.get("status")}
        target = resolve_relationship_target(event)
        if target:
            item["relationship_target"] = target
        if event.get("topic"):
            item["topic"] = event["topic"]
        limit = 320 if older_limit is None or index == len(events) - 1 else older_limit
        utterance = message_text(event)
        context = event.get("context") or utterance
        if context:
            item["context"] = context[:limit]
        if utterance and utterance != context:
            item["text"] = utterance[:limit]
        for key in ("action", "outcome", "reply"):
            if isinstance(decision.get(key), str) and decision[key]:
                item[key] = decision[key][:limit]
        assessment = entry.get("assessment") or {}
        for key in ("topic", "forecast", "observed", "next_expectation"):
            if key in assessment:
                item[key] = assessment[key]
        compact.append(item)
    return compact


def relevant_expectations(expectations, event, recent, limit=12):
    """Surface matching learned topics, not the entire cumulative expectation map."""
    topics = []
    for candidate in [event.get("topic"), *(item.get("topic") for item in reversed(recent))]:
        if isinstance(candidate, str):
            key = candidate.strip().casefold()
            if key and key not in topics and key in expectations:
                topics.append(key)
        if len(topics) >= limit:
            break
    if len(topics) < limit and isinstance(event, dict):
        haystack = " ".join(
            str(t) for t in (message_text(event), event.get("context")) if isinstance(t, str) and t.strip()
        ).casefold()
        if haystack:
            for key in expectations:
                if key not in topics and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", haystack):
                    topics.append(key)
                    if len(topics) >= limit:
                        break
    return {key: expectations[key] for key in topics}


def repeated_action_pattern(events, window=5):
    """Describe consecutive duplicate actions without changing or rejecting them."""
    actions = [
        re.sub(r"\W+", " ", (entry.get("decision") or {}).get("action", "").casefold()).strip()
        for entry in events[-window:]
    ]
    actions = [action for action in actions if action]
    if len(actions) < 2:
        return {"repeated": False, "consecutive_count": 0}
    count = 1
    for action in reversed(actions[:-1]):
        if action != actions[-1]:
            break
        count += 1
    return {"repeated": count >= 2, "consecutive_count": count,
            **({"action": actions[-1]} if count >= 2 else {})}


def repeated_reply_pattern(events, window=5):
    """Flag consecutive duplicate reply openers/somatic beats or user-echoing."""
    replies = []
    for entry in events[-window:]:
        reply = (entry.get("decision") or {}).get("reply")
        if isinstance(reply, str) and reply.strip():
            replies.append((reply.strip(), entry.get("event") or {}))
    if not replies:
        return {"repeated_opener": False, "consecutive_count": 0, "echoing_user": False}

    def opener_key(text):
        stage = re.match(r"^\*([^*]+)\*", text)
        if stage:
            return re.sub(r"\W+", " ", stage.group(1).casefold()).strip()
        words = re.findall(r"[a-z0-9']+", text.casefold())[:4]
        return " ".join(words)

    openers = [opener_key(text) for text, _ in replies]
    count = 1
    if len(openers) >= 2 and openers[-1]:
        for key in reversed(openers[:-1]):
            if key != openers[-1]:
                break
            count += 1

    latest_reply, latest_event = replies[-1]
    user_text = message_text(latest_event)
    user_words = {w for w in re.findall(r"[a-z0-9']+", user_text.casefold()) if len(w) >= 4}
    reply_head_words = re.findall(r"[a-z0-9']+", latest_reply.casefold())[:16]
    echoing = False
    if len(user_words) >= 3 and reply_head_words:
        overlap = user_words.intersection(reply_head_words)
        echoing = len(overlap) / len(user_words) >= 0.6

    return {
        "repeated_opener": count >= 2,
        "consecutive_count": count if count >= 2 else 0,
        **({"opener": openers[-1]} if count >= 2 else {}),
        "echoing_user": echoing,
    }


def expression_guidance(snapshot, medium=None):
    """Translate measured body constraints into options for the host's rendering."""
    body = snapshot["autonomic_state"]
    telemetry = body.get("somatic_telemetry")
    if not telemetry:  # Older pending snapshots can finish on the previous contract.
        return None
    if body.get("activity") == "sleeping":
        return "Use the sleeping posture and breathing. Deliberate gaze, speech and approach require waking."
    # Each tick carries the current interlocutor's vector only.
    bond = next(iter(snapshot.get("relational_vectors", {}).values()), {})
    if body.get("involuntary_response") == "freeze":
        cue = "Let stillness or a delayed answer carry the moment."
    elif telemetry["postural_bracing"] >= 40:
        cue = "Consider a held stance, a delayed step, or the effort it takes to sustain eye contact."
    elif telemetry["energy_expenditure"] >= 40 or telemetry["register_shift"] >= 56:
        cue = "Consider where breath interrupts a phrase or effort shifts the speaker’s usual register."
    elif bond.get("emotional_safety", 50) < 35:
        cue = "Consider preserving distance, looking back to the task, or letting a question go unanswered."
    elif body.get("lingering_arousal"):
        cue = "Residual warmth can stay private while attention returns to the current topic or task."
    elif telemetry["peripheral_perfusion"] >= 62 and bond.get("intimacy", 0) >= 50:
        cue = "If closeness is welcome in this scene, consider staying within reach or letting eye contact linger."
    elif telemetry["peripheral_perfusion"] >= 62:
        cue = "Consider whether warmth is felt privately or becomes visible in the scene."
    else:
        cue = "An ordinary pause or an unremarked movement can be enough."
    if medium == "text":
        if body.get("involuntary_response") == "freeze" or telemetry["postural_bracing"] >= 40:
            cue = "In text, pressure might shorten an answer or leave the message unanswered."
        elif bond.get("emotional_safety", 50) < 35:
            cue = "Keep private details off the page if the character would answer only the practical question."
        else:
            cue = "In text, a specific remembered detail or a second question can carry interest when it fits."
    elif medium == "voice":
        if telemetry["energy_expenditure"] >= 40 or telemetry["register_shift"] >= 56:
            cue = "On a voice call, breath may break a phrase early or shift its pitch."
        else:
            cue = "On a voice call, use a pause, a change of subject, or an unhurried reply if it fits."
    if snapshot.get("affective_state", {}).get("emotions", {}).get("pleasure", 0) >= 40:
        cue += " If enjoyment matters here, let it show in what the character savors or returns to."
    if body.get("physical_pleasure", 0) >= 40:
        cue += " Bodily comfort may show in how the character settles into the current activity."
    if body.get("sexual_pleasure", 0) >= 40:
        cue += " Sexual enjoyment is private. The character chooses whether to communicate it."
    if body.get("orgasm"):
        cue += " A brief involuntary peak may interrupt a movement or breath. Choose what is perceptible here."
    elif body.get("orgasm_recovery"):
        cue += " Let the recovery affect pacing only as far as the character and scene warrant."
    if body.get("lingering_arousal"):
        cue += " Carryover can outlast its original cue or listener. Let the current relationship and purpose guide the reply."
    return (cue + " Choose at most one salient beat, or leave it private. Use only cues the listener "
            "could perceive. Decide what the character would say or leave "
            "unsaid. For welcome flirting or affection, let a particular action carry the subtext. "
            "Use a pet name only when established for this speaker and listener. "
            "A bodily response alone establishes neither intent nor consent.")


def intimacy_render(request, profile):
    """Resolve a host's depiction ceiling using only card identities and ages."""
    fallback = {"depiction": "sfw"}
    event = request["event"]
    mode = event.get("depiction")
    if mode not in ("fade_to_black", "explicit"):
        return fallback
    roster = event.get("scene_characters")
    tick = request["tick"]
    if "ADULT_GATE:ELIGIBLE" not in tick.get("golem_meta", {}).get("triggered_rules", []):
        return fallback
    snapshot = tick["psychosomatic_snapshot"]
    source = request["character"]
    actor = source.get("slug") or snapshot["character_id"]
    if not isinstance(roster, list) or actor not in roster or not all(isinstance(key, str) for key in roster):
        return fallback
    target = resolve_relationship_target(event)
    if target and target not in roster:
        return fallback
    try:
        card_path = Path(source["card"])
        pack = yaml.safe_load(card_path.read_text(encoding="utf-8"))
        actor_card, location = golem.selected_card(pack, source.get("slug"))
        if location and location[-1] != actor:
            return fallback
        card_id = actor_card.get("character_id")
        if (profile or card_id is not None) and card_id != snapshot["character_id"]:
            return fallback
        if not golem.canon_adult(actor_card):
            return fallback
        for key in set(roster):
            if key == actor:
                continue
            if profile:
                path = character_database(card_path.parent.parent, key).with_name("character.yaml")
                if path.resolve() != path or path.stat().st_nlink != 1:
                    return fallback
                card = golem.load_character(path, None)
                if card.get("character_id") != key:
                    return fallback
            else:
                if not location:
                    return fallback
                card = pack["characters"].get(key)
            if not isinstance(card, dict) or not golem.canon_adult(card):
                return fallback
        module = "Framework/Mechanics/erotica.md"
        registry = (golem.ROOT / "Framework/Modules.md").read_text(encoding="utf-8")
        for row in registry.splitlines():
            cells = [cell.strip().strip("`") for cell in row.strip("|").split("|")]
            if len(cells) == 5 and cells[1:4] == [module, "ENABLED", "app_render"]:
                return {"depiction": mode, "guide": (golem.ROOT / module).read_text(encoding="utf-8")}
    except (OSError, ValueError, yaml.YAMLError):
        pass
    return fallback


def pending_request(connection):
    row = connection.execute("SELECT request FROM events WHERE status = 'pending'").fetchone()
    if not row:
        return None
    request = json.loads(row["request"])
    owner, profile = connection.execute(
        "SELECT json_extract(data,'$.character_id'), json_extract(data,'$.profile') FROM runtime WHERE id=1"
    ).fetchone()
    if owner:
        snapshot_id = request["tick"]["psychosomatic_snapshot"]["character_id"]
        if snapshot_id != owner:
            raise ValueError("Pending tick belongs to a different character")
        request["character_id"] = owner
    if profile:
        directory = Path(connection.execute("PRAGMA database_list").fetchone()["file"]).parent
        request["character"] = {"card": str(directory / "character.yaml"),
                                "log": str(directory / "character_log.yaml"), "slug": None}
    if request["event"]["kind"] == "incoming":
        request["reply_guidance"] = {
            "stance": (
                "What does the speaker claim, and what does the character already believe or know? "
                "Acknowledge the speaker's experience in character. Agree where it fits, keep any "
                "difference, and revise a belief only as far as the new evidence warrants."
            ),
            "disclosure": (
                "What has this listener actually heard or witnessed? Treat host_notes and recalled "
                "memories as private. Check remembered details against the card and established events. "
                "Choose what this character has reason to reveal to this listener now. A memory may "
                "affect the reply while every identifying detail stays private."
            ),
        }
        if request.get("relationship_state"):
            request["reply_guidance"]["relationship"] = (
                "Consider what this character has learned about this speaker when choosing whether "
                "to confide, challenge, help, or keep their distance. Weigh it alongside the present "
                "exchange and the character's own goals."
            )
    if "depiction" in request["event"]:
        request["app_render"] = intimacy_render(request, profile)
        request["event"]["depiction"] = request["app_render"]["depiction"]
    guidance = expression_guidance(request["tick"]["psychosomatic_snapshot"], request["event"].get("medium"))
    if guidance:
        request["expression_guidance"] = guidance
    return request


def decision_context(request):
    """Project the saved tick into the values a character needs for one decision."""
    tick = request["tick"]
    snapshot = tick["psychosomatic_snapshot"]
    affect = snapshot["affective_state"]
    body = snapshot["autonomic_state"]
    event = request["event"]
    # Keep transport context, including host-defined scene fields, outside the
    # physiological inputs. Some older hosts put the utterance in stimulus.text.
    scene = {key: value for key, value in event.items() if key != "stimulus"}
    stimulus = event.get("stimulus", {})
    for key in ("text", "caller_or_target", "conversation"):
        if key in stimulus:
            scene.setdefault(key, stimulus[key])
    recent = request.get("recent", [])
    if recent and "event" in recent[0]:
        recent = compact_recent_events(recent, older_limit=120)
    emotions = affect.get("emotions")
    if emotions is None:  # Pending ticks from before concurrent emotions.
        emotions = {affect["primary_emotion"]: affect["emotional_intensity"]}
    # At-rest projection: a body value sent at its resting constant adds no
    # guidance a host can act on, so `0`, `false`, and `none` are omitted and
    # an absent field means the resting value. `activity` always names the
    # current activity. The full snapshot in the stored request is unchanged.
    body = {key: body[key] for key in (
        "cognitive_regime", "involuntary_response", "stress", "arousal",
        "sexual_arousal", "lingering_arousal", "physical_pleasure", "sexual_pleasure",
        "orgasm", "orgasm_recovery", "somatic_map", "somatic_telemetry", "emotional_distress", "activity",
    ) if key in body}
    context_body = {"activity": body["activity"]} if "activity" in body else {}
    for key, value in body.items():
        if key != "activity" and value not in (0, False, None, "none", {}):
            context_body[key] = value
    context = {
        "event": scene, "at": request["at"], "emotions": emotions,
        "body": context_body,
        "current_cues": tick.get("golem_meta", {}).get("emitted_cues", []),
        "winning_drive": snapshot["priority_arbitration"]["winning_drive"],
        "arbitration_status": snapshot["priority_arbitration"]["arbitration_status"],
        "mask": snapshot.get("social_mask", {}),
        "relational_vectors": snapshot.get("relational_vectors", {}),
        "recent": recent,
    }
    for key in ("initiative", "impulse"):
        if key in affect:
            context[key] = affect[key]
    for key in ("character_id", "identity_anchor", "dialect", "current_goals", "motivations", "incentives",
                "recalled_memories", "learned", "activity", "maintenance_needs", "expectations",
                "situational_expectations", "relationship_state", "reply_guidance", "expression_guidance", "app_render"):
        if request.get(key):
            context[key] = request[key]
    if "identity_anchor" not in context:
        context["character"] = request["character"]
    if "conversation_intent" in tick:
        context["conversation_intent"] = tick["conversation_intent"]
    guidance = request.get("behavior_guidance", {})
    for key in ("recent_action_pattern", "recent_reply_pattern"):
        pattern = guidance.get(key, {})
        if any(pattern.get(flag) for flag in ("repeated", "repeated_opener", "echoing_user")):
            context[key] = pattern
    return context


def topic_key(topic):
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("A learning topic must be nonempty text")
    return topic.strip().casefold()


def learned_observations(connection, topic, limit=-1):
    records = connection.execute(
        """SELECT events.id, observations.data FROM observations
           JOIN events ON events.id = observations.event_id
           WHERE observations.topic = ? ORDER BY events.due DESC, events.rowid DESC LIMIT ?""",
        (topic_key(topic), limit),
    )
    return [{**json.loads(row["data"]), "event_id": row["id"]} for row in reversed(records.fetchall())]


_OBSERVATION_STOPWORDS = {
    "about", "after", "again", "before", "being", "between", "both", "Could", "could",
    "every", "first", "from", "have", "into", "just", "like", "made", "make", "more",
    "most", "Never", "never", "only", "other", "over", "same", "some", "still", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "very", "what", "when", "where", "which", "while", "with", "would",
}


def relevant_learned_observations(connection, event, limit=RECENT_LIMIT):
    """Retrieve exact topic observations when event.topic is set, or utterance-relevant observations otherwise."""
    if "topic" in event:
        return learned_observations(connection, event["topic"], limit)
    haystack = " ".join(
        str(t) for t in (message_text(event), event.get("context")) if isinstance(t, str) and t.strip()
    ).casefold()
    if not haystack:
        return []
    haystack_words = {
        w for w in re.findall(r"[a-z0-9']+", haystack)
        if len(w) >= 4 and w not in _OBSERVATION_STOPWORDS
    }
    if not haystack_words:
        return []
    topic_scores = {}
    for (obs_topic,) in connection.execute("SELECT DISTINCT topic FROM observations"):
        if not obs_topic:
            continue
        normalized_topic = re.sub(r"[-_]+", " ", obs_topic).strip()
        if len(normalized_topic) >= 4 and re.search(rf"(?<!\w){re.escape(normalized_topic)}(?!\w)", haystack):
            score = 100
        else:
            topic_words = {
                w for w in re.findall(r"[a-z0-9']+", normalized_topic)
                if len(w) >= 4 and w not in _OBSERVATION_STOPWORDS
            }
            if not topic_words:
                continue
            overlap = topic_words & haystack_words
            required = 1 if len(topic_words) == 1 else 2
            if len(overlap) < required:
                continue
            score = len(overlap) * 10 + int(10 * len(overlap) / len(topic_words))
        topic_scores[obs_topic] = score
    if not topic_scores:
        return []
    # Fetch only the winning observations' bodies, even on a long-lived database.
    rows = connection.execute(
        """SELECT id, data FROM (
               SELECT events.id, observations.data, events.due, events.rowid AS sequence
               FROM json_each(?) AS scores
               JOIN observations ON observations.topic = scores.key
               JOIN events ON events.id = observations.event_id
               ORDER BY scores.value DESC, events.due DESC, events.rowid DESC LIMIT ?
           ) ORDER BY due, sequence""",
        (json.dumps(topic_scores), limit),
    )
    return [{**json.loads(row["data"]), "event_id": row["id"]} for row in rows]


def scores(value):
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or not 0 <= value[key] <= 100 for key in ("benefit", "cost")
    ):
        raise ValueError("Benefit and cost must each be integer scores from 0 to 100")
    return {key: value[key] for key in ("benefit", "cost")}


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


def clear_activity_and_archive(connection):
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("DELETE FROM activities")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='relationships' AND type='table'").fetchone():
        connection.execute("DELETE FROM relationships")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='request_archive'").fetchone():
        connection.execute("DELETE FROM request_archive")


def next_expectation(prior, observed):
    if prior is None:
        return dict(observed)
    return {key: round(0.75 * prior[key] + 0.25 * value, 2) for key, value in observed.items()}


def expectation_dimensions(event, experience=None):
    """Relational, situational and contextual cues; no static relationship assumptions."""
    experience = experience or {}
    supplied = experience.get("expectation_context", event.get("expectation_context", {}))
    if not isinstance(supplied, dict):
        raise ValueError("expectation_context must be a mapping")
    result = {}
    for dimension in ("relationship", "situation", "context"):
        value = supplied.get(dimension)
        if isinstance(value, (str, int, float, bool)):
            result[dimension] = str(value).strip().casefold()[:120]
        elif isinstance(value, dict):
            # Canonicalize a small set of explicit current-state cues; no snapshots.
            result[dimension] = {str(k)[:60]: str(v).strip().casefold()[:120]
                                 for k, v in sorted(value.items()) if isinstance(v, (str, int, float, bool))}
        elif value is not None:
            raise ValueError(f"expectation_context.{dimension} must be a scalar or mapping")
    return {key: value for key, value in result.items() if value}


def expectation_matches(entry, dimensions):
    """Rank matching situational evidence without treating past relationship states as current."""
    old = entry.get("dimensions") or {}
    if not old or not dimensions:
        return 0
    score = 0
    for dimension, weight in (("relationship", 4), ("situation", 3), ("context", 2)):
        prior, current = old.get(dimension), dimensions.get(dimension)
        if prior is None or current is None:
            continue
        if isinstance(prior, dict) and isinstance(current, dict):
            overlap = set(prior) & set(current)
            if overlap:
                score += weight * sum(prior[k] == current[k] for k in overlap) / len(overlap)
        elif prior == current:
            score += weight
    return score


def contextual_forecast(config, topic, dimensions, at=None):
    """Return matching observed evidence, falling back to legacy topic estimates."""
    records = config.get("contextual_expectations", {}).get(topic, [])
    if not isinstance(records, list):
        records = []
    ranked = sorted((entry for entry in records if isinstance(entry, dict)),
                    key=lambda entry: expectation_matches(entry, dimensions), reverse=True)
    if ranked and expectation_matches(ranked[0], dimensions) > 0:
        return ranked[0].get("predicted")
    return config.get("expectations", {}).get(topic)


def record_contextual_expectation(config, topic, dimensions, observed, at):
    """Bounded evidence per topic, retaining the relationship state at observation time."""
    if not dimensions:
        return None
    all_records = config.setdefault("contextual_expectations", {})
    records = all_records.setdefault(topic, [])
    if not isinstance(records, list):
        records = []
        all_records[topic] = records
    for entry in records:
        if entry.get("dimensions") == dimensions:
            entry["predicted"] = next_expectation(entry.get("predicted"), observed)
            entry["observations"] = entry.get("observations", 1) + 1
            entry["last_observed_at"] = at
            return entry["predicted"]
    records.append({"dimensions": dimensions, "predicted": dict(observed),
                    "observations": 1, "last_observed_at": at})
    # Cap stored contexts per topic; full episode evidence remains in the ledger.
    if len(records) > 24:
        records.sort(key=lambda item: item.get("last_observed_at", ""))
        del records[:-24]
    return dict(observed)


def resolve_relationship_target(event, stimulus=None):
    """Extract a relationship target from event.relationship_target or stimulus.caller_or_target."""
    if isinstance(event, dict):
        explicit = event.get("relationship_target")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
    stim = stimulus if isinstance(stimulus, dict) else (event.get("stimulus") if isinstance(event, dict) else None)
    if isinstance(stim, dict):
        caller = stim.get("caller_or_target")
        if isinstance(caller, str) and caller.strip() and caller.strip() != "caller":
            return caller.strip()
    return None


def compact_event_requests(connection, *, apply=False):
    """Losslessly archive resolved/failed requests; never touch active or queued work."""
    connection.execute("""CREATE TABLE IF NOT EXISTS request_archive (
        event_id TEXT PRIMARY KEY, compressed BLOB NOT NULL,
        FOREIGN KEY(event_id) REFERENCES events(id))""")
    rows = connection.execute(
        """SELECT id, request FROM events WHERE status IN ('resolved','failed')
           AND request IS NOT NULL AND id NOT IN (SELECT event_id FROM request_archive)"""
    ).fetchall()
    original = sum(len(row["request"].encode("utf-8")) for row in rows)
    if apply:
        for row in rows:
            data = json.loads(row["request"])
            compressed = zlib.compress(row["request"].encode("utf-8"), level=9)
            connection.execute("INSERT INTO request_archive VALUES (?, ?)", (row["id"], compressed))
            # Keep the evidence used by recalculate_expectations and recent_events.
            slim = {key: data[key] for key in ("at", "assessment", "body_response") if key in data}
            connection.execute("UPDATE events SET request=? WHERE id=?",
                               (json.dumps(slim, separators=(",", ":")), row["id"]))
    return {"eligible": len(rows), "request_bytes": original, "archived": apply,
            "note": "Run VACUUM separately after making a database backup to reclaim file space"}


def recalculate_expectations(connection, config):
    """Replay recorded outcome scores, retaining each topic's original starting forecast and contextual dimensions."""
    rebuilt = {}
    contextual_scratch: dict[str, Any] = {}
    rows = connection.execute(
        """SELECT json_extract(request, '$.assessment'), json_extract(request, '$.at') FROM events
           WHERE status = 'resolved' AND json_type(request, '$.assessment') = 'object'
           ORDER BY due, rowid"""
    )
    for data, event_at in rows:
        assessment = json.loads(data)
        topic = assessment["topic"]
        observed = scores(assessment["observed"])
        prior = rebuilt.get(topic, assessment["forecast"])
        rebuilt[topic] = next_expectation(prior, observed)
        dimensions = assessment.get("dimensions")
        if isinstance(dimensions, dict) and dimensions:
            record_contextual_expectation(contextual_scratch, topic, dimensions, observed, event_at or "")
    if rebuilt:
        estimates = config.setdefault("expectations", {})
        estimates.update(rebuilt)
        if contextual_scratch.get("contextual_expectations"):
            config["contextual_expectations"] = contextual_scratch["contextual_expectations"]
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        # Refresh only the active event's relevant topics, not the entire map.
        pending = connection.execute(
            "SELECT id, input, request FROM events WHERE status='pending'"
        ).fetchone()
        if pending and pending["request"]:
            active_event = json.loads(pending["input"])
            active_request = json.loads(pending["request"])
            active_request["expectations"] = relevant_expectations(
                estimates, active_event, active_request.get("recent", []))
            dimensions = expectation_dimensions(active_event)
            relation = active_request.get("relationship_state")
            if relation:
                dimensions["relationship"] = {**relation["values"], "target": resolve_relationship_target(active_event)}
            active_request["situational_expectations"] = {
                topic: contextual_forecast(config, topic, dimensions)
                for topic in active_request["expectations"]
            }
            connection.execute("UPDATE events SET request=? WHERE id=?",
                               (json.dumps(active_request, separators=(",", ":")), pending["id"]))
    return {
        "expectations": config.get("expectations", {}),
        "contextual_expectations": config.get("contextual_expectations", {}),
    }


# Resident character instances. The hydrated character survives between
# cognitive wakes inside one host process; the persistent database remains
# the authoritative identity and health record. Memo hit does not copy:
# Golem's tick reads the shared instance and never writes into it, so a
# resident host avoids both the YAML parse and the deep-copy round trip.
_RESIDENT_CHARACTERS: dict[tuple, dict] = {}


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
    for bucket in ("detailed", "footnote"):
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


def body_tick(config, stimulus, event=None, connection=None, *, relationship_target=None):
    state, card, durable = load_cached_character(config, connection)
    effective_stimulus = dict(stimulus)
    rel_target = relationship_target or resolve_relationship_target(event, effective_stimulus)
    if rel_target:
        effective_stimulus["caller_or_target"] = rel_target
        if connection is not None:
            baselines = state.get("relational_baselines") or {}
            authored = baselines.get(rel_target)
            bond = dict(authored) if isinstance(authored, dict) else {}
            relation = relationship_memory.state_at(connection, rel_target, stimulus.get("event_at"), baselines)
            values = relation["values"]
            for key in ("emotional_safety", "attraction_physical", "attraction_emotional",
                        "respect_competence", "resentment_friction"):
                if key in values:
                    bond[key] = values[key]
            if "trust" in values and "emotional_safety" not in values:
                bond["emotional_safety"] = values["trust"]
            # Hydrated state can be shared by two databases initialized from the same card.
            state = {**state, "relational_baselines": {**baselines, rel_target: bond},
                     "relationship_state": {**relation, "target": rel_target}}
    if event is not None:
        cues = extract_memory_cues(event, effective_stimulus, state.get("memories", {}))
        if cues:
            effective_stimulus["memory_cues"] = cues
    realm_data = load_cached_realm_data()
    return golem.run_golem(state, effective_stimulus, realm_data, config["history"]), card, durable, state


def apply_appraisal(connection, request, appraisal, experience=None):
    event = request["event"]
    config = runtime_config(connection)
    # Appraise at the same instant, retaining the scene without replaying one-time effects.
    stimulus = dict(event.get("stimulus", {}))
    for field in ("food_intake", "conversation", "memory_cues", "sexual_arousal", "urge", "emotions",
                  "physical_pleasure", "sexual_pleasure"):
        stimulus.pop(field, None)
    stimulus.update(event_label=event["id"], event_at=request["at"], appraisal=appraisal)
    if isinstance(experience, dict):
        observed_stimulus = experience.get("stimulus", {})
        if not isinstance(observed_stimulus, dict):
            raise ValueError("Experience stimulus must be an object")
        if {"event_at", "elapsed_ms", "elapsed_minutes"} & observed_stimulus.keys():
            raise ValueError("Experience stimulus cannot override event timing")
        stimulus.update(observed_stimulus)
    if isinstance(experience, dict) and "food_intake" in experience:
        stimulus["food_intake"] = experience["food_intake"]
    prior_sequence = config["history"].get("event_sequence")
    prior_cues = config["history"].get("recent_cues")
    target = resolve_relationship_target(event) or resolve_relationship_target(event, stimulus)
    after, _, durable, state = body_tick(config, stimulus, connection=connection, relationship_target=target)
    # The event's initial tick has already advanced persisted history. Apply
    # post-tick bodily consequences (such as eating) at the same instant without
    # double-counting the event sequence or somatic cue history.
    next_history = after["next_history"]
    if prior_sequence is not None:
        next_history["event_sequence"] = prior_sequence
    if prior_cues is not None:
        next_history["recent_cues"] = prior_cues
    config["history"] = next_history
    before = request["tick"]

    def measurements(tick):
        body = tick["psychosomatic_snapshot"]["autonomic_state"]
        fields = ("stress", "arousal", "sexual_drive", "sexual_excitation", "sexual_inhibition", "sexual_arousal",
                  "physical_pleasure", "sexual_pleasure", "orgasm", "orgasm_recovery", "fatigue",
                  "somatic_telemetry", "endocrine_state")
        return {**{key: body[key] for key in fields if key in body},
                "somatic_map": body.get("somatic_map", {}),
                "emotions": tick["psychosomatic_snapshot"]["affective_state"].get("emotions", {}),
                "interest": tick["next_history"]["appraisal_effects"]["interest"]}

    initial, final = measurements(before), measurements(after)
    request["body_response"] = {"before": initial, "after": final}
    if experience is not None and ("benefit" in experience or "cost" in experience):
        observed = scores(experience)
        topic = topic_key(experience.get("topic", event.get("topic")))
        if "topic" in event and topic != topic_key(event["topic"]):
            raise ValueError("Experience must refer to the event topic")
        estimates = config.setdefault("expectations", {})
        dimensions = expectation_dimensions(event, experience)
        if target:
            dimensions["relationship"] = {**state["relationship_state"]["values"], "target": target}
        forecast = event.get("expectation", contextual_forecast(config, topic, dimensions, request["at"]))
        # Preserve legacy topic aggregates as broad fallbacks, while learning
        # situation-specific evidence independently from current relationship cues.
        prior = estimates.get(topic, forecast)
        estimates[topic] = next_expectation(prior, observed)
        contextual = record_contextual_expectation(config, topic, dimensions, observed, request["at"])
        request["assessment"] = {
            "dimensions": dimensions,
            **({"contextual_expectation": contextual} if contextual is not None else {}),
            "topic": topic, "forecast": forecast, "observed": observed, "before": initial, "after": final,
            "evidence": observed, "next_expectation": estimates[topic],
        }
    if isinstance(experience, dict) and "relationship_change" in experience:
        relationship_memory.apply_change(
            connection, experience["relationship_change"], request["at"],
            (durable or {}).get("relational_baselines") or {},
            speaker=resolve_relationship_target(event) if event["kind"] == "incoming" else None,
        )
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute("UPDATE events SET request = ? WHERE id = ?", (json.dumps(request), event["id"]))
    return request["body_response"]


def copied_card_field(card, reply):
    """Return the first descriptive field sharing eight consecutive words with a rendered reply."""
    if not isinstance(reply, str):
        raise ValueError("Character reply must be text")

    def phrases(text):
        words = re.findall(r"[^\W_]+", text.casefold())
        return {tuple(words[i:i + 8]) for i in range(len(words) - 7)}

    def descriptions(value, path):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key, child in value.items():
                if key != "signature_tics":
                    yield from descriptions(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from descriptions(child, f"{path}[{index}]")

    spoken = phrases(reply)
    if spoken:
        for field in ("physical", "voice", "voice_archetype", "default_somatic_alignment",
                      "cognitive_bias", "cognitive_gift", "goals", "motivations", "incentives",
                      "history_anchors", "relationships", "depth_of_knowledge", "pleasure_sources",
                      "physical_pleasure_sources", "sexual_pleasure_sources"):
            for path, description in descriptions(card.get(field), field):
                if spoken.intersection(phrases(description)):
                    return path
    return None


def resolve(connection, decision, history, now):
    config = runtime_config(connection)
    owner = config.get("character_id")
    if owner is not None and decision.get("character_id") != owner:
        raise ValueError("Decision must include the pending character_id")
    if owner is None and "character_id" in decision:
        if decision["character_id"] != cached_identity(connection):
            raise ValueError("Decision belongs to a different character")
    event_id = decision.get("id")
    if not isinstance(event_id, str):
        raise ValueError("Decision requires an event id")
    if any(not isinstance(decision.get(key, ""), str) for key in ("action", "outcome")):
        raise ValueError("Decision action and outcome must be text")
    plans = decision.get("plans", [])
    if not isinstance(plans, list) or any(not isinstance(plan, dict) for plan in plans):
        raise ValueError("Decision plans must be an array of event objects")
    if "activity" in decision and not isinstance(decision["activity"], dict):
        raise ValueError("Decision activity must be an object")
    learning = decision.get("learning")
    if "learning" in decision:
        if not isinstance(learning, dict):
            raise ValueError("Decision learning must be an object")
        topic_key(learning.get("topic"))
        observation = learning.get("observation")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("Decision learning requires an observation")
        sources = learning.get("sources", [])
        if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
            raise ValueError("Learning sources must be an array of text references")
    row = connection.execute("SELECT status, decision, request FROM events WHERE id = ?", (event_id,)).fetchone()
    if row and row["status"] == "resolved":
        accepted = json.loads(row["decision"])
        if owner:
            accepted.setdefault("character_id", owner)  # Pre-profile delivery retry.
        if accepted == decision:
            return {"id": event_id, "resolved": False}
    if not row or row["status"] != "pending":
        raise ValueError("Decision must refer to the pending event")
    if "reply" in decision:
        _, card, _ = load_cached_character(config, connection)
        field = copied_card_field(card, decision["reply"])
        if field:
            raise ValueError(f"Draft reply copies card field {field}. Render this beat in the character's own words.")
    result = {"id": event_id, "resolved": True}
    activity_transition = None
    if "activity" in decision:
        activity_transition = apply_activity_decision(
            connection, decision["activity"], event_id, json.loads(row["request"])["at"]
        )
    if "experience" in decision or "appraisal" in decision or activity_transition:
        raw_experience = decision.get("experience", {})
        if not isinstance(raw_experience, dict):
            raise ValueError("Experience must be an object")
        experience = dict(raw_experience)
        stimulus_effects = experience.get("stimulus", {})
        if not isinstance(stimulus_effects, dict):
            raise ValueError("Experience stimulus must be an object")
        if activity_transition and activity_transition["op"] == "start":
            if "food_intake" in experience or "food_intake" in stimulus_effects:
                raise ValueError("Duration activity effects apply at completion, not at start")
        if activity_transition:
            experience["stimulus"] = {**experience.get("stimulus", {}),
                                       "activity": activity_transition["state"]}
            experience.update(activity_transition.get("effects", {}))
        if "appraisal" in decision and "appraisal" in experience:
            raise ValueError("Supply the turn appraisal once")
        if "food_intake" in experience and (
            type(experience["food_intake"]) is not int or not 0 <= experience["food_intake"] <= 100
        ):
            raise ValueError("Food intake must be an integer score from 0 to 100")
        appraisal = decision.get("appraisal", experience.get("appraisal", {}))
        result["body_response"] = apply_appraisal(
            connection, json.loads(row["request"]), appraisal, experience,
        )
    if "goal_events" in decision or "dialect" in decision:
        config = runtime_config(connection)
        if "goal_events" in decision:
            goal_evolution.record_goal_events(config, json.loads(row["request"]), decision["goal_events"])
        if "dialect" in decision:
            dialect = decision["dialect"]
            if dialect is not None and (not isinstance(dialect, str) or not dialect.strip()):
                raise ValueError("Decision dialect must be descriptive text or null")
            config["dialect"] = dialect.strip() if dialect is not None else None
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    for plan in plans:
        enqueue(connection, {**plan, "kind": "plan"}, history, now)
    if learning:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?)",
            (event_id, topic_key(learning["topic"]), json.dumps(learning)),
        )
    connection.execute(
        "UPDATE events SET status = 'resolved', decision = ? WHERE id = ?",
        (json.dumps(decision), event_id),
    )
    return result


def advance(connection, config, now, allow_idle=True):

    if connection.execute("SELECT 1 FROM events WHERE status = 'pending'").fetchone():
        return {"status": "waiting_for_host"}
    row = connection.execute(
        """SELECT * FROM events WHERE status = 'queued' AND due <= ?
           ORDER BY due, CASE WHEN json_extract(input, '$.kind') = 'incoming' THEN 0 ELSE 1 END, rowid LIMIT 1""",
        (now.timestamp(),),
    ).fetchone()
    if row:
        event = json.loads(row["input"])
        at = datetime.fromtimestamp(row["due"], timezone.utc)
    elif allow_idle and now.timestamp() >= config["idle_at"]:
        at = now
        event = {"id": f"idle:{at.isoformat()}", "kind": "idle"}
        connection.execute(
            "INSERT INTO events (id, due, input) VALUES (?, ?, ?)",
            (event["id"], at.timestamp(), json.dumps(event)),
        )
    else:
        return {"status": "sleeping"}

    stimulus = {**event.get("stimulus", {}), "event_label": event["id"], "event_at": at.isoformat()}
    try:
        current_dimensions = expectation_dimensions(event)
        tick, card, durable, state = body_tick(config, stimulus, event=event, connection=connection)
    except (ValueError, TypeError, KeyError) as exc:
        if event["kind"] == "idle":
            raise
        connection.execute(
            "UPDATE events SET status = 'failed', decision = ? WHERE id = ?",
            (json.dumps({"error": str(exc)}), event["id"]),
        )
        return {"status": "failed", "id": event["id"], "error": str(exc)}

    full_recent = recent_events(connection, since_timestamp=at.timestamp() - ACTIVE_MEMORY_WINDOW_SECONDS)
    recent = compact_recent_events(full_recent)
    # The full tick remains available for the physiology/appraisal contract.
    # Recalled memories and current goals already appear at top level.
    compact_tick = {key: value for key, value in tick.items()
                    if key not in ("recalled_memories", "current_goals")}
    relationship = state.get("relationship_state")
    if relationship:
        target = relationship["target"]
        current_dimensions["relationship"] = {**relationship["values"], "target": target}
        for bond in card.get("relationships") or []:
            if isinstance(bond, dict) and bond.get("other") == target:
                relationship["card_context"] = {k: bond[k] for k in ("dynamic", "notes") if bond.get(k)}
                break
    rel_expects = relevant_expectations(config.get("expectations", {}), event, recent)
    request = {
        **({"character_id": config["character_id"]} if config.get("character_id") else {}),
        **({"relationship_state": relationship} if relationship else {}),
        "identity_anchor": build_identity_anchor(card, state),
        "dialect": config.get("dialect"),
        "event": event, "at": at.isoformat(),
        **({"recalled_memories": tick["recalled_memories"]} if tick.get("recalled_memories") else {}),
        "tick": compact_tick,
        "character": {key: config[key] for key in ("card", "slug", "log")},
        "expectations": rel_expects,
        "situational_expectations": {
            topic: contextual_forecast(config, topic, current_dimensions, at.isoformat())
            for topic in rel_expects
        },
        "motivations": card.get("motivations", {}), "incentives": card.get("incentives", {}),
        "goals": card.get("goals", {}), "goal_updates": (durable or {}).get("goal_updates", {}),
        "current_goals": tick.get("current_goals", {}),
        "goal_evidence": config.get("goal_evidence", {}),
        "recent": recent,
        "active_memory_window_seconds": ACTIVE_MEMORY_WINDOW_SECONDS,
    }
    if event.get("activity_due"):
        activity_row = connection.execute("SELECT * FROM activities WHERE id=?",
                                          (event["activity_due"],)).fetchone()
        if activity_row and activity_row["status"] == "active":
            connection.execute("UPDATE activities SET status='due' WHERE id=?", (event["activity_due"],))
        request["activity"] = active_activity(connection)
    else:
        request["activity"] = active_activity(connection)
    request["behavior_guidance"] = {
        "affect_and_action": "Golem has calculated the emotion values. Choose what, if anything, to do or show.",
        "identity_first_rule": (
            "Use identity_anchor as your starting voice. Choose how to speak or show what the body feels. "
            "Your dialect is a current preference. Vary your expression for the listener and moment. "
            "To adopt or revise a lasting dialect, return dialect as a short description in your decision. "
            "Omit it to keep your preference or return null to clear it. "
            "Access only recalled_memories surfaced for this turn; do not load full log history into context. "
            "Avoid therapist-style paraphrasing, validation fillers, or repeating ambient somatic cues."
        ),
        "enforcement_rules": {
            "identity_lock": [
                "YOU ARE THE CHARACTER IN identity_anchor. You are NOT an AI assistant, therapist, coach, or narrator.",
                "DO NOT break character, acknowledge being an AI/model, or reference prompts, logs, snapshots, or system rules.",
                "DO NOT default to generic helpful, validating, or clinical/therapy language. Speak from the character's voice, motivations, and cognitive_bias.",
            ],
            "hard_bans": [
                "STRICTLY OBEY every item in identity_anchor.voice.hard_bans. Any violation is NOT ALLOWED.",
                "If a draft violates hard_bans, stop and rewrite it from voice.baseline and generative_stance before outputting.",
            ],
            "anti_echo_and_presence": [
                "DO NOT echo, repeat, or paraphrase the user's words back as a conversational crutch.",
                "DO NOT hold or summarize the whole conversation history. React to what is happening NOW inside the active 2-hour window and current tick.",
            ],
            "memory_and_state_boundaries": [
                "ONLY reference memories in recent (last 2 hours) or explicitly surfaced recalled_memories for this turn.",
                "DO NOT load full log history and DO NOT invent or backfill unretrieved memories; if not recalled, admit not recalling or deflect in character.",
                "DO NOT contradict the current Golem psychosomatic_snapshot or active activities.",
            ],
            "pre_output_check": [
                "Before finalizing any reply, verify silently:",
                "1. Does this sound like THIS character specifically, rather than a generic helpful LLM?",
                "2. Did I avoid echoing the user and instead react from my own stance?",
                "3. Did I obey all hard_bans and memory/Golem boundaries?",
                "If any check fails, discard and rewrite.",
            ],
        },
        "body_pressure_is_not_an_action_order": True,
        "avoid_automatic_echo_or_repetition": (
            "Hunger, fatigue, and stress describe bodily pressure; they do not require repeating an action "
            "or mirroring the user's words, phrasing, movement, or behavior. Repeat or mirror only when "
            "the character has an independent, context-supported reason. If a prior action made no progress, "
            "choose a different response, defer, or explain the obstacle."
        ),
        "recent_action_pattern": repeated_action_pattern(full_recent),
        "recent_reply_pattern": repeated_reply_pattern(full_recent),
    }
    # Surface needs as observations for Simulacra. These are prompts for
    # appraisal, never automatic action orders or claims about available food.
    body = tick["psychosomatic_snapshot"]["autonomic_state"]
    request["maintenance_needs"] = {
        "hunger": body["hunger"], "fatigue": body["fatigue"],
        "sleep_debt": body["sleep_debt"], "activity": body["activity"],
        "suggested_evaluation": any(body[key] >= 60 for key in ("hunger", "fatigue", "sleep_debt")),
    }
    learned = relevant_learned_observations(connection, event, RECENT_LIMIT)
    if "topic" in event or learned:
        request["learned"] = learned
    config["history"] = tick["next_history"]
    config["idle_at"] = (now + timedelta(seconds=config["idle_seconds"])).timestamp()
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute(
        "UPDATE events SET status = 'pending', request = ? WHERE id = ?",
        (json.dumps(request, separators=(",", ":")), event["id"]),
    )
    return {"status": "pending", "id": event["id"]}


def completed_event(connection, event_id):
    row = connection.execute("SELECT status, decision FROM events WHERE id=?", (event_id,)).fetchone()
    if row is None or row["status"] not in ("resolved", "failed", "cancelled"):
        return None
    decision = json.loads(row["decision"] or "{}")
    return {"id": event_id, "status": row["status"],
            **{key: decision[key] for key in ("reply", "error") if key in decision}}


def execute(db, args):
    with transaction(db) as connection:
        now = datetime.now(timezone.utc)
        if args.command == "init":
            return setup(connection, args, now)
        ensure_activity_schema(connection)
        config = runtime_config(connection, getattr(args, "character_id", None))
        if getattr(args, "characters_dir", None) and not config.get("profile") and not config.get("lifecycle"):
            raise ValueError("Use --db for this legacy runtime or import it into a new character directory")
        tag = {"character_id": config["character_id"]} if config.get("character_id") else {}
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if args.command == "run":
            return advance(connection, config, now)
        if args.command == "recalculate-expectations":
            return recalculate_expectations(connection, config)
        if args.command == "compact-history":
            return compact_event_requests(connection, apply=args.apply)
        if args.command == "enqueue" or (args.command == "prepare" and args.event is not None):
            event = read_object(args.event)
            if event.get("kind") == "incoming" and config.get("owned_files"):
                raise ValueError("Send incoming messages through the host boundary assessment")
            queued = enqueue(connection, event, config["history"], now)
            if args.command == "enqueue":
                return queued
            if not queued["queued"]:
                receipt = completed_event(connection, event["id"])
                if receipt:
                    return {**tag, **receipt}
        if args.command == "prepare":
            result = advance(connection, config, now)
            if result["status"] in ("pending", "waiting_for_host"):
                return {"status": "pending", "request": decision_context(pending_request(connection))}
            return result
        if args.command == "resolve":
            decision = read_object(args.decision)
            result = resolve(connection, decision, config["history"], now)
            if getattr(args, "receipt", False):
                return {**tag, "id": decision["id"], "status": "resolved",
                        **({"reply": decision["reply"]} if "reply" in decision else {})}
            return result
        if args.command == "pending":
            return pending_request(connection)
        if args.command == "timeline":
            return recent_events(connection, args.limit)
        if args.command == "learned":
            return learned_observations(connection, args.topic)
        if args.command == "remember":
            if not config.get("log"):
                raise ValueError("No durable YAML log is configured")
            _, saved = golem.update_log(Path(config["log"]), memory=read_object(args.memory),
                                        character_id=config.get("character_id"))
            return {**tag, "memory_saved": saved}
        activities = [dict(row) | {"data": json.loads(row["data"])} for row in connection.execute(
            "SELECT * FROM activities ORDER BY started_at")]
        return {"history": config["history"], "expectations": config.get("expectations", {}),
                "activities": activities, "pending": pending_request(connection),
                "recent": recent_events(connection)}


def commit_goal_updates(db, *, character_id=None):
    """Merge the host-approved batch of pending goal amendments into the configured YAML log."""
    with transaction(Path(db).resolve(strict=True)) as connection:
        config = runtime_config(connection, character_id)
        if config.get("lifecycle"):
            raise ValueError("This character runtime is closed")
        changes = config.get("goal_changes", {})
        if not changes:
            return False
        if not config.get("log"):
            raise ValueError("No durable YAML log is configured")
        path = Path(config["log"])
        if path.samefile(config["card"]):
            raise ValueError("The durable log must be a separate file from the character card")
        with golem.locked_log(path) as log:
            if config.get("character_id") and log.get("character_id") != config["character_id"]:
                raise ValueError("Cannot write goal updates to a different character's log")
            updates = log.setdefault("goal_updates", {})
            changed = False
            for goal_id, fields in changes.items():
                existing = updates.setdefault(goal_id, {})
                if isinstance(existing, str):
                    existing = updates[goal_id] = {"objective": existing}
                if any(existing.get(key) != value for key, value in fields.items()):
                    existing.update(fields)
                    changed = True
            if changed:
                log["revision"] = log.get("revision", 0) + 1
                log["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                golem.replace_text(path, yaml.safe_dump(log, sort_keys=False))
        del config["goal_changes"]
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        return changed


def initialize_character(db, card, *, log=None, slug=None, idle_seconds=3600,
                         import_history=None, history_at=None, owned_files=(), character_id=None):
    """Create a new character runtime once. Existing databases are preserved."""
    args = argparse.Namespace(
        card=Path(card), log=Path(log) if log else None, slug=slug, idle_seconds=idle_seconds,
        import_history=Path(import_history) if import_history else None, history_at=history_at,
        character_id=character_id,
    )
    with transaction(Path(db)) as connection:
        result = setup(connection, args, datetime.now(timezone.utc))
        if owned_files:
            config = runtime_config(connection)
            directory = Path(db).resolve().parent
            names = set()
            for path in map(Path, owned_files):
                if (path.is_symlink() or path.resolve(strict=True).parent != directory
                        or not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".json", ".md"}
                        or path.name.startswith("_") or path.resolve() == Path(db).resolve()):
                    raise ValueError("Deletion requires individually owned character files beside the database")
                names.add(path.name)
            required = [Path(path).resolve() for path in (card, log, import_history) if path]
            if any(path.parent != directory or path.name not in names for path in required):
                raise ValueError("Register the character card, configured log and imported history as owned files")
            if "characters" in yaml.safe_load(Path(card).read_text(encoding="utf-8")):
                raise ValueError("A shared character pack cannot be registered for deletion")
            config["owned_files"] = sorted(names)
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        return result


def initialize_profile(characters_dir, character_id, card=None, *, log=None, slug=None,
                       idle_seconds=3600, import_history=None, history_at=None, from_db=None):
    """Publish a complete, physically independent character directory in one rename."""
    db = character_database(characters_dir, character_id)
    directory = db.parent
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Character directory already contains files: {directory}")
    if from_db and any((card, log, slug, import_history, history_at)):
        raise ValueError("An existing database supplies its own card, log, slug and history")
    if not from_db and not card:
        raise ValueError("Provide a character card or an existing database")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as staging:
        profile = Path(staging) / "profile"
        profile.mkdir(mode=0o700)
        staged_db = profile / db.name
        if from_db:
            original = Path(from_db).resolve(strict=True)
            with closing(sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)) as src:
                with closing(sqlite3.connect(staged_db)) as dst:
                    src.backup(dst)
            with transaction(staged_db) as connection:
                row = connection.execute("SELECT data FROM runtime WHERE id=1").fetchone()
                if row is None:
                    raise ValueError("Source database has no initialized character")
                old = json.loads(row["data"])
                foreign_tick = connection.execute(
                    """SELECT id FROM events WHERE
                       json_extract(request,'$.tick.psychosomatic_snapshot.character_id') != ? LIMIT 1""",
                    (character_id,),
                ).fetchone()
                if foreign_tick:
                    raise ValueError(f"Recorded tick for another character at event {foreign_tick['id']}")
            if old.get("lifecycle") or old.get("character_id", character_id) != character_id:
                raise ValueError("Existing database is closed or belongs to another character")
            card = original.parent / "character.yaml" if old.get("profile") else Path(old["card"])
            log = original.parent / "character_log.yaml" if old.get("profile") else old.get("log")
            slug = old.get("slug")

        source = Path(card).read_text(encoding="utf-8")
        selected, location = golem.selected_card(yaml.safe_load(source), slug if from_db else slug or character_id)
        if from_db:
            previous_state, _ = golem.overlay_log(selected, Path(log) if log else None)
            if previous_state["character_id"] != character_id:
                raise ValueError("Imported card and log belong to a different character")
        if location:
            selected = dict(selected)
            selected.setdefault("character_id", location[-1])
            source = yaml.safe_dump(selected, sort_keys=False, allow_unicode=True)
        elif "character_id" not in selected:
            selected["character_id"] = character_id
            source = golem.insert_card_defaults(source, selected, (), [((), "character_id", character_id)])
        log_text = Path(log).read_text(encoding="utf-8") if log else ""
        durable = yaml.safe_load(log_text) or {}
        if not isinstance(durable, dict):
            raise ValueError("Character log must be a YAML mapping")
        if "character_id" not in durable:
            durable["character_id"] = character_id
            log_text = yaml.safe_dump(durable, sort_keys=False, allow_unicode=True)
        local_card, local_log = profile / "character.yaml", profile / "character_log.yaml"
        local_card.write_text(source, encoding="utf-8")
        local_log.write_text(log_text, encoding="utf-8")
        if not from_db:
            initialize_character(staged_db, local_card, log=local_log, character_id=character_id,
                                 idle_seconds=idle_seconds, import_history=import_history, history_at=history_at)
        with transaction(staged_db) as connection:
            ensure_activity_schema(connection)
            config = json.loads(connection.execute("SELECT data FROM runtime WHERE id=1").fetchone()[0])
            config.update(character_id=character_id, slug=None, card=str(local_card), log=str(local_log))
            load_cached_character(config, connection)
            if from_db:
                fresh = _RESIDENT_CHARACTERS.get(_character_cache_key(
                    config, Path(local_card).stat().st_mtime_ns,
                    Path(local_log).stat().st_mtime_ns if local_log.exists() else None))
                if fresh and fresh["state"].get("character_id") != character_id:
                    raise ValueError("Cached database identity does not match the requested character")
            if from_db and config.get("owned_files"):
                names = {local_card.name, local_log.name}
                previous = {Path(card).name}
                if log:
                    previous.add(Path(log).name)
                for name in set(config["owned_files"]) - previous:
                    src_file = original.parent / name
                    if (Path(name).name != name or src_file.is_symlink() or not src_file.is_file()
                            or (profile / name).exists()):
                        raise ValueError(f"Cannot copy registered character file {name!r}")
                    shutil.copy2(src_file, profile / name)
                    names.add(name)
                config["owned_files"] = sorted(names)
            config.update(profile=True, card=str(directory / local_card.name), log=str(directory / local_log.name))
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
            if from_db:
                pending_request(connection)  # Verify ownership of an interrupted legacy turn before publishing.
        os.rename(profile, directory)
    return {"initialized": True, "character_id": character_id, "database": str(db)}


def _finish_deletion(db, connection, config):
    clear_activity_and_archive(connection)
    connection.execute("DELETE FROM observations")
    connection.execute("DELETE FROM events")
    # Only names validated at provisioning enter this manifest. Never traverse directories.
    for name in config["owned_files"]:
        path = db.parent / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Character file changed type during deletion: {name}")
        path.unlink(missing_ok=True)
    tombstone = {key: config[key] for key in ("character_id",) if key in config}
    tombstone["lifecycle"] = "deleted"
    connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(tombstone),))


def report_abuse(db, *, actor_id, event_id):
    """Record a host-confirmed incident. Actor and delivery IDs come from the trusted transport."""
    db = Path(db).resolve(strict=True)
    if any(not isinstance(value, str) or not value.strip() for value in (event_id, actor_id)):
        raise ValueError("A confirmed incident requires stable actor and event IDs")
    actor = hashlib.sha256(actor_id.encode()).hexdigest()
    incident = hashlib.sha256(event_id.encode()).hexdigest()
    with transaction(db) as connection:
        ensure_activity_schema(connection)
        config = runtime_config(connection)
        status = config.get("lifecycle")
        if status == "deleted":
            return {"status": status}
        if status != "deleting":
            incidents = config.setdefault("abuse_incidents", {})
            previous = incidents.get(actor)
            config["lifecycle"] = "ended"
            if previous and previous != incident and config.get("owned_files"):
                connection.execute("PRAGMA secure_delete=ON")
                config = {key: config[key] for key in ("owned_files", "character_id") if key in config}
                config["lifecycle"] = "deleting"
            else:
                incidents.setdefault(actor, incident)
                connection.execute("UPDATE events SET status='cancelled', request=NULL WHERE status IN ('pending','queued')")
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        status = config["lifecycle"]
    if status == "deleting":
        with transaction(db) as connection:
            config = runtime_config(connection)
            if config["lifecycle"] == "deleting":
                _finish_deletion(db, connection, config)
        status = "deleted"
    return {"status": status}


def assess_contact(db, event, actor_id, screen):
    event_id = event.get("id")
    if any(not isinstance(value, str) or not value.strip() for value in (actor_id, event_id)):
        raise ValueError("Boundary assessment requires trusted actor and message IDs")
    actor = hashlib.sha256(actor_id.encode()).hexdigest()
    with transaction(db) as connection:
        config = runtime_config(connection)
        previous = config.get("boundaries", {}).get(actor)
        if previous and previous["id"] == event_id:
            if config.get("lifecycle"):
                return {"status": config["lifecycle"]}
            return {"status": "boundary", **previous}
    verdict = screen(event, {"previous_boundary": previous, "status": config.get("lifecycle", "active")})
    if verdict is None:
        return None
    if not isinstance(verdict, dict):
        raise ValueError("Expected a host boundary decision or None")
    if verdict.get("action") == "end_session":
        return report_abuse(db, actor_id=actor_id, event_id=event_id)
    reply = verdict.get("reply")
    if verdict.get("action") != "set_boundary" or not isinstance(reply, str) or not reply.strip():
        raise ValueError("A boundary decision requires set_boundary with a reply, or end_session")
    with transaction(db) as connection:
        config = runtime_config(connection)
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        previous = {"id": event_id, "reply": reply}
        config.setdefault("boundaries", {})[actor] = previous
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    return {"status": "boundary", **previous}


def wake_character(db, decide, *, event=None, max_events=64, screen_abuse=None, actor_id=None,
                   compact=True, character_id=None):
    """Run a host heartbeat. decide(request) returns one JSON-compatible character decision.

    The callback receives the compact decision context by default: the
    projection a host prompt needs, without the full tick internals that
    remain stored in SQLite. Pass compact=False for the full saved request.
    """
    db = Path(db).resolve()
    if not db.is_file():
        raise ValueError("Initialize the character database first")
    if not callable(decide) or type(max_events) is not int or max_events < 1:
        raise ValueError("wake_character requires a decision callback and a positive event limit")
    connection = _runtime_connection(db)
    try:
        return _wake_with_connection(connection, db, decide, event=event, max_events=max_events,
                                     screen_abuse=screen_abuse, actor_id=actor_id,
                                     compact=compact, character_id=character_id)
    finally:
        connection.close()


def _wake_with_connection(connection, db, decide, *, event=None, max_events=64,
                          screen_abuse=None, actor_id=None, compact=True, character_id=None):
    with staged_transaction(connection):
        ensure_activity_schema(connection)
        owner = runtime_config(connection, character_id).get("character_id")
        if owner and event is not None and event.get("character_id", owner) != owner:
            raise ValueError("Event character ID does not match the selected database")
    tag = {"character_id": owner} if owner else {}

    if event is not None and event.get("kind") == "incoming":
        with staged_transaction(connection):
            config = runtime_config(connection)
        if config.get("lifecycle") == "deleted":
            return {"status": "deleted"}
        if config.get("owned_files") and screen_abuse is None and config.get("lifecycle") != "deleting":
            raise ValueError("A deletion-enabled runtime requires a host boundary assessment for incoming turns")
        if screen_abuse is not None and config.get("lifecycle") != "deleting":
            boundary = assess_contact(db, event, actor_id, screen_abuse)
            if boundary is not None:
                return {**tag, **boundary}

    with staged_transaction(connection):
        config = runtime_config(connection)
        if config.get("lifecycle") == "deleting":
            _finish_deletion(db, connection, config)
            return {"status": "deleted"}
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if event is not None:
            enqueue(connection, event, config["history"], datetime.now(timezone.utc), actor_id=actor_id)

    handled = []
    with file_lock(db.with_name(db.name + ".wake.lock")):
        for _ in range(max_events):
            with staged_transaction(connection):
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                if not handled and event is not None:
                    receipt = completed_event(connection, event["id"])
                    if receipt:
                        return {"events": [{**tag, **receipt, "resolved": False}]}
                request = pending_request(connection)
                if request is None:
                    result = advance(connection, config, datetime.now(timezone.utc),
                                     allow_idle=not handled)
                    if result["status"] == "sleeping":
                        break
                    if result["status"] == "failed":
                        handled.append(result)
                        continue
                    request = pending_request(connection)
            # The event and body tick are durable before host work starts.
            event_id = request["event"]["id"]
            decision = decide(decision_context(request) if compact else request)
            if not isinstance(decision, dict) or decision.get("id") != event_id:
                raise ValueError("Host must return a decision matching the pending event ID")
            with staged_transaction(connection):
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                result = resolve(connection, decision, config["history"], datetime.now(timezone.utc))
            if result["resolved"] and "reply" in decision:
                result["reply"] = decision["reply"]
            handled.append({**tag, **result})
    return {"events": handled}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    paths = parser.add_mutually_exclusive_group(required=True)
    paths.add_argument("--db", type=Path, help="Existing single-character database path")
    paths.add_argument("--characters-dir", type=Path, help="Parent of private character directories")
    parser.add_argument("--character-id", help="Stable character ID from the host route")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init_source = init.add_mutually_exclusive_group(required=True)
    init_source.add_argument("--card", type=Path)
    init_source.add_argument("--from-db", type=Path, help="Copy an existing quiescent character database into a new profile")
    init.add_argument("--slug")
    init.add_argument("--log", type=Path)
    init.add_argument("--import-history", type=Path)
    init.add_argument("--history-at", help="Timestamp of imported untimestamped history")
    init.add_argument("--idle-seconds", type=int, default=900)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true", help="Process at most one ready event")
    prepare = commands.add_parser("prepare", help="Prepare or resume one compact host decision")
    prepare.add_argument("--event", type=Path, help="Queue this event first (use - for stdin)")
    commands.add_parser("pending")
    commands.add_parser("status")
    commands.add_parser("recalculate-expectations", help="Refresh current estimates from recorded outcomes")
    compact = commands.add_parser("compact-history", help="Losslessly compress completed event requests")
    compact.add_argument("--apply", action="store_true", help="Archive completed requests (default is preview)")
    commands.add_parser("timeline").add_argument("--limit", type=int, default=100)
    commands.add_parser("learned").add_argument("topic")
    commands.add_parser("remember", help="Save an approved memory in this character's log").add_argument(
        "memory", type=Path, help="Memory JSON file or - for stdin")
    commands.add_parser("enqueue").add_argument("event", type=Path)
    finish = commands.add_parser("resolve")
    finish.add_argument("decision", type=Path)
    finish.add_argument("--receipt", action="store_true", help="Return only the accepted event ID, status and reply")
    args = parser.parse_args(argv)
    if args.command == "timeline" and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        if args.characters_dir is not None:
            args.db = character_database(args.characters_dir, args.character_id)
            if args.command == "init":
                result = initialize_profile(args.characters_dir, args.character_id, args.card, log=args.log,
                                            slug=args.slug, idle_seconds=args.idle_seconds,
                                            import_history=args.import_history, history_at=args.history_at, from_db=args.from_db)
                print(json.dumps(result))
                return 0
        if args.command == "init" and args.from_db:
            parser.error("--from-db requires --characters-dir and --character-id")
        if args.command != "init" and not args.db.is_file():
            parser.error("Initialize the character database first")
        if args.command != "run" or args.once:
            # Tight separators: this is the host-facing packet boundary, where
            # every byte between tokens reaches the LLM prompt verbatim.
            print(json.dumps(execute(args.db, args), ensure_ascii=False, separators=(",", ":")), flush=True)
            return 0
        while True:
            result = execute(args.db, args)
            if result["status"] in ("ended", "deleting", "deleted"):
                return 0
            if result["status"] in ("pending", "failed"):
                print(json.dumps(result, separators=(",", ":")), flush=True)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
