"""Persistent event loop and host handoff for the Golem CLI.

Public facade over golem_loop_modules/ (db, activities, projection, cache,
learning, lifecycle). Keeps SQLite connection/transaction orchestration,
provisioning, boundary enforcement, wake_character, execute, and the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

if __package__:
    from . import golem, goal_evolution, relationship_memory
else:
    import golem
    import goal_evolution
    import relationship_memory

from golem_logs import mirror_memories
from golem_loop_modules.activities import (  # noqa: E402, F401
    active_activity,
    apply_activity_decision,
    schedule_activity_due,
)
from golem_loop_modules.cache import (  # noqa: E402, F401
    _REALM_CACHE,
    _RESIDENT_CHARACTERS,
    _character_cache_key,
    _ensure_character_cache_table,
    _store_character_cache,
    _stored_character_cache,
    build_identity_anchor,
    cached_identity,
    extract_memory_cues,
    load_cached_character,
    load_cached_realm_data,
    migrate_runtime_row,
    runtime_config,
    setup,
)
from golem_loop_modules.db import (  # noqa: E402, F401
    _SCHEMA_ENSURED,
    character_database,
    check_character_files,
    clear_activity_and_archive,
    compact_event_requests,
    completed_event,
    ensure_activity_schema,
    file_lock,
    pending_log_entries,
    read_object,
)
from golem_loop_modules.learning import (  # noqa: E402, F401
    RECENT_LIMIT,
    _OBSERVATION_STOPWORDS,
    contextual_forecast,
    expectation_dimensions,
    expectation_matches,
    learned_observations,
    next_expectation,
    recalculate_expectations,
    recall_past_episodes,
    recall_stored_memories,
    record_contextual_expectation,
    relevant_expectations,
    relevant_learned_observations,
    scores,
    topic_key,
)
from golem_loop_modules.lifecycle import (  # noqa: E402, F401
    ACTIVE_MEMORY_WINDOW_SECONDS,
    advance,
    apply_appraisal,
    body_tick,
    copied_card_field,
    enqueue,
    recent_events,
    resolve,
)
from golem_loop_modules.projection import (  # noqa: E402, F401
    compact_recent_events,
    decision_context,
    expression_guidance,
    intimacy_render,
    message_text,
    pending_request,
    prompt_cache_split,
    repeated_action_pattern,
    repeated_reply_pattern,
    resolve_relationship_target,
)


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


def flush_memory_log(connection):
    """Publish only committed memories. Retry interrupted mirrors idempotently."""
    try:
        pending = connection.execute("SELECT 1 FROM memory_log_queue LIMIT 1").fetchone()
    except sqlite3.OperationalError as exc:
        if str(exc) != "no such table: memory_log_queue":
            raise
        return
    if pending:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            entries = pending_log_entries(connection)
            if entries:
                config = runtime_config(connection)
                if config.get("lifecycle") not in ("deleting", "deleted"):
                    mirror_memories(Path(config["log"]), entries, config.get("character_id"))
                connection.execute("DELETE FROM memory_log_queue")


@contextmanager
def staged_transaction(connection):
    """One committed transaction on an already-open runtime connection."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        yield connection


@contextmanager
def transaction(db: Path, *, mirror=True):
    connection = _runtime_connection(db)
    try:
        with staged_transaction(connection):
            yield connection
        if mirror:
            flush_memory_log(connection)
    finally:
        connection.close()


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
                req = pending_request(connection)
                payload = prompt_cache_split(req) if getattr(args, "split_cache", False) else decision_context(req)
                return {"status": "pending", "request": payload}
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
            with transaction(staged_db, mirror=False) as connection:
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
        with transaction(staged_db, mirror=False) as connection:
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
                   compact=True, split_cache=False, character_id=None):
    """Run a host heartbeat. decide(request) returns one JSON-compatible character decision.

    The callback receives the compact decision context by default: the
    projection a host prompt needs, without the full tick internals that
    remain stored in SQLite. Pass compact=False for the full saved request,
    or split_cache=True for a KV-cache-ready {prefix_hash, static_prefix, dynamic_turn} split.
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
                                     compact=compact, split_cache=split_cache, character_id=character_id)
    finally:
        connection.close()


def _wake_with_connection(connection, db, decide, *, event=None, max_events=64,
                          screen_abuse=None, actor_id=None, compact=True, split_cache=False, character_id=None):
    with staged_transaction(connection):
        ensure_activity_schema(connection)
        owner = runtime_config(connection, character_id).get("character_id")
        if owner and event is not None and event.get("character_id", owner) != owner:
            raise ValueError("Event character ID does not match the selected database")
    flush_memory_log(connection)
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
            if split_cache:
                payload = prompt_cache_split(request)
            elif compact:
                payload = decision_context(request)
            else:
                payload = request
            decision = decide(payload)
            if not isinstance(decision, dict) or decision.get("id") != event_id:
                raise ValueError("Host must return a decision matching the pending event ID")
            with staged_transaction(connection):
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                result = resolve(connection, decision, config["history"], datetime.now(timezone.utc))
            if result.get("remembered"):
                flush_memory_log(connection)
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
    prepare.add_argument("--split-cache", action="store_true", help="Split output into static_prefix + dynamic_turn for KV caching")
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
