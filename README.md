# Simulacra

**A framework for persistent virtual people: embodied cognition, memory, choice, and change over time.**

Simulacra is a file-native cognitive architecture for creating and running virtual individuals with continuing identities, rather than a collection of scripted character responses. A virtual person begins with an authored identity but can accumulate experiences, develop or abandon goals, change relationships, learn from outcomes, and act without waiting for a user prompt. The framework also supports long-form fiction, where the same cognitive and continuity rules guide character behavior across scenes.

**“Virtual people” describes the design goal and functional architecture, not a claim of proven consciousness or legal/moral personhood.** Simulacra models aspects of human cognition and Golem simulates physiology; the distinguishing objective is to let persistent individuals make context-dependent decisions and carry their consequences forward.

## How the architecture works

Simulacra separates the body, cognitive interpretation, decision-making, persistence, and presentation:

1. **Golem — body and time.** The Python physiology engine advances elapsed time and calculates bodily state, including fatigue, hunger, stress, autonomic responses, and concurrent affective signals. These are inputs to cognition, **not commands to act**. A hungry individual can choose to eat, delay eating, or prioritize something else.
2. **Simulacra — identity and cognition.** The [cognitive pipeline](Framework/CognitivePipeline.md) combines identity, remembered experiences, current circumstances, bodily signals, competing motives, relational context, and deliberative or acute reactive processing. It specifies the `Feels / Thinks / Says / Does` channels and the constraints under which decisions are made.
3. **Host — decisions and expression.** An LLM host supplies the `decide(request)` callback, applies the pipeline, and chooses and renders speech, action, silence, private reflection, or future plans. The host owns the UI, model invocation, scheduling, external tools, and delivery. Simulacra is not itself an LLM or a standalone consciousness.
4. **Persistence — continuity and consequences.** YAML cards provide the initial identity; durable YAML logs carry approved long-term changes; SQLite retains the event clock, pending decisions, plans, learning, and evolving goals. Future decisions can draw on the individual's prior choices and outcomes.

The loop is **body/state → interpretation and competing motivations → decision → action or silence → observed consequence → updated state and memory**. The process can recur on incoming events, scheduled plans, or quiet wakes. Physiological calculations are deterministic, and some cognitive rules impose hard constraints; **agency here means a designed capacity for contextual choice within those constraints**, not freedom from computation or proof of metaphysical free will.

## What makes this different from a scripted character

- **Continuity:** The individual does not start from the same prompt-only state on every conversation. Durable memory, relationships, plans, and learned expectations influence later choices.
- **Embodiment without puppeteering:** Somatic signals shape urgency, attention, and emotion, but do not automatically dictate voluntary behavior. Cognition can also feed appraisal back into bodily state.
- **Competing motives and mixed emotions:** Multiple feelings and priorities can coexist. The system represents ambivalence, hesitation, self-justification, and pressure rather than assigning one fixed mood or response.
- **Initiative and refusal:** A host can wake the individual without a message. They may pursue a plan, reconsider a past event, ask a question, decline a request, set a boundary, or do nothing.
- **Development:** Outcomes can change expectations and goal commitments; new goals can emerge while older goals become dormant, blocked, completed, or abandoned.
- **Individual expression:** Cards provide an initial voice; the host renders what the individual chooses to disclose, say, or withhold. A character-chosen dialect preference can persist across wakes.

These are **architectural capabilities, not a guarantee of human-equivalent cognition or spontaneous autonomy in every deployment**. Actual behavior depends on the host's decision model, scheduling, context, persistence, and tool permissions. The [project scope](PROJECT_SCOPE.md) documents the core/host boundary; [host integration](scripts/README.md#always-on-golem-loop) describes the persistent runtime.

## Draft a scene

1. Start with the book-writing guide and load the cards and durable logs for the characters present. [Drafting guide](Framework/Main.md) · [Character templates](Characters/README.md)
2. Check continuity against the movement brief. Work through the bodily response first, then the character's interpretation, social mask, and competing motives. Acute pressure can interrupt deliberation. [Drafting workflow](Framework/Drafting_Workflow.md) · [Continuity ledger](Framework/Continuity_Ledger.md)
3. Render dialogue and action in the manuscript. Keep the underlying framework vocabulary in the working notes. On approval, commit durable changes to the character log. [Rules index](Framework/rules_index.yaml)

To copy the framework into a book folder, run `python3 scripts/run.py deploy` from the checkout and select the intended target. [Deployment and lint tools](scripts/README.md)

## Run a persistent character

On a Linux VM, the host imports Golem and supplies a decision callback. Initialize one SQLite database per character. Call `wake_character` when a message arrives or when a scheduled heartbeat gives the character time to act. A quiet wake gives the host a chance to pursue an existing plan, reconsider an experience, or let the time pass.

```python
from scripts.golem_loop import initialize_character, wake_character

# Once, while provisioning the character
initialize_character(db_path, card_path, log=log_path)

# In the host's scheduled handler
wake_character(db_path, decide, compact=True)

# In the host's incoming-message handler
wake_character(db_path, decide, compact=True, event={
    "id": message_id, "kind": "incoming", "context": message_text,
})
```

