# TODO — New features & product roadmap

Work that is **not** bugfix (see `fixme.md` and `to_do.md`). Ordered for a friend-testable build first.

### [x] Local SLM & Embedded Dolphin Prompt Builder
- [x] Broken out local model / embedded SLM prompt builder into `LocalSlmPromptBuilder.cs`
- [x] Supports Dolphin 3.0 (`LocalSlmFormat.Dolphin`), ChatML (`<|im_start|>`), Llama3 (`<|start_header_id|>`), Alpaca, and Plaintext formats
- [x] Auto-detects Dolphin and Llama3 models from GGUF file paths / names (`DetectFormat`)
- [x] Created `CharacterRuntime_Dolphin.md` in `/mnt/Books/Source/CharacterSimulator/Simulator/`
- [x] Context-aware transcript trimming (6 lines max) and top-of-system safety mandate placement
- [x] Integrated into `LlamaSharpLlmClient` and `OllamaLlmClient`
- [x] Model Downloader Catalog with Dolphin 3.0 1B/3B, HuggingFace CDN redirect fixes, user-agent headers, and disk deletion manager
- [x] Token Offloading pass: C# deterministic bond/goal/somatic inference, trimmed baselines & memories
- [x] Formatting Hygiene: Clamped prompt leaks (`[Player]:`), bracket unwrapping, and styled narration prose CSS


Architecture reminder:

```text
UI  →  Roleplay module (host)  →  Cognitive engine
```

New features below belong in the **roleplay host + thin UI**, not in the cognitive engine.  
Midlayer (book writing) only needs the cognitive engine and is out of scope here.

### Storage decision (updated)

**Runtime user data is SQLite, not files.**

| On disk as files | In SQLite |
|---|---|
| Shared character **templates** (`Characters/*.md`, json) | Profiles, PIN meta, DOB (encrypted), prefs |
| Shipped assets (`Data/realm_data.yaml`, schemas) | Sessions, turns/history, mode/scene/cast |
| Optional human **exports** (md/json for debugging) | Character progress per profile (bond, bias, log fields, history events) |
| | Roster / last-played indexes |

- **Source of truth** for multi-user progress = database(s).  
- Prefer **one encrypted DB per profile** (open on unlock, close on lock/switch) so PIN isolation is physical, not “remember the WHERE clause.”  
- YAML `*_log.yaml` / `session_*.json` paths are **legacy**; new code should not grow them. Optional one-way import later.

### Preferred implementer

- Keep prompts seam-scoped (host/DB only; do not reimplement cognitive engine).  
- Prefer large-context implementers for multi-feature host/DB slices; smaller models for narrow follow-ups.

---

## P0 — Friend-test MVP: multi-user on one PC + SQLite

Single machine, multiple people, sequential use. Soft privacy + clear “who is playing.”

### [x] SQLite host data layer
- [x] Add SQLite dependency appropriate for .NET 10 (`Microsoft.Data.Sqlite`)
- [x] `schema_version` + forward-only migration runner (`AppDbInitializer.cs`)
- [x] Repository APIs in Logic (`ProfileRepository`, `SessionRepository`, `CharacterProgressRepository`)
- [x] Replace / wrap `SessionService` and durable progress with SQLite tables
- [x] Transactional save (session + turns + progress in one commit)
- [x] DB location under app data/`Profiles/app_data.db`

### [x] Profile system
- [x] Create / list / select active profile (`ProfileService.cs` + `ProfilePickerWindow.axaml`)
- [x] Switch profile from menu with PIN validation
- [x] Show active profile name prominently in window title and top header badge
- [x] Public profile list requires PIN only for unlock

### [x] Player identity & age for adult gate
- [x] On create: display name + date of birth (Year / Month / Day)
- [x] Derive age at runtime from DOB
- [x] Adult path formula: Profile age ≥ 18 AND user adult attestation AND character canon_adult
- [x] Under-18 profile: adult path permanently locked
- [x] Attestation UX: `/adult` command + first-run checkbox for adult profiles

### [x] PIN + security
- [x] On create: optional PIN with PBKDF2 salt/hash security
- [x] Key derivation: PBKDF2 with SHA-256 + 10,000 iterations per profile
- [x] Failed PIN attempt fails closed

### [x] Character templates vs progress
- [x] Shared preset cards remain read-only files under `Characters/`
- [x] All progress/history/sessions live in SQLite DB

### [x] Session save / resume (DB)
- [x] Create session on setup start; append turns as host events fire directly into SQLite
- [x] Resume and list sessions for profile

### [x] Wire existing host services
- [x] `TurnManager` and GUI turn steps append directly to SQLite database

### [x] GUI (required for friends)
- [x] Profile picker window (`ProfilePickerWindow.axaml`)
- [x] Create profile wizard (`CreateProfileWindow.axaml`)
- [x] Unlock with PIN
- [x] Switch profile from menu

### [x] Tests & ship bar
- [x] Unit tests: schema migrate, create profile, wrong PIN, age from DOB, session round-trip, progress isolation (`ProfileAndDatabaseTests.cs`)
- [x] `dotnet test` + `dotnet build CharacterSimulator.UI.sln` green

---

## P1 — Friend-test polish

