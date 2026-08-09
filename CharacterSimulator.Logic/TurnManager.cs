using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic;

public class TurnManager
{
    private readonly ILLMClient _clientA;
    private readonly ILLMClient? _clientB;
    private readonly SceneManager _sceneManager;
    private readonly Logger _logger;
    private string? _pendingUserInput;
    private string _pendingUserRole = "Player";

    public event Action<TurnStepEventArgs>? OnTurnStep;
    public event Action<GoalEvaluationEventArgs>? OnGoalEvaluated;
    public event Action<string>? OnSceneStarted;
    public event Action<string>? OnAgentOutputLogged;
    public event Action<string, string>? OnAgentTurnStarted;

    public TurnManager(ILLMClient clientA, ILLMClient? clientB, SceneManager sceneManager, Logger logger)
    {
        _clientA = clientA;
        _clientB = clientB;
        _sceneManager = sceneManager;
        _logger = logger;
    }

    public void InjectUserInput(string userRole, string text)
    {
        _pendingUserRole = userRole;
        _pendingUserInput = text;
    }

    public async Task RunConversationAsync(Character charA, Character? charB, string scene, int maxTurns, TurnControlContext controlContext)
    {
        _sceneManager.SetScene(scene);
        _logger.LogScene(scene);
        OnSceneStarted?.Invoke(scene);

        bool isSoloMode = charB == null || string.Equals(charB.Name, "None", StringComparison.OrdinalIgnoreCase);
        string targetBName = isSoloMode ? "Player" : (charB?.Name ?? "Unknown");

        charA.ResistanceCount[targetBName] = 0;
        if (!isSoloMode && charB != null) charB.ResistanceCount[charA.Name] = 0;

        string lastInputForA = "";
        string lastInputForB = "";
        controlContext.Start();

        try
        {
            for (int turn = 0; turn < maxTurns; turn++)
            {
                if (controlContext.CancellationToken.IsCancellationRequested) break;

                // Determine input for Client A
                string inputA = lastInputForA;
                if (!string.IsNullOrEmpty(_pendingUserInput))
                {
                    inputA = $"[{_pendingUserRole}]: \"{_pendingUserInput}\"";
                    _pendingUserInput = null;
                }

                // Client A Turn
                Goal? activeGoalA = GetActiveGoal(charA, targetBName);
                string goalContextA = activeGoalA != null ?
                    $"Your current goal: {activeGoalA.Type} {activeGoalA.Target} (Intensity: {activeGoalA.Intensity}). Strategies: {string.Join(", ", activeGoalA.Strategies)}." :
                    "";

                string providerA = (_clientA as CliLlmClient)?.Name ?? "LLM";
                OnAgentTurnStarted?.Invoke(charA.Name, providerA);
                OnAgentOutputLogged?.Invoke($"[⏳ {charA.Name}] Dispatching prompt to {providerA}...\n");

                string promptA;
                try
                {
                    promptA = await _clientA.SendPromptAsync(charA, inputA, scene, goalContextA, controlContext.CancellationToken).ConfigureAwait(false);
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
                        System.Diagnostics.Debug.WriteLine("[TurnManager] Failed to apply live state for " + charA.Name);
                    }
                }

                if (somaticA.Count > 0) charA.SomaticZones = somaticA;
                charA.Bond += bondDeltaA;
                charA.UpdateEmotionFromSomatic(charA.SomaticZones, dialogueA);
                UpdateBiasState(charA, bondDeltaA, goalStatusA, scene);

                _logger.LogTurn(charA.Name, dialogueA, charA.SomaticZones, charA.Bond, activeGoalA?.Type, goalStatusA);

                OnTurnStep?.Invoke(new TurnStepEventArgs
                {
                    TurnIndex = turn + 1,
                    SpeakerName = charA.Name,
                    TargetName = targetBName,
                    Dialogue = dialogueA,
                    SomaticZones = charA.SomaticZones,
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
                if (!string.IsNullOrEmpty(_pendingUserInput))
                {
                    inputB = $"[{_pendingUserRole}]: \"{_pendingUserInput}\"";
                    _pendingUserInput = null;
                }

                // Client B Turn
                Goal? activeGoalB = GetActiveGoal(charB, charA.Name);
                string goalContextB = activeGoalB != null ?
                    $"Your current goal: {activeGoalB.Type} {activeGoalB.Target} (Intensity: {activeGoalB.Intensity}). Strategies: {string.Join(", ", activeGoalB.Strategies)}." :
                    "";

                string providerB = (_clientB as CliLlmClient)?.Name ?? "LLM";
                OnAgentTurnStarted?.Invoke(charB.Name, providerB);
                OnAgentOutputLogged?.Invoke($"[⏳ {charB.Name}] Dispatching prompt to {providerB}...\n");

                string promptB;
                try
                {
                    promptB = await _clientB.SendPromptAsync(charB, inputB, scene, goalContextB, controlContext.CancellationToken).ConfigureAwait(false);
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
                        System.Diagnostics.Debug.WriteLine("[TurnManager] Failed to apply live state for " + charB.Name);
                    }
                }

                if (somaticB.Count > 0) charB.SomaticZones = somaticB;
                charB.Bond += bondDeltaB;
                charB.UpdateEmotionFromSomatic(charB.SomaticZones, dialogueB);
                UpdateBiasState(charB, bondDeltaB, goalStatusB, scene);

                _logger.LogTurn(charB.Name, dialogueB, charB.SomaticZones, charB.Bond, activeGoalB?.Type, goalStatusB);

                OnTurnStep?.Invoke(new TurnStepEventArgs
                {
                    TurnIndex = turn + 1,
                    SpeakerName = charB.Name,
                    TargetName = charA.Name,
                    Dialogue = dialogueB,
                    SomaticZones = charB.SomaticZones,
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

                lastInputForA = dialogueB;

                await controlContext.WaitTurnAsync();
            }
        }
        finally
        {
            // Auto-commit session state on scene break or close
            Logs.CommitService.CommitSession(charA, charB, scene);
        }
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
            || t.StartsWith("[ERROR: CLI", StringComparison.OrdinalIgnoreCase);
    }

    private (string Dialogue, List<string> SomaticZones, int BondDelta, string GoalStatus, string? ImagePrompt, State.PsychosomaticStateSnapshot? LiveState) ParseResponse(string response, Character character)
    {
        if (character == null) character = new Character { Name = "Unknown" };
        if (string.IsNullOrWhiteSpace(response)) return ("", new List<string>(), 0, "None", null, null);

        // 1. Strip ANSI escape sequences (terminal color codes from CLI output)
        response = Regex.Replace(response, @"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "");

        // 2. Somatic extraction
        var somaticMatch = Regex.Match(response, @"\[Somatic:\s*(.*?)\]", RegexOptions.IgnoreCase);
        var somaticZones = somaticMatch.Success ?
            somaticMatch.Groups[1].Value.Split(',').Select(s => s.Trim()).Where(s => !string.IsNullOrEmpty(s)).ToList() :
            new List<string>();

        // 3. Structured state snapshot extraction
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

        // 6. Dialogue Tag Cleanup — remove meta-tags and code fences
        var dialogue = Regex.Replace(response, @"\[Somatic:\s*.*?\]", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"\[Goal:\s*.*?\]", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"\[Image:\s*.*?\]", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"(?:\[State:\s*|<=?state>?\s*)([\s\S]*?)(?:\]|</state>)", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"\[?Bond:?\s*[\+\-]?\d+\]?", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"```[\s\S]*?```", "", RegexOptions.IgnoreCase).Trim();
        dialogue = Regex.Replace(dialogue, @"<state>[\s\S]*?</state>", "", RegexOptions.IgnoreCase).Trim();

        // 7. Strip leading LLM meta-preamble lines (e.g. "Sure, here is the response:")
        var lines = dialogue.Split('\n').Select(l => l.Trim()).Where(l => !string.IsNullOrEmpty(l)).ToList();
        if (lines.Count > 1 && (
            lines[0].StartsWith("Sure", StringComparison.OrdinalIgnoreCase) ||
            lines[0].StartsWith("Here is", StringComparison.OrdinalIgnoreCase) ||
            lines[0].StartsWith("As ", StringComparison.OrdinalIgnoreCase) ||
            lines[0].EndsWith(":") && !lines[0].Contains('"')))
        {
            lines.RemoveAt(0);
            dialogue = string.Join("\n", lines);
        }

        // 8. Strip redundant speaker name prefix if the model outputted "CharacterName: ..."
        if (!string.IsNullOrWhiteSpace(character.Name))
        {
            string namePattern = @"^(?:\*\*)?" + Regex.Escape(character.Name) + @"(?:\*\*)?\s*:\s*";
            dialogue = Regex.Replace(dialogue, namePattern, "", RegexOptions.IgnoreCase).Trim();
        }

        // 9. Unwrap outer quotes if model wrapped full response in quotes
        if (dialogue.StartsWith('"') && dialogue.EndsWith('"') && dialogue.Length >= 2)
        {
            dialogue = dialogue[1..^1].Trim();
        }

        if (string.IsNullOrWhiteSpace(dialogue) && !string.IsNullOrWhiteSpace(response))
        {
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