The host provides the paths, message data, and `decide(request)` function. The callback returns a decision with the pending event's ID. It can include a reply, private action, observed outcome, or future plan. A pending decision survives a restart. The integration guide covers hourly scheduling, contextual boundaries, and delivery retries. [Host integration](scripts/README.md#always-on-golem-loop)

## Multiple characters on one machine

Use one checkout for the code and a persistent directory for the cast. Provision each character once, for example:

```bash
python3 scripts/run.py golem loop --characters-dir /srv/characters --character-id talia init --card /cards/talia.yaml
python3 scripts/run.py golem loop --characters-dir /srv/characters --character-id selene init --card /cards/selene.yaml
```

Each directory contains its own `character.yaml`, `character_log.yaml`, and `runtime.sqlite3`. The database holds that character's event queue, memories recorded through learning, goals, and decisions. A shared source card pack can supply both characters. Provisioning copies the selected entry into each directory. Use `--log` to seed the private log. Use the card's stable `character_id` when present. A standalone source card without one receives the chosen ID in its private copy. For a pack the default selection key is the requested ID.

Bind chat sessions, scheduled jobs, model history, delivery receipts, and any host-generated files to that directory's character. Return both `character_id` and `id` from the request when resolving a decision. Two characters can receive the same message ID independently.

Use the same character route for durable memory writes. For example, `golem loop --characters-dir /srv/characters --character-id talia remember memory.json` saves an approved memory to Talia's log. The host can store any extra transcript or snapshot files alongside her database.

```python
from scripts.golem_loop import character_database, initialize_profile, wake_character

# For a new installation this provisions the same layout as the CLI.
initialize_profile("/srv/characters", "talia", "/cards/talia.yaml")
# On each wake, the host supplies the ID bound to this chat or scheduled job.
db = character_database("/srv/characters", character_id)
wake_character(db, decide, event=event, compact=True, character_id=character_id)
```

For an existing character, pause its host and use `init --from-db /absolute/path/to/character.sqlite3` in a fresh profile directory to retain pending work and history. The source database is preserved. Existing single-character integrations can continue using `--db`. Golem now resolves relative file arguments from the caller's working directory. Use absolute paths for jobs that previously relied on checkout-relative paths. [Muse setup and import](Muse.AI/INSTALLATION.md)

## Update an existing host

Between wakes, run `git pull --ff-only` in the VM's Simulacra checkout on the release branch you follow. Restart any long-running host that imports Golem or caches the pipeline. A fresh process on each cron invocation loads the updated files on its next wake. Resume with the existing database, card, and log paths.

For a host running a copied installation, the release checkout supplies an in-place updater with a preview. The integration guide also covers refreshing learned expectations from older runs. [In-place update instructions](scripts/README.md#in-place-updates)

## Muse.AI

Muse uses the shared Python CLI and SQLite runtime through scheduled cognitive wakes. See the [Muse skill](Muse.AI/SKILL.md) and [installation guide](Muse.AI/INSTALLATION.md) for persistent paths, exact commands, and restart recovery.

## What carries forward

| Record | What it holds |
| --- | --- |
| Character card (YAML) | Authored identity, voice, motivations, and initial goals |
| Character log (YAML) | Approved durable changes, including cue-linked memories and amendments to goals |
| Golem snapshot (JSON) | Bodily and psychological state for one tick, validated against the [snapshot schema](Framework/Schemas/psychosomatic_state.json) |
| Character database (SQLite) | Event clock, pending decisions, plans, duration-based activity lifecycle, learning, and the evidence behind changing expectations and goals |

A character can turn down a rehearsal because they have to work, or turn it down on a free afternoon to teach someone else. Golem can record the first as a prevented opportunity and the second as a choice to pass. If that pattern matters to the character, the host can record teaching as a new ambition while preserving the love of music behind both goals. [Goal evolution](scripts/README.md#evolving-goals)

## Development

From the repository root, set up Python and run the checks used in this project. These commands were tested with Python 3.12 on Linux.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install PyYAML==6.0.3
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/run.py validate
```

Downstream applications can extend the pipeline through documented module hooks. The project scope describes the contract between Simulacra and its hosts. [Module registry](Framework/modules.yaml) · [Project scope](PROJECT_SCOPE.md) · [Changelog](CHANGELOG.md)

## License

[![License: PolyForm Shield 1.0.0](https://img.shields.io/badge/License-PolyForm%20Shield%201.0.0-blue.svg)](https://polyformproject.org/licenses/shield/1.0.0)

Simulacra is licensed under the [PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0) (`SPDX-License-Identifier: PolyForm-Shield-1.0.0`). It is free to use, including commercially, in your own projects. You just can't use it to build a product that competes with Simulacra. Questions or other uses: contact [cian.didymos@gmail.com](mailto:cian.didymos@gmail.com). [License](LICENSE) · [Disclaimer and age requirements](DISCLAIMER.md)
