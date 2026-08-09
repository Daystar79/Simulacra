using System;
using System.IO;
using CharacterSimulator.Logic.Data.Db;
using CharacterSimulator.Logic.Services;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

[Collection("GlobalState")]
public class ProfileAndDatabaseTests
{
    [Fact]
    public void UserProfile_AgeCalculationAndAdultEligibility_EnforcesGating()
    {
        var adult = new UserProfile { DobYear = 1995, DobMonth = 5, DobDay = 15 };
        var minor = new UserProfile { DobYear = 2012, DobMonth = 8, DobDay = 20 };

        var testDate = new DateTime(2026, 7, 31);

        Assert.Equal(31, adult.CalculateAge(testDate));
        Assert.True(adult.IsAdultEligible(testDate));

        Assert.Equal(13, minor.CalculateAge(testDate));
        Assert.False(minor.IsAdultEligible(testDate));
    }

    [Fact]
    public void ProfileRepository_CreateAndVerifyPin_IsIsolatedAndSecure()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_profile_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);

            var repo = new ProfileRepository(conn);

            var p1 = repo.CreateProfile("Alice", 1990, 3, 15, pin: "1234", adultAttested: true);
            var p2 = repo.CreateProfile("Bob", 2010, 10, 5, pin: null, adultAttested: false);

            Assert.True(repo.VerifyPin(p1, "1234"));
            Assert.False(repo.VerifyPin(p1, "9999"));
            Assert.True(repo.VerifyPin(p2, "anything"));

            var all = repo.GetAllProfiles();
            Assert.Equal(2, all.Count);

            Assert.False(string.IsNullOrEmpty(p1.RecoveryCode));
            Assert.True(p1.RecoveryCode.StartsWith("REC-"));

            bool updatedPin = repo.UpdatePin(p1.Id, "1234", "5678");
            Assert.True(updatedPin);
            var updatedP1 = repo.GetById(p1.Id);
            Assert.True(repo.VerifyPin(updatedP1!, "5678"));

            bool resetPin = repo.ResetPinWithRecoveryCode(p1.Id, p1.RecoveryCode, "0000");
            Assert.True(resetPin);
            var resetP1 = repo.GetById(p1.Id);
            Assert.True(repo.VerifyPin(resetP1!, "0000"));

            bool deleted = repo.DeleteProfile(p1.Id);
            Assert.True(deleted);
            Assert.Single(repo.GetAllProfiles());
        }
        finally
        {
            if (File.Exists(tempDb))
            {
                try { File.Delete(tempDb); } catch { }
            }
        }
    }

    [Fact]
    public void SessionRepository_CreateSessionAndAddTurns_PersistsInSqlite()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_session_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);

            var pRepo = new ProfileRepository(conn);
            var profile = pRepo.CreateProfile("Tester", 1998, 6, 12);

            var sRepo = new SessionRepository(conn);
            // character_slug stores opaque card ids (filename stems), not display names
            var session = sRepo.CreateSession(profile.Id, "Test Session", "Neon Alley", "Cyberpunk", "AutoPlay", new() { "a1b2c3d4e5f60718", "f0e1d2c3b4a59687" });

            sRepo.AddTurn(new DbSessionTurn
            {
                SessionId = session.Id,
                TurnIndex = 1,
                Speaker = "Serena",
                Target = "Kira",
                Dialogue = "Hold the perimeter.",
                BondDelta = 2,
                CurrentBond = 10,
                SpeakerEmotion = "Focused"
            });

            var turns = sRepo.GetTurnsForSession(session.Id);
            Assert.Single(turns);
            Assert.Equal("Serena", turns[0].Speaker);
            Assert.Equal("Hold the perimeter.", turns[0].Dialogue);
            Assert.Equal(2, turns[0].BondDelta);
        }
        finally
        {
            if (File.Exists(tempDb))
            {
                try { File.Delete(tempDb); } catch { }
            }
        }
    }

    [Fact]
    public async Task LlmEngineDetector_DetectAvailableEngines_ReturnsDetectedProviders()
    {
        var engines = await LlmEngineDetector.DetectAvailableEnginesAsync();
        Assert.NotEmpty(engines);
        Assert.Contains(engines, e => e.Id == "AGY");
        Assert.Contains(engines, e => e.Id == "Grok");
        Assert.Contains(engines, e => e.Id == "MockEngine" && e.IsAvailable);
    }
}
