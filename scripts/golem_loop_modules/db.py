"""SQLite file locking, schema helpers, path checks, and archive compaction."""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any


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
    connection.execute("""CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        summary TEXT NOT NULL,
        reason TEXT NOT NULL,
        cues TEXT NOT NULL,
        created_at TEXT NOT NULL,
        event_id TEXT
    )""")
    if db_file and stamp is not None:
        _SCHEMA_ENSURED[db_file] = stamp


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


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def clear_activity_and_archive(connection):
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("DELETE FROM activities")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='memories' AND type='table'").fetchone():
        connection.execute("DELETE FROM memories")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='relationships' AND type='table'").fetchone():
        connection.execute("DELETE FROM relationships")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='request_archive'").fetchone():
        connection.execute("DELETE FROM request_archive")


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


def completed_event(connection, event_id):
    row = connection.execute("SELECT status, decision FROM events WHERE id=?", (event_id,)).fetchone()
    if row is None or row["status"] not in ("resolved", "failed", "cancelled"):
        return None
    decision = json.loads(row["decision"] or "{}")
    return {"id": event_id, "status": row["status"],
            **{key: decision[key] for key in ("reply", "error") if key in decision}}
