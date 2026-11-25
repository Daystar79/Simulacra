"""Builds the affective impulse, the release/pressure integration,
salient emotions, and validated willingness/urge signals.

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


from golem_physiology import APPRAISAL_HALF_LIFE_SECONDS, clamp




def stage_affect(t):
    # 2. Affective impulse
    t.emotional_intensity = clamp(25 + int(0.5 * t.stress) + int(0.3 * t.arousal))
    if t.cognitive_regime == "reactive":
        t.primary_emotion, t.secondary_emotion = "guarded_alert", "tension"
        t.impulse = t.involuntary_response
    elif t.threat >= 35 or t.latent_hit_bonus >= 15:
        t.primary_emotion, t.secondary_emotion = "cool_amusement", "guarded_recognition"
        t.impulse = "reframe_and_deflect"
    else:
        t.primary_emotion, t.secondary_emotion = "warm_amusement", "poised_curiosity"
        t.impulse = "lean_in_and_steer"

    # Relative activation, with separate body and appraisal inputs.
    # These are simulation scales rather than measured hormone concentrations.
    t.release = {
        "alarm": max(t.physical_load, t.threat, t.unease),
        "reward": max(t.appraisal_effects["delight"], t.interest * 0.5),
        "settling": t.appraisal_effects["relief"],
    }
    t.prior_release = t.history.get("release_state", {})
    # Sustain an already appraised alarm under prolonged endocrine load.
    # This changes its recovery curve without assigning a new feeling.
    t.alarm_half_life = APPRAISAL_HALF_LIFE_SECONDS * t.recovery_scale * (1 + max(0, t.cortisol - 15) / 100)
    t.alarm_remaining = 2 ** (-t.elapsed_ms / (1000 * t.alarm_half_life))
    for t.key, t.value in t.release.items():
        t.decay = t.alarm_remaining if t.key == "alarm" else t.remaining_appraisal
        t.release[t.key] = min(100, max(t.value, t.prior_release.get(t.key, 0) * t.decay))
    t.emotional_pressures = {
        "fear": t.release["alarm"], "joy": t.release["reward"], "relief": t.release["settling"],
        "sadness": t.appraisal_effects["loss"], "anger": t.appraisal_effects["frustration"],
        "anticipation": t.appraisal_effects["anticipation"], "disgust": t.disgust,
    }
    t.emotional_pressures.update(interest=t.interest, unease=t.unease, uncertainty=t.uncertainty)
    for t.name, t.intensity in t.felt.items():
        t.emotional_pressures[t.name] = max(t.emotional_pressures.get(t.name, 0), t.intensity)
    t.emotions = {t.name: clamp(t.value) for t.name, t.value in t.emotional_pressures.items() if clamp(t.value)}
    t.salient = sorted((t.name for t.name in t.emotional_pressures if t.emotional_pressures[t.name] >= 40),
                     key=t.emotional_pressures.get, reverse=True)
    if t.salient:
        if t.cognitive_regime == "reactive":
            t.secondary_emotion = t.salient[0]
        else:
            t.primary_emotion = t.salient[0]
            if len(t.salient) > 1:
                t.secondary_emotion = t.salient[1]
        t.emotional_intensity = max(t.emotional_intensity, clamp(t.emotional_pressures[t.salient[0]]))

    for t.key in ("willingness_to_pursue", "willingness_to_be_seen"):
        if t.key in t.stimulus and (type(t.stimulus[t.key]) is not int or not 0 <= t.stimulus[t.key] <= 100):
            raise ValueError(f"{t.key} must be an integer from 0 to 100")
    t.pursuit = t.stimulus.get("willingness_to_pursue", max(t.interest, t.release["reward"], t.hunger * 0.5))
    t.urge = t.stimulus.get("urge")
    if t.urge is not None:
        if (not isinstance(t.urge, dict) or not isinstance(t.urge.get("action"), str)
                or not t.urge["action"].strip() or type(t.urge.get("strength")) is not int
                or not 0 <= t.urge["strength"] <= 100):
            raise ValueError("urge requires an action and an integer strength from 0 to 100")
        if t.cognitive_regime != "reactive" and t.urge["strength"]:
            t.impulse = t.urge["action"].strip()
