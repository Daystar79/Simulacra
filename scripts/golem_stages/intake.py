"""Validates the stimulus, advances appraisal decay and felt
emotions, and recovers pain and emotional distress into t.

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

from golem_physiology import APPRAISAL_HALF_LIFE_SECONDS, APPRAISAL_SIGNALS, EMOTIONAL_DISTRESS_HALF_LIFE_MINUTES, PHYSICAL_PAIN_HALF_LIFE_MINUTES, clamp, recover_distress

from golem_time import event_clock




def stage_intake(t):
    t.rules: list[str] = []
    if t.history.get("character_id") not in (None, t.state["character_id"]):
        raise ValueError("Character ID mismatch in carried history")
    t.threat = clamp(t.stimulus.get("threat_level", 10))
    t.social_p = clamp(t.stimulus.get("social_pressure", 20))
    t.physical_pain_tolerance = t.state.get("physical_pain_tolerance", 50)
    t.emotional_distress_tolerance = t.state.get("emotional_distress_tolerance", 50)
    t.realm_hits = t.stimulus.get("realm_hits", {}) or {}
    t.context = t.stimulus.get("context", "broadcast")
    t.target = t.stimulus.get("caller_or_target", "caller")
    t.event_label = t.stimulus.get("event_label", "tick_01")
    t.elapsed_ms, t.clock_state = event_clock(t.stimulus, t.history)
    if not math.isfinite(t.elapsed_ms):
        raise ValueError("Elapsed scene time must be finite")
    t.elapsed_ms = max(0.0, t.elapsed_ms)
    t.elapsed_minutes = t.elapsed_ms / 60_000
    t.appraisal = t.stimulus.get("appraisal", {})
    if not isinstance(t.appraisal, dict) or any(
        t.key not in APPRAISAL_SIGNALS or type(t.value) is not int or not 0 <= t.value <= 100
        for t.key, t.value in t.appraisal.items()
    ):
        raise ValueError("Appraisal must map known signals to integer scores from 0 to 100")
    t.prior_appraisal_effects = t.history.get("appraisal_effects", {})
    # These are immediate appraisals, not enduring relationship measures.
    # Durable attraction/attachment remains in relational_baselines.
    t.remaining_appraisal = 2 ** (-t.elapsed_ms / (1_000 * APPRAISAL_HALF_LIFE_SECONDS))
    t.appraisal_effects = {
        t.signal: max(t.appraisal.get(t.signal, 0), t.prior_appraisal_effects.get(t.signal, 0) * t.remaining_appraisal)
        for t.signal in APPRAISAL_SIGNALS
    }
    # The host can recognize feelings whose meaning depends on the character's interpretation.
    # Keep fractional carryover so that repeated short ticks equal one longer interval.
    t.felt = {
        t.name: t.intensity * t.remaining_appraisal
        for t.name, t.intensity in t.history.get("felt_emotions", {}).items()
        if t.intensity * t.remaining_appraisal >= 0.5
    }
    t.updates = t.stimulus.get("emotions", {})
    if not isinstance(t.updates, dict):
        raise ValueError("emotions must map names to intensity scores")
    for t.name, t.intensity in t.updates.items():
        if not isinstance(t.name, str) or not t.name.strip() or t.name != t.name.strip():
            raise ValueError("emotion names must be nonempty text without surrounding whitespace")
        if type(t.intensity) is not int or not 0 <= t.intensity <= 100:
            raise ValueError("emotion intensity must be an integer from 0 to 100")
        if t.intensity:
            t.felt[t.name] = t.intensity
        else:
            t.felt.pop(t.name, None)
    t.interest = t.appraisal_effects["interest"]
    t.attraction = t.appraisal_effects["attraction"]
    t.disgust = t.appraisal_effects["disgust"]
    t.unease = t.appraisal_effects["unease"]
    t.uncertainty = t.appraisal_effects["uncertainty"]
    t.visceral_revulsion = clamp(t.disgust)
    t.pain_baseline = t.state.get("physical_pain_baseline", 0)
    t.distress_baseline = t.state.get("emotional_distress_baseline", 0)
    t.physical_pain_level = recover_distress(
        t.history.get("physical_pain", t.pain_baseline),
        t.pain_baseline,
        clamp(t.stimulus.get("physical_pain", t.stimulus.get("pain", 0))),
        t.elapsed_minutes,
        PHYSICAL_PAIN_HALF_LIFE_MINUTES,
    )
    t.emotional_distress_level = recover_distress(
        t.history.get("emotional_distress", t.distress_baseline),
        t.distress_baseline,
        clamp(t.stimulus.get("emotional_distress", 0)),
        t.elapsed_minutes,
        EMOTIONAL_DISTRESS_HALF_LIFE_MINUTES,
    )
    t.physical_pain = clamp(t.physical_pain_level)
    t.emotional_distress = clamp(t.emotional_distress_level)
