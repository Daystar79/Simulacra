using System;
using System.IO;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic.Logs;

/// <summary>
/// Service responsible for executing durable log commits according to CognitivePipeline.md §8 protocol:
/// - Map only durable fields into the log (focus, skills, memories, history, relational baselines, bias_strength, default_somatic).
/// - Live snapshot is ephemeral per tick.
/// - Commit triggers: scene break, medium+ pressure shift, session close, explicit /save.
/// </summary>
public class CommitService
{
    public static void CommitCharacterLog(Character character, string movementId, string triggerReason, string strength = "medium", string notes = "")
    {
        if (character == null) return;

        string logPath = character.LogPath ?? DurableLogStore.GetExpectedLogPath(character.CardPath);
        character.LogPath = logPath;

        DurableLog log = character.DurableLog ?? DurableLogStore.LoadLog(logPath);

        // Map live character durable state to log snapshot
        log.snapshot.active_focus = character.ActiveFocus ?? character.CurrentState ?? "";
        log.snapshot.bias_strength = character.BiasStrength;
        if (character.SomaticZones.Count > 0)
        {
            log.snapshot.default_somatic = character.SomaticZones[0];
        }

        // Map skills & memories
        log.skills.active = new System.Collections.Generic.List<string>(character.ActiveSkills);
        log.memories.detailed = new System.Collections.Generic.List<string>(character.Memories);

        // Map relational baselines
        log.relational_baselines = new System.Collections.Generic.Dictionary<string, int>(character.RelationalBaselines, StringComparer.OrdinalIgnoreCase);

        // Apply pressure transformation if trigger specifies pressure/strength
        PressureApplicator.ApplyPressure(log, movementId, triggerReason, strength, notes);

        // Save durable log to file
        DurableLogStore.SaveLog(logPath, log);
        character.DurableLog = log;

        AppLogger.Warning($"[CommitService] Committed durable log for '{character.Name}' to '{logPath}' on {triggerReason}.");
    }

    public static void CommitSession(Character charA, Character? charB, string sceneContext, string movementId = "session_close")
    {
        if (charA != null)
        {
            if (charA.DurableLog != null && charA.DurableLog.history.Count > 0)
            {
                CommitCharacterLogExplicit(charA, movementId, $"Session Close - Scene: {sceneContext}");
            }
            else
            {
                CommitCharacterLog(charA, movementId, "Session Close", "low", $"Scene: {sceneContext}");
            }
        }
        if (charB != null && !string.Equals(charB.Name, "None", StringComparison.OrdinalIgnoreCase))
        {
            if (charB.DurableLog != null && charB.DurableLog.history.Count > 0)
            {
                CommitCharacterLogExplicit(charB, movementId, $"Session Close - Scene: {sceneContext}");
            }
            else
            {
                CommitCharacterLog(charB, movementId, "Session Close", "low", $"Scene: {sceneContext}");
            }
        }
    }

    /// <summary>
    /// Explicitly commits character log to disk (for /save command).
    /// </summary>
    public static void CommitCharacterLogExplicit(Character character, string movementId = "manual_save", string notes = "")
    {
        if (character == null || character.DurableLog == null) return;

        string logPath = character.LogPath ?? DurableLogStore.GetExpectedLogPath(character.CardPath);
        character.LogPath = logPath;

        // Update the log from current character state
        character.DurableLog.character_id = character.Name;
        character.DurableLog.snapshot.active_focus = character.ActiveFocus ?? character.CurrentState ?? "";
        character.DurableLog.snapshot.bias_strength = character.BiasStrength;
        if (character.SomaticZones.Count > 0)
        {
            character.DurableLog.snapshot.default_somatic = character.SomaticZones[0];
        }
        character.DurableLog.skills.active = new System.Collections.Generic.List<string>(character.ActiveSkills);
        character.DurableLog.memories.detailed = new System.Collections.Generic.List<string>(character.Memories);
        character.DurableLog.relational_baselines = new System.Collections.Generic.Dictionary<string, int>(character.RelationalBaselines, StringComparer.OrdinalIgnoreCase);

        // Save to disk
        DurableLogStore.SaveLog(logPath, character.DurableLog);

        AppLogger.Warning($"[CommitService] Explicit save for '{character.Name}' to '{logPath}'.");
    }
}
