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

### Optional Golem interface (`scripts/golem.py`)

Simulacra runs the full cognitive pipeline from the scene, character cards, and continuity state. In standalone mode, work through the somatic and cognitive steps in this document and produce all four channels. When Golem is enabled, it supplies the body state through:
```bash
python3 scripts/run.py golem --card <card.yaml> [--slug <slug>] --log <log.yaml> --stimulus '<json>' [--history-file <hist.json>] --out <out.json> [--commit]
```
The script emits a `PsychosomaticStateSnapshot` (validated against `Framework/Schemas/psychosomatic_state.json`) plus `golem_meta`, which includes triggered rules, somatic cues, and commit eligibility. Golem supplies `Feels`. When the reactive circuit takes over, `autonomic_state.involuntary_response` records bracing or freezing already underway, and `Feels` describes it. Simulacra supplies `Thinks`, `Says`, and `Does` using the scene, the character card, and what the body is already doing.

Golem accepts separate `physical_pain` and `emotional_distress` stimulus scores from 0 to 100. YAML cards can set `physical_pain_tolerance` and `emotional_distress_tolerance` on the same scale. Both tolerances default to 50. Higher tolerance reduces the matching state's contribution to stress and arousal while preserving its intensity in the snapshot. Physical pain at 100 always produces acute overload, with stress and arousal at 100 and a reactive regime. Older stimuli can use `pain` as a fallback for `physical_pain`, and the validator accepts older snapshots with `pain`.

Pain and distress persist in turn history. Without further input, their excess above baseline halves every two minutes of scene time for physical pain and every twenty minutes for emotional distress. Both baselines default to zero. YAML cards can set `physical_pain_baseline` and `emotional_distress_baseline` when needed. A continuing stimulus holds its score while supplied, and a stronger stimulus raises the score immediately. Omitting the field or sending zero lets any residual pain or distress ease over time.

Hunger grows at 12 points per hour up to 100. Pass `food_intake` once when the character has eaten, as the number of points of hunger the meal relieves. Hunger contributes to stress and appears in `Feels`.

Environmental inputs are `cold_exposure`, `heat_exposure`, `noise_exposure`, and `bright_light_exposure` on 0–100 scales. With turn history, each exposure carries forward when omitted. Set a new level when the scene changes, including zero when an exposure ends. Felt cold and heat approach the new level with a five-minute half-life. Noise and bright light can increase discomfort immediately, even at zero elapsed time. When their exposure drops, the excess discomfort halves in two seconds for noise and five seconds for bright light. These are simulation settings. The snapshot reports exposures and discomfort separately, and discomfort contributes to stress and appears in `Feels`.

Physical fatigue and sleep debt accumulate while the character is awake. Set `activity` to `awake`, `resting`, or `sleeping` when that condition actually changes. While awake, optional `exertion` on a 0–100 scale changes how quickly physical fatigue builds. Activity and exertion carry forward with history. Rest reduces physical fatigue, while sleep reduces both fatigue and sleep debt. Golem derives `exhaustion` from the higher of the two scores once it exceeds 60. Recovery takes scene time in the relevant state.

The snapshot's `arousal` field measures general autonomic activation. For eligible adults, Golem also reports `sexual_drive` (background pressure) and `sexual_arousal` (current bodily response) on separate 0–100 scales. Drive starts at the card's optional `sexual_drive_baseline` (default 50). Pain, distress, and fatigue lower its target, and it moves toward that target with a 30-minute half-life. As bodily load eases, drive moves back toward baseline. Attraction appraisals can raise sexual arousal. The legacy `sexual_arousal` input can still supply a level, which starts at zero and carries forward when omitted. Golem reports zero for both sexual state fields when the character is ineligible.

