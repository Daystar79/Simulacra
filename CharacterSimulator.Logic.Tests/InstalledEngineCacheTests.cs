using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using CharacterSimulator.Logic.Data.Db;
using CharacterSimulator.Logic.Services;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

[Collection("StaticStateTests")]
public class InstalledEngineCacheTests
{
    [Fact]
    public void Repository_ReplaceAndList_RoundTripsRoleplayAndImage()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_engines_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);
            var repo = new InstalledEngineRepository(conn);

            Assert.False(repo.HasCategory(InstalledEngineRecord.CategoryRoleplay));

            repo.ReplaceCategory(InstalledEngineRecord.CategoryRoleplay, new[]
            {
                new InstalledEngineRecord
                {
                    EngineId = "AGY",
                    DisplayName = "AGY",
                    IsAvailable = true,
                    StatusDetail = "ok",
                    SortOrder = 0,
                    ScannedAt = DateTime.UtcNow
                },
                new InstalledEngineRecord
                {
                    EngineId = "MockEngine",
                    DisplayName = "Mock",
                    IsAvailable = true,
                    SortOrder = 1,
                    ScannedAt = DateTime.UtcNow
                }
            });

            repo.ReplaceCategory(InstalledEngineRecord.CategoryImage, new[]
            {
                new InstalledEngineRecord
                {
                    EngineId = "PollinationsAI",
                    DisplayName = "Pollinations",
                    IsAvailable = true,
                    EngineType = "PollinationsAI",
                    SortOrder = 0,
                    ScannedAt = DateTime.UtcNow
                },
                new InstalledEngineRecord
                {
                    EngineId = "AgentGrok",
                    DisplayName = "Grok",
                    IsAvailable = true,
                    EngineType = "AgentGrok",
                    SortOrder = 1,
                    ScannedAt = DateTime.UtcNow
                }
            });

            Assert.True(repo.HasCategory(InstalledEngineRecord.CategoryRoleplay));
            Assert.True(repo.HasCategory(InstalledEngineRecord.CategoryImage));

            var roleplay = repo.ListByCategory(InstalledEngineRecord.CategoryRoleplay);
            Assert.Equal(2, roleplay.Count);
            Assert.Equal("AGY", roleplay[0].EngineId);
            Assert.True(roleplay[0].IsAvailable);

            var image = repo.ListByCategory(InstalledEngineRecord.CategoryImage);
            Assert.Equal(2, image.Count);
            Assert.Equal("PollinationsAI", image[0].EngineId);
            Assert.Equal("AgentGrok", image[1].EngineType);

            // Replace roleplay only — image untouched
            repo.ReplaceCategory(InstalledEngineRecord.CategoryRoleplay, new[]
            {
                new InstalledEngineRecord
                {
                    EngineId = "MockEngine",
                    DisplayName = "Mock only",
                    IsAvailable = true,
                    SortOrder = 0,
                    ScannedAt = DateTime.UtcNow
                }
            });
            Assert.Single(repo.ListByCategory(InstalledEngineRecord.CategoryRoleplay));
            Assert.Equal(2, repo.ListByCategory(InstalledEngineRecord.CategoryImage).Count);

            Assert.NotNull(repo.GetLastScanUtc(InstalledEngineRecord.CategoryImage));
        }
        finally
        {
            try { if (File.Exists(tempDb)) File.Delete(tempDb); } catch { }
        }
    }

    [Fact]
    public async Task Detectors_PersistScanAndServeCacheOnSoftLookup()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_engines_store_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);
            var repo = new InstalledEngineRepository(conn);
            InstalledEngineStore.Bind(repo);

            // Seed image cache directly so soft detect skips live agent probes
            repo.ReplaceCategory(InstalledEngineRecord.CategoryImage, new[]
            {
                new InstalledEngineRecord
                {
                    EngineId = ImageEngineDetector.DefaultEngineId,
                    DisplayName = "✨ Pollinations AI (cached)",
                    IsAvailable = true,
                    EngineType = "PollinationsAI",
                    StatusDetail = "from test",
                    SortOrder = 0,
                    ScannedAt = DateTime.UtcNow
                }
            });

            var soft = await ImageEngineDetector.DetectAvailableImageEnginesAsync(
                probeAgents: true, forceReprobe: false);
            Assert.NotEmpty(soft);
            Assert.Equal(ImageEngineDetector.DefaultEngineId, soft[0].Id);
            Assert.Contains("cached", soft[0].DisplayName, StringComparison.OrdinalIgnoreCase);

            // Roleplay: first force scan writes DB; second soft read hits cache
            var live = await LlmEngineDetector.DetectAvailableEnginesAsync(forceRefresh: true);
            Assert.NotEmpty(live);
            Assert.True(repo.HasCategory(InstalledEngineRecord.CategoryRoleplay));

            // Corrupt cache with a marker display name and confirm soft path returns it
            repo.ReplaceCategory(InstalledEngineRecord.CategoryRoleplay, new[]
            {
                new InstalledEngineRecord
                {
                    EngineId = "MockEngine",
                    DisplayName = "🧪 CACHE MARKER",
                    IsAvailable = true,
                    StatusDetail = "forced cache",
                    SortOrder = 0,
                    ScannedAt = DateTime.UtcNow
                }
            });

            var cached = await LlmEngineDetector.DetectAvailableEnginesAsync(forceRefresh: false);
            Assert.Single(cached);
            Assert.Equal("🧪 CACHE MARKER", cached[0].DisplayName);

            // Force refresh must re-scan (more than just the marker)
            var forced = await LlmEngineDetector.DetectAvailableEnginesAsync(forceRefresh: true);
            Assert.True(forced.Count >= 2);
            Assert.Contains(forced, e => e.Id == "MockEngine");
            Assert.DoesNotContain(forced, e => e.DisplayName == "🧪 CACHE MARKER");
        }
        finally
        {
            InstalledEngineStore.Bind(null);
            try { if (File.Exists(tempDb)) File.Delete(tempDb); } catch { }
        }
    }

    [Fact]
    public void Store_SaveAndGet_RoundTripsThroughBind()
    {
        string tempDb = Path.Combine(Path.GetTempPath(), $"test_engines_bind_{Guid.NewGuid():N}.db");
        try
        {
            using var conn = AppDbInitializer.CreateConnection(tempDb);
            AppDbInitializer.InitializeDatabase(conn);
            InstalledEngineStore.Bind(new InstalledEngineRepository(conn));

            InstalledEngineStore.SaveRoleplay(new List<DetectedLlmEngine>
            {
                new("AGY", "AGY CLI", true, "path ok"),
                new("MockEngine", "Mock", true, "always")
            });
            InstalledEngineStore.SaveImage(new List<DetectedImageEngine>
            {
                new(ImageEngineDetector.DefaultEngineId, "Pollinations", true, "default",
                    ImageGeneratorEngine.PollinationsAI)
            });

            Assert.True(InstalledEngineStore.HasRoleplayCache());
            Assert.True(InstalledEngineStore.HasImageCache());

            var rp = InstalledEngineStore.TryGetRoleplayCached();
            Assert.NotNull(rp);
            Assert.Equal(2, rp!.Count);
            Assert.Equal("AGY", rp[0].Id);

            var img = InstalledEngineStore.TryGetImageCached();
            Assert.NotNull(img);
            Assert.Contains(img!, e => e.Id == ImageEngineDetector.DefaultEngineId);
            Assert.Equal(ImageGeneratorEngine.PollinationsAI, img![0].EngineType);
        }
        finally
        {
            InstalledEngineStore.Bind(null);
            try { if (File.Exists(tempDb)) File.Delete(tempDb); } catch { }
        }
    }
}
