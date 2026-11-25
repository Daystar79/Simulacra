"""Filesystem entry points shared by the Golem modules."""
from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

ROOT = Path(__file__).resolve().parents[1]
REALM_DATA_PATH = ROOT / "Framework" / "Psychology" / "realm_data.yaml"
SCHEMA_PATH = ROOT / "Framework" / "Schemas" / "psychosomatic_state.json"
