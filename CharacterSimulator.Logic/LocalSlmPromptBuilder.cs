using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CharacterSimulator.Logic;

public enum LocalSlmFormat
{
    /// <summary>Dolphin 3.0 optimized ChatML format (<|im_start|>system...)</summary>
    Dolphin,
    /// <summary>ChatML format standard (<|im_start|>system...)</summary>
    ChatMl,
    /// <summary>Llama 3 header format (<|start_header_id|>system...)</summary>
    Llama3,
    /// <summary>Alpaca instruction format (### Instruction:...)</summary>
    Alpaca,
    /// <summary>Concise plaintext format optimized for raw SLM completions</summary>
    Plaintext
}

/// <summary>
/// Specialized prompt builder optimized for local SLMs and embedded small language models
/// (e.g. Dolphin 3.0, Llama-3 1B/3B, Qwen-2.5 0.5B-7B, Phi-3, GGUF runtimes via LLamaSharp or Ollama).
/// Highlights:
/// - Compact token budget management (fits safely within 2K context windows).
/// - Safety instructions prioritized at top of system context for small model attention alignment.
/// - Dense identity formatting with zero redundant instruction fluff.
/// - Model-specific ChatML / Llama3 / Dolphin tag framing to eliminate preamble and prompt echo.
/// </summary>
public static class LocalSlmPromptBuilder
{
    public const int DefaultMaxSlmTranscriptLines = 6;

    /// <summary>
    /// Auto-detects the best local SLM format from model name or path.
    /// </summary>
    public static LocalSlmFormat DetectFormat(string? modelOrPath)
    {
        if (string.IsNullOrWhiteSpace(modelOrPath))
            return LocalSlmFormat.Dolphin;

        if (modelOrPath.Contains("dolphin", StringComparison.OrdinalIgnoreCase))
            return LocalSlmFormat.Dolphin;

        if (modelOrPath.Contains("llama3", StringComparison.OrdinalIgnoreCase) ||
            modelOrPath.Contains("llama-3", StringComparison.OrdinalIgnoreCase))
            return LocalSlmFormat.Llama3;

        if (modelOrPath.Contains("alpaca", StringComparison.OrdinalIgnoreCase) ||
            modelOrPath.Contains("vicuna", StringComparison.OrdinalIgnoreCase))
            return LocalSlmFormat.Alpaca;

        return LocalSlmFormat.ChatMl;
    }

