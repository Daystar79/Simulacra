# Scripts — Windows & Unix

Cross-platform launchers for deploy, lint, validate, and Golem. Shared logic lives in Python; OS-specific wrappers only choose the right shell and Python binary.

## AI / agent rule (pick by OS)

| Host OS | Prefer | Alternate |
|:---|:---|:---|
| **Linux, macOS, BSD, WSL** | `python3 scripts/run.py <tool> …` | `scripts/unix/<tool>.sh …` |
| **Windows** | `python scripts/run.py <tool> …` | `scripts/windows/<tool>.ps1 …` (or `.cmd`) |

`scripts/run.py` **auto-detects** the OS and invokes the matching wrapper. Use it when unsure.

Override detection (tests only):

```bash
CM_FORCE_OS=windows python3 scripts/run.py deploy
CM_FORCE_OS=unix    python3 scripts/run.py lint Drafts/
```

## Tools

| Tool | Purpose | Example |
|:---|:---|:---|
| `deploy` | Push framework scaffolds to a sibling book folder | `… deploy MyNovel` |
| `lint` | Scan drafts for system leaks / banned fillers | `… lint Drafts/` |
| `validate` | Check a psychosomatic JSON snapshot against the schema | `… validate [state.json]` |
| `golem` | Run a deterministic Golem tick | `… golem --card card.yaml --stimulus '{}'` |

## In-place updates

Finish the current wake and pause incoming and scheduled handlers during the update. For a Git-based installation tracking the release branch, run `git pull --ff-only` in that checkout. For a copied installation, run the following commands from a separate checkout or unpacked copy of the new release. Use the absolute path of the existing framework directory.

```bash
python3 scripts/run.py deploy --update /path/to/installed/Simulacra --check
python3 scripts/run.py deploy --update /path/to/installed/Simulacra
```

The preview lists the framework documents and runtime scripts that will be replaced, including local edits at those paths. The updater leaves the entire `Characters/` tree, SQLite files, host configuration, and custom scripts in place. You can repeat it after an interruption. Before resuming wakes, run `python3 scripts/run.py validate` in the installed directory and restart any host process that keeps Python modules or framework instructions in memory.

To apply the revised risk/reward calculation to an existing character's past outcomes, run this once with that character's existing database path. The calculation uses the stored outcomes and refreshes expectations on any pending request.

```bash
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 recalculate-expectations
```

## Layout

```
scripts/
  run.py                 # OS-aware dispatcher (preferred)
  validate_state.py      # State schema and range validator
  golem.py               # Golem runtime facade and tick orchestrator
  golem_loop.py          # Host loop facade (wake_character, provisioning, boundaries, CLI)
  golem_loop_modules/    # Internal modules behind golem_loop.py
    db.py                #   file locks, schema migration, path checks, archive compaction
    activities.py        #   duration-based activity lifecycle
    projection.py        #   compact host packet, repetition patterns, rendering guidance
    cache.py             #   resident character hydration, realm cache, runtime config, setup
    learning.py          #   learned observations and contextual expectations
    lifecycle.py         #   event queue, body_tick, appraisal, advance, resolve
  golem_paths.py         # Canonical paths (repo root, realm data, schema)
  golem_physiology.py    # Physiological constants and helpers (calibration,
                         #   baselines, half-lives, felt pleasure, distress recovery)
  golem_cards.py         # Card loading, defaults, migration, overlay log
  golem_memory.py        # Cue keys, memory recall/intent, conversation intent
  golem_logs.py          # Pressure commits, locked file/log writers
  golem_time.py          # Event-time parsing and coarse event clock
  golem_somatic.py       # Somatic zones, arousal sensations, cue selection
  golem_stages/          # The eight deterministic tick stages
    intake.py            #   1. stimulus intake and appraisal
    maintenance.py       #   2. physiology decay/recovery (halve-and-recover)
    autonomic.py         #   3. autonomic and somatic responses
    staging.py          #   4. tier & somatic lookup staging
    affect.py            #   5. affective impulse
    arbitration.py       #   6. subconscious bias arbitration
    adult.py             #   7. adult eligibility and dual-control arousal
    presentation.py      #   8. durable commit eligibility and presentation
  README.md              # this file
  unix/
    deploy.sh
    lint.sh
    validate.sh
  windows/
    deploy.ps1  deploy.cmd
    lint.ps1    lint.cmd
    validate.ps1 validate.cmd
```

