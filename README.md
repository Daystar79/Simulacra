# Simulacra

Simulacra is a framework for writing and running fictional characters who carry experience from one scene into the next. Authors use it to draft long-form fiction. An LLM host can also use it to run a persistent character between conversations.

Golem, the Python body engine, advances scene time and calculates what the character feels. Simulacra uses the character's memories, motives, relationships, and immediate circumstances to shape what they think, say, and do. The host renders the scene in the character's voice. [Cognitive pipeline](Framework/CognitivePipeline.md)

## Draft a scene

1. Start with the book-writing guide and load the cards and durable logs for the characters present. [Drafting guide](Framework/Main.md) · [Character templates](Characters/README.md)
2. Check continuity against the movement brief. Work through the bodily response first, then the character's interpretation, social mask, and competing motives. Acute pressure can interrupt deliberation. [Drafting workflow](Framework/Drafting_Workflow.md) · [Continuity ledger](Framework/Continuity_Ledger.md)
3. Render dialogue and action in the manuscript. Keep the underlying framework vocabulary in the working notes. On approval, commit durable changes to the character log. [Rules index](Framework/Rules_Index.md)

To copy the framework into a book folder, run `python3 scripts/run.py deploy` from the checkout and select the intended target. [Deployment and lint tools](scripts/README.md)

## Run a persistent character

On a Linux VM, the host imports Golem and supplies a decision callback. Initialize one SQLite database per character. Call `wake_character` when a message arrives or when a scheduled heartbeat gives the character time to act. A quiet wake gives the host a chance to pursue an existing plan, reconsider an experience, or let the time pass.

```python
from scripts.golem_loop import initialize_character, wake_character

# Once, while provisioning the character
initialize_character(db_path, card_path, log=log_path)

# In the host's scheduled handler
wake_character(db_path, decide)

# In the host's incoming-message handler
wake_character(db_path, decide, event={
    "id": message_id, "kind": "incoming", "context": message_text,
})
```

The host provides the paths, message data, and `decide(request)` function. The callback returns a decision with the pending event's ID. It can include a reply, private action, observed outcome, or future plan. A pending decision survives a restart. The integration guide covers hourly scheduling, contextual boundaries, and delivery retries. [Host integration](scripts/README.md#always-on-golem-loop)

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

Downstream applications can extend the pipeline through documented module hooks. The project scope describes the contract between Simulacra and its hosts. [Module registry](Framework/Modules.md) · [Project scope](PROJECT_SCOPE.md) · [Changelog](CHANGELOG.md)

## License

[![License: PolyForm Shield 1.0.0](https://img.shields.io/badge/License-PolyForm%20Shield%201.0.0-blue.svg)](https://polyformproject.org/licenses/shield/1.0.0)

Simulacra is licensed under the [PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0) (`SPDX-License-Identifier: PolyForm-Shield-1.0.0`). It is free to use, including commercially, in your own projects. You just can't use it to build a product that competes with Simulacra. Questions or other uses: contact [cian.didymos@gmail.com](mailto:cian.didymos@gmail.com). [License](LICENSE) · [Disclaimer and age requirements](DISCLAIMER.md)
