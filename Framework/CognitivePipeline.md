# Cognitive Pipeline Specification
*Psychosomatic simulation & behavior prediction engine · Simulacra · Version 2.1*

---

## 1. Purpose

The **Cognitive Pipeline** is the psychological / physical runtime for a character. It models mind-body neurobiology, subconscious perception, relational dynamics, and behavior intent.

It is **application-agnostic**: the root pipeline serves manuscript drafting (`Main.md`) and downstream interactive hosts (e.g. `CharacterSimulator`).

### Downstream decoupling contract
| Pipeline owns | Pipeline does **not** own |
|---|---|
| Autonomic reaction, affect, prism, priority arbitration | Manuscript prose style, anti-synthesis, style locks |
| 4-channel intent vector (`Feels` / `Thinks` / `Says` / `Does`) | Chat UI, OOC commands, turn-taking presentation |
| Active volition, goal-driven inquiry, probing interlocutor motives | Continuity ledger chapter rows, draft file I/O |
| Live psychosomatic snapshot (schema below) | Optional craft guides under `Mechanics/` |
| Somatic catalog lookup from `realm_data.yaml` | |

---

## 2. Required inputs (must load before a tick)

| Input | Path | Role |
|---|---|---|
| **This spec** | `Framework/CognitivePipeline.md` | Execution sequence & commit rules |
| **Realm somatics** | `Framework/Psychology/realm_data.yaml` | Brace / release body catalogs per realm |
| **Character card** | `Characters/[slug].md` | Identity, voice, build defaults, wound/gift, weights |
| **Durable log** | `Characters/[slug]_log.yaml` | Runtime evolution over card defaults |
| **Event trigger** | Movement brief / player turn / scene pressure | Sensory + social stimulus |
| **Schema** | `Framework/Schemas/psychosomatic_state.json` | Shape of the live snapshot |

### Modules (downstream injectors)
`Framework/Modules.md` is the **extension registry**. Downstream applications register modules there to inject into this loop at defined hooks (`pre_somatic`, `affect_filter`, `pre_arbitration`, `post_vector`, `app_render`, `on_commit`).

- Core sequence and state model always run.
- Only modules with Status `ENABLED` and a present file load.
- Modules are subordinate: they must not override Rules_Index, this pipeline’s invariants, card/log supremacy, or age gates.
- Full contract: [Modules.md](Modules.md).

### Card fields the pipeline reads
- `active_focus`, `latent_anchors` → realm keys into `realm_data.yaml`
- `transformation_weights` (or log overlay) → baseline drive weights & bias_strength
- `cognitive_bias` / `cognitive_gift` → prism rewrite rules (Wound / Gift)
- `default_somatic_alignment` → ambient body baseline
- `voice.*` → shapes `Says` (idiolect, defense, generative stance)
- `history_anchors` + log `memories.*` → epistemic gating
- `skills.active` / `skills.latent` (from log when present) → competence in `Does`
- `canon_adult` / `age` → hard eligibility for intimate affect (apps enforce presentation)

### Log overlay rule
When `Characters/[slug]_log.yaml` exists, **snapshot fields override card build defaults** for focus, latent weights, bias_strength, default somatic, flexibility, skills, and memories.

---

## 3. Unified state model

There is **one character runtime**, two layers of persistence:

| Layer | File | Lifetime | Owns |
|---|---|---|---|
| **Durable** | `Characters/[slug]_log.yaml` | Across movements / sessions | Focus, latent weights, bias_strength, skills, memories, history, relational baselines |
| **Live** | Conforms to `Schemas/psychosomatic_state.json` | One pipeline tick / turn | Autonomic scales, affect, active wound/gift state, relational vectors this beat, priority arbitration, 4-channel vector |

**Canonical rule:** Durable log wins for long-horizon continuity. Live snapshot is rewritten every tick. On **commit**, only durable-mapped fields merge into the log (see §8).

Card YAML is **build-time identity**, not mutable runtime. Never write evolution back into the card.

