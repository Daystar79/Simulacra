import json
import sqlite3
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import golem, golem_loop, run


class TestForensicRecoveryAndArchitectureFixes(unittest.TestCase):
    def test_closed_account_language_stays_with_its_wound_across_wakes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for owner, wound in (("talia", "Closed Account — keeps the file shut"),
                                 ("sophia", "Completeness"), ("other", "")):
                card = Path(tmp) / f"{owner}.yaml"
                data = {"name": owner, "cognitive_bias": wound}
                if owner == "sophia":
                    data.update(cognitive_gift="The Ledger", subconscious_visceral_truth="An entry is missing.",
                                conscious_rationalization="I want an accurate count.")
                card.write_text(yaml.safe_dump(data), encoding="utf-8")
                golem_loop.initialize_character(Path(tmp) / f"{owner}.sqlite3", card)
            for turn, owner in enumerate(("talia", "sophia", "other", "talia")):
                with self.subTest(owner=owner, turn=turn):
                    def decide(request):
                        snap = request["tick"]["psychosomatic_snapshot"]
                        bias = snap["subconscious_bias"]
                        drives = [d["drive_name"] for d in snap["priority_arbitration"]["competing_drives"]]
                        self.assertEqual("deflect_and_protect_closed_file" in drives, owner == "talia")
                        self.assertEqual("Account stays closed" in bias["subconscious_visceral_truth"], owner == "talia")
                        if owner == "sophia":
                            self.assertEqual(bias["subconscious_visceral_truth"], "An entry is missing.")
                            self.assertEqual(bias["conscious_rationalization"], "I want an accurate count.")
                        return {"id": request["event"]["id"]}
                    golem_loop.wake_character(Path(tmp) / f"{owner}.sqlite3", decide, event={
                        "id": str(turn), "kind": "incoming", "stimulus": {"threat_level": 45}})

    def test_lock_releases_after_host_import_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wake.lock"
            with self.assertRaisesRegex(ImportError, "host dependency"):
                with golem_loop.file_lock(path):
                    raise ImportError("host dependency")
            with golem_loop.file_lock(path):
                pass

    def test_windows_launcher_uses_active_python(self):
        with patch.dict(run.os.environ, {"CM_FORCE_WRAPPER": ""}), patch.object(run, "run_python_core", return_value=0) as core:
            self.assertEqual(run.run_windows_wrapper(Path("validate.ps1"), []), 0)
            core.assert_called_once_with("validate", [])

    def test_dynamic_subconscious_bias_and_three_state_bias_transitions(self):
        realms = golem_loop.load_cached_realm_data()
        sophia_card = {
            "character_id": "sophia",
            "name": "Sophia",
            "age": 30,
            "canon_adult": True,
            "active_focus": "Realm VIII — Integration",
            "cognitive_bias": "Completeness",
            "cognitive_gift": "The Ledger",
            "transformation_weights": {"bias_strength": 55},
            "defense_posture_default": "intellectualize",
        }
        state, _ = golem.overlay_log(sophia_card, None)

        # 1. Mundane low-stakes turn initializes/stays DORMANT and never leaks Talia's "Account stays closed"
        dormant_tick = golem.run_golem(state, {"elapsed_ms": 0}, realms, {})
        sb_dormant = dormant_tick["psychosomatic_snapshot"]["subconscious_bias"]
        self.assertEqual(sb_dormant["bias_state"], "DORMANT")
        self.assertEqual(sb_dormant["active_wound"], "Completeness")
        self.assertEqual(sb_dormant["active_gift"], "The Ledger")
        self.assertNotIn("Account stays closed", sb_dormant["subconscious_visceral_truth"])

        # 2. High interest / reward activates GENERATIVE_ACTIVE and shifts winning_drive to warm_presence_and_intake
        gen_tick = golem.run_golem(
            state,
            {"elapsed_ms": 1000, "appraisal": {"interest": 70, "delight": 50}},
            realms,
            dormant_tick["next_history"],
        )
        sb_gen = gen_tick["psychosomatic_snapshot"]["subconscious_bias"]
        self.assertEqual(sb_gen["bias_state"], "GENERATIVE_ACTIVE")
        self.assertIn("The Ledger", sb_gen["subconscious_visceral_truth"])
        self.assertEqual(
            gen_tick["psychosomatic_snapshot"]["priority_arbitration"]["winning_drive"],
            "warm_presence_and_intake",
        )

        # 3. Threat activates DEFENSIVE_ACTIVE with character-specific defensive drive
        def_tick = golem.run_golem(
            state,
            {"elapsed_ms": 1000, "threat_level": 45, "appraisal": {"unease": 50}},
            realms,
            gen_tick["next_history"],
        )
        sb_def = def_tick["psychosomatic_snapshot"]["subconscious_bias"]
        self.assertEqual(sb_def["bias_state"], "DEFENSIVE_ACTIVE")
        self.assertEqual(sb_def["defense_posture"], "intellectualize")
        drive_names = [
            d["drive_name"]
            for d in def_tick["psychosomatic_snapshot"]["priority_arbitration"]["competing_drives"]
        ]
        self.assertIn("defend_completeness", drive_names)
        self.assertNotIn("deflect_and_protect_closed_file", drive_names)

    def test_relationship_evolution_feeds_relational_vectors_and_drifts_toward_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "character.yaml"
            log = root / "character_log.yaml"
            db = root / "runtime.sqlite3"
            card.write_text("name: Sophia\ncharacter_id: sophia\nage: 30\ncanon_adult: true\n", encoding="utf-8")
            log.write_text(
                yaml.safe_dump({
                    "character_id": "sophia",
                    "relational_baselines": {
                        "Robert": {
                            "emotional_safety": 74,
                            "attraction_physical": 55,
                            "attraction_emotional": 68,
                            "respect_competence": 88,
                            "status_dynamic": "equals",
                            "resentment_friction": 4,
                            "relational_momentum": "building",
                        }
                    },
                }),
                encoding="utf-8",
            )
            start = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(
                db, card, log=log, character_id="sophia", history_at=start.isoformat()
            )

            # Turn 1: relationship_change lowers emotional_safety by 14 (74 -> 60) with drift 7/day back toward 74
            golem_loop.wake_character(
                db,
                lambda req: {
                    "character_id": "sophia",
                    "id": req["event"]["id"],
                    "experience": {
                        "relationship_change": {
                            "target": "Robert",
                            "delta": {"emotional_safety": -14, "resentment_friction": 10},
                            "drift_per_day": {"emotional_safety": 7.0},
                        }
                    },
                },
                character_id="sophia",
                event={
                    "character_id": "sophia",
                    "id": "rel-1",
                    "kind": "incoming",
                    "at": (start + timedelta(minutes=10)).isoformat(),
                    "stimulus": {"caller_or_target": "Robert"},
                    "context": "A tense exchange.",
                },
            )

            # Turn 2: 1 day later, emotional_safety has drifted half-way back (60 -> 67) and feeds relational_vectors
            seen = []
            golem_loop.wake_character(
                db,
                lambda req: (seen.append(req) or {"character_id": "sophia", "id": req["event"]["id"]}),
                character_id="sophia",
                event={
                    "character_id": "sophia",
                    "id": "rel-2",
                    "kind": "incoming",
                    "at": (start + timedelta(days=1, minutes=10)).isoformat(),
                    "stimulus": {"caller_or_target": "Robert"},
                    "context": "Checking in the next day.",
                },
            )
            req = seen[0]
            self.assertEqual(req["relationship_state"]["values"]["emotional_safety"], 67.0)
            vec = req["tick"]["psychosomatic_snapshot"]["relational_vectors"]["Robert"]
            self.assertEqual(vec["emotional_safety"], 67)
            self.assertGreaterEqual(vec["resentment_friction"], 14)

    def test_contextual_expectations_recalculate_and_text_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "character.yaml"
            db = root / "runtime.sqlite3"
            card.write_text("name: Talia\ncharacter_id: talia_comedy\n", encoding="utf-8")
            start = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="talia_comedy", history_at=start.isoformat())

            # Record an experience with situational expectation_context
            golem_loop.wake_character(
                db,
                lambda req: {
                    "character_id": "talia_comedy",
                    "id": req["event"]["id"],
                    "experience": {
                        "topic": "cooking",
                        "benefit": 88,
                        "cost": 20,
                        "expectation_context": {"situation": "kitchen with robert"},
                    },
                },
                character_id="talia_comedy",
                event={
                    "character_id": "talia_comedy",
                    "id": "cook-1",
                    "kind": "incoming",
                    "at": (start + timedelta(minutes=5)).isoformat(),
                    "topic": "cooking",
                    "context": "Making stroganoff.",
                },
            )

            # Wipe runtime expectations and recalculate from ledger
            with golem_loop.transaction(db) as connection:
                cfg = golem_loop.runtime_config(connection)
                cfg["expectations"] = {}
                cfg["contextual_expectations"] = {}
                connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(cfg),))
                rebuilt = golem_loop.recalculate_expectations(connection, cfg)
                self.assertIn("cooking", rebuilt["expectations"])
                self.assertIn("cooking", rebuilt["contextual_expectations"])

            # Next event after 3 hours (outside 2h recent window) mentions 'cooking' in text without event.topic
            seen = []
            golem_loop.wake_character(
                db,
                lambda req: (seen.append(req) or {"character_id": "talia_comedy", "id": req["event"]["id"]}),
                character_id="talia_comedy",
                event={
                    "character_id": "talia_comedy",
                    "id": "cook-2",
                    "kind": "incoming",
                    "at": (start + timedelta(hours=3)).isoformat(),
                    "expectation_context": {"situation": "kitchen with robert"},
                    "context": "Do you feel like cooking dinner tonight?",
                },
            )
            self.assertIn("cooking", seen[0]["expectations"])
            self.assertEqual(seen[0]["situational_expectations"]["cooking"], {"benefit": 88, "cost": 20})

    def test_utterance_relevant_learned_observations_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "character.yaml"
            db = root / "runtime.sqlite3"
            card.write_text("name: Talia\ncharacter_id: talia_comedy\n", encoding="utf-8")
            start = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, character_id="talia_comedy", history_at=start.isoformat())

            golem_loop.wake_character(
                db,
                lambda req: {
                    "character_id": "talia_comedy",
                    "id": req["event"]["id"],
                    "learning": {
                        "topic": "sherry, white pepper, tarragon",
                        "observation": "Cream of chicken soup wakes up with dry sherry and tarragon.",
                        "sources": [],
                    },
                },
                character_id="talia_comedy",
                event={
                    "character_id": "talia_comedy",
                    "id": "learn-1",
                    "kind": "incoming",
                    "at": (start + timedelta(minutes=5)).isoformat(),
                    "context": "Let's talk soup.",
                },
            )

            seen = []
            golem_loop.wake_character(
                db,
                lambda req: (seen.append(req) or {"character_id": "talia_comedy", "id": req["event"]["id"]}),
                character_id="talia_comedy",
                event={
                    "character_id": "talia_comedy",
                    "id": "ask-soup",
                    "kind": "incoming",
                    "at": (start + timedelta(hours=4)).isoformat(),
                    "context": "Did we put sherry and tarragon in that recipe?",
                },
            )
            learned = seen[0].get("learned", [])
            self.assertEqual(len(learned), 1)
            self.assertEqual(learned[0]["topic"], "sherry, white pepper, tarragon")

    def test_specimen_recovery_migration_isolation_and_rollback(self):
        specimen_root = Path(__file__).resolve().parents[2]
        if not (specimen_root / "talia.sqlite3").is_file():
            self.skipTest("Specimen files not present in parent workspace")

        from scripts import recover_characters

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "recovered_test"
            manifest = recover_characters.recover_installation(
                specimen_root, out_dir, carry_judgment_calls=False
            )
            self.assertTrue(manifest["verification"]["specimens_unmodified"])
            self.assertTrue(
                manifest["verification"]["clean_profile_isolation"]["talia_comedy"]["zero_cross_character_leaks"]
            )
            self.assertTrue(
                manifest["verification"]["clean_profile_isolation"]["sophia"]["zero_cross_character_leaks"]
            )
            self.assertEqual(
                manifest["verification"]["migrated_profile_integrity"]["talia_comedy"]["events_preserved"], 239
            )
            self.assertEqual(
                manifest["verification"]["migrated_profile_integrity"]["sophia"]["events_preserved"], 81
            )

            # Verify lossless decompression of an archived request from the migrated copy
            talia_mig_db = Path(manifest["migrated_profiles"]["talia_comedy"]["database"])
            conn = sqlite3.connect(f"file:{talia_mig_db}?mode=ro", uri=True)
            try:
                compressed = conn.execute(
                    "SELECT compressed FROM request_archive WHERE event_id = 'msg-pick-your-dialect-20261123'"
                ).fetchone()[0]
                restored = json.loads(zlib.decompress(compressed).decode("utf-8"))
                self.assertEqual(restored["event"]["id"], "msg-pick-your-dialect-20261123")
            finally:
                conn.close()

            # Test rollback procedure
            rb = recover_characters.rollback_recovery(specimen_root, out_dir)
            self.assertTrue(rb["rolled_back"])
            self.assertTrue(rb["specimens_verified"])
            self.assertFalse(out_dir.exists())


if __name__ == "__main__":
    unittest.main()
