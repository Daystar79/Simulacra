# Simulacra on Muse.AI

Use the existing Simulacra Python CLI and persistent SQLite loop. Muse.AI is a scheduled cognitive host, not a second Golem implementation. Read the full setup guide at [INSTALLATION.md](INSTALLATION.md).

## Fixed runtime paths

Default checkout: `~/workspace/repos/Simulacra`. Override with `SIMULACRA_DIR` if the checkout is elsewhere. Store each character's database, card, durable memory/log, and any required runtime files under persistent `~/workspace` paths. Never place character state under `/tmp`, the repository checkout, or an ephemeral VM filesystem.

```bash
SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
CHARACTER_DIR="$HOME/workspace/simulacra/characters/CHARACTER_ID"
DB="$CHARACTER_DIR/runtime.sqlite3"
CARD="$CHARACTER_DIR/character.yaml"
LOG="$CHARACTER_DIR/character_log.yaml"
```

Keep a single persistent SQLite database per character. Python 3 and PyYAML are required. Do not run an always-on Python service; use Muse scheduled agent jobs to invoke discrete CLI operations.

## Install once

```bash
mkdir -p "$CHARACTER_DIR"
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" init \
  --card "$CARD" --log "$LOG" --idle-seconds 3600
```

Omit `--log` if no durable log exists. The card and log must themselves live under persistent storage. Do not overwrite an existing database; `init` is for first provisioning only.

## Scheduled cognitive wake

Create a Muse scheduled agent job at the desired cadence. Each job runs the following sequence and uses its LLM reasoning to decide the pending character turn:

```bash
SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
DB="$HOME/workspace/simulacra/characters/CHARACTER_ID/runtime.sqlite3"
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" run --once
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" pending
```

If `run --once` returns `{"status":"sleeping"}`, there is no due work. If it returns a pending event, read the `pending` request and use Simulacra's cognitive pipeline and full character card/log context to select a response, action, or no action. Return a JSON decision with the exact pending event ID. Do not invent bodily values: Golem's `tick` is the deterministic source of physiological state. Respect `behavior_guidance`, goals, commitments, and actual host capabilities/resources.

## Render the character, not the diagnostics

Build the response through the four Simulacra channels, then render them as natural behavior:

- **Feels:** use materially relevant current bodily state and current-event somatic cues to shape delivery, pacing, posture, or an observable bodily tell. Translate diagnostic values into behavior; never print raw scales or engine labels to the user.
- **Thinks:** use the character's private appraisal and reasoning to decide what matters. Keep it private unless the established format or character intentionally expresses it.
- **Says:** preserve the character's selected spoken intent and voice in `decision.reply`.
- **Does:** include deliberate physical action when the character chooses one. Keep this distinct from an involuntary reflex already underway.

Use only bodily state that materially affects this beat. A dialogue-only response is correct when the body adds nothing relevant; do not force a cue into every reply. `tick.golem_meta.emitted_cues` are the current tick's cues for interpretation, not mandatory text to reproduce. Carried `recent_cues`/recent event history prevents stale cues from being mistaken for actions happening now. A historical cue is not evidence that the character moved or spoke in the current event.

Keep `triggered_rules`, numerical scales, arbitration scores, and internal labels as framework diagnostics. Read them to guide the cognitive decision; do not expose them as observable acts or quote them in character prose. Use `tick.output_vector.feels`, current snapshot fields, and current `golem_meta.emitted_cues` as inputs to interpretation. Muse supplies the character-specific `Thinks`, `Says`, and `Does`; do not claim Golem generated those channels.

For `autonomic_state.involuntary_response`, distinguish an already-started reflex (such as bracing or freezing) from a deliberate `Does` choice. Render the reflex as bodily behavior without attributing conscious intent to it; Simulacra may still select a separate deliberate action afterward.

See [rendering regression examples](rendering-regressions.md) for dialogue-only, fatigue, hunger, and involuntary-response cases.

Resolve the decision through the same CLI. Stdin is accepted as `-`, so no transient decision file is required:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" resolve - <<'JSON'
{"id":"PENDING_EVENT_ID","action":"Chooses to continue working for now."}
JSON
```

Use the same event ID for retries. A pending request survives VM replacement; inspect it with `pending` and resolve that request before invoking another wake. A repeated identical resolution is idempotent. Do not deliver messages or repeat external tool effects unless the event is resolved, and deduplicate those effects by character plus event ID.

After CLI resolution, preserve the accepted reply exactly. `resolve` stores the approved text in the event decision; retrieve it with `timeline --limit 1` and deliver that `decision.reply` byte-for-byte. Do not draft, paraphrase, or re-render a second reply after resolution. If the decision omitted `reply`, deliver no character message.

## Duration-based maintenance activity

Golem persists activity ID, kind, status, state, start/due/end timestamps, event IDs, and revision in the same SQLite database. A selected activity creates one scheduled due event. The duration's physiological progression is calculated by Golem from elapsed event time; no per-minute LLM calls are needed. Completion, interruption, and resumption are recorded transactionally with the decision and bodily transition.

After checking a real resource is available, a character may choose a meal. For a 20-minute meal, start with the delayed intake effect stored for completion:

```json
{"id":"PENDING_EVENT_ID","action":"Starts a meal.","activity":{"op":"start","id":"meal:PENDING_EVENT_ID","kind":"meal","state":"awake","duration_seconds":1200,"data":{"effects":{"food_intake":30}}}}
```

At the due event, the character decides whether to complete or extend it. Completion applies the stored meal effect once:

```json
{"id":"DUE_EVENT_ID","action":"Finishes the meal.","activity":{"op":"complete","id":"meal:PENDING_EVENT_ID","state":"awake"}}
```

For sleep, start a duration activity in `sleeping` state; Golem applies sleep recovery over elapsed time. At the due event, Simulacra decides whether to wake (`complete` with `state: awake`) or extend (`extend` plus a new positive `duration_seconds`). If an incoming event interrupts an activity, resolve with `op: interrupt`; to continue later, choose `op: resume` with a new duration. The loop cancels the old due event and schedules a revision-specific one. Completed and interrupted activities remain in the status history.

No state transition occurs from a bare prose plan: use the structured `activity` field. Missing food, water, or host tools must be reported to Simulacra; the engine does not manufacture resources. Hydration has no physiological model in this runtime.

## Restart, inspect, diagnose

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" status
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" pending
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" timeline --limit 100
```

At a VM replacement, use the same checkout path (or update `SIMULACRA_DIR`) and persistent database path. The SQLite queue restores active/due activities and pending cognitive requests. Never initialize a replacement database over the existing one. Never substitute LLM estimates for Golem CLI output; if Python, PyYAML, or the checkout is unavailable, report the execution failure and retry after the capability is restored.
