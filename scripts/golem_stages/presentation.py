"""Builds body signal mapping, narrative feels, visceral truth,
and the schema-validated psychosomatic snapshot.

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

import re

from golem_physiology import clamp, somatic_telemetry

from golem_somatic import REGION_ZONE, arousal_sensations, somatic_map




def stage_presentation(t):
    # 7. Durable commit eligibility (CognitivePipeline §8)
    t.pressure_tier = "High" if t.stress >= 70 else ("Medium" if t.stress >= 45 else "Low")
    t.commit_eligible = t.pressure_tier in ("Medium", "High")
    t.rules.append(f"COMMIT_GATE:{'ELIGIBLE' if t.commit_eligible else 'EPHEMERAL_ONLY'}")

    t.mapped_body = somatic_map(t.stimulus, (
        ("stomach", "hunger", t.hunger), ("gut", "queasiness", t.visceral_revulsion),
        ("eye", "light discomfort", t.exposure_state["bright_light_discomfort"]),
        ("ear", "noise discomfort", t.exposure_state["noise_discomfort"]),
        ("skin", "cold discomfort", t.exposure_state["cold_discomfort"]),
        ("skin", "heat discomfort", t.exposure_state["heat_discomfort"]),
        ("whole_body", "fatigue", t.fatigue), ("whole_body", "pain", t.physical_pain),
        ("chest", "breathing effort", t.exertion),
        ("pelvic_floor", "involuntary contractions", clamp(85 * t.peak_pulse)),
        *arousal_sensations(t.arousal, t.sexual_arousal, t.state.get("arousal_regions", ())),
    ))
    for t.location in t.mapped_body:
        t.zone = REGION_ZONE.get(re.sub(r"^(left|right)_", "", t.location))
        if t.zone and t.zone not in t.zones:
            t.zones.append(t.zone)

    t.cue_text = "; ".join(t.somatic_cues)
    t.zone_text = ", ".join(t.zones)
    t.feels = f"{t.cue_text} ({t.zone_text})." if t.cue_text else f"Active zones: {t.zone_text}."
    if t.hunger:
        t.feels += f" Hunger: {t.hunger}/100."
    if t.fatigue:
        t.feels += f" Physical fatigue: {t.fatigue}/100."
    if t.sleep_debt:
        t.feels += f" Sleep debt: {t.sleep_debt}/100."
    if t.exhaustion:
        t.feels += f" Exhaustion: {t.exhaustion}/100."
    if t.exposure_feels:
        t.feels += " " + " ".join(t.exposure_feels)
    if t.visceral_revulsion >= 50:
        t.feels += " The stomach turns."
    if t.sexual_arousal:
        t.feels += f" Sexual arousal: {t.sexual_arousal}/100."
    if t.involuntary_response == "freeze":
        t.feels = f"The body freezes involuntarily. {t.feels}"
    elif t.involuntary_response == "brace":
        t.feels = f"The body braces involuntarily. {t.feels}"
    t.rationalization = f"I am addressing what is in front of me through {t.state['active_focus']}."
    if t.closed_account:
        t.visceral_truth = "Account stays closed; others' hesitation is read as leverage or weakness."
        t.rationalization = "I am simply naming what is obvious and keeping the room moving."
    elif t.bias_state == "DEFENSIVE_ACTIVE":
        t.visceral_truth = f"Pressure against {t.wound or 'personal boundaries'} registers as exposure or loss of footing."
    elif t.bias_state == "GENERATIVE_ACTIVE":
        t.visceral_truth = f"Anchored in {t.gift or 'the present moment'}; attention stays clear without forcing control."
    else:
        t.visceral_truth = f"Baseline {t.state['active_focus']} awareness; {t.wound or 'the defensive response'} stays unactivated."

    t.snapshot = {
        "character_id": t.state["character_id"],
        "timestamp_or_movement": t.event_label,
        "autonomic_state": {
            "endocrine_state": {"estradiol": t.profile["estradiol"], "testosterone": t.profile["testosterone"],
                                "cortisol": clamp(t.cortisol)},
            "somatic_telemetry": somatic_telemetry(
                t.profile, t.arousal, max(t.stress, t.cortisol - 15), t.cortisol, t.exertion, t.fatigue,
                max(t.sexual_arousal, t.release["reward"], t.exposure_state["heat_discomfort"]),
            ),
            "polyvagal_mode": t.polyvagal_mode,
            "cognitive_regime": t.cognitive_regime,
            "arousal": t.arousal,
            "sexual_drive": clamp(t.drive_level),
            "sexual_excitation": clamp(t.excitation),
            "sexual_inhibition": clamp(t.inhibition),
            "sexual_arousal": t.sexual_arousal,
            "lingering_arousal": t.lingering_arousal,
            "physical_pleasure": clamp(t.physical_pleasure),
            "sexual_pleasure": clamp(t.sexual_pleasure),
            "orgasm": t.orgasm,
            "orgasm_recovery": clamp(100 * t.recovery_fraction),
            "visceral_revulsion": t.visceral_revulsion,
            "stress": t.stress,
            "fatigue": t.fatigue,
            "sleep_debt": t.sleep_debt,
            "exhaustion": t.exhaustion,
            "activity": t.activity,
            "exertion": t.exertion,
            "hunger": t.hunger,
            **t.exposure_state,
            "physical_pain": t.physical_pain,
            "emotional_distress": t.emotional_distress,
            "physical_pain_tolerance": t.physical_pain_tolerance,
            "emotional_distress_tolerance": t.emotional_distress_tolerance,
            "primary_somatic_zones": t.zones,
            "somatic_map": t.mapped_body,
            "autonomic_surge": t.autonomic_surge,
            "involuntary_response": t.involuntary_response,
        },
        "affective_state": {
            "initiative": clamp(t.pursuit - t.exhaustion * 0.25),
            "release_state": {t.key: clamp(t.value) for t.key, t.value in t.release.items()},
            "emotions": t.emotions,
            "primary_emotion": t.primary_emotion,
            "secondary_emotion": t.secondary_emotion,
            "emotional_intensity": t.emotional_intensity,
            "impulse": t.impulse,
        },
        "subconscious_bias": {
            "active_wound": t.state["cognitive_bias"],
            "active_gift": t.state["cognitive_gift"],
            "bias_state": t.bias_state,
            "perceptual_warp": f"Filters stimulus through {t.state['active_focus']} ({t.bias_state}).",
            "subconscious_visceral_truth": t.state.get("subconscious_visceral_truth") or t.visceral_truth,
            "conscious_rationalization": t.state.get("conscious_rationalization") or t.rationalization,
            "defense_posture": t.defense_posture,
        },
        "social_mask": {
            "facade_type": t.state["social_facade"],
            "mask_strain": t.mask_strain,
            "mask_fracture": t.mask_fracture,
            "fracture_tell": t.cue_text if t.mask_strain >= 30 and t.cue_text else "none",
        },
        "relational_vectors": {
            t.target: {
                "intimacy": clamp(t.stimulus.get("willingness_to_be_seen",
                                      t.bond.get("emotional_safety", 0) - t.threat * 0.5
                                      - t.unease * 0.25 - t.bond.get("resentment_friction", 0) * 0.25)),
                "emotional_safety": clamp(t.bond.get("emotional_safety", 60)),
                "attraction_physical": t.phys_attr,
                "attraction_emotional": t.emot_attr,
                "respect_competence": clamp(t.bond.get("respect_competence", 45)),
                "status_dynamic": t.status_dynamic,
                "resentment_friction": clamp(int(t.bond.get("resentment_friction", 0)) + int(0.3 * t.threat)),
                "relational_momentum": t.momentum,
            }
        },
        "priority_arbitration": {
            "winning_drive": t.winning_drive,
            "salience_score": t.salience_score,
            "arbitration_status": t.arbitration_status,
            "internal_friction": t.internal_friction,
            "competing_drives": t.drives,
        },
        "output_vector": {"feels": t.feels},
    }
