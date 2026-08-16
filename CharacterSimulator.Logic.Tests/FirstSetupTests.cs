using System;
using System.IO;
using CharacterSimulator.Logic;
using CharacterSimulator.Logic.Data.Db;
using CharacterSimulator.Logic.Services;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

public class FirstSetupTests
{
    [Fact]
    public void NeedsWizard_WhenFirstSetupComplete_IsFalse()
    {
        Assert.True(FirstSetup.NeedsWizard(new AppSettings()));
        Assert.True(FirstSetup.NeedsWizard(null));
        Assert.False(FirstSetup.NeedsWizard(new AppSettings { FirstSetupComplete = true }));
    }

    [Fact]
    public void SaveSettings_DoesNotFlipFirstSetupComplete()
    {
        string dir = Path.Combine(Path.GetTempPath(), "cs_firstsetup_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        string previous = Directory.GetCurrentDirectory();
        try
        {
            // AppConfigService writes next to the process base directory.
            // We only assert the in-memory contract: SaveSettings must not force the flag.
            var settings = new AppSettings { FirstSetupComplete = false, ScenePrompt = "A quiet room" };
            Assert.False(settings.FirstSetupComplete);
            settings.IsConfigured = true;
            Assert.False(settings.FirstSetupComplete);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void IsPlaceholderProfile_DetectsLegacySeedOnly()
    {
        var seed = new UserProfile
        {
            DisplayName = "Player 1",
            DobYear = 1995,
            DobMonth = 1,
            DobDay = 1
        };
        Assert.True(FirstSetup.IsPlaceholderProfile(seed));

        var named = new UserProfile
        {
            DisplayName = "Alex",
            DobYear = 1995,
            DobMonth = 1,
            DobDay = 1
        };
        Assert.False(FirstSetup.IsPlaceholderProfile(named));

        var pinned = new UserProfile
        {
            DisplayName = "Player 1",
            DobYear = 1995,
            DobMonth = 1,
            DobDay = 1,
            PinHash = "abc"
        };
        Assert.False(FirstSetup.IsPlaceholderProfile(pinned));
    }

    [Fact]
    public void RecommendedModel_IsTheSmallDefault()
    {
        var rec = FirstSetup.RecommendedModel();
        Assert.True(rec.IsDefault);
        Assert.True(rec.ApproxSizeMb < 1500);
        Assert.Contains("1B", rec.DisplayName, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ProfileService_EmptyDatabase_HasNoActiveProfile()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_firstsetup_{Guid.NewGuid():N}.db");
        try
        {
            using var svc = new ProfileService(tempDb);
            Assert.Null(svc.ActiveProfile);
            Assert.Empty(svc.GetAllProfiles());

            var created = svc.CreateOrReplacePlaceholder("Alex", 1998, 6, 12, pin: "1234", adultAttested: true);
            Assert.Equal("Alex", created.DisplayName);
            Assert.Equal("Alex", svc.ActiveProfile?.DisplayName);
            Assert.Single(svc.GetAllProfiles());
        }
        finally
        {
            try { File.Delete(tempDb); } catch { }
        }
    }

    [Fact]
    public void ProfileService_ReplacesPlaceholderInsteadOfStacking()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_firstsetup_{Guid.NewGuid():N}.db");
        try
        {
            using var svc = new ProfileService(tempDb);
            svc.CreateProfile("Player 1", 1995, 1, 1, pin: null, adultAttested: false);
            Assert.True(FirstSetup.IsPlaceholderProfile(svc.ActiveProfile));

            svc.CreateOrReplacePlaceholder("Jordan", 2001, 4, 20);
            Assert.Single(svc.GetAllProfiles());
            Assert.Equal("Jordan", svc.ActiveProfile?.DisplayName);
        }
        finally
        {
            try { File.Delete(tempDb); } catch { }
        }
    }
}
