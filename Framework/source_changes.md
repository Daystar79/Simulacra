# Source Changes — Simulacra
*Changes made from original source material during this chat*

## 2026-07-31 — Pipeline runtime hardening + remove modules — **applied** (agent)

- **Naming:** Product/path strings standardized to **Simulacra**; portable relative links (no absolute `file:///mnt/...`).
- **Module system as loop API:** `Modules.md` restored/clarified — downstream apps register injectors into the cognitive loop; core pipeline stays fixed.
- **Unified state:** Durable `_log.yaml` vs live `psychosomatic_state` schema; commit map in `CognitivePipeline.md`.
- **Pipeline wiring:** Required inputs (card, log, realm_data, schema); realm catalog lookup; salience sources.
- **Deploy:** Ships `CognitivePipeline.md` + `Framework/Schemas/` + `Modules.md`; self-ignore `Simulacra`.
- **Apps:** Restored session boot / turn / style-lock orchestration in Main + CharacterRuntime without re-merging psyche.
- **realm_data.yaml:** Single YAML document for `safe_load`.

## 2026-07-24 — Instruction-to-Constraint Optimization Pass — **applied** (agent)

- **Problem:** Imperative and procedural instructions ("Do X", "Try to ensure Y", "Make sure to check Z") are less deterministic and consume higher token overhead than explicit constraints.
- **Framework/Main.md:** Refactored engine invariants, drafting workflow constraints, embodiment baseline rules, syntactical speech engine, epistemic memory, skill lookup, transformation engine, and turn execution into structured constraint blocks and decision tables using explicit `MUST`, `NEVER`, `SCOPE`, `PRECEDENCE`, and `INVARIANT` declarations.
- **Framework/Rules_Index.md:** Converted procedural cleanup, behavior, formatting, and dialogue lists into declarative constraint tables and invariant blocks.
- **Simulator/CharacterRuntime.md** + **Simulator/Private/CharacterRuntime.md:** Refactored Somatic Engine rules, Epistemic/Skill lookup, and Adult safety gates into explicit constraint tables with quantitative bounds (`MAX 1 tell per beat`) and strict safety invariants (`ALL GATES MUST PASS`).

## 2026-07-24 — Image prompt latency optimization & decoupling — **applied** (agent)

- **Problem:** Auto-generating full image prompts and stills on every turn loop beat added significant latency/overhead to RP interactions in CharacterRuntime.
- **Simulator/CharacterRuntime.md** + **Simulator/Private/CharacterRuntime.md:** Set `visual.mode: off` by default for zero RP turn latency. Added `/visual fast` mode (lightweight 1-line prompt tag stored in MEMORY without writing files or calling tools). Turn-loop step 13 skips visual pass entirely when `visual.mode == off` (0ms overhead). Manual frame generation remains available anytime via `/render`. Prompt files (`.prompt.md`) generated during live rendering or `/render` are automatically deleted/removed after still creation to avoid taking up disk space.
- **Images/CharacterRenderingEngine.md:** Decoupled auto-visual pass from mandatory turn execution; updated `In-turn companion` rules for `off` default, `fast` mode, and automatic post-render prompt cleanup.
- **Simulator/README.md:** Documented default `off` mode and `/visual off|fast|prompts|live` slash commands.

## 2026-07-24 — Image layer: auto-render on scene motion — **applied** (agent)

- **Problem:** CharacterRenderingEngine listed auto-triggers, but TURN LOOP never ran a visual pass; frames only appeared on manual `/render`. Scene movement did not produce output.
- **Simulator/CharacterRuntime.md** + **Simulator/Private/CharacterRuntime.md:** MEMORY.visual block; `/visual live|prompts|on|off`; rewrite VISUAL RENDERING PIPELINE as mandatory motion-driven layer; turn-loop step 13 = visual pass (fingerprint → prompt → live image_gen/image_edit continuity chain).
- **Images/CharacterRenderingEngine.md:** scene-motion triggers, live gen protocol (base then delta edits), in-turn agent integration required on every motion beat.

