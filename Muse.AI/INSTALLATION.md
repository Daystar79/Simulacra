# Muse.AI installation and scheduled execution

This configures Muse.AI as a host for the existing Simulacra/Golem runtime. It does not add another runtime, keep a Python daemon alive, or require a remote service.

## 1. Persistent locations

Muse's audited persistent workspace is `~/workspace`. Use this default checkout unless the repository is installed elsewhere:

```bash
export SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
export SIMULACRA_DATA="$HOME/workspace/simulacra"
export CHARACTER_ID="rowan"
export CHARACTER_DIR="$SIMULACRA_DATA/characters/$CHARACTER_ID"
export DB="$CHARACTER_DIR/runtime.sqlite3"
export CARD="$CHARACTER_DIR/character.yaml"
export LOG="$CHARACTER_DIR/character_log.yaml"
```

Override only `SIMULACRA_DIR` for a different checkout. Keep the DB, copied character card, durable memory/log, and any other data needed after replacement under `~/workspace`. The repository itself can be recloned or replaced; the DB and canon data must not be stored in it.

## 2. Install the skill instructions and character files

Load `Muse.AI/SKILL.md` as the Muse agent's Simulacra skill/instructions. Configure the scheduled agent to use the character's existing Simulacra card, log, goals, and character context. Copy existing files without editing canon:

```bash
mkdir -p "$CHARACTER_DIR"
cp /path/to/existing/character.yaml "$CARD"
cp /path/to/existing/character_log.yaml "$LOG"  # omit only when no log exists
```

Install Python 3, PyYAML, and the Simulacra checkout. Verify the CLI:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --help
```

Initialize a new character DB once:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" init \
  --card "$CARD" --log "$LOG" --idle-seconds 3600
```

Do not run `init` against an existing DB. Omit `--log` only if no durable character log is configured.

## 3. Configure scheduled agent jobs

Create a Muse scheduled agent job using the LLM-enabled agent, with a 1-hour cadence to match the example `--idle-seconds 3600` (or set both values to the desired cadence). Set the job's instructions to follow `Muse.AI/SKILL.md` and this execution sequence:

```bash
SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
DB="$HOME/workspace/simulacra/characters/rowan/runtime.sqlite3"
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" run --once
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" pending
```

The scheduled agent should then:

1. If the first JSON result is `status: sleeping`, finish this job with no action.
2. If pending work exists, read the pending request. Use its event ID, deterministic `tick`, active activity, needs, goals, card/log context, and recent history as inputs to the Simulacra cognitive decision.
3. Check real Muse/host capabilities and resources. If an action can't be done, report that limitation in the decision so the character can respond to it.
4. Select `Thinks`, `Says`, and `Does` from the character's cognition. Let materially relevant current `Feels` affect delivery, pace, posture, or an observable tell, then render the result naturally. Keep thought private unless intentionally expressed; do not render raw numbers, framework labels, every cue, or old `recent_cues` as current behavior. Keep involuntary reflexes distinct from deliberate actions. A response can be dialogue-only when body state does not materially affect it. For duration activities, use the structured `activity` contract in the skill file. Do not calculate physiology in the LLM.
5. Resolve exactly the pending event via stdin:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" resolve - <<'JSON'
{"id":"EVENT_ID_FROM_PENDING","action":"Character-selected action or no action."}
JSON
```

6. If a `reply` was included, fetch the just-resolved event using `timeline --limit 1` and deliver its stored `decision.reply` exactly as accepted. Do not regenerate or paraphrase it after resolution; omit delivery when no reply was accepted.

The scheduled LLM job is the cognitive wake. `run --once` advances Golem deterministically and stores a pending request before cognitive work. `resolve` persists the selected result. Do not launch an always-running process; scheduled jobs can resume the DB after a VM replacement.

## 4. Incoming messages

The Muse messaging integration should pass messages to the same persistent loop using `wake_character` if a Python callback is available, or enqueue an event with a stable transport message ID and run the same scheduled cognitive resolution workflow. For CLI enqueue, write a JSON object under a persistent character directory and call:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" enqueue "$CHARACTER_DIR/incoming.json"
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" run --once
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" pending
```

Example incoming object: `{"id":"transport-message-123","kind":"incoming","context":"Message text"}`. Deliver a reply or execute an external side effect only after resolution; deduplicate it by character and event ID. If the host uses boundary screening or any existing message policy, preserve it in this path.

For runtimes configured with registered owned files and boundary screening, do not use raw CLI `enqueue` for incoming events: the existing guard requires the host's `wake_character(..., screen_abuse=...)` callback. Keep that screening in the Muse integration or use the host's established incoming-message adapter.

## 5. VM replacement recovery

After replacement, use the same persistent DB and scheduled job. Check runtime state:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" status
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" pending
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --db "$DB" timeline --limit 100
```

An unresolved pending request is returned unchanged. Active or due activities and their original timestamps/event IDs are stored in SQLite. Resolve a pending request before asking for another wake. If no request is pending, `run --once` processes the next due plan or idle wake. Activity start/completion/interruption and Golem state changes share a DB transaction; duplicate resolution of the same event ID does not apply consequences again. The runtime migrates older databases by creating its activity table without replacing existing state.

## 6. Deterministic runtime boundary

Use `python3 "$SIMULACRA_DIR/scripts/run.py" golem ...` for all body updates. The Python CLI wrapper locates files relative to its installation and emits structured JSON. A scheduled LLM may interpret the result and select behavior; it must never substitute prose, arithmetic, or guessed values for Golem. If the checkout, Python, or PyYAML is unavailable, report a runtime capability error and retry after it is restored.

For command details, activity operations, JSON fields, calibration, and limitations, read [../SKILL.md](../SKILL.md).

## Reload after this update

After installing the revised Muse skill, reload or reselect `Muse.AI/SKILL.md` in Muse and restart the active hosting session so its renderer instructions are refreshed. Update the scheduled job's instruction reference if it copied an older prompt. This is an instruction-only change: it requires no character DB migration, no Golem restart, and no edits to cards or logs.
