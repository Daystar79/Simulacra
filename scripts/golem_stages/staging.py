"""Selects the somatic tier, the realm cue catalog output, and the
starting zone list for this tick.

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


from golem_somatic import parse_realm_num, select_somatic_cues




def stage_staging(t):
    # Tier & Somatic lookup
    t.tier = "macro" if t.stress >= 65 else ("moderate" if t.stress >= 35 else "micro")
    t.active_realm_key = parse_realm_num(t.state["active_focus"])
    t.hit_realm_key = max(t.realm_hits, key=lambda k: t.realm_hits[k]) if t.realm_hits else t.active_realm_key
    t.seed = f"{t.state['character_id']}:{t.event_label}:{len(t.recent_cues)}"
    t.extra_excl = set(t.state.get("excluded_cues", set()))
    if t.state.get("conversational_stance") == "dominant":
        t.extra_excl.add("scan eyes for approval")
    t.somatic_cues = select_somatic_cues(t.realm_data, t.hit_realm_key, t.tier, t.recent_cues, t.seed, exclude_extra=t.extra_excl)
    t.rules.append(f"SOMATIC_CATALOG:{t.hit_realm_key}:{t.tier}")

    t.zones = ["Z2_Vocal_Cervical", "Z6_Peripheral_Grounding"]
    if t.tier in ("moderate", "macro"):
        t.zones.insert(0, "Z1_Cranial_Ocular")
    if t.stress >= 40:
        t.zones.append("Z3_Thoracic_Respiratory")