Each Golem call advances the state by the supplied scene time. Use `elapsed_ms` for timed updates, such as 100 ms ticks, and pass `0` to evaluate an immediate stimulus without advancing recovery, fatigue, or drive. Older stimuli can use `elapsed_minutes`; the default is one minute when both fields are omitted. Use `--history-file` to retain fractional state between calls. The caller controls when to advance the scene clock. The separate `response_time_ms` field describes response pressure for the current event.

---

## 2. Required inputs (must load before a tick)

| Input | Path | Role |
|---|---|---|
| **This spec** | `Framework/CognitivePipeline.md` | Execution sequence & commit rules |
| **Realm somatics** | `Framework/Psychology/realm_data.yaml` | Brace / release body catalogs per realm |
| **Character card** | `Characters/[slug].yaml` | Full identity, voice, knowledge, psyche, relationships, and authored motivations, goals, and incentives |
| **Durable log** | `Characters/[slug]_log.yaml` | Runtime evolution over card defaults |
| **Event trigger** | Movement brief / player turn / scene pressure | Sensory + social stimulus |
| **Schema** | `Framework/Schemas/psychosomatic_state.json` | Shape of the live snapshot |

### Modules (downstream injectors)
`Framework/Modules.md` is the **extension registry**. Downstream applications register modules there to inject into this loop at defined hooks (`pre_somatic`, `affect_filter`, `pre_arbitration`, `post_vector`, `app_render`, `on_commit`).

- Core sequence and state model always run.
- Only modules with Status `ENABLED` and a present file load.
- Modules are subordinate: they must not override Rules_Index, this pipeline’s invariants, card/log supremacy, or age gates.
- Full contract: [Modules.md](Modules.md).

### Load the full YAML card

Load the complete YAML mapping for each on-scene character before running a tick. Keep the card available throughout the scene so decisions can draw on identity, culture, physical profile, knowledge, voice, relationships, and history alongside the psyche fields. For a YAML file with a `characters` mapping, select the full entry by slug. The movement brief supplies the immediate situation and what the character can perceive.

- `active_focus`, `latent_anchors` → realm keys into `realm_data.yaml`
- `transformation_weights` (or log overlay) → baseline drive weights & bias_strength
- `cognitive_bias` / `cognitive_gift` → prism rewrite rules (Wound / Gift)
- `default_somatic_alignment` → ambient body baseline
- `voice.*` → shapes `Says` (idiolect, defense, generative stance)
- `history_anchors` + log `memories.*` → epistemic gating
- `skills` on the card and `skills.active` / `skills.latent` from the log → competence in `Does`
- `motivations`, `goals`, `incentives` → what matters, what the character is trying to accomplish, and what the current situation makes worth doing
- `canon_adult` / `age` → hard eligibility for intimate affect (apps enforce presentation)

### Log overlay rule
When `Characters/[slug]_log.yaml` exists, **snapshot fields override card build defaults** for focus, latent weights, bias_strength, default somatic, flexibility, skills, and memories.

Apply durable `goal_updates` by stable goal ID, including goals formed after the card was written. In a running host use `current_goals`, which also includes changes since the last YAML commit. Goals without an update start active. Older cards and logs may omit the new mappings. In that case, draw on authored continuity and the scene when a motive or immediate objective is evident.

---

## 3. Unified state model

There is **one character runtime**, two layers of persistence:

| Layer | File | Lifetime | Owns |
|---|---|---|---|
| **Durable** | `Characters/[slug]_log.yaml` | Across movements / sessions | Focus, latent weights, bias_strength, skills, memories, history, relational baselines, goal progress |
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
3. **Continuous loop:** Sensation, interpretation, and the consequences of action update each other. In standalone drafting, apply both directions within the cognitive pipeline using the scene and continuity state.

### Feedback when Golem is enabled

