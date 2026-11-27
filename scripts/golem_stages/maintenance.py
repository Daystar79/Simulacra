"""Advances calibration-gated body maintenance: hunger, sensory
exposures, pleasure carryover, post-peak recovery state, fatigue,
sleep debt, and exhaustion.

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

import math

from golem_physiology import DEFAULT_PHYSIOLOGY_CALIBRATION, EXPOSURE_RESPONSES, PLEASURE_HALF_LIFE_MINUTES, SOMATIC_BASELINES, canon_adult, clamp, felt_pleasure




def stage_maintenance(t):
    t.calibration = {**DEFAULT_PHYSIOLOGY_CALIBRATION, **t.state.get("physiology_calibration", {})}
    t.activity = t.stimulus.get("activity", t.history.get("activity", "awake"))
    if t.activity not in ("awake", "resting", "sleeping"):
        raise ValueError("Activity must be awake, resting, or sleeping")
    t.minutes_asleep = 0.0
    if t.activity == "sleeping":
        # A timestamped transition starts sleep now. Explicit durations describe
        # the supplied activity over the whole interval.
        entering = "event_at" in t.stimulus and t.history.get("activity") != "sleeping"
        if not entering:
            t.minutes_asleep = t.history.get("minutes_asleep", 0) + t.elapsed_minutes
    t.elapsed_hours = min(t.elapsed_minutes / 60, float(t.calibration["max_elapsed_hours_per_tick"]))
    t.hunger_rate = t.calibration["hunger_sleeping_per_hour"] if t.activity == "sleeping" else t.calibration["hunger_awake_per_hour"]
    t.accumulated_hunger = min(100.0, t.history.get("hunger", 0) + t.hunger_rate * t.elapsed_hours)
    t.food_intake = clamp(t.stimulus.get("food_intake", 0))
    t.hunger_level = max(0.0, t.accumulated_hunger - t.food_intake)
    t.hunger = clamp(t.hunger_level)

    t.exposure_history = {}
    t.exposure_state = {}
    t.exposure_feels = []
    t.exposure_load = 0.0
    for t.factor, (t.label, t.half_life_seconds, t.stress_weight, t.immediate_onset) in EXPOSURE_RESPONSES.items():
        t.exposure_key = f"{t.factor}_exposure"
        t.discomfort_key = f"{t.factor}_discomfort"
        t.exposure = clamp(t.stimulus.get(t.exposure_key, t.history.get(t.exposure_key, 0)))
        t.previous = t.history.get(t.discomfort_key, 0)
        t.remaining = 2 ** (-t.elapsed_ms / (1_000 * t.half_life_seconds))
        t.level = t.exposure + (t.previous - t.exposure) * t.remaining
        if t.immediate_onset:
            t.level = max(t.exposure, t.level)
        t.discomfort = clamp(t.level)
        t.exposure_history.update({t.exposure_key: t.exposure, t.discomfort_key: t.level})
        t.exposure_state.update({t.exposure_key: t.exposure, t.discomfort_key: t.discomfort})
        t.exposure_load += t.stress_weight * t.level
        if t.discomfort:
            t.exposure_feels.append(f"{t.label}: {t.discomfort}/100.")

    t.response_time_ms = int(t.stimulus.get("response_time_ms", 2000))
    t.time_pressure = t.stimulus.get(
        "time_pressure",
        "split_second" if t.response_time_ms <= 800 else ("deliberate" if t.response_time_ms >= 2500 else "normal"),
    )

    t.profile = t.state.get("somatic_profile", SOMATIC_BASELINES)
    # Modest, bounded tuning of response gain and recovery. Appraisal supplies
    # the meaning of the event independently of the endocrine profile.
    t.adrenergic_gain = 1 + (t.profile["testosterone"] - t.profile["estradiol"]) / 500
    t.recovery_scale = 1 + (t.profile["estradiol"] - 50) / 250
    t.adult_eligible = canon_adult(t.state)
    t.remaining_pleasure = 2 ** (-t.elapsed_minutes / PLEASURE_HALF_LIFE_MINUTES)
    t.physical_pleasure = felt_pleasure(t.stimulus, t.history, "physical_pleasure", t.remaining_pleasure)
    t.sexual_pleasure = (felt_pleasure(t.stimulus, t.history, "sexual_pleasure", t.remaining_pleasure)
                       if t.adult_eligible else 0)
    t.orgasm = False
    t.recovery_minutes_left = t.recovery_fraction = t.peak_pulse = 0.0
    t.recovery_duration = t.history.get("orgasm_recovery_duration", 0)
    if t.adult_eligible:
        # Apply individual calibration to the profile's simulated recovery time.
        t.recovery_minutes_left = max(0.0, t.history.get("orgasm_recovery_minutes_left", 0) - t.elapsed_minutes)
        t.threshold = t.calibration["orgasm_threshold"]
        t.orgasm = (t.recovery_minutes_left == 0 and "sexual_pleasure" in t.stimulus
                  and t.history.get("sexual_pleasure", 0) < t.threshold <= t.sexual_pleasure)
        if t.orgasm:
            t.recovery_duration = t.calibration["orgasm_recovery_minutes"] * (
                1 + (t.profile["testosterone"] - t.profile["estradiol"]) / 125
            )
            if not math.isfinite(t.recovery_duration) or t.recovery_duration <= 0:
                raise ValueError("Effective orgasm recovery interval must be finite and positive")
            t.recovery_minutes_left = t.recovery_duration
            t.rules.append("ORGASM_THRESHOLD_CROSSED")
        if t.recovery_minutes_left > 0:
            t.recovery_fraction = t.recovery_minutes_left / t.recovery_duration
            t.peak_pulse = max(0.0, 1 - (t.recovery_duration - t.recovery_minutes_left) / 0.5)
    t.exertion = 0
    if t.activity == "sleeping":
        t.fatigue_rate = -float(t.calibration["fatigue_sleep_recovery_per_hour"])
        t.sleep_debt_rate = -float(t.calibration["sleep_debt_sleep_recovery_per_hour"])
    elif t.activity == "resting":
        t.fatigue_rate = -float(t.calibration["fatigue_resting_recovery_per_hour"])
        t.sleep_debt_rate = float(t.calibration["sleep_debt_resting_per_hour"])
    else:
        t.exertion = clamp(t.stimulus.get("exertion", t.history.get("exertion", 0)))
        t.fatigue_rate = float(t.calibration["fatigue_awake_per_hour"]) + float(t.calibration["fatigue_exertion_per_hour"]) * t.exertion * t.adrenergic_gain
        t.sleep_debt_rate = float(t.calibration["sleep_debt_awake_per_hour"])

    t.previous_fatigue = t.history.get("last_fatigue", 15)
    t.previous_sleep_debt = t.history.get("sleep_debt", 0)
    t.fatigue_level = min(100.0, max(0.0, t.previous_fatigue + t.fatigue_rate * t.elapsed_hours))
    t.sleep_debt_level = min(100.0, max(0.0, t.previous_sleep_debt + t.sleep_debt_rate * t.elapsed_hours))
    if t.orgasm:
        # Post-coital somnolence scales with the intensity of the peak.
        t.fatigue_level = min(100.0, t.fatigue_level + round(
            (4 + 8 * clamp(t.sexual_pleasure) / 100) * t.adrenergic_gain))
    t.fatigue = clamp(t.fatigue_level)
    t.sleep_debt = clamp(t.sleep_debt_level)
    t.fatigue_load = max(t.fatigue_level, t.sleep_debt_level)
    # Exhaustion sets in well before collapse: a full day without sleep is
    # already exhausting, so the onset is card-tunable at a lower load.
    t.exhaustion = clamp((t.fatigue_load - t.calibration["exhaustion_onset_load"]) * 2.5)
    t.recent_cues: list[str] = list(t.history.get("recent_cues", []))