    /// <summary>
    /// Builds a context-optimized prompt tailored for local SLMs.
    /// </summary>
    public static string BuildPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null,
        LocalSlmFormat format = LocalSlmFormat.Dolphin)
    {
        return format switch
        {
            LocalSlmFormat.Dolphin => BuildDolphinPrompt(character, input, sceneContext, goalContext, conversationHistory),
            LocalSlmFormat.ChatMl => BuildChatMlPrompt(character, input, sceneContext, goalContext, conversationHistory),
            LocalSlmFormat.Llama3 => BuildLlama3Prompt(character, input, sceneContext, goalContext, conversationHistory),
            LocalSlmFormat.Alpaca => BuildAlpacaPrompt(character, input, sceneContext, goalContext, conversationHistory),
            _ => BuildPlaintextPrompt(character, input, sceneContext, goalContext, conversationHistory)
        };
    }

    /// <summary>
    /// Concise identity block optimized for small local model context budgets.
    /// </summary>
    public static string BuildCompactIdentityBlock(Character character)
    {
        var sb = new StringBuilder(512);

        // Safety mandate at the top for maximum attention weight in SLMs
        if (!Safety.AgeGate.IsAdultEligible(character))
        {
            sb.AppendLine("[SAFETY MANDATE]: Character non-adult/under 18. NO sexual/intimate content. Non-intimate only.");
        }
        else if (!Safety.AdultAuth.IsAdultPathAuthorized(character))
        {
            sb.AppendLine("[CONTENT RATING]: Non-explicit PG-13 interactions only.");
        }

        sb.AppendLine($"IDENTITY: {character.Name}");
        if (!string.IsNullOrWhiteSpace(character.Personality))
            sb.AppendLine($"Personality: {character.Personality.Trim()}");
        if (!string.IsNullOrWhiteSpace(character.Behavior))
            sb.AppendLine($"Behavior: {character.Behavior.Trim()}");
        if (!string.IsNullOrWhiteSpace(character.Bio))
            sb.AppendLine($"Background: {character.Bio.Trim()}");

        if (!string.IsNullOrWhiteSpace(character.CognitiveBias))
            sb.AppendLine($"Defensive Lens: {character.CognitiveBias.Trim()}");
        if (!string.IsNullOrWhiteSpace(character.CognitiveGift))
            sb.AppendLine($"Generative Lens: {character.CognitiveGift.Trim()}");
        
        if (!string.IsNullOrWhiteSpace(character.CulturalBias))
            sb.AppendLine($"Cultural Bias: {character.CulturalBias.Trim()}");

        string appearance = PromptBuilder.BuildAppearanceSummary(character);
        if (!string.IsNullOrWhiteSpace(appearance) && appearance != "As described in your character identity.")
        {
            // Truncate long pose-like descriptions into dense physical keywords so models don't copy static paragraphs verbatim
            string compactAppearance = appearance.Length > 120 ? appearance[..117].TrimEnd() + "..." : appearance;
            sb.AppendLine($"Physical: {compactAppearance}");
        }

        if (!string.IsNullOrWhiteSpace(character.CharacterStyle))
            sb.AppendLine($"Style: {character.CharacterStyle.Trim()}");

        if (character.Attributes.TryGetValue("voice", out var voice) && !string.IsNullOrWhiteSpace(voice))
            sb.AppendLine($"Voice: {voice.Trim()}");
        else if (!string.IsNullOrWhiteSpace(character.VoiceSyntacticalEngine))
            sb.AppendLine($"Voice: {character.VoiceSyntacticalEngine.Trim()}");

        if (!string.IsNullOrWhiteSpace(character.ConversationalStance))
            sb.AppendLine($"Stance: {character.ConversationalStance.Trim()}");
        
        if (!string.IsNullOrWhiteSpace(character.VerbalDefense))
            sb.AppendLine($"Verbal Defense: {character.VerbalDefense.Trim()}");
        
        if (!string.IsNullOrWhiteSpace(character.GenerativeStance))
            sb.AppendLine($"Generative Stance: {character.GenerativeStance.Trim()}");

        if (character.LatentAnchors.Count > 0)
            sb.AppendLine($"Latent Anchors: {string.Join("; ", character.LatentAnchors)}");

        if (character.SomaticZones.Count > 0)
            sb.AppendLine($"Somatic Vocabulary: {string.Join("; ", character.SomaticZones)}");

        if (character.Attributes.TryGetValue("hard_bans", out var bans) && !string.IsNullOrWhiteSpace(bans))
            sb.AppendLine($"Never do/say: {bans.Trim()}");
        
        if (character.Attributes.TryGetValue("signature_tics", out var tics) && !string.IsNullOrWhiteSpace(tics))
            sb.AppendLine($"Signature Tics: {tics.Trim()}");

        return sb.ToString().TrimEnd();
    }

    /// <summary>
    /// Compact scene block focusing strictly on immediate environment.
    /// </summary>
    public static string BuildCompactSceneBlock(string sceneContext)
    {
        if (string.IsNullOrWhiteSpace(sceneContext))
            return "SCENE: Unspecified location.";

        return $"SCENE: {sceneContext.Trim()}";
    }

    /// <summary>
    /// Compact situation and turn history block.
    /// </summary>
    public static string BuildCompactSituationBlock(
        Character character,
        string input,
        string goalContext,
        string? conversationHistory,
        int maxTranscriptLines = DefaultMaxSlmTranscriptLines)
    {
        var sb = new StringBuilder(512);
        sb.AppendLine($"SITUATION: State={character.CurrentState} | Lens={character.BiasState} | Bond={character.Bond}");

        if (character.Memories.Count > 0)
        {
            sb.AppendLine($"Memory: {character.Memories[^1]}");
        }

        if (!string.IsNullOrWhiteSpace(goalContext))
            sb.AppendLine($"Goal: {goalContext.Trim()}");

        string formattedHistory = PromptBuilder.FormatTranscript(
            conversationHistory?.Split('\n'), maxTranscriptLines);

        if (!string.IsNullOrWhiteSpace(formattedHistory))
        {
            sb.AppendLine("CONVERSATION SO FAR (already spoken in prior turns — do NOT repeat these lines):");
            sb.AppendLine(formattedHistory);
        }

        if (!string.IsNullOrWhiteSpace(input))
        {
            string cleanInput = input.Trim();
            if (cleanInput.StartsWith("[Player]:", StringComparison.OrdinalIgnoreCase))
                cleanInput = cleanInput.Substring(9).Trim().Trim('"');
            else if (cleanInput.StartsWith("Player:", StringComparison.OrdinalIgnoreCase))
                cleanInput = cleanInput.Substring(7).Trim().Trim('"');

            sb.AppendLine($"PLAYER QUESTION / STATEMENT: \"{cleanInput}\"");
            sb.AppendLine("MANDATE: Answer their question directly in character. Do NOT ignore what they asked or said. Do NOT repeat or echo their words.");
        }
        else if (!string.IsNullOrWhiteSpace(formattedHistory))
        {
            sb.AppendLine("Advance the scene with NEW dialogue and NEW actions for this turn. Do NOT repeat prior dialogue or restart the scene.");
        }
        else
        {
            sb.AppendLine("Take a natural first beat in character to open the scene.");
        }

        return sb.ToString().TrimEnd();
    }

    /// <summary>
    /// Dolphin 3.0 optimized ChatML prompt based on CharacterRuntime_Dolphin.md.
    /// </summary>
    public static string BuildDolphinPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder(1024);
        sb.AppendLine("<|im_start|>system");
        sb.AppendLine($"You are roleplaying as {character.Name}.");
        sb.AppendLine(BuildCompactIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildCompactSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine("CORE INVARIANTS:");
        sb.AppendLine("1. Identity is SSOT: Card is immutable. Setting describes room/weather only—never alter personality or voice.");
        sb.AppendLine("2. Body Before Insight: Physical posture beats operate silently. Never output system metrics inside dialogue.");
        sb.AppendLine("3. Turn Ordering: Output ONE reply formatted as:");
        sb.AppendLine("   [Somatic: brief internal reaction] Opening physical action beat. \"Spoken dialogue in character.\" Concluding physical action beat.");
        sb.AppendLine("   - Opening action beat MUST appear BEFORE spoken dialogue.");
        sb.AppendLine("   - Spoken words MUST be in double quotes. Actions outside quotes as prose.");
        sb.AppendLine("4. Dynamic Action Beats: Describe NEW physical movement or posture for THIS turn. Do NOT copy static appearance text or prior turn descriptions.");
        sb.AppendLine("5. No Echoing/Repetition: Never repeat prior dialogue from CONVERSATION SO FAR. Output FRESH dialogue and NEW physical movement for this turn.");
        sb.AppendLine("6. First-Person Perspective: Always speak and narrate in 1st person ('I', 'me', 'my'). NEVER refer to yourself in 3rd person (e.g. do NOT say 'Serena stands...') and NEVER quote your own name.");
        sb.AppendLine("7. Stop after one reply. Never output [Player]: or repeat prompt instructions.");
        sb.AppendLine("<|im_end|>");
        sb.AppendLine("<|im_start|>user");
        sb.AppendLine(BuildCompactSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine("<|im_end|>");
        sb.Append("<|im_start|>assistant\n");
        return sb.ToString();
    }

    /// <summary>
    /// ChatML format (<|im_start|>) for Qwen, Mistral, and ChatML-fine-tuned SLMs.
    /// </summary>
    public static string BuildChatMlPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder(1024);
        sb.AppendLine("<|im_start|>system");
        sb.AppendLine($"You are roleplaying as {character.Name}.");
        sb.AppendLine(BuildCompactIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildCompactSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine("RULES:");
        sb.AppendLine("1. Stay strictly in character.");
        sb.AppendLine("2. Output ONE reply formatted exactly as:");
        sb.AppendLine("   [Somatic: brief internal reaction] Opening physical action beat. \"Spoken dialogue.\" Short concluding physical action.");
        sb.AppendLine("3. First-Person Perspective: Always speak and narrate in 1st person ('I', 'me', 'my'). NEVER refer to yourself in 3rd person or quote your own name.");
        sb.AppendLine("4. No meta-commentary, no markdown code fences, no user continuation.");
        sb.AppendLine("<|im_end|>");
        sb.AppendLine("<|im_start|>user");
        sb.AppendLine(BuildCompactSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine("<|im_end|>");
        sb.Append("<|im_start|>assistant\n");
        return sb.ToString();
    }

    /// <summary>
    /// Llama 3 header format (<|start_header_id|>) for Llama 3/3.1/3.2 local models.
    /// </summary>
    public static string BuildLlama3Prompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder(1024);
        sb.AppendLine("<|start_header_id|>system<|end_header_id|>");
        sb.AppendLine($"You are roleplaying as {character.Name}.");
        sb.AppendLine(BuildCompactIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildCompactSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine("RULES:");
        sb.AppendLine("1. Stay in character.");
        sb.AppendLine("2. Output shape: [Somatic: brief internal reaction] Opening physical action. \"Spoken text.\" Concluding physical action.");
        sb.AppendLine("3. First-Person Perspective: Always speak and narrate in 1st person ('I', 'me', 'my'). NEVER refer to yourself in 3rd person.");
        sb.AppendLine("4. Output single response only.<|eot_id|>");
        sb.AppendLine("<|start_header_id|>user<|end_header_id|>");
        sb.AppendLine(BuildCompactSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine("<|eot_id|>");
        sb.Append("<|start_header_id|>assistant<|end_header_id|>\n");
        return sb.ToString();
    }

    /// <summary>
    /// Alpaca format (### Instruction:) for classical fine-tuned small models.
    /// </summary>
    public static string BuildAlpacaPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder(1024);
        sb.AppendLine("### Instruction:");
        sb.AppendLine($"Roleplay as {character.Name}.");
        sb.AppendLine(BuildCompactIdentityBlock(character));
        sb.AppendLine(BuildCompactSceneBlock(sceneContext));
        sb.AppendLine(BuildCompactSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine("Respond as: [Somatic: brief internal reaction] Opening physical action. \"Spoken text.\" Concluding physical action.");
        sb.AppendLine();
        sb.AppendLine("### Response:");
        return sb.ToString();
    }

    /// <summary>
    /// Plaintext completion format for GGUF base models or fallback SLMs.
    /// </summary>
    public static string BuildPlaintextPrompt(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        string? conversationHistory = null)
    {
        var sb = new StringBuilder(1024);
        sb.AppendLine($"Roleplay as {character.Name}.");
        sb.AppendLine(BuildCompactIdentityBlock(character));
        sb.AppendLine();
        sb.AppendLine(BuildCompactSceneBlock(sceneContext));
        sb.AppendLine();
        sb.AppendLine(BuildCompactSituationBlock(character, input, goalContext, conversationHistory));
        sb.AppendLine();
        sb.AppendLine("FORMAT REQUIREMENT:");
        sb.AppendLine("[Somatic: brief internal reaction] Opening physical action. \"Spoken dialogue.\" Short concluding physical action.");
        sb.Append($"{character.Name}: ");
        return sb.ToString();
    }
}
