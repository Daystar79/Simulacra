# Design Q&A Protocol
*Permanent recursive design workflow. Load with [Drafting_Prompt.md](Drafting_Prompt.md) on every **design** session.*

---

## Tool split

| Tool | Role | Why |
|------|------|-----|
| **Gemini CLI** | Design QA, band audits, movement outlines | ~2M context — entire manuscript + full rule stack in one pass; strong at structured design docs |
| **Cursor / Grok** | Prose draft, revision, assembly, merge | On-page voice and somatic craft; does not replace Gemini for band-scale QA |

**Handoff:** Gemini completes QA → author saves output to **`TBD/chapter_N_mM_design.md`** → paste active **Movement Brief** into `Drafting_Prompt.md` → **draft session** here writes `draft_chapter_#_m#.md`.

**Gemini does not draft prose.** Design docs and audits only unless explicitly asked otherwise.

**Gemini prompts on disk:**
- [MovementDesigner.md](Prompts/MovementDesigner.md) — **per-movement design QA** (new movement design only; manuscript closed)
- [FullBookAudit.md](Prompts/FullBookAudit.md) — full-manuscript **integrity audit** (sync, timeline, voice_protocol, release readiness)
- [improvement_pass_prompt.md](Prompts/improvement_pass_prompt.md) — **scoped band improvement pass** (irony, dread, rhythm, surgical fixes — post-close polish)

---

## When to use

| Session | Use this protocol? |
|---------|-------------------|
| **Design** | **Yes** — before Movement Brief is complete |
| **Draft** | **No** — brief is frozen; write prose only |
| **Approval / revision** | **No** — unless scope shifts → new design pass |

---

## Pre-Q&A load *(mandatory — do not ask Q1 until loaded)*

The design session assistant **must** read all files below before asking Q1 or proposing locks.

### Step 1 — Framework stack *(always)*
Read in order:
1. `Framework/Drafting_Prompt.md`
2. `Framework/Continuity_Ledger.md`
3. [source_changes.md](source_changes.md) — first ~100 lines (recent locks)
4. [formatting_rules.md](formatting_rules.md)
5. **[voices.yaml](Mechanics/voices.yaml)** — full (design must not plan voice violations)
6. [humanity.yaml](Mechanics/humanity.yaml)
8. [psyche_framework.md](psyche_framework.md) and [Framework/Psychology/](Psychology/) — Realm profiles and matrix instructions (behavior only; never nomenclature on page)

### Step 2 — Band + design archive

| File | When |
|------|------|
| `TBD/chapter_N_outline.md` | Always — active chapter band |
| `TBD/chapter_N_mM_design.md` | Prior movements in same chapter already QA'd (M2+ read M1…M−1 saves if on disk) |
| `TBD/epilogue_outline.md` | Epilogue design only |

### Step 3 — On-page prose *(minimum — non-optional)*