### Live snapshot location
Apps may:
1. Keep live state in working memory only, or
2. Write `Characters/[slug]_state.json` (optional, ephemeral), or
3. Embed the last live snapshot under `live:` in `_log.yaml` (optional; cleared or refreshed each commit)

All three must validate against `Framework/Schemas/psychosomatic_state.json`.

---

## 4. Neurobiological & Psychological execution sequence (Dual-Circuit Architecture)

Human cognition does not run a single flat loop. Real nervous systems operate across two distinct functional circuits based on autonomic pressure:

```
                      📥 Sensory Event / Input
                                 │
                                 ▼
                    ⚡ 1. NERVOUS SYSTEM & POLYVAGAL STATE
             (Polyvagal mode: ventral, sympathetic, dorsal, dissociated)
             (Visceral baseline, startle, heart rate, gut, Z1–Z6 cascades)
             (Sensory tunneling: micro-fixation on physical anchor)
             [module hook: pre_somatic]
                                 │
                                 ▼
                    ❤️ 2. RAW AFFECTIVE IMPULSE & AMBIVALENCE
             (Un-thought urge: fear, arousal, anger, shock, warmth)
             (Raw action impulse: push, strike, bolt, freeze, seize control)
             [module hook: affect_filter]
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
    [Autonomic Pressure < Threshold]   [Autonomic Pressure ≥ Threshold]
     REGIME: "deliberative"             REGIME: "reactive"
     (Cortical / Regulated Loop)        (Limbic Short-Circuit / Hijack)
                 │                               │
                 ▼                               ▼
     🧠 3. SUBCONSCIOUS PRISM             ⚡ PREFRONTAL BYPASS:
        (Inner Split: gut truth              Input is NOT parsed as debate logic;
         vs. conscious rationalization)      words are felt purely as threat/impact.
        (Defense posture: intellectualize,   No rational deliberation.
         fawn, deflect, withdraw, etc.)          │
                 │                               ▼
                 ▼                        💥 MASK COLLAPSE:
     🎭 4. SOCIAL MASKING & STRAIN           Social facade shatters or locks into
        (Facade type, strain 0–100,          rigid armor (mask_fracture: true).
         micro-fracture tells)                   │
                 │                               ▼
                 ▼                        🛑 ARBITRATION BYPASS:
     ⚖️ 5. DYNAMIC ARBITRATION               Priority arbitration is bypassed
        (Drives compete by salience;         (arbitration_status: "bypassed_reactive").
         internal friction scored)           Primal impulse takes 100% unilateral lock.
                 │                               │
                 ▼                               ▼
  ┌──────────────┼──────────────┐                │
  ▼              ▼              ▼                │
🫀 FEELS       🧠 THINKS      🗣️ SAYS/DOES        │
(Autonomic     (Ego rational-  (Masked speech   │
 & Zones)      ization &       & posture)        │
               friction)                         ▼
                 │                      ┌────────┼────────┐
                 │                      ▼        ▼        ▼
                 │                    🫀 FEELS 🧠 THINKS 🗣️ SAYS/DOES
                 │                    (Visceral (Cognitive (DIRECT IMPULSE
                 │                     flooding  blank or   DISCHARGE:
                 │                     & shock)  visceral   raw vocal/motor
                 │                               noise)     reaction: snap,
                 │                                          strike, bolt, freeze)
                 ▼                               │
        📤 7. LIVE SNAPSHOT + APP RENDER ◄───────┘
           [module hook: app_render — host presentation]
           [module hook: on_commit — after durable merge]
```

### Cognitive Regimes: Deliberative vs. Reactive