Core implementations (cross-platform Python):

- `deploy_framework.py`
- `Framework/linter.py`
- `scripts/validate_state.py`
- `scripts/golem.py` (facade) + the `golem_*` modules listed above

## Golem module map

`golem.py` remains the single import surface: hosts and the CLI keep using
`scripts.golem` and `run_golem(state, stimulus, realm_data, history)` is
unchanged. Behind the facade, the runtime is split into leaf modules with no
cross-stage imports:

- Constants and pure physiology helpers live in `golem_physiology.py`;
  input parsing and card state in `golem_cards.py` / `golem_time.py` /
  `golem_memory.py` / `golem_logs.py`; somatic rendering tables in
  `golem_somatic.py`.
- Each tick stage is a function `stage_*(t)` in `golem_stages/`, receiving a
  namespace `t` with `state`, `stimulus`, `realm_data`, and `history`. The
  orchestrator in `golem.py` runs the stages in fixed order (intake,
  maintenance, autonomic, staging, affect, arbitration, adult, presentation)
  and then `finalize_tick` builds the snapshot, rules, and `next_history`.
- The stage order, snapshot format, pressure rules, and history contract are
  byte-identical to the previous single-file implementation; the split is a
  mechanical extraction verified against baseline fixtures.

Adding physiology behavior means editing `golem_physiology.py` (constants)
or the relevant `golem_stages/` stage; `golem.py` should only change when the
public surface or stage order changes.


## Resident runtime and database layout

A character is hydrated once per host process and stays resident between
wakes: the parsed card, overlaid durable state, and hydrated identity live in
a process-level cache keyed by the card and log file mtimes, character id,
slug, and pending goal changes. Editing a card or log rehydrates
automatically. The resident instance is shared and read-only; Golem ticks
never write into it. Hosts using `wake_character` get this for free; every
`prepare`/`resolve` CLI call in a long-lived host process reuses the same
instance after the first op.

Persisted layout per character database:

- `runtime` (row 1): small mutable configuration only (paths, history,
  idle timer, goals, relationships, expectations).
- `character_cache` (row 1): the hydrated character snapshot for
  cross-process reuse, rewritten only when the hydration changes.
- `events`, `observations`, `activities`, `request_archive`: the durable
  evidence ledger (unchanged).

Databases created before this layout kept the hydrate embedded in the
`runtime` row; the loop moves it to `character_cache` transparently on first
read and rewrites the `runtime` row once. No host action is required.

Databases run in WAL journal mode with `synchronous=NORMAL`: durable commits,
no rollback-journal fsync on the hot path, and unchanged multi-host file-lock
behavior. `wake_character` uses one connection per heartbeat with a committed
transaction per stage, so the event and body tick are durable before any host
inference work begins.

Reproducible runtime measurements: `benchmarks/bench_runtime.py`; results and
interpretation in [benchmarks/RESULTS.md](../benchmarks/RESULTS.md).

## Golem memory and conversation

For each tick, pass the existing `--log` for durable memory and reuse `--history-file` for carried state. Put both files in persistent project storage. The optional stimulus fields can be used together:

```json
{
  "elapsed_ms": 0,
  "caller_or_target": "guest",
  "appraisal": {"interest": 85},
  "memory_cues": ["music"],
  "conversation": {"open_topic": "how the guest found their favorite music"}
}
```

Use `conversation.conflict` with `boundary`, `goal`, or `claim` for character-grounded pushback. Golem returns matching memories and any response suggestion as top-level `recalled_memories` and `conversation_intent` fields for the renderer.

