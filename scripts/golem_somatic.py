"""Somatic cue staging and body-region mapping.

Realm-catalog cue selection (non-repeating, deterministic by event seed), the
six coarse somatic zones with their region map, and localized arousal and body
sensation mapping. No physiological state lives here.
"""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import hashlib
import re
from typing import Any

from golem_physiology import GENITAL_RESPONSE_SITES, clamp


ZONE_MAP = {
    "Z1": "Z1_Cranial_Ocular",
    "Z2": "Z2_Vocal_Cervical",
    "Z3": "Z3_Thoracic_Respiratory",
    "Z4": "Z4_Abdominal_Visceral",
    "Z5": "Z5_Pelvic_Kinesthetic",
    "Z6": "Z6_Peripheral_Grounding",
}


def parse_realm_num(focus_str: str) -> str:
    m = re.search(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X)\b", str(focus_str))
    return m.group(1) if m else "X"



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
    # Prefer fresh cues from the current tier so low-stress ticks don't emit
    # macro-tier cues; expand to other tiers only when the tier's fresh cues
    # are exhausted.
    tier_pool = [c for c in r.get(tier, []) if c not in excluded]
    pool = list(tier_pool)
    for other_tier in ("micro", "moderate", "macro"):
        if other_tier != tier:
            pool.extend(c for c in r.get(other_tier, []) if c not in excluded and c not in pool)
    if not pool:
        return []
    fresh = [c for c in tier_pool if c not in recent_cues]
    if not fresh:
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

