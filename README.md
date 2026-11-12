# Simulacra
**An invisible, file-native cognitive layer for AI-assisted long-form drafting and character runtime.**

Body-first psychology, dual-aspect psyche (wound ↔ gift), realm-aware somatics — running **off-page** so manuscripts and RP stay clean of system jargon.

---

## What it is

Simulacra is the **root psychological and physical cognition layer for characters**:

| Layer | File | Job |
|---|---|---|
| **Cognitive Pipeline** | `Framework/CognitivePipeline.md` | Mind-body simulation → `Feels` / `Thinks` / `Says` / `Does` |
| **Book Writing Layer** | `Framework/Main.md` | Manuscript prose, style locks, ledgers |
| **Rules & somatics** | `Rules_Index.md`, `Psychology/realm_data.yaml` | Hard bans + body catalogs |
| **State** | `Characters/[slug]_log.yaml` + live snapshot schema | Durable vs per-tick state |

It targets common AI fiction defects: therapy-speak, perfect recall, symmetric dialogue, filler, and framework jargon leakage.

---

## Core pillars

| Pillar | Why it matters |
|---|---|
| **Body before insight** | Polyvagal mode (ventral/sympathetic/dorsal/dissociated) & somatic tells precede labeled thought |
| **Dual-Circuit Execution** | Cortical deliberation under calm vs. limbic reactive short-circuit under acute adrenaline/threat |
| **The Inner Split** | Subconscious visceral truth vs. conscious ego rationalization & defense postures |
| **Social masking** | Tracks facade strain and physical fracture points under social pressure |
| **Dual-aspect psyche** | Wound *and* gift modes — not trauma-only engines |
| **4-channel output** | Structured intent vector (`Feels` / `Thinks` / `Says` / `Does`) for downstream renderers and runtimes |
| **Durable + live state** | Logs for continuity; psychosomatic snapshot per tick |
| **100% off-page matrix** | Rules + linter keep system terms out of prose |

---

## System architecture

```
                     Cognitive Pipeline
             (Framework/CognitivePipeline.md)
              Feels · Thinks · Says · Does
             + psychosomatic_state schema
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
    Book Writing Layer         Downstream Runtimes
       (Main.md)             (CharacterSimulator)
    manuscript prose            interactive chat / host UI
```

**State:**
- **Card** (`Characters/[slug].md`) — build identity (immutable defaults)
- **Log** (`Characters/[slug]_log.yaml`) — durable runtime evolution
- **Live snapshot** — matches `Framework/Schemas/psychosomatic_state.json` each tick

**Module system:** Downstream applications register injectors in [`Framework/Modules.md`](Framework/Modules.md) to enter the cognitive loop at defined hooks (`pre_somatic`, `affect_filter`, `pre_arbitration`, `post_vector`, `app_render`, `on_commit`). Core pipeline always runs; modules are subordinate and cannot override Rules_Index, prism law, or age invariants. Core ships with an empty active module registry.

---

## Quick start (drafting)

1. Load `Framework/Main.md` + `CognitivePipeline.md` + `Rules_Index.md` + `Psychology/realm_data.yaml`
2. Load on-scene character cards and their `_log.yaml` overlays
3. Run ledger integrity pass; execute movement brief through the pipeline
4. Render clean prose; on approval, commit durable fields to the log

## Downstream integration

External interactive runtimes (e.g. `CharacterSimulator`) and host applications consume this root layer's intent vector and psychosomatic state schema. See [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) §8 for contract details.

## Deploy to book folders

From this repository:

```bash
python scripts/run.py deploy              # interactive
python scripts/run.py deploy MyBookName   # named target under parent dir
```

Deploy ships the pipeline, schema, Main, Rules, realm data, scripts, and mechanics craft files.

---

## License & disclaimer

- Software utilities (`.py`): **MIT**
- Framework specs / markdown: **CC BY-SA 4.0** — see [LICENSE.md](LICENSE.md)
- Compliance and 18+ terms: [DISCLAIMER.md](DISCLAIMER.md)

Author-local cast files stay private (see LICENSE §3 and `.gitignore`).
