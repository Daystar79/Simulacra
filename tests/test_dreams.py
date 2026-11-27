import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts import golem_loop as loop


class TestDreams(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db, self.log, card = (root / name for name in ("state.db", "log.yaml", "card.yaml"))
        card.write_text("name: Mira\nage: 12\n")
        self.log.write_text("memories:\n  detailed:\n    - {id: ferry, summary: An old ferry, cues: [water]}\n")
        self.start = datetime.now(timezone.utc) - timedelta(days=2)
        loop.initialize_character(self.db, card, log=self.log, history_at=self.start.isoformat())

    def turn(self, name, minute, decision=None, *, kind="world", split=False, **fields):
        packet = []
        def decide(req):
            req = req["dynamic_turn"] if split else req
            packet.append(req)
            return {"id": req["event"]["id"], **(decision or {})}
        result = loop.wake_character(self.db, decide, split_cache=split, max_events=1,
                                     event={"id": name, "at": (self.start + timedelta(minutes=minute)).isoformat(),
                                            "kind": kind, **fields})
        return packet, result

    def memories(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute("SELECT kind, summary FROM memories").fetchall()

    def test_private_dream_until_waking_and_typed_recall(self):
        self.turn("talk", 0, kind="incoming", text="Who will look after the orchard?", relationship_target="Ari")
        self.turn("bed", 5, stimulus={"activity": "sleeping"})
        short, _ = self.turn("short", 10)
        self.assertNotIn("dream_opportunity", short[0])
        dream = {"scene": "A silent room full of paper trees.", "fragment": "A paper orchard.",
                 "cues": ["paper"], "mood": {"wonder": 34}}
        sleeping, _ = self.turn("night", 80, {"dream": dream}, split=True)
        offer = sleeping[0]["dream_opportunity"]
        self.assertEqual(offer["stage"], "REM")
        self.assertEqual(offer["conversation"]["speaker"], "Ari")
        self.assertEqual(offer["memory"]["summary"], "An old ferry")
        self.assertEqual(self.memories(), [])
        again, _ = self.turn("still-asleep", 82)
        self.assertNotIn("dream_opportunity", again[0])
        self.assertNotIn("waking_dream", again[0])
        waking, _ = self.turn("awake", 85, stimulus={"activity": "awake"})
        self.assertEqual(waking[0]["waking_dream"]["fragment"], dream["fragment"])
        self.assertEqual(waking[0]["emotions"]["wonder"], 34)
        self.assertNotIn(dream["scene"], json.dumps(waking[0]))
        self.assertEqual(self.memories(), [("dream", "Dream fragment: A paper orchard.")])
        self.assertEqual(yaml.safe_load(self.log.read_text())["memories"]["dream"][0]["id"], "dream:night")
        retry, _ = self.turn("awake", 85, stimulus={"activity": "awake"})
        self.assertFalse(retry)
        revisit, _ = self.turn("tomorrow", 1500, kind="incoming", text="Do you have any paper?")
        self.assertNotIn("waking_dream", revisit[0])
        recalled = next(m for m in revisit[0]["recalled_memories"] if m["id"] == "dream:night")
        self.assertEqual(recalled["kind"], "dream")
        self.assertEqual(len(self.memories()), 1)

    def test_sleep_activity_can_end_with_only_a_mood(self):
        self.turn("bed", 0, {"activity": {"op": "start", "kind": "nap", "state": "sleeping",
                                         "id": "nap", "duration_seconds": 30 * 60}})
        def wake(req):
            self.assertEqual(req["dream_opportunity"]["stage"], "NREM")
            return {"id": req["event"]["id"], "dream": {"scene": "Hidden room", "mood": {"unease": 20}},
                    "activity": {"op": "complete", "id": "nap"}}
        loop.wake_character(self.db, wake, max_events=1)
        after, _ = self.turn("after", 31)
        self.assertEqual(after[0]["waking_dream"]["mood"], {"unease": 20})
        self.assertNotIn("Hidden room", json.dumps(after[0]))
        self.assertEqual(self.memories(), [])
        later, _ = self.turn("later", 32)
        self.assertNotIn("waking_dream", later[0])

    def test_sparse_sleep_and_forgotten_dream(self):
        with self.assertRaisesRegex(ValueError, "sleep opportunity"):
            self.turn("day", 0, {"dream": {"scene": "Impossible while awake"}})
        self.turn("day", 0)
        self.turn("bed", 500, stimulus={"activity": "sleeping"})
        waking, _ = self.turn("wake", 575, {"dream": {"scene": "A quiet garden"}}, stimulus={"activity": "awake"})
        self.assertEqual(waking[0]["dream_opportunity"]["stage"], "REM")
        after, _ = self.turn("morning", 576)
        self.assertNotIn("waking_dream", after[0])
        self.assertNotIn("A quiet garden", json.dumps(after[0]))
        self.assertEqual(self.memories(), [])
