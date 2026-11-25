"""Applies subconscious bias, social mask strain, and drive
priority arbitration with the time-based tiebreakers.

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
from typing import Any

from golem_physiology import clamp




def stage_arbitration(t):
    # 3. Subconscious Bias & Defense Posture
    if t.threat >= 30 or t.latent_hit_bonus >= 12 or t.unease >= 45 or t.stress >= 45:
        t.bias_state = "DEFENSIVE_ACTIVE"
        t.defense_posture = t.state["defense_posture"]
        t.rules.append("BIAS_DEFENSIVE_ACTIVE")
    elif (
        t.interest >= 35
        or t.release["reward"] >= 30
        or t.release["settling"] >= 30
        or t.attraction >= 25
        or t.active_realm_key in t.realm_hits
    ):
        t.bias_state = "GENERATIVE_ACTIVE"
        t.defense_posture = "none"
        t.rules.append("BIAS_GENERATIVE_ACTIVE")
    else:
        t.bias_state = "DORMANT"
        t.defense_posture = "none"
        t.rules.append("BIAS_DORMANT")

    # 4. Social Masking & Strain
    t.mask_strain = clamp(int(0.6 * t.stress) + int(0.25 * t.latent_hit_bonus) - int(0.1 * t.state["flexibility"]))
    t.mask_fracture = t.mask_strain >= 75 or t.cognitive_regime == "reactive"
    if t.mask_fracture:
        t.rules.append("MASK_FRACTURE_TRUE")

    # 5. Priority Arbitration (with time-based body vs mind tiebreaker)
    t.drives: list[dict[str, Any]] = []
    if t.context == "broadcast" and t.state.get("broadcast_persona"):
        t.drives.append({"drive_name": "broadcast_entertainment_control", "circuit": "mind", "salience": clamp(88 - int(0.45 * t.stress))})
    t.drives.append({"drive_name": f"realm_{t.active_realm_key}_containment", "circuit": "body", "salience": clamp(45 + int(0.4 * t.state["bias_strength"]) + int(0.3 * t.latent_hit_bonus))})
    t.intake_boost = int(0.2 * max(t.interest, t.release["reward"]))
    t.drives.append({"drive_name": "warm_presence_and_intake", "circuit": "mind", "salience": min(74, clamp(62 - int(0.3 * t.threat) + t.intake_boost))})
    t.wound = str(t.state.get("cognitive_bias") or "").split("—", 1)[0].strip().rstrip(".")
    t.gift = str(t.state.get("cognitive_gift") or "").split("—", 1)[0].strip().rstrip(".")
    t.closed_account = t.wound.startswith("Closed Account")
    if t.bias_state == "DEFENSIVE_ACTIVE":
        t.wound_slug = re.sub(r"[^a-z0-9]+", "_", t.wound.casefold()).strip("_")
        t.defensive_drive = f"defend_{t.wound_slug}" if t.wound_slug else "self_protection"
        if t.closed_account:
            t.defensive_drive = "deflect_and_protect_closed_file"
        t.drives.append({"drive_name": t.defensive_drive, "circuit": "body", "salience": clamp(55 + int(0.4 * t.threat))})

    t.drives.sort(key=lambda d: d["salience"], reverse=True)
    if len(t.drives) > 1 and abs(t.drives[0]["salience"] - t.drives[1]["salience"]) <= 5:
        t.c0, t.c1 = t.drives[0]["circuit"], t.drives[1]["circuit"]
        if t.c0 != t.c1:
            if t.time_pressure == "split_second" and t.c1 == "body":
                t.drives[0], t.drives[1] = t.drives[1], t.drives[0]
                t.rules.append("TIME_TIEBREAKER:SPLIT_SECOND->BODY")
            elif t.time_pressure == "deliberate" and t.c1 == "mind":
                t.drives[0], t.drives[1] = t.drives[1], t.drives[0]
                t.rules.append("TIME_TIEBREAKER:DELIBERATE->MIND")

    # Strip internal circuit tag before schema validation
    for t.d in t.drives:
        t.d.pop("circuit", None)

    t.winning_drive = t.drives[0]["drive_name"]
    t.salience_score = t.drives[0]["salience"]
    t.internal_friction = clamp(abs(t.drives[0]["salience"] - t.drives[1]["salience"]) if len(t.drives) > 1 else 0)
    t.internal_friction = clamp(100 - t.internal_friction) if len(t.drives) > 1 and t.drives[1]["salience"] >= 60 else clamp(int(0.4 * t.stress) + int(0.3 * t.latent_hit_bonus))
    t.arbitration_status = "bypassed_reactive" if t.cognitive_regime == "reactive" else "arbitrated"
    if (t.urge and t.cognitive_regime != "reactive" and t.urge["strength"] >= 75
            and t.urge["strength"] > t.salience_score and t.time_pressure != "deliberate"):
        t.arbitration_status = "impulse_override"
        t.winning_drive, t.salience_score = t.impulse, t.urge["strength"]
    t.rules.append(f"ARBITRATION:{t.arbitration_status}:{t.winning_drive}")
