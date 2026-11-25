"""Deterministic physiology scales, calibration, and leaf somatic math.

Constants and helpers shared across the Golem pipeline: 0-100 clamp,
sub-additive summation, recovery/half-life helpers, the somatic profile and
genital response layout, and the card-tunable physiology_calibration values.
This module is computational only; it never touches stimulus history.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import math
from typing import Any


PLEASURE_HALF_LIFE_MINUTES = 2
PHYSICAL_PAIN_HALF_LIFE_MINUTES = 2
EMOTIONAL_DISTRESS_HALF_LIFE_MINUTES = 20
# Physiological rates are per simulated hour. Cards may override these under
# physiology_calibration; old cards use the shared, character-neutral defaults.
DEFAULT_PHYSIOLOGY_CALIBRATION = {
    "hunger_awake_per_hour": 4.0,
    "hunger_sleeping_per_hour": 2.0,
    "fatigue_awake_per_hour": 0.8,
    "fatigue_exertion_per_hour": 0.04,
    "fatigue_resting_recovery_per_hour": 2.0,
    "fatigue_sleep_recovery_per_hour": 5.0,
    "sleep_debt_awake_per_hour": 2.5,
    "sleep_debt_resting_per_hour": 0.5,
    "sleep_debt_sleep_recovery_per_hour": 12.0,
    "max_elapsed_hours_per_tick": 24.0,
    "sexual_arousal_half_life_minutes": 12.0,
    "orgasm_threshold": 85,
    "orgasm_recovery_minutes": 10.0,
    # Adult response fidelity defaults (see run_golem section 6 and SKILL.md).
    "excitation_transfer_gain": 0.35,
    "tactile_excitation_gain": 0.5,
    "resolution_half_life_divisor": 4.0,
    # Stress and endurance fidelity: plasma cortisol clears in roughly an hour,
    # moderate threat suppresses genital response well before it becomes acute,
    # and a full day without sleep is already exhausting.
    "cortisol_rise_half_life_minutes": 15.0,
    "cortisol_decay_half_life_minutes": 45.0,
    "shock_ceiling_multiplier": 1.5,
    "exhaustion_onset_load": 45.0,
}
# Half-lives are in seconds. Sensory loads can rise immediately.
EXPOSURE_RESPONSES = {
    "cold": ("Cold discomfort", 300, 0.25, False),
    "heat": ("Heat discomfort", 300, 0.25, False),
    "noise": ("Noise discomfort", 2, 0.20, True),
    "bright_light": ("Bright light discomfort", 5, 0.15, True),
}
APPRAISAL_SIGNALS = ("interest", "attraction", "disgust", "unease", "uncertainty",
                     "anticipation", "loss", "frustration", "delight", "relief")
APPRAISAL_HALF_LIFE_SECONDS = 10
ACTIVATION_RECOVERY_MINUTES = 1
SLEEP_PULSE_HALF_LIFE_MINUTES = 2


# Fictional adult reference points on independent 0–100 scales. Each axis
# can be authored separately, including for intersex or unspecified cards.
SOMATIC_BASELINES = {
    "estradiol": 50, "testosterone": 50, "resting_register": 50,
}
ADULT_SEX_PROFILES = {
    "female": {"estradiol": 65, "testosterone": 30, "resting_register": 62},
    "male": {"estradiol": 35, "testosterone": 70, "resting_register": 38},
    "intersex": {}, "unspecified": {},
}


# Extra sites for the adult arousal map. Cards can select any combination
# independently of endocrine calibration. Empty means shared sites only.
GENITAL_RESPONSE_SITES = {
    "clitoris": ("fullness", 0, 0.9), "labia": ("warmth", 10, 0.7),
    "vagina": ("fullness", 20, 0.55), "penis": ("fullness", 0, 0.9),
    "scrotum": ("tension", 20, 0.5),
}
DEFAULT_AROUSAL_REGIONS = {
    "female": ("clitoris", "labia", "vagina"), "male": ("penis", "scrotum"),
    "intersex": (), "unspecified": (),
}


def biological_sex(card):
    sex = card.get("biological_sex", "unspecified")
    if sex is None:
        sex = "unspecified"
    if not isinstance(sex, str) or sex.strip().lower() not in ADULT_SEX_PROFILES:
        raise ValueError("biological_sex must be female, male, intersex, or unspecified")
    return sex.strip().lower()


def arousal_regions(card):
    sites = card.get("arousal_regions")
    if sites is None:
        return list(DEFAULT_AROUSAL_REGIONS[biological_sex(card)])
    if not isinstance(sites, list) or any(
        not isinstance(site, str) or site not in GENITAL_RESPONSE_SITES for site in sites
    ):
        raise ValueError(f"arousal_regions must be a list of sites from {', '.join(GENITAL_RESPONSE_SITES)}")
    return list(dict.fromkeys(sites))


def card_age(card):
    """Unknown or unparseable ages use the existing unknown-age default."""
    try:
        return int(card.get("age", 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def canon_adult(card):
    return card.get("canon_adult") is True and card_age(card) >= 18


def somatic_profile(card):
    sex = biological_sex(card)
    baselines = SOMATIC_BASELINES.copy()
    if card_age(card) >= 18:
        baselines.update(ADULT_SEX_PROFILES[sex])
    custom = card.get("somatic_baselines", {})
    if not isinstance(custom, dict) or custom.keys() - baselines.keys():
        raise ValueError("somatic_baselines accepts estradiol, testosterone, and resting_register")
    for key, value in custom.items():
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f"somatic_baselines.{key} must be an integer from 0 to 100")
    return {**baselines, **custom}


def somatic_telemetry(profile, arousal, stress_load, cortisol, exertion, fatigue, warmth):
    # All outputs are relative simulation indices. Register is relative to the
    # character's authored voice, perfusion describes peripheral circulation.
    effort = 0.55 * exertion + 0.25 * arousal + 0.2 * stress_load
    tension = clamp(0.45 * stress_load + 0.3 * arousal + 0.25 * exertion)
    return {
        "hrv": clamp(82 - 0.45 * arousal - 0.22 * cortisol - 0.12 * fatigue),
        "peripheral_perfusion": clamp(55 + 0.25 * warmth - 0.35 * stress_load),
        "muscle_tension": tension,
        "postural_bracing": clamp(0.55 * stress_load + 0.30 * tension),
        "vocal_register": clamp(profile["resting_register"] + 0.22 * tension - 0.08 * fatigue),
        "register_shift": clamp(50 + 0.22 * tension - 0.08 * fatigue),
        "energy_expenditure": clamp(effort),
    }


def sleep_excitation(minutes_asleep: float) -> float:
    """Approximate intermittent autonomic excitation during sustained adult sleep."""
    # Simulation defaults. Sample scene time so a long tick can span a peak.
    phase = minutes_asleep % 90
    rising = max(0.0, (phase - 55) / 20) if phase <= 75 else 0.0
    since_peak = (minutes_asleep - 75) % 90
    falling = 2 ** (-since_peak / SLEEP_PULSE_HALF_LIFE_MINUTES) if minutes_asleep >= 75 else 0.0
    return 24 * max(rising, falling)


def combine_levels(*levels):
    """Sub-additive summation of parallel 0-100 inputs.

    Real dual-control inputs (excitatory or inhibitory signals) summate:
    several moderate signals outweigh any single one, combined signals
    saturate instead of stacking linearly. A single input keeps its exact
    value, so single-channel behavior is unchanged.
    """
    retained = 1.0
    for level in levels:
        retained *= 1.0 - min(100.0, max(0.0, float(level))) / 100.0
    # Round away sub-ULP accumulator drift so repeat ticks stay idempotent.
    return round(100.0 * (1.0 - retained), 9)


def clamp(val: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(val))))


def physiology_calibration(card: dict[str, Any]) -> dict[str, float]:
    configured = card.get("physiology_calibration") or {}
    if not isinstance(configured, dict) or set(configured) - DEFAULT_PHYSIOLOGY_CALIBRATION.keys():
        raise ValueError("physiology_calibration must contain only documented rate keys")
    values = {**DEFAULT_PHYSIOLOGY_CALIBRATION, **configured}
    for key, value in values.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"physiology_calibration.{key} must be a finite nonnegative number")
    for key in ("max_elapsed_hours_per_tick", "sexual_arousal_half_life_minutes", "orgasm_recovery_minutes",
                "resolution_half_life_divisor", "cortisol_rise_half_life_minutes",
                "cortisol_decay_half_life_minutes"):
        if values[key] <= 0:
            raise ValueError(f"physiology_calibration.{key} must be positive")
    if values["resolution_half_life_divisor"] < 1:
        raise ValueError("physiology_calibration.resolution_half_life_divisor must be at least 1")
    if values["cortisol_decay_half_life_minutes"] < values["cortisol_rise_half_life_minutes"]:
        raise ValueError("physiology_calibration.cortisol_decay_half_life_minutes must be at "
                         "least cortisol_rise_half_life_minutes")
    if values["shock_ceiling_multiplier"] <= 0 or values["shock_ceiling_multiplier"] > 10:
        raise ValueError("physiology_calibration.shock_ceiling_multiplier must be between 0 and 10")
    if not 0 <= values["exhaustion_onset_load"] <= 100:
        raise ValueError("physiology_calibration.exhaustion_onset_load must be between 0 and 100")
    for key in ("excitation_transfer_gain", "tactile_excitation_gain"):
        if values[key] > 1:
            raise ValueError(f"physiology_calibration.{key} must be between 0 and 1")
    if not 1 <= values["orgasm_threshold"] <= 100:
        raise ValueError("physiology_calibration.orgasm_threshold must be between 1 and 100")
    return {key: float(value) for key, value in values.items()}


def felt_pleasure(stimulus, history, key, remaining):
    """A current observation replaces the carried level, including an explicit zero."""
    if key in stimulus:
        value = stimulus[key]
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f"{key} must be an integer from 0 to 100")
        return value
    return history.get(key, 0) * remaining


def recover_distress(
    previous: float, baseline: int, current_stimulus: int, elapsed_minutes: float, half_life_minutes: float
) -> float:
    remaining = 2 ** (-elapsed_minutes / half_life_minutes)
    residual = baseline + (previous - baseline) * remaining
    return max(baseline, residual, current_stimulus)

