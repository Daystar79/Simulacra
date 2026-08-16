using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace CharacterSimulator.Logic;

/// <summary>
/// Clamps runaway SLM/LLM completions to a single in-character reply.
/// Small models often continue past the first answer, re-emit the same beat,
/// or invent prompt/meta fragments — this keeps only the first usable unit.
/// </summary>
public static class LlmResponseSanitizer
{
    private static readonly string[] LeakMarkers =
    {
        "PLAYER QUESTION",
        "PLAYER STATEMENT",
        "PLAYER QUESTION / STATEMENT:",
        "PLAYER QUESTION / INPUT:",
        "THEY JUST SAID/DID",
        "THEY JUST SAID",
        "A beat of time has passed",
        "The other person is still present",
        "Winning drive this beat",
        "[HOST CONSTRAINTS]",
        "HOST CONSTRAINTS",
        "MANDATE:",
        "First-Person Perspective:",
        "\n[Somatic:",
        "\r\n[Somatic:",
        "[Somatic:", // second occurrence handled separately
        "FORMATTING RULE",
        "Current Situation:",
        "Active Focus / State:",
        "Active Bias Lens:",
        "Bond with interlocutor:",
        "Last somatic tells:",
        "CONVERSATION SO FAR",
        "They just said/did",
        "[They just said",
        "[Player]",
        "[Player]:",
        "[User]",
        "[User]:",
        "[System]",
        "[System]:",
        "[Human]",
        "[Human]:",
        "[Interlocutor]",
        "You are roleplaying",
        "You are physically present",
        "Respond in this exact format",
        "Respond ONCE only",
        "SCENE (location",
        "SCENE:",
        "RULES:",
        "CHARACTER IDENTITY",
        "<|im_end|>",
        "<|im_start|>",
        "<|eot_id|>",
        "<|end_of_text|>",
        "[spoken",
        "<spoken",
        "\nUser:",
        "\nPlayer:",
        "\nSystem:",
        "\nHuman:",
        "\n###",
    };

    /// <summary>
    /// Returns the first complete reply and drops continuation / prompt-leak tail.
    /// </summary>
    public static string ClampToFirstReply(string? raw)
    {
        return ClampToFirstReply(raw, null, null);
    }

    /// <summary>
    /// Returns the first complete reply, stripping any leading user input parrot echoes,
    /// prompt headers, or runaway completion tails.
    /// </summary>
    public static string ClampToFirstReply(string? raw, string? userInput)
    {
        return ClampToFirstReply(raw, userInput, null);
    }

