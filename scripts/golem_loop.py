"""Persistent event loop and host handoff for the Golem CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from . import golem, goal_evolution
else:
    import golem
    import goal_evolution

RECENT_LIMIT = 12


@contextmanager
def transaction(db: Path):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
    finally:
        connection.close()


def setup(connection, args, now):
    card = args.card.resolve(strict=True)
    log = args.log.resolve(strict=True) if args.log else None
    golem.overlay_log(golem.load_character(card, args.slug), log)
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
        "card": str(card), "log": str(log) if log else None, "slug": args.slug,
        "idle_seconds": args.idle_seconds, "history": history,
        "idle_at": (now + timedelta(seconds=args.idle_seconds)).timestamp(),
    }
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
    connection.execute("INSERT INTO runtime VALUES (1, ?)", (json.dumps(config),))
    return {"initialized": True}


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def enqueue(connection, event, history, now):
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
    if "expectation" in event:
        topic_key(event.get("topic"))
        scores(event["expectation"])
    if "topic" in event:
        topic_key(event["topic"])
    existing = connection.execute("SELECT input FROM events WHERE id = ?", (event_id,)).fetchone()
    if existing is not None:
        if json.loads(existing["input"]) != event:
            raise ValueError(f"Event ID already exists with different contents: {event_id}")
        return {"id": event_id, "queued": False}
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


def recent_events(connection, limit=RECENT_LIMIT):
    rows = connection.execute(
        """SELECT input, due, decision, status, json_extract(request, '$.assessment') AS assessment FROM events
           WHERE status IN ('resolved', 'failed')
           ORDER BY due DESC, rowid DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [
        {
            "event": json.loads(row["input"]), "at": datetime.fromtimestamp(row["due"], timezone.utc).isoformat(),
            "decision": json.loads(row["decision"]), "status": row["status"],
            **({"assessment": json.loads(row["assessment"])} if row["assessment"] else {}),
        }
        for row in reversed(rows)
    ]


def pending_request(connection):
    row = connection.execute("SELECT request FROM events WHERE status = 'pending'").fetchone()
    return json.loads(row["request"]) if row else None


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


def scores(value):
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or not 0 <= value[key] <= 100 for key in ("benefit", "cost")
    ):
        raise ValueError("Benefit and cost must each be integer scores from 0 to 100")
    return {key: value[key] for key in ("benefit", "cost")}


def runtime_config(connection):
    return json.loads(connection.execute("SELECT data FROM runtime WHERE id = 1").fetchone()["data"])


def body_tick(config, stimulus):
    card = golem.load_character(Path(config["card"]), config["slug"])
    log = Path(config["log"]) if config["log"] else None
    state, durable = golem.overlay_log(card, log, goal_changes=config.get("goal_changes"))
    realm_data = yaml.safe_load(golem.REALM_DATA_PATH.read_text(encoding="utf-8"))
    return golem.run_golem(state, stimulus, realm_data, config["history"]), card, durable


def assess_experience(connection, request, experience):
    observed = scores(experience)
    event = request["event"]
    topic = topic_key(experience.get("topic", event.get("topic")))
    if "topic" in event and topic != topic_key(event["topic"]):
        raise ValueError("Experience must refer to the event topic")
    config = runtime_config(connection)
    estimates = config.setdefault("expectations", {})
    forecast = event.get("expectation", estimates.get(topic))
    # Appraise at the same instant, retaining the scene without replaying one-time effects.
    stimulus = dict(event.get("stimulus", {}))
    for field in ("food_intake", "conversation", "memory_cues"):
        stimulus.pop(field, None)
    stimulus.update(event_label=event["id"], event_at=request["at"], appraisal=experience.get("appraisal", {}))
    after, _, _ = body_tick(config, stimulus)
    before = request["tick"]

    def measurements(tick):
        body = tick["psychosomatic_snapshot"]["autonomic_state"]
        return {"stress": body["stress"], "arousal": body["arousal"],
                "interest": tick["next_history"]["appraisal_effects"]["interest"]}

    initial, final = measurements(before), measurements(after)
    evidence = {
        "benefit": golem.clamp(observed["benefit"] + 0.25 * (final["interest"] - initial["interest"])),
        "cost": golem.clamp(observed["cost"] + 0.25 * (final["stress"] - initial["stress"])),
    }
    # A stated forecast belongs to this episode. Repeated observations update the learned prior.
    prior = estimates.get(topic, forecast)
    estimates[topic] = {
        key: round(0.75 * prior[key] + 0.25 * value, 2) if prior else value
        for key, value in evidence.items()
    }
    request["assessment"] = {
        "topic": topic, "forecast": forecast, "observed": observed, "before": initial, "after": final,
        "evidence": evidence, "next_expectation": estimates[topic],
    }
    config["history"] = after["next_history"]
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute("UPDATE events SET request = ? WHERE id = ?", (json.dumps(request), event["id"]))


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
                      "history_anchors", "relationships", "depth_of_knowledge"):
            for path, description in descriptions(card.get(field), field):
                if spoken.intersection(phrases(description)):
                    return path
    return None


