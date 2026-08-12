using System;
using System.Text.RegularExpressions;
using CharacterSimulator.Logic.Data.Db;

namespace CharacterSimulator.Logic.Safety;

public static class DepictionController
{
    public const string ModeSfw = "SFW";
    public const string ModeFadeToBlack = "FadeToBlack";
    public const string ModeExplicit = "Explicit";

    /// <summary>
    /// Validates and normalizes requested depiction mode against player age and adult gate.
    /// Under-18 profiles or non-adult attested users can never use Explicit mode.
    /// </summary>
    public static string NormalizeDepictionMode(UserProfile? profile, string requestedMode)
    {
        if (profile == null) return ModeSfw;

        bool adultEligible = profile.IsAdultEligible() && profile.IsAdultAttested && AdultAuth.IsUserAdultAttested;
        if (!adultEligible)
        {
            return ModeSfw;
        }

        return requestedMode switch
        {
            ModeSfw => ModeSfw,
            ModeFadeToBlack => ModeFadeToBlack,
            ModeExplicit => ModeExplicit,
            _ => ModeExplicit
        };
    }

    /// <summary>
    /// Applies presentation level filters without modifying character consent or underlying choices.
    /// </summary>
    public static string ApplyDepictionFilter(string text, string depictionMode)
    {
        if (string.IsNullOrWhiteSpace(text)) return text;

        if (string.Equals(depictionMode, ModeSfw, StringComparison.OrdinalIgnoreCase))
        {
            // SFW: sanitize explicit markers and replace intimate scenes with non-intimate prose summary
            string filtered = Regex.Replace(text, @"(?i)\b(nsfw|explicit|erotic|sex)\b", "[non-intimate]");
            return filtered;
        }

        if (string.Equals(depictionMode, ModeFadeToBlack, StringComparison.OrdinalIgnoreCase))
        {
            // Fade-to-black: append cinematic transition when intimate escalation is detected
            if (Regex.IsMatch(text, @"(?i)\b(intimate|embrace|kiss|sensual|undress)\b"))
            {
                if (!text.Contains("[Scene fades to black...]"))
                {
                    return text.TrimEnd() + "\n\n*[The scene fades to black as the moment deepens...]*";
                }
            }
        }

        return text;
    }
}