    /// <summary>
    /// Returns the first complete reply, stripping any leading user input parrot echoes,
    /// past turn dialogue re-prints, prompt headers, or runaway completion tails.
    /// </summary>
    public static string ClampToFirstReply(string? raw, string? userInput, string? conversationHistory)
    {
        if (string.IsNullOrWhiteSpace(raw))
            return raw ?? "";

        string text = raw.Trim();

        // Strip ANSI escape sequences (CLI color codes)
        text = Regex.Replace(text, @"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "");

        // Strip leading user input parroted back by local model before its reply
        if (!string.IsNullOrWhiteSpace(userInput))
        {
            string cleanUser = userInput.Trim().Trim('"', '\'');
            if (!string.IsNullOrWhiteSpace(cleanUser) && cleanUser.Length >= 3)
            {
                if (text.StartsWith(cleanUser, StringComparison.OrdinalIgnoreCase))
                {
                    text = text[cleanUser.Length..].TrimStart(' ', ':', '-', '"', '\'');
                }
                else if (text.StartsWith($"\"{cleanUser}\"", StringComparison.OrdinalIgnoreCase))
                {
                    text = text[(cleanUser.Length + 2)..].TrimStart(' ', ':', '-');
                }
                else if (text.StartsWith($"User input: \"{cleanUser}\"", StringComparison.OrdinalIgnoreCase) ||
                         text.StartsWith($"[Player]: \"{cleanUser}\"", StringComparison.OrdinalIgnoreCase) ||
                         text.StartsWith($"[User]: \"{cleanUser}\"", StringComparison.OrdinalIgnoreCase) ||
                         text.StartsWith($"User: \"{cleanUser}\"", StringComparison.OrdinalIgnoreCase) ||
                         text.StartsWith($"Player: \"{cleanUser}\"", StringComparison.OrdinalIgnoreCase))
                {
                    int endQuoteIdx = text.IndexOf(cleanUser, StringComparison.OrdinalIgnoreCase);
                    if (endQuoteIdx >= 0)
                    {
                        int afterQuote = endQuoteIdx + cleanUser.Length;
                        if (afterQuote < text.Length && text[afterQuote] == '"') afterQuote++;
                        text = text[afterQuote..].TrimStart(' ', ':', '-', '\r', '\n');
                    }
                }
            }
        }

        // Strip leading bracketed speaker prefix (e.g. "[Serena] *action*" or "[Serena]: hello")
        text = Regex.Replace(text, @"^\[[A-Za-z0-9_\-\s]{2,30}\]\s*:?\s*", "", RegexOptions.IgnoreCase).Trim();

        // Strip duplicate dialogue lines or action beats re-printed from prior turns in conversation history
        if (!string.IsNullOrWhiteSpace(conversationHistory))
        {
            var historyLines = conversationHistory.Split('\n')
                .Select(l => Regex.Replace(l.Trim(), @"^[A-Za-z0-9_\-\s]{2,30}\s*:\s*", "").Trim())
                .Select(l => l.Trim('"', '\''))
                .Where(l => l.Length > 8)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();

            foreach (var pastLine in historyLines)
            {
                int lineIdx = text.IndexOf(pastLine, StringComparison.OrdinalIgnoreCase);
                if (lineIdx >= 0 && lineIdx < 120) // model re-emitted past turn line at start
                {
                    int nextPara = text.IndexOf("\n\n", lineIdx);
                    if (nextPara > 0 && nextPara + 2 < text.Length)
                    {
                        text = text[(nextPara + 2)..].TrimStart();
                    }
                    else
                    {
                        int nextLine = text.IndexOf('\n', lineIdx + pastLine.Length);
                        if (nextLine > 0 && nextLine + 1 < text.Length)
                        {
                            text = text[(nextLine + 1)..].TrimStart();
                        }
                        else
                        {
                            text = text[(lineIdx + pastLine.Length)..].TrimStart();
                        }
                    }
                    break;
                }
            }
        }

        // Prefer content starting at first somatic tag when present
        int firstSomatic = IndexOfIgnoreCase(text, "[Somatic:");
        if (firstSomatic > 0)
            text = text[firstSomatic..].TrimStart();

        // Cut at second [Somatic: ...] block (intra-generation re-roll)
        if (firstSomatic >= 0 || text.StartsWith("[Somatic:", StringComparison.OrdinalIgnoreCase))
        {
            int second = IndexOfIgnoreCase(text, "[Somatic:", startIndex: 1);
            // First tag is at 0 after trim; find next occurrence after the first closing ]
            int afterFirstTag = text.IndexOf(']');
            if (afterFirstTag >= 0)
            {
                second = IndexOfIgnoreCase(text, "[Somatic:", startIndex: afterFirstTag + 1);
                if (second >= 0)
                    text = text[..second].TrimEnd();
            }
        }

        // Cut at earliest prompt-leak / meta marker (skip markers that are part of the first somatic line)
        int cutAt = text.Length;
        foreach (var marker in LeakMarkers)
        {
            if (marker.Equals("[Somatic:", StringComparison.Ordinal))
                continue;

            int idx = IndexOfIgnoreCase(text, marker);
            if (idx <= 0)
                continue;

            // Allow the first line to contain "[Somatic:" only
            if (marker.Contains("Somatic", StringComparison.OrdinalIgnoreCase) && idx < 12)
                continue;

            if (idx < cutAt)
                cutAt = idx;
        }

        if (cutAt < text.Length)
            text = text[..cutAt].TrimEnd();

        // Drop trailing meta lines that look like instruction echo
        text = TrimTrailingMetaLines(text);

        // Collapse exact duplicate paragraphs (model re-pasted the same block)
        text = CollapseDuplicateParagraphs(text);

        return text.Trim();
    }

    private static string TrimTrailingMetaLines(string text)
    {
        var lines = text.Split('\n').ToList();
        while (lines.Count > 0)
        {
            string t = lines[^1].Trim();
            if (string.IsNullOrEmpty(t))
            {
                lines.RemoveAt(lines.Count - 1);
                continue;
            }

            if (t.StartsWith("FORMATTING", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("RULES:", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("[spoken", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("<spoken", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("Current Situation", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("You are physically", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("You are roleplaying", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("[Player]", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("[User]", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("[System]", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("Player:", StringComparison.OrdinalIgnoreCase)
                || t.StartsWith("User:", StringComparison.OrdinalIgnoreCase)
                || t.Equals("System:", StringComparison.OrdinalIgnoreCase))
            {
                lines.RemoveAt(lines.Count - 1);
                continue;
            }

            break;
        }

        return string.Join("\n", lines).TrimEnd();
    }

    private static string CollapseDuplicateParagraphs(string text)
    {
        var parts = Regex.Split(text.Trim(), @"\n\s*\n")
            .Select(p => p.Trim())
            .Where(p => p.Length > 0)
            .ToList();

        if (parts.Count <= 1)
            return text.Trim();

        var kept = new List<string>();
        foreach (var p in parts)
        {
            if (kept.Count > 0 && string.Equals(NormalizeWs(kept[^1]), NormalizeWs(p), StringComparison.OrdinalIgnoreCase))
                continue;
            // Near-duplicate: second paragraph starts with same dialogue quote as first
            if (kept.Count > 0 && SharesLeadingDialogue(kept[0], p))
                continue;
            kept.Add(p);
        }

        // One reply unit is enough for turn parsing
        if (kept.Count > 2)
            kept = kept.Take(2).ToList();

        return string.Join("\n\n", kept).Trim();
    }

    private static bool SharesLeadingDialogue(string a, string b)
    {
        string qa = ExtractFirstQuoted(a);
        string qb = ExtractFirstQuoted(b);
        if (string.IsNullOrEmpty(qa) || string.IsNullOrEmpty(qb))
            return false;
        return string.Equals(qa, qb, StringComparison.OrdinalIgnoreCase);
    }

    private static string ExtractFirstQuoted(string s)
    {
        var m = Regex.Match(s, "\"([^\"]{3,})\"");
        return m.Success ? m.Groups[1].Value.Trim() : "";
    }

    private static string NormalizeWs(string s) =>
        Regex.Replace(s ?? "", @"\s+", " ").Trim();

    private static int IndexOfIgnoreCase(string haystack, string needle, int startIndex = 0)
    {
        if (string.IsNullOrEmpty(haystack) || string.IsNullOrEmpty(needle))
            return -1;
        if (startIndex < 0 || startIndex >= haystack.Length)
            return -1;
        return haystack.IndexOf(needle, startIndex, StringComparison.OrdinalIgnoreCase);
    }
}
