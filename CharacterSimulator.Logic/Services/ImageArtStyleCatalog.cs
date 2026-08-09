using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// Shared art-style presets for portrait + scene image generation.
/// Id is persisted in <see cref="AppSettings.ImageArtStyle"/>.
/// </summary>
public static class ImageArtStyleCatalog
{
    public const string DefaultStyleId = "anime";

    public sealed record ArtStyle(
        string Id,
        string DisplayName,
        string Description,
        /// <summary>Short cue appended/merged into portrait prompts.</summary>
        string PortraitCue,
        /// <summary>Short cue for environment / wide shots.</summary>
        string SceneCue);

    private static readonly ArtStyle[] Styles =
    {
        new(
            "anime",
            "Anime",
            "Clean anime / cel-shaded illustration",
            "anime style character portrait, clean linework, soft cel shading, expressive eyes, high quality illustration",
            "anime style environment art, clean linework, soft cel shading, cinematic lighting, high quality illustration"),
        new(
            "semi_realistic",
            "Semi-realistic",
            "Stylized realism — painterly faces, soft detail",
            "semi-realistic digital portrait, soft painterly detail, natural proportions, high quality character art",
            "semi-realistic digital environment, painterly detail, natural lighting, cinematic composition"),
        new(
            "photoreal",
            "Photoreal",
            "Photo-like realism",
            "photorealistic portrait photo, natural skin texture, sharp focus, cinematic lighting, 85mm lens",
            "photorealistic location photo, natural light, depth of field, cinematic wide shot"),
        new(
            "watercolor",
            "Watercolor",
            "Soft watercolor wash",
            "watercolor portrait illustration, soft washes, paper texture, delicate edges, artistic",
            "watercolor landscape illustration, soft washes, paper texture, atmospheric"),
        new(
            "comic",
            "Comic / Ink",
            "Western comic ink & color",
            "western comic book portrait, bold ink outlines, flat color, dramatic shading",
            "western comic book environment panel, bold ink outlines, dynamic composition"),
        new(
            "oil",
            "Oil painting",
            "Classical oil portrait feel",
            "oil painting portrait, rich brushwork, classical lighting, fine art canvas",
            "oil painting landscape, rich brushwork, classical composition, fine art"),
        new(
            "pixel",
            "Pixel art",
            "Retro pixel sprite style",
            "pixel art character portrait, limited palette, clean pixels, 16-bit aesthetic",
            "pixel art environment scene, limited palette, clean pixels, 16-bit game background"),
        new(
            "3d_render",
            "3D Render",
            "Modern CGI / game render",
            "3D rendered character portrait, subsurface scattering, studio lighting, game-cinematic quality",
            "3D rendered environment, cinematic lighting, game-quality scenery"),
    };

    public static IReadOnlyList<ArtStyle> All => Styles;

    public static ArtStyle GetById(string? id)
    {
        if (string.IsNullOrWhiteSpace(id))
            return Styles[0];
        return Styles.FirstOrDefault(s => s.Id.Equals(id.Trim(), StringComparison.OrdinalIgnoreCase))
               ?? Styles[0];
    }

    /// <summary>
    /// Merge subject appearance with art style for a character portrait.
    /// <b>Appearance comes first</b> — URL-based generators (Pollinations/Flux) weight early
    /// tokens heavily; burying physical description after a long style preamble causes drift.
    /// </summary>
    public static string ApplyPortraitStyle(string? prompt, string? artStyleId)
    {
        var style = GetById(artStyleId);
        string p = SanitizeAppearancePrompt(prompt);
        if (string.IsNullOrEmpty(p))
            return $"solo character portrait, centered, {style.PortraitCue}, no text, no watermark";

        // Already fully assembled
        if (p.Contains(style.PortraitCue, StringComparison.OrdinalIgnoreCase) &&
            p.Contains("portrait", StringComparison.OrdinalIgnoreCase))
            return p;

        // Appearance-first binding (do not lead with style-only cues)
        return $"solo character portrait of this exact person: {p}. " +
               $"Match hair, eyes, skin, face, build, and clothing from the description. " +
               $"Single character only. Art style: {style.PortraitCue}. " +
               "No text, no watermark, no extra people.";
    }

