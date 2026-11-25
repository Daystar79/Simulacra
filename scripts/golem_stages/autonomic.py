"""Computes the autonomic and polyvagal core: realm hits, loads,
activation, stress, cortisol dynamics, and the dual-circuit regime.

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


from golem_physiology import ACTIVATION_RECOVERY_MINUTES, clamp




def stage_autonomic(t):
    # 1. Autonomic & Polyvagal calculation (CognitivePipeline §4.1)
    t.latent_hit_bonus = 0
    for t.rk, t.weight in t.state["latent_weights"].items():
        t.clean_rk = str(t.rk).replace("Realm_", "")
        if t.clean_rk in t.realm_hits:
            t.latent_hit_bonus += int(t.realm_hits[t.clean_rk] * (t.weight / 100.0))
            t.rules.append(f"LATENT_REALM_HIT:{t.clean_rk}")

    t.physical_load = t.physical_pain_level * (150 - t.physical_pain_tolerance) / 100
    t.emotional_load = t.emotional_distress_level * (150 - t.emotional_distress_tolerance) / 100
    t.distress_load = t.physical_load + t.emotional_load
    t.appraisal_activation = 0.25 * t.interest + 0.25 * t.disgust + 0.20 * t.unease
    t.resting_activation = {"sleeping": 5, "resting": 15, "awake": 25}[t.activity]
    t.social_load = max(t.felt.get("vulnerability", 0), t.felt.get("protectiveness", 0))
    t.phasic_load = (0.4 * t.threat + 0.3 * t.social_p + 0.25 * t.latent_hit_bonus
                   + 0.35 * t.exertion + t.exposure_load + 0.5 * t.distress_load
                   + t.appraisal_activation + 0.2 * t.social_load)
    t.activation_target = clamp(t.resting_activation + t.adrenergic_gain * t.phasic_load)
    t.prior_activation = t.history.get("arousal", t.activation_target)
    t.activation = t.activation_target + max(0, t.prior_activation - t.activation_target) * 2 ** (
        -t.elapsed_minutes / (ACTIVATION_RECOVERY_MINUTES * t.recovery_scale)
    )
    t.activation = max(t.activation, 70 * t.peak_pulse)
    t.arousal = clamp(t.activation)
    t.baseline_stress = (
        10 + int(0.55 * t.threat) + int(0.2 * t.social_p) + int(0.35 * t.latent_hit_bonus)
        - int(0.15 * t.state["flexibility"])
    )
    t.exhaustion_load = max(0, t.fatigue_load - 40) * 0.2
    t.appraisal_stress = 0.40 * t.disgust + 0.35 * t.unease + 0.15 * t.uncertainty
    t.stress = clamp(
        t.baseline_stress + t.distress_load + 0.15 * t.hunger_level + t.exposure_load + t.exhaustion_load + t.appraisal_stress
    )
    if t.physical_pain == 100:
        t.activation = 100
        t.arousal = t.stress = 100
        t.rules.append("ACUTE_PHYSICAL_PAIN_OVERLOAD")
    # Integrate sustained load separately from the immediate autonomic surge.
    # Fractional history survives short ticks. Same-instant appraisals cost no time.
    t.cortisol_target = clamp(15 + t.adrenergic_gain * 0.75 * t.stress)
    t.previous_cortisol = t.history.get("cortisol", 15.0)
    # Plasma cortisol peaks tens of minutes after a stressor and clears over
    # roughly an hour, so sustained stress outlasts the immediate surge.
    t.half_life = (t.calibration["cortisol_rise_half_life_minutes"] if t.cortisol_target > t.previous_cortisol
                 else t.calibration["cortisol_decay_half_life_minutes"]) * t.recovery_scale
    t.cortisol = t.cortisol_target + (t.previous_cortisol - t.cortisol_target) * 2 ** (-t.elapsed_minutes / t.half_life)
    t.autonomic_surge = t.stress >= 75 or t.threat >= 80

    t.involuntary_response = "none"
    if t.stress >= 70 or t.arousal >= 75 or t.autonomic_surge or (t.time_pressure == "split_second" and t.stress >= 55):
        t.cognitive_regime = "reactive"
        t.polyvagal_mode = "dorsal_freeze" if t.fatigue_load >= 75 else "sympathetic_mobilized"
        t.involuntary_response = "freeze" if t.polyvagal_mode == "dorsal_freeze" else "brace"
        t.rules.append("DUAL_CIRCUIT_REACTIVE_BYPASS")
        if t.time_pressure == "split_second" and t.stress < 70 and t.arousal < 75 and not t.autonomic_surge:
            t.rules.append("SPLIT_SECOND_REACTIVE_TIP")
    else:
        t.cognitive_regime = "deliberative"
        t.polyvagal_mode = "ventral_grounded"
        t.rules.append("DUAL_CIRCUIT_DELIBERATIVE")