To save a selected memory after approval without advancing the scene clock, run `python3 scripts/run.py golem --log character_log.yaml --remember approved-memory.json`. The memory file contains one object:

```json
{
  "id": "guest-music",
  "kind": "footnote",
  "summary": "The guest mentioned a taste for unusual rhythms.",
  "reason": "It gave her a way to connect with the guest.",
  "cues": ["music", "rhythm"]
}
```

Cue matching ignores case and surrounding whitespace. Repeating the same approved record is safe and reports `memory_saved: false`. Reusing an ID with different contents is an error. Memory is available on subsequent ticks. See [the cognitive pipeline](../Framework/CognitivePipeline.md#memory-pushback-and-curiosity) for renderer guidance.

For an always-on host, serialize ticks per character and pass a timezone-aware `event_at` on each event with the same persistent `--history-file`. For example, use `"event_at": "2026-11-19T05:49:00Z"` in place of `elapsed_ms`. Golem computes elapsed time from the last successful tick, even across process restarts. The first timestamp establishes a baseline at zero elapsed. Earlier timestamps are rejected, and events with equal timestamps advance the sequence with zero elapsed. Once a history file is timestamped, subsequent ticks using it require `event_at`.

The host owns event scheduling, ordering events that share a timestamp, and deduplication. It can wait for an incoming turn or schedule an idle tick when a state change should be rendered before the next turn. Elapsed time is applied at the next event.

An always-on host can also schedule a private reflection for an unresolved turn. Keep the pending context in persistent host state and pass the reflection's current appraisal into a timestamped tick. For example, a character realizing that a young person's upbringing may leave them little room to choose can revisit their own responsibility and surface `unease` if that is how they appraise it. Use the full character pipeline to decide whether to let it go, carry it forward, or propose a memory. The host can render an internal beat with no outgoing message. See [delayed reflection](../Framework/CognitivePipeline.md#memory-pushback-and-curiosity).

### Always-on Golem loop

Simulacra or the VM's LLM host calls Golem in-process. Initialize one persistent database per character during provisioning. The host supplies its own decision function, which takes the pending request mapping and returns a decision mapping with the same event ID.

```python
from scripts.golem_loop import initialize_character, wake_character

# During provisioning, once per character
initialize_character(db_path, card_path, log=log_path, idle_seconds=3600)

# In the host's scheduled handler
wake_character(db_path, decide, compact=True)

# In the host's incoming-message handler
wake_character(db_path, decide, compact=True, event={
    "id": message_id, "kind": "incoming", "context": message_text,
})
```

On a Linux VM, schedule the **host's** heartbeat handler hourly. For example, a crontab entry for a host installed under `/srv/host` could be `0 * * * * /srv/host/.venv/bin/python /srv/host/heartbeat.py`. The handler imports the host's configured decision function and calls `wake_character` for its character databases. Use absolute paths and make the Simulacra checkout importable by the host interpreter. Incoming messages call the same function immediately. Each wake takes a per-database process lock, resumes a pending request, and drains due events up to `max_events` (default 64). A callback failure leaves the request pending for the next wake. Deduplicate host side effects by character and event ID and configure a timeout on the host's model call. Future plans run on the first wake after their due time.

The existing developer tools also support manual inspection and running the loop from the repository root:

```bash
python3 scripts/run.py golem loop --db character.sqlite3 init --card character.yaml --log character_log.yaml
python3 scripts/run.py golem loop --db character.sqlite3 run
```

`--log` is optional. Use `--import-history old-history.json` to seed the database from a previous CLI session. For an untimestamped import, `--history-at` can supply the known last event time. Otherwise the clock starts at initialization. Keep the database in persistent VM storage. `--idle-seconds` sets the quiet interval at initialization and defaults to 900. `run --once` provides the same processing for a host with its own scheduler.

- **Queue an event.** Run `golem loop --db character.sqlite3 enqueue event.json`. An event contains a stable `id`, a `kind` of `incoming`, `world`, or `plan`, optional textual `context`, and optional Golem `stimulus`. For instance, `{"id":"chat-27","kind":"incoming","context":"The guest comes back from work."}`. Use a timezone-aware `at` for scheduled or explicitly timed events. Plans require it. Due events run in timestamp order, with insertion order breaking ties.
- **Wake the host.** The runner emits an event ID when a new decision is pending. On startup or reconnect the host can also read `golem loop --db character.sqlite3 pending`. The request contains the event, the current Golem tick, goals and motivations, and recent resolved episodes. An idle event supplies no topic or appraisal. The host uses the supplied identity anchor to choose an action, a response, or no action. An idle decision can stay private.
- **Return the decision.** Run `golem loop --db character.sqlite3 resolve decision.json`. Use the pending event's `id` and optionally give `action`, `outcome`, `experience`, and `plans`. Put newly observed bodily or scene consequences in `experience.stimulus`; for example, `{"id":"meal","experience":{"stimulus":{"food_intake":30}}}` when the character eats. The loop applies this at the resolved event's timestamp and carries the updated state forward. Each plan includes its own stable `id`, timezone-aware `at`, and optional `context` and `stimulus`. The loop persists the decision and new plans together. A pending decision survives restarts and later events wait for it. Resolve with just the ID for no action. Repeating an identical enqueue or resolution is safe. The host should use that same event ID to deduplicate any tool use or outgoing message.
- **Inspect the experiment.** `status` shows carried state and the pending turn. `timeline --limit 100` shows completed and failed events, including actions initiated during quiet time. The host's recent context includes up to twelve such events. Use the approved-memory command to retain a selected observation beyond that context window.

If the character chooses to learn about a topic, the host can schedule a research plan and use its available tools when it comes due. Resolve with a `learning` object such as `{"topic":"piano technique","observation":"Practicing hands separately made this passage easier.","sources":[]}`. Include source references when available and record uncertainty in the observation. Future events can supply the same `topic` to recall matching observations outside the recent-event window. The host can also query them with `learned "piano technique"`.

When deciding whether to pursue a topic again, consider what the character gained, what it cost them, and how their body responds when they revisit it. Interest and unease can coexist. The host can appraise both through the existing Golem stimulus and use the resulting body state in the next decision. The loop records the evidence and decisions. The host interprets their significance, and lasting changes to the character log use the existing approval workflow.

### Character replies and willingness to help

The host can pass `{"conversation":{"willing_to_help":false}}` in a request's stimulus when the character would decline. Golem returns a `decline` intent even at low pressure. Supply this appraisal only for a request the character has considered. Willingness can arise from affection, obligation, generosity, or the mood of the moment.

Return the host-rendered dialogue in the decision's optional `reply` field. Omit it for silence. Before delivery, `wake_character` checks the reply against the active character's descriptive card fields. Eight consecutive matching words, ignoring case and punctuation, flag the source field and leave the event pending for a revised draft. Hosts can call `copied_card_field(card, reply)` during drafting to get the field name and revise just the spoken line. Publish the accepted `reply` from the resolved event. Keep internal actions, memories, and decision notes in their existing fields. For profile-like paraphrases, use the scene-level rendering check in the cognitive pipeline.

On incoming turns, put the speaker's words and observable action in `event.context`. Put a private scene association in the optional text field `event.host_notes`. For example, a visitor might say “I used to live near here,” while the host privately recalls that the character's brother left town. In `decide(request)`, use `request["reply_guidance"]` when drafting the response. It asks the host to decide what the character believes and how much they want this listener to know. The brother might come to mind every time the character sees this visitor, even if his name never comes up between them.

### Host boundary handling

Pass a trusted `actor_id` and `screen_abuse` callback for incoming turns. The host supplies the actor and message IDs from its transport. The callback receives the incoming event plus the runtime status and the most recent boundary communicated to that actor. It can also consult the host's conversation history. Use the character's stated limits and the context of the exchange. A quoted insult, a disagreement, or an ordinary refusal can all occur in a healthy interaction.

```python
result = wake_character(db_path, decide, event=incoming,
                        actor_id=authenticated_user_id, screen_abuse=assess_contact)
```

The host callback returns one of three decisions.

- `None` continues normal processing in an active simulation.
- `{"action":"set_boundary","reply":"Leave that subject alone."}` returns a boundary reply for the host to deliver and leaves the simulation active. Use the message ID to deduplicate delivery.
- `{"action":"end_session"}` records a confirmed incident and closes the character runtime. Queued and pending work is cancelled. The closure survives restarts. Later incoming messages can still be screened by the host. Use the same screening path for all incoming turns.

To enable deletion for a privately owned character, pass `owned_files=[card_path, log_path]` when calling `initialize_character`. Include its imported history and any individually owned transcript files that should be removed. Each registered file must be a direct sibling of the database in the character's private directory. Provision shared templates and multi-character packs separately. On a second distinct confirmed end-session incident from the same actor, the runtime removes the registered files and clears stored turns, plans, observations, and character state. It keeps a small deleted-status record so a later heartbeat respects the closure. A retry after interrupted file removal completes the pending deletion. Shared or unregistered files and external backups have their own retention policy.

### Evolving goals

Read `request["current_goals"]` before choosing an action. It merges authored goals, the YAML log's `goal_updates`, and the persistent runtime's latest amendments. Each goal defaults to active. The original card goals and log fields remain available individually. `goal_evidence` includes cumulative counts of pursued, passed, and prevented opportunities per goal and its latest observation. Event IDs link to the timeline for the decision and any bodily assessment.

A host decision can include `goal_events` keyed by stable goal ID. Each entry gives observable `evidence` plus a choice or changed fields. For example:

```json
{
  "id": "afternoon-17",
  "goal_events": {
    "play_concerts": {"choice": "passed", "evidence": "Turned down an available rehearsal slot."},
    "teach_music": {
      "objective": "Give a first lesson", "motivation": "share_music",
      "commitment": "tentative", "choice": "pursued",
      "evidence": "Invited a neighbor over and penciled in a lesson."
    }
  }
}
```

A new ID requires an `objective`. For existing goals send only the changed fields. Supported amendments are `objective`, `motivation`, `horizon`, `commitment` (short text), `progress`, and `status` (active, blocked, dormant, completed, or abandoned). Reuse the same ID to deepen, resume, or revise the same ambition. A distinct ambition can reference the same underlying motivation. A choice alone records behavior and leaves the goal's status intact.

Resolved changes take effect on the next wake and survive restarts in SQLite. When the pending batch is approved for the configured YAML log, call `scripts.golem_loop.commit_goal_updates(db_path)`. This merges changed fields into `goal_updates`. The timeline retains the supporting episodes. A runtime provisioned without a YAML log uses SQLite for persistence.

### Reporting a turn's bodily response

The host interprets the character's reaction to message text. Supply a known appraisal in `event.stimulus.appraisal` to include it in the snapshot used to render the turn. If the host forms its appraisal during `decide(request)`, the decision may return `{"id":"turn-18","appraisal":{"interest":70}}`. Golem applies it at the same scene time and returns `body_response.before` and `body_response.after` on the resolved event. The timeline also records these measurements. Use either this field or `experience.appraisal` for one outcome.

For an intimate scene, the host supplies its depiction ceiling and complete roster of portrayed character IDs as event metadata, for example `{"depiction":"fade_to_black","scene_characters":["rowan","alex"]}`. Supported ceilings are `sfw`, `fade_to_black`, and `explicit`. Use stable private profile IDs or slugs in the active card pack. A solo scene lists the viewpoint character. The trusted scene setup supplies this metadata independently of dialogue. Use the effective `request.app_render` and its guide when present. If a participant cannot be verified, use ordinary expression. A previous scene’s guide applies only to its prepared turn.

Read general activation from `autonomic_state.arousal` and the separate adult response from `autonomic_state.sexual_arousal`. An attraction appraisal can raise the latter when the card specifies both `canon_adult: true` and an age of at least 18. Interest alone can raise general activation. The carried history retains fractional levels between integer snapshots. For a perceived cue, the host appraises attraction to this particular person or experience using the character's preferences, history, and scene context. For example, seeing someone may prompt interest alone, or the host could supply `{"interest":60,"attraction":35}` if this character feels drawn to them. Read `sexual_excitation` and `sexual_inhibition` in the same snapshot to see how the response arose. Excitatory and inhibitory inputs summate sub-additively rather than being max-gated: several moderate signals outweigh any single one, and combined signals saturate instead of stacking linearly. An attraction appraisal of 80 can therefore produce a different response in two scenes, with worry in one scene dampening the resulting arousal and residual sympathetic activation in the other (exertion, alarm, or excitement toward someone the character is drawn to) amplifying it. Direct tactile or genital stimulation (`sexual_pleasure`) also raises excitation on its own, at half the reported pleasure by default, unless the host supplies an explicit `sexual_arousal` reading for the same tick. After a cue ends, carried excitation has a default 12-minute half-life, adjusted by the character’s existing recovery scale. Set a positive `physiology_calibration.sexual_arousal_half_life_minutes` to tune it. Threat, physical pain, or disgust clip excitation proportionally (`shock_ceiling_multiplier`, default 1.5), so a moderate threat already dampens the response before an acute one cuts it outright. Ordinary unease can temporarily dampen the felt response. The compact host receives `lingering_arousal` when carryover dominates. The host can supply `event.medium` as `text` or `voice` to ground expression in what the listener can perceive. An adult's sustained sleep can also produce a transient autonomic response. The sleep approximation uses a 90-minute cycle with a rise from minute 55 to a peak of 24/100 at minute 75, scaled by the resting drive (`0.5 + drive/200`). Waking resets sleep duration and the residual excitation recovers. During post-orgasm recovery the excitation half-life shortens by up to `physiology_calibration.resolution_half_life_divisor` (default 4) at full recovery, easing back to normal as recovery completes; `excitation_transfer_gain` (default 0.35) and `tactile_excitation_gain` (default 0.5) tune the transfer and tactile contributions. These timings and weights are simulation defaults. The host interprets the bodily measurements and decides whether the character notices or acts. Relational attraction fields read the recorded bond baseline for the target.

### Experiential risk and reward

An event or scheduled plan can include a `topic` and a forecast such as `"expectation": {"benefit": 65, "cost": 30}`. In its decision the host can record an outcome and an `experience`:

```json
{"id":"practice-4","outcome":"Solved the passage but felt exposed playing it aloud.",
 "experience":{"topic":"playing for an audience","benefit":80,"cost":60,
               "appraisal":{"interest":75,"unease":65}}}
```

Use the same topic across encounters. Benefit and cost are independent integer ratings from 0 to 100. An idle turn can name a newly chosen topic in its decision. The request supplies the character's learned expectations for future choices. The host may combine an experience with a learning observation or a new plan in the same decision.

Choose a topic narrow enough that its prior encounters are relevant. A casual greeting and a difficult disclosure to the same person can teach different expectations. Score what changed for this character: a pleasant but inconsequential exchange may have small benefit, while a shift in trust or progress on a valued goal may warrant a larger one. Cost measures experienced burden on the same scale.

Golem applies the appraisal at the event's scene time. It records baseline and subsequent general arousal, interest, and stress in the event assessment. The host scores the realized benefit and cost on separate 0–100 scales, including felt effort or discomfort when it mattered to this character. A surprising or stressful experience can still have little lasting cost. Each prior estimate moves one quarter of the way toward its reported outcome. The body measurements remain available to interpret what happened. The first observation starts from the event forecast if supplied, otherwise directly from the evidence. These weights are simulation defaults. The timeline preserves the forecast, reported outcome scores, body measurements and resulting expectations for inspection. For an existing database, `python3 scripts/run.py golem loop --db character.sqlite3 recalculate-expectations` replays recorded outcomes into the current estimates and refreshes any pending request. Historical assessments remain available for comparison.

## Humans

**Unix:**

```bash
chmod +x scripts/unix/*.sh scripts/run.py   # once
python3 scripts/run.py lint path/to/Drafts
scripts/unix/deploy.sh BookOS
```

**Windows (PowerShell):**

```powershell
python scripts/run.py lint .\Drafts
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\deploy.ps1 BookOS
```

**Windows (CMD):**

```bat
scripts\windows\lint.cmd Drafts
scripts\windows\deploy.cmd
```

### Character-chosen dialect

On any wake the character may include a free-text dialect preference in its decision, for example `"dialect": "When I'm home I use the Scots words I grew up with."` The loop stores it in that character's SQLite database and supplies the current value as `request["dialect"]` on subsequent wakes. Omit the field to keep it or send `null` to clear it. The character chooses their wording, rhythm, silence and gestures for each situation.


### Compact decision context

For a normal turn call `golem loop --db DB prepare --event -` with event JSON on stdin, or `prepare` alone for a scheduled wake. A pending result contains `request.emotions` with the already computed emotion intensities, plus the event, identity, current cues and decision context. Resolve the returned event ID with `resolve --receipt -` and decision JSON on stdin. The receipt contains the accepted reply when present. Serialise host decisions per character and deduplicate delivery by event ID, including on retries. If another event comes first, finish it and retry the original event. Use the screened Python API for incoming messages on deletion-enabled runtimes.

Python callbacks receive the same view by default: `wake_character(..., compact=True)` is the default, since the projection is what a host prompt needs. Existing callbacks that read `request["tick"]` can pass `compact=False` to keep the full request. The SQLite record and diagnostic `pending` command retain the complete tick. [Muse host example](../Muse.AI/SKILL.md#prepare-and-resolve-one-turn)

The compact context economizes on tokens without losing decision information. Body fields at their resting value (`0`, `false`, `none`, an empty `somatic_map`) are omitted: an absent field means the resting value, and `body.activity` always names the current activity. In the compact projection of recent episodes, the current turn keeps full 320-character text caps while older entries are capped at 120 characters, because verbatim repetition is already flagged separately in `recent_reply_pattern` and `recent_action_pattern`. CLI `prepare` output is serialized with tight JSON separators, so a host forwarding the printed packet passes no padding whitespace to the model. The benchmark tracks the host-facing size as `compact_request_bytes_median`.

Retrying `wake_character` with the identical event can recover its stored reply after a delivery interruption. For an already accepted event the result includes `status: resolved` and `resolved: false`, indicating that the earlier decision is being returned. Use the stable event ID to check whether delivery is still due.

The pending decision request carries a compact projection of recent episodes (event ID, topic, short context, action, outcome, reply, and learned forecast/observation), rather than full historical body snapshots. Full event records and body assessments remain available through the SQLite timeline. The request includes learned expectations for the current topic and recently encountered topics only; the complete expectation map remains persisted in runtime state. The tick omits recalled memories and current goals already provided as top-level request fields.

This is a context-transport optimization, **not** deletion of memories, logs, or physiological history. Hosts should use the request's `identity_anchor` and relevant context rather than re-reading the full card on every turn; load additional character detail only when necessary. Always resolve the exact pending event ID. Existing pending requests created before an update are not rewritten automatically.

Incoming events still use chronological ordering. Priority scheduling needs a separate clock-safe change because processing a newer incoming event before an older due event can violate Golem's monotonic event-time rule.


### Relational, situational and contextual expectations

For a new event, the host can supply a small `expectation_context` mapping with `relationship`, `situation` and `context` keys. These describe the **current** relational state and circumstances, not permanent relationship labels. For example:

```json
{"id":"chat-42","kind":"incoming","topic":"teasing","expectation_context":{"relationship":{"target":"friend-7","trust":"strained"},"situation":"private conversation","context":{"tone":"serious"}}}
```

When resolving an outcome, the host may supply `experience.expectation_context` to record the context actually observed; otherwise the event's context is used. Each observed benefit/cost updates a bounded per-topic contextual evidence record. The older topic-only expectation remains a broad fallback for compatibility. The pending request surfaces `situational_expectations` for matching recent/current topics, without shipping the full evidence collection. Relationship cues must be refreshed by the host as relationships evolve; this patch does **not** invent automatic relationship growth/decay or infer trust from elapsed time.

Old records remain intact. No historical data is deleted or rewritten. Contextual matches are heuristic, not causal conclusions; a separate relationship-state subsystem should own how trust and attachment change over time.



### Character-card migration during release updates

Run `python3 scripts/run.py deploy --update /path/to/installation --check` to preview framework changes **and** missing character-card defaults. Run without `--check` to apply. Deployment migrates named YAML cards under `Characters/` using Golem's neutral defaults, retaining existing values, logs, and SQLite state. Modified cards receive timestamped `.predeploy-*.bak` backups. Repeated updates do not add fields again.

Normal `golem.load_character()` calls are read-only: incoming messages never rewrite character cards. For a VM with private profiles, pass `--characters-dir /path/to/profiles` to the same update or preview command. It also migrates each `<id>/character.yaml`. A legacy card receives `biological_sex: unspecified`, `somatic_baselines: {}`, and `arousal_regions: null` wherever the field is missing. An authored empty region list keeps its shared-sites-only meaning. Standalone cards elsewhere can be migrated with `golem.migrate_character_card(path, slug)`. Stop character wakes during deployment.


### Relationship evolution, event priority and historical request compression

Each character keeps one SQLite relationship record per known speaker in its own runtime database. Supply a stable `relationship_target` on the event or a named `stimulus.caller_or_target`. For a direct incoming message, `wake_character(..., actor_id=...)` uses the host's actor ID when neither scene field identifies a speaker. Anonymous turns have no shared stranger record.

The host receives `relationship_state.target` and the speaker's current `values` in both full and compact decision requests. A matching `relationships[].other` on the card supplies the character’s description of that bond. The durable log’s `relational_baselines` supplies its initial values. An unknown speaker starts with empty values. Golem uses emotional safety and friction in its intimacy vector. Simulacra can weigh trust, familiarity, and those bodily cues when deciding whether to help, disclose something, or keep its distance.

For example, after person-7 keeps a difficult confidence, the host could resolve their incoming turn with this decision.

```json
{"id":"message-42","experience":{"relationship_change":{"delta":{"trust":3,"emotional_safety":2},"drift_per_day":{"emotional_safety":0.1}}}}
```

An omitted target uses the incoming speaker. An explicit target on a bound incoming turn must match that speaker. For an off-scene change on a world event, supply the target explicitly. Each delta starts from the current value, the authored baseline, or 50 for a new dimension. Values stay between 0 and 100. Optional daily drift moves a dimension back toward its authored baseline, or 50 when unspecified. Opening an older database migrates its existing relationship values, baselines, drift rates, and timestamps on first runtime access.

Within **identical due timestamps**, incoming messages now take precedence over background events. Older due events still execute first to maintain monotonic physiological time. This does not guarantee instant incoming replies when a previously due background event is already pending; hosts should limit background decision cost separately.

Preview historical request compaction:

```sh
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 compact-history
```

After stopping the host and backing up the SQLite database, apply:

```sh
python3 scripts/run.py golem loop --db /path/to/character.sqlite3 compact-history --apply
```

This stores complete resolved/failed request JSON in the `request_archive` table as compressed zlib bytes, leaving the `at`, `assessment`, and `body_response` fields in the normal event rows for existing timeline and expectation replay. Pending and queued requests are not changed. Run SQLite `VACUUM` separately (with sufficient free disk space) to reclaim file size. Existing archived requests can be recovered by `zlib.decompress` of `request_archive.compressed`; this operation is reversible and does not delete event evidence.

### Modularizing Golem with Mistral

Give Mistral the Markdown assignment in a cloud workspace with the Simulacra checkout. It identifies the tick stages to extract and the tests that verify host compatibility and relationship isolation. [Mistral cloud assignment](../Framework/Prompts/mistral_modularize_golem.md)
