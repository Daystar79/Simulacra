#!/usr/bin/env python3
"""Validate a psychosomatic state JSON against Framework/Schemas/psychosomatic_state.json.

Uses the stdlib only (no jsonschema dependency). Checks required keys, basic types,
and 0–100 integer ranges for known autonomic/relational scales.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "Framework" / "Schemas" / "psychosomatic_state.json"
EXAMPLE = ROOT / "Framework" / "Schemas" / "examples" / "psychosomatic_state.example.json"

SCALE_PATHS = [
    ("autonomic_state", "arousal"),
    ("autonomic_state", "stress"),
    ("autonomic_state", "fatigue"),
    ("autonomic_state", "pain"),
    ("affective_state", "emotional_intensity"),
    ("priority_arbitration", "salience_score"),
]


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def require_keys(obj: dict, keys: list[str], path: str, errors: list[str]) -> None:
    for k in keys:
        if k not in obj:
            errors.append(f"{path}: missing required key '{k}'")


def check_scale(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{path}: expected integer 0–100, got {type(value).__name__}")
        return
    if value < 0 or value > 100:
        errors.append(f"{path}: {value} out of range 0–100")


def validate(state: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    top_required = schema.get("required", [])
    require_keys(state, top_required, "$", errors)

    props = schema.get("properties", {})

    # autonomic
    auto = state.get("autonomic_state")
    if isinstance(auto, dict):
        auto_schema = props["autonomic_state"]
        require_keys(auto, auto_schema.get("required", []), "autonomic_state", errors)
        pain_options = auto_schema.get("anyOf", [])
        if pain_options and not any(all(key in auto for key in option["required"]) for option in pain_options):
            errors.append("autonomic_state: expected physical pain, emotional distress, and both tolerances, or legacy pain")
        if "polyvagal_mode" in auto:
            allowed_pv = set(props["autonomic_state"]["properties"]["polyvagal_mode"].get("enum", []))
            if allowed_pv and auto["polyvagal_mode"] not in allowed_pv:
                errors.append(f"autonomic_state.polyvagal_mode: invalid value {auto['polyvagal_mode']!r}")
        if "cognitive_regime" in auto:
            allowed_cr = set(props["autonomic_state"]["properties"]["cognitive_regime"].get("enum", []))
            if allowed_cr and auto["cognitive_regime"] not in allowed_cr:
                errors.append(f"autonomic_state.cognitive_regime: invalid value {auto['cognitive_regime']!r}")
        for key, field_schema in auto_schema["properties"].items():
            if field_schema.get("type") == "integer" and key in auto:
                check_scale(auto[key], f"autonomic_state.{key}", errors)
            if field_schema.get("type") == "boolean" and key in auto and not isinstance(auto[key], bool):
                errors.append(f"autonomic_state.{key}: expected boolean")
        for key in ("endocrine_state", "somatic_telemetry"):
            if key not in auto:
                continue
            group = auto[key]
            fields = auto_schema["properties"][key]["required"]
            if not isinstance(group, dict) or set(group) != set(fields):
                errors.append(f"autonomic_state.{key}: expected fields {fields}")
                continue
            for field, value in group.items():
                check_scale(value, f"autonomic_state.{key}.{field}", errors)
        for key in ("involuntary_response", "activity"):
            options = auto_schema["properties"].get(key, {}).get("enum", [])
            if key in auto and options and auto[key] not in options:
                errors.append(f"autonomic_state.{key}: invalid value")
        if "primary_somatic_zones" in auto:
            zones = auto["primary_somatic_zones"]
            allowed_zones = set(props["autonomic_state"]["properties"]["primary_somatic_zones"]["items"].get("enum", []))
            if not isinstance(zones, list):
                errors.append("autonomic_state.primary_somatic_zones: expected array")
            else:
                if len(zones) < 2:
                    errors.append(f"autonomic_state.primary_somatic_zones: requires at least 2 body zones (got {len(zones)}) for multi-zone cascade")
                for z in zones:
                    if allowed_zones and z not in allowed_zones:
                        errors.append(f"autonomic_state.primary_somatic_zones: unknown zone {z!r}")
    elif "autonomic_state" in state:
        errors.append("autonomic_state: expected object")

    # affective
    aff = state.get("affective_state")
    if isinstance(aff, dict):
        require_keys(aff, props["affective_state"].get("required", []), "affective_state", errors)
        if "emotional_intensity" in aff:
            check_scale(aff["emotional_intensity"], "affective_state.emotional_intensity", errors)
    elif "affective_state" in state:
        errors.append("affective_state: expected object")

    # bias & inner split
    bias = state.get("subconscious_bias")
    if isinstance(bias, dict):
        require_keys(bias, props["subconscious_bias"].get("required", []), "subconscious_bias", errors)
        allowed_bias = set(props["subconscious_bias"]["properties"]["bias_state"].get("enum", []))
        if "bias_state" in bias and allowed_bias and bias["bias_state"] not in allowed_bias:
            errors.append(f"subconscious_bias.bias_state: invalid value {bias['bias_state']!r}")
        if "defense_posture" in bias:
            allowed_postures = set(props["subconscious_bias"]["properties"]["defense_posture"].get("enum", []))
            if allowed_postures and bias["defense_posture"] not in allowed_postures:
                errors.append(f"subconscious_bias.defense_posture: invalid value {bias['defense_posture']!r}")
    elif "subconscious_bias" in state:
        errors.append("subconscious_bias: expected object")

    # social mask
    mask = state.get("social_mask")
    if isinstance(mask, dict):
        require_keys(mask, props.get("social_mask", {}).get("required", []), "social_mask", errors)
        if "mask_strain" in mask:
            check_scale(mask["mask_strain"], "social_mask.mask_strain", errors)
        if "mask_fracture" in mask and not isinstance(mask["mask_fracture"], bool):
            errors.append("social_mask.mask_fracture: expected boolean")
        if "facade_type" in mask and not isinstance(mask["facade_type"], str):
            errors.append("social_mask.facade_type: expected string")
    elif "social_mask" in state:
        errors.append("social_mask: expected object")

    # relational vectors
    rel = state.get("relational_vectors")
    if isinstance(rel, dict):
        rel_props = props["relational_vectors"].get("additionalProperties", {}).get("properties", {})
        rel_req = props["relational_vectors"].get("additionalProperties", {}).get("required", [])
        for target, vec in rel.items():
            if not isinstance(vec, dict):
                errors.append(f"relational_vectors.{target}: expected object")
                continue
            require_keys(vec, rel_req, f"relational_vectors.{target}", errors)
            for scale in (
                "emotional_safety",
                "attraction_physical",
                "attraction_emotional",
                "respect_competence",
                "resentment_friction",
            ):
                if scale in vec:
                    check_scale(vec[scale], f"relational_vectors.{target}.{scale}", errors)
            if "status_dynamic" in vec and "status_dynamic" in rel_props:
                allowed_stat = set(rel_props["status_dynamic"].get("enum", []))
                if allowed_stat and vec["status_dynamic"] not in allowed_stat:
                    errors.append(f"relational_vectors.{target}.status_dynamic: invalid value {vec['status_dynamic']!r}")
            if "relational_momentum" in vec and "relational_momentum" in rel_props:
                allowed_mom = set(rel_props["relational_momentum"].get("enum", []))
                if allowed_mom and vec["relational_momentum"] not in allowed_mom:
                    errors.append(f"relational_vectors.{target}.relational_momentum: invalid value {vec['relational_momentum']!r}")
            if "perceived_reciprocity" in vec and isinstance(vec["perceived_reciprocity"], dict):
                prec = vec["perceived_reciprocity"]
                for pscale in ("perceived_liking", "perceived_threat"):
                    if pscale in prec:
                        check_scale(prec[pscale], f"relational_vectors.{target}.perceived_reciprocity.{pscale}", errors)
    elif "relational_vectors" in state:
        errors.append("relational_vectors: expected object")

    # priority arbitration
    pri = state.get("priority_arbitration")
    if isinstance(pri, dict):
        require_keys(pri, props["priority_arbitration"].get("required", []), "priority_arbitration", errors)
        if "salience_score" in pri:
            check_scale(pri["salience_score"], "priority_arbitration.salience_score", errors)
        if "arbitration_status" in pri:
            allowed_as = set(props["priority_arbitration"]["properties"]["arbitration_status"].get("enum", []))
            if allowed_as and pri["arbitration_status"] not in allowed_as:
                errors.append(f"priority_arbitration.arbitration_status: invalid value {pri['arbitration_status']!r}")
        if "internal_friction" in pri:
            check_scale(pri["internal_friction"], "priority_arbitration.internal_friction", errors)
        if "competing_drives" in pri:
            cdrives = pri["competing_drives"]
            if not isinstance(cdrives, list):
                errors.append("priority_arbitration.competing_drives: expected array")
            else:
                for idx, cd in enumerate(cdrives):
                    if not isinstance(cd, dict):
                        errors.append(f"priority_arbitration.competing_drives[{idx}]: expected object")
                    else:
                        if "salience" in cd:
                            check_scale(cd["salience"], f"priority_arbitration.competing_drives[{idx}].salience", errors)
                        if "drive_name" in cd and not isinstance(cd["drive_name"], str):
                            errors.append(f"priority_arbitration.competing_drives[{idx}].drive_name: expected string")
    elif "priority_arbitration" in state:
        errors.append("priority_arbitration: expected object")

    # output vector (optional but if present check channels)
    out = state.get("output_vector")
    if isinstance(out, dict):
        require_keys(out, props.get("output_vector", {}).get("required", []), "output_vector", errors)
        for ch in ("feels", "thinks", "says", "does"):
            if ch in out and not isinstance(out[ch], str):
                errors.append(f"output_vector.{ch}: expected string")
    elif "output_vector" in state:
        errors.append("output_vector: expected object")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "state_file",
        nargs="?",
        type=Path,
        default=EXAMPLE,
        help=f"Path to state JSON or directory containing JSON states (default: example at {EXAMPLE.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Path to schema JSON",
    )
    args = parser.parse_args(argv)

    if not args.schema.is_file():
        print(f"Schema not found: {args.schema}", file=sys.stderr)
        return 2

    schema = load_json(args.schema)

    if args.state_file.is_dir():
        files = [p for p in sorted(args.state_file.rglob("*.json")) if p.resolve() != args.schema.resolve()]
        if not files:
            print(f"No JSON files found in {args.state_file}")
            return 0
        total_errors = 0
        for f in files:
            try:
                state = load_json(f)
            except Exception as e:
                print(f"INVALID (JSON decode error: {e}) — {f}")
                total_errors += 1
                continue
            if not isinstance(state, dict):
                print(f"INVALID (root must be object) — {f}")
                total_errors += 1
                continue
            errors = validate(state, schema)
            if errors:
                print(f"INVALID ({len(errors)} issue(s)) — {f}")
                for e in errors:
                    print(f"  - {e}")
                total_errors += 1
            else:
                print(f"OK — {f}")
        return 1 if total_errors > 0 else 0

    if not args.state_file.is_file():
        print(f"State file not found: {args.state_file}", file=sys.stderr)
        return 2

    try:
        state = load_json(args.state_file)
    except Exception as e:
        print(f"INVALID (JSON decode error: {e}) — {args.state_file}")
        return 1
    if not isinstance(state, dict):
        print("State root must be a JSON object", file=sys.stderr)
        return 1

    errors = validate(state, schema)
    if errors:
        print(f"INVALID ({len(errors)} issue(s)) — {args.state_file}")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — {args.state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