def resolve(connection, decision, history, now):
    event_id = decision.get("id")
    if not isinstance(event_id, str):
        raise ValueError("Decision requires an event id")
    if any(not isinstance(decision.get(key, ""), str) for key in ("action", "outcome")):
        raise ValueError("Decision action and outcome must be text")
    plans = decision.get("plans", [])
    if not isinstance(plans, list) or any(not isinstance(plan, dict) for plan in plans):
        raise ValueError("Decision plans must be an array of event objects")
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
    if row and row["status"] == "resolved" and json.loads(row["decision"]) == decision:
        return {"id": event_id, "resolved": False}
    if not row or row["status"] != "pending":
        raise ValueError("Decision must refer to the pending event")
    if "reply" in decision:
        config = runtime_config(connection)
        card = golem.load_character(Path(config["card"]), config["slug"])
        field = copied_card_field(card, decision["reply"])
        if field:
            raise ValueError(f"Draft reply copies card field {field}. Render this beat in the character's own words.")
    if "experience" in decision:
        assess_experience(connection, json.loads(row["request"]), decision["experience"])
    if "goal_events" in decision:
        config = runtime_config(connection)
        goal_evolution.record_goal_events(config, json.loads(row["request"]), decision["goal_events"])
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
    return {"id": event_id, "resolved": True}


def advance(connection, config, now, allow_idle=True):

    if connection.execute("SELECT 1 FROM events WHERE status = 'pending'").fetchone():
        return {"status": "waiting_for_host"}
    row = connection.execute(
        "SELECT * FROM events WHERE status = 'queued' AND due <= ? ORDER BY due, rowid LIMIT 1",
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
        tick, card, durable = body_tick(config, stimulus)
    except (ValueError, TypeError, KeyError) as exc:
        if event["kind"] == "idle":
            raise
        connection.execute(
            "UPDATE events SET status = 'failed', decision = ? WHERE id = ?",
            (json.dumps({"error": str(exc)}), event["id"]),
        )
        return {"status": "failed", "id": event["id"], "error": str(exc)}

    request = {
        "event": event, "at": at.isoformat(), "tick": tick,
        "character": {key: config[key] for key in ("card", "slug", "log")},
        "expectations": config.get("expectations", {}),
        "motivations": card.get("motivations", {}), "incentives": card.get("incentives", {}),
        "goals": card.get("goals", {}), "goal_updates": (durable or {}).get("goal_updates", {}),
        "current_goals": tick.get("current_goals", {}),
        "goal_evidence": config.get("goal_evidence", {}),
        "recent": recent_events(connection),
    }
    if "topic" in event:
        request["learned"] = learned_observations(connection, event["topic"], RECENT_LIMIT)
    config["history"] = tick["next_history"]
    config["idle_at"] = (now + timedelta(seconds=config["idle_seconds"])).timestamp()
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute(
        "UPDATE events SET status = 'pending', request = ? WHERE id = ?",
        (json.dumps(request), event["id"]),
    )
    return {"status": "pending", "id": event["id"]}


def execute(db, args):
    with transaction(db) as connection:
        now = datetime.now(timezone.utc)
        if args.command == "init":
            return setup(connection, args, now)
        config = runtime_config(connection)
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if args.command == "run":
            return advance(connection, config, now)
        if args.command == "enqueue":
            event = read_object(args.event)
            if event.get("kind") == "incoming" and config.get("owned_files"):
                raise ValueError("Send incoming messages through the host boundary assessment")
            return enqueue(connection, event, config["history"], now)
        if args.command == "resolve":
            return resolve(connection, read_object(args.decision), config["history"], now)
        if args.command == "pending":
            return pending_request(connection)
        if args.command == "timeline":
            return recent_events(connection, args.limit)
        if args.command == "learned":
            return learned_observations(connection, args.topic)
        return {"history": config["history"], "expectations": config.get("expectations", {}), "pending": pending_request(connection), "recent": recent_events(connection)}


def commit_goal_updates(db):
    """Merge the host-approved batch of pending goal amendments into the configured YAML log."""
    with transaction(Path(db).resolve(strict=True)) as connection:
        config = runtime_config(connection)
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
                         import_history=None, history_at=None, owned_files=()):
    """Create a new character runtime once. Existing databases are preserved."""
    args = argparse.Namespace(
        card=Path(card), log=Path(log) if log else None, slug=slug, idle_seconds=idle_seconds,
        import_history=Path(import_history) if import_history else None, history_at=history_at,
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


def _finish_deletion(db, connection, config):
    # Only names validated at provisioning enter this manifest. Never traverse directories.
    for name in config["owned_files"]:
        path = db.parent / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Character file changed type during deletion: {name}")
        path.unlink(missing_ok=True)
    connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps({"lifecycle": "deleted"}),))


