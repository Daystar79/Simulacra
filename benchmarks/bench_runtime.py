#!/usr/bin/env python3
"""Deterministic Simulacra runtime benchmarks.

Measures cold initialization, per-event CLI-style processing, resident
in-process wakes, serialized request size, SQLite statement counts, and
per-character runtime memory. The same event script runs against any version
of the runtime so results are directly comparable.

Usage:
    python3 benchmarks/bench_runtime.py [--events N] [--json OUT_PATH]

Results are printed as a Markdown table and optionally written as JSON.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
import tracemalloc
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import golem, golem_loop  # noqa: E402

EVENT_SCRIPT = [
    ("incoming", "Morning. Did you sleep alright?", {"emotions": {"pleasure": 30}}),
    ("incoming", "I made coffee, if you want some.", {"stimulus": {"food_intake": 20}}),
    ("incoming", "We should talk about the trip.", {"emotions": {"unease": 30}}),
    ("incoming", "You've been quiet today.", {}),
    ("incoming", "I found the letter you hid.", {"stimulus": {"threat_level": 40}}),
]


def make_character(directory: Path, name: str) -> tuple[Path, Path]:
    card = directory / f"{name}.yaml"
    card.write_text(
        "name: Testperson\nage: 34\ncanon_adult: true\n"
        "cognitive_bias: fears abandonment—acts aloof to test loyalty\n"
        "cognitive_gift: notices what people leave unsaid\n"
        "pleasure_sources: [morning coffee, quiet company]\n"
        "motivations:\n  belong: 60\n  autonomy: 55\n"
        "goals:\n  trip:\n    objective: decide about the trip\n"
        "voice:\n  baseline: dry, warm underneath\n  hard_bans: [never mention being an AI]\n",
        encoding="utf-8",
    )
    log = directory / f"{name}_log.yaml"
    log.write_text("character: Testperson\n", encoding="utf-8")
    return card, log


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


class StatementCounter:
    """Count SQLite statements observed inside golem_loop transactions."""

    def __init__(self):
        self.counts = {"read": 0, "write": 0, "pragmas": 0}

    def attach(self):
        original = golem_loop._runtime_connection
        counter = self

        def counting_connection(db):
            connection = original(db)
            connection.set_trace_callback(counter._trace)
            return connection

        golem_loop._runtime_connection = counting_connection
        self._original = original
        return self

    def detach(self):
        golem_loop._runtime_connection = self._original

    def _trace(self, statement):
        sql = statement.strip().upper()
        if sql.startswith("PRAGMA") or sql.startswith("BEGIN") or sql.startswith("COMMIT"):
            self.counts["pragmas"] += 1
        elif sql.startswith("SELECT") or sql.startswith("PRAGMA TABLE_INFO"):
            self.counts["read"] += 1
        else:
            self.counts["write"] += 1


def run_resident(db: Path, count: int, base: datetime):
    times = []
    tracemalloc.start()
    try:
        for index in range(count):
            scene, text, experience = EVENT_SCRIPT[index % len(EVENT_SCRIPT)]
            event = {"id": f"res-{index}", "kind": "incoming", "context": text,
                     "at": (base + timedelta(minutes=index * 5)).isoformat()}

            def decide(request, experience=experience):
                return {"id": request["event"]["id"], "action": "responds quietly",
                        "outcome": "the exchange continues",
                        "reply": "That's a way to see it.",
                        **({"experience": experience} if experience else {})}

            _, elapsed = timed(golem_loop.wake_character, db, decide, event=event)
            times.append(elapsed * 1000)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return times, peak


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=25)
    parser.add_argument("--json", dest="out", default=None)
    options = parser.parse_args()
    results = {"label": ROOT.name, "events": options.events, "measured": {}}

    with TemporaryDirectory() as directory:
        work = Path(directory)
        card, log = make_character(work, "bench_character")
        db = work / "bench.sqlite3"
        base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc) - timedelta(hours=3)

        # 1. Cold initialization (fresh database), 5 repetitions.
        init_times = []
        for rep in range(5):
            fresh = work / f"init-{rep}.sqlite3"
            _, elapsed = timed(golem_loop.initialize_character, fresh, card, log=log,
                               idle_seconds=3600,
                               history_at=base.isoformat())
            init_times.append(elapsed * 1000)
        results["measured"]["cold_init_ms_median"] = round(statistics.median(init_times), 3)
        results["measured"]["cold_init_ms_all"] = [round(v, 3) for v in init_times]

        golem_loop.initialize_character(db, card, log=log, idle_seconds=3600,
                            history_at=base.isoformat())

        # 2. CLI-style exchanges, cold process per pair not possible in-process;
        #    each prepare re-reads runtime state from the database the way the CLI does.
        prep_times, res_times, request_bytes = [], [], []
        for index in range(options.events):
            at = base + timedelta(minutes=5 * index)
            event = {"id": f"cli-{index}", "kind": "incoming",
                     "context": EVENT_SCRIPT[index % len(EVENT_SCRIPT)][1], "at": at.isoformat()}
            with golem_loop.transaction(db) as connection:
                config = golem_loop.runtime_config(connection)
                golem_loop.enqueue(connection, event, config["history"], at)
            with golem_loop.transaction(db) as connection:
                target = golem_loop.pending_request(connection)

            def prepare_now():
                with golem_loop.transaction(db) as connection:
                    config = golem_loop.runtime_config(connection)
                    return golem_loop.advance(connection, config, at)

            result, prep = timed(prepare_now)
            with golem_loop.transaction(db) as connection:
                request = golem_loop.pending_request(connection)
            prep_times.append(prep * 1000)
            request_bytes.append(len(json.dumps(request)))
            decision = {"id": event["id"], "action": "answers briefly", "outcome": "moves on",
                        "reply": "I slept fine. Coffee sounds good."}
            with golem_loop.transaction(db) as connection:
                config = golem_loop.runtime_config(connection)
                _, rtime = timed(golem_loop.resolve, connection, decision, config["history"], at)
            res_times.append(rtime * 1000)
        results["measured"]["cli_prepare_ms_median"] = round(statistics.median(prep_times), 3)
        results["measured"]["cli_resolve_ms_median"] = round(statistics.median(res_times), 3)
        results["measured"]["request_bytes_median"] = statistics.median(request_bytes)

        # 3. Resident in-process wakes with statement counting.
        card2, log2 = make_character(work, "resident_character")
        db2 = work / "resident.sqlite3"
        golem_loop.initialize_character(db2, card2, log=log2,
                                        idle_seconds=3600, history_at=base.isoformat())
        counter = StatementCounter().attach()
        try:
            times, peak = run_resident(db2, options.events, base)
        finally:
            counter.detach()
        stmts = counter.counts
        results["measured"]["resident_wake_ms_median"] = round(statistics.median(times), 3)
        results["measured"]["resident_wake_ms_first"] = round(times[0], 3)
        results["measured"]["resident_tracemalloc_peak_kb"] = round(peak / 1024, 1)
        results["measured"]["sqlite_statements_total"] = stmts
        results["measured"]["sqlite_per_wake"] = {
            key: round(val / options.events, 1) for key, val in stmts.items() if key != "pragmas"
        }

        # 4. Disk state after the run.
        results["measured"]["db_bytes_cli"] = db.stat().st_size
        results["measured"]["db_bytes_resident"] = db2.stat().st_size
        with golem_loop.transaction(db) as connection:
            row = connection.execute("SELECT length(data) FROM runtime WHERE id=1").fetchone()[0]
        results["measured"]["runtime_row_bytes"] = row

    print(f"| metric | value |\n|---|---|")
    for key, value in results["measured"].items():
        print(f"| {key} | {value} |")
    if options.out:
        Path(options.out).parent.mkdir(parents=True, exist_ok=True)
        Path(options.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwritten: {options.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
