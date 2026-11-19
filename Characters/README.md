# Characters Directory

Named fictional people are the **unit of load**. Archetypes A–F are voice/matrix templates only ([Main.md](../Framework/Main.md), [voices.md](../Framework/Mechanics/voices.md)).

## Card vs log vs live snapshot

| File | Role |
|:---|:---|
| `Characters/[slug].yaml` | **Full character card** — identity, voice, psyche, history, relationships, motivations, goals, and incentives |
| `Characters/[slug]_log.yaml` | **Durable runtime** — snapshot, history, and goal progress |
| Live snapshot | **Per-tick** psychosomatic state (`Framework/Schemas/psychosomatic_state.json`) from the Cognitive Pipeline |
| [`_log_template.yaml`](./_log_template.yaml) | Schema scaffold for new durable logs |

Do **not** write movement deltas onto the card. Durable evolution commits go to the log (see [CognitivePipeline.md](../Framework/CognitivePipeline.md) §8 and [Character_Change_Log.md](../Framework/Character_Change_Log.md)). Scene close goes to [Continuity_Ledger.md](../Framework/Continuity_Ledger.md).

## Card format

Each card is a single YAML document. Use the [full template](./_template.yaml) for the field layout. To migrate an old Markdown card, copy its YAML to `Characters/[slug].yaml` and keep the existing log under the same slug.

Use stable keys for motivations, goals, and incentives so the card and log can refer to the same entries. A goal can reference a motivation, and an incentive can reference the goal it affects.

```yaml
motivations:
  protect_family:
    reason: "She promised her father she would look after her sister."
    awareness: conscious
goals:
  bring_sister_home:
    objective: "Get her sister home before the bridge closes."
    horizon: scene
    motivation: protect_family
incentives:
  quiet_route:
    trigger: "The ferry operator offers a private crossing."
    stake: "Avoid the bridge guards at the cost of owing the operator a favor."
    goal: bring_sister_home
```

Record approved changes in `goal_updates` in the durable log, keyed by goal ID. An update may revise the objective, motivation, horizon, commitment, progress, or status. Supported statuses are active, blocked, dormant, completed, and abandoned. A new goal ID with an objective records an ambition formed during play. A new goal may share an existing motivation.

## Drafting flow

1. Author names on-scene characters.
2. Load the full `Characters/[slug].yaml` (or a pasted YAML card).
3. Overlay `Characters/[slug]_log.yaml` when present.
4. Run [CognitivePipeline.md](../Framework/CognitivePipeline.md) with realm_data + trigger → live snapshot + 4-channel vector.
5. [Main.md](../Framework/Main.md) + [Rules_Index.md](../Framework/Rules_Index.md) render manuscript prose.
6. On approval: commit durable fields to log + Continuity_Ledger (not the card).

## Files

- [`_template.yaml`](./_template.yaml) — **public** card scaffold (CC BY-SA 4.0)
- [`_log_template.yaml`](./_log_template.yaml) — **public** log schema (CC BY-SA 4.0)
- [`README.md`](./README.md) — this file (public format docs)

See [LICENSE.md](../LICENSE.md) §3 for the carve-out. Downstream projects can start from the public card and log templates.

## Downstream runtime testing

Drafting uses this folder + Framework. For interactive chat testing or runtime simulation, use the downstream `CharacterSimulator` project, which consumes these character cards and durable logs.

## Adding a novel character

1. Copy `_template.yaml` → `Characters/[slug].yaml` (or run [character_builder_prompt.md](../Framework/Prompts/character_builder_prompt.md))
2. Copy `_log_template.yaml` → `Characters/[slug]_log.yaml`; seed snapshot from the card (`as_of: build`); leave `history: []`
3. Add a Snapshot row in [Character_Change_Log.md](../Framework/Character_Change_Log.md)
4. Fill in identity, psychological profile, motivations, goals, and incentives from the character setup.
5. Voice: nearest A–F base under `voice:`, then override with idiolect on the card
6. Drafting: load Main + Rules_Index + realm_data.yaml + card + log (+ Continuity_Ledger)
