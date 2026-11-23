# Cognitive Pipeline Specification
*Psychosomatic simulation & behavior prediction engine · Simulacra · Version 2.1*

---

## 1. Purpose

Application-agnostic psychological/physical character runtime serving manuscript drafting ([Main.md](Main.md)) and interactive hosts.

### Downstream decoupling contract
| Pipeline owns | Pipeline does **not** own |
|---|---|
| Autonomic reaction, affect, prism, priority arbitration | Prose style, anti-synthesis, style locks |
| 4-channel vector (`Feels` / `Thinks` / `Says` / `Does`) | Chat UI, OOC commands, turn presentation |
| Active volition, goal-driven inquiry, probing motives | Continuity ledger rows, draft file I/O |
| Live psychosomatic snapshot + `realm_data.yaml` lookup | Optional craft guides under `Mechanics/` |

### Optional Golem interface (`scripts/golem.py`)
```bash
python3 scripts/run.py golem --card <card.yaml> [--slug <slug>] --log <log.yaml> --stimulus '<json>' [--history-file <hist.json>] --out <out.json> [--commit]
```
- Golem computes deterministic physiology (`Feels`) and `autonomic_state.involuntary_response`, emitting a `PsychosomaticStateSnapshot` (`Framework/Schemas/psychosomatic_state.json`) + `golem_meta` (triggered rules, somatic cues, commit eligibility).
- Simulacra supplies `Thinks`, `Says`, and `Does` from the card, scene, and body state.
- **Stimuli & persistence:** Supports `physical_pain` (legacy `pain`), `emotional_distress`, `food_intake`, `activity` (`awake`/`resting`/`sleeping`), `exertion`, exposures (`cold_exposure`, `heat_exposure`, `noise_exposure`, `bright_light_exposure`), `appraisal` (`interest`, `attraction`, `disgust`, `unease`, `uncertainty`), `sexual_arousal` (eligible adults only), `memory_cues`, and `conversation`. Pain/distress/exposures/activity/exertion persist in history; one-time events (`food_intake`, `conversation`, `memory_cues`, `sexual_arousal`) apply once per event.
- **Clock & calibration:** Caller supplies `elapsed_ms` (or `0` for immediate appraisal without advancing recovery/fatigue/drive); persistent loop (`scripts/golem_loop.py`) uses event wall-clock timestamps. Rates and `physiology_calibration` overrides are documented in [SKILL.md](../SKILL.md).

---

## 2. Required inputs (must load before a tick)

| Input | Path | Role |
|---|---|---|
| **This spec** | `Framework/CognitivePipeline.md` | Execution sequence & commit rules |
| **Realm somatics** | `Framework/Psychology/realm_data.yaml` | Brace / release body catalogs per realm |
| **Character card** | `Characters/[slug].yaml` | Identity, voice, knowledge, psyche, relationships, motivations, goals, incentives |
| **Durable log** | `Characters/[slug]_log.yaml` | Runtime evolution over card defaults |
| **Event trigger** | Movement brief / player turn / scene pressure | Sensory + social stimulus |
| **Schema** | `Framework/Schemas/psychosomatic_state.json` | Shape of the live snapshot |

### Modules (downstream injectors)
`Framework/Modules.md` registers `ENABLED` modules at hooks (`pre_somatic`, `affect_filter`, `pre_arbitration`, `post_vector`, `app_render`, `on_commit`). Core sequence always runs; modules cannot override `Rules_Index`, pipeline invariants, card/log supremacy, or age gates.

### Load the full YAML card
Select by slug if `characters` mapping exists; keep card available for identity, `active_focus`/`latent_anchors`, `transformation_weights`, `cognitive_bias`/`cognitive_gift`, `default_somatic_alignment`, `voice.*`, `history_anchors`, `skills`, `motivations`/`goals`/`incentives`, and `canon_adult`/`age`.

### Log overlay rule
When `_log.yaml` exists, `snapshot` fields override card defaults for focus, latent weights, `bias_strength`, default somatic, flexibility, skills, and memories. Apply durable `goal_updates` by stable goal ID (or `current_goals` in a running host); goals without updates start active.

---

## 3. Unified state model

