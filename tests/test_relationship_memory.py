import json
import tempfile
import unittest
from pathlib import Path

from scripts import golem_loop as loop


class TestRelationshipMemory(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.card = root / "shared.yaml"
        self.card.write_text("name: Jo\nrelationships:\n"
                             "  - {other: a, dynamic: old friends}\n"
                             "  - {other: b, notes: met at work}\n")
        self.log = root / "shared_log.yaml"
        self.log.write_text("relational_baselines:\n  a: {emotional_safety: 70}\n")
        self.db = root / "one.sqlite3"
        loop.initialize_character(self.db, self.card, log=self.log)

    def turn(self, event_id, speaker=None, change=None, db=None):
        seen = []
        def decide(request):
            seen.append(request)
            decision = {"id": request["event"]["id"]}
            if change:
                decision["experience"] = {"relationship_change": change}
            return decision
        loop.wake_character(db or self.db, decide, compact=True, actor_id=speaker,
                            event={"id": event_id, "kind": "incoming"})
        return seen

    def test_two_speakers_two_databases_and_delivery_retry(self):
        first, = self.turn("first", "a", {"delta": {"emotional_safety": -21}})
        self.assertEqual(first["relationship_state"]["values"]["emotional_safety"], 70)
        self.assertEqual(first["relationship_state"]["card_context"], {"dynamic": "old friends"})
        self.assertEqual(self.turn("first", "a"), [])
        with self.assertRaisesRegex(ValueError, "different contents"):
            self.turn("first", "b")

        second, = self.turn("second", "b")
        self.assertEqual(second["relationship_state"]["target"], "b")
        self.assertEqual(second["relationship_state"]["values"], {})
        self.assertEqual(second["relationship_state"]["card_context"], {"notes": "met at work"})
        self.assertEqual(second["recent"][0]["relationship_target"], "a")
        third, = self.turn("third", "a")
        self.assertEqual(third["relational_vectors"]["a"]["emotional_safety"], 49)

        other_db = self.db.with_name("two.sqlite3")
        loop.initialize_character(other_db, self.card, log=self.log)
        other, = self.turn("third", "a", db=other_db)
        self.assertEqual(other["relational_vectors"]["a"]["emotional_safety"], 70)
        anonymous, = self.turn("anon")
        self.assertNotIn("relationship_state", anonymous)

    def test_wrong_target_rolls_back_and_pending_decision_can_resume(self):
        with self.assertRaisesRegex(ValueError, "current speaker"):
            self.turn("pending", "a", {"target": "b", "delta": {"trust": -30}})
        with loop.transaction(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0], 0)
        self.turn("pending", "a", {"delta": {"trust": -10}})
        with loop.transaction(self.db) as connection:
            rows = connection.execute("SELECT target,data FROM relationships").fetchall()
        self.assertEqual([(row[0], json.loads(row[1])["values"]["trust"]) for row in rows], [("a", 60)])

    def test_embedded_records_migrate_intact_and_clear_on_deletion(self):
        legacy = {"baseline": {"trust": 80}, "values": {"trust": 62},
                  "drift_per_day": {"trust": 0.5}, "updated_at": "2025-01-01T00:00:00+00:00"}
        with loop.transaction(self.db) as connection:
            config = loop.runtime_config(connection)
            config.pop("relationship_store_version")
            config["relationships"] = {"a": legacy, "b": legacy}
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
            connection.execute("DROP TABLE relationships")
        for _ in range(2):
            with loop.transaction(self.db) as connection:
                self.assertNotIn("relationships", loop.runtime_config(connection))
                rows = connection.execute("SELECT target,data FROM relationships").fetchall()
                self.assertEqual({key: json.loads(value) for key, value in rows}, {"a": legacy, "b": legacy})
        with loop.transaction(self.db) as connection:
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps({"lifecycle": "deleted"}),))
            self.assertEqual(loop.runtime_config(connection), {"lifecycle": "deleted"})
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0], 0)