## 2026-07-17 — Rename Sexuality → Erotica module — **applied** (agent)

- **Rename:** `Framework/Mechanics/sexuality.md` → `Framework/Mechanics/erotica.md`
- **Modules.md:** Registry entry **Erotica Protocol** → path `erotica.md` (still `DISABLED`)
- **Title:** Protocol renamed; ambient desire remains Main middleware; this file is scene craft only (content pass still pending)

## 2026-07-17 — Main: embodiment baseline → runtime filters — **applied** (agent)

- **Main.md (Psyche Matrix Core):** Added **Embodiment Baseline → Runtime Filters** pipeline. Body (card physical + sexed/hormonal capacity when established) sets silent baseline and low-amplitude ambient attraction/aversion; culture, occupation, Focus, belief/voice, memory, Bias, and scene pressure filter final output. No default eroticization; erotica/intimacy scene craft deferred to ENABLED modules. Explicitly bans generic sex-stereotype scripts.
- **Execute on Movement:** Steps reordered — body baseline → filters → Focus/Bias → body-first prose → prism → modules → transform → bans → commit.

## 2026-07-17 — Simulator `/adult on` one-switch for private RP — **applied** (agent)

- **Problem:** Private RP partners had to juggle `/18+ on` + `/mode heat` + bond friction; no single toggle.
- **Simulator/CharacterRuntime.md:** Added `/adult on|off` (aliases `/heat on|off`; `/18+ on|off` still sets auth). Sets `adult_auth` + HEAT when canon adult. Softens HEAT decision-tree friction on clear mutual intent (still hard_bans / bias tripwires / age gates). Added `/bond set …` for established-relationship setup. MEMORY field `adult_auth`. Boot + quick-start copy updated.
- **Simulator/README.md** + root **README.md:** Document the one-switch path for private live RP.

## 2026-07-13 — Finish Main entry path (post-refactor cleanup) — **applied** (agent)

- **Main.md:** Honest load protocol (always Main + Rules_Index + realm_data.yaml + cards); strip RP opening beat / CONFIG / `/debug`; add Prism §3c; de-B&L brief template; drafting-only execute loop; author commands cleaned.
- **Rules_Index.md:** Drafting-first; playground reduced to pointer; generic phrase watchlist; book-local watchlist optional.
- **Stubs:** `psyche_framework.md`, `Drafting_Workflow.md` → point at Main (do not load for gen).
- **Mechanics:** `humanity.md` / `voices.md` slimmed to optional supplements; prose.md marked optional detail.
- **deploy_framework.py:** Ships Main + Rules_Index first; keeps stubs for overwrite of old book installs.
- **Characters/README** + `_template` point at Main; samples/ removed again.

## 2026-07-13 — Remove Web/; Simulator/ holds playground — **applied** (agent)

- **Deleted** `Web/` (mirrored flat copies no longer used).
- **Created** `Simulator/`; moved root `playground.md` → `Simulator/playground.md`.
- Updated links in `psyche_framework.md`, `Characters/README.md`; relative path in playground to `../Framework/Mechanics/humanity.md`.
- `deploy_framework.py`: distribute `Simulator/` (+ playground path); dropped `Web` from deploy dirs.

## 2026-07-13 — Ban debug dump in drafts/samples/prose — **applied** (agent)

- **Problem:** Models were writing playground-style `[bracket]` somatics, matrix-notes footers, and engine jargon (`Prism intercept`, bias names, realm labels) into `samples/` and draft prose.
- **Engine:** Hard bans added to `Drafting_Workflow.md` cleanup, `psyche_framework.md` Scene Audit (internal only), `prose.md` output modes table, `humanity.md` output hygiene, and `playground.md` output + turn loop + hard bans.
- **Rule:** Audits and turn-loop math stay silent. Prose/draft/sample files get narrative only (optional short pre-scene header above `---`). Brackets = playground chat mode only; body-only, no labels.

## 2026-07-12 — Token Usage Optimization (Psychology Index) — **applied** (agent)

