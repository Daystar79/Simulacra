### [x] Dolphin 3.0 1B Default Model & Model Catalog Selection
- **Default Model:** Updated default local SLM model to **Dolphin 3.0 (Llama 3.2 1B)** (`Dolphin3.0-Llama3.2-1B-Q4_K_M.gguf`).
- **Model Downloader Catalog:** Added a preset model catalog in `SlmModelDownloaderService.cs` allowing users to pick and download from a dropdown:
  - `Dolphin 3.0 (Llama 3.2 1B)` (~800 MB, Uncensored, Default)
  - `Dolphin 3.0 (Llama 3.2 3B)` (~2.0 GB, Uncensored 3B)
  - `Qwen 2.5 (3B Instruct)` (~1.9 GB)
  - `Llama 3.2 (3B Instruct)` (~2.0 GB)
  - `SmolLM2 (1.7B Instruct)` (~1.0 GB)
- **UI Integration:** Integrated model preset selector dropdown into `SimulationSetupModal.razor` under Roleplaying LLM settings.

### [x] Local Model & Embedded SLM Prompt Builder Disambiguation
- **Problem:** Embedded SLMs (LLamaSharp, llama.cpp GGUFs, Ollama local runtimes like Llama-3 1B/3B, Qwen-2.5 0.5B-7B) require different context management, stop sequences, and prompt formatting compared to large cloud Web APIs or CLI agent runners (Agy, Claude CLI, Mistral Vibe, Grok CLI).
- **Implementation:**
  - Added `LocalSlmPromptBuilder.cs` in `CharacterSimulator.Logic`.
  - Added model format presets: `ChatMl`, `Llama3`, `Alpaca`, and `Plaintext`.
  - Prioritized safety mandates (`AgeGate`) at the very top of system context to guarantee high attention-head weighting in small context windows.
  - Formatted identity blocks densely, stripping redundant instructional prose to optimize 2K/4K KV-cache usage.
  - Reduced default turn history context depth for local models (`DefaultMaxSlmTranscriptLines = 6`) to prevent context overflow and prompt echo.
  - Updated `LlamaSharpLlmClient` and `OllamaLlmClient` to consume `LocalSlmPromptBuilder`.
  - Created `LocalSlmPromptBuilderTests.cs` covering safety placement, compact identity blocks, ChatML, and Llama 3 formatting.

### [x] Logic & Performance Pass
- **Turn & Context Optimization:** Standardized prompt dispatching so heavy full-context prompts go to cloud/agent clients while lightweight ChatML/Llama3 templates go to embedded SLMs.
- **Sanitizer Hygiene:** Verified leak marker filtering in `LlmResponseSanitizer` to handle local model output quirks cleanly without runaway completions.
### [x] Dolphin 3.0 Runtime & Format Auto-Detection
- **CharacterRuntime_Dolphin.md:** Created optimized runtime in `/mnt/Books/Source/CharacterSimulator/Simulator/CharacterRuntime_Dolphin.md`.
- **C# Auto-Switcher:** Added `LocalSlmFormat.Dolphin` and `DetectFormat` in `LocalSlmPromptBuilder.cs` auto-routing Dolphin models.
- **Model Downloader & Deletion Manager:** Fixed Hugging Face GGUF URLs, added desktop User-Agent header, and installed model deletion UI list.
- **Token Offloading:** C# deterministic bond/goal/somatic evaluation reduced prompt context tokens by ~500+ and completion tokens by ~80 per turn.
- **Formatting Hygiene:** Anti-parroting directives, `[Player]:` leak clamping, bracket unwrapping, and CSS narration prose styling.
- **Verification:** All 80 unit tests in `CharacterSimulator.Logic.Tests` passing cleanly.

---

## Active Roadmap & Upcoming Tasks

### P1 — Friend-test & Local SLM Polish
- [ ] **PIN Recovery & Re-keying:** Add recovery code generation during profile setup and atomic SQLite re-keying on PIN change.
- [ ] **Unsaved Session Dirty Confirmation:** Prompt user before switching profiles if a turn or session has unsaved modifications.
- [ ] **Session Export Tools:** Export SQLite session transcripts directly to `.md` or JSON snapshots for debugging.

### P2 — Packaging & Release Distribution
- [ ] **GitHub Releases Integration:** Package Photino + Blazor desktop app artifacts for friend testing.
- [ ] **Local Version Check:** Non-blocking check against GitHub API for available client updates.

### P3 — Cloud Sealed SQLite Sync
- [ ] **Client-side Encrypted Sync:** Upload/download sealed SQLite profile blobs (ciphertext only on server; key derived from local PIN).
