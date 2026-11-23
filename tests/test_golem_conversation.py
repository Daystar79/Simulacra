"""Regression tests for memory and conversational intent at the Golem CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class TestGolemConversation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.log = self.directory / "log.yaml"
        self.log.write_text("revision: 1\nmemories: {detailed: [], footnote: []}\nhistory: []\n")
        self.history = self.directory / "history.json"

    def tick(self, stimulus, *args):
        result = subprocess.run(
            [
                sys.executable, "scripts/run.py", "golem",
                "--card", "Characters/_template.yaml", "--log", str(self.log),
                "--history-file", str(self.history), "--stimulus", json.dumps(stimulus), *args,
            ],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout.split("\n", 1)[1])

    def test_spontaneous_urge_and_deliberate_restraint(self):
        stimulus = {
            "urge": {"action": "reach for a hug", "strength": 100},
            "caller_or_target": "friend", "willingness_to_be_seen": 80,
            "willingness_to_pursue": 85, "appraisal": {"delight": 90},
        }
        snapshot = self.tick(stimulus)["psychosomatic_snapshot"]
        self.assertEqual(snapshot["priority_arbitration"]["arbitration_status"], "impulse_override")
        self.assertEqual(snapshot["affective_state"]["primary_emotion"], "joy")
        self.assertEqual(snapshot["affective_state"]["initiative"], 85)
        self.assertEqual(snapshot["relational_vectors"]["friend"]["intimacy"], 80)
        deliberate = self.tick({**stimulus, "time_pressure": "deliberate"})["psychosomatic_snapshot"]
        self.assertEqual(deliberate["affective_state"]["impulse"], "reach for a hug")
        self.assertEqual(deliberate["priority_arbitration"]["arbitration_status"], "arbitrated")
        later = self.tick({"caller_or_target": "stranger"})["psychosomatic_snapshot"]
        self.assertNotEqual(later["affective_state"]["impulse"], "reach for a hug")
        self.assertEqual(later["relational_vectors"]["stranger"]["intimacy"], 0)

    def test_approved_low_pressure_memory_survives_reload_without_pressure_commit(self):
        memory = self.directory / "memory.json"
        memory.write_text(json.dumps({
            "id": "unusual-rhythms", "kind": "footnote",
            "summary": "A guest likes unusual rhythms.",
            "reason": "It gave her a way to connect.", "cues": ["Music"],
        }))
        result = self.tick({}, "--remember", str(memory), "--commit")
        self.assertTrue(result["golem_meta"]["memory_saved"])
        self.assertFalse(result["golem_meta"]["committed_to_log"])
        self.assertFalse(self.tick({}, "--remember", str(memory))["golem_meta"]["memory_saved"])

        self.history.unlink()
        self.assertNotIn("recalled_memories", self.tick({"memory_cues": ["weather"]}))
        recalled = self.tick({"memory_cues": [" music "]})["recalled_memories"]
        self.assertEqual(recalled, [{
            "id": "unusual-rhythms", "summary": "A guest likes unusual rhythms.", "kind": "footnote",
        }])
        log = yaml.safe_load(self.log.read_text())
        self.assertEqual(log["revision"], 2)
        self.assertEqual(log["history"], [])

    def test_curiosity_uses_carried_interest_and_yields_to_pushback(self):
        self.tick({"elapsed_ms": 0, "appraisal": {"interest": 90}})
        stimulus = {"elapsed_ms": 0, "conversation": {"open_topic": "music"}}
        curious = self.tick(stimulus)
        autonomic = curious["psychosomatic_snapshot"]["autonomic_state"]
        self.assertGreaterEqual(autonomic["arousal"], 40)
        self.assertEqual(autonomic["sexual_arousal"], 0)
        self.assertEqual(curious["conversation_intent"], {"intent": "ask", "topic": "music"})
        self.assertNotIn("conversation_intent", self.tick(stimulus))
        stimulus["conversation"]["open_topic"] = "rhythm"
        stimulus["conversation"]["conflict"] = "boundary"
        self.assertEqual(self.tick(stimulus)["conversation_intent"], {
            "intent": "push_back", "conflict": "boundary", "delivery": "brief",
        })
        del stimulus["conversation"]["conflict"]
        stimulus["threat_level"] = 90
        self.assertNotIn("conversation_intent", self.tick(stimulus))

    def test_event_clock_orders_ticks_and_applies_idle_decay(self):
        first = self.tick({"event_at": "2026-11-18T21:49:00-08:00", "appraisal": {"interest": 90}})
        self.assertEqual(first["golem_meta"]["elapsed_ms"], 0)
        second = self.tick({"event_at": "2026-11-19T05:49:10Z"})
        self.assertEqual(second["next_history"]["event_sequence"], 2)
        self.assertEqual(second["golem_meta"]["elapsed_ms"], 10_000)
        self.assertEqual(second["next_history"]["appraisal_effects"]["interest"], 45)
        saved = self.history.read_bytes()
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.tick({"event_at": "2026-11-19T05:49:05Z"})
        self.assertIn("earlier than the last processed event", error.exception.stderr)
        self.assertEqual(self.history.read_bytes(), saved)
