"""Adult physiology fidelity: summation, transfer, tactile input, resolution."""

import unittest

import yaml

from scripts import golem


def adult(**card):
    state, _ = golem.overlay_log({"age": 32, "canon_adult": True, **card}, None)
    return state


class TestPhysiologyFidelity(unittest.TestCase):
    def setUp(self):
        self.realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())

    def tick(self, history=None, minutes=0, **stimulus):
        stimulus.setdefault("elapsed_ms", 0)
        if minutes:
            stimulus.pop("elapsed_ms")
            stimulus["elapsed_minutes"] = minutes
        result = golem.run_golem(adult(), stimulus, self.realms, history or {})
        return result["next_history"], result["psychosomatic_snapshot"]["autonomic_state"]

    def test_inhibitory_inputs_summate_sub_additively(self):
        # The combiner itself keeps a single input exact and saturates pairs.
        self.assertEqual(golem.combine_levels(50), 50)
        self.assertEqual(golem.combine_levels(40, 40), 64)
        self.assertLess(golem.combine_levels(60, 60), 92)
        # In the body, moderate parallel inhibitors add up instead of the
        # strongest one max-gating the rest away.
        disgust, _ = self.tick(appraisal={"disgust": 40})
        unease, _ = self.tick(appraisal={"unease": 40})
        both, _ = self.tick(appraisal={"disgust": 40, "unease": 40})
        self.assertGreater(both["sexual_inhibition"], max(disgust["sexual_inhibition"],
                                                          unease["sexual_inhibition"]))

    def test_excitation_transfer_only_in_appetitive_context(self):
        # Any arousal from strenuous exertion stays purely non-sexual when no
        # attraction appraisal is present.
        plain, _ = self.tick(exertion=90)
        self.assertEqual(plain["sexual_excitation"], 0)
        # The same exertion amplifies the response to an attraction cue.
        drawn, _ = self.tick(exertion=90, appraisal={"attraction": 60})
        calm, _ = self.tick(appraisal={"attraction": 60})
        self.assertGreater(drawn["sexual_excitation"], calm["sexual_excitation"])

    def test_tactile_pleasure_excites_without_attraction(self):
        # Direct stimulation produces a genital response on its own; half the
        # reported pleasure by default.
        history, body = self.tick(sexual_pleasure=60)
        self.assertEqual(history["sexual_excitation"], 30)
        self.assertGreater(body["sexual_arousal"], 0)
        # An explicit host-supplied arousal reading is authoritative and is
        # not inflated on top of the tactile estimate.
        history, _ = self.tick(sexual_pleasure=60, sexual_arousal=60)
        self.assertEqual(history["sexual_excitation"], 60)

    def test_resolution_phase_clears_excitation_faster(self):
        peak_state = adult()
        settling = {"sexual_excitation": 80, "sexual_drive": 50}
        recovering = dict(settling, orgasm_recovery_minutes_left=8,
                          orgasm_recovery_duration=10)
        for history in (settling, recovering):
            result = golem.run_golem(peak_state, {"elapsed_minutes": 6},
                                     self.realms, history)
            history.update(result["next_history"])
        self.assertAlmostEqual(settling["sexual_excitation"], 80 * 2 ** -0.5)
        self.assertLess(recovering["sexual_excitation"], settling["sexual_excitation"])

    def test_sleep_excitation_scales_with_drive(self):
        low, _ = self.tick({"sexual_drive": 10, "minutes_asleep": 75},
                           activity="sleeping", minutes=75)
        high, _ = self.tick({"sexual_drive": 90, "minutes_asleep": 75},
                            activity="sleeping", minutes=75)
        self.assertGreater(high["sexual_excitation"], 0)
        self.assertGreater(high["sexual_excitation"], low["sexual_excitation"])

    def test_post_coital_somnolence_scales_with_peak_intensity(self):
        before, before_body = self.tick(sexual_pleasure=0)
        _, gentle = self.tick(before, sexual_pleasure=85)
        _, intense = self.tick(before, sexual_pleasure=100)
        self.assertTrue(gentle["orgasm"] and intense["orgasm"])
        self.assertGreater(intense["fatigue"], gentle["fatigue"])
        self.assertGreaterEqual(intense["fatigue"] - before_body["fatigue"], 11)


