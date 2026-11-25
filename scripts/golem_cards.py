"""Character card hydration: defaults, validation, and durable-log overlay.

Reads character cards without rewriting them during live wakes, insert
defaults for legacy cards, and overlay the durable log snapshot onto the
hydrated state. Produces the read-only state consumed by a Golem tick.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from golem_logs import locked_file, replace_text
from golem_physiology import (DEFAULT_PHYSIOLOGY_CALIBRATION, arousal_regions,
                              card_age, clamp, physiology_calibration,
                              somatic_profile)
from goal_evolution import current_goals


# Only persist defaults that are character-neutral or already used by the runtime.
CARD_DEFAULTS = {
    "biological_sex": "unspecified", "somatic_baselines": {}, "arousal_regions": None,
    "pleasure_sources": [], "physical_pleasure_sources": [], "sexual_pleasure_sources": [],
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
        "age": card_age(card),
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