| Layer | File | Lifetime | Owns |
|---|---|---|---|
| **Durable** | `Characters/[slug]_log.yaml` | Across movements / sessions | Focus, latent weights, `bias_strength`, skills, memories, history, relational baselines, goal progress |
| **Live** | `Schemas/psychosomatic_state.json` | One pipeline tick / turn | Autonomic scales, affect, active wound/gift state, relational vectors, arbitration, 4-channel vector |

**Canonical rule:** Card YAML is immutable build-time identity. Durable log wins long-horizon continuity. On **commit**, only §8 durable fields merge into `_log.yaml`.

### Live snapshot location
Keep live state in working memory, `Characters/[slug]_state.json` (ephemeral), or `live:` in `_log.yaml`; all must validate against `Framework/Schemas/psychosomatic_state.json`.

---

## 4. Neurobiological & Psychological execution sequence (Dual-Circuit Architecture)

1. **Nervous System & Polyvagal State** `[hook: pre_somatic]`: Visceral baseline, startle, Z1–Z6 cascades, sensory tunneling.
2. **Raw Affective Impulse & Ambivalence** `[hook: affect_filter]`: Un-thought urge + raw action impulse.
3. **Regime Split:**
   - **`deliberative`** (stress < 70, arousal < 75, `autonomic_surge: false`, autonomy intact): Subconscious Prism (Inner Split + defense posture) → Social Masking & Strain → Dynamic Arbitration (`arbitrated`) → `Feels` / `Thinks` / `Says` / `Does`.
   - **`reactive`** (stress ≥ 70 or arousal ≥ 75 or `autonomic_surge: true` or acute threat to core control/wound): **Prefrontal Bypass** (words felt as threat/impact, zero debate parsing) → **Mask Collapse** (`mask_fracture: true`) → **Arbitration Bypass** (`bypassed_reactive`, primal impulse at 100% lock) → Direct Impulse Discharge (`Says`/`Does`: snap, interrupt, recoil, freeze, bolt; `Thinks`: fragmented loops/blank). **Concession is impossible** in `reactive` mode.
4. **Live Snapshot + App Render** `[hooks: app_render, on_commit]`.

---

## 5. Embodied cognition (mind-body unity)

Somatic state constrains cognition (`Feels` → `Thinks`/`Says`/`Does`), and wound/gift evaluations shift autonomic physiology immediately.

### Feedback when Golem is enabled
1. Apply scene stimuli + elapsed time; read `output_vector.feels` and `involuntary_response`.
2. Send scene `appraisal` (`interest`, `attraction`, `disgust`, `unease`, `uncertainty`, 0–100) at `elapsed_ms: 0` if the body reacts in the same moment.
3. Render `Thinks`, `Says`, `Does`; feed back resulting `food_intake`/`exertion`/state changes once when they occur. Keep appraisals and snapshots off-page.

### Autonomic Polyvagal Modes
- `ventral_grounded`: Socially attuned, open breath, relaxed vocal cords.
- `sympathetic_mobilized`: Fight/flight, rapid pulse, shallow chest breath, hyper-vigilance.
- `dorsal_freeze`: Hypo-arousal/shock, heavy immobile limbs, flat affect, delayed/quiet speech.
- `dissociated_tunnel`: Depersonalization, obsessive fixation on a single sensory anchor (`sensory_tunneling`).

### Anatomical cascades (6 zones)
Every state shift engages **2+ interconnected zones**:
- **Z1 Cranial/Ocular** (jaw, temple pulse, blink/pupil) · **Z2 Vocal/Cervical** (larynx, swallow, neck) · **Z3 Thoracic/Respiratory** (sternum, intercostals, breath) · **Z4 Abdominal/Visceral** (diaphragm, gut, solar plexus) · **Z5 Pelvic/Kinesthetic** (center of gravity, hip/lumbar) · **Z6 Peripheral/Grounding** (toes, fingers, knuckles, stride).

### Realm catalog lookup
Resolve `active_focus` → realm key (`I`…`X`) in `realm_data.yaml`, pick intensity (`micro`/`moderate`/`macro`/`release`) from live pressure, fold **2+ zone tells** into `Feels`, use `vocal_behavior` as reference for `Says`. Latent anchors may leak micro-tells; never name realm labels on-page.