- **Psychology Realm Data:** Created [realm_data.yaml](./Psychology/realm_data.yaml) to consolidate the somatic focus, release/passage states, bracing/remnants, and keys of all 10 Realms in one dense YAML document.
- **Loading Protocol update:** Updated `psyche_framework.md` and its copy `Web/psyche_framework.md` to load only `realm_data.yaml` by default, reducing the token overhead of loading individual realm files by thousands of tokens. Individual realm files are now only loaded for deep somatic audits.

## 2026-07-12 — Refactor & Auditing — **applied** (agent)

- **Humanity Protocol optimizations:** Refactored `humanity.md` and `Web/humanity.md` to organize human behavior rules under a clean bulleted `Core Rules` schema. Added a strict **Per-body-zone rule** to somatic pacing (limiting somatic updates to one explicit tell per body zone per turn/beat to prevent redundant visual/lexical ticks).
- **Prose Style Auto-Locking:** Updated `prose.md` and `Web/prose.md` to introduce an auto-lock mechanism. If the style is `UNLOCKED` after the first character response, the engine automatically sets `Style Lock = LOCKED` to `llm` to prevent register drift. Restricted `UNLOCKED` to mean "user can change freely" rather than allowing model self-migration.

## 2026-07-12 — Somatic-Cognitive Sequence — **applied** (agent)

- **Somatic-Cognitive Sequence rule:** Added a rule under the physicality guidelines in `humanity.md` and its copy `Web/humanity.md` enforcing the biological constant of "body first, mind second". The body reacts instantly to inputs before the cognitive labeling or dialogue occurs.
- **Dynamic Turn Loop processing:** Updated `playground.md` and `Web/playground.md` to require the immediate depiction of a somatic reaction *before* any cognitive labeling, rationalization, or dialogue is spoken, followed by cognitive catch-up allocating 1 Primary and 2-3 Secondary Realms.

## 2026-07-12 — Wound Activity & Dormancy — **applied** (agent)

- **Wound activity and dormancy protocol:** Added `Wound Activity & Dormancy (Active vs. Dormant)` rules to `humanity.md` and its copy `Web/humanity.md` to prevent characters from being constantly defensive. Wounds (Cognitive Biases) and somatic tells remain dormant in casual or low-stakes situations, allowing characters to communicate normally.
- **Bias State tracking:** Added `Bias State` (`ACTIVE` or `DORMANT`) to the live session configuration in `playground.md` and `Web/playground.md`. By default, wounds are dormant in mundane situations, activating only under specific triggers, emotional pressure, or manual command.
- **Turn loop updates:** Updated the Turn Loop in the playground to bypass cognitive misconstrual, somatic bracing, and prism distortion when `Bias State = DORMANT`. Mapped `/bias active` and `/bias dormant` commands to toggle this state.

## 2026-07-12 — Dynamic Canon Character Synthesis — **applied** (agent)

- **Dynamically Synthesized Characters:** Removed pre-baked custom demo characters (Reed, Helen, Cass, Wren, Nora, Lior) from `playground.md` and `Web/playground.md` to drastically reduce token count.
- **Canon Synthesis engine:** Instructed the AI to dynamically generate character cards on the fly using standard card structures (Focus, Latents, Bias, Somatics, Voice) when the user names any well-documented fictional character.
- **Boot sequence updates:** Updated the engine to boot directly by prompting the user to name a fictional character to begin, rather than loading a default card.

## 2026-07-12 — Dynamic Focus Shifting — **applied** (agent)

- **Dynamic Focus Shifting protocol:** Added rules to `psyche_framework.md` and its copy `Web/psyche_framework.md` to allow the AI to automatically shift the active Focus of a character based on the immediate scene context and emotional pressure, unless locked.
- **Focus Lock state machine:** Introduced `Focus Lock` (`UNLOCKED` or `LOCKED`) to the live session configuration in `playground.md` and `Web/playground.md`. Manual commands like `/focus N` set `Focus Lock = LOCKED`, while `/focus unlock` and `/reset` restore it to `UNLOCKED`.
- **Turn loop updates:** Modified the Turn Loop to evaluate and update the active Focus on every turn if the lock is `UNLOCKED`.

