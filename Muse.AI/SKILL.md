# Simulacra on Muse.AI

Use the existing Simulacra Python CLI and persistent SQLite loop. Muse.AI is a scheduled cognitive host, not a second Golem implementation. Read the full setup guide at [INSTALLATION.md](INSTALLATION.md).

## Shared installation and private character directories

Use one Simulacra checkout on the VM. Bind each chat and scheduled job to its own stable character ID in the host configuration. Each character has a separate database, card, durable log, model conversation, and directory for any host-created transcripts, attachments or snapshots. Key delivery retries and any host caches by character ID as well as event ID. For scenes with multiple participants, forward only the speech and actions each participant can observe.

```bash
SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
CHARACTERS_DIR="$HOME/workspace/simulacra/characters"
# Example job binding. Set a different value in each character's job.
CHARACTER_ID=rowan
```

For first provisioning, run the following from the shared checkout with the character's source card. An optional source log can be supplied with `--log`. To bring over a running character's history, follow the database import instructions in [INSTALLATION.md](INSTALLATION.md).

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" init --card /path/to/rowan.yaml
```

## Prepare and resolve one turn

Use the same decision path for incoming messages and scheduled wakes. On an incoming message, the transport supplies its stable event ID and actual text to `prepare --event -` as JSON on stdin. A scheduled wake calls `prepare` with no event. Preparation queues the input, advances the next due event or resumes its saved tick, and returns the character's decision context in one tool call. Use the established screened Python adapter for runtimes with registered owned files.

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" prepare --event - <<'JSON'
{"id":"transport-id","kind":"incoming","context":"Did you hear the news?"}
JSON
```

On `status: pending`, make **one character decision** from `request`. Golem has already calculated the concurrent `emotions` as independent 0–100 values. The character chooses whether any feeling matters enough to affect their speech or action. Ground the voice in `identity_anchor`, its hard bans, and the chosen `dialect`. Use `recent` for continuity and `recalled_memories` for private recall. Respect the character's own stance and what they would disclose to this listener. A current cue or involuntary reflex may shape delivery. The character can answer normally, act, or stay silent.

Return the exact `character_id` and event ID from the prepared request and the reply in the character's voice. Include a brief `action` when something happens and any substantive learning, appraisal, or activity change when it occurs. Ordinary dialogue needs only `character_id`, `id`, and `reply` in profile mode. The runtime persists the tick. Routine turns require no snapshot files, grounding essay, separate emotion analysis, or timeline read.

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" resolve --receipt - <<'JSON'
{"character_id":"rowan","id":"transport-id","reply":"What happened?"}
JSON
```

Deliver the receipt's exact `reply` once per character and event ID when present. On retry, use the same event and ID. A resolved event returns its receipt directly from preparation. A different pending ID means older work came first. Resolve that event and retry the original input to reach its turn. A sleeping, failed, or closed status requires no character generation. Serialize decision and delivery work per character. Use `pending` when inspecting the full saved tick for diagnostics.

## Duration-based maintenance activity

Golem persists activity ID, kind, status, state, start/due/end timestamps, event IDs, and revision in the same SQLite database. A selected activity creates one scheduled due event. The duration's physiological progression is calculated by Golem from elapsed event time; no per-minute LLM calls are needed. Completion, interruption, and resumption are recorded transactionally with the decision and bodily transition.

After checking a real resource is available, a character may choose a meal. For a 20-minute meal, start with the delayed intake effect stored for completion:

```json
{"character_id":"rowan","id":"PENDING_EVENT_ID","action":"Starts a meal.","activity":{"op":"start","id":"meal:PENDING_EVENT_ID","kind":"meal","state":"awake","duration_seconds":1200,"data":{"effects":{"food_intake":30}}}}
```

At the due event, the character decides whether to complete or extend it. Completion applies the stored meal effect once:

```json
{"character_id":"rowan","id":"DUE_EVENT_ID","action":"Finishes the meal.","activity":{"op":"complete","id":"meal:PENDING_EVENT_ID","state":"awake"}}
```

For sleep, start a duration activity in `sleeping` state; Golem applies sleep recovery over elapsed time. At the due event, Simulacra decides whether to wake (`complete` with `state: awake`) or extend (`extend` plus a new positive `duration_seconds`). If an incoming event interrupts an activity, resolve with `op: interrupt`; to continue later, choose `op: resume` with a new duration. The loop cancels the old due event and schedules a revision-specific one. Completed and interrupted activities remain in the status history.

No state transition occurs from a bare prose plan: use the structured `activity` field. Missing food, water, or host tools must be reported to Simulacra; the engine does not manufacture resources. Hydration has no physiological model in this runtime.

## Restart, inspect, diagnose

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" status
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" pending
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" timeline --limit 100
```

At a VM replacement, use the same checkout path (or update `SIMULACRA_DIR`) and persistent database path. The SQLite queue restores active/due activities and pending cognitive requests. Never initialize a replacement database over the existing one. Never substitute LLM estimates for Golem CLI output; if Python, PyYAML, or the checkout is unavailable, report the execution failure and retry after the capability is restored.
