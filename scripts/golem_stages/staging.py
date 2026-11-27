"""Classify pressure and resolve the active focus for drive arbitration.

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


from golem_somatic import parse_realm_num




def stage_staging(t):
    t.tier = "macro" if t.stress >= 65 else ("moderate" if t.stress >= 35 else "micro")
    t.active_realm_key = parse_realm_num(t.state["active_focus"])