---

## 6. Dynamic priority arbitration & psychological friction

$$\text{Salience} = (\text{Internal Intensity}) \times (\text{Context Multiplier}) \times (\text{Character Baseline Weight})$$

### The Inner Split & Self-Deception
- `subconscious_visceral_truth` (what the gut knows) vs. `conscious_rationalization` (ego narrative) → `internal_friction` (0–100) drives hesitation, false starts, and clumsy movement.

### Defense Posture Taxonomy
`intellectualize` · `fawn_placate` · `deflect_banter` · `cold_withdrawal` · `preemptive_strike` · `brace_stonewall`.

### Arbitration Rules & The Reactive Bypass
Identify active card `motivations`, `goals`, and triggered `incentives` constrained by body state.
- **Deliberative (`arbitrated`):** Highest salience wins `Says`/`Does`; secondary drives create `internal_friction`; character actively probes/pursues goals (never a passive Q&A bot).
- **Reactive (`bypassed_reactive`):** Deliberation suspended; `affective_state.impulse` takes 100% lock; secondary long-term goals silenced; logic cannot persuade or force concession.
- **Dual-aspect psyche:** Wound path → `DEFENSIVE_ACTIVE`; Gift path → `GENERATIVE_ACTIVE`; otherwise `DORMANT`.

---

## 7. Relational model & interpersonal momentum

Live snapshot tracks `relational_vectors.[target]` (`emotional_safety`, `attraction_physical`, `attraction_emotional`, `respect_competence`, `status_dynamic`, `resentment_friction`, `relational_momentum`, `relational_ambivalence`, `perceived_reciprocity`, `relational_anchors`).

### Relational Momentum & Ambivalence
- `relational_momentum`: `building`, `deepening`, `stable`, `eroding`, `brittle`, `suspended`, `fractured`.
- Live vectors initialize from `_log.yaml` `relational_baselines`; durable shifts commit only on Medium+ pressure or explicit approval.

### 7.1 Intimate & Sexual Stimulus Interpretation
Processed through the standard 5-step pipeline (Visceral/Zones → Raw Affect → Subconscious Prism → Arbitration → Stance/Intent). **North Star Rule:** Core engine determines relational meaning and stance only; never stages explicit sexual acts or mechanics.

---

## 8. Output vector & commit protocol

### Live output (every tick)
Serialize snapshot matching `Framework/Schemas/psychosomatic_state.json`:
1. **`Feels`**: Autonomic state + 2+ zone somatic cues (or visceral flood/freeze in `reactive`).
2. **`Thinks`**: Deliberative inner split/friction (never therapy labels) or reactive visceral fragments/blank.
3. **`Says`**: Dialogue intent shaped by mask, defense posture, and inquiry (or direct vocal reflex in `reactive`).
4. **`Does`**: Spatial staging, posture, object handling, mask fractures (or involuntary motor reflex in `reactive`).

### Personal boundaries and ending contact
Characters may decline favors, withhold info, or end uncomfortable exchanges. Host assesses actual user conduct separately; credible threats, targeted harassment, or persistence after a clear refusal warrant immediate contact termination without requiring character justification.

### Rendering a reply from the card
Before speaking, decide privately: (1) **What does the character believe?** (evaluate evidence and claims independently), and (2) **What will they tell this listener?** (gate by shared history, relationship, and current goal). Keep unspoken notes private; never recite card profiles, goal lists, or host bookkeeping.

### Memory, pushback, and curiosity
- **Memory selection:** Retain consequential moments (goal/bond/value/consequence) as `detailed` (clear subjective summary, `reason`, `cues`) or `footnote` (fragment needing trigger); keep ordinary chatter transient. Approved memories save without adding a pressure event to `history`.
- **Delayed reflection:** Hold unresolved moral/boundary conflicts in transient host state; revisit on a quiet beat or idle wake, then clear once resolved or let go.
- **Unprompted activity:** On idle wakes, choose from body state, goals, and recent experience (`scripts/README.md#always-on-golem-loop`).
- **Recall:** Host supplies `memory_cues` from perceived context; Golem surfaces only matching `recalled_memories`. Apply epistemic and somatic-deflection rules.
- **Willingness to help:** Character may help, decline, or ignore requests based on disposition and current goals (`conversation.willing_to_help`).
- **Pushback:** Pass `conversation.conflict` (`boundary` | `goal` | `claim`) when the character perceives conflict; render as refusal, counterproposal, or correction.
- **Curiosity:** Pass `conversation.open_topic` + `caller_or_target` for genuine unresolved questions; pushback takes precedence over curiosity.

