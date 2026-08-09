using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using CharacterSimulator.Logic.Data.Db;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic;

/// <summary>
/// Discovers loadable character card files under Characters/.
/// Card files use opaque random IDs as filenames; display names come from card content
/// (preferably via the SQLite character_catalog index when bound).
/// </summary>
public static class CharacterCatalog
{
    private static readonly object IndexLock = new();
    private static CharacterCatalogRepository? _index;

    private static readonly HashSet<string> ExcludedNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "HOW_TO_CARD.md",
        "Relations.md",
        "README.md",
    };

    /// <summary>
    /// A discovered card: stable file identity + human-facing name from the card body.
    /// </summary>
    public record CharacterCardRef(
        string FileName,
        string DisplayName,
        string CardId,
        string Description = "",
        string AvatarPath = "");

    /// <summary>
    /// Wire the SQLite catalog index (called from ProfileService on startup).
    /// When bound, ListCards prefers the index over full-file scans.
    /// </summary>
    public static void BindIndex(CharacterCatalogRepository? repository)
    {
        lock (IndexLock)
        {
            _index = repository;
        }
    }

    public static bool HasIndex
    {
        get { lock (IndexLock) return _index != null; }
    }

    /// <summary>
    /// Reconcile SQLite index with Characters/ on disk (mtime/size fingerprint).
    /// Safe no-op when no index is bound.
    /// </summary>
    public static int ReconcileFromDisk(string? baseDir = null)
    {
        CharacterCatalogRepository? repo;
        lock (IndexLock) repo = _index;
        if (repo == null) return 0;

        string charDir = ResolveCharactersDirectory(baseDir);
        return repo.ReconcileFromDisk(charDir);
    }

    /// <summary>
    /// Upsert one card into the SQLite index after create/derive/save.
    /// </summary>
    public static CharacterCatalogRecord? UpsertIndexFromFile(
        string cardPath,
        string? sourceLabel = null,
        bool? isDerived = null)
    {
        CharacterCatalogRepository? repo;
        lock (IndexLock) repo = _index;
        if (repo == null) return null;
        return repo.UpsertFromFile(cardPath, sourceLabel, isDerived);
    }

    public static string ResolveCharactersDirectory(string? baseDir = null)
    {
        var candidates = new List<string>();

        // 1. App executable output directory
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        candidates.Add(Path.Combine(appDir, "Characters"));

        // 2. Working directory
        string current = baseDir ?? Directory.GetCurrentDirectory();
        candidates.Add(Path.Combine(current, "Characters"));

        // 3. Parent directories up to root
        string? parent = Directory.GetParent(current)?.FullName;
        if (parent != null)
        {
            candidates.Add(Path.Combine(parent, "Characters"));
            string? grandParent = Directory.GetParent(parent)?.FullName;
            if (grandParent != null)
            {
                candidates.Add(Path.Combine(grandParent, "Characters"));
            }
        }

        foreach (var dir in candidates)
        {
            if (Directory.Exists(dir) && Directory.GetFiles(dir).Any(IsLoadableCardFile))
                return dir;
        }

        // Fallback: create Characters directory under appDir and seed default cards
        string targetDir = Path.Combine(appDir, "Characters");
        EnsureFallbackCharactersSeeded(targetDir);
        return targetDir;
    }

    /// <summary>
    /// Generates a new opaque card id (16 lowercase hex chars). Used as the file stem.
    /// </summary>
    public static string GenerateCardId()
    {
        Span<byte> bytes = stackalloc byte[8];
        RandomNumberGenerator.Fill(bytes);
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    /// <summary>
    /// Full card filename for a newly allocated id, e.g. "a1b2c3d4e5f60718.json".
    /// </summary>
    public static string GenerateCardFileName() => GenerateCardId() + ".json";

    /// <summary>
    /// Allocates a unique card path under the Characters directory (file is not created).
    /// </summary>
    public static string AllocateCardPath(string? baseDir = null)
    {
        string charDir = ResolveCharactersDirectory(baseDir);
        if (!Directory.Exists(charDir))
            Directory.CreateDirectory(charDir);

        for (int attempt = 0; attempt < 16; attempt++)
        {
            string fileName = GenerateCardFileName();
            string path = Path.Combine(charDir, fileName);
            if (!File.Exists(path))
                return path;
        }

        // Extremely unlikely collision path
        return Path.Combine(charDir, Guid.NewGuid().ToString("N") + ".json");
    }

    public static string GetCardId(string fileNameOrPath)
    {
        if (string.IsNullOrWhiteSpace(fileNameOrPath)) return "";
        return Path.GetFileNameWithoutExtension(fileNameOrPath);
    }

    private static void EnsureFallbackCharactersSeeded(string charDir)
    {
        try
        {
            if (!Directory.Exists(charDir))
                Directory.CreateDirectory(charDir);

            // Seed only when the folder has no loadable cards
            if (Directory.GetFiles(charDir).Any(IsLoadableCardFile))
                return;

            string cardId = GenerateCardId();
            string defaultCard = Path.Combine(charDir, cardId + ".json");
            File.WriteAllText(defaultCard,
@"{
  ""name"": ""Serena"",
  ""call_name"": ""Serena"",
  ""age"": 24,
  ""canon_adult"": true,
  ""physical"": ""Slender, athletic build with expressive blue eyes and silver-tinted hair."",
  ""character_style"": ""Simple layered lounge wear; minimal jewelry."",
  ""personality"": ""Quiet observer who values composure and self-reliance."",
  ""behavior"": ""Watches first, speaks second; under pressure stays still and measured."",
  ""active_focus"": ""Realm I — Form"",
  ""cognitive_bias"": ""Self-reliance and quiet observation."",
  ""cognitive_gift"": ""Unflappable composure under pressure."",
  ""default_somatic_alignment"": ""Calm, steady breathing."",
  ""somatic_zones"": [
    ""Face/Eyes: calm gaze"",
    ""Chest/Breath: steady, rhythmic breath""
  ],
  ""voice"": {
    ""baseline"": ""Clear, low, measured tone."",
    ""syntactical_engine"": ""Linear sentences with calm cadence."",
    ""conversational_stance"": ""collaborative""
  }
}
");
        }
        catch (Exception ex)
        {
            AppLogger.Warning("[CharacterCatalog] Seed fallback failed: " + ex.Message);
        }
    }

    public static bool IsLoadableCardFile(string pathOrFileName)
    {
        string name = Path.GetFileName(pathOrFileName);
        if (string.IsNullOrEmpty(name) || name.StartsWith('_')) return false;
        if (ExcludedNames.Contains(name)) return false;
        if (name.EndsWith("_state.json", StringComparison.OrdinalIgnoreCase)) return false;
        if (name.EndsWith("_log.yaml", StringComparison.OrdinalIgnoreCase) ||
            name.EndsWith("_log.yml", StringComparison.OrdinalIgnoreCase)) return false;

        string ext = Path.GetExtension(name);
        // Catalog is JSON-first; legacy .md cards remain loadable by path but are not listed.
        return ext.Equals(".json", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Lists cards sorted by display name. Prefers SQLite index when bound;
    /// falls back to file scan (and backfills the index when possible).
    /// </summary>
    public static List<CharacterCardRef> ListCards(string? baseDir = null)
    {
        CharacterCatalogRepository? repo;
        lock (IndexLock) repo = _index;

        if (repo != null)
        {
            // Fast path: serve SQLite index as-is (no disk walk). Use ListCardsFresh after imports.
            var rows = repo.ListAll();
            if (rows.Count > 0)
            {
                return rows.Select(r => new CharacterCardRef(
                    r.FileName,
                    r.DisplayName,
                    r.CardId,
                    r.Description,
                    r.AvatarPath)).ToList();
            }

            // Empty index only — one reconcile to seed
            try
            {
                repo.ReconcileFromDisk(ResolveCharactersDirectory(baseDir));
                rows = repo.ListAll();
                if (rows.Count > 0)
                {
                    return rows.Select(r => new CharacterCardRef(
                        r.FileName,
                        r.DisplayName,
                        r.CardId,
                        r.Description,
                        r.AvatarPath)).ToList();
                }
            }
            catch (Exception ex)
            {
                AppLogger.Warning("[CharacterCatalog] Reconcile: " + ex.Message);
            }
        }

        return ListCardsFromFiles(baseDir);
    }

    /// <summary>
    /// Force a disk reconcile then return index/file listing (used by UI Refresh).
    /// </summary>
    public static List<CharacterCardRef> ListCardsFresh(string? baseDir = null)
    {
        ReconcileFromDisk(baseDir);
        return ListCards(baseDir);
    }

    private static List<CharacterCardRef> ListCardsFromFiles(string? baseDir = null)
    {
        string charDir = ResolveCharactersDirectory(baseDir);
        if (!Directory.Exists(charDir)) return new List<CharacterCardRef>();

        return Directory.GetFiles(charDir)
            .Where(IsLoadableCardFile)
            .Select(path =>
            {
                string fileName = Path.GetFileName(path);
                string cardId = GetCardId(fileName);
                string displayName = ReadDisplayNameFromFile(path, fileName);
                return new CharacterCardRef(fileName, displayName, cardId);
            })
            .OrderBy(c => c.DisplayName, StringComparer.OrdinalIgnoreCase)
            .ThenBy(c => c.FileName, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    /// <summary>
    /// Filenames only (opaque card ids + .json), ordered by display name for selector stability.
    /// </summary>
    public static List<string> ListCardFileNames(string? baseDir = null)
    {
        return ListCards(baseDir).Select(c => c.FileName).ToList();
    }

    public record LoadedCharacterCardInfo(
        string Name,
        int Age,
        /// <summary>Who they are (temperament/values). Not body.</summary>
        string Personality,
        /// <summary>How they act under pressure/trust. Not appearance.</summary>
        string Behavior,
        /// <summary>Body identity only.</summary>
        string Physical,
        /// <summary>Default dress / accessories.</summary>
        string CharacterStyle,
        string CognitiveGift,
        List<string> Goals,
        List<string> Likes,
        List<string> Skills,
        string AvatarPath
    )
    {
        /// <summary>Legacy alias used by older callers; equals Personality.</summary>
        public string Description => Personality;
    };

    public static string GetCharacterDisplayName(string fileName, string? baseDir = null)
    {
        if (string.IsNullOrEmpty(fileName) || fileName.StartsWith("("))
            return fileName;

        // Prefer SQLite index
        CharacterCatalogRepository? repo;
        lock (IndexLock) repo = _index;
        if (repo != null)
        {
            var row = repo.GetByFileName(fileName) ?? repo.GetByCardId(GetCardId(fileName));
            if (row != null && !string.IsNullOrWhiteSpace(row.DisplayName))
                return row.DisplayName;
        }

        string charDir = ResolveCharactersDirectory(baseDir);
        string filePath = Path.Combine(charDir, fileName);

        if (!File.Exists(filePath))
            return "Unknown Character";

        return ReadDisplayNameFromFile(filePath, fileName);
    }

    private static string ReadDisplayNameFromFile(string filePath, string fileName)
    {
        try
        {
            string content = File.ReadAllText(filePath);
            if (fileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase) ||
                filePath.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                using var doc = JsonDocument.Parse(content);
                var root = doc.RootElement;
                if (root.TryGetProperty("name", out var n))
                {
                    string? name = n.GetString();
                    if (!string.IsNullOrWhiteSpace(name))
                        return name.Trim();
                }
                if (root.TryGetProperty("call_name", out var cn))
                {
                    string? callName = cn.GetString();
                    if (!string.IsNullOrWhiteSpace(callName))
                        return callName.Trim();
                }
            }
            else
            {
                foreach (var line in content.Split('\n'))
                {
                    var trimmed = line.Trim();
                    if (trimmed.StartsWith("name:", StringComparison.OrdinalIgnoreCase))
                    {
                        string name = trimmed[5..].Trim(' ', '"', '\'');
                        if (!string.IsNullOrWhiteSpace(name))
                            return name;
                    }
                }
            }
        }
        catch { }

        string id = GetCardId(fileName);
        if (id.Length > 8)
            return $"Unnamed ({id[..8]})";
        return string.IsNullOrEmpty(id) ? "Unnamed Character" : $"Unnamed ({id})";
    }

    public static LoadedCharacterCardInfo LoadCardDetails(string fileName, string? baseDir = null)
    {
        if (string.IsNullOrEmpty(fileName) || fileName.StartsWith("("))
            return new LoadedCharacterCardInfo("(No Character Selected)", 0, "No character card loaded.", "", "", "", "", new(), new(), new(), "");

        string charDir = ResolveCharactersDirectory(baseDir);
        string filePath = Path.Combine(charDir, fileName);

        if (!File.Exists(filePath))
            return new LoadedCharacterCardInfo("Unknown Character", 0, "Character card file not found.", "", "", "", "", new(), new(), new(), "");

        string content = File.ReadAllText(filePath);
        string name = "";
        int age = 0;
        string personality = "";
        string behavior = "";
        string physical = "";
        string characterStyle = "";
        string cognitiveGift = "";
        var goals = new List<string>();
        var likes = new List<string>();
        var skills = new List<string>();

        if (fileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            try
            {
                using var doc = JsonDocument.Parse(content);
                var root = doc.RootElement;
                if (root.TryGetProperty("name", out var n)) name = n.GetString() ?? "";
                if (string.IsNullOrWhiteSpace(name) && root.TryGetProperty("call_name", out var cn))
                    name = cn.GetString() ?? "";
                if (root.TryGetProperty("age", out var a) && a.ValueKind == JsonValueKind.Number)
                    age = a.GetInt32();

                personality = CardFieldFormatter.ReadPersonality(root);
                behavior = CardFieldFormatter.ReadBehavior(root);
                physical = CardFieldFormatter.FlattenPhysical(root);
                characterStyle = CardFieldFormatter.FlattenCharacterStyle(root);

                if (root.TryGetProperty("cognitive_gift", out var cg))
                    cognitiveGift = cg.GetString() ?? "";

                if (root.TryGetProperty("somatic_zones", out var sz) && sz.ValueKind == JsonValueKind.Array)
                {
                    foreach (var elem in sz.EnumerateArray())
                    {
                        var str = elem.GetString();
                        if (!string.IsNullOrEmpty(str)) likes.Add(str.Split(':')[0].Trim());
                    }
                }

                if (root.TryGetProperty("depth_of_knowledge", out var dok) &&
                    dok.ValueKind == JsonValueKind.Object &&
                    dok.TryGetProperty("general", out var gen))
                {
                    var genStr = gen.GetString();
                    if (!string.IsNullOrEmpty(genStr))
                    {
                        foreach (var s in genStr.Split(',', ';'))
                        {
                            string trimmed = s.Trim();
                            if (!string.IsNullOrEmpty(trimmed)) skills.Add(trimmed);
                        }
                    }
                }

                if (root.TryGetProperty("hobbies", out var hobbies) && hobbies.ValueKind == JsonValueKind.Array)
                {
                    foreach (var h in hobbies.EnumerateArray())
                    {
                        string? hs = h.GetString();
                        if (!string.IsNullOrWhiteSpace(hs) && likes.Count < 8)
                            likes.Add(hs.Trim());
                    }
                }
            }
            catch { }
        }
        else
        {
            // Markdown parsing (legacy line scan)
            var lines = content.Split('\n');
            bool inYaml = false;
            foreach (var line in lines)
            {
                var trimmed = line.Trim();
                if (trimmed == "---")
                {
                    inYaml = !inYaml;
                    continue;
                }

                if (trimmed.StartsWith("name:", StringComparison.OrdinalIgnoreCase))
                    name = trimmed[5..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("age:", StringComparison.OrdinalIgnoreCase))
                    int.TryParse(trimmed[4..].Trim(' ', '"', '\''), out age);
                else if (trimmed.StartsWith("personality:", StringComparison.OrdinalIgnoreCase))
                    personality = trimmed["personality:".Length..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("behavior:", StringComparison.OrdinalIgnoreCase))
                    behavior = trimmed["behavior:".Length..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("cultural_bias:", StringComparison.OrdinalIgnoreCase) && string.IsNullOrEmpty(personality))
                    personality = trimmed[14..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("physical:", StringComparison.OrdinalIgnoreCase))
                    physical = trimmed[9..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("character_style:", StringComparison.OrdinalIgnoreCase))
                    characterStyle = trimmed["character_style:".Length..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("cognitive_gift:", StringComparison.OrdinalIgnoreCase))
                    cognitiveGift = trimmed[15..].Trim(' ', '"', '\'');
                else if (trimmed.StartsWith("active_focus:", StringComparison.OrdinalIgnoreCase))
                    goals.Add(trimmed[13..].Trim(' ', '"', '\''));
                else if (trimmed.StartsWith("- \"") || trimmed.StartsWith("- '") || (inYaml && trimmed.StartsWith("- ")))
                {
                    var val = trimmed.TrimStart('-', ' ', '"', '\'').TrimEnd('"', '\'');
                    if (val.Contains(':')) val = val.Split(':')[0].Trim();
                    if (!string.IsNullOrEmpty(val) && likes.Count < 6) likes.Add(val);
                }
            }
        }

        if (string.IsNullOrWhiteSpace(name))
            name = GetCharacterDisplayName(fileName, baseDir);

        // Never fall physical into personality — leave blank if unknown
        if (string.IsNullOrWhiteSpace(personality))
            personality = string.IsNullOrWhiteSpace(name) ? "" : $"{name} — personality not specified on card.";

        if (goals.Count == 0)
        {
            goals.Add("Maintain emotional stability & composure");
            goals.Add("Engage in collaborative dialogue");
        }

        if (likes.Count == 0)
        {
            likes.Add("Quiet Observation");
            likes.Add("Strategic Stance");
            likes.Add("Embodied Presence");
        }

        if (skills.Count == 0)
        {
            skills.Add("Somatic Grounding");
            skills.Add("Tactical Observation");
            skills.Add("Empathy Tuning");
        }

        string cardId = GetCardId(fileName);
        // Prefer SQLite portrait BLOB → data URI; else file on disk
        string avatarPath = "";
        try
        {
            string? dbUri = Services.CharacterPortraitService.TryGetStoredDataUri(cardId);
            if (!string.IsNullOrEmpty(dbUri))
                avatarPath = dbUri;
        }
        catch { }

        if (string.IsNullOrEmpty(avatarPath))
            avatarPath = ResolveAvatarPath(charDir, cardId, name);

        return new LoadedCharacterCardInfo(
            name, age, personality, behavior, physical, characterStyle,
            cognitiveGift, goals, likes, skills, avatarPath);
    }

    private static string ResolveAvatarPath(string charDir, string cardId, string displayName)
    {
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        var stems = new List<string>();
        if (!string.IsNullOrWhiteSpace(cardId)) stems.Add(cardId);
        if (!string.IsNullOrWhiteSpace(displayName))
        {
            stems.Add(displayName);
            stems.Add(displayName.ToLowerInvariant());
            stems.Add(displayName.Replace(' ', '_').ToLowerInvariant());
        }

        string[] dirs =
        {
            charDir,
            Path.Combine(appDir, "Assets", "Portraits"),
            Path.Combine(Directory.GetCurrentDirectory(), "CharacterSimulator.GUI", "Assets", "Portraits"),
            Path.Combine(Directory.GetCurrentDirectory(), "Assets", "Portraits"),
        };

        string[] exts = { ".png", ".jpg", ".jpeg", ".webp" };

        foreach (var stem in stems.Where(s => !string.IsNullOrWhiteSpace(s)).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            foreach (var dir in dirs)
            {
                if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) continue;
                foreach (var ext in exts)
                {
                    string candidate = Path.Combine(dir, stem + ext);
                    if (File.Exists(candidate)) return candidate;
                }
            }
        }

        return "";
    }
}
