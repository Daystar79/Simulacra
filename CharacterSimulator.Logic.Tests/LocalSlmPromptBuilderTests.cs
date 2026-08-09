using System;
using System.Collections.Generic;
using Xunit;
using CharacterSimulator.Logic;

namespace CharacterSimulator.Logic.Tests;

public class LocalSlmPromptBuilderTests
{
    [Fact]
    public void BuildCompactIdentityBlock_FormatsSafetyAndAttributes()
    {
        var character = new Character
        {
            Name = "Anya",
            Personality = "Sharp, observant, loyal",
            Behavior = "Maintains calm distance until trusted",
            Bio = "Senior strategist with tactical background.",
            CognitiveBias = "Guarded posture under scrutiny",
            CognitiveGift = "Insightful pattern recognition"
        };
        character.Attributes["voice"] = "Measured, quiet tone";
        character.Attributes["hard_bans"] = "Never panic or abandon companions";

        string identity = LocalSlmPromptBuilder.BuildCompactIdentityBlock(character);

        Assert.Contains("IDENTITY: Anya", identity);
        Assert.Contains("Personality: Sharp, observant, loyal", identity);
        Assert.Contains("Voice: Measured, quiet tone", identity);
        Assert.Contains("Never do/say: Never panic or abandon companions", identity);
    }

    [Fact]
    public void BuildChatMlPrompt_EmbedsTagsCorrectly()
    {
        var character = new Character
        {
            Name = "Vance",
            Personality = "Pragmatic investigator"
        };

        string prompt = LocalSlmPromptBuilder.BuildChatMlPrompt(
            character,
            input: "What did you find in the archives?",
            sceneContext: "Dimly lit study with antique books",
            goalContext: "Uncover hidden ledger",
            conversationHistory: "User: Are you sure?\nVance: Look at this entry.");

        Assert.Contains("<|im_start|>system", prompt);
        Assert.Contains("<|im_start|>user", prompt);
        Assert.Contains("<|im_start|>assistant", prompt);
        Assert.Contains("Dimly lit study", prompt);
        Assert.Contains("What did you find in the archives?", prompt);
        Assert.Contains("[Somatic:", prompt);
    }

    [Fact]
    public void BuildLlama3Prompt_EmbedsLlama3HeaderTokens()
    {
        var character = new Character
        {
            Name = "Vance",
            Personality = "Pragmatic investigator"
        };

        string prompt = LocalSlmPromptBuilder.BuildLlama3Prompt(
            character,
            input: "Check the door.",
            sceneContext: "Corridor");

        Assert.Contains("<|start_header_id|>system<|end_header_id|>", prompt);
        Assert.Contains("<|start_header_id|>user<|end_header_id|>", prompt);
        Assert.Contains("<|start_header_id|>assistant<|end_header_id|>", prompt);
        Assert.Contains("<|eot_id|>", prompt);
    }

    [Fact]
    public void BuildPrompt_PrioritizesSafetyMandateForNonAdultEligibleCharacter()
    {
        var character = new Character
        {
            Name = "JuniorHero",
            Age = 15,
            CanonAdult = false
        };

        string identity = LocalSlmPromptBuilder.BuildCompactIdentityBlock(character);

        Assert.Contains("[SAFETY MANDATE]: Character non-adult/under 18", identity);
    }

    [Fact]
    public void BuildDolphinPrompt_EmbedsDolphinInvariantsAndFormat()
    {
        var character = new Character
        {
            Name = "Serena",
            Personality = "Calm sanctuary guardian"
        };

        string prompt = LocalSlmPromptBuilder.BuildDolphinPrompt(
            character,
            input: "Is everything alright?",
            sceneContext: "Quiet sanctuary");

        Assert.Contains("<|im_start|>system", prompt);
        Assert.Contains("CORE INVARIANTS:", prompt);
        Assert.Contains("Opening physical action beat", prompt);
        Assert.Contains("Stop after one reply. Never output [Player]:", prompt);
    }

    [Fact]
    public void DetectFormat_AutoDetectsDolphinAndLlama3FromNames()
    {
        Assert.Equal(LocalSlmFormat.Dolphin, LocalSlmPromptBuilder.DetectFormat("Dolphin3.0-Llama3.2-1B.Q4_K_M.gguf"));
        Assert.Equal(LocalSlmFormat.Dolphin, LocalSlmPromptBuilder.DetectFormat("dolphin-3.0-3b"));
        Assert.Equal(LocalSlmFormat.Llama3, LocalSlmPromptBuilder.DetectFormat("Llama-3.2-3B-Instruct.gguf"));
        Assert.Equal(LocalSlmFormat.ChatMl, LocalSlmPromptBuilder.DetectFormat("Qwen2.5-3B-Instruct.gguf"));
    }

    [Fact]
    public void TokenCounter_TruncateToContextLimit_PreservesSystemHeaderAndAssistantTail()
    {
        var character = new Character { Name = "Vance", Personality = "Investigator" };
        string prompt = LocalSlmPromptBuilder.BuildChatMlPrompt(character, "Did you see the ledger?", "Dim room");

        // Request aggressive truncation context limit
        string truncated = CharacterSimulator.Logic.Utilities.TokenCounter.TruncateToContextLimit(prompt, contextSize: 200, reservedForResponse: 50);

        Assert.Contains("<|im_start|>system", truncated);
        Assert.Contains("<|im_start|>assistant", truncated);
        Assert.Contains("Did you see the ledger?", truncated);
    }
}
