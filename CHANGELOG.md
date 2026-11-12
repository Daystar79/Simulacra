# Changelog

All notable changes to the **Simulacra** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to standard Semantic Versioning / chronological release tracking.

---

## [Unreleased] - 2026-08-18

### Added
- **Humanized State Machine Evolution:**
  - **Dual-Circuit Cognitive Architecture:** Added `cognitive_regime` (`deliberative` vs. `reactive`) to `autonomic_state` and `arbitration_status` (`arbitrated` vs. `bypassed_reactive`) to `priority_arbitration`. In `reactive` mode (acute stress ≥ 70, adrenaline surge, or core control threat), prefrontal deliberation is bypassed, social masks collapse, and raw affective `impulse` discharges directly into `Does` and `Says` as pure motor/vocal reflex.
  - **Anti-Sycophancy & Non-Concession Invariant:** Added explicit hard ban in `Rules_Index.md`, `CognitivePipeline.md`, and `CharacterRuntime.md` against synthetic surrender or conceding arguments to interlocutor logic when activated or when dominant/controlling/prideful traits are challenged.
  - **Autonomic Polyvagal Modes:** Added `polyvagal_mode` (`ventral_grounded`, `sympathetic_mobilized`, `dorsal_freeze`, `dissociated_tunnel`) and `sensory_tunneling` anchor tracking in `Framework/Schemas/psychosomatic_state.json`.
  - **The Inner Split & Self-Deception:** Added `subconscious_visceral_truth` (gut reality) vs. `conscious_rationalization` (ego self-deceptive narrative) to `subconscious_bias`.
  - **Defense Posture Taxonomy:** Added `defense_posture` enum (`intellectualize`, `fawn_placate`, `deflect_banter`, `cold_withdrawal`, `preemptive_strike`, `brace_stonewall`).
  - **Social Masking & Persona Strain:** Added `social_mask` block tracking `facade_type`, `mask_strain` (0–100), `mask_fracture`, and `fracture_tell`.
  - **Relational Momentum & Ambivalence:** Added `relational_momentum` (`building`, `deepening`, `stable`, `eroding`, `brittle`, `suspended`, `fractured`) and `relational_ambivalence`.
  - **Cognitive Dissonance & Friction:** Added `internal_friction` (0–100) to priority arbitration to model hesitation, ambivalence, and resistance between competing drives.
- **`PROJECT_SCOPE.md`:** Authoritative product boundaries and downstream integration contract (v2).
- **§8.3 Implementation Language Boundary:** Simulacra stays file-native + Python ops; C# / Rust / Go (or other) runtimes are downstream consumers only (v2.0.1).
- **Unified state model:** Durable `Characters/[slug]_log.yaml` vs live `Schemas/psychosomatic_state.json`, with commit mapping in `CognitivePipeline.md`.
- **Pipeline wiring:** Card, log, `realm_data.yaml`, and schema as required inputs; intimate stimulus as ordinary pipeline interpretation (§7.1).
- **State validator + example:** `scripts/validate_state.py` and `Framework/Schemas/examples/psychosomatic_state.example.json`.
- **Deploy:** Ships pipeline, schema, Modules registry, and `PROJECT_SCOPE.md`.
- **Automated test suite:** Added `tests/test_framework.py` covering state schema validation, linter patterns, and deploy decoupling.

### Changed
- **Product rename (2026-11-12):** CognitiveMiddleware → Simulacra. The repo was already named Simulacra; all in-repo product references now match it. The downstream .NET host previously called Simulacra in PROJECT_SCOPE §8.3 and the deploy comments is no longer named in those spots — it needs a distinct name if it still exists as a separate project.
- **Root Cognition Layer Focus:** Decoupled `CharacterRuntime` and `Simulator/` from Simulacra; interactive chat host runtimes are housed in downstream projects (`CharacterSimulator`). Simulacra remains purely the root psychological and physical cognition layer.
- **Product naming:** Paths and deploy self-ignore use **Simulacra**.
- **Sex in core = interpretation only:** Desire/stance via body → prism → arbitration → vector; no staging craft in core.
- **Switchless runtime:** Automated durable commit; `/adult` / HEAT behavioral modes removed from host docs; optional `/state` for debug only.
- **Modules as loop API:** Empty core registry; downstream apps register injectors; core supremacy intact.
- **`realm_data.yaml`:** Single-document YAML (`yaml.safe_load` compatible).
- **Log template v2:** `character_id`, `relational_baselines`.
- **Toolchain launcher & validation:** Integrated `validate` into `scripts/run.py` and added platform wrappers (`scripts/unix/validate.sh`, `scripts/windows/validate.ps1`, `scripts/windows/validate.cmd`).
- **Linter synchronization & accuracy:** Updated `Framework/linter.py` to audit new engine terms, polyvagal labels, defense postures, mask variables, and banned dialogue/beat markers, with contextual checks avoiding false positives on common English vocabulary.
- **Deployment hardening:** `deploy_framework.py` now preserves Unix file permissions (`+x`) via `shutil.copy2`, prunes `__pycache__` and private dirs from traversal, and cleans up retired files/directories in downstream targets.

