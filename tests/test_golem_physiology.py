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
