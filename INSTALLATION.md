# INSTALLATION — Simulacra and persistent Golem

This is the human-facing installation and host integration guide. For autonomous installers, use [SETUP.md](SETUP.md). The authoritative runtime documentation is [scripts/README.md](scripts/README.md).

## Requirements

- Python 3.12 (the version used for the repository's documented Linux checks).
- PyYAML 6.0.3.
- Persistent writable storage for each character's SQLite database and, when used, YAML log.
- An LLM host that can call Python, supply a decision callback, and schedule incoming and idle events.
- A character YAML card. The public scaffold is `Characters/_template.yaml`.

From the repository root on Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install PyYAML==6.0.3
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/run.py validate
```

On Windows use `python` and the appropriate virtual-environment executable; see [scripts/README.md](scripts/README.md) for OS-specific dispatch.

## Choose the correct execution mode

**Persistent character:** use `scripts.golem_loop`, with one SQLite database per character. This is the required path for scheduled autonomous actions, plans, pending decisions, and continuity across host restarts.

**One-off/manual tick:** `scripts/run.py golem` (or `scripts/golem.py`) can calculate a snapshot. A successful snapshot does **not** mean the persistent loop is installed. The CLI's `--history-file` and `--log` support carried state in manual workflows but are not a replacement for a connected loop.

Do not run both modes as independent writers for the same character. If migrating manual history, use the loop's documented `--import-history` option.

## Provision one character

Use absolute paths in production. Ensure the character card and optional existing durable log are accessible to the host process.

```python
from pathlib import Path
from scripts.golem_loop import initialize_character

root = Path("/srv/characters/talia")
db_path = root / "character.sqlite3"
card_path = root / "talia.yaml"
log_path = root / "talia_log.yaml"

# Provision once, not once per message. Existing installations should
# reopen the existing DB rather than reinitializing it.
initialize_character(db_path, card_path, log=log_path, idle_seconds=3600)
```

Paths above are examples, not paths supplied by the repository. Use a separate database and appropriate card/log for each character. Keep the SQLite database in durable storage, not a temporary working directory.

Equivalent manual initialization from the repository root:

```bash
python3 scripts/run.py golem loop --db /srv/characters/talia/character.sqlite3 init --card /srv/characters/talia/talia.yaml --log /srv/characters/talia/talia_log.yaml --idle-seconds 3600
```

Omit `--log` if the character has no durable log.

## Connect the host loop — mandatory

The host must provide `decide(request)`, which receives the pending event, current Golem tick, motivations/goals, and recent context. The host loads the character card and applies the Simulacra cognitive pipeline to choose the reply, private action, outcome, or plans. It returns a decision mapping **with the same event ID**.

```python
from scripts.golem_loop import wake_character

def decide(request):
    # Implement in your host: run the Simulacra cognitive pipeline and
    # render the character's response from the supplied tick and context.
    # This no-action example proves the loop wiring, not character behavior.
    return {"id": request["event"]["id"]}

# Called on each incoming message:
result = wake_character(
    db_path,
    decide,
    event={"id": message_id, "kind": "incoming", "context": message_text},
)

# Called from a host-owned scheduled heartbeat:
result = wake_character(db_path, decide)
```

Do not substitute `golem.py` snapshot calls for `wake_character`. Do not hardcode `elapsed_ms: 0` on every event. The loop owns event time and carried history. A first timestamp can legitimately produce zero elapsed time; later events should reflect their actual time difference.

Use stable, unique incoming message IDs. Deliver only accepted replies from resolved events, and deduplicate external delivery/tool effects by character and event ID. A failed callback leaves the request pending; retry by waking the same database rather than inventing a new event.

## Scheduling and persistence

Schedule the **host's** heartbeat handler (not a raw Golem snapshot invocation). For example, on Linux:

```cron
0 * * * * /srv/host/.venv/bin/python /srv/host/heartbeat.py
```

The heartbeat handler must import the configured host decision callback and call `wake_character` for each character database. Set `idle_seconds` to match the desired quiet cadence. Plans run on the first wake after their due time; a continuously running daemon is not required, but a scheduler is required for autonomous activity when no messages arrive.

The loop serializes work per database, carries history and plans in SQLite, and resumes pending requests after a restart. The character's approved memories remain in its YAML log; see the existing memory approval instructions in [scripts/README.md](scripts/README.md).

## Manual diagnostics

```bash
python3 scripts/run.py golem loop --db /srv/characters/talia/character.sqlite3 status
python3 scripts/run.py golem loop --db /srv/characters/talia/character.sqlite3 pending
python3 scripts/run.py golem loop --db /srv/characters/talia/character.sqlite3 timeline --limit 100
```

To exercise the manual queue, see the `enqueue`, `run`, and `resolve` examples in [scripts/README.md](scripts/README.md). A pending event must be resolved before later events proceed.

## Acceptance checklist

- [ ] Dependencies and repository tests pass.
- [ ] Character card and optional log load successfully.
- [ ] One persistent SQLite database is initialized and reused.
- [ ] Incoming messages enter `wake_character`, not just a snapshot CLI.
- [ ] The host callback consumes the actual tick and returns the matching event ID.
- [ ] A second event uses carried history; event time advances when wall-clock time advances.
- [ ] Idle wake runs through the same callback and can produce a private action, no action, or a plan.
- [ ] Pending work survives host restart; duplicate delivery is prevented.
- [ ] Approved memories persist under the documented approval rules.
- [ ] `status` and `timeline` show completed loop activity.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Snapshots exist but no SQLite timeline | Host is using the standalone Golem CLI instead of `wake_character` |
| Every snapshot shows zero elapsed time | First-event baseline, duplicate timestamps, or host supplying zero time instead of using the loop |
| Pending event never resolves | Callback failure, wrong event ID, or failure to return the decision |
| Idle plans never run | Missing heartbeat, incorrect cadence, or plan due time not reached |
| Memories vanish | Wrong log path, missing approval/write, or ephemeral storage |
| One host works and another does not | Compare provisioning, persistent DB path, callback wiring, and scheduler before modifying engine logic |

Do not change Golem's core algorithms or rewrite a character card to hide a host installation defect.