1. Apply scene stimuli and elapsed time to Golem, using a separate turn history for each character. Read `output_vector.feels` and the snapshot, including any involuntary reaction already underway.
2. Appraise the scene through the character's perspective. Send any new appraisal to Golem at `elapsed_ms: 0` if the body reacts in the same moment. For example, a character who reads a remark as welcome flirtation might supply `{"elapsed_ms":0,"appraisal":{"interest":70,"attraction":60}}`. Supported signals are `interest`, `attraction`, `disgust`, `unease`, and `uncertainty`, each an integer from 0 to 100. Retain the scene inputs that still apply, such as current threat and social pressure. Supply one-time events like eating only when they occur.
3. Use the updated state to decide `Thinks`, `Says`, and `Does`. Feed the consequences back when they occur. For example, pass `food_intake` once the character eats, or update `exertion` once they start running. Advance elapsed time only once for the scene interval.

Appraisals register immediately and their effects halve over ten seconds of scene time unless refreshed by a new appraisal. Interest raises general activation. Unease, uncertainty, and disgust add strain, and strong disgust can make the stomach turn. Attraction can raise sexual arousal in an eligible adult, and disgust can dampen it. Keep appraisal data and state snapshots off-page.

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
4. Fold **2+** zone tells into `Feels`. Simulacra accounts for any involuntary response when rendering `Does` and can use `vocal_behavior` as reference when rendering `Says`.
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

Before selecting a response, use the character's full card to identify the goals relevant to this scene, the motivations behind them, and the incentives the character currently perceives. A motivation explains why the outcome matters. A goal gives the character an outcome to pursue. An incentive changes the expected benefit, cost, or risk of a particular choice when its trigger applies. The character can pursue a goal, postpone it, or do something that works against it under pressure. Keep the goal active until the story establishes a durable change.

Use the body state to constrain the choices the character can realistically make. When Golem is enabled, Simulacra uses the full card and the returned `Feels` to evaluate the competing pressures and choose the response.

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

### Personal boundaries and ending contact

The character can decline a favor, withhold personal information, or end an uncomfortable exchange. Treat ordinary disagreement, criticism, a difficult question, and consensual fictional conflict in their scene context. A refusal or a spike in Golem stress establishes how the character feels. The host assesses the user's actual conduct separately.

Before passing an incoming message into the simulation, consider who the message targets, what happened earlier, whether a limit was communicated, and whether the person respected it. A character can name the limit plainly and give the person room to change course. A credible threat, targeted harassment, or continued pressure after a clear refusal can warrant ending contact immediately. The host can close the simulation without requiring the character to justify the boundary or negotiate further. The host owns the assessment and any file-retention policy.

### Rendering a reply from the card

Read the card privately. Use a goal to select what the character wants *here*, a voice description to shape cadence, and a history anchor to decide what they might disclose. When someone asks about the character, choose one thing they would actually say to this person now. A joke they abandon halfway through or a specific incident they choose to tell can reveal more than a list of their traits. Before releasing the line, check whether it recites a profile, paraphrases the goals in card order, or reports the host's bookkeeping. Render that beat again from the scene. Names, facts and intentional signature phrases can carry through.

### Memory, pushback, and curiosity

