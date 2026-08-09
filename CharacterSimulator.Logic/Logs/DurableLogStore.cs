using System;
using System.Collections.Generic;
using System.IO;
using CharacterSimulator.Logic.State;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic.Logs;

/// <summary>
/// Handles durable log I/O (`Characters/[slug]_log.yaml`) and log overlay precedence rules.
/// Log overlay ALWAYS wins over identity card defaults for runtime transformation attributes.
/// </summary>
public static class DurableLogStore
{
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();

    private static readonly ISerializer Serializer = new SerializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .ConfigureDefaultValuesHandling(DefaultValuesHandling.OmitNull)
        .Build();

    public static DurableLog LoadLog(string path)
    {
        if (!File.Exists(path))
        {
            var empty = new DurableLog();
            empty.EnsureShape();
            return empty;
        }

        try
        {
            string yamlText = File.ReadAllText(path);
            var log = Deserializer.Deserialize<DurableLog>(yamlText) ?? new DurableLog();
            log.EnsureShape();
            return log;
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[DurableLogStore] Failed to load log at '{path}': {ex.Message}");
            var fallback = new DurableLog();
            fallback.EnsureShape();
            return fallback;
        }
    }

    public static void SaveLog(string path, DurableLog log)
    {
        log.EnsureShape();
        log.updated_at = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
        
        string body = Serializer.Serialize(log);
        string text = "---\n" + body;
        
        string? dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }
        
        File.WriteAllText(path, text);
    }

    /// <summary>
    /// Applies log overlay over character card defaults.
    /// Log overlay wins for: active focus, latent weights, bias_strength, skills, memories, relational baselines, default somatic.
    /// Never writes evolution back to card.
    /// </summary>
    public static void ApplyOverlay(Character character, DurableLog log)
    {
        if (character == null) throw new ArgumentNullException(nameof(character));
        if (log == null) throw new ArgumentNullException(nameof(log));
        
        log.EnsureShape();
        character.DurableLog = log;
        character.LogPath ??= GetExpectedLogPath(character.CardPath);

        // 1. Active Focus
        if (!string.IsNullOrWhiteSpace(log.snapshot.active_focus))
        {
            character.ActiveFocus = log.snapshot.active_focus;
            character.CurrentState = log.snapshot.active_focus;
        }

        // 2. Bias Strength (clamped)
        character.BiasStrength = ScaleClamps.Clamp0To100(log.snapshot.bias_strength);

        // 3. Default Somatic
        if (!string.IsNullOrWhiteSpace(log.snapshot.default_somatic))
        {
            if (character.SomaticZones.Count == 0 || !character.SomaticZones.Contains(log.snapshot.default_somatic))
            {
                character.SomaticZones.Insert(0, log.snapshot.default_somatic);
            }
        }

        // 4. Skills (active)
        if (log.skills.active != null && log.skills.active.Count > 0)
        {
            character.ActiveSkills = new List<string>(log.skills.active);
        }

        // 5. Memories (detailed)
        if (log.memories.detailed != null && log.memories.detailed.Count > 0)
        {
            character.Memories = new List<string>(log.memories.detailed);
        }

        // 6. Relational Baselines
        if (log.relational_baselines != null && log.relational_baselines.Count > 0)
        {
            foreach (var (k, v) in log.relational_baselines)
            {
                character.RelationalBaselines[k] = ScaleClamps.Clamp0To100(v);
            }
        }
    }

    public static string GetExpectedLogPath(string cardPath)
    {
        if (string.IsNullOrWhiteSpace(cardPath)) return "_log.yaml";
        string dir = Path.GetDirectoryName(cardPath) ?? "";
        string slug = Path.GetFileNameWithoutExtension(cardPath).ToLowerInvariant();
        return Path.Combine(dir, $"{slug}_log.yaml");
    }
}
