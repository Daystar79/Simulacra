using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic.Safety;

namespace CharacterSimulator.Logic;

/// <summary>
/// Desktop/host bridge: owns the active <see cref="TurnManager"/> loop, player commands,
/// and fan-out events for UI (dialogue feed, system log, waiting badge).
/// GUI and future midlayer both drive this instead of calling TurnManager directly.
/// </summary>
public sealed class SimulationHost
{
    private readonly TurnControlContext _control;
    private readonly object _gate = new();

    private Task? _runTask;
    private TurnManager? _turnManager;
    private Character? _charA;
    private Character? _charB;
    private string _stagedPrimaryFile = "";
    private string _sceneOverride = "";
    private string? _pendingInject;
    private volatile bool _waitingForLlm;
    private volatile bool _pauseAfterEachTurn;
    private volatile bool _sessionStartInFlight;

    public SimulationHost(TurnControlContext control)
    {
        _control = control ?? throw new ArgumentNullException(nameof(control));
    }

    public TurnControlContext Control => _control;
    public Character? CharacterA => _charA;
    public Character? CharacterB => _charB;
    public bool IsSessionRunning => _runTask != null && !_runTask.IsCompleted;
    public bool IsWaitingForLlm => _waitingForLlm;
    public string StagedPrimaryFile => _stagedPrimaryFile;

    /// <summary>Structured dialogue / system lines for the center feed.</summary>
    public event Action<DialogueLine>? OnDialogueLine;

    /// <summary>Raw system / agent diagnostic log lines.</summary>
    public event Action<string>? OnLog;

    /// <summary>Clear dialogue feed (/clear).</summary>
    public event Action? OnFeedClear;

    /// <summary>Waiting-for-LLM badge.</summary>
    public event Action<bool>? OnWaitingChanged;

    /// <summary>Character card telemetry refresh after a turn.</summary>
    public event Action? OnCharacterStateChanged;

    /// <summary>UI should open Simulation Setup (/setup).</summary>
    public event Action? OnRequestSetup;

    /// <summary>Mode badge text changed (Auto-Play / Player-Guided).</summary>
    public event Action<string>? OnModeChanged;

    /// <summary>Status bar one-liner.</summary>
    public event Action<string>? OnStatus;

    /// <summary>Stage character from the right-panel selector (overrides settings Char A for next session).</summary>
    public void SetStagedCharacter(string? cardFileName)
    {
        _stagedPrimaryFile = string.IsNullOrWhiteSpace(cardFileName) ? "" : cardFileName.Trim();
    }

    public void SetSceneOverride(string? sceneText)
    {
        _sceneOverride = sceneText?.Trim() ?? "";
        if (!string.IsNullOrEmpty(_sceneOverride))
            OnStatus?.Invoke($"Scene set: {_sceneOverride}");
    }

    public void Play()
    {
        lock (_gate)
        {
            if (IsSessionRunning)
            {
                if (_control.State == SimulationState.Paused || _control.State == SimulationState.Ready)
                {
                    _control.Resume();
                    PostSystem("▶ Resumed.");
                    OnStatus?.Invoke("Simulation resumed.");
                }
                else if (_control.State == SimulationState.Stopped)
                {
                    // Task still finishing; ignore
                }
                else
                {
                    OnStatus?.Invoke("Already running.");
                }
                return;
            }
        }

        _ = StartSessionAsync();
    }

    public void Pause()
    {
        _control.Pause();
        PostSystem("⏸ Paused.");
        OnStatus?.Invoke("Simulation paused.");
    }

    public void Step()
    {
        if (!IsSessionRunning)
        {
            // One-shot: start session; Player-Guided will pause after the first turn.
            _ = StartSessionAsync(stepOnce: true);
            return;
        }

        _control.Step();
        OnStatus?.Invoke("Stepping one turn…");
    }

    public void Stop()
    {
        if (!IsSessionRunning && _control.State != SimulationState.Running)
        {
            _control.Stop();
            SetWaiting(false);
            OnStatus?.Invoke("No active simulation.");
            return;
        }

        _control.Stop();
        SetWaiting(false);
        PostSystem("⏹ Stopped.");
        OnStatus?.Invoke("Simulation stopped.");
    }

