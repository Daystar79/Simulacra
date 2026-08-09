using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CharacterSimulator.Logic;

/// <summary>
/// Builds LLM prompts with a hard split:
/// - Identity (who they are) comes only from the character card and never changes with location.
/// - Scene is where/when the exchange happens; it may affect awareness, not personality or voice.
/// </summary>
public static class PromptBuilder
{
    public static string BuildAppearanceSummary(Character character)
    {
        if (!string.IsNullOrWhiteSpace(character.PhysicalDescription))
            return character.PhysicalDescription.Trim();

        var attrs = character.Attributes;
        if (attrs.TryGetValue("physical", out var physical) && !string.IsNullOrWhiteSpace(physical)
            && !attrs.ContainsKey("hair") && !attrs.ContainsKey("eyes"))
        {
            return physical.Trim();
        }

        var parts = new List<string>();
        // Body only — never clothing (that is CharacterStyle)
        foreach (var key in new[] { "height", "build", "body_details", "hair", "eyes", "skin", "face", "defining_features", "distinguishing_features", "posture_movement" })
        {
            if (attrs.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value))
                parts.Add(value);
        }

        if (parts.Count == 0 && attrs.TryGetValue("physical", out var fallback) && !string.IsNullOrWhiteSpace(fallback))
            return fallback.Trim();

