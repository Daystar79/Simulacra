"""Activation must respond and recover across ordinary persistent host turns."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts import golem, golem_loop


class TestGolemActivation(unittest.TestCase):
    def test_enduring_relationship_attraction_survives_idle_day(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"name": "Rowan", "age": 30, "canon_adult": True}, None)
        state["relational_baselines"] = {"caller": {"attraction_emotional": 72, "attraction_physical": 48}}
        first = golem.run_golem(state, {"elapsed_ms": 0, "caller_or_target": "caller",
                                        "appraisal": {"attraction": 80}}, realms, {})
        idle = golem.run_golem(state, {"elapsed_minutes": 24 * 60, "caller_or_target": "caller"},
                               realms, first["next_history"])
        vectors = idle["psychosomatic_snapshot"]["relational_vectors"]["caller"]
        self.assertEqual((vectors["attraction_emotional"], vectors["attraction_physical"]), (72, 48))
        self.assertEqual(idle["next_history"]["appraisal_effects"]["attraction"], 0)

    def test_calibrated_elapsed_time_and_sleep_recovery(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"name": "Rowan"}, None)
        one_hour = golem.run_golem(state, {"elapsed_minutes": 60}, realms, {})["next_history"]
        self.assertAlmostEqual(one_hour["hunger"], 4)
        self.assertAlmostEqual(one_hour["last_fatigue"], 15.8)
        eight_hours = golem.run_golem(state, {"elapsed_minutes": 480}, realms, {})["next_history"]
        self.assertAlmostEqual(eight_hours["hunger"], 32)
        one_day = golem.run_golem(state, {"elapsed_minutes": 24 * 60}, realms, {})["next_history"]
        self.assertAlmostEqual(one_day["hunger"], 96)
        working = golem.run_golem(state, {"elapsed_minutes": 8 * 60, "exertion": 50}, realms, {})["next_history"]
        self.assertAlmostEqual(working["last_fatigue"], 37.4)
        self.assertAlmostEqual(working["sleep_debt"], 12)
        slept = golem.run_golem(state, {"elapsed_minutes": 480, "activity": "sleeping"}, realms,
                                {"last_fatigue": 40, "sleep_debt": 40})["next_history"]
        self.assertEqual(slept["last_fatigue"], 0)
        self.assertEqual(slept["sleep_debt"], 0)
        self.assertEqual(slept["hunger"], 16)
        multi_day = golem.run_golem(state, {"elapsed_minutes": 5 * 24 * 60}, realms, {})["next_history"]
        self.assertEqual(multi_day["hunger"], 96)  # One tick is capped at 24 simulated hours.

    def test_65_turns_through_the_host_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db, card = root / "runtime.db", root / "card.yaml"
            card.write_text("name: Rowan\nage: 30\ncanon_adult: true\n")
            start = datetime.now(timezone.utc) - timedelta(hours=2)
            golem_loop.initialize_character(db, card, history_at=start.isoformat())
            snapshots = []

            def decide(request):
                snapshots.append(request["tick"]["psychosomatic_snapshot"]["autonomic_state"])
                decision = {"id": request["event"]["id"]}
                if decision["id"] == "30":
                    decision["appraisal"] = {"interest": 80, "attraction": 70}
                return decision

            for turn in range(65):
                result = golem_loop.wake_character(db, decide, event={
                    "id": str(turn), "kind": "incoming",
                    "at": (start + timedelta(minutes=turn)).isoformat(),
                    "stimulus": {"activity": "sleeping" if turn < 10 else "awake",
                                 "exertion": 80 if 10 <= turn < 20 else 0},
                })
                if turn == 30:
                    response = result["events"][0]["body_response"]
                    self.assertGreater(response["after"]["arousal"], response["before"]["arousal"])
                    self.assertGreater(response["after"]["sexual_arousal"], 0)
                    with golem_loop.transaction(db) as connection:
                        saved = golem_loop.runtime_config(connection)["history"]
                        self.assertEqual(round(saved["sexual_arousal"]), response["after"]["sexual_arousal"])
            self.assertLess(snapshots[0]["arousal"], snapshots[10]["arousal"])
            self.assertGreater(snapshots[19]["arousal"], snapshots[29]["arousal"])
            neutral = [body["sexual_arousal"] for body in snapshots[:31]]
            self.assertEqual(set(neutral), {0})
            self.assertLess(max(neutral), response["after"]["sexual_arousal"])
            self.assertGreater(snapshots[31]["sexual_arousal"], snapshots[32]["sexual_arousal"])
            self.assertGreater(snapshots[32]["sexual_arousal"], snapshots[-1]["sexual_arousal"])
            self.assertEqual(snapshots[-1]["sexual_arousal"], 0)

    def test_cue_depends_on_character_appraisal(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"name": "Ari", "age": 35, "canon_adult": True}, None)
        scene = {"elapsed_ms": 0, "caller_or_target": "guest", "intimacy_cue": True}
        for attraction in (0, 70):
            with self.subTest(attraction=attraction):
                tick = golem.run_golem(state, {**scene, "appraisal": {
                    "interest": 80, "attraction": attraction,
                }}, realms, {})
                level = tick["next_history"]["sexual_arousal"]
                self.assertEqual(level > 0, attraction > 0)
                self.assertNotIn("conversation_intent", tick)
                later = golem.run_golem(state, {"elapsed_minutes": 2}, realms, tick["next_history"])
                self.assertAlmostEqual(later["next_history"]["sexual_arousal"], level / 2)

    def test_worry_brakes_the_same_cue_and_same_instant_is_stable(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"age": 30, "canon_adult": True}, None)
        calm = golem.run_golem(state, {"elapsed_ms": 0, "appraisal": {"attraction": 80}}, realms, {})
        worried = golem.run_golem(state, {"elapsed_ms": 0, "appraisal": {"unease": 80}},
                                  realms, calm["next_history"])
        before = calm["psychosomatic_snapshot"]["autonomic_state"]
        after = worried["psychosomatic_snapshot"]["autonomic_state"]
        self.assertEqual(before["sexual_excitation"], after["sexual_excitation"])
        self.assertGreater(after["sexual_inhibition"], before["sexual_inhibition"])
        self.assertLess(after["sexual_arousal"], before["sexual_arousal"])
        repeat = golem.run_golem(state, {"elapsed_ms": 0}, realms, worried["next_history"])
        self.assertEqual(repeat["next_history"]["sexual_arousal"], worried["next_history"]["sexual_arousal"])

    def test_sleep_response_survives_reload_without_implying_attraction(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for age, adult in [(30, True), (17, True), (30, False), (None, True)]:
            card = {"canon_adult": adult}
            if age is not None:
                card["age"] = age
            state, _ = golem.overlay_log(card, None)
            history = {}
            for minutes in (50, 25):
                tick = golem.run_golem(state, {"elapsed_minutes": minutes, "activity": "sleeping"},
                                       realms, history)
                history = tick["next_history"]
            eligible = adult and age is not None and age >= 18
            self.assertEqual(history["sexual_arousal"] > 0, eligible)
            self.assertEqual(history["sexual_excitation"] > 0, eligible)
            self.assertEqual(history["appraisal_effects"]["attraction"], 0)
            self.assertNotIn("conversation_intent", tick)
            bond = tick["psychosomatic_snapshot"]["relational_vectors"]["caller"]
            self.assertEqual((bond["attraction_physical"], bond["attraction_emotional"]), (0, 0))
            woke = golem.run_golem(state, {"elapsed_minutes": 2, "activity": "awake"}, realms, history)
            self.assertEqual(woke["next_history"]["minutes_asleep"], 0)
            self.assertAlmostEqual(woke["next_history"]["sexual_arousal"], history["sexual_arousal"] / 2)

    def test_legacy_history_recovers_and_age_gate_discards_carried_response(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for age, confirmed, expected in [(30, True, 25), (17, True, 0), (30, False, 0)]:
            with self.subTest(age=age, confirmed=confirmed):
                state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed, "sexual_drive_baseline": 0}, None)
                tick = golem.run_golem(state, {"elapsed_minutes": 2}, realms, {"sexual_arousal": 50})
                self.assertEqual(tick["next_history"]["sexual_arousal"], expected)
                self.assertEqual(tick["psychosomatic_snapshot"]["autonomic_state"]["sexual_arousal"], expected)

    def test_high_arousal_triggers_reactive_regime(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"age": 30, "canon_adult": True}, None)
        tick = golem.run_golem(
            state,
            {"elapsed_ms": 0, "threat_level": 10, "social_pressure": 20, "exertion": 100, "appraisal": {"interest": 90}},
            realms,
            {},
        )
        auto = tick["psychosomatic_snapshot"]["autonomic_state"]
        self.assertGreaterEqual(auto["arousal"], 75)
        self.assertLess(auto["stress"], 70)
        self.assertEqual(auto["cognitive_regime"], "reactive")

    def test_relational_baselines_and_empty_log_overlay(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_log = root / "empty_log.yaml"
            empty_log.write_text("# empty\n")
            card = {"name": "Rowan", "transformation_weights": None, "voice": None, "skills": None}
            state, log_data = golem.overlay_log(card, empty_log)
            self.assertEqual(log_data, {})

            baseline_log = root / "baseline_log.yaml"
            baseline_log.write_text(yaml.safe_dump({
                "relational_baselines": {
                    "guest": {
                        "emotional_safety": 82,
                        "attraction_physical": 40,
                        "attraction_emotional": 55,
                        "respect_competence": 78,
                        "status_dynamic": "equals",
                        "resentment_friction": 12,
                        "relational_momentum": "deepening",
                    }
                }
            }))
            state, _ = golem.overlay_log({"name": "Rowan", "age": 30, "canon_adult": True}, baseline_log)
            tick = golem.run_golem(state, {"elapsed_ms": 0, "caller_or_target": "guest", "threat_level": 0}, realms, {})
            vec = tick["psychosomatic_snapshot"]["relational_vectors"]["guest"]
            self.assertEqual(vec["emotional_safety"], 82)
            self.assertEqual(vec["respect_competence"], 78)
            self.assertEqual(vec["status_dynamic"], "equals")
            self.assertEqual(vec["resentment_friction"], 12)
            self.assertEqual(vec["relational_momentum"], "deepening")