### Removed
- **`Simulator/` & `Images/`:** Removed standalone chat host and rendering engine from this root cognition repository.
- **`Framework/Mechanics/erotica.md`:** Explicit sex craft is downstream-only; not shipped in core.
- **`migrate_optimized.py` & wrappers:** Retired spent optimization migration scripts from toolchain.

### Prior (2026-07-29)
- **Full-Body Anatomical Cascade Engine**, **Dual-Aspect Psyche (Wound & Gift)**, **Generative Prism**, gift catalog/hygiene, local agent safeguards, silent image prompts, instruction-to-constraint optimization, live image still routing.

---

## [1.2.0] - 2026-07-23

### Added
- **Character Engine Vocal Synthesis**: Introduced vocal behavior profiles, verbal defense mechanisms, conversational stance rules, and dual-register synthesis into character cards (`e868cce`).
- **Motion-Driven Visual Layer**: Integrated auto-rendering of image layers triggered dynamically by scene movement in `CharacterRuntime` (`45191eb`).

### Changed
- **Simulator Streamlining**: Refactored private `CharacterRuntime` to streamline author live testing and chat drop-ins (`74f4119`).
- **Private Directory Security**: Untracked `Simulator/Private/` from git and added default exclusion patterns to `.gitignore` (`81e1c79`).

---

## [1.1.0] - 2026-07-17

### Added
- **Embodiment Baseline Pipeline**: Added body-first physical and sexed/hormonal capacity baselines in `Framework/Main.md` to feed silently into runtime filters (`725e431`).
- **One-Switch `/adult` Toggle**: Added `/adult on|off` command in `CharacterRuntime` for quick activation of heat/intimacy protocols during private RP sessions (`725e431`).
- **Obsidian Visual Relations Canvas**: Added linkified character relationship structures and visual canvas support (`56724fe`).
- **World Builder & Degradation Protocols**: Integrated world builder prompt utilities and system degradation handling into core framework (`001dfc2`).

### Changed
- **Product Scope Refinement**: Positioned Simulacra as a 100% off-page drafting middle layer for fiction, categorizing `Simulator/` as an optional side tool (`a4d89b7`).
- **Module Renaming**: Renamed `Sexuality` module to `Erotica Protocol` (`erotica.md`) with act-agnostic scene craft scope (`725e431`, `872ac97`).
- **Dual Licensing Model**: Introduced hybrid MIT license for the core framework engine and CC BY-SA 4.0 for documentation (`0cf1d39`).
- **Local Character Separation**: Carved out named character cards (`Characters/`) from open distribution as author-local files (`9ac3ecb`).

---

## [1.0.0] - 2026-07-15 - 2026-07-16

### Added
- **Tripartite Filtering System**: Split character worldview into Cultural Bias & Occupation (background) and Cognitive Bias / Wound (dynamic situational filter) (`5804cdb`).
- **Transformation Engine & Depth of Knowledge**: Added transformation weights, memory recall filters, and somatic tell decay logs (`1bb8218`, `7527be4`).
- **Automated Prose Linter**: Integrated `Framework/linter.py` with cross-platform wrapper scripts (`scripts/run.py`, `scripts/unix/deploy.sh`, `scripts/windows/deploy.ps1`) (`9a3e658`).
- **Historical Character Importing & Safety Gates**: Added temporal awareness gating, historical character import rules, and visual appearance verification (`20bfed8`, `5328dc9`, `7a8019e`).

### Changed
- **YAML Frontmatter Optimization**: Converted verbose markdown character cards and realm profiles to pure YAML arrays (`realm_data.yaml`), reducing mandatory token load by 46%-57% (`261f48c`, `2c8f330`, `OPTIMIZATION_SUMMARY.md`).

---

## [0.9.0] - 2026-07-12 - 2026-07-14

### Added
- **Single Entry Point (`Main.md`)**: Consolidated load stack, workflow commands, and execution loop into `Framework/Main.md` (`7ec5732`).
- **Central Rules Index (`Rules_Index.md`)**: Consolidated hard bans, cleanup protocols, and dialogue rules (`23579c9`).
- **Somatic-Cognitive Engine**: Enforced "body-first, mind-second" sequence where somatic reactions precede cognitive labeling and dialogue (`humanity.md`).

### Changed
- **Project Rebranding**: Renamed project from *PsycheFramework* / *Psyche Framework* to **CognitiveMiddleware** (`35d2f4f`, `9b8b139`) — renamed again to **Simulacra** on 2026-11-12 (see [Unreleased]).
- **Off-Page Matrix Guarantee**: Hard-banned system jargon, realm numbers, bias names, and bracketed debug output from draft manuscript prose (`8a8cc6a`, `d8004e6`).
- **Modular Directory Restructure**: Moved chat playground tools to `Simulator/playground.md` and decoupled drafting runtime from live chat (`e8c5cc5`, `69f111d`).

### Initial Release
- **Initial Commit**: Established initial body-first psychological framework, 10 Realms somatic model, and markdown-native runtime (`030713d`).
