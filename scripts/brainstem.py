#!/usr/bin/env python3
"""
Simulacra Deterministic Brain-Stem Engine (Layer 1-2 Runtime)
-------------------------------------------------------------
Computes autonomic state, polyvagal mode, dual-circuit regime, social mask strain,
non-repeating somatic cues from realm_data.yaml, drive priority arbitration, and
§8 durable commit gating—outputting a schema-validated psychosomatic_state.json
plus explicit triggered_rules and style_constraints for downstream LLM rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REALM_DATA_PATH = ROOT / "Framework" / "Psychology" / "realm_data.yaml"
SCHEMA_PATH = ROOT / "Framework" / "Schemas" / "psychosomatic_state.json"

sys.path.insert(0, str(ROOT / "scripts"))
import validate_state  # noqa: E402

ZONE_MAP = {
    "Z1": "Z1_Cranial_Ocular",
    "Z2": "Z2_Vocal_Cervical",
    "Z3": "Z3_Thoracic_Respiratory",
    "Z4": "Z4_Abdominal_Visceral",
    "Z5": "Z5_Pelvic_Kinesthetic",
    "Z6": "Z6_Peripheral_Grounding",
}

DEFAULT_BROADCAST_OPENERS = [
    "[direct_observation]",
    "[deadpan_statement]",
    "[abrupt_reframe]",
    "[quiet_agreement]",
]

ENDEARMENT_PLACEMENTS = ["omit", "mid_sentence", "closing", "opener"]


def clamp(val: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(val))))


def parse_realm_num(focus_str: str) -> str:
    m = re.search(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X)\b", str(focus_str))
    return m.group(1) if m else "X"


def load_character(card_path: Path, slug: str | None) -> dict[str, Any]:
    data = yaml.safe_load(card_path.read_text(encoding="utf-8"))
    if "characters" in data and isinstance(data["characters"], dict):
        key = slug or next(iter(data["characters"]))
        if key not in data["characters"]:
            raise KeyError(f"Slug '{key}' not found in {card_path}; available: {list(data['characters'])}")
        return dict(data["characters"][key])
    return dict(data)


def overlay_log(card: dict[str, Any], log_path: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    state = {
        "character_id": card.get("character_id") or (card.get("call_name") or card.get("name", "unknown")).lower(),
        "canon_adult": bool(card.get("canon_adult", False)),
        "age": int(card.get("age", 18)),
        "active_focus": card.get("active_focus", "Realm X — The Return"),
        "latent_weights": dict(card.get("transformation_weights", {}).get("latent_anchors", {})),
        "bias_strength": int(card.get("transformation_weights", {}).get("bias_strength", 60)),
        "flexibility": int(card.get("transformation_weights", {}).get("somatic_flexibility", 40)),
        "defense_posture": card.get("defense_posture_default", "none"),
        "social_facade": card.get("social_facade_default", "cool_politeness"),
        "default_somatic": card.get("default_somatic_alignment", ""),
        "cognitive_bias": card.get("cognitive_bias", ""),
        "cognitive_gift": card.get("cognitive_gift", ""),
        "broadcast_persona": card.get("broadcast_persona"),
        "conversational_stance": card.get("voice", {}).get("conversational_stance", ""),
        "excluded_cues": set(card.get("excluded_cues", [])),
        "skills": list(card.get("skills", [])),
    }
    if not log_path or not log_path.is_file():
        return state, None

    log_data = yaml.safe_load(log_path.read_text(encoding="utf-8"))
    snap = log_data.get("snapshot", {})
    if snap.get("active_focus"):
        state["active_focus"] = snap["active_focus"]
    if snap.get("latent_weights"):
        state["latent_weights"] = dict(snap["latent_weights"])
    if "bias_strength" in snap:
        state["bias_strength"] = int(snap["bias_strength"])
    if "flexibility" in snap:
        state["flexibility"] = int(snap["flexibility"])
    if snap.get("defense_posture"):
        state["defense_posture"] = snap["defense_posture"]
    if snap.get("social_facade"):
        state["social_facade"] = snap["social_facade"]
    if snap.get("default_somatic"):
        state["default_somatic"] = snap["default_somatic"]
    if log_data.get("character_id"):
        state["character_id"] = log_data["character_id"]
    if log_data.get("skills", {}).get("active"):
        state["skills"] = list(log_data["skills"]["active"])
    return state, log_data


NON_PHYSICAL_CUES = {
    "speech offers no commit",
}


def select_somatic_cues(
    realm_data: dict[str, Any],
    realm_key: str,
    tier: str,
    recent_cues: list[str],
    seed_str: str,
    exclude_extra: set[str] | None = None,
) -> tuple[list[str], str]:
    realms = realm_data.get("realms", {})
    r = realms.get(realm_key) or realms.get("X") or next(iter(realms.values()))
    raw_pool = list(r.get(tier, [])) or list(r.get("micro", []))
    excluded = NON_PHYSICAL_CUES | (exclude_extra or set())
    pool = [c for c in raw_pool if c not in excluded] or raw_pool
    fresh = [c for c in pool if c not in recent_cues] or pool
    idx = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % len(fresh)
    chosen = [fresh[idx]]
    if len(fresh) > 1:
        chosen.append(fresh[(idx + 1) % len(fresh)])
    vocal = r.get("vocal_behavior", {}).get(tier, "")
    return chosen, vocal


def run_brainstem(
    state: dict[str, Any],
    stimulus: dict[str, Any],
    realm_data: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    rules: list[str] = []
    threat = clamp(stimulus.get("threat_level", 10))
    social_p = clamp(stimulus.get("social_pressure", 20))
    realm_hits = stimulus.get("realm_hits", {}) or {}
    context = stimulus.get("context", "broadcast")
    target = stimulus.get("caller_or_target", "caller")
    event_label = stimulus.get("event_label", "tick_01")
    intimacy_cue = bool(stimulus.get("intimacy_cue", False))
    response_time_ms = int(stimulus.get("response_time_ms", 2000))
    time_pressure = stimulus.get(
        "time_pressure",
        "split_second" if response_time_ms <= 800 else ("deliberate" if response_time_ms >= 2500 else "normal"),
    )

    prev_fatigue = int(history.get("last_fatigue", 15))
    recent_cues: list[str] = list(history.get("recent_cues", []))
    recent_openers: list[str] = list(history.get("recent_openers", []))
    recent_patterns: list[str] = list(history.get("recent_patterns", []))
    pattern_weights: dict[str, int] = dict(history.get("pattern_weights", {}))

    # 1. Autonomic & Polyvagal calculation (CognitivePipeline §4.1)
    latent_hit_bonus = 0
    for rk, weight in state["latent_weights"].items():
        clean_rk = str(rk).replace("Realm_", "")
        if clean_rk in realm_hits:
            latent_hit_bonus += int(realm_hits[clean_rk] * (weight / 100.0))
            rules.append(f"LATENT_REALM_HIT:{clean_rk}")

    arousal = clamp(25 + int(0.4 * threat) + int(0.3 * social_p) + int(0.25 * latent_hit_bonus))
    stress = clamp(10 + int(0.55 * threat) + int(0.2 * social_p) + int(0.35 * latent_hit_bonus) - int(0.15 * state["flexibility"]))
    fatigue = clamp(prev_fatigue + (3 if context == "broadcast" else 5))
    pain = clamp(stimulus.get("pain", 0))
    autonomic_surge = stress >= 75 or threat >= 80

    if stress >= 70 or autonomic_surge or (time_pressure == "split_second" and stress >= 55):
        cognitive_regime = "reactive"
        polyvagal_mode = "dorsal_freeze" if fatigue >= 75 else "sympathetic_mobilized"
        rules.append("DUAL_CIRCUIT_REACTIVE_BYPASS")
        if time_pressure == "split_second" and stress < 70 and not autonomic_surge:
            rules.append("SPLIT_SECOND_REACTIVE_TIP")
    else:
        cognitive_regime = "deliberative"
        polyvagal_mode = "ventral_grounded"
        rules.append("DUAL_CIRCUIT_DELIBERATIVE")

    # Tier & Somatic lookup
    tier = "macro" if stress >= 65 else ("moderate" if stress >= 35 else "micro")
    active_realm_key = parse_realm_num(state["active_focus"])
    hit_realm_key = max(realm_hits, key=lambda k: realm_hits[k]) if realm_hits else active_realm_key
    seed = f"{state['character_id']}:{event_label}:{len(recent_cues)}"
    extra_excl = set(state.get("excluded_cues", set()))
    if state.get("conversational_stance") == "dominant":
        extra_excl.add("scan eyes for approval")
    somatic_cues, vocal_cue = select_somatic_cues(realm_data, hit_realm_key, tier, recent_cues, seed, exclude_extra=extra_excl)
    rules.append(f"SOMATIC_CATALOG:{hit_realm_key}:{tier}")

    zones = ["Z2_Vocal_Cervical", "Z6_Peripheral_Grounding"]
    if tier in ("moderate", "macro"):
        zones.insert(0, "Z1_Cranial_Ocular")
    if stress >= 40:
        zones.append("Z3_Thoracic_Respiratory")

    # 2. Affective impulse
    emotional_intensity = clamp(25 + int(0.5 * stress) + int(0.3 * arousal))
    if cognitive_regime == "reactive":
        primary_emotion, secondary_emotion = "guarded_alert", "tension"
        impulse = "brace_and_cut_off"
    elif threat >= 35 or latent_hit_bonus >= 15:
        primary_emotion, secondary_emotion = "cool_amusement", "guarded_recognition"
        impulse = "reframe_and_deflect"
    else:
        primary_emotion, secondary_emotion = "warm_amusement", "poised_curiosity"
        impulse = "lean_in_and_steer"

    # 3. Subconscious Bias & Defense Posture
    if threat >= 30 or latent_hit_bonus >= 12:
        bias_state = "DEFENSIVE_ACTIVE"
        defense_posture = "deflect_banter" if context == "broadcast" else state["defense_posture"]
        rules.append("BIAS_DEFENSIVE_ACTIVE")
    else:
        bias_state = "GENERATIVE_ACTIVE"
        defense_posture = "none"
        rules.append("BIAS_GENERATIVE_ACTIVE")

    # 4. Social Masking & Strain
    mask_strain = clamp(int(0.6 * stress) + int(0.25 * latent_hit_bonus) - int(0.1 * state["flexibility"]))
    mask_fracture = mask_strain >= 75 or cognitive_regime == "reactive"
    if mask_fracture:
        rules.append("MASK_FRACTURE_TRUE")

    # 5. Priority Arbitration (with time-based body vs mind tiebreaker)
    drives: list[dict[str, Any]] = []
    if context == "broadcast" and state.get("broadcast_persona"):
        drives.append({"drive_name": "broadcast_entertainment_control", "circuit": "mind", "salience": clamp(88 - int(0.45 * stress))})
    drives.append({"drive_name": f"realm_{active_realm_key}_containment", "circuit": "body", "salience": clamp(45 + int(0.4 * state["bias_strength"]) + int(0.3 * latent_hit_bonus))})
    drives.append({"drive_name": "warm_presence_and_intake", "circuit": "mind", "salience": clamp(62 - int(0.3 * threat))})
    if bias_state == "DEFENSIVE_ACTIVE":
        drives.append({"drive_name": "deflect_and_protect_closed_file", "circuit": "body", "salience": clamp(55 + int(0.4 * threat))})

    drives.sort(key=lambda d: d["salience"], reverse=True)
    if len(drives) > 1 and abs(drives[0]["salience"] - drives[1]["salience"]) <= 5:
        c0, c1 = drives[0]["circuit"], drives[1]["circuit"]
        if c0 != c1:
            if time_pressure == "split_second" and c1 == "body":
                drives[0], drives[1] = drives[1], drives[0]
                rules.append("TIME_TIEBREAKER:SPLIT_SECOND->BODY")
            elif time_pressure == "deliberate" and c1 == "mind":
                drives[0], drives[1] = drives[1], drives[0]
                rules.append("TIME_TIEBREAKER:DELIBERATE->MIND")

    # Strip internal circuit tag before schema validation
    for d in drives:
        d.pop("circuit", None)

    winning_drive = drives[0]["drive_name"]
    salience_score = drives[0]["salience"]
    internal_friction = clamp(abs(drives[0]["salience"] - drives[1]["salience"]) if len(drives) > 1 else 0)
    internal_friction = clamp(100 - internal_friction) if len(drives) > 1 and drives[1]["salience"] >= 60 else clamp(int(0.4 * stress) + int(0.3 * latent_hit_bonus))
    arbitration_status = "bypassed_reactive" if cognitive_regime == "reactive" else "arbitrated"
    rules.append(f"ARBITRATION:{arbitration_status}:{winning_drive}")

    # 6. Adult eligibility gate (Main.md / CognitivePipeline §2)
    adult_eligible = bool(state["canon_adult"] and state["age"] >= 18)
    phys_attr = 15 if (adult_eligible and intimacy_cue) else (5 if adult_eligible else 0)
    emot_attr = 20 if context == "broadcast" else 15
    rules.append(f"ADULT_GATE:{'ELIGIBLE' if adult_eligible else 'RESTRICTED'}")

    # 7. Anti-repetition & Speech-Pattern Emergence
    bp = state.get("broadcast_persona") or {}
    opener_pool = list(bp.get("openers") or DEFAULT_BROADCAST_OPENERS)
    hard_banned_openers = list(bp.get("banned_openers") or ["Of course."])
    banned_openers = list(dict.fromkeys(hard_banned_openers + (recent_openers[-3:] if recent_openers else [])))
    available_openers = [o for o in opener_pool if o not in banned_openers] or opener_pool
    opener_idx = int(hashlib.sha256((seed + ":open").encode("utf-8")).hexdigest(), 16) % len(available_openers)
    suggested_opener = available_openers[opener_idx]
    endearment_idx = int(hashlib.sha256((seed + ":endear").encode("utf-8")).hexdigest(), 16) % len(ENDEARMENT_PLACEMENTS)
    endearment_placement = ENDEARMENT_PLACEMENTS[endearment_idx]

    card_patterns = bp.get("speech_patterns") or {
        "imperative_plus_sting": {"weight": 25, "cadence": "Short command followed by cold consequence."},
        "dry_literal_flip": {"weight": 25, "cadence": "Literalize phrasing, then invert who has the problem."},
        "split_second_snap": {"weight": 15, "cadence": "Clipped, immediate 1-2 short clauses; zero preamble."},
    }
    for pname, pcfg in card_patterns.items():
        pattern_weights.setdefault(pname, int(pcfg.get("weight", 20)))
    if stimulus.get("reinforce_pattern") in pattern_weights:
        rp = stimulus["reinforce_pattern"]
        pattern_weights[rp] = clamp(pattern_weights[rp] + 8, 5, 80)
        rules.append(f"SPEECH_PATTERN_REINFORCED:{rp}")

    if (time_pressure == "split_second" or cognitive_regime == "reactive") and "split_second_snap" in card_patterns:
        selected_pattern = "split_second_snap"
        rules.append("SPEECH_PATTERN:SPLIT_SECOND_SNAP")
    else:
        candidates = [p for p in card_patterns if p != "split_second_snap"] or list(card_patterns)
        non_recent = [p for p in candidates if p not in recent_patterns[-2:]] or candidates
        non_recent.sort(key=lambda p: (pattern_weights.get(p, 20), hashlib.sha256((seed + p).encode()).hexdigest()), reverse=True)
        selected_pattern = non_recent[0]
        rules.append(f"SPEECH_PATTERN:{selected_pattern}")
    selected_cadence = card_patterns[selected_pattern].get("cadence", "")

    # 8. Durable commit eligibility (CognitivePipeline §8)
    pressure_tier = "High" if stress >= 70 else ("Medium" if stress >= 45 else "Low")
    commit_eligible = pressure_tier in ("Medium", "High")
    rules.append(f"COMMIT_GATE:{'ELIGIBLE' if commit_eligible else 'EPHEMERAL_ONLY'}")

    snapshot = {
        "character_id": state["character_id"],
        "timestamp_or_movement": event_label,
        "autonomic_state": {
            "polyvagal_mode": polyvagal_mode,
            "cognitive_regime": cognitive_regime,
            "arousal": arousal,
            "stress": stress,
            "fatigue": fatigue,
            "pain": pain,
            "primary_somatic_zones": zones,
            "autonomic_surge": autonomic_surge,
        },
        "affective_state": {
            "primary_emotion": primary_emotion,
            "secondary_emotion": secondary_emotion,
            "emotional_intensity": emotional_intensity,
            "impulse": impulse,
            "ambivalence": "enjoys conversational control while keeping closed accounts untouched",
        },
        "subconscious_bias": {
            "active_wound": state["cognitive_bias"],
            "active_gift": state["cognitive_gift"],
            "bias_state": bias_state,
            "perceptual_warp": f"Filters stimulus through {state['active_focus']} ({bias_state}).",
            "subconscious_visceral_truth": "Account stays closed; others' hesitation is read as leverage or weakness.",
            "conscious_rationalization": "I am simply naming what is obvious and keeping the room moving.",
            "defense_posture": defense_posture,
        },
        "social_mask": {
            "facade_type": state["social_facade"],
            "mask_strain": mask_strain,
            "mask_fracture": mask_fracture,
            "fracture_tell": "; ".join(somatic_cues) if mask_strain >= 30 else "none",
        },
        "relational_vectors": {
            target: {
                "emotional_safety": 60,
                "attraction_physical": phys_attr,
                "attraction_emotional": emot_attr,
                "respect_competence": 45,
                "status_dynamic": "dominant",
                "resentment_friction": clamp(int(0.3 * threat)),
                "relational_momentum": "stable",
            }
        },
        "priority_arbitration": {
            "winning_drive": winning_drive,
            "salience_score": salience_score,
            "arbitration_status": arbitration_status,
            "internal_friction": internal_friction,
            "competing_drives": drives,
        },
        "output_vector": {
            "feels": f"{'; '.join(somatic_cues)} ({', '.join(zones)}).",
            "thinks": f"[{cognitive_regime}] Drive={winning_drive}; {bias_state} framing active.",
            "says": f"Pattern: {selected_pattern} ({selected_cadence}) | Vocal: {vocal_cue} | Avoid {banned_openers}.",
            "does": f"Execute physical cues: {'; '.join(somatic_cues)}.",
        },
    }

    schema = validate_state.load_json(SCHEMA_PATH)
    schema_errors = validate_state.validate(snapshot, schema)
    if schema_errors:
        raise RuntimeError(f"Brain-stem produced invalid snapshot: {schema_errors}")

    return {
        "psychosomatic_snapshot": snapshot,
        "brainstem_meta": {
            "triggered_rules": rules,
            "emitted_cues": somatic_cues,
            "vocal_behavior_cue": vocal_cue,
            "pressure_tier": pressure_tier,
            "time_pressure": time_pressure,
            "response_time_ms": response_time_ms,
            "commit_eligible": commit_eligible,
            "style_constraints": {
                "speech_pattern": selected_pattern,
                "speech_cadence": selected_cadence,
                "banned_recent_openers": banned_openers,
                "suggested_opener": suggested_opener,
                "endearment_placement": endearment_placement,
                "target_word_range": [18, 35] if context == "broadcast" else None,
            },
        },
        "next_history": {
            "last_fatigue": fatigue,
            "recent_cues": (recent_cues + somatic_cues)[-10:],
            "recent_openers": (recent_openers + [suggested_opener])[-5:],
            "recent_patterns": (recent_patterns + [selected_pattern])[-5:],
            "pattern_weights": pattern_weights,
        },
    }


def apply_commit(log_path: Path, output: dict[str, Any], force: bool = False) -> bool:
    meta = output["brainstem_meta"]
    if not meta["commit_eligible"] and not force:
        return False
    log_data = yaml.safe_load(log_path.read_text(encoding="utf-8"))
    snap = log_data.setdefault("snapshot", {})
    auto = output["psychosomatic_snapshot"]["autonomic_state"]
    if auto["stress"] >= 65:
        snap["bias_strength"] = clamp(int(snap.get("bias_strength", 80)) - 2)
    log_data.setdefault("history", []).append({
        "movement": output["psychosomatic_snapshot"]["timestamp_or_movement"],
        "pressure": f"BrainStem/{meta['pressure_tier']}",
        "delta": "bias_strength -2" if auto["stress"] >= 65 else "none",
        "permanence": "temporary" if meta["pressure_tier"] == "Medium" else "permanent",
        "notes": f"Rules: {', '.join(meta['triggered_rules'][:4])}",
    })
    log_path.write_text(yaml.safe_dump(log_data, sort_keys=False), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulacra Deterministic Brain-Stem Engine")
    parser.add_argument("--card", required=True, help="Path to character YAML/.md card")
    parser.add_argument("--slug", default=None, help="Character slug for multi-character cards")
    parser.add_argument("--log", default=None, help="Path to durable *_log.yaml")
    parser.add_argument("--stimulus", required=True, help="JSON string or path to stimulus JSON")
    parser.add_argument("--history-file", default=None, help="Optional ephemeral history JSON for cue/opener rotation")
    parser.add_argument("--out", default=None, help="Path to write full output JSON (and *_snapshot.json)")
    parser.add_argument("--commit", action="store_true", help="Commit to --log if pressure >= Medium")
    parser.add_argument("--force-commit", action="store_true", help="Force commit to --log")
    args = parser.parse_args()

    card = load_character(Path(args.card), args.slug)
    log_path = Path(args.log) if args.log else None
    state, _ = overlay_log(card, log_path)

    stim_path = Path(args.stimulus)
    stimulus = json.loads(stim_path.read_text(encoding="utf-8")) if stim_path.is_file() else json.loads(args.stimulus)

    hist_path = Path(args.history_file) if args.history_file else None
    history = json.loads(hist_path.read_text(encoding="utf-8")) if (hist_path and hist_path.is_file()) else {}

    realm_data = yaml.safe_load(REALM_DATA_PATH.read_text(encoding="utf-8"))
    result = run_brainstem(state, stimulus, realm_data, history)

    if hist_path:
        hist_path.write_text(json.dumps(result["next_history"], indent=2), encoding="utf-8")

    if args.commit or args.force_commit:
        if not log_path:
            raise ValueError("--commit requires --log")
        committed = apply_commit(log_path, result, force=args.force_commit)
        result["brainstem_meta"]["committed_to_log"] = committed

    if args.out:
        out_p = Path(args.out)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        snap_p = out_p.with_name(out_p.stem + "_snapshot.json")
        snap_p.write_text(json.dumps(result["psychosomatic_snapshot"], indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