if __name__ == "__main__":
    unittest.main()


class TestStressAndEnduranceFidelity(unittest.TestCase):
    def setUp(self):
        self.realms = yaml.safe_load(golem.REALM_DATA_PATH.read_text())
        self.state, _ = golem.overlay_log({"age": 32, "canon_adult": True}, None)

    def history(self, **stimulus):
        result = golem.run_golem(self.state, stimulus, self.realms, stimulus.pop("history", {}) or {})
        return result["next_history"], result["psychosomatic_snapshot"]["autonomic_state"]

    def test_cortisol_clears_over_roughly_an_hour(self):
        # A strong stressor raises cortisol well above baseline.
        crisis = {"elapsed_minutes": 20, "threat_level": 80}
        peak, _ = self.history(**dict(crisis))
        self.assertGreater(peak["cortisol"], 35)
        # From an identical raised level, an hour of calm closes about three
        # quarters of the gap to the calm target and another 45 minutes
        # halves it again: a 45-minute decay half-life, not the pre-fidelity
        # 20-minute constant.
        calm_45 = golem.run_golem(self.state, {"elapsed_minutes": 45},
                                  self.realms, {"cortisol": 60.0})["next_history"]
        calm_90 = golem.run_golem(self.state, {"elapsed_minutes": 90},
                                  self.realms, {"cortisol": 60.0})["next_history"]
        self.assertLess(calm_45["cortisol"], 50)
        self.assertLess(calm_90["cortisol"], calm_45["cortisol"])
        # Each 45 calm minutes halves the remaining distance to the calm
        # target: 2 ** (elapsed / half_life) with half_life 45.
        self.assertAlmostEqual(3 * (60 - calm_45["cortisol"]),
                               2 * (60 - calm_90["cortisol"]), delta=3)
        card = dict(self.state)
        card["physiology_calibration"] = {"cortisol_decay_half_life_minutes": 0}
        self.assertRaises(ValueError, golem.overlay_log, card, None)

    def test_a_full_day_without_sleep_is_exhausting(self):
        clock = golem.run_golem(self.state, {"elapsed_minutes": 24 * 60}, self.realms, {})
        day = clock["next_history"]
        body = clock["psychosomatic_snapshot"]["autonomic_state"]
        self.assertGreaterEqual(day["sleep_debt"], 60)
        # Exhaustion registers well before collapse: a 24-hour stretch is
        # already substantially impairing.
        self.assertGreater(body["exhaustion"], 30)
        # A normal active day leaves exhaustion alone.
        usual = golem.run_golem(self.state, {"elapsed_minutes": 16 * 60}, self.realms, {})
        self.assertEqual(usual["psychosomatic_snapshot"]["autonomic_state"]["exhaustion"], 0)

    def test_moderate_threat_clips_excitation_below_ceiling(self):
        resting = golem.run_golem(self.state, {"elapsed_ms": 0, "sexual_arousal": 80},
                                  self.realms, {})
        self.assertEqual(resting["psychosomatic_snapshot"]["autonomic_state"]["sexual_arousal"], 80)
        # The same carried arousal under a moderate threat (50) is clipped by
        # the shock ceiling (default multiplier 1.5) instead of passing 100.
        wary = golem.run_golem(self.state, {"elapsed_ms": 0, "threat_level": 50},
                               self.realms, resting["next_history"])
        response = wary["psychosomatic_snapshot"]["autonomic_state"]
        carried = wary["next_history"]["sexual_excitation"]
        self.assertLess(carried, 80)
        self.assertLessEqual(carried, 1.5 * (100 - 50))
        self.assertLess(response["sexual_arousal"], resting["psychosomatic_snapshot"]["autonomic_state"]["sexual_arousal"])
