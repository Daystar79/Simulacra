using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace CharacterSimulator.Logic;

public enum DialogueSegmentKind
{
    Somatic,
    Narration,
    Speech
}

public sealed record DialogueSegment(DialogueSegmentKind Kind, string Text);

/// <summary>
/// Splits a raw SLM/LLM roleplay reply into somatic tell, spoken dialogue, and narration.
/// Small models routinely omit quotes, echo card zone dumps, and glue internal state
/// onto the spoken line — this is the host-side repair for the main window feed.
/// </summary>
public static class DialogueSegmentParser
{
    private static readonly Regex SomaticTagRegex = new(
        @"\[Somatic:?\s*([^\]]*)\]",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex SomaticLineRegex = new(
        @"(?:^|\n)\s*Somatic:\s*(.+?)(?=\n\s*(?:Action\s*beat:|Somatic:|"")|\n\s*\n|$)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled | RegexOptions.Singleline);

    private static readonly Regex ActionBeatLabelRegex = new(
        @"(?:^|\n)\s*(?:Opening|Concluding|Closing)?\s*(?:physical\s+)?action\s*beat\s*:?\s*",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex InlineActionBeatLabelRegex = new(
        @"\b(?:Opening|Concluding|Closing)\s+(?:physical\s+)?action\s+beat\s*:?\s*",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex MetaTagRegex = new(
        @"\[(?:Goal|Image|Bond):\s*[^\]]*\]",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex BondBareRegex = new(
        @"(?:^|[\s])\[?Bond:?\s*[\+\-]?\d+\]?",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex StateBlockRegex = new(
        @"(?:\[State:\s*|<=?state>?\s*)([\s\S]*?)(?:\]|</state>)|<state>[\s\S]*?</state>",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex CodeFenceRegex = new(
        @"```[\s\S]*?```",
        RegexOptions.Compiled);

    private static readonly Regex XmlHintRegex = new(
        @"</?(?:spoken\s*dialogue|narrative\s*action[^>]*|autonomic\s*internal\s*tell)\s*/?>",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex FirstPersonMetaRegex = new(
        @"\s+in\s+1st\s+person\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex ZoneLabelRegex = new(
        @"\b(?:Face/Eyes|Throat/Neck|Chest/Breath|Hands/Arms|Spine/Posture|Feet/Staging)\s*:",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex AttributionRegex = new(
        @"^\s*(?:[A-Z][A-Za-z0-9'\-]+|[Ii]|[Ss]he|[Hh]e|[Tt]hey)\s+(?:say|says|said|ask|asks|asked|repl(?:y|ies|ied)|responds?|responded|murmurs?|murmured|whispers?|whispered|repeats?|repeated|adds?|added|confirms?|confirmed|continues?|continued)\b",
        RegexOptions.Compiled);

    private static readonly Regex PhysicalVerbRegex = new(
        @"\b(?:step(?:s|ped|ping)?|reach(?:es|ed|ing)?|turn(?:s|ed|ing)?|pull(?:s|ed|ing)?|lift(?:s|ed|ing)?|lean(?:s|ed|ing)?|nod(?:s|ded|ding)?|slide(?:s|d|ing)?|trace(?:s|d|ing)?|cup(?:s|ped|ping)?|tilt(?:s|ed|ing)?|ris(?:e|es|ing|en)|extend(?:s|ed|ing)?|walk(?:s|ed|ing)?|sit(?:s|ting)?|stood|stand(?:s|ing)?|gesture(?:s|d)?|opens?|closes?|pauses?|sighs?|smiles?|takes?\s+a\s+step|looks?\s+(?:over|away|down|up|at)|holds?|rests?)\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex InternalTellRegex = new(
        @"\b(?:heart\s*rate|pulse|blush|breath(?:e|ing|es)?|cheeks?|shiver|flush|stomach|throat\s+tightens)\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex SpeechOpenerRegex = new(
        @"^\s*(?:yes|no|yeah|yep|nah|well|oh|ah|hey|hi|hello|please|thank|sorry|wait|of course|very well|shall we|i(?:'m| am| do| don't| cannot| can't| won't| would| will| appreciate| think| know| want| need| love| believe)\b)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    /// <summary>Parse a reply (or already-cleaned dialogue) into display segments.</summary>
    public static List<DialogueSegment> Parse(string? raw)
    {
        return Parse(raw, speakerName: null, physicalDescription: null).Segments;
    }

    public static DialogueParseResult Parse(string? raw, string? speakerName, string? physicalDescription = null)
    {
        var result = new DialogueParseResult();
        if (string.IsNullOrWhiteSpace(raw))
            return result;

        string text = NormalizeQuotes(raw.Trim());
        text = Regex.Replace(text, @"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "");

        ExtractSomatic(ref text, result.SomaticTells, speakerName);

        text = StripMeta(text, speakerName, physicalDescription);
        if (string.IsNullOrWhiteSpace(text))
        {
            result.RebuildCanonical();
            return result;
        }

        ScanBody(text, result.Segments);
        MergeAdjacent(result.Segments);

        // Somatic tells render as their own row; keep them at the front of the segment list
        // only when they were not already emitted from leftover body text.
        if (result.SomaticTells.Count > 0 && result.Segments.All(s => s.Kind != DialogueSegmentKind.Somatic))
        {
            string tell = FormatSomaticForDisplay(result.SomaticTells);
            if (!string.IsNullOrWhiteSpace(tell))
                result.Segments.Insert(0, new DialogueSegment(DialogueSegmentKind.Somatic, tell));
        }

        result.RebuildCanonical();
        return result;
    }

    /// <summary>True when the model echoed the card's zone vocabulary instead of a live tell.</summary>
    public static bool IsZoneVocabularyDump(IEnumerable<string>? tells)
    {
        if (tells == null) return false;
        string joined = string.Join(" ", tells);
        return ZoneLabelRegex.Matches(joined).Count >= 2;
    }

    public static string FormatSomaticForDisplay(IEnumerable<string>? tells)
    {
        if (tells == null) return "";
        var list = tells.Where(t => !string.IsNullOrWhiteSpace(t)).Select(t => t.Trim()).ToList();
        if (list.Count == 0) return "";

        if (IsZoneVocabularyDump(list))
            return "";

        string joined = string.Join("; ", list);
        joined = Regex.Replace(joined, @"\s+", " ").Trim();
        if (joined.Length > 180)
            joined = joined[..177].TrimEnd() + "…";
        return joined;
    }

    private static void ExtractSomatic(ref string text, List<string> tells, string? speakerName = null)
    {
        foreach (Match m in SomaticTagRegex.Matches(text))
            AddTell(tells, m.Groups[1].Value, speakerName);

        text = SomaticTagRegex.Replace(text, " ").Trim();

        foreach (Match m in SomaticLineRegex.Matches(text))
            AddTell(tells, m.Groups[1].Value, speakerName);

        text = SomaticLineRegex.Replace(text, "\n").Trim();

        // Collapse a comma-split zone dump back into labeled chunks when possible
        if (IsZoneVocabularyDump(tells))
        {
            string joined = string.Join(", ", tells);
            var chunks = Regex.Split(joined, @"(?=\b(?:Face/Eyes|Throat/Neck|Chest/Breath|Hands/Arms|Spine/Posture|Feet/Staging)\s*:)", RegexOptions.IgnoreCase)
                .Select(s => s.Trim().Trim(','))
                .Where(s => s.Length > 0)
                .ToList();
            if (chunks.Count >= 2)
            {
                tells.Clear();
                tells.AddRange(chunks);
            }
        }
    }

    private static void AddTell(List<string> tells, string raw, string? speakerName = null)
    {
        string value = Regex.Replace(raw ?? "", @"\s+", " ").Trim().Trim('"', '\'');
        if (string.IsNullOrWhiteSpace(value)) return;

        if (!string.IsNullOrWhiteSpace(speakerName) &&
            value.StartsWith(speakerName.Trim(), StringComparison.OrdinalIgnoreCase))
        {
            value = value[speakerName.Trim().Length..].TrimStart(' ', ',', '.', ':');
        }

        // Card scent / appearance dumped into the tell — keep the first clause
        // (do not chop zone-vocabulary dumps; those are classified later)
        if (value.Length > 56 && value.Contains(',') && ZoneLabelRegex.Matches(value).Count < 2)
            value = value[..value.IndexOf(',')].Trim();

        if (string.IsNullOrWhiteSpace(value)) return;
        if (tells.Any(t => string.Equals(t, value, StringComparison.OrdinalIgnoreCase))) return;
        tells.Add(value);
    }

    private static string StripMeta(string text, string? speakerName, string? physicalDescription)
    {
        text = CodeFenceRegex.Replace(text, " ");
        text = StateBlockRegex.Replace(text, " ");
        text = MetaTagRegex.Replace(text, " ");
        text = BondBareRegex.Replace(text, " ");
        text = XmlHintRegex.Replace(text, " ");
        text = ActionBeatLabelRegex.Replace(text, " ");
        text = InlineActionBeatLabelRegex.Replace(text, " ");
        text = FirstPersonMetaRegex.Replace(text, " ");
        text = Regex.Replace(text, @"\bthe interlocutor\b", "you", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"\s+-\s*$", "", RegexOptions.Multiline);

        // Unwrap leftover [action / voice] brackets that are not known tags
        text = Regex.Replace(text, @"\[\s*([^\]]+?)\s*\]", "$1");
        text = text.Replace("[", " ").Replace("]", " ");

        if (!string.IsNullOrWhiteSpace(speakerName))
        {
            string esc = Regex.Escape(speakerName.Trim());
            text = Regex.Replace(text,
                @"^(?:\[?" + esc + @"\]?|\*\*" + esc + @"\*\*)\s*:?\s*",
                "",
                RegexOptions.IgnoreCase | RegexOptions.Multiline);
            // "Serena looks thoughtfully…" — third-person self-narration, keep the verb
            text = Regex.Replace(text,
                @"(?:^|\n)\s*" + esc + @"\s+(?=[a-z])",
                "\n",
                RegexOptions.IgnoreCase);
            // orphan possessive after a stripped "Serena:" → "'s eyes close"
            text = Regex.Replace(text, @"(?:^|\n)\s*'s\s+", " ");
        }

        if (!string.IsNullOrWhiteSpace(physicalDescription) && physicalDescription.Trim().Length > 15)
        {
            string phys = physicalDescription.Trim();
            text = text.Replace(phys, "", StringComparison.OrdinalIgnoreCase);
        }

        // Drop leading LLM preamble
        var lines = text.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).ToList();
        if (lines.Count > 1 && IsPreamble(lines[0]))
            lines.RemoveAt(0);

        text = string.Join("\n", lines);
        text = Regex.Replace(text, @"[ \t]{2,}", " ");
        text = Regex.Replace(text, @"\n{3,}", "\n\n");
        return text.Trim();
    }

    private static bool IsPreamble(string line)
    {
        return line.StartsWith("Sure", StringComparison.OrdinalIgnoreCase)
            || line.StartsWith("Here is", StringComparison.OrdinalIgnoreCase)
            || line.StartsWith("As ", StringComparison.OrdinalIgnoreCase)
            || (line.EndsWith(':') && !line.Contains('"'));
    }

    private static void ScanBody(string text, List<DialogueSegment> segments)
    {
        var plain = new StringBuilder();
        int i = 0;

        void FlushPlain()
        {
            if (plain.Length == 0) return;
            ClassifyPlain(plain.ToString(), segments);
            plain.Clear();
        }

        while (i < text.Length)
        {
            char c = text[i];

            if (c == '*' && i + 1 < text.Length && text[i + 1] == '*')
            {
                int close = text.IndexOf("**", i + 2, StringComparison.Ordinal);
                if (close > i)
                {
                    FlushPlain();
                    AddSegment(segments, DialogueSegmentKind.Narration, text[(i + 2)..close]);
                    i = close + 2;
                    continue;
                }
            }

            if (c == '*')
            {
                int close = FindUnescaped(text, '*', i + 1);
                if (close > i)
                {
                    FlushPlain();
                    AddSegment(segments, DialogueSegmentKind.Narration, text[(i + 1)..close]);
                    i = close + 1;
                    continue;
                }
            }

            if (c == '"')
            {
                bool opener = LooksLikeOpener(text, i);
                bool closer = LooksLikeCloser(text, i);

                if (closer && !opener)
                {
                    string spoken = plain.ToString();
                    plain.Clear();
                    AddSegment(segments, DialogueSegmentKind.Speech, spoken);
                    i++;
                    continue;
                }

                int close = FindClosingQuote(text, i + 1);
                if (close >= 0)
                {
                    FlushPlain();
                    string inner = text[(i + 1)..close];
                    var kind = IsLikelyActionProse(inner)
                        ? DialogueSegmentKind.Narration
                        : DialogueSegmentKind.Speech;
                    AddSegment(segments, kind, inner);
                    i = close + 1;
                    continue;
                }

                FlushPlain();
                SplitUnclosedQuote(text[(i + 1)..], segments);
                return;
            }

            plain.Append(c);
            i++;
        }

        FlushPlain();
    }

    private static void SplitUnclosedQuote(string rest, List<DialogueSegment> segments)
    {
        if (string.IsNullOrWhiteSpace(rest)) return;

        var sentences = SplitSentences(rest);
        var speech = new StringBuilder();
        var leftover = new List<string>();
        bool spilled = false;

        foreach (var sentence in sentences)
        {
            // Inside an unclosed quote the default is speech. Spill only when a
            // later sentence is clearly an action / attribution beat.
            bool clearlyAction = AttributionRegex.IsMatch(sentence)
                || (PhysicalVerbRegex.IsMatch(sentence) && !SpeechOpenerRegex.IsMatch(sentence));

            if (!spilled && !clearlyAction)
            {
                if (speech.Length > 0) speech.Append(' ');
                speech.Append(sentence);
            }
            else
            {
                spilled = true;
                leftover.Add(sentence);
            }
        }

        AddSegment(segments, DialogueSegmentKind.Speech, speech.ToString());
        if (leftover.Count > 0)
            ClassifyPlain(string.Join(" ", leftover), segments);
    }

    private static void ClassifyPlain(string text, List<DialogueSegment> segments)
    {
        text = CollapseWs(text);
        if (string.IsNullOrEmpty(text)) return;

        var sentences = SplitSentences(text);
        DialogueSegmentKind? current = null;
        var buf = new StringBuilder();

        foreach (var sentence in sentences)
        {
            var kind = ClassifyPlainSentence(sentence);
            if (current == null)
            {
                current = kind;
                buf.Append(sentence);
                continue;
            }

            if (kind == current)
            {
                if (buf.Length > 0) buf.Append(' ');
                buf.Append(sentence);
                continue;
            }

            AddSegment(segments, current.Value, buf.ToString());
            buf.Clear();
            current = kind;
            buf.Append(sentence);
        }

        if (current != null)
            AddSegment(segments, current.Value, buf.ToString());
    }

    private static DialogueSegmentKind ClassifyPlainSentence(string sentence)
    {
        string trimmed = sentence.Trim();
        if (trimmed.Length == 0) return DialogueSegmentKind.Narration;

        if (InternalTellRegex.IsMatch(trimmed) && !trimmed.Contains('"') && trimmed.Length < 160
            && !SpeechOpenerRegex.IsMatch(trimmed))
        {
            return DialogueSegmentKind.Somatic;
        }

        if (AttributionRegex.IsMatch(trimmed))
            return DialogueSegmentKind.Narration;

        if (PhysicalVerbRegex.IsMatch(trimmed) && !SpeechOpenerRegex.IsMatch(trimmed))
            return DialogueSegmentKind.Narration;

        if (trimmed.EndsWith('?') || trimmed.EndsWith('!'))
            return DialogueSegmentKind.Speech;

        if (SpeechOpenerRegex.IsMatch(trimmed))
            return DialogueSegmentKind.Speech;

        // Short address without a physical beat — treat as spoken
        if (trimmed.Length <= 90 && !PhysicalVerbRegex.IsMatch(trimmed))
            return DialogueSegmentKind.Speech;

        return DialogueSegmentKind.Narration;
    }

    private static bool IsLikelyActionProse(string text)
    {
        string trimmed = text.Trim();
        if (trimmed.Length == 0) return true;
        string lower = trimmed.ToLowerInvariant();
        if (lower.StartsWith("she ") || lower.StartsWith("he ") || lower.StartsWith("they "))
            return true;
        if (PhysicalVerbRegex.IsMatch(trimmed) && !SpeechOpenerRegex.IsMatch(trimmed))
            return true;
        return false;
    }

    private static bool LooksLikeOpener(string text, int quoteIndex)
    {
        char prev = quoteIndex > 0 ? text[quoteIndex - 1] : ' ';
        char next = quoteIndex + 1 < text.Length ? text[quoteIndex + 1] : '\0';
        bool prevOk = char.IsWhiteSpace(prev) || prev is '(' or '[' or '{' or '-' or '—' or ':' or ';';
        bool nextOk = next == '\0' || char.IsLetter(next) || next is '.' or '\'' or '…';
        return prevOk && nextOk;
    }

    private static bool LooksLikeCloser(string text, int quoteIndex)
    {
        char prev = quoteIndex > 0 ? text[quoteIndex - 1] : '\0';
        char next = quoteIndex + 1 < text.Length ? text[quoteIndex + 1] : ' ';
        bool prevOk = char.IsLetterOrDigit(prev) || prev is '.' or '!' or '?' or ',' or ';' or ':' or '\'' or '…';
        bool nextOk = char.IsWhiteSpace(next) || next is '.' or '!' or '?' or ',' or ';' or ')' or ']' or '}' || next == '\0';
        return prevOk && nextOk;
    }

    private static int FindClosingQuote(string text, int start)
    {
        for (int i = start; i < text.Length; i++)
        {
            if (text[i] != '"') continue;
            if (LooksLikeCloser(text, i))
                return i;
        }

        return -1;
    }

    private static int FindUnescaped(string text, char mark, int start)
    {
        int idx = text.IndexOf(mark, start);
        return idx;
    }

    private static List<string> SplitSentences(string text)
    {
        var parts = Regex.Split(text.Trim(), @"(?<=[.!?])\s+(?=[A-Z""*])")
            .Select(CollapseWs)
            .Where(s => s.Length > 0)
            .ToList();
        return parts.Count > 0 ? parts : new List<string> { CollapseWs(text) };
    }

    private static void AddSegment(List<DialogueSegment> segments, DialogueSegmentKind kind, string text)
    {
        text = CollapseWs(text).Trim('"', ' ');
        if (string.IsNullOrWhiteSpace(text)) return;
        segments.Add(new DialogueSegment(kind, text));
    }

    private static void MergeAdjacent(List<DialogueSegment> segments)
    {
        if (segments.Count < 2) return;
        for (int i = 1; i < segments.Count; )
        {
            if (segments[i].Kind == segments[i - 1].Kind)
            {
                segments[i - 1] = new DialogueSegment(
                    segments[i].Kind,
                    CollapseWs(segments[i - 1].Text + " " + segments[i].Text));
                segments.RemoveAt(i);
            }
            else
            {
                i++;
            }
        }
    }

    private static string NormalizeQuotes(string text)
    {
        return text
            .Replace('“', '"').Replace('”', '"')
            .Replace('„', '"').Replace('«', '"').Replace('»', '"')
            .Replace('‘', '\'').Replace('’', '\'');
    }

    private static string CollapseWs(string text) =>
        Regex.Replace(text ?? "", @"[ \t]+", " ").Trim();
}

public sealed class DialogueParseResult
{
    public List<string> SomaticTells { get; } = new();
    public List<DialogueSegment> Segments { get; } = new();
    public string CanonicalDialogue { get; set; } = "";

    public string SomaticText => DialogueSegmentParser.FormatSomaticForDisplay(SomaticTells);

    internal void RebuildCanonical()
    {
        var parts = new List<string>();
        foreach (var seg in Segments)
        {
            if (seg.Kind == DialogueSegmentKind.Somatic) continue;
            if (string.IsNullOrWhiteSpace(seg.Text)) continue;
            parts.Add(seg.Kind == DialogueSegmentKind.Speech ? $"\"{seg.Text}\"" : seg.Text);
        }

        CanonicalDialogue = string.Join(" ", parts).Trim();
    }
}
