using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace CharacterSimulator.Logic.Hygiene;

public class LeakFinding
{
    public string Type { get; set; } = "System Leak";
    public string Category { get; set; } = string.Empty;
    public string Match { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
}

public class LinterResult
{
    public bool HasCriticalLeaks => Findings.Count > 0;
    public List<LeakFinding> Findings { get; } = new();
    public string SanitizedDialogue { get; set; } = string.Empty;
}

public static class SystemLeakLinter
{
    private record LeakPattern(Regex Regex, string Category, string Description);

    private static readonly List<LeakPattern> Patterns = new()
    {
        new(new Regex(@"\bRealm (I|II|III|IV|V|VI|VII|VIII|IX|X|\d+)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Realm [N] references on-page"),
        new(new Regex(@"\bFocus Lock\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Focus Lock status leak"),
        new(new Regex(@"\bBias State\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Bias State status leak"),
        new(new Regex(@"\btransformation_weights\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "transformation_weights leak"),
        new(new Regex(@"\btransformation_history\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "transformation_history leak"),
        new(new Regex(@"\bPrism Distortion\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Prism Distortion engine reference"),
        new(new Regex(@"\bGenerative Prism\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Generative Prism engine reference"),
        new(new Regex(@"\bGreat Wheel\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Framework Jargon", "Great Wheel reference"),
        new(new Regex(@"\b(trauma|reframe|coping mechanism|emotional wound|active wound|psychological wound|emotional trigger|psychological trigger|wound trigger|cognitive gift|sacred anchor|virtue lens|self-actualiz\w+|empowerment|safe space|healing journey)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Psychological Labels (Therapy Speak)", "Psychological/therapy labels"),
        new(new Regex(@"\bDebt Ledger\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Debt Ledger bias name leak"),
        new(new Regex(@"\bSaviour Complex\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Saviour Complex bias name leak"),
        new(new Regex(@"\bSystem Architect\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "System Architect bias name leak"),
        new(new Regex(@"\bMirror (bias|reflector)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Mirror bias name leak"),
        new(new Regex(@"\bInsulation (Bias|Lens|Engine)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Insulation bias name leak"),
        new(new Regex(@"\bDissolution (Bias|Lens|Engine)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Dissolution bias name leak"),
        new(new Regex(@"\bSacred Stewardship\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Sacred Stewardship gift name leak"),
        new(new Regex(@"\bTrue Sanctuary\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "True Sanctuary gift name leak"),
        new(new Regex(@"\bIlluminated Symmetry\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Illuminated Symmetry gift name leak"),
        new(new Regex(@"\bResonant Truth\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Resonant Truth gift name leak"),
        new(new Regex(@"\bSanctuary Bridge\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Sanctuary Bridge gift name leak"),
        new(new Regex(@"\bThreshold Vision\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Engine Bias & Gift Names", "Threshold Vision gift name leak"),
        new(new Regex(@"\b(look up|database|search the web|search web|as an AI|my database|retriev\w+ records|external search)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Out-of-Character Lookup / Temporal Leaks", "Out-of-character AI lookup / temporal leak"),
        new(new Regex(@"\b(it'?s important to remember|to be fair|let'?s look at this|while that is a common|actually, from a|safety guidelines?|safety protocols?|respectful conversation|inappropriate content|moral perspective|ethical considerations?|cannot fulfill this request)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "AI Safety / Preachy Tone Leaks", "AI safety tone / preachiness leak"),
        new(new Regex(@"\b(?:how can I help(?: you)?(?: today)?|what would you like me to (?:do|help with)|is there anything else I can (?:help with|do)(?: for you)?|let me know if you need anything)\b", RegexOptions.IgnoreCase | RegexOptions.Compiled), "Assistant Register", "Passive assistant / helpdesk register"),
    };

    public static LinterResult Audit(string text)
    {
        var result = new LinterResult { SanitizedDialogue = text ?? string.Empty };
        if (string.IsNullOrWhiteSpace(text)) return result;

        string currentText = text;
        foreach (var pattern in Patterns)
        {
            var matches = pattern.Regex.Matches(currentText);
            foreach (Match match in matches)
            {
                result.Findings.Add(new LeakFinding
                {
                    Category = pattern.Category,
                    Match = match.Value,
                    Message = pattern.Description
                });
            }

            // Strip framework jargon, engine terms, AI safety preachiness, and OOC leaks (preserve natural dialogue words)
            if (pattern.Category != "Psychological Labels (Therapy Speak)" && matches.Count > 0)
            {
                currentText = pattern.Regex.Replace(currentText, "").Trim();
            }
        }

        result.SanitizedDialogue = currentText;
        return result;
    }
}
