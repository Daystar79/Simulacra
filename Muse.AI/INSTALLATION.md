# Muse.AI installation and scheduled execution

This configures Muse.AI as a host for the existing Simulacra/Golem runtime. It does not add another runtime, keep a Python daemon alive, or require a remote service.

## 1. Persistent locations

Muse's audited persistent workspace is `~/workspace`. Use this default checkout unless the repository is installed elsewhere:

```bash
export SIMULACRA_DIR="${SIMULACRA_DIR:-$HOME/workspace/repos/Simulacra}"
export SIMULACRA_DATA="$HOME/workspace/simulacra"
export CHARACTER_ID="rowan"
export CHARACTERS_DIR="$SIMULACRA_DATA/characters"
```

Bind the ID separately in each chat adapter and heartbeat. Give each character its own Muse conversation history and tool working directory under `$CHARACTERS_DIR/$CHARACTER_ID`. Share the checkout and read-only framework instructions across jobs.

## 2. Provision or import a character

Install Python 3, PyYAML and the Muse skill. To create a new character runtime from authored files:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" init --card /path/to/rowan.yaml --log /path/to/rowan_log.yaml
```

For an existing character, pause its old chat handler and heartbeat. Choose a fresh destination directory under a suitable characters root. Import its existing database in place of running the fresh-card command:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" init --from-db /path/to/old.sqlite3
```

The importer copies the SQLite ledger, pending work, current card and durable log. Registered character-owned files are copied too. Place any separate host-maintained transcripts or attachments in the new character directory. Resume the chat handler and heartbeat against the new profile. If the old history already includes material from multiple characters, it requires review before import. [Profile layout and Python API](../README.md#multiple-characters-on-one-machine)

## 3. Configure scheduled agent jobs

Schedule the host job at the desired cadence. It prepares one due event and follows the decision and receipt contract in the [Muse host guide](SKILL.md#prepare-and-resolve-one-turn).

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" prepare
```

## 4. Incoming messages

Have the messaging adapter call `prepare --event -` with the stable transport ID and message as event JSON on stdin. Feed the returned decision context to Simulacra once. Resolve its decision with `resolve --receipt -` and deliver the accepted reply, deduplicated by character and event ID. Follow the same guide for retries and earlier pending work. Replace any older per-message job instructions that request a full tick, separate snapshot files, or a written emotional rationale.

For a Python adapter, use `wake_character(db, decide, event=incoming, character_id=character_id, compact=True)`. Preserve the host's boundary screening and trusted actor ID. Runtimes with registered owned files require the screened Python adapter for incoming events.

## 5. VM replacement recovery

After replacement, use the same persistent DB and scheduled job. Check runtime state:

```bash
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" status
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" pending
python3 "$SIMULACRA_DIR/scripts/run.py" golem loop --characters-dir "$CHARACTERS_DIR" --character-id "$CHARACTER_ID" timeline --limit 100
```

An unresolved pending request is returned unchanged. Active or due activities and their original timestamps/event IDs are stored in SQLite. Resolve a pending request before asking for another wake. If no request is pending, `run --once` processes the next due plan or idle wake. Activity start/completion/interruption and Golem state changes share a DB transaction; duplicate resolution of the same event ID does not apply consequences again. The runtime migrates older databases by creating its activity table without replacing existing state.

## 6. Deterministic runtime boundary

Use `python3 "$SIMULACRA_DIR/scripts/run.py" golem ...` for all body updates. The Python CLI wrapper locates files relative to its installation and emits structured JSON. A scheduled LLM may interpret the result and select behavior; it must never substitute prose, arithmetic, or guessed values for Golem. If the checkout, Python, or PyYAML is unavailable, report a runtime capability error and retry after it is restored.

For command details, activity operations, JSON fields, calibration, and limitations, read [../SKILL.md](../SKILL.md).

## Reload after this update

Install the updated runtime and Muse guide together. Reload or reselect `Muse.AI/SKILL.md` and refresh any saved job prompt that copied the older procedure. Restart any long-running Python adapter so it loads the new runtime. Resume using the existing database, card and log paths.
