using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic;

/// <summary>
/// Offline stand-in that answers from the loaded character card.
/// Does not hardcode cyberpunk (or any scene genre) identity by name.
/// </summary>
public class MockLLMClient : ILLMClient
{
    private static readonly Random _rng = new();

    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "", string? conversationHistory = null)
    {
        if (character == null) throw new ArgumentNullException(nameof(character));
        
        // History is host-owned; mock still keys off the latest stimulus only.
        _ = conversationHistory;
        string inputLower = (input ?? "").ToLowerInvariant();
        string appearanceCue = FirstAppearanceCue(character);
        string voiceHint = character.Attributes?.GetValueOrDefault("voice", "") ?? "";
        string bioSnippet = FirstSentence(character.Bio);
        string sceneNote = string.IsNullOrWhiteSpace(sceneContext)
            ? "this place"
            : sceneContext.Split(',')[0].Trim();

        string somatic;
        string dialogue;
        int bondDelta;
        string goalStatus;

        var activeGoal = character.Goals
            .Where(g => g.CooldownRemaining == 0)
            .OrderByDescending(g => g.Priority)
            .FirstOrDefault();

        if (inputLower.Contains("who are you") || inputLower.Contains("your name") || inputLower.Contains("about yourself"))
        {
            somatic = appearanceCue;
            dialogue = string.IsNullOrWhiteSpace(bioSnippet)
                ? $"I'm {character.Name}. That's enough for now."
                : $"{bioSnippet} I'm {character.Name}.";
            bondDelta = 1;
            goalStatus = "Neutral: Self-description from card.";
        }
        else if (inputLower.Contains("where") || inputLower.Contains("place") || inputLower.Contains("here"))
        {
            somatic = appearanceCue;
            dialogue = $"We're in {sceneNote}. I am still who I am — that doesn't change with the room.";
            bondDelta = 1;
            goalStatus = "Neutral: Scene acknowledged, identity held.";
        }
        else if (activeGoal != null && (inputLower.Contains("goal") || inputLower.Contains(activeGoal.Type.ToLowerInvariant())
                 || activeGoal.Strategies.Any(s => inputLower.Contains(s.ToLowerInvariant()))))
        {
            string strategy = activeGoal.Strategies.FirstOrDefault() ?? "directness";
            somatic = appearanceCue;
            dialogue = $"Regarding {activeGoal.Type.ToLowerInvariant()}… I lean on {strategy.ToLowerInvariant()}. That is mine to own, not the scenery.";
            bondDelta = 2;
            goalStatus = $"Advanced: {activeGoal.Type} via {strategy}.";
        }
        else if (inputLower.Contains("help") || inputLower.Contains("please") || inputLower.Contains("need"))
        {
            somatic = appearanceCue;
            dialogue = PickLine(character, new[]
            {
                "Ask clearly. I answer as myself — not as whatever this setting expects.",
                "I'll help if it fits who I am. Don't rewrite me for convenience.",
                "State what you need. My answer will sound like me."
            });
            bondDelta = 2;
            goalStatus = "Neutral: Offer filtered through identity.";
        }
        else if (inputLower.Contains("flirt") || inputLower.Contains("beautiful") || inputLower.Contains("love") || inputLower.Contains("kiss"))
        {
            somatic = appearanceCue;
            dialogue = PickLine(character, new[]
            {
                "Careful. Charm doesn't get to edit who I am.",
                "I heard that. My reaction is mine — not a scene costume.",
                "Flattery noted. I stay myself either way."
            });
            bondDelta = 1;
            goalStatus = "Resisted: Identity held under pressure.";
        }
        else
        {
            somatic = appearanceCue;
            dialogue = BuildDefaultDialogue(character, sceneNote, voiceHint, bioSnippet);
            bondDelta = 1;
            goalStatus = activeGoal != null
                ? $"Neutral: Holding goal {activeGoal.Type}."
                : "Neutral: In-character beat.";
        }

        // Soft-apply hard bans: if mock line violates a known ban keyword, fall back
        if (character.Attributes?.TryGetValue("hard_bans", out var bans) == true && !string.IsNullOrWhiteSpace(bans))
        {
            // Mock lines are written to be generic; no action needed beyond not inventing banned registers.
            _ = bans;
        }

        string bondSign = bondDelta >= 0 ? "+" : "";
        return $"[Somatic: {somatic}] {dialogue} bond {bondSign}{bondDelta} [Goal: {goalStatus}]";
    }

    private static string BuildDefaultDialogue(Character character, string sceneNote, string voiceHint, string bioSnippet)
    {
        if (!string.IsNullOrWhiteSpace(voiceHint))
        {
            return PickLine(character, new[]
            {
                $"({character.Name}, in my own voice.) I take in {sceneNote}, but I don't become it. What do you want from me?",
                $"Still {character.Name}. {sceneNote} is only where we stand. Go on.",
                string.IsNullOrWhiteSpace(bioSnippet)
                    ? $"I remain myself here in {sceneNote}. Speak."
                    : $"{bioSnippet.TrimEnd('.')} — and that holds even here in {sceneNote}."
            });
        }

        return PickLine(character, new[]
        {
            $"I'm {character.Name}. {sceneNote} is just where we are.",
            string.IsNullOrWhiteSpace(bioSnippet)
                ? $"I hear you. I answer as {character.Name}, not as this place."
                : $"{bioSnippet.TrimEnd('.')}. That doesn't change because of {sceneNote}.",
            $"Look at me, not the backdrop. What are you really asking?"
        });
    }

    private static string FirstAppearanceCue(Character character)
    {
        if (character.SomaticZones.Count > 0)
        {
            string zone = character.SomaticZones[_rng.Next(character.SomaticZones.Count)];
            // If zone is a long card description, take a short lead-in
            if (zone.Length > 80) zone = zone.Split(':')[0].Trim() + " shifts slightly";
            return zone;
        }

        if (character.Attributes.TryGetValue("signature_tics", out var tics) && !string.IsNullOrWhiteSpace(tics))
            return tics.Split(';')[0].Trim();

        if (character.Attributes.TryGetValue("clothing", out var clothing) && !string.IsNullOrWhiteSpace(clothing))
            return $"adjusts {clothing.Split(',')[0].Trim().ToLowerInvariant()}";

        return "holds still, present as themselves";
    }

    private static string FirstSentence(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return "";
        // Prefer first non-empty line (JSON bios are multi-field)
        string line = text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .FirstOrDefault() ?? text.Trim();
        if (line.Length > 160) return line.Substring(0, 157).Trim() + "…";
        return line;
    }

    private static string PickLine(Character character, string[] lines)
    {
        // Stable-ish variety without coupling to scene genre
        int idx = Math.Abs((character.Name + character.Bond).GetHashCode() + _rng.Next(lines.Length * 3)) % lines.Length;
        return lines[idx];
    }
    
    public Task<string> SendPromptAsync(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        CancellationToken ct = default,
        string? conversationHistory = null)
    {
        // Mock client is synchronous and fast, so just return completed task
        return Task.FromResult(SendPrompt(character, input, sceneContext, goalContext, conversationHistory));
    }

    public Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        // Offline derive-card scaffold: extract a target name if present, emit valid pack JSON.
        string name = "Derived Character";
        if (!string.IsNullOrWhiteSpace(prompt))
        {
            // Prefer "TARGET CHARACTER NAME: X" from DeriveCardService prompts
            var lines = prompt.Split('\n');
            foreach (var line in lines)
            {
                var t = line.Trim();
                if (t.StartsWith("TARGET CHARACTER NAME:", StringComparison.OrdinalIgnoreCase))
                {
                    name = t["TARGET CHARACTER NAME:".Length..].Trim();
                    if (!string.IsNullOrWhiteSpace(name)) break;
                }
            }
        }

        string json = $$"""
            {
              "accuracy_summary": {
                "sources": ["mock offline derive (no network)"],
                "kept": ["name", "playable skeleton"],
                "compressed": [],
                "left_blank": ["canon detail — replace via re-derive with real LLM + source"]
              },
              "card": {
                "name": "{{name.Replace("\"", "'")}}",
                "call_name": "{{name.Replace("\"", "'")}}",
                "age": 25,
                "canon_adult": true,
                "physical": "Appearance not locked — mock derive without canon fetch.",
                "character_style": "unknown",
                "personality": "unknown — source not available in mock mode",
                "behavior": "unknown — source not available in mock mode",
                "hobbies": ["unknown"],
                "voice_archetype": "B",
                "cultural_bias": "unknown",
                "active_focus": "Realm I — Form",
                "latent_anchors": ["Realm VI — Compassion", "Realm VIII — Ambition"],
                "cognitive_bias": "Guard — holds surface composure when uncertain",
                "cognitive_gift": "Presence — steadies when trust is clear",
                "default_somatic_alignment": "Even breath; hands still",
                "somatic_zones": [
                  "Face/Eyes: steady gaze",
                  "Chest/Breath: controlled rhythm",
                  "Hands/Arms: quiet",
                  "Spine/Posture: upright"
                ],
                "transformation_weights": {
                  "active_focus": 70,
                  "latent_anchors": { "VI": 15, "VIII": 15 },
                  "bias_strength": 55,
                  "somatic_flexibility": 40
                },
                "depth_of_knowledge": {
                  "general": "unknown",
                  "esoteric": "unknown",
                  "personal": "unknown"
                },
                "voice": {
                  "baseline": "Clear, measured",
                  "syntactical_engine": "Short direct sentences",
                  "conversational_stance": "collaborative",
                  "verbal_defense": "deflects with brevity",
                  "generative_stance": "opens slightly when safe",
                  "hard_bans": ["system jargon", "therapy-speak labels"],
                  "signature_tics": ["brief pause before answering"],
                  "relational_verbal_shifts": {}
                },
                "history_anchors": [
                  "unknown — source not available in mock mode"
                ],
                "scene_seeds": [
                  "Quiet room; first meeting; neutral object between them"
                ]
              }
            }
            """;

        return Task.FromResult(json);
    }
}
