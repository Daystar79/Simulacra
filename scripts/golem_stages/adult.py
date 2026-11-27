"""Runs adult eligibility and the dual-control adult physiology, and
reads the relational bond for the present target.

Stage functions operate on the shared per-tick context `t` (a SimpleNamespace
created fresh by golem.run_golem each call) and follow the original
run_golem stage order exactly.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


from golem_physiology import clamp, combine_levels, sleep_excitation




def stage_adult(t):
    # 6. Adult eligibility and background state (CognitivePipeline §2)
    t.drive_level = 0.0
    t.sexual_response = 0.0
    t.excitation = t.inhibition = 0.0
    t.sexual_arousal = 0
    t.lingering_arousal = False
    if t.adult_eligible:
        t.baseline_drive = t.state.get("sexual_drive_baseline", 50)
        t.previous_drive = t.history.get("sexual_drive", t.baseline_drive)
        t.bodily_load = max(t.physical_pain_level, t.emotional_distress_level, t.fatigue_load)
        t.target_drive = t.baseline_drive * (1 - t.bodily_load / 200)
        # Keep the fractional state in history so short ticks can accumulate.
        t.remaining = 2 ** (-t.elapsed_minutes / 30)
        t.drive_level = t.target_drive + (t.previous_drive - t.target_drive) * t.remaining
        if t.recovery_fraction:
            t.drive_level = min(t.drive_level, t.baseline_drive * (1 - 0.6 * t.recovery_fraction))
        # The body already carries earlier cues. Reusing the decaying appraisal
        # here could recreate excitation immediately after a shock cut it.
        t.new_attraction = t.appraisal.get("attraction", 0)
        t.cue_excitation = min(100, t.new_attraction * (0.5 + 0.5 * t.drive_level / 100) * t.adrenergic_gain)
        # Older histories saved only the resulting response.
        t.prior_excitation = t.history.get("sexual_excitation", t.history.get("sexual_arousal", 0))
        t.half_life = t.calibration["sexual_arousal_half_life_minutes"] * t.recovery_scale
        # The resolution phase clears excitation several times faster than it rose.
        # the divisor eases back to 1 as recovery completes.
        if t.recovery_fraction:
            t.half_life /= 1 + (t.calibration["resolution_half_life_divisor"] - 1) * t.recovery_fraction
        t.recovery = 2 ** (-t.elapsed_minutes / t.half_life)
        t.residual = t.prior_excitation * t.recovery
        if "sexual_arousal" in t.stimulus:
            t.residual = clamp(t.stimulus["sexual_arousal"])
        # Sleep-related excitation tracks the resting drive, not a fixed amplitude.
        t.sleep_pulse = sleep_excitation(t.minutes_asleep) * (0.5 + t.drive_level / 200)
        # A strong shock can interrupt the carried response even at zero elapsed
        # time. A ceiling is idempotent when the host re-appraises that instant.
        t.shock = max(t.threat, t.physical_pain, t.disgust)
        # Moderate threat already suppresses genital response; the ceiling clips
        # proportionally to the shock level instead of only biting when acute.
        t.excitation_ceiling = min(100, t.calibration["shock_ceiling_multiplier"] * (100 - t.shock))
        # Direct tactile/genital stimulation raises excitation without requiring
        # an interpersonal attraction appraisal. An explicit host-supplied
        # sexual_arousal reading is already the measured body level, so the
        # tactile path only fills in when the host does not supply one.
        t.tactile_excitation = (0.0 if "sexual_arousal" in t.stimulus
                              else t.calibration["tactile_excitation_gain"] * t.sexual_pleasure)
        # Residual sympathetic activation (exertion, alarm, excitement) transfers
        # into excitation only in an appetitive context: the character is drawn
        # to who or what is present. Interest alone stays cognitive; threat
        # remains purely inhibitory through the shock ceiling.
        t.positive_appraisal = min(1.0, t.appraisal.get("attraction", 0) / 60)
        t.transfer_excitation = (t.calibration["excitation_transfer_gain"]
                               * max(0.0, t.arousal - 40) * t.positive_appraisal)
        # Parallel dual-control inputs summate sub-additively rather than being
        # max-gated: moderate signals add up, combined signals saturate.
        t.excitation = min(t.excitation_ceiling, combine_levels(
            t.residual, t.cue_excitation, t.sleep_pulse, t.tactile_excitation, t.transfer_excitation))
        t.inhibition = min(100, combine_levels(
            t.disgust, t.unease, 0.75 * t.physical_load, 0.75 * t.emotional_load,
            t.stress - 25, 0.5 * t.exhaustion, 70 * t.recovery_fraction * (1 - t.peak_pulse)))
        t.sexual_response = t.excitation * (1 - t.inhibition / 100)
        t.sexual_arousal = clamp(t.sexual_response)
        t.lingering_arousal = (t.sexual_arousal > 0
                             and all(t.residual > t.source for t.source in
                                     (t.cue_excitation, t.sleep_pulse, t.tactile_excitation,
                                      t.transfer_excitation))
                             and "sexual_arousal" not in t.stimulus and not t.new_attraction)
    else:
        t.appraisal_effects["attraction"] = 0
    # A bodily response can have no interpersonal target (sleep, memory, or touch).
    t.bond = t.state.get("relational_baselines", {}).get(t.target) or {}
    if not isinstance(t.bond, dict):
        t.bond = {}
    t.phys_attr = clamp(t.bond.get("attraction_physical", 0)) if t.adult_eligible else 0
    t.emot_attr = clamp(t.bond.get("attraction_emotional", 0))
    t.status_dynamic = t.bond.get("status_dynamic", "dominant")
    if t.status_dynamic not in ("dominant", "yielding", "equals", "deference"):
        t.status_dynamic = "dominant"
    t.momentum = t.bond.get("relational_momentum", "stable")
    if t.momentum not in ("building", "deepening", "stable", "eroding", "brittle", "suspended", "fractured"):
        t.momentum = "stable"
    t.rules.append(f"ADULT_GATE:{'ELIGIBLE' if t.adult_eligible else 'RESTRICTED'}")
