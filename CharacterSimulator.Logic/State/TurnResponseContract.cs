using System;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CharacterSimulator.Logic.State;

public class TurnMetaSnapshot
{
    public string Emotion { get; set; } = "Neutral";
    public int BondDelta { get; set; } = 0;
    public string SomaticState { get; set; } = "Calm";
    public string Focus { get; set; } = "";
    public string NarrativeTone { get; set; } = "Standard";
    public string ParseMethod { get; set; } = "BalancedBrace";
}

public static class TurnResponseContract
{
    /// <summary>
    /// Extract structured live state metadata JSON block from model turn response without relying on fragile regexes.
    /// </summary>
    public static TurnMetaSnapshot ExtractTurnSnapshot(string rawResponse, string speakerName)
    {
        var snapshot = new TurnMetaSnapshot();

        // 1. Try PsychosomaticStateValidator balanced brace extraction first
        string json = PsychosomaticStateValidator.ExtractStateJson(rawResponse) ?? "";
        if (!string.IsNullOrWhiteSpace(json) && json != "{}")
        {
            try
            {
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;

                if (root.TryGetProperty("emotion", out var emProp))
                    snapshot.Emotion = emProp.GetString() ?? snapshot.Emotion;
                else if (root.TryGetProperty("speaker_emotion", out var emProp2))
                    snapshot.Emotion = emProp2.GetString() ?? snapshot.Emotion;

                if (root.TryGetProperty("bond_delta", out var bdProp) && bdProp.TryGetInt32(out int bd))
                    snapshot.BondDelta = bd;

                if (root.TryGetProperty("somatic_state", out var somProp))
                    snapshot.SomaticState = somProp.GetString() ?? snapshot.SomaticState;

                if (root.TryGetProperty("focus", out var focProp))
                    snapshot.Focus = focProp.GetString() ?? snapshot.Focus;
            }
            catch
            {
                snapshot.ParseMethod = "FallbackExtraction";
            }
        }

        // 2. Derive emotion from parenthetical actions if unpopulated
        if (snapshot.Emotion == "Neutral")
        {
            var match = Regex.Match(rawResponse, @"\*([^*]{3,30})\*");
            if (match.Success)
            {
                snapshot.Emotion = match.Groups[1].Value.Trim();
            }
        }

        return snapshot;
    }

    public static string SerializeMetaJson(TurnMetaSnapshot snapshot)
    {
        return JsonSerializer.Serialize(snapshot);
    }
}