        return parts.Count > 0 ? string.Join("; ", parts) : "As described in your character identity.";
    }

    public static string BuildIdentityBlock(Character character)
    {
        var sb = new StringBuilder();
        sb.AppendLine("CHARACTER IDENTITY (immutable — this is who you are in every scene):");
        sb.AppendLine("Name: " + character.Name);

        if (!string.IsNullOrWhiteSpace(character.Personality))
            sb.AppendLine("Personality (who you are): " + character.Personality.Trim());

        if (!string.IsNullOrWhiteSpace(character.Behavior))
            sb.AppendLine("Behavior (how you act): " + character.Behavior.Trim());

        if (!string.IsNullOrWhiteSpace(character.Bio))
            sb.AppendLine("Background & knowledge: " + character.Bio.Trim());

        if (!string.IsNullOrWhiteSpace(character.CognitiveBias))
            sb.AppendLine("Cognitive Wound (Defensive Lens): " + character.CognitiveBias.Trim());

        if (!string.IsNullOrWhiteSpace(character.CognitiveGift))
            sb.AppendLine("Cognitive Gift (Generative Lens): " + character.CognitiveGift.Trim());

        if (!string.IsNullOrWhiteSpace(character.CulturalBias))
            sb.AppendLine("Cultural & Background Bias: " + character.CulturalBias.Trim());

        string appearance = BuildAppearanceSummary(character);
        sb.AppendLine("Physical Appearance (body only): " + appearance);

        if (!string.IsNullOrWhiteSpace(character.CharacterStyle))
            sb.AppendLine("Default dress / style: " + character.CharacterStyle.Trim());
        else if (character.Attributes.TryGetValue("character_style", out var styleAttr) && !string.IsNullOrWhiteSpace(styleAttr))
            sb.AppendLine("Default dress / style: " + styleAttr.Trim());

        if (character.Attributes.TryGetValue("voice", out var voice) && !string.IsNullOrWhiteSpace(voice))
            sb.AppendLine("Voice: " + voice.Trim());

        if (!string.IsNullOrWhiteSpace(character.VoiceSyntacticalEngine))
            sb.AppendLine("Syntactical Engine: " + character.VoiceSyntacticalEngine.Trim());

        if (!string.IsNullOrWhiteSpace(character.ConversationalStance))
            sb.AppendLine("Conversational Stance: " + character.ConversationalStance.Trim());

        if (!string.IsNullOrWhiteSpace(character.VerbalDefense))
            sb.AppendLine("Verbal Defense (Defensive Stance): " + character.VerbalDefense.Trim());

        if (!string.IsNullOrWhiteSpace(character.GenerativeStance))
            sb.AppendLine("Generative Stance (Trust Stance): " + character.GenerativeStance.Trim());

        if (character.LatentAnchors.Count > 0)
            sb.AppendLine("Latent Anchors / Subconscious Realms: " + string.Join("; ", character.LatentAnchors));

        if (character.Attributes.TryGetValue("relational_verbal_shifts", out var shifts) && !string.IsNullOrWhiteSpace(shifts))
            sb.AppendLine("Relational Verbal Shifts: " + shifts.Trim());

        if (character.Attributes.TryGetValue("hard_bans", out var bans) && !string.IsNullOrWhiteSpace(bans))
            sb.AppendLine("Never do/say: " + bans.Trim());

        if (character.Attributes.TryGetValue("signature_tics", out var tics) && !string.IsNullOrWhiteSpace(tics))
            sb.AppendLine("Signature mannerisms: " + tics.Trim());

        if (character.ActiveSkills.Count > 0)
            sb.AppendLine("Active Skills & Knowledge Database: " + string.Join("; ", character.ActiveSkills));

        if (character.SomaticZones.Count > 0)
            sb.AppendLine("Baseline somatic vocabulary: " + string.Join("; ", character.SomaticZones));

        if (!Safety.AgeGate.IsAdultEligible(character))
        {
            sb.AppendLine("SAFETY MANDATE: Character is non-canon-adult or under 18. ABSOLUTE HARD BAN on sexual, intimate, or romantic sexualization content. Maintain strictly non-intimate interaction at all times.");
        }
        else if (!Safety.AdultAuth.IsAdultPathAuthorized(character))
        {
            sb.AppendLine("CONTENT RATING: Adult path not authorized by user. Maintain PG-13 non-explicit interactions at all times.");
        }

        return sb.ToString().TrimEnd();
    }

    public static string BuildSceneBlock(string sceneContext)
    {
        if (string.IsNullOrWhiteSpace(sceneContext))
            return "SCENE: (unspecified location — do not invent a genre or world that contradicts your identity.)";

        var sb = new StringBuilder();
        sb.AppendLine("SCENE (location / genre environment only — not your personality):");
        sb.AppendLine(sceneContext.Trim());
        sb.AppendLine("You are physically present in this place. Genre and scenery describe the room, weather, and world texture only.");
        sb.AppendLine("You remain the same person: same history, voice, values, appearance, and mannerisms.");
        sb.AppendLine("Do not become a different archetype because of the setting or genre label.");
        return sb.ToString().TrimEnd();
    }

    /// <summary>
    /// Max transcript lines injected into each prompt (oldest dropped).
    /// </summary>
    public const int MaxTranscriptLines = 12;

    /// <summary>
    /// Formats prior turns for the prompt. Pass newest-last chronological lines.
    /// </summary>
    public static string FormatTranscript(IReadOnlyList<string>? lines, int maxLines = MaxTranscriptLines)
    {
        if (lines == null || lines.Count == 0)
            return "";

        IEnumerable<string> slice = lines.Count <= maxLines
            ? lines
            : lines.Skip(Math.Max(0, lines.Count - maxLines));

        return string.Join("\n", slice.Where(l => !string.IsNullOrWhiteSpace(l)).Select(l => l.Trim()));
    }

    public static string BuildSituationBlock(
        Character character,
        string input,
        string goalContext,
        string? conversationHistory = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine("CURRENT SITUATION:");
        sb.AppendLine("Active Focus / State: " + character.CurrentState);
        sb.AppendLine("Active Bias Lens: " + character.BiasState);
        sb.AppendLine("Bond with interlocutor: " + character.Bond);

        if (character.RelationalBaselines.Count > 0)
        {
            var relevantBaselines = character.RelationalBaselines.Take(2).Select(kv => $"{kv.Key}={kv.Value}");
            sb.AppendLine("Relational Baseline: " + string.Join(", ", relevantBaselines));
        }

        if (character.Memories.Count > 0)
        {
            var topMemories = character.Memories.TakeLast(3);
            sb.AppendLine("Key Memories: " + string.Join(" | ", topMemories));
        }

        if (character.DurableLog?.history != null && character.DurableLog.history.Count > 0)
            sb.AppendLine("Recent Pressure: " + string.Join(" | ", character.DurableLog.history.TakeLast(2).Select(h => $"[{h.movement}] {h.pressure}")));

        if (character.SomaticZones.Count > 0)
            sb.AppendLine("Last somatic tells: " + string.Join(", ", character.SomaticZones.Take(3)));

        string realmGuidance = Somatics.RealmDataCatalog.BuildPromptSomaticGuidance(character.ActiveFocus);
        if (!string.IsNullOrWhiteSpace(realmGuidance))
            sb.AppendLine(realmGuidance);

        if (!string.IsNullOrWhiteSpace(goalContext))
            sb.AppendLine(goalContext.Trim());

        bool hasHistory = !string.IsNullOrWhiteSpace(conversationHistory);
        if (hasHistory)
        {
            sb.AppendLine("CONVERSATION SO FAR (already happened — do not repeat these lines or the same physical beat):");
            sb.AppendLine(conversationHistory!.Trim());
        }

        if (string.IsNullOrWhiteSpace(input))
        {
            if (hasHistory)
            {
                sb.AppendLine("Continue the scene as yourself with the next natural beat.");
                sb.AppendLine("Do not restart the scene. Do not repeat prior dialogue or the same gesture/pose.");
            }
            else
            {
                sb.AppendLine("The scene has just opened; no one has spoken to you yet. Take a natural first beat in character.");
            }
        }
        else
        {
            sb.AppendLine("They just said/did: \"" + input.Trim() + "\"");
            if (hasHistory)
                sb.AppendLine("Respond to that latest beat only. Advance the moment; do not restate your previous line.");
            sb.AppendLine("Respond directly to their statement/action in your own voice. Do NOT repeat, quote, or parrot their words back to them.");
        }

        return sb.ToString().TrimEnd();
    }

    public static string BuildFullPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine("You are roleplaying as " + character.Name + " and only as " + character.Name + ".");
        sb.AppendLine();
        sb.AppendLine(BuildIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine(BuildSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine();
        sb.AppendLine("RULES:");
        sb.AppendLine("1. Stay strictly in character as defined by CHARACTER IDENTITY. Scene never rewrites who you are.");
        sb.AppendLine("2. Autonomic Somatic tells: [Somatic: ...] is strictly for internal/involuntary physiological reactions (e.g. heartbeat, micro-tension, skin warmth, pupil dilation, breath shift). Never put active external stage movements in [Somatic: ...].");
        sb.AppendLine("3. Dual-Aspect Psyche: Under scene pressure, channel your Cognitive Wound (Defensive Lens). Under trust/safety/flow, channel your Cognitive Gift (Generative Lens).");
        sb.AppendLine("4. Off-page matrix guarantee: NEVER output system terms, raw metrics, or internal scoring inside spoken dialogue. Keep dialogue 100% natural and in-character.");
        sb.AppendLine("5. Somatic tells must fit YOUR character's autonomic vocabulary.");
        sb.AppendLine("6. Output ONE reply only. Stop after a single [Somatic] + opening physical action + spoken line + optional concluding action. Never continue as the user, never restate the rules, never invent a second reply.");
        sb.AppendLine();
        sb.AppendLine("Respond in this exact shape (invent fresh words and action for THIS moment — do not copy the sample wording):");
        sb.AppendLine("[Somatic: brief internal tell] Opening physical action beat. \"Spoken words that fit the moment.\" Short concluding physical action.");
        sb.AppendLine("Put spoken words inside double quotes. Write actions before/after quotes as prose. No placeholders, no character-name prefix, no markdown fences, no meta-commentary.");
        return sb.ToString();
    }

    public static string BuildChatMlPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine("<|im_start|>system");
        sb.AppendLine("You are roleplaying as " + character.Name + " and only as " + character.Name + ".");
        sb.AppendLine(BuildIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine("RULES:");
        sb.AppendLine("1. Stay strictly in character as defined by CHARACTER IDENTITY.");
        sb.AppendLine("2. Autonomic Somatic tells: Start with [Somatic: ...] for internal/involuntary physiological reactions only.");
        sb.AppendLine("3. Dual-Aspect Psyche: Channel Cognitive Wound under pressure; Cognitive Gift under trust.");
        sb.AppendLine("4. Respond ONCE only. Stop after one reply. Do not repeat yourself, do not output system/user tags, do not invent further turns.");
        sb.AppendLine("5. Shape: [Somatic: brief internal tell] Opening physical action. \"Spoken words.\" Concluding physical action.");
        sb.AppendLine("6. Invent fresh wording for this moment. Never copy sample lines from the instructions. No placeholder tags, no markdown fences, no meta-commentary.");
        sb.AppendLine("<|im_end|>");
        sb.AppendLine("<|im_start|>user");
        sb.AppendLine(BuildSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine("<|im_end|>");
        sb.Append("<|im_start|>assistant\n");
        return sb.ToString();
    }

    public static string BuildDefaultImagePrompt(Character character, string? sceneContext = null)
    {
        string appearance = BuildAppearanceSummary(character);
        var sb = new StringBuilder();
        sb.Append("Portrait of " + character.Name);
        if (!string.IsNullOrWhiteSpace(appearance) && appearance != "As described in your character identity.")
            sb.Append(", " + appearance);
        sb.Append(", expression: " + character.EmotionEmoji + " " + character.Emotion);
        if (character.SomaticZones.Count > 0)
            sb.Append(", body language: " + string.Join(", ", character.SomaticZones.Take(3)));
        if (!string.IsNullOrWhiteSpace(sceneContext))
            sb.Append(", background setting only: " + sceneContext.Trim());
        sb.Append(". Keep character identity consistent; setting is background only.");
        return sb.ToString();
    }
}
