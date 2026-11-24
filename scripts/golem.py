#!/usr/bin/env python3
"""
Simulacra Golem Engine (Layer 1-2 Runtime)
-------------------------------------------------------------
Computes autonomic state, polyvagal mode, dual-circuit regime, social mask strain,
non-repeating somatic cues from realm_data.yaml, drive priority arbitration, and
§8 durable commit gating—outputting a schema-validated psychosomatic_state.json
plus triggered rules and somatic cues for downstream LLM rendering.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REALM_DATA_PATH = ROOT / "Framework" / "Psychology" / "realm_data.yaml"
SCHEMA_PATH = ROOT / "Framework" / "Schemas" / "psychosomatic_state.json"

sys.path.insert(0, str(ROOT / "scripts"))
import validate_state  # noqa: E402
from goal_evolution import current_goals  # noqa: E402

ZONE_MAP = {
    "Z1": "Z1_Cranial_Ocular",
    "Z2": "Z2_Vocal_Cervical",
    "Z3": "Z3_Thoracic_Respiratory",
    "Z4": "Z4_Abdominal_Visceral",
    "Z5": "Z5_Pelvic_Kinesthetic",
    "Z6": "Z6_Peripheral_Grounding",
}

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
    "sleep_debt_awake_per_hour": 1.5,
    "sleep_debt_resting_per_hour": 0.5,
    "sleep_debt_sleep_recovery_per_hour": 12.0,
    "max_elapsed_hours_per_tick": 24.0,
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
SEXUAL_AROUSAL_RECOVERY_MINUTES = 2


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


def somatic_profile(card):
    sex = biological_sex(card)
    baselines = SOMATIC_BASELINES.copy()
    if int(card.get("age", 0)) >= 18:
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
    falling = 2 ** (-since_peak / SEXUAL_AROUSAL_RECOVERY_MINUTES) if minutes_asleep >= 75 else 0.0
    return 24 * max(rising, falling)


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
    if values["max_elapsed_hours_per_tick"] <= 0:
        raise ValueError("physiology_calibration.max_elapsed_hours_per_tick must be positive")
    return {key: float(value) for key, value in values.items()}


def recover_distress(
    previous: float, baseline: int, current_stimulus: int, elapsed_minutes: float, half_life_minutes: float
) -> float:
    remaining = 2 ** (-elapsed_minutes / half_life_minutes)
    residual = baseline + (previous - baseline) * remaining
    return max(baseline, residual, current_stimulus)


def parse_realm_num(focus_str: str) -> str:
    m = re.search(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X)\b", str(focus_str))
    return m.group(1) if m else "X"


# Only persist defaults that are character-neutral or already used by the runtime.
CARD_DEFAULTS = {
    "biological_sex": "unspecified", "somatic_baselines": {}, "arousal_regions": None,
    "age": 0, "canon_adult": False, "physical_pain_baseline": 0,
    "emotional_distress_baseline": 0, "physical_pain_tolerance": 50,
    "emotional_distress_tolerance": 50, "sexual_drive_baseline": 50,
    "physiology_calibration": DEFAULT_PHYSIOLOGY_CALIBRATION,
    "active_focus": "Realm X — The Return", "defense_posture_default": "none",
    "social_facade_default": "cool_politeness", "default_somatic_alignment": "",
    "cognitive_bias": "", "cognitive_gift": "", "excluded_cues": [],
    "transformation_weights": {"latent_anchors": {}, "bias_strength": 60, "somatic_flexibility": 40},
    "voice": {"conversational_stance": ""}, "skills": [], "relationships": [],
    "motivations": {}, "incentives": {}, "goals": {},
}


def missing_card_fields(card, defaults=CARD_DEFAULTS, path=()):
    for key, default in defaults.items():
        if key not in card:
            yield path, key, default
        elif isinstance(default, dict) and isinstance(card[key], dict):
            yield from missing_card_fields(card[key], default, (*path, key))


def selected_card(data, slug):
    if not isinstance(data, dict):
        raise ValueError("Character card must be a YAML mapping")
    if isinstance(data.get("characters"), dict):
        cards = data["characters"]
        key = slug or next(iter(cards), None)
        if key not in cards:
            raise ValueError(f"Slug '{key}' not found; available: {list(cards)}")
        if not isinstance(cards[key], dict):
            raise ValueError("Selected character card must be a YAML mapping")
        return cards[key], ("characters", key)
    return data, ()


def insert_card_defaults(source, data, card_path, changes):
    # Insert into the original mappings so comments, quoting and untouched cards survive.
    root = yaml.compose(source)
    additions = {}
    for path, key, value in changes:
        additions.setdefault(card_path + path, {})[key] = value
    edits = []
    for path, fields in additions.items():
        node = root
        for part in path:
            node = next((v for k, v in node.value if k.value == part), None)
            if node is None:  # A mapping inherited through a YAML merge.
                break
        if node is None:
            break
        if node.flow_style:
            pos = node.end_mark.index - 1
            fragment = (", " if node.value else "") + json.dumps(fields, ensure_ascii=False)[1:-1]
            if node.value and source[node.value[-1][1].end_mark.index:pos].strip() == ",":
                fragment = fragment[1:]
        else:
            first = node.value[0][0].start_mark
            pos = first.index
            indent = " " * first.column
            lines = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True).rstrip().splitlines()
            fragment = ("\n" + indent).join(lines) + "\n" + indent
        edits.append((pos, fragment))
    else:
        candidate = source
        for pos, fragment in sorted(edits, reverse=True):
            candidate = candidate[:pos] + fragment + candidate[pos:]
        try:
            if yaml.safe_load(candidate) == data:
                return candidate
        except yaml.YAMLError:
            pass
    # Shared aliases and inherited mappings may require materializing a separate card.
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def load_character(card_path: Path, slug: str | None) -> dict[str, Any]:
    """Read a character without modifying its card during a live wake."""
    card, _ = selected_card(yaml.safe_load(Path(card_path).read_text(encoding="utf-8")), slug)
    return card


def migrate_character_card(card_path: Path, slug: str | None = None) -> dict[str, Any]:
    """Add missing neutral defaults explicitly, during deployment only."""
    card_path = card_path.resolve()
    with locked_file(card_path):
        source = card_path.read_text(encoding="utf-8")
        data = yaml.safe_load(source)
        card, path = selected_card(data, slug)
        changes = list(missing_card_fields(card))
        if changes:
            # Copy mappings along the edit path to isolate YAML anchors shared by other cards.
            for parents, key, default in changes:
                current = data
                for part in path + parents:
                    current[part] = dict(current[part])
                    current = current[part]
                current[key] = copy.deepcopy(default)
            card, _ = selected_card(data, slug)
            overlay_log(card, None)  # Validate operational values before updating the file.
            replace_text(card_path, insert_card_defaults(source, data, path, changes))
        return card


def overlay_log(
    card: dict[str, Any], log_path: Path | None, *, goal_changes: dict | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    weights = card.get("transformation_weights") or {}
    voice = card.get("voice") or {}
    state = {
        "character_id": card.get("character_id") or (card.get("call_name") or card.get("name") or "unknown").lower(),
        "canon_adult": card.get("canon_adult") is True,
        "age": int(card.get("age", 0)),
        "sexual_drive_baseline": clamp(card.get("sexual_drive_baseline", 50)),
        "physical_pain_tolerance": clamp(card.get("physical_pain_tolerance", 50)),
        "emotional_distress_tolerance": clamp(card.get("emotional_distress_tolerance", 50)),
        "physical_pain_baseline": clamp(card.get("physical_pain_baseline", 0)),
        "emotional_distress_baseline": clamp(card.get("emotional_distress_baseline", 0)),
        "active_focus": card.get("active_focus", "Realm X — The Return"),
        "latent_weights": dict(weights.get("latent_anchors") or {}),
        "bias_strength": int(weights.get("bias_strength", 60)),
        "flexibility": int(weights.get("somatic_flexibility", 40)),
        "defense_posture": card.get("defense_posture_default", "none"),
        "social_facade": card.get("social_facade_default", "cool_politeness"),
        "default_somatic": card.get("default_somatic_alignment", ""),
        "cognitive_bias": card.get("cognitive_bias", ""),
        "cognitive_gift": card.get("cognitive_gift", ""),
        **{k: card[k] for k in ("subconscious_visceral_truth", "conscious_rationalization") if card.get(k)},
        "broadcast_persona": card.get("broadcast_persona"),
        "conversational_stance": voice.get("conversational_stance", ""),
        "excluded_cues": sorted(set(card.get("excluded_cues") or [])),
        "skills": list(card.get("skills") or []),
        "physiology_calibration": physiology_calibration(card),
        "somatic_profile": somatic_profile(card),
        "arousal_regions": arousal_regions(card),
    }
    if not log_path or not log_path.is_file():
        state["current_goals"] = current_goals(card.get("goals"), None, goal_changes)
        return state, None

    log_data = yaml.safe_load(log_path.read_text(encoding="utf-8")) or {}
    if card.get("character_id") and log_data.get("character_id") not in (None, card["character_id"]):
        raise ValueError("Character ID mismatch between card and durable log")
    snap = log_data.get("snapshot") or {}
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
    skills_map = log_data.get("skills") or {}
    if skills_map.get("active"):
        state["skills"] = list(skills_map["active"])
    state["memories"] = log_data.get("memories") or {}
    state["relational_baselines"] = log_data.get("relational_baselines") or {}
    state["current_goals"] = current_goals(card.get("goals"), log_data.get("goal_updates"), goal_changes)
    return state, log_data


def cue_keys(cues: Any) -> set[str]:
    if not isinstance(cues, list) or any(not isinstance(cue, str) or not cue.strip() for cue in cues):
        raise ValueError("Memory cues must be a list of nonempty strings")
    return {cue.strip().casefold() for cue in cues}


def recall_memories(memories: dict[str, Any], cues: Any) -> list[dict[str, Any]]:
    keys = cue_keys(cues)
    return [
        {"id": entry["id"], "summary": entry["summary"], "kind": kind}
        for kind in ("detailed", "footnote")
        for entry in memories.get(kind, [])
        if isinstance(entry, dict) and {"id", "summary"} <= entry.keys()
        and keys.intersection(cue_keys(entry.get("cues", [])))
    ]


def add_memory(log_data: dict[str, Any], memory: dict[str, Any]) -> bool:
    fields = ("id", "kind", "summary", "reason")
    if not isinstance(memory, dict) or any(
        not isinstance(memory.get(key), str) or not memory[key].strip() for key in fields
    ):
        raise ValueError("An approved memory requires nonempty id, kind, summary, and reason strings")
    kind = memory["kind"].strip()
    if kind not in ("detailed", "footnote"):
        raise ValueError("Memory kind must be detailed or footnote")
    cues = sorted(cue_keys(memory.get("cues")))
    if not cues:
        raise ValueError("An approved memory requires at least one recall cue")
    entry = {key: memory[key].strip() for key in ("id", "summary", "reason")}
    entry["cues"] = cues
    memories = log_data.setdefault("memories", {})
    for bucket in ("detailed", "footnote"):
        for existing in memories.get(bucket, []):
            if isinstance(existing, dict) and existing.get("id") == entry["id"]:
                if bucket == kind and existing == entry:
                    return False
                raise ValueError(f"Memory ID already exists: {entry['id']}")
    memories.setdefault(kind, []).append(entry)
    log_data["revision"] = log_data.get("revision", 0) + 1
    log_data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_data["last_commit_id"] = entry["id"]
    return True


def conversation_intent(
    conversation: dict[str, Any], interest: float, guarded: bool, activated: bool,
    target: str, recent_inquiries: list[list[str]],
) -> dict[str, str] | None:
    if not isinstance(conversation, dict):
        raise ValueError("Conversation must be a JSON object")
    conflict = conversation.get("conflict")
    topic = conversation.get("open_topic", "")
    if conflict not in (None, "boundary", "goal", "claim") or not isinstance(topic, str):
        raise ValueError("Conversation accepts a boundary, goal, or claim conflict and a text open_topic")
    if "willing_to_help" in conversation:
        willing = conversation["willing_to_help"]
        if not isinstance(willing, bool):
            raise ValueError("willing_to_help must be a boolean")
        if not willing:
            return {"intent": "decline", "delivery": "brief" if activated else "deliberate"}
    if conflict:
        return {"intent": "push_back", "conflict": conflict, "delivery": "brief" if activated else "deliberate"}
    topic = topic.strip()
    if topic and interest >= 60 and not guarded and [target, topic.casefold()] not in recent_inquiries:
        return {"intent": "ask", "topic": topic}
    return None


def parse_event_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("event_at must be an ISO 8601 timestamp with a timezone")
    timestamp = datetime.fromisoformat(value)
    if timestamp.utcoffset() is None:
        raise ValueError("event_at must include a timezone")
    return timestamp.astimezone(timezone.utc)


def event_clock(stimulus: dict[str, Any], history: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    previous = history.get("last_event_at")
    if "event_at" in stimulus:
        if {"elapsed_ms", "elapsed_minutes"} & stimulus.keys():
            raise ValueError("event_at cannot be combined with explicit elapsed time")
        current = parse_event_time(stimulus["event_at"])
        elapsed_ms = (current - parse_event_time(previous)).total_seconds() * 1_000 if previous else 0.0
        if elapsed_ms < 0:
            raise ValueError("event_at is earlier than the last processed event")
        return elapsed_ms, {
            "last_event_at": current.isoformat(),
            "event_sequence": history.get("event_sequence", 0) + 1,
        }
    if previous:
        raise ValueError("event_at is required when continuing timestamped history")
    if "elapsed_ms" in stimulus:
        return float(stimulus["elapsed_ms"]), {}
    return float(stimulus.get("elapsed_minutes", 1)) * 60_000, {}


# The shared realm catalog includes staging and dialogue cues for the renderer.
RENDERING_CUES = {
    "adjust collar",
    "adjust cuffs/sleeves",
    "align geometrically",
    "avoid organic shapes",
    "check exits",
    "check fingernails",
    "code-switch no transition",
    "compulsive rearranging",
    "controlled blink",
    "echo other's speech",
    "echolalia/repetition",
    "flat managed voice",
    "fold objects repeatedly",
    "lean forward shield",
    "measured speech",
    "micro-adjust vocal register",
    "monosyllabic speech",
    "parse speech for threats",
    "performance of composure",
    "performed open hands",
    "performed stillness",
    "push gifts away",
    "rapid nodding soothe",
    "refuse raw textures",
    "repeat words under breath",
    "rotate objects",
    "singsong voice",
    "slow speaking rhythm",
    "speech offers no commit",
    "speech fragmented",
    "speech hammer beats",
    "smooth clothing",
    "spine deliberate",
    "spine display posture",
    "straighten items",
    "talk fast prevent silence",
    "talk over pauses",
    "trace edges",
    "vocal chords tighten/monotone",
    "voice abrupt switches",
    "voice clipped/technical",
    "voice core tone",
    "voice drone",
    "voice growl/monotone",
    "voice projects artificially",
    "voice singsong",
    "voice tones switch mid-sentence",
    "voice trembles false",
    "wait fear to pass",
    "wipe surfaces obsessively",
}


def select_somatic_cues(
    realm_data: dict[str, Any],
    realm_key: str,
    tier: str,
    recent_cues: list[str],
    seed_str: str,
    exclude_extra: set[str] | None = None,
) -> list[str]:
    realms = realm_data.get("realms", {})
    r = realms.get(realm_key) or realms.get("X") or next(iter(realms.values()))
    excluded = RENDERING_CUES | (exclude_extra or set())
    pool = [c for c in r.get(tier, []) if c not in excluded]
    if not pool:
        pool = [c for c in r.get("micro", []) if c not in excluded]
    if not pool:
        return []
    fresh = [c for c in pool if c not in recent_cues] or pool
    idx = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % len(fresh)
    chosen = [fresh[idx]]
    if len(fresh) > 1:
        chosen.append(fresh[(idx + 1) % len(fresh)])
    return chosen


# Regions refine the six coarse zones used by existing cards and snapshots.
SOMATIC_ZONES = {
    "Z1_Cranial_Ocular": "scalp head face forehead brow eye ear nose cheek jaw mouth lip tongue teeth",
    "Z2_Vocal_Cervical": "neck throat larynx",
    "Z3_Thoracic_Respiratory": "chest breast nipple areola ribs lungs heart diaphragm upper_back",
    "Z4_Abdominal_Visceral": "abdomen lower_abdomen stomach gut flank lower_back",
    "Z5_Pelvic_Kinesthetic": "pelvis hip groin genitals pelvic_floor perineum clitoris labia vagina penis scrotum bladder buttock",
    "Z6_Peripheral_Grounding": "shoulder upper_arm elbow forearm wrist hand palm finger thumb thigh inner_thigh knee shin calf ankle foot heel sole toe",
}
REGION_ZONE = {region: zone for zone, regions in SOMATIC_ZONES.items() for region in regions.split()}


def arousal_sensations(arousal, sexual_arousal, sites):
    """Localize this tick's two response levels, preserving the coarse pelvic signal."""
    # General autonomic activation can be felt after exertion or alarm.
    yield "heart", "noticeable heartbeat", clamp(0.8 * (arousal - 45))
    yield "diaphragm", "quicker breathing", clamp(0.55 * (arousal - 50))
    if not sexual_arousal:
        return
    yield "pelvis", "arousal", sexual_arousal
    # Thresholds keep a faint response local. Intensities are simulation scales.
    shared = (
        ("pelvic_floor", "tension", 10, 0.65), ("perineum", "fullness", 18, 0.50),
        ("lower_abdomen", "warmth", 25, 0.55), ("inner_thigh", "tension", 45, 0.45),
        ("nipple", "sensitivity", 55, 0.45),
    )
    for region, sensation, threshold, gain in shared:
        yield region, sensation, clamp((sexual_arousal - threshold) * gain)
    for region in sites:
        sensation, threshold, gain = GENITAL_RESPONSE_SITES[region]
        yield region, sensation, clamp((sexual_arousal - threshold) * gain)


