#!/usr/bin/env python3
"""
Simulacra Golem Engine (Layer 1-2 Runtime)
-------------------------------------------------------------
Public orchestrator of the deterministic body tick. The pipeline stages live
in golem_stages/ (intake, maintenance, autonomic, staging, affect,
arbitration, adult, presentation) and their leaf math in golem_physiology,
golem_time, golem_somatic, golem_memory, golem_cards, golem_logs, and
golem_paths. run_golem keeps its original signature and assembles the
schema-validated psychosomatic snapshot, triggered rules, and next_history.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import validate_state  # noqa: E402
from goal_evolution import current_goals  # noqa: E402

from golem_paths import ROOT, REALM_DATA_PATH, SCHEMA_PATH  # noqa: E402
from golem_physiology import (  # noqa: E402
    ACTIVATION_RECOVERY_MINUTES, ADULT_SEX_PROFILES, APPRAISAL_HALF_LIFE_SECONDS,
    APPRAISAL_SIGNALS, DEFAULT_AROUSAL_REGIONS, DEFAULT_PHYSIOLOGY_CALIBRATION,
    EMOTIONAL_DISTRESS_HALF_LIFE_MINUTES, EXPOSURE_RESPONSES,
    GENITAL_RESPONSE_SITES, PLEASURE_HALF_LIFE_MINUTES,
    PHYSICAL_PAIN_HALF_LIFE_MINUTES, SLEEP_PULSE_HALF_LIFE_MINUTES,
    SOMATIC_BASELINES, arousal_regions, biological_sex, canon_adult, card_age,
    clamp, combine_levels, felt_pleasure, physiology_calibration, recover_distress,
    sleep_excitation, somatic_profile, somatic_telemetry,
)
from golem_cards import (  # noqa: E402
    CARD_DEFAULTS, insert_card_defaults, load_character, migrate_character_card,
    missing_card_fields, overlay_log, selected_card,
)
from golem_memory import (  # noqa: E402
    add_memory, conversation_intent, cue_keys, recall_memories,
)
from golem_logs import (  # noqa: E402
    locked_file, locked_log, record_pressure_commit, replace_text, update_log,
)
from golem_time import event_clock, parse_event_time  # noqa: E402
from golem_somatic import (  # noqa: E402
    REGION_ZONE, RENDERING_CUES, SOMATIC_ZONES, ZONE_MAP, arousal_sensations,
    parse_realm_num, select_somatic_cues, somatic_map,
)
from golem_stages.intake import stage_intake  # noqa: E402
from golem_stages.maintenance import stage_maintenance  # noqa: E402
from golem_stages.autonomic import stage_autonomic  # noqa: E402
from golem_stages.staging import stage_staging  # noqa: E402
from golem_stages.affect import stage_affect  # noqa: E402
from golem_stages.arbitration import stage_arbitration  # noqa: E402
from golem_stages.adult import stage_adult  # noqa: E402
from golem_stages.presentation import stage_presentation  # noqa: E402

def run_golem(
    state: dict[str, Any],
    stimulus: dict[str, Any],
    realm_data: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    """Orchestrate one deterministic body tick over the shared tick context."""
    t = SimpleNamespace(state=state, stimulus=stimulus, realm_data=realm_data,
                        history=history)
    stage_intake(t)
    stage_maintenance(t)
    stage_autonomic(t)
    stage_staging(t)
    stage_affect(t)
    stage_arbitration(t)
    stage_adult(t)
    stage_presentation(t)
    return finalize_tick(t)



def finalize_tick(t):
    """Validate the snapshot, recall memory and conversation intent, and
    assemble the tick result exactly as the original run_golem tail."""
    t.schema = validate_state.load_json(SCHEMA_PATH)
    t.schema_errors = validate_state.validate(t.snapshot, t.schema)
    if t.schema_errors:
        raise RuntimeError(f"Golem produced invalid snapshot: {t.schema_errors}")

    t.recalled = recall_memories(t.state.get("memories", {}), t.stimulus.get("memory_cues", []))
    t.recent_inquiries = t.history.get("recent_inquiries", [])
    t.guarded = t.cognitive_regime == "reactive" or t.stress >= 40
    t.intent = conversation_intent(
        t.stimulus.get("conversation", {}), t.interest, t.guarded, t.guarded or t.arousal >= 40,
        t.target, t.recent_inquiries,
    )
    if t.intent and t.intent["intent"] == "ask":
        t.recent_inquiries = (t.recent_inquiries + [[t.target, t.intent["topic"].casefold()]])[-10:]

    return {
        "psychosomatic_snapshot": t.snapshot,
        "golem_meta": {
            "triggered_rules": t.rules,
            "emitted_cues": t.somatic_cues,
            "pressure_tier": t.pressure_tier,
            "time_pressure": t.time_pressure,
            "response_time_ms": t.response_time_ms,
            "elapsed_ms": t.elapsed_ms,
            "commit_eligible": t.commit_eligible,
        },
        "next_history": {
            "character_id": t.state["character_id"],
            **t.clock_state,
            "release_state": t.release,
            "cortisol": t.cortisol,
            "felt_emotions": t.felt,
            "last_fatigue": t.fatigue_level,
            "sleep_debt": t.sleep_debt_level,
            "activity": t.activity,
            "exertion": t.exertion,
            "hunger": t.hunger_level,
            **t.exposure_history,
            "physical_pain": t.physical_pain_level,
            "emotional_distress": t.emotional_distress_level,
            "recent_cues": (t.recent_cues + t.somatic_cues)[-10:],
            "sexual_drive": t.drive_level,
            "sexual_excitation": t.excitation,
            "sexual_inhibition": t.inhibition,
            "minutes_asleep": t.minutes_asleep,
            "arousal": t.activation,
            "sexual_arousal": t.sexual_response,
            "physical_pleasure": t.physical_pleasure,
            "sexual_pleasure": t.sexual_pleasure,
            "orgasm_recovery_minutes_left": t.recovery_minutes_left,
            **({"orgasm_recovery_duration": t.recovery_duration} if t.recovery_minutes_left > 0 else {}),
            "appraisal_effects": t.appraisal_effects,
            **({"recent_inquiries": t.recent_inquiries} if t.recent_inquiries else {}),
        },
        **({"current_goals": t.state["current_goals"]} if t.state.get("current_goals") else {}),
        **({"recalled_memories": t.recalled} if t.recalled else {}),
        **({"conversation_intent": t.intent} if t.intent else {}),
    }

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
