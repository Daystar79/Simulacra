import tempfile
import unittest
from pathlib import Path

import yaml

from scripts import golem_loop as loop


class TestGoalEvolution(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.db = root / "character.sqlite"
        self.card = root / "card.yaml"
        self.log = root / "log.yaml"
        self.card.write_text("name: Rowan\nmotivations: {music: {reason: Enjoys playing}}\n"
                             "goals: {perform: {objective: Play in public, motivation: music}}\n")
        self.log.write_text("revision: 1\ngoal_updates: {perform: {progress: Found a venue}}\n")
        loop.initialize_character(self.db, self.card, log=self.log)

    def turn(self, event_id, changes=None, **kwargs):
        requests = []

        def decide(request):
            requests.append(request)
            decision = {"id": event_id, **kwargs}
            if changes is not None:
                decision["goal_events"] = changes
            return decision

        loop.wake_character(self.db, decide, compact=False, event={"id": event_id, "kind": "world"})
        return requests[0]

    def test_choices_and_goals_carry_across_wakes_and_log_commit(self):
        original = self.card.read_bytes()
        self.turn("busy", {"perform": {"choice": "prevented", "evidence": "Worked the late shift."}})
        request = self.turn("free", {"perform": {"choice": "passed", "evidence": "Spent the afternoon teaching."}})
        self.assertEqual(request["current_goals"]["perform"]["status"], "active")
        request = self.turn("class", {
            "perform": {"status": "dormant", "evidence": "Released the reserved venue."},
            "teach": {"objective": "Start a class", "motivation": "music", "commitment": "tentative",
                      "choice": "pursued", "evidence": "Booked a room for a first lesson."},
        }, experience={"topic": "teaching", "benefit": 80, "cost": 20})
        self.assertEqual(request["goal_evidence"]["perform"]["choices"], {"prevented": 1, "passed": 1})
        self.assertEqual(request["current_goals"]["perform"]["status"], "active")
        request = self.turn("return", {
            "perform": {"status": "active", "evidence": "Accepted a concert invitation."},
            "teach": {"objective": "Teach a full term", "commitment": "central",
                      "evidence": "Signed up for twelve weeks."},
        })
        self.assertIn("teaching", request["expectations"])
        self.assertEqual(request["current_goals"]["perform"]["status"], "dormant")
        self.assertEqual(request["current_goals"]["teach"]["status"], "active")
        request = self.turn("finish", {
            "perform": {"status": "abandoned", "evidence": "Gave up the concert spot."},
            "teach": {"status": "completed", "evidence": "Delivered the last lesson."},
        })
        self.assertEqual(request["current_goals"]["perform"]["status"], "active")
        self.assertEqual(request["current_goals"]["teach"]["commitment"], "central")
        self.assertTrue(loop.commit_goal_updates(self.db))
        self.assertFalse(loop.commit_goal_updates(self.db))
        request = self.turn("later")
        self.assertEqual(request["current_goals"]["perform"], {
            "objective": "Play in public", "motivation": "music", "progress": "Found a venue",
            "status": "abandoned",
        })
        self.assertEqual(request["current_goals"]["teach"]["status"], "completed")
        self.assertEqual(request["current_goals"]["teach"]["motivation"], "music")
        self.assertEqual(self.card.read_bytes(), original)
        self.assertEqual(yaml.safe_load(self.log.read_text())["revision"], 2)

    def test_invalid_goal_rolls_back_and_replayed_decision_counts_once(self):
        with self.assertRaisesRegex(ValueError, "objective"):
            self.turn("try", {
                "perform": {"choice": "pursued", "evidence": "Rehearsed."},
                "typo": {"status": "completed", "evidence": "Finished."},
            })
        decision = {"id": "try", "goal_events": {"perform": {"choice": "pursued", "evidence": "Rehearsed."}}}
        loop.wake_character(self.db, lambda _: decision)
        with loop.transaction(self.db) as connection:
            config = loop.runtime_config(connection)
            self.assertEqual(config["goal_evidence"]["perform"]["choices"], {"pursued": 1})
            self.assertFalse(loop.resolve(connection, decision, config["history"], None)["resolved"])
