using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using CharacterSimulator.Logic.Data.Db;

namespace CharacterSimulator.Logic.Services;

public static class SessionExportService
{
    /// <summary>
    /// Exports session transcript directly to Markdown (.md) file.
    /// </summary>
    public static string ExportSessionToMarkdown(DbSession session, List<DbSessionTurn> turns, List<string> participants, string? outputPath = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"# Roleplay Session Transcript: {session.Title}");
        sb.AppendLine();
        sb.AppendLine($"**Session ID:** `{session.Id}`  ");
        sb.AppendLine($"**Scene:** {session.Scene}  ");
        sb.AppendLine($"**Genre:** {session.Genre}  ");
        sb.AppendLine($"**Mode:** {session.Mode}  ");
        sb.AppendLine($"**Started At:** {session.StartedAt:yyyy-MM-dd HH:mm:ss} UTC  ");
        sb.AppendLine($"**Participants:** {string.Join(", ", participants)}  ");
        sb.AppendLine();
        sb.AppendLine("---");
        sb.AppendLine();

        foreach (var turn in turns)
        {
            sb.AppendLine($"### Turn {turn.TurnIndex} — {turn.Speaker} ➔ {turn.Target}");
            if (!string.IsNullOrWhiteSpace(turn.SpeakerEmotion))
            {
                sb.AppendLine($"*Emotion:* **{turn.SpeakerEmotion}** | *Bond Delta:* `{turn.BondDelta:+0;-0;0}` (Total: `{turn.CurrentBond}`)");
            }
            sb.AppendLine();
            sb.AppendLine(turn.Dialogue);
            if (!string.IsNullOrWhiteSpace(turn.SomaticJson) && turn.SomaticJson != "{}")
            {
                sb.AppendLine();
                sb.AppendLine($"<details><summary>Somatic State</summary>");
                sb.AppendLine($"```json\n{turn.SomaticJson}\n```");
                sb.AppendLine("</details>");
            }
            sb.AppendLine();
            sb.AppendLine("---");
            sb.AppendLine();
        }

        string mdContent = sb.ToString();

        if (!string.IsNullOrWhiteSpace(outputPath))
        {
            var dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(outputPath, mdContent);
        }

        return mdContent;
    }

    /// <summary>
    /// Exports character progress snapshot as JSON for debugging.
    /// </summary>
    public static string ExportCharacterProgressToJson(CharacterProgressRecord progress, string? outputPath = null)
    {
        var options = new JsonSerializerOptions { WriteIndented = true };
        string json = JsonSerializer.Serialize(progress, options);

        if (!string.IsNullOrWhiteSpace(outputPath))
        {
            var dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(outputPath, json);
        }

        return json;
    }
}
