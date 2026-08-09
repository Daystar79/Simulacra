using System;
using System.IO;
using System.Linq;
using CharacterSimulator.Logic;
using CharacterSimulator.Logic.Data.Db;
using Xunit;

[assembly: CollectionBehavior(DisableTestParallelization = true)]

namespace CharacterSimulator.Logic.Tests;

[Collection("StaticStateTests")]
public class CharacterCatalogIndexTests
{
    [Fact]
    public void ReconcileFromDisk_IndexesCardsAndSkipsUnchanged()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), $"cs_catalog_{Guid.NewGuid():N}");
        string charDir = Path.Combine(tempRoot, "Characters");
        string dbPath = Path.Combine(tempRoot, "app_data.db");
        Directory.CreateDirectory(charDir);

        try
        {
            string id1 = "aabbccddeeff0011";
            string id2 = "1122334455667788";
            File.WriteAllText(Path.Combine(charDir, id1 + ".json"),
                """{"name":"Alpha","call_name":"Al","age":30,"canon_adult":true,"personality":"Scout ethos","physical":"Tall frame, dark hair","character_style":"dark coat"}""");
            File.WriteAllText(Path.Combine(charDir, id2 + ".json"),
                """{"name":"Beta","age":22,"canon_adult":true,"personality":"Quiet wit","physical":"Short silver hair"}""");
            // Template / non-cards must be ignored
            File.WriteAllText(Path.Combine(charDir, "_template.json"), """{"name":"Template"}""");
            File.WriteAllText(Path.Combine(charDir, id1 + "_state.json"), """{"x":1}""");

            using var conn = AppDbInitializer.CreateConnection(dbPath);
            AppDbInitializer.InitializeDatabase(conn);
            var repo = new CharacterCatalogRepository(conn);

            int written = repo.ReconcileFromDisk(charDir);
            Assert.Equal(2, written);
            Assert.Equal(2, repo.Count());

            var all = repo.ListAll();
            Assert.Equal(2, all.Count);
            // Sorted by display name
            Assert.Equal("Alpha", all[0].DisplayName);
            Assert.Equal("Beta", all[1].DisplayName);
            Assert.Equal(id1 + ".json", all[0].FileName);
            Assert.Equal("Scout ethos", all[0].Description); // catalog description = personality
            Assert.Contains("Tall", all[0].PhysicalShort);
            Assert.DoesNotContain("coat", all[0].PhysicalShort); // style not mixed into physical

            // Second reconcile: fingerprints match → no writes
            int written2 = repo.ReconcileFromDisk(charDir);
            Assert.Equal(0, written2);
            Assert.Equal(2, repo.Count());

            // Edit Beta → one update
            File.WriteAllText(Path.Combine(charDir, id2 + ".json"),
                """{"name":"Beta Prime","age":22,"canon_adult":true,"physical":"Short silver hair"}""");
            // Ensure mtime/size fingerprint changes
            int written3 = repo.ReconcileFromDisk(charDir);
            Assert.Equal(1, written3);
            Assert.Equal("Beta Prime", repo.GetByCardId(id2)!.DisplayName);

            // Delete file → orphan removed
            File.Delete(Path.Combine(charDir, id1 + ".json"));
            repo.ReconcileFromDisk(charDir);
            Assert.Null(repo.GetByCardId(id1));
            Assert.Equal(1, repo.Count());
        }
        finally
        {
            try { Directory.Delete(tempRoot, recursive: true); } catch { }
        }
    }

    [Fact]
    public void CharacterCatalog_DisplayName_UsesBoundIndex()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), $"cs_catalog_bind_{Guid.NewGuid():N}");
        string charDir = Path.Combine(tempRoot, "Characters");
        string dbPath = Path.Combine(tempRoot, "app_data.db");
        Directory.CreateDirectory(charDir);

        try
        {
            string id = "deadbeefcafebabe";
            string cardPath = Path.Combine(charDir, id + ".json");
            File.WriteAllText(cardPath,
                """{"name":"IndexHero","age":28,"canon_adult":true,"personality":"From SQLite","physical":"Average height"}""");

            using var conn = AppDbInitializer.CreateConnection(dbPath);
            AppDbInitializer.InitializeDatabase(conn);
            var repo = new CharacterCatalogRepository(conn);
            CharacterCatalog.BindIndex(repo);

            var upserted = repo.UpsertFromFile(cardPath);
            Assert.NotNull(upserted);
            Assert.Equal("IndexHero", upserted!.DisplayName);

            // GetCharacterDisplayName should hit index (no file read required for path resolution)
            Assert.Equal("IndexHero", CharacterCatalog.GetCharacterDisplayName(id + ".json"));
            Assert.Equal("From SQLite", repo.GetByCardId(id)!.Description);
        }
        finally
        {
            CharacterCatalog.BindIndex(null);
            try { Directory.Delete(tempRoot, recursive: true); } catch { }
        }
    }

    [Fact]
    public void UpsertFromFile_SetsDerivedAndSourceLabel()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), $"cs_catalog_up_{Guid.NewGuid():N}");
        string charDir = Path.Combine(tempRoot, "Characters");
        string dbPath = Path.Combine(tempRoot, "app_data.db");
        Directory.CreateDirectory(charDir);

        try
        {
            string id = "0123456789abcdef";
            string path = Path.Combine(charDir, id + ".json");
            File.WriteAllText(path,
                """{"name":"DerivedOne","age":25,"canon_adult":true,"derived":true,"physical":"Blue eyes"}""");

            using var conn = AppDbInitializer.CreateConnection(dbPath);
            AppDbInitializer.InitializeDatabase(conn);
            var repo = new CharacterCatalogRepository(conn);

            var rec = repo.UpsertFromFile(path, sourceLabel: "Wikipedia: DerivedOne", isDerived: true);
            Assert.NotNull(rec);
            Assert.True(rec!.IsDerived);
            Assert.Equal("Wikipedia: DerivedOne", rec.SourceLabel);
            Assert.Equal("DerivedOne", repo.GetByFileName(id + ".json")!.DisplayName);
        }
        finally
        {
            try { Directory.Delete(tempRoot, recursive: true); } catch { }
        }
    }
}
