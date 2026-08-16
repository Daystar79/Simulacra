using System;
using System.IO;
using System.Text;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// Compact host-side cognitive constraints. Never dumps the pipeline document
/// (that would leak jargon and blow the SLM budget). Optional overlay file
/// may append extra lines; it does not replace the core four.
/// </summary>
public static class CognitiveEngineRulesInjector
{
    public static string LoadCognitiveRules(string? customRulesPath = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine("[HOST CONSTRAINTS]");
        sb.AppendLine("- Volition: never a passive Q&A endpoint; ask back, probe motives, or act from the winning drive.");
        sb.AppendLine("- Body before insight: physical beat before or folded into speech.");
        sb.AppendLine("- Off-page matrix: never speak Realm, Bias, Gift, Prism, Bond scores, or engine labels.");
        sb.AppendLine("- Card supremacy: identity is the card; scene is room and weather only.");

        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string targetPath = customRulesPath ?? Path.Combine(baseDir, "Data", "cognitive_rules.md");
        if (File.Exists(targetPath))
        {
            try
            {
                string extra = File.ReadAllText(targetPath).Trim();
                if (extra.Length > 0)
                {
                    sb.AppendLine(extra);
                }
            }
            catch (Exception ex)
            {
                AppLogger.Warning($"[CognitiveEngineRulesInjector] Could not read rules file {targetPath}: {ex.Message}");
            }
        }

        return sb.ToString().TrimEnd();
    }
}
