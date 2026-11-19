# SETUP — Instructions for an AI installation agent

**Mission:** Install and verify Simulacra with the **persistent Golem loop** in the target host. A successful call to `golem.py` is insufficient. Read [INSTALLATION.md](INSTALLATION.md), [scripts/README.md](scripts/README.md), and [Framework/CognitivePipeline.md](Framework/CognitivePipeline.md) before editing the host.

## Non-negotiable boundaries

1. Treat the repository's Golem implementation as the reference. Do **not** change Golem's core algorithms, physiology, or character psychology to conceal a host integration defect.
2. Do not overwrite existing character cards, YAML logs, memories, or SQLite databases. Back up existing persistent state before migrations.
3. Do not fabricate elapsed time, appraisals, goals, memory approvals, or outcomes merely to make a test pass.
4. Use `scripts.golem_loop.initialize_character` for initial provisioning and `scripts.golem_loop.wake_character` for all ongoing incoming and idle events.
5. Keep host transport, LLM rendering, external tool execution, and scheduling outside Golem. The host supplies a decision callback and delivers accepted replies.

## Phase 1 — Inspect, do not guess

- Locate the actual Simulacra checkout, Python environment, installed dependencies, character card, durable log, existing history file, SQLite DB, host message handler, and heartbeat/scheduler.
- Determine whether the host currently calls the standalone CLI, uses `--history-file`, or is already connected to `golem_loop`.
- Check whether it creates a new DB, history, or character state for each message.
- Identify the exact source of message IDs and timestamps. Check whether time is being forced to zero.
- Record the current behavior before changing anything. If a required path or API is absent, stop and report it rather than inventing one.

## Phase 2 — Install

From the repository root on Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install PyYAML==6.0.3
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/run.py validate
```

Adapt executable paths to the target OS and environment. Preserve the host's existing dependency management when appropriate.

## Phase 3 — Wire persistent execution

- Provision exactly one durable SQLite database per character, with the correct card and optional log.
- Initialize only when the database does not already exist. For old CLI history, follow the documented `--import-history` migration rather than discarding state.
- Make the repository importable to the host Python interpreter.
- Connect incoming messages to `wake_character(db_path, decide, event={"id": stable_message_id, "kind": "incoming", "context": message_text})`.
- Implement `decide(request)` using the **actual** request tick, card, memory, goals, and Simulacra cognitive pipeline. Return the pending event ID in the decision.
- Wire a host-owned heartbeat to `wake_character(db_path, decide)`. Configure an explicit idle interval and scheduling cadence.
- Deliver accepted `reply` values only once. Use event IDs to deduplicate outbound messages and tool side effects.
- Preserve pending work and resume it on reconnect/restart. Avoid competing independent writers to the same character state.

Do not turn the character's performance persona into an always-active task unless the card and current activity actually require it.

## Phase 4 — Validate causality and continuity

Perform these checks with a test character or a backed-up test database. Never alter a production character to manufacture evidence.

**A. Initialization:** confirm that the DB exists and `status` reports the intended character.

**B. Incoming event:** send a unique message ID; verify that the host callback receives a request containing the event and Golem tick, and that its decision resolves that ID.

**C. Time progression:** process another event after time advances. Confirm that the next tick uses carried history and reports a positive elapsed interval when appropriate. Do not expect positive elapsed time for the initial baseline or equal timestamps.

**D. Idle event:** invoke the host heartbeat after the configured idle interval. Verify that a quiet event reaches the callback without a fabricated conversation prompt.

**E. Restart:** restart the host and reopen the same database. Verify that state, recent events, and plans remain. Test a deliberately failed callback and confirm that the pending request survives and can be retried.

**F. Memory:** verify approved memories survive a subsequent turn. Do not confuse `COMMIT_GATE:EPHEMERAL_ONLY` with the separately documented explicit memory-approval path.

**G. Character behavior:** compare ordinary conversation and performance contexts. Inspect which goals and arbitration results are supplied to the renderer; do not infer that every unchanged value is a defect.

**H. Duplicate event:** replay a previously processed event ID and confirm that it does not produce duplicate host side effects.

Use the existing repository tests as the regression baseline. Where possible, add host-side integration tests for message routing, heartbeat, persistence, and delivery idempotency.

## Phase 5 — Report before declaring success

Provide:

- Host and environment details, including Python and dependency versions.
- Existing integration mode and confirmed root cause.
- Exact paths/files changed and backups made.
- Whether the persistent loop, incoming handler, heartbeat, and callback are all connected.
- Test commands, outputs, and pass/fail status for phases A–H.
- Remaining limitations or unverified behavior.

**Fail the installation** if the host can generate snapshots but cannot show a persisted, resolved event in the Golem loop. Do not report success based solely on character dialogue sounding correct.

## Reference commands

```bash
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 status
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 pending
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 timeline --limit 100
```

See [scripts/README.md](scripts/README.md) for initialization, queueing, resolving, importing history, and operational details.