- **Memory selection:** After a turn, consider what the character would retain because it bears on a goal, bond, value, or consequence. Propose a short subjective summary, why it matters, and concrete cues that could bring it back. Keep ordinary exchanges transient. Use `detailed` for material the character retains clearly and `footnote` for a fragment that requires a scene trigger. Approval can save a selected memory even after a Low-pressure tick. This updates `memories` without adding a pressure event to `history`.
- **Delayed reflection:** When a turn leaves the character with an unresolved moral conflict, a boundary they have just recognized, or a consequence they have yet to absorb, keep a brief pending reflection in the host's persistent session state. Record what the character actually learned, what remains uncertain, and why it matters to them. Revisit it at the next plausible quiet beat or on an always-on host's scheduled idle event. Run the body-first pipeline for that moment. The character may find the issue more troubling, change their intent, let it go, or propose a durable memory for approval. A pending item is temporary context for reflection, and its presence alone conveys no durable fact, goal change, or obligation to bring the subject up aloud. Clear it after resolution or a decision to let it go.
- **Unprompted activity:** On an idle event, start from the body's current state, the character's goals, and recent experience. The character may continue an activity, reconsider an earlier exchange, pursue a new interest, or do nothing. Keep the event itself neutral when testing which thread the character chooses. The [Golem loop](../scripts/README.md#always-on-golem-loop) carries the chosen action, outcome, and plans forward for the host.
- **Recall:** The host supplies `memory_cues` from what the character actually perceives. Golem matches saved cues and exposes only matching records in `recalled_memories`. Apply the epistemic and somatic-deflection rules before rendering. Treat summaries as subjective evidence, and keep private memories private unless the character chooses to share them. Older authored memory entries remain available through the host's existing log-reading workflow.
- **Willingness to help.** When someone asks for help, let the character decide whether they feel like doing it and whether the act fits who they are. Care, loyalty, duty, irritation, or simply wanting to carry on with their day can settle the choice. A calm character can decline even a harmless, easy favor. They may say no, leave the request unanswered, or keep doing what they were doing. Let that stand. An explanation, alternative offer or follow-up question belongs only when the character independently wants to give one. For a request appraised before the tick, pass the character's choice as `conversation.willing_to_help`. The host can also make the choice at render time.
- **Pushback:** Appraise the scene against the character's own boundaries, goals, and beliefs. Supply `conversation.conflict` as `boundary`, `goal`, or `claim` when the character perceives a real conflict and has reason to resist. Render the resulting intent as a refusal, counterproposal, or correction in their voice. Under heightened pressure use brief defensive delivery consistent with the body and reactive invariants.
- **Curiosity:** When the character has a genuine unresolved question about someone who interests them, supply a specific `conversation.open_topic` and a stable `caller_or_target` ID. Golem suggests an inquiry at carried interest of 60 or higher when stress is below 40 and the circuit is deliberative. Interest can raise general autonomic activation (`autonomic_state.arousal`), and activation can make a subject more intriguing if the character appraises it that way. General activation can shape how the character asks. Sexual arousal and sexual drive are separate background state fields and are outside the curiosity decision. Pushback takes precedence. Carried history suppresses the ten most recent inquiry suggestions by target and topic. Render a follow-up only when it fits the beat. The host owns the wording and can leave a suggestion unused.

### Goals across a life

On each wake, consider current goals alongside the actual opportunities available. An empty afternoon in which a character chooses teaching over rehearsal carries different evidence from an afternoon spent working a compulsory shift. Record the choice and what happened, even when the character cannot explain it. Use the linked episode to recover its bodily reaction, social context, or outcome when interpreting a pattern later.

A single consequential experience or a series of smaller choices can justify forming a goal, changing its objective or commitment, or moving it to dormant, blocked, completed, or abandoned. Dormancy leaves room for renewed pursuit. Blockage describes an obstacle. Completion records attainment. Abandonment records that the character has let the goal go. The motive can outlast any of these outcomes and support a new ambition. A character may resume a former goal when later events warrant it.

Record a change when the scene supports it. Quiet time alone supplies no evidence about commitment. Treat an old scheduled plan as an opportunity for a new decision against the current goals. The character can skip it, change it, or follow through. Their actions can shift well before they speak about the change.

### Anticipation and experience

Before a chosen activity, consider its possible benefit and cost independently through the character's goals, knowledge, and boundaries. A valuable outcome can also be costly. Record a forecast when making the plan. On completion, describe what actually happened and appraise it from the character's perspective. Golem measures the immediate bodily change and updates the two expectations for that topic. At the next decision the host can use that history when choosing to return, withdraw, change approach, or consider the matter settled.

Repeated experiences across situations may support a broader change in a goal, relationship, or habitual response. Evaluate that evidence through the existing durable-change protocol. A single experience may still establish an immediate personal boundary. On a neutral idle wake, leave the choice of activity to the character.

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
| Confirmed goal progress or status change | `goal_updates.[goal_id]` |
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
