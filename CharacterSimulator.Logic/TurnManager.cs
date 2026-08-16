using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic;

public class TurnManager
{
    private readonly ILLMClient _clientA;
    private readonly ILLMClient? _clientB;
    private readonly SceneManager _sceneManager;
    private readonly Logger _logger;
    private string? _pendingUserInput;
    private string _pendingUserRole = "Player";
    private bool _pendingAmbient;
    private string _pendingAmbientCue = "";
    private readonly object _inputLock = new object();

    public event Action<TurnStepEventArgs>? OnTurnStep;
    public event Action<GoalEvaluationEventArgs>? OnGoalEvaluated;
    public event Action<string>? OnSceneStarted;
    public event Action<string>? OnAgentOutputLogged;
    public event Action<string, string>? OnAgentTurnStarted;

    public TurnManager(ILLMClient clientA, ILLMClient? clientB, SceneManager sceneManager, Logger logger)
    {
        _clientA = clientA ?? throw new ArgumentNullException(nameof(clientA));
        _clientB = clientB;
        _sceneManager = sceneManager ?? throw new ArgumentNullException(nameof(sceneManager));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public void InjectUserInput(string userRole, string text)
    {
        lock (_inputLock)
        {
            _pendingUserRole = userRole;
            _pendingUserInput = text;
            _pendingAmbient = false;
            _pendingAmbientCue = "";
        }
    }

    /// <summary>
    /// Queue a host-side idle beat. Not player speech. Ignored if a player line is already waiting.
    /// </summary>
    public void InjectAmbientBeat(string? cue = null)
    {
        lock (_inputLock)
        {
            if (!string.IsNullOrEmpty(_pendingUserInput))
                return;
            _pendingAmbient = true;
            _pendingAmbientCue = cue?.Trim() ?? "";
        }
    }

    public async Task RunConversationAsync(Character charA, Character? charB, string scene, int maxTurns, TurnControlContext controlContext)
    {
        if (charA == null) throw new ArgumentNullException(nameof(charA));
        if (scene == null) throw new ArgumentNullException(nameof(scene));
        if (controlContext == null) throw new ArgumentNullException(nameof(controlContext));
        
        _sceneManager.SetScene(scene);
        _logger.LogScene(scene);
        OnSceneStarted?.Invoke(scene);

        bool isSoloMode = charB == null || string.Equals(charB.Name, "None", StringComparison.OrdinalIgnoreCase);
        string targetBName = isSoloMode ? "Player" : (charB?.Name ?? "Unknown");

        charA.ResistanceCount[targetBName] = 0;
        if (!isSoloMode && charB != null) charB.ResistanceCount[charA.Name] = 0;

        // Host-owned rolling transcript (stateless SLM/LLM has no KV session).
        var transcript = new List<string>();
        string lastInputForA = "";
        string lastInputForB = "";
        controlContext.Start();

        int loopMaxTurns = (isSoloMode || maxTurns <= 0) ? int.MaxValue : maxTurns;

        try
        {
            for (int turn = 0; turn < loopMaxTurns; turn++)
            {
                if (controlContext.CancellationToken.IsCancellationRequested) break;

                // Determine input for Client A
                string inputA = lastInputForA;
                string? pendingStimulusLine = null;
                ConsumePendingStimulus(ref inputA, ref pendingStimulusLine);

                string historyForA = PromptBuilder.FormatTranscript(transcript);

                // Client A Turn
                Goal? activeGoalA = GetActiveGoal(charA, targetBName);
                string goalContextA = PromptBuilder.FormatWinningDrive(activeGoalA);

                string providerA = (_clientA as CliLlmClient)?.Name ?? "LLM";
                OnAgentTurnStarted?.Invoke(charA.Name, providerA);
                OnAgentOutputLogged?.Invoke($"[⏳ {charA.Name}] Dispatching prompt to {providerA}...\n");

                string promptA;
                try
                {
                    promptA = await _clientA.SendPromptAsync(
                        charA, inputA, scene, goalContextA, controlContext.CancellationToken, historyForA).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (controlContext.CancellationToken.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    promptA = $"[CLI ERROR] Exception in {providerA}: {ex.Message}";
                }
                if (controlContext.CancellationToken.IsCancellationRequested) break;

                // Defense in depth if a provider skips client-side clamp
                if (!IsCliSystemError(promptA))
                    promptA = LlmResponseSanitizer.ClampToFirstReply(promptA, inputA, historyForA);

                OnAgentOutputLogged?.Invoke($"[{charA.Name} RAW LLM STDOUT]\n{promptA}\n");

                if (IsCliSystemError(promptA))
                {
                    OnAgentOutputLogged?.Invoke($"[SYSTEM] Provider error for {charA.Name} — not treated as in-character dialogue.\n");
                    OnTurnStep?.Invoke(new TurnStepEventArgs
                    {
                        TurnIndex = turn + 1,
                        SpeakerName = "⚙️ System",
                        TargetName = charA.Name,
                        Dialogue = promptA.Trim(),
                        SomaticZones = new List<string>(),
                        BondDelta = 0,
                        CurrentBond = charA.Bond,
                        SpeakerEmotion = "Error",
                        SpeakerEmotionEmoji = "⚠️",
                        ActiveGoalType = null,
                        GoalStatus = "CLI Error",
                        SceneContext = scene,
                        RawAgentOutput = promptA,
                        ImagePrompt = null
                    });
                    await controlContext.WaitTurnAsync();
                    if (controlContext.CancellationToken.IsCancellationRequested) break;
                    continue; // do not advance character state or feed peer with error text
                }

                var (dialogueA, somaticA, bondDeltaA, goalStatusA, imagePromptA, liveStateA) = ParseResponse(promptA, charA);

                if (liveStateA != null)
                {
                    bool applied = State.PsychosomaticStateValidator.ApplyToCharacter(liveStateA, charA);
                    if (!applied)
                    {
                        AppLogger.Warning("[TurnManager] Failed to apply live state for " + charA.Name);
                    }
                }

                if (somaticA.Count > 0) charA.SomaticZones = somaticA;
                charA.Bond += bondDeltaA;
                charA.UpdateEmotionFromSomatic(somaticA.Count > 0 ? somaticA : charA.SomaticZones, dialogueA);
                UpdateBiasState(charA, bondDeltaA, goalStatusA, scene);

                _logger.LogTurn(charA.Name, dialogueA, somaticA.Count > 0 ? somaticA : charA.SomaticZones, charA.Bond, activeGoalA?.Type, goalStatusA);

                // Append stimulus (if any) then A's line to host transcript
                if (!string.IsNullOrWhiteSpace(pendingStimulusLine))
                    AppendTranscript(transcript, pendingStimulusLine);
                else if (!string.IsNullOrWhiteSpace(inputA) && transcript.Count == 0)
                    AppendTranscript(transcript, TrimForTranscript(inputA));
                AppendTranscript(transcript, FormatSpeakerLine(charA.Name, dialogueA));

                OnTurnStep?.Invoke(new TurnStepEventArgs
                {
                    TurnIndex = turn + 1,
                    SpeakerName = charA.Name,
                    TargetName = targetBName,
                    Dialogue = dialogueA,
                    SomaticZones = somaticA,
                    BondDelta = bondDeltaA,
                    CurrentBond = charA.Bond,
                    SpeakerEmotion = charA.Emotion,
                    SpeakerEmotionEmoji = charA.EmotionEmoji,
                    ActiveGoalType = activeGoalA?.Type,
                    GoalStatus = goalStatusA,
                    SceneContext = scene,
                    RawAgentOutput = promptA,
                    ImagePrompt = imagePromptA ?? PromptBuilder.BuildDefaultImagePrompt(charA, scene)
                });

                if (activeGoalA != null && !isSoloMode && charB != null)
                {
                    if (charA.EvaluateSuccess(activeGoalA, charB))
                    {
                        _logger.LogGoalSuccess(charA.Name, activeGoalA.Type, charB.Name);
                        OnGoalEvaluated?.Invoke(new GoalEvaluationEventArgs
                        {
                            CharacterName = charA.Name,
                            GoalType = activeGoalA.Type,
                            TargetName = charB.Name,
                            IsSuccess = true
                        });
                        charA.Goals.Remove(activeGoalA);
                    }
                    else if (charA.EvaluateFailure(activeGoalA, charB))
                    {
                        _logger.LogGoalFailure(charA.Name, activeGoalA.Type, charB.Name);
                        OnGoalEvaluated?.Invoke(new GoalEvaluationEventArgs
                        {
                            CharacterName = charA.Name,
                            GoalType = activeGoalA.Type,
                            TargetName = charB.Name,
                            IsSuccess = false
                        });
                        activeGoalA.CooldownRemaining = activeGoalA.Cooldown;
                        activeGoalA.Attempts++;
                    }
                }

                lastInputForB = dialogueA;
                // Solo: next auto-turn uses empty stimulus + full transcript (continue, don't re-open scene)
                lastInputForA = "";

                await controlContext.WaitTurnAsync();
                if (controlContext.CancellationToken.IsCancellationRequested) break;

                // If Solo Mode, skip Client B's automatic turn
                if (isSoloMode || charB == null || _clientB == null)
                {
                    foreach (var goal in charA.Goals) if (goal.CooldownRemaining > 0) goal.CooldownRemaining--;
                    continue;
                }

                // Determine input for Client B
                string inputB = lastInputForB;
                string? pendingStimulusLineB = null;
                ConsumePendingStimulus(ref inputB, ref pendingStimulusLineB);

                // B already sees A's line in transcript; pass empty stimulus when no player/ambient inject
                // so the model is not told the same line twice.
                if (pendingStimulusLineB == null && !PromptBuilder.TryReadAmbientStimulus(inputB, out _))
                    inputB = "";

                string historyForB = PromptBuilder.FormatTranscript(transcript);

                // Client B Turn
                Goal? activeGoalB = GetActiveGoal(charB, charA.Name);
                string goalContextB = PromptBuilder.FormatWinningDrive(activeGoalB);

                string providerB = (_clientB as CliLlmClient)?.Name ?? "LLM";
                OnAgentTurnStarted?.Invoke(charB.Name, providerB);
                OnAgentOutputLogged?.Invoke($"[⏳ {charB.Name}] Dispatching prompt to {providerB}...\n");

                string promptB;
                try
                {
                    promptB = await _clientB.SendPromptAsync(
                        charB, inputB, scene, goalContextB, controlContext.CancellationToken, historyForB).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (controlContext.CancellationToken.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    promptB = $"[CLI ERROR] Exception in {providerB}: {ex.Message}";
                }
                if (controlContext.CancellationToken.IsCancellationRequested) break;

                if (!IsCliSystemError(promptB))
                    promptB = LlmResponseSanitizer.ClampToFirstReply(promptB, inputB, historyForB);

                OnAgentOutputLogged?.Invoke($"[{charB.Name} RAW LLM STDOUT]\n{promptB}\n");

                if (IsCliSystemError(promptB))
                {
                    OnAgentOutputLogged?.Invoke($"[SYSTEM] Provider error for {charB.Name} — not treated as in-character dialogue.\n");
                    OnTurnStep?.Invoke(new TurnStepEventArgs
                    {
                        TurnIndex = turn + 1,
                        SpeakerName = "⚙️ System",
                        TargetName = charB.Name,
                        Dialogue = promptB.Trim(),
                        SomaticZones = new List<string>(),
                        BondDelta = 0,
                        CurrentBond = charB.Bond,
                        SpeakerEmotion = "Error",
                        SpeakerEmotionEmoji = "⚠️",
                        ActiveGoalType = null,
                        GoalStatus = "CLI Error",
                        SceneContext = scene,
                        RawAgentOutput = promptB,
                        ImagePrompt = null
                    });
                    await controlContext.WaitTurnAsync();
                    if (controlContext.CancellationToken.IsCancellationRequested) break;
                    continue;
                }

                var (dialogueB, somaticB, bondDeltaB, goalStatusB, imagePromptB, liveStateB) = ParseResponse(promptB, charB);

                if (liveStateB != null)
                {
                    bool applied = State.PsychosomaticStateValidator.ApplyToCharacter(liveStateB, charB);
                    if (!applied)
                    {
                        AppLogger.Warning("[TurnManager] Failed to apply live state for " + charB.Name);
                    }
                }

                if (somaticB.Count > 0) charB.SomaticZones = somaticB;
                charB.Bond += bondDeltaB;
                charB.UpdateEmotionFromSomatic(somaticB.Count > 0 ? somaticB : charB.SomaticZones, dialogueB);
                UpdateBiasState(charB, bondDeltaB, goalStatusB, scene);

                _logger.LogTurn(charB.Name, dialogueB, somaticB.Count > 0 ? somaticB : charB.SomaticZones, charB.Bond, activeGoalB?.Type, goalStatusB);

                if (!string.IsNullOrWhiteSpace(pendingStimulusLineB))
                    AppendTranscript(transcript, pendingStimulusLineB);
                AppendTranscript(transcript, FormatSpeakerLine(charB.Name, dialogueB));

                OnTurnStep?.Invoke(new TurnStepEventArgs
                {
                    TurnIndex = turn + 1,
                    SpeakerName = charB.Name,
                    TargetName = charA.Name,
                    Dialogue = dialogueB,
                    SomaticZones = somaticB,
                    BondDelta = bondDeltaB,
                    CurrentBond = charB.Bond,
                    SpeakerEmotion = charB.Emotion,
                    SpeakerEmotionEmoji = charB.EmotionEmoji,
                    ActiveGoalType = activeGoalB?.Type,
                    GoalStatus = goalStatusB,
                    SceneContext = scene,
                    RawAgentOutput = promptB,
                    ImagePrompt = imagePromptB ?? PromptBuilder.BuildDefaultImagePrompt(charB, scene)
                });

                if (activeGoalB != null)
                {
                    if (charB.EvaluateSuccess(activeGoalB, charA))
                    {
                        _logger.LogGoalSuccess(charB.Name, activeGoalB.Type, charA.Name);
                        OnGoalEvaluated?.Invoke(new GoalEvaluationEventArgs
                        {
                            CharacterName = charB.Name,
                            GoalType = activeGoalB.Type,
                            TargetName = charA.Name,
                            IsSuccess = true
                        });
                        charB.Goals.Remove(activeGoalB);
                    }
                    else if (charB.EvaluateFailure(activeGoalB, charA))
                    {
                        _logger.LogGoalFailure(charB.Name, activeGoalB.Type, charA.Name);
                        OnGoalEvaluated?.Invoke(new GoalEvaluationEventArgs
                        {
                            CharacterName = charB.Name,
                            GoalType = activeGoalB.Type,
                            TargetName = charA.Name,
                            IsSuccess = false
                        });
                        activeGoalB.CooldownRemaining = activeGoalB.Cooldown;
                        activeGoalB.Attempts++;
                    }
                }

                foreach (var goal in charA.Goals) if (goal.CooldownRemaining > 0) goal.CooldownRemaining--;
                if (charB != null) foreach (var goal in charB.Goals) if (goal.CooldownRemaining > 0) goal.CooldownRemaining--;

                // Next A turn: stimulus empty; B's line is already in transcript
                lastInputForA = "";
                lastInputForB = dialogueB;

                await controlContext.WaitTurnAsync();
            }
        }
        finally
        {
            // Auto-commit session state on scene break or close
            Logs.CommitService.CommitSession(charA, charB, scene);
        }
    }

    private void ConsumePendingStimulus(ref string input, ref string? pendingStimulusLine)
    {
        string pendingUserRoleCopy;
        string pendingUserInputCopy;
        bool pendingAmbient;
        string pendingAmbientCue;
        lock (_inputLock)
        {
            pendingUserInputCopy = _pendingUserInput ?? "";
            pendingUserRoleCopy = _pendingUserRole;
            pendingAmbient = _pendingAmbient;
            pendingAmbientCue = _pendingAmbientCue;
            if (!string.IsNullOrEmpty(pendingUserInputCopy))
            {
                _pendingUserInput = null;
                _pendingAmbient = false;
                _pendingAmbientCue = "";
            }
            else if (pendingAmbient)
            {
                _pendingAmbient = false;
                _pendingAmbientCue = "";
            }
        }

        if (!string.IsNullOrEmpty(pendingUserInputCopy))
        {
            pendingStimulusLine = $"{pendingUserRoleCopy}: \"{pendingUserInputCopy}\"";
            input = $"[{pendingUserRoleCopy}]: \"{pendingUserInputCopy}\"";
        }
        else if (pendingAmbient)
        {
            pendingStimulusLine = null;
            input = PromptBuilder.FormatAmbientStimulus(pendingAmbientCue);
        }
    }

    private const int MaxTranscriptLineLength = 2000;
    private const int TranscriptHardCap = 40;

    private static void AppendTranscript(List<string> transcript, string line)
    {
        if (string.IsNullOrWhiteSpace(line)) return;
        
        // Truncate overly long lines to prevent memory bloat
        string trimmedLine = line.Trim();
        if (trimmedLine.Length > MaxTranscriptLineLength)
            trimmedLine = trimmedLine.Substring(0, MaxTranscriptLineLength) + "…";
        
        transcript.Add(trimmedLine);
        
        // Hard cap so long scenes do not bloat indefinitely (FormatTranscript also windows)
        if (transcript.Count > TranscriptHardCap)
            transcript.RemoveRange(0, transcript.Count - TranscriptHardCap);
    }

    private static string FormatSpeakerLine(string speaker, string dialogue)
    {
        string body = TrimForTranscript(dialogue);
        if (string.IsNullOrWhiteSpace(body))
            return $"{speaker}: (no audible line)";
        // Keep transcript compact for context budget
        if (body.Length > 280)
            body = body[..277].TrimEnd() + "...";
        return $"{speaker}: {body}";
    }

    private static string TrimForTranscript(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return "";
        return Regex.Replace(text.Trim(), @"\s+", " ");
    }

    private static int InferBondDeltaFromDialogue(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return 0;
        string lower = text.ToLowerInvariant();
        if (lower.Contains("smile") || lower.Contains("thank") || lower.Contains("nod") || lower.Contains("agree") || lower.Contains("warm"))
            return 1;
        if (lower.Contains("glare") || lower.Contains("shout") || lower.Contains("scowl") || lower.Contains("reject") || lower.Contains("snap"))
            return -1;
        return 0;
    }

    /// <summary>
    /// Synchronous version for backward compatibility. Note: This blocks the calling thread.
    /// Consider using RunConversationAsync for UI applications to avoid thread pool starvation.
    /// </summary>
    public void RunConversation(Character charA, Character? charB, string scene, int maxTurns)
    {
        var dummyContext = new TurnControlContext();
        dummyContext.DelayMs = 0;
        RunConversationAsync(charA, charB, scene, maxTurns, dummyContext).GetAwaiter().GetResult();
    }

    private Goal? GetActiveGoal(Character character, string targetName)
    {
        return character.Goals
            .Where(g => g.Target == targetName && g.CooldownRemaining == 0)
            .OrderByDescending(g => g.Priority)
            .ThenByDescending(g => g.Intensity)
            .FirstOrDefault();
    }

    private static bool IsCliSystemError(string response)
    {
        if (string.IsNullOrWhiteSpace(response)) return true;
        string t = response.TrimStart();
        return t.StartsWith("[CLI ERROR", StringComparison.OrdinalIgnoreCase)
            || t.StartsWith("[ERROR: CLI", StringComparison.OrdinalIgnoreCase)
            || IsCloudModelRefusal(t);
    }

    private static bool IsCloudModelRefusal(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return false;
        string lower = text.ToLowerInvariant();
        return lower.Contains("cannot fulfill this request") ||
               lower.Contains("against my safety guidelines") ||
               lower.Contains("as an ai language model, i cannot") ||
               lower.Contains("i cannot generate content of a sexual") ||
               lower.Contains("i am unable to generate content") ||
               lower.Contains("i cannot assist with sexually explicit");
    }

    private (string Dialogue, List<string> SomaticZones, int BondDelta, string GoalStatus, string? ImagePrompt, State.PsychosomaticStateSnapshot? LiveState) ParseResponse(string response, Character character)
    {
        if (character == null) character = new Character { Name = "Unknown" };
        if (string.IsNullOrWhiteSpace(response)) return ("", new List<string>(), 0, "None", null, null);

        // 0. Clamp runaway multi-reply / prompt-leak tails before field extraction
        response = LlmResponseSanitizer.ClampToFirstReply(response);
        if (string.IsNullOrWhiteSpace(response)) return ("", new List<string>(), 0, "None", null, null);

        // 1. Strip ANSI escape sequences (terminal color codes from CLI output)
        response = Regex.Replace(response, @"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "");

        // 2. Structured state snapshot extraction
        State.PsychosomaticStateSnapshot? liveState = null;
        string? extractedJson = State.PsychosomaticStateValidator.ExtractStateJson(response);
        if (!string.IsNullOrWhiteSpace(extractedJson))
        {
            State.PsychosomaticStateValidator.ValidateJson(extractedJson, out liveState);
        }
        else
        {
            var stateMatch = Regex.Match(response, @"(?:\[State:\s*|<=?state>?\s*)([\s\S]*?)(?:\]|</state>)", RegexOptions.IgnoreCase);
            if (stateMatch.Success)
            {
                string jsonText = stateMatch.Groups[1].Value;
                State.PsychosomaticStateValidator.ValidateJson(jsonText, out liveState);
            }
        }

        // 4. Bond Delta extraction — handles [Bond: +1], bond +1, bond: -1, [bond: 2], etc.
        var bondDelta = 0;
        var bondMatch = Regex.Match(response, @"(?:\[?Bond:?\s*|bond\s*)([\+\-]?\d+)(?:\]|\b)", RegexOptions.IgnoreCase);
        if (bondMatch.Success && int.TryParse(bondMatch.Groups[1].Value, out int bVal))
        {
            bondDelta = bVal;
        }
        else
        {
            bondDelta = InferBondDeltaFromDialogue(response);
        }

        // 5. Goal & Image prompt extraction
        var goalStatus = "None";
        var goalMatch = Regex.Match(response, @"\[Goal:\s*(.*?)\]", RegexOptions.IgnoreCase);
        if (goalMatch.Success)
        {
            goalStatus = goalMatch.Groups[1].Value.Trim();
        }

        string? imagePrompt = null;
        var imgMatch = Regex.Match(response, @"\[Image:\s*(.*?)\]", RegexOptions.IgnoreCase);
        if (imgMatch.Success)
        {
            imagePrompt = imgMatch.Groups[1].Value.Trim();
        }

        // 6. Split somatic tell from spoken/narration; rebuild a quoted canonical line
        var parsed = DialogueSegmentParser.Parse(response, character.Name, character.PhysicalDescription);
        var somaticZones = DialogueSegmentParser.IsZoneVocabularyDump(parsed.SomaticTells)
            ? new List<string>()
            : parsed.SomaticTells.ToList();

        var dialogue = parsed.CanonicalDialogue;

        // 7. Truncate prompt leak headers the sanitizer may have left mid-body
        int leakIdx = dialogue.IndexOf("PLAYER QUESTION", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("PLAYER STATEMENT", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("[They just said", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("[Player]", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("[User]", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("\nPlayer:", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();
        leakIdx = dialogue.IndexOf("\nUser:", StringComparison.OrdinalIgnoreCase);
        if (leakIdx >= 0) dialogue = dialogue[..leakIdx].Trim();

        if (string.IsNullOrWhiteSpace(dialogue) && !string.IsNullOrWhiteSpace(response))
        {
            dialogue = parsed.CanonicalDialogue;
            if (string.IsNullOrWhiteSpace(dialogue))
                dialogue = response.Trim();
        }

        // Hard ban filtering (P3)
        var banAudit = Safety.HardBanFilter.AuditAndSanitize(dialogue, character);
        dialogue = banAudit.SanitizedDialogue;

        // Output hygiene linter (P4)
        var leakAudit = Hygiene.SystemLeakLinter.Audit(dialogue);
        dialogue = leakAudit.SanitizedDialogue;

        return (dialogue, somaticZones, bondDelta, goalStatus, imagePrompt, liveState);
    }

    private static void UpdateBiasState(Character character, int bondDelta, string goalStatus, string sceneContext = "")
    {
        // Track bias state changes in memory (no disk commit per turn)
        // Disk commit happens on session end via CommitService.CommitSession
        if (bondDelta < 0 || goalStatus.Contains("Resisted", StringComparison.OrdinalIgnoreCase))
        {
            character.BiasState = "DEFENSIVE_ACTIVE";
            // Medium+ pressure still appends history in memory via PressureApplicator
            // but we don't write to disk every turn to avoid thrash
            if (Math.Abs(bondDelta) >= 3 || goalStatus.Contains("Resisted", StringComparison.OrdinalIgnoreCase))
            {
                // Apply pressure to in-memory log only (no disk write)
                ApplyPressureInMemory(character, "turn_tick", "Resistance/Friction", "medium", $"Goal: {goalStatus}, Bond: {bondDelta}");
            }
        }
        else if (bondDelta > 0 || goalStatus.Contains("Advanced", StringComparison.OrdinalIgnoreCase))
        {
            character.BiasState = "GENERATIVE_ACTIVE";
            if (bondDelta >= 3 || goalStatus.Contains("Advanced", StringComparison.OrdinalIgnoreCase))
            {
                ApplyPressureInMemory(character, "turn_tick", "Trust/Bond Expansion", "medium", $"Goal: {goalStatus}, Bond: {bondDelta}");
            }
        }
        else
        {
            character.BiasState = "DORMANT";
        }
    }

    /// <summary>
    /// Applies pressure to in-memory durable log without writing to disk.
    /// Use this for turn-by-turn pressure tracking.
    /// </summary>
    private static void ApplyPressureInMemory(Character character, string movementId, string pressure, string strength, string notes)
    {
        if (character.DurableLog == null)
        {
            if (!string.IsNullOrEmpty(character.LogPath) && System.IO.File.Exists(character.LogPath))
            {
                character.DurableLog = Logs.DurableLogStore.LoadLog(character.LogPath);
            }

            if (character.DurableLog == null && !string.IsNullOrEmpty(character.CardPath))
            {
                string dir = System.IO.Path.GetDirectoryName(character.CardPath) ?? "";
                string stem = System.IO.Path.GetFileNameWithoutExtension(character.CardPath);
                string candidatePath = System.IO.Path.Combine(dir, $"{stem}_log.yaml");
                if (System.IO.File.Exists(candidatePath))
                {
                    character.LogPath = candidatePath;
                    character.DurableLog = Logs.DurableLogStore.LoadLog(candidatePath);
                }
                else
                {
                    candidatePath = System.IO.Path.Combine(dir, $"{stem.ToLowerInvariant()}_log.yaml");
                    if (System.IO.File.Exists(candidatePath))
                    {
                        character.LogPath = candidatePath;
                        character.DurableLog = Logs.DurableLogStore.LoadLog(candidatePath);
                    }
                }
            }

            if (character.DurableLog == null)
            {
                character.DurableLog = new Logs.DurableLog();
                character.DurableLog.EnsureShape();
                character.DurableLog.character_id = character.Name;
                character.DurableLog.snapshot.bias_strength = character.BiasStrength;
            }
        }
        
        // Apply pressure transformation to in-memory log only
        Logs.PressureApplicator.ApplyPressure(character.DurableLog, movementId, pressure, strength, notes);
        
        // Update character bias_strength from log
        if (character.DurableLog.snapshot != null)
        {
            character.BiasStrength = character.DurableLog.snapshot.bias_strength;
        }
    }
}