## 2026-07-12 — Somatic Pacing and Decay — **applied** (agent)

- **Somatic pacing rules:** Added `Somatic Pacing & Decay (Pacing Limits)` rule to `humanity.md` to ensure somatic tells do not behave like repetitive "idle animations". States are persistent; tells are limited to once per major beat, shifting across different body zones.
- **Playground updates:** Updated `playground.md` and its copy `Web/playground.md` to change the instruction from printing somatics in brackets "every turn" to only printing them when the somatic state shifts, intensifies, or releases. Added a hard ban against repetitive somatic tells or idle ticks.
- **Web copies synced:** Synced `Web/humanity.md` and `Web/playground.md` with these updates.

## 2026-07-09 — playground.md drop-in chat file — **applied** (agent)

- **Primary drop-in:** `Web/playground.md` (and root `playground.md` copy) — attach/paste entire file into a chat, then name a character and interact.
- No nested code fence (whole file is the engine). Human how-to at top; AI activation rules when file is in context.
- Boot: file alone or "start" → Reed; name in same message → load that character.
- `psyche_playground_poc.md` redirected to `playground.md`. Framework pointer updated.


## 2026-07-09 — Mechanics rename to short names — **applied** (agent)

- Renamed `Framework/Mechanics/`: `humanity_protocol.md` → `humanity.md`, `sex_master_protocol.md` → `sexuality.md`, `voice_protocol.md` → `voices.md`, `prose_style_protocol.md` → `prose.md`.
- Web copies renamed to match: `humanity.md`, `sexuality.md`, `voices.md`, `prose.md`.
- Updated all internal links and location lines across Framework, Web, Characters, natural_prose, formatting_rules.
- Normalized remaining “Sex Master” labels to Sexuality Protocol where appropriate.

## 2026-07-09 — Prose style lock-on-select — **applied** (agent)

- **Style Lock field:** `UNLOCKED` at session start with default `llm`; first explicit style choice sets style and **LOCKED**.
- **While locked:** no silent drift; refuse casual restyle; change only via `/style unlock` then reselect, `/style force <id>`, or `/reset`.
- **Session-level:** character swaps do not clear locked style.
- **Brief = lock:** drafting `Prose Style: <id>` treated as locked for that pass.
- Updated `prose.md`, `psyche_framework.md` §0a, playground CONFIG/commands/turn loop; Web synced.

## 2026-07-09 — Prose style selector (default = LLM) — **applied** (agent)

- **Selectable prose styles:** Added `Framework/Mechanics/prose.md` with catalog: `llm` (default), `natural` (optional house/Anthony–Barker asymmetric pack), `clean`, `literary`, `hardboiled`, `cinematic`, `minimal`, `romantic`, `custom`.
- **Default is model prose:** Sessions no longer auto-apply jagged natural_prose rules. User must choose `natural` (aliases: house, asymmetric, anthony, barker, anthony/barker, anti-ai).
- **natural_prose.md:** Marked optional style pack; points to selector; not applied automatically.
- **psyche_framework.md:** New §0a Prose Style.
- **Playground POC:** Live field Prose Style; §5a catalog; `/style` commands; hard ban on forcing house texture under `llm`; CONFIG CARD shows style; `/reset` restores `llm`.
- **Web sync:** `prose.md` + updated framework/playground.

## 2026-07-09 — Character-first load + Canon Adult 18+ gate — **applied** (agent)

- **Character-first model:** Named characters are the unit of load. Naming a character pulls their card (matrix, voice, somatic, age, Canon Adult) and runs from that data. Archetypes A–F are build templates only.
- **Characters directory:** Added `_template.md`, `README.md`, and demo cards `reed`, `helen`, `cass`, `wren`, `nora`, `lior` (all Canon Adult YES for demos).
- **18+ gate:** Sexuality Protocol requires **Canon Adult: YES** on the character card **and** explicit enable. Canon Adult NO / under 18 / unclear → permanent lock; no age-up. Switching to a non-adult card forces 18+ OFF.
- **Playground POC:** Rewrote single prompt for character load (`/character Name`, natural language names, `/list`, `/create` with required adult field), embedded directory, eligibility on CONFIG CARD.
- **Protocols:** Updated `sexuality.md`, `psyche_framework.md` §0, `humanity.md` intimacy pairing rule; synced Web copies.