    public void Reset()
    {
        Stop();
        lock (_gate)
        {
            _charA = null;
            _charB = null;
            _turnManager = null;
            _sceneOverride = "";
        }
        OnFeedClear?.Invoke();
        PostSystem("↺ Stage reset. Load a character and Play, or open Settings → Roleplaying.");
        OnStatus?.Invoke("Stage reset.");
        OnCharacterStateChanged?.Invoke();
    }

    /// <summary>
    /// Player chat line or slash command. Dialogue is injected into the next character turn.
    /// </summary>
    public void SubmitPlayerLine(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        string line = text.Trim();

        if (PlayerCommandService.IsCommand(line))
        {
            HandleCommand(PlayerCommandService.Parse(line));
            return;
        }

        // Player dialogue bubble
        OnDialogueLine?.Invoke(new DialogueLine
        {
            SpeakerName = "Player",
            TargetName = _charA?.Name ?? "Character",
            Dialogue = line,
            SpeakerColor = "#34D399",
            IsLeft = true,
            SpeakerEmotionEmoji = "💬",
            IsSystem = false
        });

        EnsureTurnManagerInject(line);

        if (!IsSessionRunning)
        {
            PostSystem("Starting session with your line as the opening cue…");
            _ = StartSessionAsync();
        }
        else if (_control.State == SimulationState.Paused || _control.State == SimulationState.Ready)
        {
            // Advance so InjectUserInput is consumed on the next agent turn.
            _control.Step();
        }
        // If already Running, input is queued for the next turn boundary.
    }

    public void SetRoleplayMode(string mode)
    {
        var settings = _control.CurrentSettings ?? new AppSettings();
        bool auto = mode.Equals("AutoPlay", StringComparison.OrdinalIgnoreCase)
                    || mode.Contains("Auto", StringComparison.OrdinalIgnoreCase);
        settings.RoleplayMode = auto ? "AutoPlay" : "PlayerGuided";
        _control.UpdateSettings(settings);
        string badge = auto ? "🤖 Auto-Play" : "🎮 Player-Guided";
        OnModeChanged?.Invoke(badge);
        PostSystem(auto
            ? "Mode: Auto-Play (turns advance on delay)."
            : "Mode: Player-Guided (pauses after each turn; Send or Step to continue).");
    }

    // ── commands ──────────────────────────────────────────────────────────

    private void HandleCommand(PlayerCommand cmd)
    {
        switch (cmd.Kind)
        {
            case PlayerCommandKind.Help:
                PostSystem(PlayerCommandService.GetHelpText());
                break;
            case PlayerCommandKind.Play:
                Play();
                break;
            case PlayerCommandKind.Pause:
                Pause();
                break;
            case PlayerCommandKind.Step:
                Step();
                break;
            case PlayerCommandKind.Stop:
                Stop();
                break;
            case PlayerCommandKind.Reset:
                Reset();
                break;
            case PlayerCommandKind.Clear:
                OnFeedClear?.Invoke();
                PostSystem("Dialogue feed cleared.");
                break;
            case PlayerCommandKind.Setup:
                OnRequestSetup?.Invoke();
                PostSystem("Opening simulation setup…");
                break;
            case PlayerCommandKind.AutoPlay:
                SetRoleplayMode("AutoPlay");
                break;
            case PlayerCommandKind.PlayerGuided:
                SetRoleplayMode("PlayerGuided");
                break;
            case PlayerCommandKind.Status:
            case PlayerCommandKind.State:
                PostSystem(BuildStatusReport());
                break;
            case PlayerCommandKind.Scene:
                if (cmd.Args.Length == 0)
                    PostSystem("Usage: /scene <place or detail>");
                else
                {
                    SetSceneOverride(cmd.Args[0]);
                    PostSystem($"Scene place set to: {cmd.Args[0]} (applies on next session start).");
                }
                break;
            case PlayerCommandKind.Genre:
                if (cmd.Args.Length == 0)
                    PostSystem("Usage: /genre <genre id or name>");
                else
                {
                    var g = SceneGenreCatalog.GetById(cmd.Args[0]);
                    var s = _control.CurrentSettings ?? new AppSettings();
                    s.SelectedGenre = g.Id;
                    _control.UpdateSettings(s);
                    PostSystem($"Genre set to: {g.DisplayName}");
                }
                break;
            case PlayerCommandKind.Adult:
                HandleAdult(cmd.Args);
                break;
            case PlayerCommandKind.Save:
            case PlayerCommandKind.Load:
                PostSystem($"/{cmd.RawName} is not wired in the host yet — use Settings → Saved Sessions.");
                break;
            case PlayerCommandKind.Unknown:
                PostSystem($"Unknown command. Type /help for the list.\n({cmd.RawText})");
                break;
            default:
                PostSystem($"Command /{cmd.RawName} is not available here.");
                break;
        }
    }

