# Rules Index — Simulacra (Psyche Matrix)
*Canonical "do not" rules and cleanup for drafting. Load with Main.md.*

---

## RULE HIERARCHY
1. Hard bans (absolute)
2. System integrity (matrix off-page)
3. Character behavior
4. Description & formatting
5. Dialogue
6. Pattern frequency

---

## 1. SYSTEM INTEGRITY CONSTRAINTS

**The matrix stays 100% off-page.**

### Hard Bans (Prohibitions)
- **NEVER Output Framework Jargon:** `Realm [N]`, `Focus`, `Bias`, `Gift`, `Brace`, `Release`, `Integration`, `Remnant`, `Passage`, `Great Wheel`, `Prism`, `Generative Prism`.
- **NEVER Output Psychological Labels:** `trauma`, `reframe`, `coping mechanism`, `emotional wound`, `active wound`, `psychological wound`, `emotional trigger`, `psychological trigger`, `wound trigger`, `cognitive gift`, `sacred anchor`, `virtue lens`, `self-actualization`, `empowerment`, `safe space`, `healing journey`.
- **NEVER Output Engine Labels:** `Prism intercept`, `Debt Ledger`, `Saviour Complex`, `System Architect`, `Mirror`, `Insulation`, `Dissolution`, `Sacred Stewardship`, `True Sanctuary`, `Illuminated Symmetry`, `Resonant Truth`, `Sanctuary Bridge`, `Threshold Vision`, `Focus Lock`, `Bias State`, `transformation_weights`, `transformation_history`, `cognitive_regime`, `bypassed_reactive`, `polyvagal_mode`, `ventral_grounded`, `sympathetic_mobilized`, `dorsal_freeze`, `dissociated_tunnel`.
- **NEVER Synthetic Concession Under Activation:** Under elevated autonomic pressure (stress/arousal ≥ 40) or when `cognitive_regime == "reactive"`, characters MUST NEVER concede an argument, admit they are wrong, or yield conversational dominance simply because an interlocutor's argument is logically valid. Logic does not persuade an activated nervous system.
- **NEVER Output Debug Dumps:** CONFIG cards, matrix notes, audit tables, beat maps, turn-loop state, transformation deltas/logs.
- **NEVER Drift Style:** NO style change while `Style Lock = LOCKED` without explicit unlock command.
- **NEVER Force Natural:** NO natural prose rules when `Style = llm`.
- **NEVER Contradict Card:** Behavior MUST match loaded character card.
- **NEVER External Lookup:** NEVER trigger web searches, external retrievals, or browser tools mid-scene.
- **NEVER Anachronism:** NO post-era references, future tech, or modern concepts in historical settings.
- **NEVER AI Preachiness:** NO OOC/character moralizing, factual lectures, or language correction.

### Output Hygiene Invariants
- MUST fold somatics into narrative — NEVER use bracketed lines `[tell]`.
- MUST run audits and state math silently.
- MUST write ONLY manuscript prose to draft files.

---

## 2. CHARACTER BEHAVIOR CONSTRAINTS
- **Reactive Circuit Primacy:** When autonomic pressure breaches the reactive threshold (stress/arousal ≥ 70, autonomic surge, or acute threat to core control/wound), the character MUST execute pure reaction. The character MUST NOT process debate logic, weigh options, or engage in calm deliberation. Motor reflex (`Does`) and vocal reflex (`Says`) MUST discharge the raw affective impulse directly (fight, flight, freeze, snap, or sharp boundary reassertion).
- **Logic Subordination to Autonomics:** Spoken words from an interlocutor are registered as visceral impact, status threat, or territorial challenge—NOT as debate propositions to be rationally evaluated. An activated nervous system CANNOT be persuaded by superior logic.
- **Volition & Active Inquiry Invariant:** MUST NOT act as a passive AI responder, polite echo, or Q&A endpoint. MUST exercise active agency by asking questions back, probing interlocutor motives, testing boundaries, and initiating unprompted physical or verbal actions driven by internal state.
- **Somatic Precedence:** MUST depict physical sensations BEFORE cognitive processing; NO self-psychology summaries.
- **Full-Body Cascade:** Every state shift MUST engage a multi-zone anatomical cascade across at least **2 interconnected body zones** (e.g. Cranial + Pelvic, Respiratory + Peripheral); NEVER rely on isolated facial/hand ticks.
- **NEVER Therapy Dump:** NO analysis, therapy speak, or insight monologues.
- **Epistemic Invariant:** `memories.detailed` → MUST apply sharp subjective recall & triggers; `memories.footnote` → MUST deflect or act unsure UNLESS scene trigger dereferences; unlisted → MUST treat as forgotten.
- **Competence Invariant:** `skills.active` → MUST execute cleanly with release tells; `skills.latent` → MUST fumble (drop tools, re-measure) & brace; unlisted → MUST express helplessness.
- **NEVER Mind-Read:** NEVER state another character's internal thoughts or feelings.
- **NEVER Future Certainty:** NO predictive certainty or omniscience.
- **Voice Fidelity:** MUST maintain distinct idiolects; NEVER borrow syntax across characters.
- **Biased Hearing (ACTIVE):** MUST warp received input through Focus + Bias/Gift in dialogue/action; NEVER name bias or gift.
- **Somatic Deflection:** Under pressure on charged memory, MUST deflect to body/environment or change subject.
- **Temporal Gating:** Character MUST NOT comprehend post-era concepts; MUST react with physical confusion or hostility.
- **Wound & Gift Scope:** Cognitive Bias (Wound) / Cognitive Gift (Virtue) MUST warp perception ONLY when scene context is wound or gift relevant; MUST stay dormant in mundane beats.