def somatic_map(stimulus, body_signals):
    """Merge inferred and scene-local sensations without losing coexisting sensations."""
    regions = {}
    for region, sensation, intensity in body_signals:
        if intensity:
            regions.setdefault(region, {})[sensation] = intensity
    observations = stimulus.get("somatic_map", {})
    if not isinstance(observations, dict):
        raise ValueError("somatic_map must map body regions to sensations")
    for location, sensations in observations.items():
        region = re.sub(r"^(left|right)_", "", location) if isinstance(location, str) else ""
        if region not in REGION_ZONE and location not in ("skin", "whole_body"):
            raise ValueError(f"Unknown somatic region: {location}")
        if not isinstance(sensations, dict):
            raise ValueError("Each somatic region must map sensation names to intensities")
        for name, value in sensations.items():
            if not isinstance(name, str) or not name.strip() or type(value) is not int or not 0 <= value <= 100:
                raise ValueError("A sensation requires a name and integer intensity from 0 to 100")
            if value:
                regions.setdefault(location, {})[name] = value
            elif location in regions:
                regions[location].pop(name, None)
    return {location: sensations for location, sensations in regions.items() if sensations}


def run_golem(
    state: dict[str, Any],
    stimulus: dict[str, Any],
    realm_data: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    rules: list[str] = []
    if history.get("character_id") not in (None, state["character_id"]):
        raise ValueError("Character ID mismatch in carried history")
    threat = clamp(stimulus.get("threat_level", 10))
    social_p = clamp(stimulus.get("social_pressure", 20))
    physical_pain_tolerance = state.get("physical_pain_tolerance", 50)
    emotional_distress_tolerance = state.get("emotional_distress_tolerance", 50)
    realm_hits = stimulus.get("realm_hits", {}) or {}
    context = stimulus.get("context", "broadcast")
    target = stimulus.get("caller_or_target", "caller")
    event_label = stimulus.get("event_label", "tick_01")
    elapsed_ms, clock_state = event_clock(stimulus, history)
    if not math.isfinite(elapsed_ms):
        raise ValueError("Elapsed scene time must be finite")
    elapsed_ms = max(0.0, elapsed_ms)
    elapsed_minutes = elapsed_ms / 60_000
    appraisal = stimulus.get("appraisal", {})
    if not isinstance(appraisal, dict) or any(
        key not in APPRAISAL_SIGNALS or type(value) is not int or not 0 <= value <= 100
        for key, value in appraisal.items()
    ):
        raise ValueError("Appraisal must map known signals to integer scores from 0 to 100")
    prior_appraisal_effects = history.get("appraisal_effects", {})
    # These are immediate appraisals, not enduring relationship measures.
    # Durable attraction/attachment remains in relational_baselines.
    remaining_appraisal = 2 ** (-elapsed_ms / (1_000 * APPRAISAL_HALF_LIFE_SECONDS))
    appraisal_effects = {
        signal: max(appraisal.get(signal, 0), prior_appraisal_effects.get(signal, 0) * remaining_appraisal)
        for signal in APPRAISAL_SIGNALS
    }
    # The host can recognize feelings whose meaning depends on the character's interpretation.
    # Keep fractional carryover so that repeated short ticks equal one longer interval.
    felt = {
        name: intensity * remaining_appraisal
        for name, intensity in history.get("felt_emotions", {}).items()
        if intensity * remaining_appraisal >= 0.5
    }
    updates = stimulus.get("emotions", {})
    if not isinstance(updates, dict):
        raise ValueError("emotions must map names to intensity scores")
    for name, intensity in updates.items():
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ValueError("emotion names must be nonempty text without surrounding whitespace")
        if type(intensity) is not int or not 0 <= intensity <= 100:
            raise ValueError("emotion intensity must be an integer from 0 to 100")
        if intensity:
            felt[name] = intensity
        else:
            felt.pop(name, None)
    interest = appraisal_effects["interest"]
    attraction = appraisal_effects["attraction"]
    disgust = appraisal_effects["disgust"]
    unease = appraisal_effects["unease"]
    uncertainty = appraisal_effects["uncertainty"]
    visceral_revulsion = clamp(disgust)
    pain_baseline = state.get("physical_pain_baseline", 0)
    distress_baseline = state.get("emotional_distress_baseline", 0)
    physical_pain_level = recover_distress(
        history.get("physical_pain", pain_baseline),
        pain_baseline,
        clamp(stimulus.get("physical_pain", stimulus.get("pain", 0))),
        elapsed_minutes,
        PHYSICAL_PAIN_HALF_LIFE_MINUTES,
    )
    emotional_distress_level = recover_distress(
        history.get("emotional_distress", distress_baseline),
        distress_baseline,
        clamp(stimulus.get("emotional_distress", 0)),
        elapsed_minutes,
        EMOTIONAL_DISTRESS_HALF_LIFE_MINUTES,
    )
    physical_pain = clamp(physical_pain_level)
    emotional_distress = clamp(emotional_distress_level)

    calibration = {**DEFAULT_PHYSIOLOGY_CALIBRATION, **state.get("physiology_calibration", {})}
    activity = stimulus.get("activity", history.get("activity", "awake"))
    if activity not in ("awake", "resting", "sleeping"):
        raise ValueError("Activity must be awake, resting, or sleeping")
    elapsed_hours = min(elapsed_minutes / 60, float(calibration["max_elapsed_hours_per_tick"]))
    hunger_rate = calibration["hunger_sleeping_per_hour"] if activity == "sleeping" else calibration["hunger_awake_per_hour"]
    accumulated_hunger = min(100.0, history.get("hunger", 0) + hunger_rate * elapsed_hours)
    food_intake = clamp(stimulus.get("food_intake", 0))
    hunger_level = max(0.0, accumulated_hunger - food_intake)
    hunger = clamp(hunger_level)

    exposure_history = {}
    exposure_state = {}
    exposure_feels = []
    exposure_load = 0.0
    for factor, (label, half_life_seconds, stress_weight, immediate_onset) in EXPOSURE_RESPONSES.items():
        exposure_key = f"{factor}_exposure"
        discomfort_key = f"{factor}_discomfort"
        exposure = clamp(stimulus.get(exposure_key, history.get(exposure_key, 0)))
        previous = history.get(discomfort_key, 0)
        remaining = 2 ** (-elapsed_ms / (1_000 * half_life_seconds))
        level = exposure + (previous - exposure) * remaining
        if immediate_onset:
            level = max(exposure, level)
        discomfort = clamp(level)
        exposure_history.update({exposure_key: exposure, discomfort_key: level})
        exposure_state.update({exposure_key: exposure, discomfort_key: discomfort})
        exposure_load += stress_weight * level
        if discomfort:
            exposure_feels.append(f"{label}: {discomfort}/100.")

    response_time_ms = int(stimulus.get("response_time_ms", 2000))
    time_pressure = stimulus.get(
        "time_pressure",
        "split_second" if response_time_ms <= 800 else ("deliberate" if response_time_ms >= 2500 else "normal"),
    )

    profile = state.get("somatic_profile", SOMATIC_BASELINES)
    # Modest, bounded tuning of response gain and recovery. Appraisal supplies
    # the meaning of the event independently of the endocrine profile.
    adrenergic_gain = 1 + (profile["testosterone"] - profile["estradiol"]) / 500
    recovery_scale = 1 + (profile["estradiol"] - 50) / 250
    exertion = 0
    if activity == "sleeping":
        fatigue_rate = -float(calibration["fatigue_sleep_recovery_per_hour"])
        sleep_debt_rate = -float(calibration["sleep_debt_sleep_recovery_per_hour"])
    elif activity == "resting":
        fatigue_rate = -float(calibration["fatigue_resting_recovery_per_hour"])
        sleep_debt_rate = float(calibration["sleep_debt_resting_per_hour"])
    else:
        exertion = clamp(stimulus.get("exertion", history.get("exertion", 0)))
        fatigue_rate = float(calibration["fatigue_awake_per_hour"]) + float(calibration["fatigue_exertion_per_hour"]) * exertion * adrenergic_gain
        sleep_debt_rate = float(calibration["sleep_debt_awake_per_hour"])

    previous_fatigue = history.get("last_fatigue", 15)
    previous_sleep_debt = history.get("sleep_debt", 0)
    fatigue_level = min(100.0, max(0.0, previous_fatigue + fatigue_rate * elapsed_hours))
    sleep_debt_level = min(100.0, max(0.0, previous_sleep_debt + sleep_debt_rate * elapsed_hours))
    fatigue = clamp(fatigue_level)
    sleep_debt = clamp(sleep_debt_level)
    fatigue_load = max(fatigue_level, sleep_debt_level)
    exhaustion = clamp((fatigue_load - 60) * 2.5)
    recent_cues: list[str] = list(history.get("recent_cues", []))

    # 1. Autonomic & Polyvagal calculation (CognitivePipeline §4.1)
    latent_hit_bonus = 0
    for rk, weight in state["latent_weights"].items():
        clean_rk = str(rk).replace("Realm_", "")
        if clean_rk in realm_hits:
            latent_hit_bonus += int(realm_hits[clean_rk] * (weight / 100.0))
            rules.append(f"LATENT_REALM_HIT:{clean_rk}")

    physical_load = physical_pain_level * (150 - physical_pain_tolerance) / 100
    emotional_load = emotional_distress_level * (150 - emotional_distress_tolerance) / 100
    distress_load = physical_load + emotional_load
    appraisal_activation = 0.25 * interest + 0.25 * disgust + 0.20 * unease
    resting_activation = {"sleeping": 5, "resting": 15, "awake": 25}[activity]
    social_load = max(felt.get("vulnerability", 0), felt.get("protectiveness", 0))
    phasic_load = (0.4 * threat + 0.3 * social_p + 0.25 * latent_hit_bonus
                   + 0.35 * exertion + exposure_load + 0.5 * distress_load
                   + appraisal_activation + 0.2 * social_load)
    activation_target = clamp(resting_activation + adrenergic_gain * phasic_load)
    prior_activation = history.get("arousal", activation_target)
    activation = activation_target + max(0, prior_activation - activation_target) * 2 ** (
        -elapsed_minutes / (ACTIVATION_RECOVERY_MINUTES * recovery_scale)
    )
    arousal = clamp(activation)
    baseline_stress = (
        10 + int(0.55 * threat) + int(0.2 * social_p) + int(0.35 * latent_hit_bonus)
        - int(0.15 * state["flexibility"])
    )
    exhaustion_load = max(0, fatigue_load - 40) * 0.2
    appraisal_stress = 0.40 * disgust + 0.35 * unease + 0.15 * uncertainty
    stress = clamp(
        baseline_stress + distress_load + 0.15 * hunger_level + exposure_load + exhaustion_load + appraisal_stress
    )
    if physical_pain == 100:
        activation = 100
        arousal = stress = 100
        rules.append("ACUTE_PHYSICAL_PAIN_OVERLOAD")
    # Integrate sustained load separately from the immediate autonomic surge.
    # Fractional history survives short ticks. Same-instant appraisals cost no time.
    cortisol_target = clamp(15 + adrenergic_gain * 0.75 * stress)
    previous_cortisol = history.get("cortisol", 15.0)
    half_life = (8 if cortisol_target > previous_cortisol else 20) * recovery_scale
    cortisol = cortisol_target + (previous_cortisol - cortisol_target) * 2 ** (-elapsed_minutes / half_life)
    autonomic_surge = stress >= 75 or threat >= 80

    involuntary_response = "none"
    if stress >= 70 or arousal >= 75 or autonomic_surge or (time_pressure == "split_second" and stress >= 55):
        cognitive_regime = "reactive"
        polyvagal_mode = "dorsal_freeze" if fatigue_load >= 75 else "sympathetic_mobilized"
        involuntary_response = "freeze" if polyvagal_mode == "dorsal_freeze" else "brace"
        rules.append("DUAL_CIRCUIT_REACTIVE_BYPASS")
        if time_pressure == "split_second" and stress < 70 and arousal < 75 and not autonomic_surge:
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
    somatic_cues = select_somatic_cues(realm_data, hit_realm_key, tier, recent_cues, seed, exclude_extra=extra_excl)
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
        impulse = involuntary_response
    elif threat >= 35 or latent_hit_bonus >= 15:
        primary_emotion, secondary_emotion = "cool_amusement", "guarded_recognition"
        impulse = "reframe_and_deflect"
    else:
        primary_emotion, secondary_emotion = "warm_amusement", "poised_curiosity"
        impulse = "lean_in_and_steer"

    # Relative activation, with separate body and appraisal inputs.
    # These are simulation scales rather than measured hormone concentrations.
    release = {
        "alarm": max(physical_load, threat, unease),
        "reward": max(appraisal_effects["delight"], interest * 0.5),
        "settling": appraisal_effects["relief"],
    }
    prior_release = history.get("release_state", {})
    # Sustain an already appraised alarm under prolonged endocrine load.
    # This changes its recovery curve without assigning a new feeling.
    alarm_half_life = APPRAISAL_HALF_LIFE_SECONDS * recovery_scale * (1 + max(0, cortisol - 15) / 100)
    alarm_remaining = 2 ** (-elapsed_ms / (1000 * alarm_half_life))
    for key, value in release.items():
        decay = alarm_remaining if key == "alarm" else remaining_appraisal
        release[key] = min(100, max(value, prior_release.get(key, 0) * decay))
    emotional_pressures = {
        "fear": release["alarm"], "joy": release["reward"], "relief": release["settling"],
        "sadness": appraisal_effects["loss"], "anger": appraisal_effects["frustration"],
        "anticipation": appraisal_effects["anticipation"], "disgust": disgust,
    }
    emotional_pressures.update(interest=interest, unease=unease, uncertainty=uncertainty)
    for name, intensity in felt.items():
        emotional_pressures[name] = max(emotional_pressures.get(name, 0), intensity)
    emotions = {name: clamp(value) for name, value in emotional_pressures.items() if clamp(value)}
    salient = sorted((name for name in emotional_pressures if emotional_pressures[name] >= 40),
                     key=emotional_pressures.get, reverse=True)
    if salient:
        if cognitive_regime == "reactive":
            secondary_emotion = salient[0]
        else:
            primary_emotion = salient[0]
            if len(salient) > 1:
                secondary_emotion = salient[1]
        emotional_intensity = max(emotional_intensity, clamp(emotional_pressures[salient[0]]))

    for key in ("willingness_to_pursue", "willingness_to_be_seen"):
        if key in stimulus and (type(stimulus[key]) is not int or not 0 <= stimulus[key] <= 100):
            raise ValueError(f"{key} must be an integer from 0 to 100")
    pursuit = stimulus.get("willingness_to_pursue", max(interest, release["reward"], hunger * 0.5))
    urge = stimulus.get("urge")
    if urge is not None:
        if (not isinstance(urge, dict) or not isinstance(urge.get("action"), str)
                or not urge["action"].strip() or type(urge.get("strength")) is not int
                or not 0 <= urge["strength"] <= 100):
            raise ValueError("urge requires an action and an integer strength from 0 to 100")
        if cognitive_regime != "reactive" and urge["strength"]:
            impulse = urge["action"].strip()

    # 3. Subconscious Bias & Defense Posture
    if threat >= 30 or latent_hit_bonus >= 12 or unease >= 45 or stress >= 45:
        bias_state = "DEFENSIVE_ACTIVE"
        defense_posture = state["defense_posture"]
        rules.append("BIAS_DEFENSIVE_ACTIVE")
    elif (
        interest >= 35
        or release["reward"] >= 30
        or release["settling"] >= 30
        or attraction >= 25
        or active_realm_key in realm_hits
    ):
        bias_state = "GENERATIVE_ACTIVE"
        defense_posture = "none"
        rules.append("BIAS_GENERATIVE_ACTIVE")
    else:
        bias_state = "DORMANT"
        defense_posture = "none"
        rules.append("BIAS_DORMANT")

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
    intake_boost = int(0.2 * max(interest, release["reward"]))
    drives.append({"drive_name": "warm_presence_and_intake", "circuit": "mind", "salience": min(74, clamp(62 - int(0.3 * threat) + intake_boost))})
    wound = str(state.get("cognitive_bias") or "").split("—", 1)[0].strip().rstrip(".")
    gift = str(state.get("cognitive_gift") or "").split("—", 1)[0].strip().rstrip(".")
    closed_account = wound.startswith("Closed Account")
    if bias_state == "DEFENSIVE_ACTIVE":
        wound_slug = re.sub(r"[^a-z0-9]+", "_", wound.casefold()).strip("_")
        defensive_drive = f"defend_{wound_slug}" if wound_slug else "self_protection"
        if closed_account:
            defensive_drive = "deflect_and_protect_closed_file"
        drives.append({"drive_name": defensive_drive, "circuit": "body", "salience": clamp(55 + int(0.4 * threat))})

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
    if (urge and cognitive_regime != "reactive" and urge["strength"] >= 75
            and urge["strength"] > salience_score and time_pressure != "deliberate"):
        arbitration_status = "impulse_override"
        winning_drive, salience_score = impulse, urge["strength"]
    rules.append(f"ARBITRATION:{arbitration_status}:{winning_drive}")

    # 6. Adult eligibility and background state (CognitivePipeline §2)
    adult_eligible = state["canon_adult"] is True and state["age"] >= 18
    drive_level = 0.0
    sexual_response = 0.0
    excitation = inhibition = minutes_asleep = 0.0
    sexual_arousal = 0
    if adult_eligible:
        baseline_drive = state.get("sexual_drive_baseline", 50)
        previous_drive = history.get("sexual_drive", baseline_drive)
        bodily_load = max(physical_pain_level, emotional_distress_level, fatigue_load)
        target_drive = baseline_drive * (1 - bodily_load / 200)
        # Keep the fractional state in history so short ticks can accumulate.
        remaining = 2 ** (-elapsed_minutes / 30)
        drive_level = target_drive + (previous_drive - target_drive) * remaining
        cue_excitation = min(100, attraction * (0.5 + 0.5 * drive_level / 100) * adrenergic_gain)
        if activity == "sleeping":
            minutes_asleep = history.get("minutes_asleep", 0) + elapsed_minutes
        # Older histories saved only the resulting response.
        prior_excitation = history.get("sexual_excitation", history.get("sexual_arousal", 0))
        recovery = 2 ** (-elapsed_minutes / (SEXUAL_AROUSAL_RECOVERY_MINUTES * recovery_scale))
        residual = prior_excitation * recovery
        if "sexual_arousal" in stimulus:
            residual = clamp(stimulus["sexual_arousal"])
        excitation = max(residual, cue_excitation, sleep_excitation(minutes_asleep))
        inhibition = min(100, max(disgust, unease, 0.75 * physical_load, 0.75 * emotional_load,
                                  stress - 25, 0.5 * exhaustion))
        sexual_response = excitation * (1 - inhibition / 100)
        sexual_arousal = clamp(sexual_response)
    else:
        appraisal_effects["attraction"] = 0
    # A bodily response can have no interpersonal target (sleep, memory, or touch).
    bond = state.get("relational_baselines", {}).get(target) or {}
    if not isinstance(bond, dict):
        bond = {}
    phys_attr = clamp(bond.get("attraction_physical", 0)) if adult_eligible else 0
    emot_attr = clamp(bond.get("attraction_emotional", 0))
    status_dynamic = bond.get("status_dynamic", "dominant")
    if status_dynamic not in ("dominant", "yielding", "equals", "deference"):
        status_dynamic = "dominant"
    momentum = bond.get("relational_momentum", "stable")
    if momentum not in ("building", "deepening", "stable", "eroding", "brittle", "suspended", "fractured"):
        momentum = "stable"
    rules.append(f"ADULT_GATE:{'ELIGIBLE' if adult_eligible else 'RESTRICTED'}")

    # 7. Durable commit eligibility (CognitivePipeline §8)
    pressure_tier = "High" if stress >= 70 else ("Medium" if stress >= 45 else "Low")
    commit_eligible = pressure_tier in ("Medium", "High")
    rules.append(f"COMMIT_GATE:{'ELIGIBLE' if commit_eligible else 'EPHEMERAL_ONLY'}")

    mapped_body = somatic_map(stimulus, (
        ("stomach", "hunger", hunger), ("gut", "queasiness", visceral_revulsion),
        ("eye", "light discomfort", exposure_state["bright_light_discomfort"]),
        ("ear", "noise discomfort", exposure_state["noise_discomfort"]),
        ("skin", "cold discomfort", exposure_state["cold_discomfort"]),
        ("skin", "heat discomfort", exposure_state["heat_discomfort"]),
        ("whole_body", "fatigue", fatigue), ("whole_body", "pain", physical_pain),
        ("chest", "breathing effort", exertion),
        *arousal_sensations(arousal, sexual_arousal, state.get("arousal_regions", ())),
    ))
    for location in mapped_body:
        zone = REGION_ZONE.get(re.sub(r"^(left|right)_", "", location))
        if zone and zone not in zones:
            zones.append(zone)

    cue_text = "; ".join(somatic_cues)
    zone_text = ", ".join(zones)
    feels = f"{cue_text} ({zone_text})." if cue_text else f"Active zones: {zone_text}."
    if hunger:
        feels += f" Hunger: {hunger}/100."
    if fatigue:
        feels += f" Physical fatigue: {fatigue}/100."
    if sleep_debt:
        feels += f" Sleep debt: {sleep_debt}/100."
    if exhaustion:
        feels += f" Exhaustion: {exhaustion}/100."
    if exposure_feels:
        feels += " " + " ".join(exposure_feels)
    if visceral_revulsion >= 50:
        feels += " The stomach turns."
    if sexual_arousal:
        feels += f" Sexual arousal: {sexual_arousal}/100."
    if involuntary_response == "freeze":
        feels = f"The body freezes involuntarily. {feels}"
    elif involuntary_response == "brace":
        feels = f"The body braces involuntarily. {feels}"
    rationalization = f"I am addressing what is in front of me through {state['active_focus']}."
    if closed_account:
        visceral_truth = "Account stays closed; others' hesitation is read as leverage or weakness."
        rationalization = "I am simply naming what is obvious and keeping the room moving."
    elif bias_state == "DEFENSIVE_ACTIVE":
        visceral_truth = f"Pressure against {wound or 'personal boundaries'} registers as exposure or loss of footing."
    elif bias_state == "GENERATIVE_ACTIVE":
        visceral_truth = f"Anchored in {gift or 'the present moment'}; attention stays clear without forcing control."
    else:
        visceral_truth = f"Baseline {state['active_focus']} awareness; {wound or 'the defensive response'} stays unactivated."

    snapshot = {
        "character_id": state["character_id"],
        "timestamp_or_movement": event_label,
        "autonomic_state": {
            "endocrine_state": {"estradiol": profile["estradiol"], "testosterone": profile["testosterone"],
                                "cortisol": clamp(cortisol)},
            "somatic_telemetry": somatic_telemetry(
                profile, arousal, max(stress, cortisol - 15), cortisol, exertion, fatigue,
                max(sexual_arousal, release["reward"], exposure_state["heat_discomfort"]),
            ),
            "polyvagal_mode": polyvagal_mode,
            "cognitive_regime": cognitive_regime,
            "arousal": arousal,
            "sexual_drive": clamp(drive_level),
            "sexual_excitation": clamp(excitation),
            "sexual_inhibition": clamp(inhibition),
            "sexual_arousal": sexual_arousal,
            "visceral_revulsion": visceral_revulsion,
            "stress": stress,
            "fatigue": fatigue,
            "sleep_debt": sleep_debt,
            "exhaustion": exhaustion,
            "activity": activity,
            "exertion": exertion,
            "hunger": hunger,
            **exposure_state,
            "physical_pain": physical_pain,
            "emotional_distress": emotional_distress,
            "physical_pain_tolerance": physical_pain_tolerance,
            "emotional_distress_tolerance": emotional_distress_tolerance,
            "primary_somatic_zones": zones,
            "somatic_map": mapped_body,
            "autonomic_surge": autonomic_surge,
            "involuntary_response": involuntary_response,
        },
        "affective_state": {
            "initiative": clamp(pursuit - exhaustion * 0.25),
            "release_state": {key: clamp(value) for key, value in release.items()},
            "emotions": emotions,
            "primary_emotion": primary_emotion,
            "secondary_emotion": secondary_emotion,
            "emotional_intensity": emotional_intensity,
            "impulse": impulse,
        },
        "subconscious_bias": {
            "active_wound": state["cognitive_bias"],
            "active_gift": state["cognitive_gift"],
            "bias_state": bias_state,
            "perceptual_warp": f"Filters stimulus through {state['active_focus']} ({bias_state}).",
            "subconscious_visceral_truth": state.get("subconscious_visceral_truth") or visceral_truth,
            "conscious_rationalization": state.get("conscious_rationalization") or rationalization,
            "defense_posture": defense_posture,
        },
        "social_mask": {
            "facade_type": state["social_facade"],
            "mask_strain": mask_strain,
            "mask_fracture": mask_fracture,
            "fracture_tell": cue_text if mask_strain >= 30 and cue_text else "none",
        },
        "relational_vectors": {
            target: {
                "intimacy": clamp(stimulus.get("willingness_to_be_seen",
                                      bond.get("emotional_safety", 0) - threat * 0.5
                                      - unease * 0.25 - bond.get("resentment_friction", 0) * 0.25)),
                "emotional_safety": clamp(bond.get("emotional_safety", 60)),
                "attraction_physical": phys_attr,
                "attraction_emotional": emot_attr,
                "respect_competence": clamp(bond.get("respect_competence", 45)),
                "status_dynamic": status_dynamic,
                "resentment_friction": clamp(int(bond.get("resentment_friction", 0)) + int(0.3 * threat)),
                "relational_momentum": momentum,
            }
        },
        "priority_arbitration": {
            "winning_drive": winning_drive,
            "salience_score": salience_score,
            "arbitration_status": arbitration_status,
            "internal_friction": internal_friction,
            "competing_drives": drives,
        },
        "output_vector": {"feels": feels},
    }

    schema = validate_state.load_json(SCHEMA_PATH)
    schema_errors = validate_state.validate(snapshot, schema)
    if schema_errors:
        raise RuntimeError(f"Golem produced invalid snapshot: {schema_errors}")

    recalled = recall_memories(state.get("memories", {}), stimulus.get("memory_cues", []))
    recent_inquiries = history.get("recent_inquiries", [])
    guarded = cognitive_regime == "reactive" or stress >= 40
    intent = conversation_intent(
        stimulus.get("conversation", {}), interest, guarded, guarded or arousal >= 40,
        target, recent_inquiries,
    )
    if intent and intent["intent"] == "ask":
        recent_inquiries = (recent_inquiries + [[target, intent["topic"].casefold()]])[-10:]

    return {
        "psychosomatic_snapshot": snapshot,
        "golem_meta": {
            "triggered_rules": rules,
            "emitted_cues": somatic_cues,
            "pressure_tier": pressure_tier,
            "time_pressure": time_pressure,
            "response_time_ms": response_time_ms,
            "elapsed_ms": elapsed_ms,
            "commit_eligible": commit_eligible,
        },
        "next_history": {
            "character_id": state["character_id"],
            **clock_state,
            "release_state": release,
            "cortisol": cortisol,
            "felt_emotions": felt,
            "last_fatigue": fatigue_level,
            "sleep_debt": sleep_debt_level,
            "activity": activity,
            "exertion": exertion,
            "hunger": hunger_level,
            **exposure_history,
            "physical_pain": physical_pain_level,
            "emotional_distress": emotional_distress_level,
            "recent_cues": (recent_cues + somatic_cues)[-10:],
            "sexual_drive": drive_level,
            "sexual_excitation": excitation,
            "sexual_inhibition": inhibition,
            "minutes_asleep": minutes_asleep,
            "arousal": activation,
            "sexual_arousal": sexual_response,
            "appraisal_effects": appraisal_effects,
            **({"recent_inquiries": recent_inquiries} if recent_inquiries else {}),
        },
        **({"current_goals": state["current_goals"]} if state.get("current_goals") else {}),
        **({"recalled_memories": recalled} if recalled else {}),
        **({"conversation_intent": intent} if intent else {}),
    }


def record_pressure_commit(log_data: dict[str, Any], output: dict[str, Any]) -> None:
    meta = output["golem_meta"]
    snap = log_data.setdefault("snapshot", {})
    auto = output["psychosomatic_snapshot"]["autonomic_state"]
    if auto["stress"] >= 65:
        snap["bias_strength"] = clamp(int(snap.get("bias_strength", 80)) - 2)
    log_data.setdefault("history", []).append({
        "movement": output["psychosomatic_snapshot"]["timestamp_or_movement"],
        "pressure": f"Golem/{meta['pressure_tier']}",
        "delta": "bias_strength -2" if auto["stress"] >= 65 else "none",
        "permanence": "temporary" if meta["pressure_tier"] == "Medium" else "permanent",
        "notes": f"Rules: {', '.join(meta['triggered_rules'][:4])}",
    })


def replace_text(path: Path, text: str) -> None:
    path = path.resolve()
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as stream:
            pending = Path(stream.name)
            stream.write(text)
        if path.exists():
            pending.chmod(path.stat().st_mode & 0o777)
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


@contextmanager
def locked_file(path: Path):
    path = path.resolve()
    lock = path.with_name(path.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError(f"File is locked: {lock}") from exc
    try:
        yield
    finally:
        lock.rmdir()


@contextmanager
def locked_log(log_path: Path):
    with locked_file(log_path):
        yield yaml.safe_load(log_path.read_text(encoding="utf-8")) or {}


def update_log(
    log_path: Path, output: dict[str, Any] | None = None, *,
    commit: bool = False, force: bool = False, memory: dict[str, Any] | None = None,
    character_id: str | None = None,
) -> tuple[bool, bool]:
    commit_pressure = output is not None and (force or (commit and output["golem_meta"]["commit_eligible"]))
    if not commit_pressure and memory is None:
        return False, False

    with locked_log(log_path) as log_data:
        if character_id is not None and log_data.get("character_id") != character_id:
            raise ValueError("Character ID mismatch when saving the durable log")
        if output is not None and log_data.get("character_id") not in (None, output["psychosomatic_snapshot"]["character_id"]):
            raise ValueError("Character ID mismatch when saving the durable log")
        saved_memory = memory is not None and add_memory(log_data, memory)
        if commit_pressure:
            record_pressure_commit(log_data, output)
        if saved_memory or commit_pressure:
            replace_text(log_path, yaml.safe_dump(log_data, sort_keys=False))
        return commit_pressure, saved_memory


def main() -> int:
    if sys.argv[1:2] == ["loop"]:
        import golem_loop

        return golem_loop.main(sys.argv[2:])
    parser = argparse.ArgumentParser(description="Simulacra Golem Engine")
    parser.add_argument("--card", help="Path to a YAML character card (required for a tick)")
    parser.add_argument("--slug", default=None, help="Character slug for multi-character cards")
    parser.add_argument("--log", default=None, help="Path to durable *_log.yaml")
    parser.add_argument("--stimulus", help="JSON string or path to stimulus JSON (required for a tick)")
    parser.add_argument("--history-file", default=None, help="Optional JSON history for state carried between ticks")
    parser.add_argument("--out", default=None, help="Path to write full output JSON (and *_snapshot.json)")
    parser.add_argument("--commit", action="store_true", help="Commit to --log if pressure >= Medium")
    parser.add_argument("--force-commit", action="store_true", help="Force commit to --log")
    parser.add_argument("--remember", type=Path, help="Save an approved memory from a JSON file to --log")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else None
    if (args.commit or args.force_commit or args.remember) and not log_path:
        parser.error("--commit, --force-commit, and --remember require --log")
    memory = None
    if args.remember:
        if not log_path.is_file():
            parser.error("--remember requires an existing character log")
        memory = json.loads(args.remember.read_text(encoding="utf-8"))
        if not isinstance(memory, dict):
            parser.error("--remember requires a JSON object")
        if not any((args.card, args.stimulus, args.slug, args.history_file, args.out, args.commit, args.force_commit)):
            _, saved_memory = update_log(log_path, memory=memory)
            print(json.dumps({"memory_saved": saved_memory}))
            return 0

    if not args.card or args.stimulus is None:
        parser.error("A tick requires both --card and --stimulus")
    card = load_character(Path(args.card), args.slug)
    state, _ = overlay_log(card, log_path)

    stim_path = Path(args.stimulus)
    stimulus = json.loads(stim_path.read_text(encoding="utf-8")) if stim_path.is_file() else json.loads(args.stimulus)

    hist_path = Path(args.history_file) if args.history_file else None
    out_path = Path(args.out) if args.out else None
    snapshot_path = out_path.with_name(out_path.stem + "_snapshot.json") if out_path else None
    paths = [path.resolve() for path in (Path(args.card), log_path, hist_path, out_path, snapshot_path) if path]
    if len(paths) != len(set(paths)):
        parser.error("Card, log, history, output, and snapshot paths must be distinct")
    history = json.loads(hist_path.read_text(encoding="utf-8")) if (hist_path and hist_path.is_file()) else {}

    realm_data = yaml.safe_load(REALM_DATA_PATH.read_text(encoding="utf-8"))
    result = run_golem(state, stimulus, realm_data, history)

    if log_path:
        committed, saved_memory = update_log(
            log_path, result, commit=args.commit, force=args.force_commit, memory=memory,
        )
        if args.commit or args.force_commit:
            result["golem_meta"]["committed_to_log"] = committed
        if args.remember:
            result["golem_meta"]["memory_saved"] = saved_memory

    if hist_path:
        replace_text(hist_path, json.dumps(result["next_history"], indent=2))

    if out_path and snapshot_path:
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        snapshot_path.write_text(json.dumps(result["psychosomatic_snapshot"], indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
