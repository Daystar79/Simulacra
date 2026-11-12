# Modules Index — Simulacra
*Extension registry for the Cognitive Pipeline. Downstream applications register modules here to inject into the cognitive loop.*

Load with the pipeline and the active app host ([Main.md](./Main.md) or downstream application renderer).

---

## 1. Purpose

The **Cognitive Pipeline** is the fixed psychological / physical character runtime.  
The **module system** is how downstream applications (book projects, host tools) **add optional behavior into that loop** without forking the core engine.

| Layer | Role |
|---|---|
| **Core pipeline** | Always on: nervous system → affect → prism → arbitration → 4-channel vector |
| **Modules** | Optional, registry-gated injectors at defined loop hooks |
| **App hosts** | Main / downstream renderers present output; they do not re-implement psyche |

Modules are **not** a second personality engine. They supply domain constraints, craft rules, genre pacing, or app-specific filters that run *inside* the pipeline tick under core supremacy.

---

## 2. Core supremacy rule

No module may override, supersede, or conflict with:

1. **`Rules_Index.md`** hard bans and output hygiene  
2. **`CognitivePipeline.md`** sequence, state model, and invariants  
3. Character **card + `_log.yaml`** supremacy for identity and durable state  
4. Absolute **age gates** (`canon_adult`, age ≥ 18) for adult content  

On conflict: core wins; the conflicting module instruction is **silently ignored** (optional stdout warning for agents).

---

## 3. Cognitive loop hooks

Modules declare which hook(s) they use. Agents apply ENABLED modules only at those points:

```
 📥 Event trigger
        │
        ▼
 1. NERVOUS SYSTEM          ← hook: pre_somatic (rare; ambient body modifiers)
        │
        ▼
 2. RAW AFFECT              ← hook: affect_filter (genre/intensity shaping)
        │
        ▼
 3. PRISM (wound/gift)      ← core only — modules MUST NOT rewrite prism law
        │
        ▼
 4. PRIORITY ARBITRATION    ← hook: pre_arbitration (drive weights, context multipliers)
        │
        ▼
 5. 4-CHANNEL VECTOR        ← hook: post_vector (craft constraints on Feels/Thinks/Says/Does)
        │
        ▼
 6. APP RENDER              ← hook: app_render (prose/RP presentation only; host-owned)
        │
        ▼
 7. COMMIT                  ← hook: on_commit (extra durable fields if declared)
```

| Hook | May do | Must not do |
|---|---|---|
| `pre_somatic` | Suggest extra ambient tells | Replace realm_data catalogs or invent on-page jargon |
| `affect_filter` | Scale intensity / gate domains | Force emotions that contradict card + live state |
| `pre_arbitration` | Adjust context multipliers / competing drives | Override card baseline weights permanently without commit rules |
| `post_vector` | Constrain how channels are phrased/crafted | Emit system labels into `Says` meant for on-page use |
| `app_render` | Style/genre presentation rules | Bypass Rules_Index hygiene |
| `on_commit` | Append module-specific durable notes | Write evolution into the character **card** |

---

## 4. Active modules registry

Only rows with an existing file and `ENABLED` status load. Downstream apps **add rows** (or drop local module files under the book tree) to extend the loop.

| Module Name | Path | Status | Hooks | Compatibility |
|:---|:---|:---|:---|:---|
| *(None shipped in core)* | — | — | — | Core runs fully with zero ENABLED modules |

*Note: Downstream projects register local modules in their deployed copy of this registry. The core framework ships with an empty active registry.*

### How a downstream app adds a module

1. Author the module file (e.g. `Framework/Mechanics/mystery.md` or `Modules/my_app_tuning.md` in the **book** folder).
2. Declare in the module header: hooks used, incompatibilities, dependencies.
3. Register a row in **this file** (or the book’s deployed copy of it) with Status `ENABLED`.
4. On next session boot, agents run verification (§5) and inject at declared hooks only.

To disable: set Status to `DISABLED` or remove the row — core pipeline continues unchanged.

---

## 5. Verification rules (for AI agents)

Before applying any module:

1. Scan the registry for Status = `ENABLED`.
2. If none: skip module protocol entirely (core pipeline only).
3. For each ENABLED row: resolve path; if missing → skip with warning.
4. **Compatibility check:**
   - No contradiction with `Rules_Index.md` hard bans / off-page matrix  
   - No conflict with other currently ENABLED modules’ declared incompatibilities  
   - Adult modules: all on-scene participants pass age gates  
5. On failure: `[Warning] Module [Name] failed verification: … Skipping.`
6. Apply verified modules as **subordinate** parameters at their hooks only — never as a replacement for `CognitivePipeline.md`.

---

## 6. Load order

- Registry order = application order within the same hook.
- Later modules cannot disable earlier ones except via explicit incompatibility (then the later one is skipped).
- Multiple non-conflicting modules may run on the same tick.

---

## 7. Shipped optional craft vs app modules

| Kind | Location | Notes |
|---|---|---|
| **Core** | `CognitivePipeline.md`, `realm_data.yaml`, schema | Always loaded — not modules |
| **Shipped optional** | `Framework/Mechanics/*` | Registered above when used as loop injectors |
| **App-local** | Book tree `Modules/` or `Framework/Mechanics/` | Downstream owns content; register here to enter the loop |

Planned / not shipped (examples only — add when real files exist):

- Mystery Engine — `Modules/mystery.md`
- Romance Tuning — `Modules/romance.md`
- Action & Pacing — `Modules/action.md` (incompatible with Romance Tuning when both try exclusive pacing hooks)

---

## 8. Session boot integration

**Always load this registry file** when running drafting or downstream sessions so agents know what is enabled.

- **Pipeline:** execute core sequence; at each hook, apply ENABLED modules for that hook.
- **Main / Downstream hosts:** still own presentation; `app_render` modules refine host output only.

There is no separate “module runtime.” Modules are **configuration for the cognitive loop**.

---

*Registry is deployable. Downstream books edit their copy to enable app-specific injectors without modifying upstream core files in place (or re-register after deploy).*
