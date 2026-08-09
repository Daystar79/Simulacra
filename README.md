# Simulacra

**Desktop roleplay host** for the [CharacterSimulator](https://github.com/Daystar79/CharacterSimulator) cognitive pipeline — not the mind engine itself.

**Product name:** Simulacra  
**Code / repos:** still under `CharacterSimulator.UI` / `CharacterSimulator.*` project names.

```text
Human  →  Simulacra (this app)  →  LLM  ←  Cognitive Pipeline prompts / cards
                │
                ├── SQLite profiles, sessions, portraits
                ├── Character cards (identity)
                └── Optional image engines (portraits / scenes)
```

---

## What this is

| Simulacra **is** | Simulacra **is not** |
|:---|:---|
| A Blazor desktop (Photino) **roleplay host** | The prompt-only paste runtime (`CharacterRuntime.md`) |
| Card loaders, safety gates, session/DB bookkeeping | The full psyche math (that stays in LLM + Framework prompts) |
| Theme chrome, scene/location, portrait generation UX | Midlayer book-writing tools |

Upstream cognitive / card **schemas** live in **CharacterSimulator** (or CognitiveMiddleware). Simulacra **implements** loaders, gates, and UI against those contracts.

---

## Solution layout

| Project | Role |
|:---|:---|
| `CharacterSimulator.GUI` | Photino + Blazor desktop shell (**Simulacra**) — **stage still** (left: physical + scene, one button) · dialogue (center) · character + scene controls (right) |
| `CharacterSimulator.Logic` | Host services: cards, catalog, safety, prompts, images, SQLite |
| `CharacterSimulator.Logic.Tests` | xUnit tests |
| `Characters/` | Card templates + sample cast (JSON/MD) |

The old Spectre.Console **TUI** host was removed — the product surface is the desktop GUI only.

Entry: **`CharacterSimulator.UI.sln`**

---

## Character card fields (identity)

Cards keep **separate** human-facing fields (do not merge into one “description”):

| Field | Meaning |
|:---|:---|
| `personality` | Who they are (temperament, values, stance) |
| `behavior` | How they act under pressure / trust / routine |
| `physical` | Body only (imaging identity; structured map preferred) |
| `character_style` | Default dress / accessories |
| `hobbies` | Free-time scene fuel |
| `voice`, psyche matrix, … | Speech + engine wound/gift (unchanged) |

Profile panel shows **Personality · Behavior · Physical · Style** as **tabs** (one editor at a time).  
Portrait prompts use **physical + character_style only**.

See `Characters/HOW_TO_CARD.md`, `Characters/_template.json`, and upstream CharacterSimulator card docs.

---

## UI themes (chrome packs)

Themes recolor **application chrome** via CSS design tokens (`data-theme` on `<html>`).

| Id | Display name | Intent |
|:---|:---|:---|
| `midnight` | Midnight Slate | Default product dark (cyan accent) |
| `cyberpunk` | Cyberpunk Synthwave | Neon cyan/magenta |
| `matrix` | Emerald Matrix | Terminal green |
| `amber` | Solarized Amber | Warm mahogany / amber |
| `obsidian` | Obsidian OLED | True black / silver |

**How it works**

- Token packs: `CharacterSimulator.GUI/wwwroot/css/app.css`
- Boot / apply: `wwwroot/js/theme.js` → `csTheme.apply(id)` (also writes `localStorage`)
- Scene atmosphere: `csTheme.setSceneBackdrop(url)` after scene art generation
- Catalog metadata + preview swatches: `ThemeCatalog` in Logic
- Switch: menu **Theme**, or **Setup → UI Theme** (live preview cards)

---

## Build & test

```bash
dotnet build CharacterSimulator.UI.sln
dotnet test CharacterSimulator.Logic.Tests/CharacterSimulator.Logic.Tests.csproj
dotnet run --project CharacterSimulator.GUI
```

SSH push (if using machine keys):

```bash
GIT_SSH_COMMAND="ssh -i /mnt/Books/Keys/id_ed25519_github -o StrictHostKeyChecking=accept-new" git push origin main
```

See [AGENTS.md](AGENTS.md) for agent notes.

---

## Related repos

- **CharacterSimulator** — prompt runtime, Framework pipeline, card templates, rendering engine docs  
- **CognitiveMiddleware** — pipeline core lineage (where applicable)

---

## License / cast

Follow the upstream CharacterSimulator license carve-outs for named cast cards. Templates (`_template*`) are the public scaffold; named characters may be author-local.
