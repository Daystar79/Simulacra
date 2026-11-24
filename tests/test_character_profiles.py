"""Two independent characters sharing the same installation and transport event IDs."""
import json
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from scripts import golem, golem_loop as loop


class TestCharacterProfiles(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profiles = self.root / "characters"
        self.pack = self.root / "both.yaml"
        self.pack.write_text("characters:\n  talia: {name: Talia}\n  selene: {name: Selene}\n")

    def cli(self, who, *args, payload=None, check=True):
        cmd = [sys.executable, str(golem.ROOT / "scripts/run.py"), "golem", "loop",
               "--characters-dir", "characters", "--character-id", who, *args]
        result = subprocess.run(cmd, cwd=self.root, input=json.dumps(payload), text=True,
                                capture_output=True, check=check)
        if check:
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result.stderr

    def test_scene_render_rechecks_profile_cards_on_resume(self):
        self.pack.write_text("characters:\n  talia: {name: Talia, age: 30, canon_adult: true}\n"
                             "  selene: {name: Selene, age: 27, canon_adult: true, cognitive_bias: PRIVATE_TEST_VALUE}\n")
        for who in ("talia", "selene"):
            self.cli(who, "init", "--card", "both.yaml")
        event = {"id": "scene", "kind": "incoming", "relationship_target": "selene",
                 "scene_characters": ["talia", "selene"], "depiction": "explicit"}
        request = self.cli("talia", "prepare", "--event", "-", payload=event)["request"]
        self.assertEqual(request["app_render"]["depiction"], "explicit")
        self.assertIn("Recovery", request["app_render"]["guide"])
        self.assertNotIn("PRIVATE_TEST_VALUE", json.dumps(request))
        partner = self.profiles / "selene" / "character.yaml"
        partner.write_text("character_id: selene\nage: 17\ncanon_adult: true\n")
        resumed = self.cli("talia", "prepare")["request"]
        self.assertEqual(resumed["app_render"], {"depiction": "sfw"})
        self.assertEqual(request["body"], resumed["body"])

    def test_parallel_cli_same_event_id_and_restart(self):
        def provision(who):
            log = self.root / (who + ".yaml")
            log.write_text(yaml.safe_dump({"memories": {"detailed": [
                {"id": "m", "summary": who + " alone recalls this", "cues": ["harbor"]}]}}))
            self.cli(who, "init", "--card", "both.yaml", "--log", str(log))
            return self.cli(who, "prepare", "--event", "-", payload={
                "id": "msg-1", "kind": "incoming", "context": "At the harbor."})["request"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            contexts = list(pool.map(provision, ("talia", "selene")))
        for request, who in zip(contexts, ("talia", "selene")):
            directory = self.profiles / who
            self.assertEqual(request["character_id"], who)
            self.assertEqual(request["identity_anchor"]["name"], who.title())
            self.assertEqual(request["recalled_memories"][0]["summary"], who + " alone recalls this")
            self.assertEqual(set(yaml.safe_load((directory / "character.yaml").read_text())), {"name", "character_id"})
            self.assertTrue((directory / "runtime.sqlite3").is_file())
            self.assertEqual(yaml.safe_load((directory / "character_log.yaml").read_text())["character_id"], who)

        decision = {"character_id": "talia", "id": "msg-1", "reply": "My answer.", "dialect": "lilting"}
        self.assertIn("character_id", self.cli("selene", "resolve", "-", payload=decision, check=False))
        self.assertIn("character_id", self.cli("selene", "resolve", "-", payload={"id": "msg-1"}, check=False))
        self.assertEqual(self.cli("talia", "resolve", "--receipt", "-", payload=decision)["character_id"], "talia")
        self.assertEqual(self.cli("selene", "prepare")["request"], contexts[1])
        self.assertEqual(self.cli("selene", "timeline"), [])
        self.assertEqual(self.cli("talia", "timeline")[0]["decision"]["reply"], "My answer.")
        self.assertIn("already contains", self.cli("talia", "init", "--card", "both.yaml", check=False))
        memory = {"id": "private", "kind": "detailed", "summary": "Talia learned the refrain.",
                  "reason": "A first lesson", "cues": ["music"]}
        self.assertTrue(self.cli("talia", "remember", "-", payload=memory)["memory_saved"])
        self.assertNotIn("refrain", (self.profiles / "selene/character_log.yaml").read_text())
        self.assertNotIn("refrain", (self.root / "talia.yaml").read_text())
        self.assertIn("refrain", (self.profiles / "talia/character_log.yaml").read_text())

    def test_relative_db_paths_follow_each_hosts_directory(self):
        # Same checkout and same relative filenames in two independent host processes.
        cmd = [sys.executable, str(golem.ROOT / "scripts/run.py"), "golem", "loop", "--db", "runtime.sqlite3"]
        for who in ("talia", "selene"):
            cwd = self.root / who
            cwd.mkdir()
            (cwd / "card.yaml").write_text("name: " + who)
            subprocess.run(cmd + ["init", "--card", "card.yaml"], cwd=cwd, check=True, capture_output=True)
            with loop.transaction(cwd / "runtime.sqlite3") as conn:
                self.assertEqual(Path(loop.runtime_config(conn)["card"]), cwd / "card.yaml")

    def test_copy_live_history_with_pending_turn_and_resume_from_new_paths(self):
        source = self.root / "legacy"
        source.mkdir()
        db, card, log = (source / name for name in ("old.db", "talia.yaml", "memories.yaml"))
        card.write_text("name: Talia")
        log.write_text("character_id: talia")
        loop.initialize_character(db, card, log=log)
        loop.wake_character(db, lambda r: {"id": "old", "dialect": "lilting", "reply": "Hello."},
                            event={"id": "old", "kind": "incoming"})
        def interrupt(_):
            raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            loop.wake_character(db, interrupt, event={"id": "next", "kind": "incoming"})
        self.cli("talia", "init", "--from-db", str(db))
        # Moving the entire profile must never redirect later reads or writes to its old paths.
        moved_root = self.root / "moved"
        self.profiles.rename(moved_root)
        new_db = loop.character_database(moved_root, "talia")
        def decide(request):
            self.assertEqual(request["dialect"], "lilting")
            self.assertEqual(Path(request["character"]["card"]).parent, new_db.parent)
            return {"character_id": request["character_id"], "id": "next", "reply": "Morning."}
        result = loop.wake_character(new_db, decide, character_id="talia")
        self.assertEqual(result["events"][0]["character_id"], "talia")
        with loop.transaction(db) as conn:
            self.assertEqual(loop.pending_request(conn)["event"]["id"], "next")
        with self.assertRaisesRegex(ValueError, "does not match"):
            loop.wake_character(new_db, self.fail, character_id="selene")

    def test_wrong_log_history_and_directory_rejected(self):
        log = self.root / "log.yaml"
        log.write_text("character_id: selene")
        self.assertIn("mismatch", self.cli("talia", "init", "--card", "both.yaml", "--log", str(log), check=False))
        self.assertFalse((self.profiles / "talia").exists())
        history = self.root / "history.json"
        history.write_text('{"character_id":"selene"}')
        self.assertIn("history", self.cli("talia", "init", "--card", "both.yaml",
                                         "--import-history", str(history), check=False))
        self.cli("talia", "init", "--card", "both.yaml")
        (self.profiles / "selene").symlink_to(self.profiles / "talia", target_is_directory=True)
        self.assertIn("distinct", self.cli("selene", "prepare", check=False))
        self.assertIn("lowercase", self.cli("../talia", "prepare", check=False))