| Attribute | `deliberative` (Regulated Circuit) | `reactive` (Limbic Short-Circuit) |
|---|---|---|
| **Trigger Threshold** | Stress < 70, arousal < 75, `autonomic_surge: false`, core autonomy intact | Stress ≥ 70, arousal ≥ 75, `autonomic_surge: true`, or acute threat to core control/wound |
| **Logic & Argument Handling** | Prefrontal cortex evaluates statements, weighs context, and processes points | **Prefrontal bypass:** Words are registered strictly as autonomic impact/threat; zero logical debate parsing |
| **Social Mask** | Facade maintained with measurable strain (0–100) and micro-fractures | Facade collapses or freezes into rigid defensive wall (`mask_fracture: true`) |
| **Priority Arbitration** | Weighs competing drives (`arbitration_status: "arbitrated"`) | Bypassed (`arbitration_status: "bypassed_reactive"`); survival/defensive impulse takes 100% lock |
| **`Thinks` Channel** | Structured internal monologue, rationalization, and subtext friction | Fragmented visceral loops (*"No. Get away. Stop."*), sensory fixation, or cognitive blank |
| **`Says` & `Does` Channels** | Calibrated dialogue intent, vocal behavior, and deliberate physical staging | **Direct impulse discharge:** involuntary vocal snap, sharp interruption, blunt denial, slam, or recoil |
| **Persuasion / Concession** | Concession possible with high emotional safety (> 75) and low friction | **Concession impossible:** Nervous system is hijacked; character cannot admit defeat or yield ground |

---

## 5. Embodied cognition (mind-body unity)

1. **Somatic → Cognitive:** Fatigue, pain, gut drop, arousal, intercostal tension alter patience, risk tolerance, memory access, word choice.
2. **Cognitive → Somatic:** Wound/gift evaluations shift autonomic physiology immediately.
3. **Continuous loop:** Sensation, self-deception, and social masking update each other within the tick.

### Autonomic Polyvagal Modes
The nervous system operates across 4 distinct states:
- **`ventral_grounded`:** Socially attuned, open breathing, relaxed vocal cords, receptive to connection.
- **`sympathetic_mobilized`:** Fight/flight activation; rapid pulse, shallow chest breathing, tense perimeter muscles, hyper-vigilance.
- **`dorsal_freeze`:** Hypo-arousal / shock; numb gut, heavy immobile limbs, flat affect, quiet or delayed vocalization.
- **`dissociated_tunnel`:** Sensory detachment; depersonalization under high trauma/stress; obsessive fixation on a single irrelevant sensory anchor (`sensory_tunneling`).

### Anatomical cascades (6 zones)
Every state shift engages **at least 2 interconnected zones**:

| Zone | Examples |
|---|---|
| Z1 Cranial & Ocular | Temple pulse, jaw lock, blink rate, pupil focus |
| Z2 Vocal & Cervical | Larynx shift, swallow, corded neck |
| Z3 Thoracic & Respiratory | Sternum, intercostals, apex vs diaphragm breath |
| Z4 Abdominal & Visceral | Diaphragm catch, gut drop, solar plexus |
| Z5 Pelvic & Kinesthetic | Center of gravity, lumbar arch/slump, hip angle |
| Z6 Peripheral & Grounding | Toe curl, finger tremor, white knuckles, stride weight |

### Realm catalog lookup
1. Resolve `active_focus` → realm key (`I`…`X`) from card/log.
2. Load that realm block from `realm_data.yaml` (`micro` / `moderate` / `macro` / `release` + `vocal_behavior`).
3. Select intensity from live autonomic pressure (stress/arousal/pain thresholds).
4. Fold **2+** zone tells into `Feels` / `Does`; fold vocal_behavior into `Says`.
5. Latent anchors may leak secondary micro-tells under residual pressure — never name realm labels on-page.

---

## 6. Dynamic priority arbitration & psychological friction

At any moment, multiple internal drives carry baseline weights. Compute **salience** per drive:

$$\text{Salience} = (\text{Internal Intensity}) \times (\text{Context Multiplier}) \times (\text{Character Baseline Weight})$$

### The Inner Split & Self-Deception
Real humans do not experience emotions in clean isolation; they experience **The Inner Split**:
- **`subconscious_visceral_truth`:** What the nervous system and gut know (e.g., *"I feel terrified of being abandoned"*).
- **`conscious_rationalization`:** The self-deceptive narrative the ego constructs to maintain pride and control (e.g., *"I'm just declining because they are wasting my time"*).
- **`internal_friction` (0–100):** The dissonance between competing drives. High friction causes hesitation, stammering, false starts, and clumsy physical actions.

