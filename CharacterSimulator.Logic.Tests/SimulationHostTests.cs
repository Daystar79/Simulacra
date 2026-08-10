using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using CharacterSimulator.Logic;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

[Collection("StaticStateTests")]
public class SimulationHostTests
{
    [Fact]
    public void HelpCommand_PostsSystemLine()
    {
        var control = new TurnControlContext();
        control.DelayMs = 0;
        var host = new SimulationHost(control);
        var lines = new List<DialogueLine>();
        host.OnDialogueLine += lines.Add;

        host.SubmitPlayerLine("/help");

        Assert.Contains(lines, l => l.IsSystem && l.Dialogue.Contains("/play", StringComparison.Ordinal));
    }

    [Fact]
    public async Task PlayWithMock_ProducesCharacterTurn()
    {
        // Find any character card in repo Characters/
        string? card = null;
        foreach (var root in new[]
                 {
                     Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Characters"),
                     Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "..", "..", "..", "Characters")),
                 })
        {
            if (!Directory.Exists(root)) continue;
            foreach (var f in Directory.EnumerateFiles(root, "*.json"))
            {
                card = Path.GetFileName(f);
                // Ensure catalog can resolve this dir
                Environment.SetEnvironmentVariable("CHARACTERS_DIR", root);
                break;
            }
            if (card != null) break;
        }

        // Fall back: use CharacterCatalog discovery
        var cards = CharacterCatalog.ListCards();
        if (cards.Count == 0 && card == null)
        {
            // No cards available in CI — skip soft
            return;
        }

        if (card == null)
            card = cards[0].FileName;

        var settings = new AppSettings
        {
            SelectedCharA = card,
            SelectedCharB = "",
            RoleplayLlmProvider = "Mock / Simulation",
            SelectedLlmA = "Mock",
            RoleplayMode = "AutoPlay",
            MaxTurns = 2,
            ScenePrompt = "Quiet test room",
            SelectedGenre = SceneGenreCatalog.DefaultGenreId
        };
        AppConfigService.SaveSettings(settings);

        var control = new TurnControlContext();
        control.UpdateSettings(settings);
        control.DelayMs = 0;

        var host = new SimulationHost(control);
        host.SetStagedCharacter(card);
        var lines = new List<DialogueLine>();
        var sync = new object();
        host.OnDialogueLine += l => { lock (sync) lines.Add(l); };

        host.Play();
        // Wait for background session
        for (int i = 0; i < 100 && host.IsSessionRunning; i++)
            await Task.Delay(50);

        List<DialogueLine> snapshot;
        lock (sync) snapshot = lines.ToList();

        Assert.True(snapshot.Count > 0, "Expected at least system start line");
        Assert.Contains(snapshot, l => !l.IsSystem && l.SpeakerName != "Player");
    }
}