def report_abuse(db, *, actor_id, event_id):
    """Record a host-confirmed incident. Actor and delivery IDs come from the trusted transport."""
    db = Path(db).resolve(strict=True)
    if any(not isinstance(value, str) or not value.strip() for value in (event_id, actor_id)):
        raise ValueError("A confirmed incident requires stable actor and event IDs")
    actor = hashlib.sha256(actor_id.encode()).hexdigest()
    incident = hashlib.sha256(event_id.encode()).hexdigest()
    with transaction(db) as connection:
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
                connection.execute("DELETE FROM observations")
                connection.execute("DELETE FROM events")
                config = {"lifecycle": "deleting", "owned_files": config["owned_files"]}
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


def wake_character(db, decide, *, event=None, max_events=64, screen_abuse=None, actor_id=None):
    """Run a host heartbeat. decide(request) returns one JSON-compatible character decision."""
    db = Path(db).resolve()
    if not db.is_file():
        raise ValueError("Initialize the character database first")
    if not callable(decide) or type(max_events) is not int or max_events < 1:
        raise ValueError("wake_character requires a decision callback and a positive event limit")
    # flock is released by the VM kernel when the process exits, including after a crash.
    import fcntl

    if event is not None and event.get("kind") == "incoming":
        with transaction(db) as connection:
            config = runtime_config(connection)
        if config.get("lifecycle") == "deleted":
            return {"status": "deleted"}
        if config.get("owned_files") and screen_abuse is None and config.get("lifecycle") != "deleting":
            raise ValueError("A deletion-enabled runtime requires a host boundary assessment for incoming turns")
        if screen_abuse is not None and config.get("lifecycle") != "deleting":
            boundary = assess_contact(db, event, actor_id, screen_abuse)
            if boundary is not None:
                return boundary

    with transaction(db) as connection:
        config = runtime_config(connection)
        if config.get("lifecycle") == "deleting":
            _finish_deletion(db, connection, config)
            return {"status": "deleted"}
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if event is not None:
            enqueue(connection, event, config["history"], datetime.now(timezone.utc))

    handled = []
    with db.with_name(db.name + ".wake.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(max_events):
            with transaction(db) as connection:
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
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
            decision = decide(request)
            if not isinstance(decision, dict) or decision.get("id") != event_id:
                raise ValueError("Host must return a decision matching the pending event ID")
            with transaction(db) as connection:
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                result = resolve(connection, decision, config["history"], datetime.now(timezone.utc))
            if result["resolved"] and "reply" in decision:
                result["reply"] = decision["reply"]
            handled.append(result)
    return {"events": handled}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Persistent SQLite database for one character")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--card", type=Path, required=True)
    init.add_argument("--slug")
    init.add_argument("--log", type=Path)
    init.add_argument("--import-history", type=Path)
    init.add_argument("--history-at", help="Timestamp of imported untimestamped history")
    init.add_argument("--idle-seconds", type=int, default=900)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true", help="Process at most one ready event")
    commands.add_parser("pending")
    commands.add_parser("status")
    commands.add_parser("timeline").add_argument("--limit", type=int, default=100)
    commands.add_parser("learned").add_argument("topic")
    commands.add_parser("enqueue").add_argument("event", type=Path)
    commands.add_parser("resolve").add_argument("decision", type=Path)
    args = parser.parse_args(argv)
    if args.command == "timeline" and args.limit < 1:
        parser.error("--limit must be positive")
    if args.command != "init" and not args.db.is_file():
        parser.error("Initialize the character database first")
    try:
        if args.command != "run" or args.once:
            print(json.dumps(execute(args.db, args), ensure_ascii=False), flush=True)
            return 0
        while True:
            result = execute(args.db, args)
            if result["status"] in ("ended", "deleting", "deleted"):
                return 0
            if result["status"] in ("pending", "failed"):
                print(json.dumps(result), flush=True)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