## 2026-07-09 — Single-prompt POC + archetype canon + realm fixes — **applied** (agent)

- **Single-prompt playground:** Rebuilt `Web/psyche_playground_poc.md` as a fully self-contained pasteable system prompt (boot sequence, live config, matrix rules, bias catalog, 10-realm DB, A–F presets, deep focus, slash commands, hard bans, turn loop). No external files required for web LLM demos.
- **Archetype A–F canon:** Unified defaults across `voices.md`, `humanity.md`, `psyche_framework.md`, and playground (A: Focus 8 Debt Ledger; B: 6 Saviour; C: 4 System Architect; D: 7 Mirror; E: 6 Insulation; F: 9 Dissolution). Added missing E voice profile; aligned Focus examples with playground.
- **Bias catalog:** Formalized six core wounds with trigger/rewrite/hearing warp/somatic tell/passage opposite in `psyche_framework.md` and the playground.
- **Great Wheel:** Added sequence/zone load notes (Internal I–V / External VI–X) to framework + playground.
- **Realm VIII:** Mapped Remnant Gate; de-novelized Remnant Lament (removed journalist/source/job bleed).
- **Realm diagnostics:** Added fourth looping signs for Realms V and VI.
- **Typos:** Fixed one's / everyone else's / another's in realm somatic lines (I, III, VI).
- **Web sync:** Refreshed `Web/` copies of psyche_framework, voices, humanity, sexuality from Framework sources.
- **Playground ergonomics:** Scene seed auto-boot, `/mode playground|prose`, `/deep N`, `/seed`, `/latent`, `/somatic`, `/card`, `/reset`; removed `/character mara` novel bleed; never-name-the-system rule.

## 2026-07-09 — Imperfect Recall, Deflection, and Optional Sexuality Protocol — **applied** (agent)

- **Imperfect Recall & Deflection:** Added rules for natural decay, blur, and deflection in human memory to `psyche_framework.md` (both Framework and Web copies), `humanity.md`, and `psyche_playground_poc.md`.
- **Optional Sexuality Protocol:** Configured `sexuality.md` to be strictly optional and restricted to 18+ content only. Updated references across all prompts and general files. Added default-disabled status and playground controls to `psyche_playground_poc.md`.
- **Natural Human Behaviors:** Integrated key rules from `natural_prose.md` directly into the playground proof of concept prompt (`psyche_playground_poc.md`), explicitly instructing the AI to use conversational asymmetry (dialogue drift), physical fumbles/clumsiness (keys, sticky drawers), anti-synthesis (no narrative summary endings), and asymmetric sensory focus/blindness to ensure characters act realistically rather than like database systems.
- **Voice Protocol Generalization:** Completely removed specific novel character references (Thomas, Valen, Maya, Mara, Rue, Selene, Talia, Anastasia) from `voices.md` (both Framework and Web copies), converting specific character profiles into generic voice archetypes (Archetypes A, B, C, and D) and translating all polarization examples and rules into generic equivalents to fit the general psyche framework.
- **Cognitive Misconstrual (Biased Hearing):** Formulated rules for conversational bias where characters do not receive spoken dialogue objectively, but rather warp, misinterpret, or misconstrue incoming statements through their core cognitive bias and active focus loop. Added this to `psyche_framework.md` (Section III point 3), `humanity.md` (Rule 1 behavior and summary), and `psyche_playground_poc.md` (Section B protocol instructions).
- **Playground Proof of Concept Renaming:** Renamed the web roleplay prompt file from `psyche_roleplay_prompt.md` to `psyche_playground_poc.md` and updated its H1 and prompt headers to explicitly serve as a modular, general playground and proof of concept for the Psyche Matrix system rather than a character-specific module.
