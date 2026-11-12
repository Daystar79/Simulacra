# MAIN — Book Writing Layer (Manuscript Engine)
*System: Simulacra · Role: Novel drafting & prose rendering*

---

## Architecture

The **Book Writing Layer** consumes the Cognitive Pipeline’s 4-channel vector (`Feels`, `Thinks`, `Says`, `Does`) and renders clean manuscript prose. Psychology and body runtime live in the pipeline — not here.

```
 🧠 COGNITIVE PIPELINE  (Framework/CognitivePipeline.md)
         │  Feels / Thinks / Says / Does + live psychosomatic snapshot
         ▼
 📖 BOOK WRITING LAYER  (this file)
   ├── Style locks & prose craft
   ├── Output hygiene (Rules_Index)
   ├── Ledger integrity
   └── Manuscript prose only (off-page matrix)
```

---

## Session boot (drafting)

Run once at session start, before a movement brief:

1. **Load stack (always):**
   - `Framework/Main.md` (this file)
   - `Framework/CognitivePipeline.md`
   - `Framework/Rules_Index.md`
   - `Framework/Psychology/realm_data.yaml`
   - `Framework/Modules.md` (registry — may be empty of ENABLED rows)
   - On-scene cards: `Characters/[slug].md`
   - Durable logs: `Characters/[slug]_log.yaml` (overlay card defaults)
   - `Framework/Continuity_Ledger.md`
2. **Modules into the cognitive loop:** verify ENABLED rows in [Modules.md](Modules.md); inject only at declared hooks during each pipeline tick. Downstream books add their own modules by registering paths here.
3. **Optional non-module craft (brief-driven):**
   - `Framework/Mechanics/prose.md`, `voices.md`, `humanity.md`
   - `Framework/natural_prose.md` — when Style = `natural`
4. **Never load:** `source_changes.md`, `formatting_rules.md`, `Framework/Prompts/*`, debug dumps.
5. **Ledger integrity pass** (§ below). Gate = CLEAN before drafting.
6. **Style lock:** default `LOCKED` to project style (`natural` | `cinematic` | `historical` | `llm`). Change only on explicit unlock.

---

## Canonical state

| Layer | File | Role |
|---|---|---|
| Build identity | `Characters/[slug].md` | Immutable defaults (voice, wound/gift, build weights) |
| **Durable runtime** | `Characters/[slug]_log.yaml` | Focus, weights, skills, memories, history, relational baselines |
| **Live tick** | Snapshot matching `Schemas/psychosomatic_state.json` | Autonomic/affect/arbitration/4-channel for this beat |
| Projection | `Framework/Character_Change_Log.md` | Regenerated human summary |

**Conflict rule:** YAML/JSON state wins; Markdown projections are regenerated from state.

Pipeline owns live ticks and commit mapping. Full protocol: [CognitivePipeline.md](CognitivePipeline.md) §3 and §8.

---

## Ledger integrity pass (pre-session)

1. **Continuity_Ledger:** chapter/movement rows current; prior movement committed.
2. **Character logs:** load latest `snapshot` over card defaults for each on-scene slug.
3. **Gates:**
   - **CLEAN** → proceed to movement brief.
   - **BLOCKED** → resolve ledger lag before prose.

---

## Drafting workflow (per movement brief)

| Step | Operation | Detail |
|:---:|---|---|
| **1** | Query pipeline | Run [CognitivePipeline.md](CognitivePipeline.md) with brief as trigger. Receive 4-channel vector + live snapshot (`polyvagal_mode`, `cognitive_regime`, inner split, mask strain/fracture). |
| **2** | Body precedence | Render somatic cascades (2+ zones) and mask fracture tells **before** or folded into speech/action. Never bracketed `[tell]`. |
| **3** | Dialogue & Mask | Preserve idiolect, clipping, asymmetry, active volition, and counter-inquiry from card `voice.*` + `Says`. In deliberative mode: filter through facade and posture. In reactive mode: render as raw vocal reflex (snap, blunt denial, sharp interruption, stammer, silence). |
| **4** | Internal Monologue | In deliberative mode: express ego rationalization in `Thinks` while action leaks visceral truth. In reactive mode: render `Thinks` as fragmented visceral loops, sensory shock, or cognitive blank. |
| **5** | Style lock | Enforce project style; no purple prose / AI clichés unless style allows. |
| **6** | Anti-synthesis | Close paragraphs on sensory fact, raw action, or unanswered dialogue — never interpretive summary. |
| **7** | Hygiene | Apply [Rules_Index.md](Rules_Index.md) hard bans (no system jargon, polyvagal labels, cognitive regimes, or posture enums on page). |
| **8** | Commit | On approval: merge durable fields into `_log.yaml` per pipeline §8; update Continuity_Ledger scene-close body; regenerate Character_Change_Log if needed. |

### Style lock machine
- `LOCKED` — do not drift mid-movement.
- `UNLOCK` — author command only; then re-`LOCK` at new style.
- Style = `llm` disables natural-prose constraints.

### Intimacy & desire handling
Character attraction and desire are output states of the core pipeline ([CognitivePipeline.md](CognitivePipeline.md) §7.1)—never gated by switches or modes. Explicit erotica craft (if any) is non-core, lives in downstream projects, and registers via [Modules.md](Modules.md). The core pipeline outputs character stance and intent without explicit sexual choreography.

---

## Hard invariants (drafting)

- **Reactive Primacy & Anti-Sycophancy** — Characters under acute stress or in reactive regime do not calmly concede debates or act as reasonable consensus-seekers. Characters fight, deflect, or withdraw according to their archetype.
- **Active Character Agency & Brief Supremacy** — Character volition governs *how* characters act (actively probing, resisting, advancing personal goals), while the Movement Brief governs *what* narrative milestones occur. Volition creates realistic dramatic friction to reach scene goals without derailing movement completion.
- **Clean manuscript only** during draft output — no CONFIG cards, audit tables, or debug banners in the draft file.
- **100% off-page matrix** — Focus, Bias, Gift, Prism, Realm labels never appear in prose.
- **Card supremacy** — card baseline overrides generic AI tropes; log overrides card for evolved state.
- **Pipeline is the psyche runtime** — do not re-implement wound/gift/realm math inside this file.
- **Modules extend the loop** — register in Modules.md; never bypass core supremacy.

---

*Loaded for manuscript drafting. Executes on movement briefs.*