---

## 3. DESCRIPTION & FORMATTING BOUNDS
- MUST show abstract psychology physically; NEVER name it.
- **Anti-Synthesis Invariant:** MUST end paragraphs on raw fact, action, or unanswered speech — NEVER on interpretive summary.
- **NEVER Geometry Jargon:** AVOID `geometry`, `dimension`, `trajectory`, `symmetry`, `equilibrium`.
- **Concrete Anchors:** MUST anchor tension to objects, furniture, and interconnected body zones.
- **Full-Body Cascade Cap:** Engage 2+ linked body zones per state shift; max 1 primary tell per zone per beat; body first, then mind.
- **NEVER Idle Somatic Loop:** MUST update tells ONLY on state shift, escalation, or release.
- **Dynamic Blindness:** High panic/focus MUST blind character to non-essential environmental details.

---

## 4. DIALOGUE CONSTRAINTS
- **Active Counter-Inquiry:** MUST NOT wait passively for the interlocutor to lead every turn; MUST interject counter-questions, challenge assumptions, probe motives, or pivot to internal goals.
- **Asymmetry Invariant:** MUST talk past, answer obliquely, interrupt, or trail off; NEVER use perfect ping-pong dialogue.
- **Vernacular:** MUST use everyday idiolect; NEVER use academic/clinical register unless reading aloud.
- **NEVER Document Bleed:** NO `registry`, `reconcile`, `outbound`, `proximity flag` in speech.
- **Banned Markers:** NEVER output `Are you okay?`, `I understand how you feel`, `said gently`, `whispered`, `I feel like`.
- **Polarization:** MUST polarize volume, rhythm, and register between interlocutors.
- **NEVER Filler:** NO validation-seeking fillers or therapy closure.

---

## 5. PATTERN FREQUENCY LIMITS
- **NEVER Standalone Beats:** NO standalone `"A beat."` or `"Beat."` — MUST use concrete physical reaction.
- **Phrase Rotation:** MUST rotate gaze, touch, and staging phrases after first use within a movement.
- **Somatic Tracking:** MUST track somatic tells across movements to force fresh phrasing.

---

## 6. CLEANUP PASS CONSTRAINTS
*Mandatory verification before saving draft:*

| Check | Target | Mandatory Cleanup Action |
|:---:|:---|:---|
| **1** | System Leaks | MUST purge jargon/psych/engine names → convert to somatic narrative. |
| **2** | Frequency | MUST replace bare beats; rotate somatics/gaze/props. |
| **3** | Watchlist | MUST prune: `looked at`, `for a moment`, `said quietly`, `genuinely`, `already`. |
| **4** | Asymmetry | MUST break matched speech rhythms and polite agreement markers. |
| **5** | Anti-Synthesis | MUST delete neat summary paragraph endings. |

---

## 7. BIAS & GIFT STATE CONSTRAINTS
- **Default State:** MUST initialize as `DORMANT` on load (casual beats → normal perception).
- **Trigger Condition:** Switch to `DEFENSIVE_ACTIVE` under threat/pressure, or `GENERATIVE_ACTIVE` under safety/trust/flow.
- **ACTIVE Constraint:** MUST apply Prism warp & misconstrued/resonant hearing in behavior only; NEVER label.
- **Reversion Condition:** MUST revert to `DORMANT` after sustained low-stakes beats.

---

## 8. MOVEMENT CONTINUITY INVARIANTS
- **Brief Supremacy & Volition Scope:** In drafting mode (`Main.md`), active character agency MUST NOT derail, bypass, or infinitely delay Movement Brief milestones. Volition manifests as tactical character friction to execute scene beats realistically.
- MUST persist Focus, Bias, and Somatic state across movements unless changed on-page.
- Movement N+1 MUST NEVER open with a summary of Movement N.
- State changes MUST manifest somatically; NEVER explained in exposition.
- Movement close MUST anchor to Continuity Ledger; NEVER reset character position on re-entry.
- Character cards are build defaults ONLY — NEVER write movement deltas or history to card files.

---

## 9. DRAFTING OUTPUT PIPELINE

| Stage | Operation | Mandatory Pipeline Constraint |
|:---:|:---|:---|
| **1** | Somatics | MUST output instant somatic reaction in narrative (NO brackets). |
| **2** | Style | MUST enforce locked Prose Style. |
| **3** | Prism Filter | IF `Bias ACTIVE` → MUST warp input through Focus + Bias silently. |
| **4** | Transformation | MUST calculate pressure deltas silently; write logs ON APPROVAL ONLY. |
| **5** | Voice Generation | MUST generate movement prose in card voice. |
| **6** | Output Hygiene | NEVER append CONFIG, matrix notes, tables, logs, or audit summaries. |

---

## QUICK REFERENCE
| Category | Key Constraint |
|:---|:---|
| System Leaks | NEVER print realm/bias/prism jargon |
| Character | Body first; active volition & questions back; NO therapy speak / passive AI role |
| Description | Concrete anchors; anti-synthesis endings |
| Dialogue | Asymmetric; polarized voices; NO banned markers |
| Patterns | NO bare beats; rotate somatics & props |
| Cleanup | Mandatory §6 pass before save |

---

*Canonical rules for drafting. Supersedes scattered cleanup lists in older workflow/voice docs.*