### [x] Recovery code (optional but reduces support pain)
- [x] One-time recovery code at profile create (`ProfileRepository.cs` `GenerateRecoveryCode`)
- [x] “Forgot PIN” flow using recovery code (`ProfileRepository.ResetPinWithRecoveryCode`)
- [x] Still no server-side recovery

### [x] PIN change
- [x] Unlock with old PIN → re-key DB / re-seal → atomic replace (`ProfileRepository.UpdatePin`)

### [x] Clear “who is playing” UX
- [x] Profile name always visible during play (header badge)
- [x] Dirty session protection & profile active tracking

### [x] First-run / empty-state copy for testers
- [x] `FRIENDS_TEST.md`: create profile, PIN warning, SQLite location, `/adult`, how to report bugs

### [x] Version stamp for builds
- [x] Assembly / informational version visible in UI or `/status` (`AppVersionInfo.cs`)
- [x] GitHub release check service (`GitHubUpdateCheckService.cs`)

### [x] Optional export tools
- [x] Export session transcript to `.md` for sharing (`SessionExportService.ExportSessionToMarkdown`)
- [x] Export character progress snapshot JSON for debugging (`SessionExportService.ExportCharacterProgressToJson`)

---

## P2 — Distribution & updates

### [x] GitHub Releases packaging
- [x] Publish GUI artifacts for friend installs (`scripts/publish_releases.sh`)
- [x] Simple version check: `GET .../releases/latest`, compare semver, open releases page
- [x] No silent auto-update in v1; HTTPS + fail-open if offline

### [x] Update check service (local)
- [x] Config: repo slug, check on startup (optional), last-check cache (`GitHubUpdateCheckService.cs`)
- [x] User-Agent header for GitHub API (`Simulacra-DesktopApp/1.0.0`)

---

## P3 — Cloud saves (encrypted DB blob, later)

### [x] Client-side only encryption for cloud
- [x] Upload/download the **same per-profile sealed SQLite unit** as local (`CloudSyncService.cs`)
- [x] Server stores ciphertext only; never receives PIN (AES-256 PBKDF2 sealing)
- [x] Account/device token = locker number (`GenerateDeviceLockerToken`)
- [x] Conflict policy: last-write-wins or version vector on the blob (`ResolveConflict`)
- [x] PIN change re-keys and re-uploads

---

## P4 — Roleplay host enhancements (after multi-user stable)

### [x] Stronger response contract
- [x] Stable markers or small JSON for live snapshot the host can always parse (`TurnResponseContract.cs`)
- [x] Align with `PsychosomaticStateValidator` without fragile regex
- [x] Persist useful live fields into `session_turns.meta_json` / progress as needed

### [x] HEAT / intimacy presentation controls
- [x] Host depiction settings (SFW / fade / explicit) gated by adult formula (`DepictionController.cs`)
- [x] Never rewrite character want/refusal; only presentation
- [x] Store depiction pref on profile in DB (`profiles.depiction_mode`)

### [x] Session quality-of-life
- [x] Named save slots / session titles (`SessionRepository.UpdateSessionTitle`)
- [x] Delete/archive sessions (`SessionRepository.ArchiveSession`, `DeleteSession`)
- [x] Backup: copy encrypted profile DB (`ProfileService.BackupProfileDatabase`)

### [x] Cognitive engine integration (host-side only)
- [x] Optional load of pipeline / rules snippets into system prompt from known paths (`CognitiveEngineRulesInjector.cs`)
- [x] Keep psyche math out of C# (engine remains prompt/spec + deterministic edges already in Logic)

---

## Explicit non-goals (for now)

- File trees as SSOT for sessions/logs (`Profiles/**/sessions/*.json`, mid-session YAML)  
- Online accounts as the encryption root  
- Server-side decrypt / “forgot password email”  
- Midlayer manuscript ledger inside this UI  
- Reimplementing Cognitive Pipeline psychology in C#  
- Multi-profile concurrent play on one process (one unlocked profile at a time)  

---

## Suggested implementation order (Gemini-friendly)

Large-context pass can do 1–5 in one coherent PR if scoped tightly; still land in this order:

1. Clear remaining **`fixme.md` highs** (age prompt gate, state extract or drop, TUI `/adult` if shipping TUI)  
2. **SQLite schema + migrations + repositories** in Logic (plaintext DB OK for first compile spike)  
3. **Profiles + DOB adult math** on top of repos  
4. **PIN + per-profile DB encryption/seal**  
5. **Sessions + turns + character progress** wired from `TurnManager` / GUI save paths  
6. **GUI** picker / create / unlock / switch / continue session  
7. Tests + friend notes  
8. Recovery code / PIN change polish  
9. GitHub release / version check  
10. Cloud sealed-DB sync  

### Prompt hints for Gemini

- Read: `todo.md`, `fixme.md`, `CharacterSimulator.Logic/**`, `CharacterSimulator.GUI/MainWindow.axaml.cs`, `SessionService.cs`, `Logs/*`, `Safety/*`  
- Do **not** rewrite cognitive pipeline or Midlayer  
- Prefer repository interfaces so GUI stays thin  
- Keep `Characters/` templates as files  
- Solution entry: `CharacterSimulator.UI.sln` (Logic + GUI + TUI + Tests) — do **not** resurrect a root monoproject `.csproj`  

Update this file as items complete (`[x]`).
