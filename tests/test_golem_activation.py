"""Activation must respond and recover across ordinary persistent host turns."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts import golem, golem_loop


class TestGolemActivation(unittest.TestCase):
    def test_legacy_card_backfill_preserves_overrides_and_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.yaml"
            path.write_text("characters:\n  a:\n    name: A # keep me\n"
                            "    physiology_calibration: {hunger_awake_per_hour: 0}\n"
                            "    canon_adult: false\n  b: {name: B}\n")
            before = yaml.safe_load(path.read_text())["characters"]["a"]
            state, _ = golem.overlay_log(before, None)
            self.assertEqual(golem.load_character(path, "a"), before)
            golem.migrate_character_card(path, "a")
            card = golem.load_character(path, "a")
            self.assertEqual(golem.overlay_log(card, None)[0], state)
            self.assertEqual(card["physiology_calibration"]["hunger_awake_per_hour"], 0)
            self.assertEqual(card["age"], 0)
            self.assertFalse(card["canon_adult"])
            self.assertFalse(list(golem.missing_card_fields(card)))
            self.assertIn("# keep me", path.read_text())
            self.assertEqual(yaml.safe_load(path.read_text())["characters"], {"a": card, "b": {"name": "B"}})
            stamp = path.stat().st_mtime_ns
            self.assertEqual(golem.load_character(path, "a"), card)
            self.assertEqual(path.stat().st_mtime_ns, stamp)

    def test_bodily_pleasures_are_independent_of_arousal_age_and_each_other(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for age, confirmed in ((31, True), (31, False), (17, True)):
            state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed}, None)
            eligible = age >= 18 and confirmed
            for physical, sexual, arousal in ((70, 0, 0), (0, 60, 0), (60, 50, 0), (0, 0, 75)):
                with self.subTest(age=age, confirmed=confirmed, physical=physical, sexual=sexual, arousal=arousal):
                    tick = golem.run_golem(state, {"physical_pleasure": physical, "sexual_pleasure": sexual,
                                                   "sexual_arousal": arousal, "elapsed_ms": 0}, realms, {})
                    body = tick["psychosomatic_snapshot"]["autonomic_state"]
                    self.assertEqual(body["physical_pleasure"], physical)
                    self.assertEqual(body["sexual_pleasure"], sexual if eligible else 0)
                    self.assertEqual(body["sexual_arousal"], arousal if eligible else 0)
            if not eligible:
                tick = golem.run_golem(state, {"elapsed_ms": 0}, realms, {"sexual_pleasure": 88})
                self.assertEqual(tick["next_history"]["sexual_pleasure"], 0)
        adult, _ = golem.overlay_log({"age": 30, "canon_adult": True}, None)
        for key in ("physical_pleasure", "sexual_pleasure"):
            for invalid in (True, -1, 101, "60"):
                with self.assertRaisesRegex(ValueError, key):
                    golem.run_golem(adult, {"elapsed_ms": 0, key: invalid}, realms, {})

    def test_orgasm_threshold_requires_a_fresh_crossing_after_recovery(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"age": 32, "canon_adult": True, "physiology_calibration": {
            "orgasm_threshold": 90, "orgasm_recovery_minutes": 4}}, None)

        def tick(history, minutes=0, **stimulus):
            result = golem.run_golem(state, {"elapsed_minutes": minutes, **stimulus}, realms, history)
            return result["next_history"], result["psychosomatic_snapshot"]["autonomic_state"]

        history, before = tick({}, sexual_pleasure=89, physical_pleasure=100, sexual_arousal=60)
        self.assertFalse(before["orgasm"])
        history, peak = tick(history, sexual_pleasure=90)
        self.assertTrue(peak["orgasm"])
        self.assertEqual(peak["orgasm_recovery"], 100)
        self.assertIn("involuntary contractions", peak["somatic_map"]["pelvic_floor"])
        self.assertGreater(peak["arousal"], before["arousal"])
        self.assertGreater(peak["fatigue"], before["fatigue"])
        self.assertLess(peak["sexual_drive"], before["sexual_drive"])
        self.assertEqual(peak["physical_pleasure"], before["physical_pleasure"])
        history, same_time = tick(history, sexual_pleasure=100)
        self.assertFalse(same_time["orgasm"])
        self.assertEqual(same_time["fatigue"], peak["fatigue"])
        history, resting = tick(history, 2, sexual_pleasure=0)
        self.assertEqual(resting["orgasm_recovery"], 50)
        self.assertGreater(resting["sexual_inhibition"], peak["sexual_inhibition"])
        history, early = tick(history, sexual_pleasure=95)
        self.assertFalse(early["orgasm"])
        history, held = tick(history, 2, sexual_pleasure=95)
        self.assertFalse(held["orgasm"])
        self.assertEqual(held["orgasm_recovery"], 0)
        history, _ = tick(history, sexual_pleasure=80)
        _, next_peak = tick(history, sexual_pleasure=90)
        self.assertTrue(next_peak["orgasm"])

    def test_orgasm_profile_recovery_and_adult_gate(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for sex, minutes in (("female", 7.2), ("male", 12.8), ("unspecified", 10), ("intersex", 10)):
            state, _ = golem.overlay_log({"biological_sex": sex, "age": 30, "canon_adult": True}, None)
            tick = golem.run_golem(state, {"elapsed_ms": 0, "sexual_pleasure": 85}, realms, {})
            self.assertAlmostEqual(tick["next_history"]["orgasm_recovery_minutes_left"], minutes)
        for age, confirmed in ((17, True), (30, False)):
            state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed}, None)
            tick = golem.run_golem(state, {"sexual_pleasure": 100}, realms, {"orgasm_recovery_minutes_left": 9})
            self.assertFalse(tick["psychosomatic_snapshot"]["autonomic_state"]["orgasm"])
            self.assertEqual(tick["next_history"]["orgasm_recovery_minutes_left"], 0)

    def test_profile_changes_body_and_authored_baselines_take_precedence(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        def tick(sex, **card):
            state, _ = golem.overlay_log(
                {"age": 30, "canon_adult": True, "biological_sex": sex, **card}, None)
            return golem.run_golem(state, {"elapsed_minutes": 12, "threat_level": 55,
                                          "appraisal": {"attraction": 45}}, realms, {})

        female = tick("female")
        male = tick("male")
        first = female["psychosomatic_snapshot"]["autonomic_state"]
        second = male["psychosomatic_snapshot"]["autonomic_state"]
        for field in ("arousal", "sexual_arousal", "endocrine_state", "somatic_telemetry"):
            self.assertNotEqual(first[field], second[field])
        self.assertEqual(female["psychosomatic_snapshot"]["relational_vectors"],
                         male["psychosomatic_snapshot"]["relational_vectors"])
        profile = golem.somatic_profile({"age": 30, "biological_sex": "female"})
        for sex in ("male", "intersex", None):
            self.assertEqual(tick(sex, somatic_baselines=profile,
                                  arousal_regions=["clitoris", "labia", "vagina"]), female)
        self.assertEqual(golem.somatic_profile({"name": "Sophia", "gender": "woman"}),
                         golem.SOMATIC_BASELINES)
        for custom in ({"estradiol": True}, {"testosterone": 102}, {"mood": 55}):
            with self.assertRaises(ValueError):
                golem.somatic_profile({"somatic_baselines": custom})

    def test_arousal_map_localizes_the_current_response_and_recovers(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        adult = {"age": 30, "canon_adult": True}
        cases = [
            ({"biological_sex": "female"}, {"clitoris", "labia", "vagina"}),
            ({"biological_sex": "male"}, {"penis", "scrotum"}),
            ({"biological_sex": "intersex", "arousal_regions": ["clitoris", "scrotum"]},
             {"clitoris", "scrotum"}),
            ({"biological_sex": "female", "arousal_regions": []}, set()),
            ({}, set()),
        ]
        for card, sites in cases:
            with self.subTest(card=card):
                state, _ = golem.overlay_log({**adult, **card}, None)
                stimulated = golem.run_golem(state, {"sexual_arousal": 90, "elapsed_ms": 0}, realms, {})
                body = stimulated["psychosomatic_snapshot"]["autonomic_state"]
                regions = body["somatic_map"]
                self.assertEqual(sites, set(regions).intersection(golem.GENITAL_RESPONSE_SITES))
                self.assertEqual(regions["pelvis"]["arousal"], body["sexual_arousal"])
                self.assertTrue({"pelvic_floor", "perineum", "lower_abdomen", "inner_thigh", "nipple"} <= regions.keys())
                quiet = golem.run_golem(state, {"elapsed_minutes": 180}, realms, stimulated["next_history"])
                cooled = quiet["psychosomatic_snapshot"]["autonomic_state"]["somatic_map"]
                self.assertTrue((sites | {"pelvis", "perineum", "nipple"}).isdisjoint(cooled))
        with self.assertRaisesRegex(ValueError, "arousal_regions"):
            golem.overlay_log({**adult, "arousal_regions": "penis"}, None)

    def test_activation_alone_and_age_gate_keep_local_responses_distinct(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for age, confirmed, signal in ((30, True, 0), (17, True, 90), (30, False, 90)):
            state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed, "biological_sex": "male"}, None)
            tick = golem.run_golem(state, {"threat_level": 95, "exertion": 90, "sexual_arousal": signal},
                                   realms, {})
            regions = tick["psychosomatic_snapshot"]["autonomic_state"]["somatic_map"]
            self.assertTrue({"heart", "diaphragm"} <= regions.keys())
            self.assertTrue({"pelvis", "penis", "nipple", "perineum"}.isdisjoint(regions))

    def test_local_observations_override_one_sensation_for_one_event(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"age": 30, "canon_adult": True, "biological_sex": "female"}, None)
        tick = golem.run_golem(state, {"sexual_arousal": 90, "elapsed_ms": 0, "somatic_map": {
            "clitoris": {"fullness": 0, "pressure": 8}, "left_areola": {"tenderness": 12}
        }}, realms, {})
        regions = tick["psychosomatic_snapshot"]["autonomic_state"]["somatic_map"]
        self.assertEqual(regions["clitoris"], {"pressure": 8})
        self.assertEqual(regions["left_areola"], {"tenderness": 12})
        later = golem.run_golem(state, {"elapsed_ms": 0}, realms, tick["next_history"])
        regions = later["psychosomatic_snapshot"]["autonomic_state"]["somatic_map"]
        self.assertGreater(regions["clitoris"]["fullness"], 0)
        self.assertNotIn("left_areola", regions)

    def test_alarm_recovery_uses_profile_and_sexual_response_still_requires_adult_gate(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        alarms = []
        for sex in ("female", "male"):
            for age, confirmed in ((16, True), (32, False), (32, True)):
                state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed,
                                              "biological_sex": sex}, None)
                stressed = golem.run_golem(state, {"elapsed_minutes": 15, "threat_level": 70,
                                                   "appraisal": {"attraction": 90}}, realms, {})
                body = stressed["psychosomatic_snapshot"]["autonomic_state"]
                self.assertEqual(body["sexual_arousal"] > 0, age >= 18 and confirmed)
                if age >= 18 and confirmed:
                    after = golem.run_golem(state, {"elapsed_ms": 10000, "threat_level": 0},
                                            realms, stressed["next_history"])
                    alarms.append(after["next_history"]["release_state"]["alarm"])
        self.assertTrue(all(0 < alarm < 70 for alarm in alarms))
        self.assertNotAlmostEqual(*alarms)

    def test_sustained_load_and_recovery_use_elapsed_time(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state, _ = golem.overlay_log({"age": 32, "biological_sex": "female"}, None)
        def tick(minutes, threat, history):
            return golem.run_golem(state, {"elapsed_minutes": minutes, "threat_level": threat},
                                   realms, history)
        first = tick(0, 80, {})
        tense = tick(8, 80, first["next_history"])
        again = tick(0, 80, tense["next_history"])
        settled = tick(120, 0, again["next_history"])
        self.assertGreater(tense["next_history"]["cortisol"], first["next_history"]["cortisol"])
        self.assertEqual(tense["next_history"]["cortisol"], again["next_history"]["cortisol"])
        self.assertLess(settled["next_history"]["cortisol"], tense["next_history"]["cortisol"])
        self.assertEqual(again["next_history"]["sexual_arousal"], 0)
        first_half = tick(4, 80, first["next_history"])
        split = tick(4, 80, first_half["next_history"])
        self.assertAlmostEqual(split["next_history"]["cortisol"], tense["next_history"]["cortisol"])
        for feeling in ("vulnerability", "protectiveness"):
            response = golem.run_golem(state, {"elapsed_minutes": 0, "threat_level": 0,
                                              "emotions": {feeling: 90}}, realms, {})
            baseline = tick(0, 0, {})
            self.assertGreater(response["next_history"]["arousal"], baseline["next_history"]["arousal"])
            self.assertEqual(response["next_history"]["sexual_arousal"], 0)

    def test_expression_uses_target_and_telemetry_without_changing_the_body(self):
        state, _ = golem.overlay_log({"age": 30, "biological_sex": "male"}, None)
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        state["relational_baselines"] = {"friend": {"emotional_safety": 90}, "stranger": {"emotional_safety": 10}}
        snapshots = [
            golem.run_golem(state, {"elapsed_minutes": 0, "threat_level": 0, "caller_or_target": who,
                                    "appraisal": {"delight": 80}}, realms, {})["psychosomatic_snapshot"]
            for who in ("friend", "stranger")
        ]
        self.assertEqual(snapshots[0]["autonomic_state"], snapshots[1]["autonomic_state"])
        self.assertIn("within reach", golem_loop.expression_guidance(snapshots[0]))
        self.assertIn("preserving distance", golem_loop.expression_guidance(snapshots[1]))
        del snapshots[0]["autonomic_state"]["somatic_telemetry"]
        self.assertIsNone(golem_loop.expression_guidance(snapshots[0]))

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
        # Sleep debt accrues at the fidelity default of 2.5/hour awake.
        self.assertAlmostEqual(working["sleep_debt"], 20)
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
                result = golem_loop.wake_character(db, decide, compact=False, event={
                    "id": str(turn), "kind": "incoming",
                    "at": (start + timedelta(minutes=turn)).isoformat(),
                    "stimulus": {"activity": "sleeping" if turn < 10 else "awake",
                                 "exertion": 80 if 10 <= turn < 20 else 0},
                })
                if turn == 30:
                    response = result["events"][0]["body_response"]
                    self.assertGreater(response["after"]["arousal"], response["before"]["arousal"])
                    self.assertGreater(response["after"]["sexual_arousal"], 0)
                    self.assertNotIn("perineum", response["before"]["somatic_map"])
                    self.assertGreater(response["after"]["somatic_map"]["perineum"]["fullness"], 0)
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
            self.assertGreater(snapshots[-1]["sexual_arousal"], 0)
            self.assertTrue(snapshots[-1]["lingering_arousal"])

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
                later = golem.run_golem(state, {"elapsed_minutes": 12}, realms, tick["next_history"])
                self.assertAlmostEqual(later["next_history"]["sexual_arousal"], level / 2)

    def test_lingering_response_uses_scene_time_and_jarring_events_cut_carryover(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        card = {"age": 30, "canon_adult": True}
        state, _ = golem.overlay_log(card, None)

        def tick(minutes, history, **stimulus):
            return golem.run_golem(state, {"elapsed_minutes": minutes, **stimulus}, realms, history)

        initial = tick(0, {}, sexual_arousal=80)["next_history"]
        quiet = tick(5, initial, caller_or_target="another person")
        snapshot = quiet["psychosomatic_snapshot"]
        self.assertEqual(snapshot["autonomic_state"]["sexual_arousal"], 60)
        self.assertTrue(snapshot["autonomic_state"]["lingering_arousal"])
        self.assertEqual(snapshot["relational_vectors"]["another person"]["attraction_physical"], 0)
        self.assertIn("Carryover", golem_loop.expression_guidance(snapshot, "text"))
        self.assertIn("voice call", golem_loop.expression_guidance(snapshot, "voice"))
        self.assertEqual(tick(12, initial)["next_history"]["sexual_arousal"], 40)
        split = tick(7, quiet["next_history"])
        self.assertAlmostEqual(split["next_history"]["sexual_arousal"], 40)

        fresh_cue = tick(0, {}, appraisal={"attraction": 90})["next_history"]
        for shock in ({"threat_level": 95}, {"physical_pain": 95}, {"appraisal": {"disgust": 95}}):
            interrupted = tick(0, fresh_cue, **shock)
            carried = interrupted["next_history"]["sexual_excitation"]
            self.assertLessEqual(carried, 15)
            repeat = tick(0, interrupted["next_history"], **shock)
            self.assertEqual(repeat["next_history"]["sexual_excitation"], carried)
            self.assertLessEqual(tick(0, repeat["next_history"])["next_history"]["sexual_excitation"], carried)
            self.assertLessEqual(tick(2, repeat["next_history"])["next_history"]["sexual_excitation"], carried)

        state, _ = golem.overlay_log({**card, "physiology_calibration": {"sexual_arousal_half_life_minutes": 20}}, None)
        self.assertEqual(tick(20, initial)["next_history"]["sexual_arousal"], 40)
        with self.assertRaisesRegex(ValueError, "must be positive"):
            golem.overlay_log({"physiology_calibration": {"sexual_arousal_half_life_minutes": 0}}, None)

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
            woke = golem.run_golem(state, {"elapsed_minutes": 12, "activity": "awake"}, realms, history)
            self.assertEqual(woke["next_history"]["minutes_asleep"], 0)
            self.assertAlmostEqual(woke["next_history"]["sexual_arousal"], history["sexual_arousal"] / 2)

    def test_legacy_history_recovers_and_age_gate_discards_carried_response(self):
        realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        for age, confirmed, expected in [(30, True, 25), (17, True, 0), (30, False, 0)]:
            with self.subTest(age=age, confirmed=confirmed):
                state, _ = golem.overlay_log({"age": age, "canon_adult": confirmed, "sexual_drive_baseline": 0}, None)
                tick = golem.run_golem(state, {"elapsed_minutes": 12}, realms, {"sexual_arousal": 50})
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
