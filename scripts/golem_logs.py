"""Durable log persistence: pressure commits, locking, and atomic saves."""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from golem_loop_modules.db import file_lock
from golem_memory import add_memory
from golem_physiology import clamp


def record_pressure_commit(log_data: dict[str, Any], output: dict[str, Any]) -> None:
    meta = output["golem_meta"]
    snap = log_data.setdefault("snapshot", {})
    auto = output["psychosomatic_snapshot"]["autonomic_state"]
    if auto["stress"] >= 65:
        snap["bias_strength"] = clamp(int(snap.get("bias_strength", 80)) - 2)
    log_data.setdefault("history", []).append({
        "movement": output["psychosomatic_snapshot"]["timestamp_or_movement"],
        "pressure": f"Golem/{meta['pressure_tier']}",
        "delta": "bias_strength -2" if auto["stress"] >= 65 else "none",
        "permanence": "temporary" if meta["pressure_tier"] == "Medium" else "permanent",
        "notes": f"Rules: {', '.join(meta['triggered_rules'][:4])}",
    })


def replace_text(path: Path, text: str) -> None:
    path = path.resolve()
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as stream:
            pending = Path(stream.name)
            stream.write(text)
        if path.exists():
            pending.chmod(path.stat().st_mode & 0o777)
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


@contextmanager
def locked_file(path: Path):
    path = path.resolve()
    lock = path.with_name(path.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError(f"File is locked: {lock}") from exc
    try:
        yield
    finally:
        lock.rmdir()


@contextmanager
def locked_log(log_path: Path):
    # A terminated writer must release the YAML lock so committed mirrors can resume.
    path = log_path.resolve()
    with file_lock(path.with_name(path.name + ".lock")):
        yield yaml.safe_load(log_path.read_text(encoding="utf-8")) or {}


def mirror_memories(log_path, entries, character_id, *, validate_only=False):
    """Validate a whole batch under the log lock and optionally publish it once."""
    with locked_log(log_path) as log:
        if character_id is not None and log.get("character_id") != character_id:
            raise ValueError("Character ID mismatch when saving the durable log")
        changed = False
        for entry in entries:
            if add_memory(log, entry):
                changed = True
        if changed and not validate_only:
            replace_text(log_path, yaml.safe_dump(log, sort_keys=False))


def update_log(
    log_path: Path, output: dict[str, Any] | None = None, *,
    commit: bool = False, force: bool = False, memory: dict[str, Any] | None = None,
    character_id: str | None = None,
) -> tuple[bool, bool]:
    commit_pressure = output is not None and (force or (commit and output["golem_meta"]["commit_eligible"]))
    if not commit_pressure and memory is None:
        return False, False

    with locked_log(log_path) as log_data:
        if character_id is not None and log_data.get("character_id") != character_id:
            raise ValueError("Character ID mismatch when saving the durable log")
        if output is not None and log_data.get("character_id") not in (None, output["psychosomatic_snapshot"]["character_id"]):
            raise ValueError("Character ID mismatch when saving the durable log")
        saved_memory = memory is not None and add_memory(log_data, memory)
        if commit_pressure:
            record_pressure_commit(log_data, output)
        if saved_memory or commit_pressure:
            replace_text(log_path, yaml.safe_dump(log_data, sort_keys=False))
        return commit_pressure, saved_memory

