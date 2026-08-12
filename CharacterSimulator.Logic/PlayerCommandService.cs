using System;
using System.Collections.Generic;
using System.Linq;

namespace CharacterSimulator.Logic;

public enum PlayerCommandKind
{
    Unknown,
    Help,
    Play,
    Pause,
    Step,
    Stop,
    Reset,
    Save,
    Load,
    Setup,
    Status,
    State,
    Clear,
    Scene,
    Genre,
    Adult,
}

public sealed class PlayerCommand
{
    public PlayerCommandKind Kind { get; init; }
    public string RawName { get; init; } = string.Empty;
    public string[] Args { get; init; } = Array.Empty<string>();
    public string RawText { get; init; } = string.Empty;
}

public static class PlayerCommandService
{
    private static readonly Dictionary<string, PlayerCommandKind> Aliases = new(StringComparer.OrdinalIgnoreCase)
    {
        ["help"] = PlayerCommandKind.Help,
        ["h"] = PlayerCommandKind.Help,
        ["?"] = PlayerCommandKind.Help,
        ["play"] = PlayerCommandKind.Play,
        ["start"] = PlayerCommandKind.Play,
        ["resume"] = PlayerCommandKind.Play,
        ["pause"] = PlayerCommandKind.Pause,
        ["step"] = PlayerCommandKind.Step,
        ["next"] = PlayerCommandKind.Step,
        ["stop"] = PlayerCommandKind.Stop,
        ["reset"] = PlayerCommandKind.Reset,
        ["save"] = PlayerCommandKind.Save,
        ["load"] = PlayerCommandKind.Load,
        ["setup"] = PlayerCommandKind.Setup,
        ["config"] = PlayerCommandKind.Setup,
        ["status"] = PlayerCommandKind.Status,
        ["state"] = PlayerCommandKind.State,
        ["clear"] = PlayerCommandKind.Clear,
        ["scene"] = PlayerCommandKind.Scene,
        ["genre"] = PlayerCommandKind.Genre,
        ["tone"] = PlayerCommandKind.Genre,
        ["adult"] = PlayerCommandKind.Adult,
    };

    /// <summary>
    /// True when the line is a slash command (system control), not in-character dialogue.
    /// </summary>
    public static bool IsCommand(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return false;
        string t = text.Trim();
        return t.StartsWith('/') || t.StartsWith('\\');
    }

    public static PlayerCommand Parse(string text)
    {
        string raw = text.Trim();
        // Allow \help as well as /help
        if (raw.StartsWith('\\')) raw = "/" + raw.Substring(1);
        if (!raw.StartsWith('/'))
        {
            return new PlayerCommand
            {
                Kind = PlayerCommandKind.Unknown,
                RawText = text,
            };
        }

        string body = raw.Substring(1).Trim();
        if (string.IsNullOrEmpty(body))
        {
            return new PlayerCommand
            {
                Kind = PlayerCommandKind.Help,
                RawName = "",
                RawText = text,
            };
        }

        var parts = SplitArgs(body);
        string name = parts[0];
        string[] args = parts.Skip(1).ToArray();

        var kind = Aliases.TryGetValue(name, out var mapped)
            ? mapped
            : PlayerCommandKind.Unknown;

        return new PlayerCommand
        {
            Kind = kind,
            RawName = name,
            Args = args,
            RawText = text.Trim(),
        };
    }

    public static string GetHelpText()
    {
        return string.Join("\n", new[]
        {
            "Slash commands control the simulator. They are NOT sent to characters.",
            "",
            "  /help              Show this list",
            "  /play              Start or resume simulation",
            "  /pause             Pause between turns",
            "  /step              Advance one turn (or start paused)",
            "  /stop              Stop the active simulation",
            "  /reset             Clear stage and stop",
            "  /save              Save current session",
            "  /load              Load most recent session",
            "  /setup             Open simulation setup",
            "  /status            Show playback / mode status",
            "  /state             Inspect character OOC psych/somatic state & durable log",
            "  /scene <text>      Set scene place/detail (not dialogue)",
            "  /genre <name>      Set scene genre/environment tone only",
            "  /clear             Clear the dialogue feed",
            "  /adult on|off      Toggle user adult content attestation",
            "",
            "Anything that does not start with / is treated as player dialogue.",
        });
    }

    public static string BuildCharacterStateReport(Character character)
    {
        if (character == null) return "No active character.";

        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"=== OOC PSYCHOSOMATIC & DURABLE STATE: {character.Name} ===");
        sb.AppendLine($"Active Focus / Realm: {character.ActiveFocus}");
        sb.AppendLine($"Bias State: {character.BiasState} | Bias Strength: {character.BiasStrength}/100");
        sb.AppendLine($"Autonomic Scales: Stress={character.Stress}, Arousal={character.Arousal}, Fatigue={character.Fatigue}, Pain={character.Pain}");
        sb.AppendLine($"Safety Eligibility: CanonAdult={character.CanonAdult}, Age={character.Age}, AdultAuthorized={Safety.AdultAuth.IsAdultPathAuthorized(character)}");

        var realm = Somatics.RealmDataCatalog.GetRealm(character.ActiveFocus);
        if (realm != null)
        {
            sb.AppendLine($"Realm Data ({realm.name}): Zone='{realm.zone}', Micro=[{string.Join(", ", realm.micro.Take(3))}]");
        }

        if (character.DurableLog != null)
        {
            sb.AppendLine($"Durable Log: File='{character.LogPath}', AsOf='{character.DurableLog.snapshot.as_of}', HistoryEntries={character.DurableLog.history.Count}");
        }
        else
        {
            sb.AppendLine($"Durable Log Path: {character.LogPath ?? "(none)"}");
        }

        if (character.SomaticZones.Count > 0)
        {
            sb.AppendLine($"Active Somatic Zones: {string.Join(", ", character.SomaticZones)}");
        }

        return sb.ToString().TrimEnd();
    }

    private static List<string> SplitArgs(string body)
    {
        var parts = new List<string>();
        // First token is command; remainder is one optional freeform arg for /scene etc.
        int space = body.IndexOf(' ');
        if (space < 0)
        {
            parts.Add(body);
            return parts;
        }

        parts.Add(body.Substring(0, space));
        string rest = body.Substring(space + 1).Trim();
        if (rest.Length > 0)
            parts.Add(rest);
        return parts;
    }
}