    /// <summary>
    /// Build the subject string for portrait gen from card fields (physical + dress only).
    /// </summary>
    public static string BuildPortraitSubject(string? name, string? physical, string? characterStyle)
    {
        var parts = new List<string>();
        if (!string.IsNullOrWhiteSpace(name) &&
            !name.Contains("No Character", StringComparison.OrdinalIgnoreCase) &&
            !name.Contains("Unknown", StringComparison.OrdinalIgnoreCase))
        {
            parts.Add(name.Trim());
        }

        string body = SanitizeAppearancePrompt(physical);
        if (!string.IsNullOrEmpty(body))
            parts.Add(body);

        string dress = SanitizeAppearancePrompt(characterStyle);
        if (!string.IsNullOrEmpty(dress))
            parts.Add("wearing " + dress);

        return string.Join(", ", parts);
    }

    /// <summary>Strip noise that dilutes image-gen prompts (system labels, personality leaks).</summary>
    public static string SanitizeAppearancePrompt(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "";
        string p = raw.Trim();
        // Collapse whitespace / newlines into commas for URL models
        p = System.Text.RegularExpressions.Regex.Replace(p, @"[\r\n]+", ", ");
        p = System.Text.RegularExpressions.Regex.Replace(p, @"\s{2,}", " ");
        p = System.Text.RegularExpressions.Regex.Replace(p, @",\s*,+", ", ");
        return p.Trim(' ', ',', ';');
    }

    /// <summary>
    /// Combined stage still: character physical (required when present) + scene place.
    /// Appearance is early in the prompt so Pollinations/Flux honor body details.
    /// </summary>
    public static string BuildScenePrompt(
        string? scenePlaceOrContext,
        string? characterName,
        string? characterDescription,
        string? characterPhysical,
        string? artStyleId)
    {
        var style = GetById(artStyleId);
        string place = string.IsNullOrWhiteSpace(scenePlaceOrContext)
            ? "Quiet interior room, soft ambient light"
            : scenePlaceOrContext.Trim();
        place = Truncate(place, 240);

        string appearance = FirstNonEmpty(characterPhysical, characterDescription);
        appearance = string.IsNullOrWhiteSpace(appearance) ? "" : Truncate(SanitizeAppearancePrompt(appearance), 320);

        var sb = new StringBuilder();

        if (!string.IsNullOrWhiteSpace(appearance))
        {
            string who = string.IsNullOrWhiteSpace(characterName) ? "the character" : characterName.Trim();
            // Character first — combined stage image is person-in-place, not empty environment.
            sb.Append("Cinematic full-body shot of ");
            sb.Append(who);
            sb.Append(" (");
            sb.Append(appearance);
            sb.Append("), standing or present in this location: ");
            sb.Append(place);
            sb.Append(". Match the character's hair, eyes, skin, face, build, and clothing exactly. ");
            sb.Append("Same person, coherent lighting with the environment. ");
        }
        else
        {
            sb.Append("Cinematic environment establishing shot of: ");
            sb.Append(place);
            sb.Append(". Atmospheric location, no people unless implied. ");
        }

        sb.Append("Art style: ");
        sb.Append(style.SceneCue);
        sb.Append(". No text, no watermark, no UI, no logo.");

        return sb.ToString();
    }

    private static string? FirstNonEmpty(params string?[] parts)
    {
        foreach (var p in parts)
        {
            if (!string.IsNullOrWhiteSpace(p))
                return p.Trim();
        }
        return null;
    }

    private static string Truncate(string text, int max)
    {
        if (string.IsNullOrEmpty(text) || text.Length <= max) return text;
        return text[..(max - 1)].TrimEnd() + "…";
    }
}
