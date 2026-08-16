using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

public class KeepAliveTests
{
    [Fact]
    public void PickDelay_StaysInsideClampedRange()
    {
        var rng = new Random(42);
        for (int i = 0; i < 40; i++)
        {
            var delay = KeepAliveBeats.PickDelay(rng, 10, 12);
            Assert.InRange(delay.TotalSeconds, 10, 12);
        }

        int min = 0, max = 1;
        KeepAliveBeats.ClampRange(ref min, ref max);
        Assert.Equal(4, min);
        Assert.True(max >= min);
        Assert.Equal(1, KeepAliveBeats.ClampMaxIdleBeats(0));
        Assert.Equal(12, KeepAliveBeats.ClampMaxIdleBeats(99));
        Assert.Equal(15, KeepAliveBeats.DefaultMinSeconds);
        Assert.Equal(120, KeepAliveBeats.DefaultMaxSeconds);

        for (int i = 0; i < 80; i++)
        {
            var idle = KeepAliveBeats.PickDelay(rng, KeepAliveBeats.DefaultMinSeconds, KeepAliveBeats.DefaultMaxSeconds);
            Assert.InRange(idle.TotalSeconds, 15, 120);
        }
    }

    [Fact]
    public void PickCue_IsFromCatalog()
    {
        var rng = new Random(7);
        for (int i = 0; i < 20; i++)
        {
            string cue = KeepAliveBeats.PickCue(rng);
            Assert.Contains(cue, KeepAliveBeats.Cues);
            Assert.DoesNotContain("keep-alive", cue, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Player", cue, StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task Scheduler_FiresThenDisarms()
    {
        int fires = 0;
        var delayGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var scheduler = new KeepAliveScheduler(
            () => TimeSpan.FromMilliseconds(1),
            () => Interlocked.Increment(ref fires),
            async (_, ct) => await delayGate.Task.WaitAsync(ct));

        scheduler.Arm();
        Assert.True(scheduler.IsArmed);
        delayGate.SetResult();

        for (int i = 0; i < 50 && Volatile.Read(ref fires) == 0; i++)
            await Task.Delay(20);

        Assert.Equal(1, fires);
        Assert.False(scheduler.IsArmed);
    }

    [Fact]
    public async Task Scheduler_CancelPreventsFire()
    {
        int fires = 0;
        var delayGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var scheduler = new KeepAliveScheduler(
            () => TimeSpan.FromSeconds(30),
            () => Interlocked.Increment(ref fires),
            async (_, ct) => await delayGate.Task.WaitAsync(ct));

        scheduler.Arm();
        scheduler.Cancel();
        delayGate.TrySetCanceled();

        await Task.Delay(40);
        Assert.Equal(0, fires);
        Assert.False(scheduler.IsArmed);
    }

    [Fact]
    public void PromptBuilder_AmbientUsesIdleVolitionNotPlayerSpeech()
    {
        var character = new Character { Name = "Vance", Bio = "An investigator." };
        string input = PromptBuilder.FormatAmbientStimulus("Notice something small in the space or in your body.");
        string situation = PromptBuilder.BuildSituationBlock(character, input, "", "Vance: Earlier line.");

        Assert.Contains(PromptBuilder.VolitionIdle, situation);
        Assert.Contains("Notice something small", situation);
        Assert.DoesNotContain("THEY JUST SAID/DID", situation);
        Assert.DoesNotContain(PromptBuilder.AmbientStimulusPrefix, situation);
        Assert.DoesNotContain("CS_AMBIENT", situation);
    }

    [Fact]
    public void LocalSlmPromptBuilder_AmbientUsesIdleVolition()
    {
        var character = new Character { Name = "Vance" };
        string input = PromptBuilder.FormatAmbientStimulus("A quiet stretch of time passes. Stay in the room.");
        string prompt = LocalSlmPromptBuilder.BuildChatMlPrompt(
            character, input, "Quiet study", "", "Vance: Earlier line.");

        Assert.Contains(PromptBuilder.VolitionIdle, prompt);
        Assert.DoesNotContain("THEY JUST SAID/DID", prompt);
        Assert.DoesNotContain("CS_AMBIENT", prompt);
    }

    [Fact]
    public void AppSettings_MissingKeepAliveMeansOn()
    {
        var missing = new AppSettings();
        Assert.True(missing.KeepAliveIsOn);

        var off = new AppSettings { KeepAliveEnabled = false };
        Assert.False(off.KeepAliveIsOn);

        var on = new AppSettings { KeepAliveEnabled = true };
        Assert.True(on.KeepAliveIsOn);
        Assert.Equal(15, on.KeepAliveMinSeconds);
        Assert.Equal(120, on.KeepAliveMaxSeconds);
    }

    [Fact]
    public void PlayerCommand_ParsesKeepAlive()
    {
        Assert.Equal(PlayerCommandKind.KeepAlive, PlayerCommandService.Parse("/keepalive off").Kind);
        Assert.Equal("off", PlayerCommandService.Parse("/keepalive off").Args[0]);
        Assert.Equal(PlayerCommandKind.KeepAlive, PlayerCommandService.Parse("/alive now").Kind);
        Assert.Contains("/keepalive", PlayerCommandService.GetHelpText(), StringComparison.Ordinal);
    }
}

[Collection("StaticStateTests")]
public class KeepAliveHostTests
{
    [Fact]
    public async Task KeepAliveTurn_ProducesCharacterLineWithoutPlayerBubble()
    {
        if (!TryPickCard(out string card))
            return;

        var settings = NewMockSettings(card);
        settings.KeepAliveEnabled = true;
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
        if (!await WaitUntil(() => CountCharacterLines(lines, sync) >= 1, 5000))
            return;

        int before = CountCharacterLines(lines, sync);
        int playerBefore = CountPlayerLines(lines, sync);
        Assert.True(host.TryTriggerKeepAlive(), "Expected parked session to accept an idle beat");

        Assert.True(await WaitUntil(() => CountCharacterLines(lines, sync) > before, 5000));
        Assert.Equal(playerBefore, CountPlayerLines(lines, sync));
        Assert.True(host.KeepAliveIdleBeats >= 1);
    }

    [Fact]
    public async Task UserPause_BlocksKeepAlive()
    {
        if (!TryPickCard(out string card))
            return;

        var settings = NewMockSettings(card);
        settings.KeepAliveEnabled = true;
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
        if (!await WaitUntil(() => CountCharacterLines(lines, sync) >= 1, 5000))
            return;

        host.Pause();
        int before = CountCharacterLines(lines, sync);
        Assert.False(host.TryTriggerKeepAlive());
        await Task.Delay(80);
        Assert.Equal(before, CountCharacterLines(lines, sync));
    }

    [Fact]
    public void KeepAliveOff_CommandPersists()
    {
        var settings = new AppSettings { KeepAliveEnabled = true, MaxTurns = 4 };
        AppConfigService.SaveSettings(settings);
        var control = new TurnControlContext();
        control.UpdateSettings(settings);
        var host = new SimulationHost(control);
        var lines = new List<DialogueLine>();
        host.OnDialogueLine += lines.Add;

        host.SubmitPlayerLine("/keepalive off");

        Assert.False(control.CurrentSettings.KeepAliveIsOn);
        Assert.Contains(lines, l => l.IsSystem && l.Dialogue.Contains("OFF", StringComparison.Ordinal));
    }

    private static AppSettings NewMockSettings(string card) => new()
    {
        SelectedCharA = card,
        SelectedCharB = "",
        RoleplayLlmProvider = "Mock / Simulation",
        SelectedLlmA = "Mock",
        MaxTurns = 4,
        ScenePrompt = "Quiet test room",
        SelectedGenre = SceneGenreCatalog.DefaultGenreId,
        KeepAliveEnabled = true
    };

    private static int CountCharacterLines(List<DialogueLine> lines, object sync)
    {
        lock (sync)
            return lines.Count(l => !l.IsSystem && l.SpeakerName != "Player");
    }

    private static int CountPlayerLines(List<DialogueLine> lines, object sync)
    {
        lock (sync)
            return lines.Count(l => l.SpeakerName == "Player");
    }

    private static async Task<bool> WaitUntil(Func<bool> pred, int timeoutMs)
    {
        for (int i = 0; i < timeoutMs / 25; i++)
        {
            if (pred()) return true;
            await Task.Delay(25);
        }
        return pred();
    }

    private static bool TryPickCard(out string card)
    {
        card = "";
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
                Environment.SetEnvironmentVariable("CHARACTERS_DIR", root);
                return true;
            }
        }

        var cards = CharacterCatalog.ListCards();
        if (cards.Count == 0) return false;
        card = cards[0].FileName;
        return true;
    }
}