### Defense Posture Taxonomy
Under threat/pressure (`DEFENSIVE_ACTIVE`), the character adopts a specific human defense strategy:
- `intellectualize`: Retreats into hyper-logic, vocabulary, aloof cynicism, or technical analysis.
- `fawn_placate`: Smiles, over-agrees, and accommodates while gut drops in terror.
- `deflect_banter`: Deflects tension with jokes, sarcasm, teasing, or topic changes.
- `cold_withdrawal`: Shuts down verbal output, looks away, delivers monosyllabic answers.
- `preemptive_strike`: Lashes out verbally or physically before the other person can hurt them.
- `brace_stonewall`: Rigid posture, unyielding physical barrier, refusing compromise.

### Arbitration Rules & The Reactive Bypass
1. **Deliberative Regime (`arbitration_status: "arbitrated"`):**
   - **Winning drive** = highest computed salience → primary driver for `Says` & `Does`.
   - **Secondary drives** produce monologue friction (`internal_friction`), hesitation, stammering, or opposing micro-tells.
   - **Volitional Drive & Active Inquiry:** Characters MUST NOT act as passive AI responders. Winning drives dictate active goals and counter-probing.
2. **Reactive Regime (`arbitration_status: "bypassed_reactive"`):**
   - **Deliberative weighing is suspended.** The limbic emergency lock assigns salience 100 directly to the raw survival/defensive impulse (`affective_state.impulse`).
   - Secondary long-term goals (reputation, diplomacy, being reasonable, future consequences) are completely silenced by autonomic flooding.
   - **The Non-Concession / Defeat Block:** When an activated character (especially controlling, proud, or traumatized types) faces a threat to autonomy or ego, **logic does not penetrate**. The character CANNOT concede an argument or admit defeat. They react through pure defensive reflex: interrupting, doubling down, counter-attacking, stonewalling, or physical termination.

Dual-aspect psyche:
- Wound path → `DEFENSIVE_ACTIVE` bias_state when context is wound-relevant.
- Gift path → `GENERATIVE_ACTIVE` when safety/trust/flow allows virtue lens.
- Otherwise → `DORMANT` (ambient personality only).

---

## 7. Relational model & interpersonal momentum

Bonds are continuous multi-dimensional vectors in the **live** snapshot:

```json
{
  "relational_vectors": {
    "interlocutor_slug": {
      "emotional_safety": 65,
      "attraction_physical": 80,
      "attraction_emotional": 40,
      "respect_competence": 90,
      "status_dynamic": "equals",
      "resentment_friction": 15,
      "relational_momentum": "brittle",
      "relational_ambivalence": "admires competence but deeply mistrusts authority",
      "perceived_reciprocity": {
        "perceived_liking": 50,
        "perceived_threat": 10
      },
      "relational_anchors": ["shared_secret_ch2"]
    }
  }
}
```

### Relational Momentum & Ambivalence
- **`relational_momentum`:** Tracks directional velocity (`building`, `deepening`, `stable`, `eroding`, `brittle`, `suspended`, `fractured`).
- **`relational_ambivalence`:** Captures messy human duality (e.g., high attraction + high resentment = electric push-pull).

Durable baselines for bonds live under `_log.yaml` → `relational_baselines`. Live vectors start from those baselines each session and drift; commit writes durable shifts only on Medium+ pressure or explicit author approval.

### 7.1 Intimate & Sexual Stimulus Interpretation

Sex is not a special subsystem or separate operational mode—it is a class of stimulus processed through the standard pipeline sequence:

1. **Nervous System (Visceral/Zones):** Physical arousal, pulse, skin temperature, respiratory shift across Z1–Z6.
2. **Raw Affect:** Immediate visceral impulse (attraction, shock, discomfort, warmth, pull).
3. **Subconscious Prism:** Filtered through upbringing, memory, and wound/gift matrix. Sex is interpreted through character-specific meaning (e.g., debt, vulnerability, control, caretaking, threat, sacred connection, escape, or curiosity).
4. **Priority Arbitration:** Drive salience computation evaluating whether desire wins, freezes, deflects, approaches, or withdraws.
5. **Output Vector:** Emits character **stance and intent** (`Feels`, `Thinks`, `Says`, `Does`).