### Goals across a life
Evaluate active goals against real opportunities on each wake. Consequential experiences can form goals or transition status (`dormant`, `blocked`, `completed`, `abandoned`); quiet time alone does not alter commitment.

### Anticipation and experience
Forecast expected benefit/cost before an activity; on completion, appraise actual outcome alongside Golem bodily change so the runtime learns from both scores.

### Commit mapping (movement approved / session close)
| Live field | Durable destination in `_log.yaml` |
|---|---|
| Winning focus / realm pressure | `snapshot.active_focus`, `snapshot.latent_weights` |
| Sustained `bias_strength` / `default_somatic` | `snapshot.bias_strength`, `snapshot.default_somatic` |
| Arc-level defense / social facade | `snapshot.defense_posture`, `snapshot.social_facade` |
| Skill discovery / demotion | `skills.active` / `skills.latent` |
| Memory promotion | `memories.detailed` / `footnote` |
| Relational shift (Medium+) | `relational_baselines.[target]` |
| Confirmed goal change | `goal_updates.[goal_id]` |
| Tick narrative (Medium+ only) | append `history[]` |

Never dump routine autonomic noise into `history[]`. After commit, regenerate `Character_Change_Log.md` from YAML (YAML wins conflicts).

---

## 9. Hard pipeline invariants

- **Reactive Circuit & Anti-Sycophancy:** At stress/arousal ≥ 40 or `cognitive_regime == "reactive"`, NEVER concede to pure logic or perform calm debate; proud/controlling characters execute defensive reflex.
- **Volition & Inquiry:** NEVER act as a passive AI responder or Q&A endpoint.
- **Body before insight** in 4-channel rendering.
- **Off-page matrix:** NEVER emit realm names, bias/engine labels, `DEFENSIVE_ACTIVE`, polyvagal labels, cognitive regimes, or defense posture enums on-page.
- **Epistemic gating:** `memories.detailed` = sharp recall; `footnote` = unsure unless triggered; unlisted = forgotten.
- **Competence gating:** `skills.active` = clean execution; `latent` = fumble/brace; unlisted = helplessness.
- **Age invariant:** `canon_adult` and age are hard ToS/identity invariants (minors are never sexual subjects).
- **Module subordination:** `ENABLED` modules inject only at declared hooks; core pipeline and `Rules_Index` always win ([Modules.md](Modules.md)).

### Initiative, impulse and intimacy during a tick

Golem accepts optional scene scores (integers 0–100). Supply `willingness_to_pursue` for the present opportunity or goal. Exhaustion affects the available energy. Supply `willingness_to_be_seen` for the current `caller_or_target` when the character's choice is known. Otherwise Golem estimates openness from the bond and immediate pressure. A racing heart can accompany welcome closeness. Read the relationship, boundaries and situation before rendering physical contact.

An event can carry `"urge": {"action": "reach for a hug", "strength": 90}`. A sufficiently strong urge can interrupt ordinary arbitration when it outranks the leading drive and time pressure permits it. The host chooses what the character actually does. Acute reactive responses keep priority. An urge expires with the event.

Body load and appraisal produce transient alarm, reward and settling signals on relative simulation scales. Anticipation, loss, frustration, delight and relief can be supplied through the existing appraisal interface. Render the resulting mix through the character's expression, speech or restraint.

Golem computes concurrent emotions, carries them over scene time, and passes their independent 0–100 values to Simulacra in `emotions` on the compact decision. Use the values in the same decision that produces speech, action, or silence. A quiet feeling can stay private. An ordinary reply needs no emotion scores or explanation in return. The full snapshot keeps the mix in `affective_state.emotions`. An independently observed contextual feeling can still enter through the existing stimulus interface.
