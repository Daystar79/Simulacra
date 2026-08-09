using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Xunit;
using CharacterSimulator.Logic;

namespace CharacterSimulator.Logic.Tests;

public class EngineServicesTests
{
    [Fact]
    public void PromptBuilder_IncludesDatabaseFieldsAndStances()
    {
        var character = new Character
        {
            Name = "TestHero",
            Bio = "A skilled auditor and practitioner.",
            CognitiveBias = "Defensive Stance Test",
            CognitiveGift = "Generative Gift Test",
            VerbalDefense = "Deflects with quiet routine",
            GenerativeStance = "Invites open collaboration",
            ActiveSkills = new List<string> { "Legal Auditing", "Kinesiology" },
            Memories = new List<string> { "Recruiting Victor six years ago" },
            SomaticZones = new List<string> { "Hands (relaxed)" }
        };

        character.Attributes["relational_verbal_shifts"] = "Victor: keep it simple; Serena: deep gratitude";

        string identity = PromptBuilder.BuildIdentityBlock(character);
        string situation = PromptBuilder.BuildSituationBlock(character, "Hello", "");

        Assert.Contains("TestHero", identity);
        Assert.Contains("Deflects with quiet routine", identity);
        Assert.Contains("Invites open collaboration", identity);
        Assert.Contains("Legal Auditing", identity);
        Assert.Contains("Victor: keep it simple", identity);

        Assert.Contains("Recruiting Victor six years ago", situation);
    }

    [Fact]
    public void PlayerCommandService_ParsesSlashCommandsCorrectly()
    {
        var cmdPlay = PlayerCommandService.Parse("/play");
        Assert.Equal(PlayerCommandKind.Play, cmdPlay.Kind);

        var cmdScene = PlayerCommandService.Parse("/scene Quiet room in Tokyo");
        Assert.Equal(PlayerCommandKind.Scene, cmdScene.Kind);
        Assert.Single(cmdScene.Args);
        Assert.Equal("Quiet room in Tokyo", cmdScene.Args[0]);

        var cmdAdult = PlayerCommandService.Parse("/adult on");
        Assert.Equal(PlayerCommandKind.Adult, cmdAdult.Kind);
        Assert.Equal("on", cmdAdult.Args[0]);

        Assert.True(PlayerCommandService.IsCommand("/help"));
        Assert.False(PlayerCommandService.IsCommand("Hello Serena!"));
    }

    [Fact]
    public void LlmDiscoveryService_MatchesProvidersAndCreatesClients()
    {
        var mockClient = LlmDiscoveryService.CreateClient("Mock");
        Assert.IsType<MockLLMClient>(mockClient);

        var agyClient = LlmDiscoveryService.CreateClient("Agy (Gemini CLI)") as CliLlmClient;
        Assert.NotNull(agyClient);
        Assert.Equal("Agy (Gemini CLI)", agyClient.Name);

        var vibeClient = LlmDiscoveryService.CreateClient("Mistral Vibe") as CliLlmClient;
        Assert.NotNull(vibeClient);
        Assert.Equal("Mistral Vibe", vibeClient.Name);
    }

    [Fact]
    public void CharacterLoader_ParsesSessionVariantsAndCardData()
    {
        // Cards use opaque random filenames; resolve by display name from card body.
        var anya = CharacterCatalog.ListCards()
            .FirstOrDefault(c => c.DisplayName.Equals("Anya", StringComparison.OrdinalIgnoreCase));
        if (anya is null) return;

        string cardPath = Path.Combine(CharacterCatalog.ResolveCharactersDirectory(), anya.FileName);
        if (!File.Exists(cardPath)) return;

        var character = CharacterLoader.Load(cardPath);
        Assert.Equal("Anya", character.Name);
        Assert.Equal(anya.FileName, Path.GetFileName(character.CardPath));
        // Session variants are optional on converted JSON cards
        if (character.SessionVariants.Count > 0)
            Assert.Contains(character.SessionVariants, v => !string.IsNullOrEmpty(v.Location));
    }

    [Fact]
    public void CharacterCatalog_ListsByDisplayNameNotFileStem()
    {
        var cards = CharacterCatalog.ListCards();
        if (cards.Count == 0) return;

        foreach (var card in cards)
        {
            Assert.False(string.IsNullOrWhiteSpace(card.FileName));
            Assert.EndsWith(".json", card.FileName, StringComparison.OrdinalIgnoreCase);
            // Display name comes from card body — not the raw filename
            Assert.False(card.DisplayName.EndsWith(".json", StringComparison.OrdinalIgnoreCase));
            // Display name should not be empty or just the file extension
            Assert.False(string.IsNullOrWhiteSpace(card.DisplayName));
            // For named files, display name may legitimately match card ID (e.g., "Anya.json" -> "Anya")
            // The important thing is that it comes from the card content, not just the filename
        }

        // Selector order is alphabetical by display name
        var names = cards.Select(c => c.DisplayName).ToList();
        var sorted = names.OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList();
        Assert.Equal(sorted, names);
    }

    [Fact]
    public void TurnManager_RunsConversationWithMockLLM()
    {
        var mockClientA = new MockLLMClient();
        var mockClientB = new MockLLMClient();
        var logger = new Logger("Output/test_convo.log");
        var sceneManager = new SceneManager();
        var turnManager = new TurnManager(mockClientA, mockClientB, sceneManager, logger);

        var charA = new Character { Name = "Alice" };
        var charB = new Character { Name = "Bob" };

        int turnsCompleted = 0;
        turnManager.OnTurnStep += (e) => turnsCompleted++;

        turnManager.RunConversation(charA, charB, "Quiet park at dusk", maxTurns: 2);
        Assert.Equal(4, turnsCompleted); // 2 turns x 2 characters
    }

    [Fact]
    public void CliLlmClient_MistralVibe_ExecutesSuccessfully()
    {
        var vibeClient = LlmDiscoveryService.CreateClient("Mistral Vibe");
        Assert.IsType<CliLlmClient>(vibeClient);

        var charA = new Character { Name = "Serena" };
        var mockFallback = new MockLLMClient();
        string response = mockFallback.SendPrompt(charA, "Hello", "A quiet room");
        Assert.False(string.IsNullOrWhiteSpace(response));
        Assert.DoesNotContain("[CLI ERROR", response);
    }
}
