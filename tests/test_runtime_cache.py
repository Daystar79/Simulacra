"""Resident character cache, serialization, and persistence integrity tests."""
import copy
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from scripts import golem, golem_loop

CARD = ("name: Resdent\nage: 30\ncanon_adult: true\n"
        "cognitive_bias: keeps others at a distance\n"
        "cognitive_gift: notices small changes\n"
        "voice:\n  baseline: quiet and precise\n")


class TestResidentCache(unittest.TestCase):
    def test_hydrate_once_and_share_between_wakes(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            golem_loop.initialize_character(db, card, character_id="resdent",
                                            history_at=datetime.now(timezone.utc).isoformat())
            first = golem_loop.load_cached_character({"card": str(card), "slug": None, "log": None, "history": {},
                                                      "character_id": "resdent"})
            second = golem_loop.load_cached_character({"card": str(card), "slug": None, "log": None, "history": {},
                                                       "character_id": "resdent"})
            self.assertIs(first[1], second[1], "card must be the shared resident instance")
            self.assertIs(first[0], second[0], "state must be the shared resident instance")

    def test_card_edit_rehydrates(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            golem_loop.initialize_character(db, card, character_id="resdent",
                                            history_at=datetime.now(timezone.utc).isoformat())
            first = golem_loop.load_cached_character({"card": str(card), "slug": None, "log": None, "history": {},
                                                     "character_id": "resdent"})
            time.sleep(0.01)
            card.write_text(CARD + "pleasure_sources: [rain]\n", encoding="utf-8")
            second = golem_loop.load_cached_character({"card": str(card), "slug": None, "log": None, "history": {},
                                                      "character_id": "resdent"})
            self.assertIsNot(first[1], second[1], "card change must rehydrate")
            self.assertEqual(second[1]["pleasure_sources"], ["rain"])

    def test_tick_does_not_mutate_shared_state(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="resdent", history_at=base.isoformat())
            now = base + timedelta(minutes=10)
            with golem_loop.transaction(db) as connection:
                config = golem_loop.runtime_config(connection, "resdent")
                _, card_data, _ = golem_loop.load_cached_character(config, connection)
                frozen = copy.deepcopy(card_data)
                frozen_state = copy.deepcopy(config)
                event = {"id": "tick1", "kind": "incoming", "context": "hello",
                         "at": now.isoformat()}
                golem_loop.enqueue(connection, event, config["history"], now)
                golem_loop.advance(connection, config, now)
                self.assertEqual(card_data, frozen, "the resident card must stay untouched by a tick")
            # A second wake reuses the same instance and produces a full tick.
            with golem_loop.transaction(db) as connection:
                golem_loop.resolve(connection, {"id": "tick1", "character_id": "resdent",
                                                 "action": "greets", "outcome": "ok", "reply": "hello"},
                                    golem_loop.runtime_config(connection)["history"], now)

    def test_legacy_runtime_row_migrates_to_cache_table(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            golem_loop.initialize_character(db, card, character_id="resdent",
                                            history_at=datetime.now(timezone.utc).isoformat())
            # Simulate a legacy database by re-embedding the hydrate in the row.
            with golem_loop.transaction(db) as connection:
                row = json.loads(connection.execute("SELECT data FROM character_cache WHERE id=1").fetchone()["data"])
                config = golem_loop.runtime_config(connection, "resdent")
                config["cached_character"] = row["entry"]
                connection.execute("DELETE FROM character_cache")
                connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
            with golem_loop.transaction(db) as connection:
                config = golem_loop.runtime_config(connection, "resdent")
                self.assertNotIn("cached_character", config, "legacy blob must move out of the row")
                stored = connection.execute("SELECT length(data) FROM runtime WHERE id=1").fetchone()[0]
                cache = json.loads(connection.execute("SELECT data FROM character_cache WHERE id=1").fetchone()["data"])
                self.assertEqual(cache["entry"]["card"]["name"], "Resdent")
                self.assertLess(stored, len(json.dumps(config)) + 10000)

    def test_runtime_row_stays_small_across_events(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="resdent", history_at=base.isoformat())
            sizes = []
            for index in range(6):
                at = base + timedelta(minutes=5 * index)
                event = {"id": f"s{index}", "kind": "incoming", "context": "hi", "at": at.isoformat()}
                with golem_loop.transaction(db) as connection:
                    config = golem_loop.runtime_config(connection, "resdent")
                    golem_loop.enqueue(connection, event, config["history"], at)
                def decide(request):
                    return {"id": request["event"]["id"], "character_id": "resdent",
                            "action": "waves", "outcome": "ok", "reply": "hi there"}
                golem_loop.wake_character(db, decide, event=event, character_id="resdent")
                with golem_loop.transaction(db) as connection:
                    sizes.append(connection.execute("SELECT length(data) FROM runtime WHERE id=1").fetchone()[0])
            self.assertLess(max(sizes), len(json.dumps({"history": "x" * 4000})) + 16000,
                            "runtime row must not embed the hydrated character")

    def test_wal_journal_mode_applied(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="resdent", history_at=base.isoformat())
            with sqlite3.connect(db) as connection:
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_cross_process_cache_reuse(self):
        with TemporaryDirectory() as directory:
            work = Path(directory)
            card = work / "c.yaml"
            card.write_text(CARD, encoding="utf-8")
            db = work / "c.sqlite3"
            base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="resdent", history_at=base.isoformat())
            golem_loop._RESIDENT_CHARACTERS.clear()
            with golem_loop.transaction(db) as connection:
                config = golem_loop.runtime_config(connection, "resdent")
                state, card_data, durable = golem_loop.load_cached_character(config, connection)
                self.assertEqual(card_data["name"], "Resdent",
                                  "a fresh process must hydrate from the persisted cache table")


if __name__ == "__main__":
    unittest.main()
