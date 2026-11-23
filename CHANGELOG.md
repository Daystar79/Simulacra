# Changelog

## Unreleased

### Added

- Added per-character directories with private card and log copies, independent SQLite databases, and character-scoped decisions and receipts. Existing character databases can be imported with pending work intact. Relative Golem paths follow the calling host’s working directory.

- Muse can prepare one compact decision and receive the accepted reply directly on resolution. Golem calculates concurrent emotion intensities on the tick. Simulacra receives their values and chooses how to respond.

- Added `deploy --update INSTALL_DIR` for refreshing copied installations in place and `--check` to preview changed runtime files. Existing character state and host files stay in place.

### Fixed

- Incoming message text now reaches memory recall, echo detection, and recent conversation context across supported transport fields. Older free-text memory entries can coexist with cue-linked records.
- Malformed expectation context can no longer stall later turns. Python retries recover the accepted reply by event ID, and Golem CLI results can be parsed directly as JSON.
- Character deletion clears activity records and archived requests. Opening an older deleted runtime also clears residual rows in those tables.

- Incoming host requests now carry guidance for deciding what a character believes and what they will disclose to the current listener. Hosts can pass a private memory cue separately from the visitor's words in `event.host_notes`.

- Topic expectations learn from reported outcomes. Interest and stress changes are recorded separately, preventing an intense reaction from inflating both scores.

- General activation now responds to sleep, rest, exertion and sensory load. Both activation fields persist their computed response and recover over scene time. Eligible adult snapshots expose separate sexual excitation and inhibition. A cue can produce different bodily responses under calm and stressful conditions, and sustained sleep can produce a response without an interpersonal cue. Hosts can return an appraisal on an ordinary decision and inspect the immediate bodily change.

### License · November 19, 2026

- Relicensed the project under the [PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0) (`SPDX-License-Identifier: PolyForm-Shield-1.0.0`). It is free to use, including commercially, in your own projects. You just can't use it to build a product that competes with Simulacra. Questions or other uses: contact cian.didymos@gmail.com. This replaces the PolyForm Noncommercial 1.0.0 terms published earlier the same day.

### Persistent characters · November 19, 2026

- Added a Python host API for one persistent Golem runtime per character. Timestamped events advance bodily state across restarts. The SQLite loop handles incoming messages, scheduled plans, neutral idle wakes, and pending decisions.
- Added selective memory and topic-based learning. An approved memory can persist after a low-pressure turn. A host can record a discovery with its sources and retrieve it when the subject returns.
- Added conversational intents for curiosity, pushback, and declining help. General autonomic activation can accompany curiosity. The host's reply check flags eight consecutive words copied from descriptive character-card fields.
- Added contextual boundary handling. The host can state a limit or end contact. A privately owned character can opt into deletion of registered files and runtime data after two distinct confirmed end-session incidents from the same actor.
- Added independent estimates of expected benefit and cost for each topic. Event assessments preserve the forecast, reported outcome, and bodily response that shaped the next estimates.
- Added evolving goals. The host can record formation, revision, dormancy, resumption, completion, and abandonment, along with evidence of opportunities pursued, passed, or prevented. Changes survive restarts and approved amendments can be merged into the YAML log.
- Added regression tests for memory and rendering, event ordering, host retries and overlapping wakes, boundary handling, deletion recovery, and goal evolution.

### Framework and tooling · July–November 2026

- Renamed CognitiveMiddleware to Simulacra on November 12. The core project supplies character cognition, Python utilities, and drafting guidance. Interactive chat hosts and visual rendering moved downstream. The standalone simulator and image directories were removed from the core repository.
- Expanded the body-first pipeline with deliberative and reactive circuits, autonomic modes, involuntary responses, sensory tunneling, and arbitration bypass under acute pressure. Added the inner split, defensive postures, social mask strain, relational ambivalence, and friction between competing drives.
- Extended the somatic model with a full-body cascade, wound and gift responses, and the Generative Prism. Updated dialogue rules to preserve character agency under pressure and the linter to detect framework vocabulary leaking into prose.
- Documented how character cards, durable YAML logs, and live JSON snapshots fit together. Added the snapshot schema, example, validator, and framework tests. Version 2 of the log template introduced character IDs and relational baselines.
- Defined module hooks and the downstream integration contract. Core handles the interpretation of intimate stimuli. Staging guidance moved downstream, and the legacy adult-mode switches were removed.
- Updated deployment to include the pipeline, modules, schema, and project scope. Deployment preserves Unix executable permissions, excludes caches and private directories, and cleans up retired framework files. Added cross-platform validation wrappers, consolidated realm data into one YAML document, and retired the optimization migration scripts.

## 1.2.0 · July 23, 2026

- Added character voice profiles covering verbal defenses, conversational stance, and shifts in register.
- Added post-movement still-image cues to the then-separate simulator, streamlined its author testing workflow, and excluded its private test directory from Git.

## 1.1.0 · July 17, 2026

- Added full-body somatic responses to the drafting guide and introduced the historical runtime's adult-mode toggle.
- Added relationship maps, scene-design and world-building prompts, and guidance for handling missing or degraded character data.
- Established the division between the drafting framework and the roleplay simulator. Introduced MIT licensing for executable code, CC BY-SA 4.0 for framework materials, and separate terms for author-local character assets.

## 1.0.0 · July 15–16, 2026

- Separated cultural and occupational background from the character's active cognitive bias. Added transformation weights, selective recall, knowledge limits, and decay of repeated somatic tells.
- Added prose linting and cross-platform launchers, historical character import rules, temporal awareness checks, and visual identity verification.
- Converted character cards and realm profiles to YAML to reduce the context required to load them. [Optimization summary](OPTIMIZATION_SUMMARY.md)

## 0.9.0 · July 12–14, 2026

- Established the body-first framework and ten-realm somatic model. Consolidated drafting instructions in `Framework/Main.md` and output rules in `Framework/Rules_Index.md`.
- Renamed PsycheFramework to CognitiveMiddleware, separated the chat playground from the drafting workflow, and added rules for keeping engine terminology out of manuscripts.