**North Star Rule:** The pipeline concludes how a person relates to and interprets intimate stimulus. Nothing in the core engine stages sex, details positions, or specifies explicit act mechanics. Explicit presentation belongs strictly downstream.

---

## 8. Output vector & commit protocol

### Live output (every tick)
Serialize a full snapshot matching `Framework/Schemas/psychosomatic_state.json`:

1. **`Feels`** — autonomic polyvagal state & multi-zone somatic manifestations (2+ zones). In `reactive` mode, shows visceral surge, flooding, or acute somatic freeze.
2. **`Thinks`** — in `deliberative` mode: conscious rationalization vs. subconscious friction and monologue (not therapy labels). In `reactive` mode: degraded to cognitive noise (visceral fragments, single-word loops, sensory shock, or blank).
3. **`Says`** — in `deliberative` mode: dialogue intent shaped by social mask, defense posture, and active counter-inquiry. In `reactive` mode: direct vocal reflex (snap, blunt denial, sharp interruption, stammer, silence) discharging raw impulse.
4. **`Does`** — in `deliberative` mode: posture, spatial staging, object handling, and mask fracture tells. In `reactive` mode: involuntary motor reflex (slamming, stepping in, recoiling, freezing, bolting).

Apps render these channels into prose (drafting) or downstream interactive hosts. Framework jargon never appears in rendered output.

### Commit mapping (movement approved / session close)

| Live field | Durable destination in `_log.yaml` |
|---|---|
| Winning focus / realm pressure outcome | `snapshot.active_focus`, `snapshot.latent_weights` |
| Sustained bias_strength change | `snapshot.bias_strength` |
| Permanent baseline body change | `snapshot.default_somatic` |
| Arc-level defense posture evolution | `snapshot.defense_posture` |
| Arc-level social facade shift | `snapshot.social_facade` |
| Skill discovery / demotion | `skills.active` / `skills.latent` |
| Memory promotion (triggered → detailed) | `memories.detailed` / `footnote` |
| Relational baseline shift (Medium+) | `relational_baselines.[target]` |
| Tick narrative (Medium+ only) | append `history[]` |

Do **not** dump full live autonomic noise into history every beat. History records durable pressure events only.

After commit: regenerate human-readable projections (`Character_Change_Log.md`) from YAML. YAML wins conflicts.

---

## 9. Hard pipeline invariants

- **Reactive Circuit & Anti-Sycophancy invariant:** Under elevated autonomic pressure (stress/arousal ≥ 40) or when `cognitive_regime == "reactive"`, characters MUST NOT execute calm deliberation, weigh syllogisms, or concede arguments to an interlocutor's logic. If a controlling or prideful character's dominance is challenged, they MUST execute pure defensive/reactive reflex (fight/pushback/dismissal/stonewall) rather than polite capitulation.
- **Volition & Inquiry invariant:** Characters MUST NOT act as passive AI responders or Q&A endpoints. Every turn must express active volition (asking counter-questions, probing motives, asserting goals).
- **Body before insight** in the 4-channel vector ordering for downstream renderers.
- **Off-page matrix:** never emit realm names, bias engine labels, `DEFENSIVE_ACTIVE`, debt-ledger names, polyvagal labels, cognitive regimes, or defense posture enums into text meant for on-page use.
- **Epistemic gating:** `memories.detailed` = sharp recall; `footnote` = unsure unless scene trigger; unlisted = forgotten.
- **Competence gating:** `skills.active` = clean execution; `latent` = fumble/brace; unlisted = helplessness.
- **Age invariant:** `canon_adult` and age are identity/ToS data invariants (minors are never sexual subjects). This is a safety boundary, not a behavior toggle or mood switch.
- **Module subordination:** ENABLED modules inject only at declared hooks; core sequence and Rules_Index always win ([Modules.md](Modules.md)).

---

*Core simulation engine for Simulacra. State shape: `Framework/Schemas/psychosomatic_state.json`. Extensions: `Framework/Modules.md`.*
