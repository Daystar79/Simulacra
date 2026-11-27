import json
import sqlite3
import unittest

from scripts.golem_loop_modules import recall


class TestWeightedRecall(unittest.TestCase):
    def test_two_week_boundary_intensity_and_notebook(self):
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE memories(id,kind,summary,cues,created_at)")
            db.execute("INSERT INTO memories VALUES ('legacy','dream','A ferry. More detail.',?,?)",
                       (json.dumps(["ferry"]), "2026-01-01T00:00:00+00:00"))
            recall.ensure_schema(db)
            for ident, intensity, ts in (("strong", 90, 1700000000), ("recent", 50, 1768000000)):
                recall.index_entry(db, {"id": ident, "kind": "detailed", "summary": "Kept in full. Detail.",
                                        "cues": ["ferry"], "emotional_intensity": intensity}, "stored", ts)
            def lookup(at):
                return recall.ranked(db, "the ferry", set(), at + "+00:00", 8)
            self.assertNotIn("detail", lookup("2026-01-14T23:59:59")[-1])
            results = lookup("2026-01-15T00:00:00")
            self.assertEqual([r["id"] for r in results], ["strong", "recent", "legacy"])
            self.assertEqual(results[-1]["summary"], "A ferry.")
            self.assertEqual(results[-1]["kind"], "dream")
            self.assertNotIn("detail", results[0])
            recall.use_notebook(db, {"write": "Ferry ticket #429."}, "event", results[-1]["at"])
            page = recall.use_notebook(db, {"read": "TICKET"}, "later", results[0]["at"])
            self.assertEqual(page["entries"][0]["note"], "Ferry ticket #429.")
            self.assertEqual(recall.ranked(db, "ticket", set(), None, 8), [])

    def test_physical_sensation_and_intent_can_each_sustain_recall(self):
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE memories(id,kind,summary,cues,created_at)")
            recall.ensure_schema(db)
            body = {"somatic_map": {"left_hand": {"cold": 92}}}
            for ident, signals in (("cold", {"physical_intensity": recall.physical_intensity(body)}),
                                   ("promise", {"remember_by_choice": True}), ("routine", {})):
                entry = {"id": ident, "kind": "detailed", "emotional_intensity": 12,
                         "cues": ["door"], "summary": "At the door. A second detail.", **signals}
                recall.index_entry(db, entry, "stored", 1700000000)
            results = recall.ranked(db, "door", set(), "2026-01-01T00:00:00+00:00", 8)
            self.assertEqual([m["strength"] for m in results], [92, 85, 12])
            self.assertEqual([m.get("detail") for m in results], [None, None, "key_point"])
            self.assertTrue(all(m["emotional_intensity"] == 12 for m in results))
