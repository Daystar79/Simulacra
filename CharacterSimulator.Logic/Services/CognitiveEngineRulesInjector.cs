using System;
using System.IO;
using System.Text;

namespace CharacterSimulator.Logic.Services;

public static class CognitiveEngineRulesInjector
{
    /// <summary>
    /// Optionally loads pipeline and system rules snippets from disk into system prompt context
    /// without placing psychology math inside C# logic.
    /// </summary>
    public static string LoadCognitiveRules(string? customRulesPath = null)
    {
        var sb = new StringBuilder();

        // 1. Check for standard runtime spec file
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string defaultPath = Path.Combine(baseDir, "Data", "cognitive_rules.md");
        string targetPath = customRulesPath ?? defaultPath;

        if (File.Exists(targetPath))
        {
            try
            {
                string text = File.ReadAllText(targetPath);
                sb.AppendLine("\n[COGNITIVE ENGINE PIPELINE MANDATE]");
                sb.AppendLine(text.Trim());
            }
            catch (Exception ex)
            {
                AppLogger.Warning($"[CognitiveEngineRulesInjector] Could not read rules file {targetPath}: {ex.Message}");
            }
        }
        else
        {
            // Fallback default host cognitive guidelines
            sb.AppendLine("\n[COGNITIVE ENGINE HOST RULES]");
            sb.AppendLine("1. Maintain persistent emotional trajectory and body state across turns.");
            sb.AppendLine("2. Respect relationship bond deltas and character agency without breaking immersion.");
        }

        return sb.ToString();
    }
}
