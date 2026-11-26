# Project Scope and Objectives: Simulacra

**File Version:** 2.0.1 (Authoritative Product Alignment)  
**Target Audience:** Autonomous AI Agents, LLM Orchestrators, and Downstream Integration Tools  
**Repository Root:** `file:///mnt/Books/Source/Simulacra`  

---

## 1. Executive Summary & Product Boundaries

**Simulacra** is an invisible, file-native psychological and physical character runtime that emulates how a human mind and body respond under pressure.

It separates **character psychology and somatic simulation** from **downstream prose rendering and presentation UI**. System mechanics, psychological jargon, and internal scoring run **100% off-page** and never leak into manuscript prose or roleplay dialogue.

### Canonical Product Definitions

- **Product:** Invisible psych/physical character runtime; apps only render.
- **Modules:** Downstream injectors into the cognitive loop; optional; subordinate.
- **Sex in core:** Interpretation through the pipeline only — not craft, not modes.
- **Switches:** Ops and host policy only — not personality.

### What Simulacra IS NOT

- **NOT** a prose style pack.
- **NOT** an adult writing kit or erotica framework.
- **NOT** a plugin marketplace of genre content.
- **NOT** a set of "modes" that turn human behavior on or off.

---

## 2. Two-Tier Architecture

| Tier | Owns | Core Files |
|---|---|---|
| **Core Engine** | Mind-body simulation → intent vector (`Feels`, `Thinks`, `Says`, `Does`) | [Framework/CognitivePipeline.md](file:///mnt/Books/Source/Simulacra/Framework/CognitivePipeline.md), `realm_data.yaml`, state schema, [rules_index.yaml](file:///mnt/Books/Source/Simulacra/Framework/rules_index.yaml) |
| **Application Shells** | How intent vector is rendered into text or UI | [Framework/Main.md](file:///mnt/Books/Source/Simulacra/Framework/Main.md) (manuscript); downstream hosts (e.g. `CharacterSimulator`) |

```
                         Cognitive Pipeline
             (Framework/CognitivePipeline.md)
   Human Mind-Body Emulation → Feels / Thinks / Says / Does
                                 │
           ┌─────────────────────┴─────────────────────┐
           ▼                                           ▼
   Book Writing Layer                         Downstream Runtimes
   (Framework/Main.md)                  (CharacterSimulator)
 Novel Manuscript Prose                   Interactive Chat / Host UIs
```

---

## 3. Core Simulation Principles & Invariants

### 3.1 Body Before Insight & Polyvagal Modes
Autonomic nervous system reactions, polyvagal states (`ventral_grounded`, `sympathetic_mobilized`, `dorsal_freeze`, `dissociated_tunnel`), sensory tunneling anchors, and multi-zone somatic cascades (Z1–Z6) complete **before** labeled cognition or dialogue. The 4-channel vector (`Feels` → `Thinks` → `Says` → `Does`) preserves this neurobiological order in every tick.

### 3.2 Dual-Aspect Psyche & The Inner Split
Characters operate on paired **Wound ↔ Gift** vectors and experience authentic human internal division:
- **Subconscious Visceral Truth:** What the gut and nervous system know (e.g. terror of exposure).
- **Conscious Rationalization:** The self-deceptive narrative the ego constructs to maintain composure and control.
- **Defense Postures:** Specific survival strategies under threat (`intellectualize`, `fawn_placate`, `deflect_banter`, `cold_withdrawal`, `preemptive_strike`, `brace_stonewall`).

### 3.3 Social Masking & Persona Strain
Characters maintain a social facade (`facade_type`) under varying degrees of effort (`mask_strain` 0–100). When pressure exceeds coping limits, the state machine triggers a `mask_fracture`, leaking a concrete physical tell into `Does` or dialogue slip into `Says`.

### 3.4 Dynamic Priority Arbitration & Internal Friction
Competing internal drives arbitrate dynamically based on salience score:
$$\text{Salience} = (\text{Internal Intensity}) \times (\text{Context Multiplier}) \times (\text{Character Baseline Weight})$$
The engine tracks `internal_friction` (0–100) to measure cognitive dissonance between competing urges, driving hesitations, dialogue asymmetry, and somatic dissonance.

### 3.5 Interpersonal Momentum & Ambivalence
Relational vectors track directional velocity (`relational_momentum`: `building`, `deepening`, `stable`, `eroding`, `brittle`, `suspended`, `fractured`) and simultaneous conflicting feelings (`relational_ambivalence`).

### 3.6 Unified 2-Tier State Model
State is managed across two persistence tiers:
1. **Immutable Build Identity (`Characters/[slug].yaml`):** Full character profile, including voice, baseline weights, wound/gift, defense postures, motivations, goals, and incentives.
2. **Durable Runtime Log (`Characters/[slug]_log.yaml`):** Persistent evolution across movements/sessions (focus, weights, skills, detailed memories, relational baselines with momentum). Overrides card defaults.
3. **Live Ephemeral Snapshot (`Framework/Schemas/psychosomatic_state.json`):** Per-tick mind-body state (polyvagal mode, cognitive regime, autonomic scales 0–100, inner split, social mask strain/fracture, relational vectors, salience score, internal friction, 4-channel vector). Rewritten every tick.

### 3.7 Dual-Circuit Cognition & Limbic Short-Circuit
The runtime executes across two distinct neurobiological operational circuits:
- **Deliberative Regime (`deliberative`):** Cortical/regulated loop. Evaluates context, weighs competing drives via priority arbitration, maintains social masks, and generates reasoned rationalization in monologue and speech.
- **Reactive Regime (`reactive`):** Limbic short-circuit triggered by acute autonomic surge (stress/arousal ≥ 70) or threats to core autonomy/wounds. Prefrontal deliberation is bypassed; input is felt purely as autonomic impact rather than debate logic. Social masks collapse, arbitration is bypassed (`bypassed_reactive`), and the raw affective impulse discharges directly into reflexive motor action (`Does`) and vocal snaps/outbursts (`Says`). Synthetic capitulation and debate concession are strictly prohibited under activation.

---

## 4. Intimate & Sexual Stimulus in Core

Sex is **not a special subsystem or operational mode**. It is a standard class of stimulus processed through the normal pipeline:

1. **Nervous System (Visceral/Zones):** Autonomic arousal, pulse, skin temperature, Z1–Z6 tells.
2. **Raw Affect:** Immediate visceral impulse (attraction, shock, discomfort, warmth, pull).
3. **Subconscious Prism:** Filtered through upbringing, memory, culture, and wound/gift matrix (e.g., sex as debt, vulnerability, control, caretaking, threat, sacred connection, escape, or curiosity).
4. **Priority Arbitration:** Drive salience evaluation determining whether desire wins, freezes, deflects, approaches, or withdraws.
5. **4-Channel Vector:** Emits character **stance and intent** (`Feels`, `Thinks`, `Says`, `Does`).

### The One-Line North Star Rule for Sex
> **The pipeline determines how the person responds. The optional adult guide supports depiction at the host’s rendering stage.**

- **Emulation (Core):** Did they want it? How do they interpret it? Continuous and switchless. Always runs for adult characters when stimulus exists.
- **Depiction Policy (Host / Downstream):** May we print explicit sex in this session/book? Optional renderer ceiling (SFW / fade-to-black / explicit). Must **never** rewrite whether the human wanted it.

### Data Invariants
- `canon_adult` and `age` are identity/ToS data invariants (minors are never sexual subjects). This is a safety boundary, not a behavior toggle or mood switch.

---

## 5. Extension Registry & Module System

[Framework/modules.yaml](file:///mnt/Books/Source/Simulacra/Framework/modules.yaml) is the explicit extension API for downstream applications (book folders, tools, UIs) to inject behavior into the cognitive loop without forking the pipeline:

- **Loop Hooks:** Subordinate injectors at fixed points (`pre_somatic`, `affect_filter`, `pre_arbitration`, `post_vector`, `app_render`, `on_commit`).
- **Core Supremacy:** `rules_index.yaml`, pipeline sequence, card/log identity, and age invariants always win. Conflicting module instructions are silently ignored.
- **Empty Registry:** An empty active module list is completely valid. The core engine runs fully with zero `ENABLED` modules.
- **Downstream Ownership:** Downstream books register local modules in their copy of `modules.yaml`. The distribution includes an optional adult expression guide at the host-owned `app_render` hook.

---

## 6. Design Principle: Switchless & Automated Operations

If the goal is to emulate a human, **character behavior must not require switches, and state persistence must be automated**:

- **Switchless Psychology:** Humans do not have adult modes or mood switches; they have bodies, histories, bonds, and situations. Character psychology operates 100% switchlessly through continuous state math.
- **Automated Hands-Free Persistence:** State saving is completely automated. Live snapshots update every turn tick, and durable evolutions automatically merge into `_log.yaml` on scene breaks, movement ends, or session close per the pipeline commit protocol. Manual `/save` commands are eliminated.

| Automated / Developer Inspection Only | Eliminated Manual / Mode Switches |
|---|---|
| Automated durable log commit on scene close | Manual `/save` or `/adult on` commands |
| Automated live tick state snapshots | HEAT / COMPANION behavioral modes |
| Optional `/state` OOC for dev debugging | "Enable erotica module or they won't act sexual" |

---

## 7. System Components & File Map

| Path | Purpose | Downstream Impact |
|---|---|---|
| [Framework/CognitivePipeline.md](file:///mnt/Books/Source/Simulacra/Framework/CognitivePipeline.md) | Core psych/physical simulation engine specification. | Required execution spec for all mind-body ticks. |
| [Framework/Main.md](file:///mnt/Books/Source/Simulacra/Framework/Main.md) | Manuscript drafting engine specification & style lock rules. | Defines drafting session boot, ledger checks, anti-synthesis rules. |
| [Framework/modules.yaml](file:///mnt/Books/Source/Simulacra/Framework/modules.yaml) | Extension registry & loop hook specification. | Downstream module registration and core supremacy rules. |
| [Framework/rules_index.yaml](file:///mnt/Books/Source/Simulacra/Framework/rules_index.yaml) | Hard bans catalog and off-page matrix rules. | Enforced by AI agents and linter on all rendered text. |
| [Framework/Psychology/realm_data.yaml](file:///mnt/Books/Source/Simulacra/Framework/Psychology/realm_data.yaml) | 10-realm somatic body catalog (micro, moderate, macro, release, vocal). | Data source for physical tells in `Feels` and `Does`. |
| [Framework/Schemas/psychosomatic_state.json](file:///mnt/Books/Source/Simulacra/Framework/Schemas/psychosomatic_state.json) | Ephemeral live state schema. | Used by `scripts/validate_state.py` to validate state structure. |
| [Framework/linter.py](file:///mnt/Books/Source/Simulacra/Framework/linter.py) | Automated prose linter for system leaks and banned phrases. | CI/CD and pre-commit check for manuscript compliance. |
| [scripts/validate_state.py](file:///mnt/Books/Source/Simulacra/scripts/validate_state.py) | State structure & range validator. | Validates character log and live state files. |
| [deploy_framework.py](file:///mnt/Books/Source/Simulacra/deploy_framework.py) | Framework deployment & synchronization script. | Copies framework scaffolding into downstream book projects. |

---

## 8. Downstream Projects & Integration Contract

### 8.1 Context Load Budget
AI agents operating in downstream projects must follow the context loading protocol:

```
Mandatory Session Boot Stack (~2,760 - 3,500 words):
1. Framework/Main.md
2. Framework/CognitivePipeline.md
3. Framework/modules.yaml (Check ENABLED registry status)
4. Framework/rules_index.yaml
5. Framework/Psychology/realm_data.yaml
6. Characters/[slug].yaml (Card)
7. Characters/[slug]_log.yaml (Log overlay)
8. Framework/Continuity_Ledger.md
```

### 8.2 Hard Downstream Invariants for AI Agents

1. **Zero System Leaks (Off-Page Contract):** Agents MUST NEVER write framework terminology into draft prose or RP responses.
2. **Durable vs Live State Isolation:** Card is immutable build identity; Log is durable evolution; Live snapshot is per-tick ephemeral state.
3. **Age Data Invariant:** Minors (`canon_adult: false` or age < 18) are never sexual subjects.
4. **Style Locks & Anti-Synthesis:** Paragraphs close on sensory fact, raw action, or unanswered dialogue—NEVER interpretive summary.
5. **Module Subordination:** Core invariants always supersede module rules.
6. **Automated Audit Requirement:** Downstream prose must pass [Framework/linter.py](file:///mnt/Books/Source/Simulacra/Framework/linter.py) with 0 critical leaks.

### 8.3 Implementation Language Boundary (Do Not Forget)

**Simulacra is intentionally left alone as a language-agnostic product.** It is a file-native cognitive layer (markdown specs, YAML data, JSON schema) plus thin Python utilities (deploy, lint, validate). It is **not** a multi-language runtime monorepo.

| Lives in this repo | Does **not** live in this repo |
|---|---|
| Pipeline / rules / modules contracts | Compiled host engines (C#, Rust, Go, …) |
| Somatic catalogs and state schemas | GUI / TUI / service shells |
| Cross-platform Python ops scripts | Provider SDKs or app-specific logic |

**If a C#, Rust, Go, or other native implementation is needed, it is built downstream** — as a separate product that **consumes** this contract (intent vector, psychosomatic snapshot schema, module hooks, age invariants). Examples of that pattern already exist outside this tree. Those hosts may reimplement execution mechanics; they must not become the source of truth for psych/physical rules. Spec changes still land here first, then deploy or sync to consumers.

**Deploy reminder:** Framework deploys target allowlisted *framework trees* only (e.g. Midlayer, CharacterSimulator). Compiled host projects are not Framework trees and must not receive bulk markdown spray as if they were.

---

*This document serves as the authoritative scope and product alignment specification for Simulacra.*