    private void HandleAdult(string[] args)
    {
        if (args.Length == 0)
        {
            PostSystem($"Adult attestation: {(AdultAuth.IsUserAdultAttested ? "ON" : "OFF")}. Use /adult on|off");
            return;
        }

        string v = args[0].Trim().ToLowerInvariant();
        if (v is "on" or "true" or "1" or "yes")
        {
            AdultAuth.SetUserAdultAttested(true);
            PostSystem("Adult attestation ON (still requires character age eligibility).");
        }
        else if (v is "off" or "false" or "0" or "no")
        {
            AdultAuth.SetUserAdultAttested(false);
            PostSystem("Adult attestation OFF.");
        }
        else
            PostSystem("Usage: /adult on|off");
    }

    private string BuildStatusReport()
    {
        var s = _control.CurrentSettings ?? new AppSettings();
        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"State: {_control.State} | Session: {(IsSessionRunning ? "active" : "idle")} | WaitingLLM: {_waitingForLlm}");
        sb.AppendLine($"Mode: {s.RoleplayMode} | Delay: {_control.DelayMs}ms | MaxTurns: {s.MaxTurns}");
        sb.AppendLine($"LLM: {s.RoleplayLlmProvider} ({s.RoleplayModelIdentifier})");
        sb.AppendLine($"Genre: {s.SelectedGenre} | Scene: {(!string.IsNullOrEmpty(_sceneOverride) ? _sceneOverride : s.ScenePrompt)}");
        sb.AppendLine($"Staged card: {(string.IsNullOrEmpty(_stagedPrimaryFile) ? "(none)" : _stagedPrimaryFile)}");
        if (_charA != null)
            sb.AppendLine(PlayerCommandService.BuildCharacterStateReport(_charA));
        if (_charB != null)
            sb.AppendLine(PlayerCommandService.BuildCharacterStateReport(_charB));
        return sb.ToString().TrimEnd();
    }

    // ── session ───────────────────────────────────────────────────────────

    private void EnsureTurnManagerInject(string line)
    {
        lock (_gate)
        {
            if (_turnManager != null)
                _turnManager.InjectUserInput("Player", line);
            else
                _pendingInject = line;
        }
    }

    private async Task StartSessionAsync(bool stepOnce = false)
    {
        lock (_gate)
        {
            if (_sessionStartInFlight || (_runTask != null && !_runTask.IsCompleted))
            {
                OnStatus?.Invoke("Session already active.");
                return;
            }
            _sessionStartInFlight = true;
        }

        Character charA;
        Character? charB;
        TurnManager manager;
        string scene;
        int maxTurns;

        try
        {
            var settings = _control.CurrentSettings ?? AppConfigService.LoadSettings();
            string charDir = CharacterCatalog.ResolveCharactersDirectory();

            string fileA = !string.IsNullOrWhiteSpace(_stagedPrimaryFile)
                ? _stagedPrimaryFile
                : settings.SelectedCharA;

            if (string.IsNullOrWhiteSpace(fileA) || IsNone(fileA))
            {
                PostSystem("No character loaded. Select a card on the right panel, or configure Roleplaying Setup.");
                OnStatus?.Invoke("Cannot start — no character.");
                _sessionStartInFlight = false;
                return;
            }

            string pathA = Path.Combine(charDir, fileA);
            if (!File.Exists(pathA))
            {
                PostSystem($"Character file not found: {fileA}");
                OnStatus?.Invoke("Cannot start — missing card file.");
                _sessionStartInFlight = false;
                return;
            }

            charA = CharacterLoader.Load(pathA);

            charB = null;
            string fileB = settings.SelectedCharB ?? "";
            if (!string.IsNullOrWhiteSpace(fileB) && !IsNone(fileB))
            {
                string pathB = Path.Combine(charDir, fileB);
                if (File.Exists(pathB))
                    charB = CharacterLoader.Load(pathB);
                else
                    OnLog?.Invoke($"[warn] Character B file missing ({fileB}); running solo.");
            }

            string providerA = PreferProvider(settings.RoleplayLlmProvider, settings.SelectedLlmA);
            string providerB = PreferProvider(settings.RoleplayLlmProvider, settings.SelectedLlmB);
            var clientA = LlmDiscoveryService.CreateClient(providerA, settings.RoleplayModelIdentifier);
            ILLMClient? clientB = charB != null ? LlmDiscoveryService.CreateClient(providerB, settings.RoleplayModelIdentifier) : null;

            string place = !string.IsNullOrWhiteSpace(_sceneOverride)
                ? _sceneOverride
                : settings.ScenePrompt;
            scene = SceneGenreCatalog.ComposeSceneContext(settings.SelectedGenre, place);
            maxTurns = settings.MaxTurns > 0 ? settings.MaxTurns : 10;
            if (maxTurns < 4) maxTurns = 4;
            if (maxTurns > 200) maxTurns = 200;

            bool playerGuided = !string.Equals(settings.RoleplayMode, "AutoPlay", StringComparison.OrdinalIgnoreCase);
            _pauseAfterEachTurn = playerGuided || stepOnce;

            string logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Output");
            Directory.CreateDirectory(logDir);
            string logPath = Path.Combine(logDir, $"conversation_gui_{DateTime.Now:yyyy-MM-dd-HH-mm-ss}.log");
            var logger = new Logger(logPath);
            var sceneManager = new SceneManager();
            manager = new TurnManager(clientA, clientB, sceneManager, logger);

            manager.OnTurnStep += OnManagerTurnStep;
            manager.OnAgentOutputLogged += msg => OnLog?.Invoke(msg.TrimEnd());
            manager.OnAgentTurnStarted += (name, provider) =>
            {
                SetWaiting(true);
                OnLog?.Invoke($"[⏳ {name}] → {provider}");
                OnStatus?.Invoke($"Waiting for {name} ({provider})…");
            };
            manager.OnSceneStarted += s =>
            {
                OnLog?.Invoke($"[scene] {s}");
                PostSystem("🎬 Scene started.");
            };
            manager.OnGoalEvaluated += g =>
            {
                string mark = g.IsSuccess ? "★ GOAL SUCCESS" : "✖ GOAL FAILED";
                PostSystem($"{mark}: {g.CharacterName} — {g.GoalType} vs {g.TargetName}");
            };

            string? inject;
            lock (_gate)
            {
                _charA = charA;
                _charB = charB;
                _turnManager = manager;
                inject = _pendingInject;
                _pendingInject = null;
            }

            if (!string.IsNullOrEmpty(inject))
                manager.InjectUserInput("Player", inject);

            string vs = charB?.Name ?? "Player (solo)";
            PostSystem($"▶ Starting: {charA.Name} vs {vs} | LLM: {providerA}" +
                       (charB != null ? $" / {providerB}" : "") +
                       $" | Mode: {(playerGuided ? "Player-Guided" : "Auto-Play")} | Turns: {maxTurns}");
            OnLog?.Invoke($"Log: {logPath}");
            OnStatus?.Invoke($"Running: {charA.Name}");
            OnCharacterStateChanged?.Invoke();
        }
        catch (Exception ex)
        {
            PostSystem($"Failed to start session: {ex.Message}");
            OnStatus?.Invoke("Start failed.");
            OnLog?.Invoke(ex.ToString());
            _sessionStartInFlight = false;
            return;
        }

        var runTask = Task.Run(async () =>
        {
            try
            {
                await manager.RunConversationAsync(charA, charB, scene, maxTurns, _control)
                    .ConfigureAwait(false);

                if (_control.CancellationToken.IsCancellationRequested)
                    PostSystem("Session ended (stopped).");
                else
                    PostSystem($"Simulation complete ({maxTurns} turn cap). Play or Send to start again.");
            }
            catch (OperationCanceledException)
            {
                PostSystem("Session cancelled.");
            }
            catch (Exception ex)
            {
                PostSystem($"Session error: {ex.Message}");
                OnLog?.Invoke(ex.ToString());
            }
            finally
            {
                SetWaiting(false);
                _pauseAfterEachTurn = false;
                try
                {
                    if (_control.State == SimulationState.Running || _control.State == SimulationState.Paused)
                        _control.Stop();
                }
                catch { /* ignore */ }

                lock (_gate)
                {
                    if (_turnManager == manager)
                        _turnManager = null;
                    _runTask = null;
                    _sessionStartInFlight = false;
                }

                OnStatus?.Invoke("Session idle.");
                OnCharacterStateChanged?.Invoke();
            }
        });

        lock (_gate)
        {
            _runTask = runTask;
        }

        await runTask.ConfigureAwait(false);
    }

    private void OnManagerTurnStep(TurnStepEventArgs e)
    {
        SetWaiting(false);

        bool isSystem = e.SpeakerName.Contains("System", StringComparison.OrdinalIgnoreCase)
                        || e.SpeakerEmotionEmoji == "⚠️";

        string color = isSystem
            ? "#94A3B8"
            : (_charA != null && e.SpeakerName.Equals(_charA.Name, StringComparison.OrdinalIgnoreCase))
                ? "#38BDF8"
                : "#C084FC";

        bool isLeft = isSystem
            || (_charA != null && e.SpeakerName.Equals(_charA.Name, StringComparison.OrdinalIgnoreCase));

        string somatic = e.SomaticZones is { Count: > 0 }
            ? string.Join(", ", e.SomaticZones)
            : "";

        string bond = e.BondDelta != 0
            ? (e.BondDelta > 0 ? $"+{e.BondDelta}" : e.BondDelta.ToString()) + $" (now {e.CurrentBond})"
            : "";

        OnDialogueLine?.Invoke(new DialogueLine
        {
            SpeakerName = e.SpeakerName,
            TargetName = e.TargetName,
            Dialogue = e.Dialogue,
            SomaticText = somatic,
            BondDeltaText = bond,
            SpeakerEmotionEmoji = string.IsNullOrEmpty(e.SpeakerEmotionEmoji) ? "💬" : e.SpeakerEmotionEmoji,
            SpeakerColor = color,
            IsLeft = isLeft,
            IsSystem = isSystem
        });

        OnCharacterStateChanged?.Invoke();
        OnStatus?.Invoke($"T{e.TurnIndex} {e.SpeakerName}");

        // Player-Guided / single-step: park between speaker turns so Send or Step continues.
        if (_pauseAfterEachTurn)
        {
            try { _control.Pause(); }
            catch { /* ignore */ }
        }
    }

    private void PostSystem(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        OnDialogueLine?.Invoke(new DialogueLine
        {
            SpeakerName = "System",
            TargetName = "",
            Dialogue = text,
            IsSystem = true,
            SpeakerColor = "#94A3B8",
            SpeakerEmotionEmoji = "⚙️"
        });
        OnLog?.Invoke(text);
    }

    private void SetWaiting(bool waiting)
    {
        if (_waitingForLlm == waiting) return;
        _waitingForLlm = waiting;
        if (waiting)
            Services.BusyTaskService.BeginTask("llm_roleplay", "Waiting for LLM roleplay response...");
        else
            Services.BusyTaskService.EndTask("llm_roleplay");

        OnWaitingChanged?.Invoke(waiting);
    }

    private static bool IsNone(string fileName) =>
        string.IsNullOrWhiteSpace(fileName)
        || fileName.StartsWith("None", StringComparison.OrdinalIgnoreCase)
        || fileName.Contains("No Character", StringComparison.OrdinalIgnoreCase)
        || fileName.Contains("Not Selected", StringComparison.OrdinalIgnoreCase)
        || fileName.StartsWith('(');

    private static string PreferProvider(string roleplayProvider, string selectedSlot)
    {
        if (!string.IsNullOrWhiteSpace(selectedSlot)
            && !selectedSlot.Contains("Mock", StringComparison.OrdinalIgnoreCase)
            && !selectedSlot.Equals("Mock", StringComparison.OrdinalIgnoreCase))
        {
            return selectedSlot;
        }

        if (string.IsNullOrWhiteSpace(roleplayProvider))
            return "Mock / Simulation";

        return roleplayProvider;
    }
}

/// <summary>UI-agnostic dialogue feed row from <see cref="SimulationHost"/>.</summary>
public sealed class DialogueLine
{
    public string SpeakerName { get; set; } = "";
    public string TargetName { get; set; } = "";
    public string Dialogue { get; set; } = "";
    public string SomaticText { get; set; } = "";
    public string BondDeltaText { get; set; } = "";
    public string SpeakerEmotionEmoji { get; set; } = "💬";
    public string SpeakerColor { get; set; } = "#38BDF8";
    public bool IsLeft { get; set; } = true;
    public bool IsSystem { get; set; }
}
