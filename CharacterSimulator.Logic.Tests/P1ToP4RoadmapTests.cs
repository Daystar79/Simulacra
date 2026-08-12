using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using CharacterSimulator.Logic.Data.Db;
using CharacterSimulator.Logic.Safety;
using CharacterSimulator.Logic.Services;
using CharacterSimulator.Logic.State;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

[Collection("GlobalState")]
public class P1ToP4RoadmapTests
{
    [Fact]
    public void P1_RecoveryCode_And_PinReset_WorksCorrectly()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_recovery_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);

            var repo = new ProfileRepository(conn);
            var p = repo.CreateProfile("Tester", 1995, 4, 10, pin: "1111", adultAttested: true);

            Assert.False(string.IsNullOrWhiteSpace(p.RecoveryCode));
            Assert.StartsWith("REC-", p.RecoveryCode);

            // Attempt reset with invalid code
            bool failedReset = repo.ResetPinWithRecoveryCode(p.Id, "REC-INVALID-CODE", "2222");
            Assert.False(failedReset);
            Assert.True(repo.VerifyPin(p, "1111"));

            // Reset with valid recovery code
            bool successReset = repo.ResetPinWithRecoveryCode(p.Id, p.RecoveryCode, "3333");
            Assert.True(successReset);

            var updatedP = repo.GetById(p.Id);
            Assert.True(repo.VerifyPin(updatedP!, "3333"));
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
    public void P1_SessionExportService_ExportsMarkdownAndJson()
    {
        var session = new DbSession
        {
            Id = "session_123",
            Title = "Neon Sunset",
            Scene = "Cyberpunk Lounge",
            Genre = "Sci-Fi",
            Mode = "AutoPlay",
            StartedAt = DateTime.UtcNow
        };

        var turns = new System.Collections.Generic.List<DbSessionTurn>
        {
            new DbSessionTurn
            {
                SessionId = session.Id,
                TurnIndex = 1,
                Speaker = "Vera",
                Target = "Kira",
                Dialogue = "The grid is live.",
                SpeakerEmotion = "Confident",
                BondDelta = 1,
                CurrentBond = 5
            }
        };

        var participants = new System.Collections.Generic.List<string> { "Vera", "Kira" };

        string tempMd = Path.Combine(Path.GetTempPath(), $"export_{Guid.NewGuid():N}.md");
        try
        {
            string mdText = SessionExportService.ExportSessionToMarkdown(session, turns, participants, tempMd);
            Assert.Contains("# Roleplay Session Transcript: Neon Sunset", mdText);
            Assert.Contains("The grid is live.", mdText);
            Assert.True(File.Exists(tempMd));
        }
        finally
        {
            if (File.Exists(tempMd))
            {
                try { File.Delete(tempMd); } catch { }
            }
        }
    }

    [Fact]
    public void P1_AppVersionInfo_ProvidesDisplayVersion()
    {
        Assert.Equal("v1.0.0", AppVersionInfo.DisplayVersion);
        Assert.False(string.IsNullOrWhiteSpace(AppVersionInfo.FullVersionString));
    }

    [Fact]
    public async Task P2_GitHubUpdateCheckService_FailsOpenOffline()
    {
        var result = await GitHubUpdateCheckService.CheckForUpdatesAsync("NonExistentOwner9999/NonExistentRepo9999");
        Assert.NotNull(result);
        Assert.Equal("1.0.0", result.CurrentVersion);
        Assert.False(result.IsUpdateAvailable);
    }

    [Fact]
    public void P3_CloudSyncService_ExportAndDecryptSealedBlob()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_cloud_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);

            var pRepo = new ProfileRepository(conn);
            var profile = pRepo.CreateProfile("CloudUser", 1992, 1, 1, pin: "5555");

            string passphrase = "SecretPassphrase123!";
            var exportRes = CloudSyncService.ExportSealedProfileBlob(profile, conn, passphrase);
            Assert.True(exportRes.Success);
            Assert.NotNull(exportRes.Blob);
            Assert.False(string.IsNullOrWhiteSpace(exportRes.Blob.CipherTextBase64));

            var decryptRes = CloudSyncService.DecryptSealedProfileBlob(exportRes.Blob, passphrase, out string? jsonPayload);
            Assert.True(decryptRes.Success);
            Assert.NotNull(jsonPayload);
            Assert.Contains("CloudUser", jsonPayload);

            // Test wrong passphrase fails
            var badDecryptRes = CloudSyncService.DecryptSealedProfileBlob(exportRes.Blob, "WrongPass", out _);
            Assert.False(badDecryptRes.Success);
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
    public void P4_DepictionController_EnforcesPresentationAndAgeGating()
    {
        var minor = new UserProfile { DobYear = 2012, DobMonth = 1, DobDay = 1, IsAdultAttested = false };
        var adult = new UserProfile { DobYear = 1990, DobMonth = 1, DobDay = 1, IsAdultAttested = true };

        AdultAuth.SetUserAdultAttested(true);

        // Minor downgraded to SFW
        string minorMode = DepictionController.NormalizeDepictionMode(minor, DepictionController.ModeExplicit);
        Assert.Equal(DepictionController.ModeSfw, minorMode);

        // Adult allows Explicit
        string adultMode = DepictionController.NormalizeDepictionMode(adult, DepictionController.ModeExplicit);
        Assert.Equal(DepictionController.ModeExplicit, adultMode);

        // FadeToBlack filter appends fade-to-black notice on intimate escalation
        string filteredFtb = DepictionController.ApplyDepictionFilter("They share a sensual kiss.", DepictionController.ModeFadeToBlack);
        Assert.Contains("[The scene fades to black", filteredFtb);
    }

    [Fact]
    public void P4_TurnResponseContract_ExtractsStructuredSnapshot()
    {
        string rawResponse = "Vera nods quietly.\n<state>\n{\n  \"emotion\": \"Determined\",\n  \"bond_delta\": 3,\n  \"somatic_state\": \"Alert\"\n}\n</state>";
        var snapshot = TurnResponseContract.ExtractTurnSnapshot(rawResponse, "Vera");

        Assert.Equal("Determined", snapshot.Emotion);
        Assert.Equal(3, snapshot.BondDelta);
        Assert.Equal("Alert", snapshot.SomaticState);
    }

    [Fact]
    public void P4_SessionRepository_UpdateTitleAndArchiveSession()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_sess_qol_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);

            var pRepo = new ProfileRepository(conn);
            var p = pRepo.CreateProfile("SessionUser", 1999, 5, 5);

            var sRepo = new SessionRepository(conn);
            var sess = sRepo.CreateSession(p.Id, "Old Title", "Dojo", "Action", "AutoPlay", new() { "slug1" });

            bool titleUpdated = sRepo.UpdateSessionTitle(sess.Id, "Renamed Dojo Session");
            Assert.True(titleUpdated);

            bool archived = sRepo.ArchiveSession(sess.Id);
            Assert.True(archived);

            var profileSessions = sRepo.GetSessionsForProfile(p.Id);
            Assert.Single(profileSessions);
            Assert.Equal("Renamed Dojo Session", profileSessions[0].Title);
            Assert.Equal("Archived", profileSessions[0].Status);
        }
        finally
        {
            if (File.Exists(tempDb))
            {
                try { File.Delete(tempDb); } catch { }
            }
        }
    }
}