| Designing | Read in full |
|-----------|--------------|
| **Ch. N, M1** | **Entire preceding chapter** Ch. N−1 — every movement: `Drafts/draft_chapter_{N-1}_m#.md` (all on disk) or `Drafts/Completed/draft_chapter_{N-1}.md` |
| **Ch. N, M2+** | **Every prior movement** in Ch. N (M1 … M#−1) in `Drafts/draft_chapter_N_m#.md` **plus** **entire preceding chapter** Ch. N−1 (same rule as M1) |

**Gemini CLI:** May load `Drafts/master_manuscript.md` and full active `Completed/` band in addition — use when context allows. **Minimum** remains Step 3 table.

Verify before Q1: timeline, locations, somatic close, parallel lanes.

### Step 4 — Character cards *(on-scene + POV)*

- POV card — always
- Every on-scene character card in `Characters/` directory
- Background on-scene cards only when load-bearing

### Step 5 — Declare load complete

Output a short **Load manifest** (chapter/movement target, files read, last on-page close verified) plus **Auto guardrails** (merged must-not list) — **then** begin Q1.

**Never** callback staging that didn't happen (somatic state on close).

---

## Question order (default spine)

Use this sequence for every movement. Skip only if already locked in band scope or prior movement.

| # | Question | Locks |
|---|----------|-------|
| — | **Auto guardrails** | Declared by assistant after load — **not asked** |
| 1 | **Job** — What is this movement's single job? (one primary; optional secondary) | Movement purpose |
| 2 | **Reader** — What must the reader *see* or *feel*? *(positive only — deferrals live in Auto guardrails)* | Dramatic irony, scope |
| 3 | **POV** — Who holds the camera? Who is on scene? | POV lane |
| 4 | **Opens** — Exact image / room / line? | Open beat |
| 5 | **Characters** — Per on-scene character: what would they **do**, **think**, **believe**? *(character lens — cards + behavior + prior prose)* | Behavior spine |
| 6 | **Dual arc** — Trace parallel character arcs/motivations if multi-POV or sideplots? | Parallel lanes |
| 7 | **Must-land** — Ordered beats 1–6 | Draft spine |
| 8 | **Close** — Last image; who goes where; next movement handoff | Close + handoff |
| 9 | **Checklist** — World setting rules, vestments, rhythms, thematic tags, protocols | Pre-draft checklist |

Add **movement-specific** questions between 5 and 7 when needed (e.g. after a huge prior movement: *How does X react to Y?*) — still **one per turn**, still **Pro/Con per option**. Any question touching a named character runs through the **character lens** (below).

---

## Character lens *(mandatory for character Q&A)*

Any Q&A turn about **who does what, says what, wants what, or carries what** must be answered **through that character's lens** — not plot convenience, not author summary, not merged voices.

**Frame questions as:**
- What would **[character]** actually **do** here? (body first — action, refusal, stillness)
- What would they **think** in third-limited interior? (their idiolect, not therapist or operator register)
- What do they **believe** is true right now? (beliefs, motivations, context — per card)

**When presenting options to the user:** Run the **real-person test** on each option before offering it (see Core rule §4). Options that fail — drop or revise.

**Do not ask or lock:**
- "What should happen in the scene?" without naming whose want drives it
- Interchangeable dialogue lanes (separate cards mean separate voices and wants)
- Psychology labels or framework nomenclature on page — translate to **behavior** only
- **Standard tropes** or conventional moral crises that conflict with their defined cognitive biases or character cards. Sincere belief, somatic shock, and internal compartmentalization must drive their depiction.

**Required reads before character locks**:
- On-scene character cards in the `Characters/` directory (POV card first) and active depictions in prior movements. **Always read the character cards and depictions before proposing questions or options that affect them.**
- **`voices.yaml`** + **`humanity.yaml`** — voice split, no blending
- **`psyche_framework.md`** + **`Framework/Psychology/`** — Realm profiles and rules for each on-scene character
- Prior on-page prose for that character in preceding chapter + current band movements

**Answer format for character turns:** *Locked: [Character] — [believe / want / do]* in one sentence grounded in card + last on-page beat.

---

## Answer format (assistant)

Each turn after the user answers:

- **Locked:** one sentence recording their choice
- **Next:** one new question only

When the spine is complete, paste filled blocks into **Movement Brief** in [Drafting_Prompt.md](Drafting_Prompt.md). The author then saves the completed outline to **`TBD/chapter_#_M#_design.md`** — permanent archive; not deleted on approval.

---

## Saves

| File | Use |
|------|-----|
| [Drafting_Prompt.md](Drafting_Prompt.md) → Movement Brief | Active session (current movement only) |
| [TBD/chapter_#_M#_design.md](TBD/) | **Completed movement** — full QA outline after design session *(user adds)* |
| [TBD/chapter_N_outline.md](TBD/) | Chapter band map (pending / in-progress) |
| [source_changes.md](source_changes.md) | Design locks + approvals |

**Do not delete** `TBD/chapter_#_M#_design.md` when a movement or chapter is approved. On-page prose in `Drafts/` supersedes TBD on conflict.

---

## Example (abbreviated)

**Load manifest — Auto guardrails:** No kitchen scene, no name-drops; phrase watchlist per `Drafting_Prompt.md`.

**Q1 — Job** *(each option shown with Pro/Con in session)*  
**A:** Choice A — focus on character's entry.  
**Locked:** Job = reveal the character's arrival and their immediate shock.

**Q2 — Reader** *(positive only)*  
**A:** Choice B — reader tracks physical reaction and silence.  
**Locked:** Reader feels the weight of the room through character's stillness.

*(Continue one question at a time until brief complete.)*

---

*Last updated: 2026-07-14 — MC Pro/Con mandatory; Must-not auto-compiled (not user Q)*