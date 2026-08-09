using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic.Data.Db;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// Portrait lookup: SQLite BLOB by card_id. On character load, return stored image
/// or generate once and upsert.
/// </summary>
public static class CharacterPortraitService
{
    private static readonly object BindLock = new();
    private static CharacterPortraitRepository? _portraits;
    private static CharacterCatalogRepository? _catalog;

    /// <summary>In-flight generates so double-select doesn't spam the image API.</summary>
    private static readonly ConcurrentDictionary<string, SemaphoreSlim> Locks =
        new(StringComparer.OrdinalIgnoreCase);

    public static void Bind(CharacterPortraitRepository? portraits, CharacterCatalogRepository? catalog = null)
    {
        lock (BindLock)
        {
            _portraits = portraits;
            if (catalog != null)
                _catalog = catalog;
        }
    }

    public static bool HasStore
    {
        get { lock (BindLock) return _portraits != null; }
    }

    public static bool HasPortrait(string cardId)
    {
        if (string.IsNullOrWhiteSpace(cardId)) return false;
        if (TryGetStoredDataUri(cardId) != null) return true;
        CharacterPortraitRepository? repo;
        lock (BindLock) repo = _portraits;
        return repo != null && repo.Exists(cardId);
    }

    /// <summary>
    /// Try to resolve an emotion-specific portrait sprite URI for a character and emotion name
    /// (e.g. cardId="kira", emotion="Smirking" -> looks for kira_smirking.png or DB record "kira_smirking").
    /// Returns null if no emotion-specific sprite file or DB record is found.
    /// </summary>
    public static string? TryGetExpressionDataUri(string cardId, string? emotion)
    {
        if (string.IsNullOrWhiteSpace(cardId) || string.IsNullOrWhiteSpace(emotion)) return null;

        string normEmotion = emotion.Trim().ToLowerInvariant()
            .Replace(" ", "_")
            .Replace("-", "_");

        string key = $"{cardId}_{normEmotion}";

        CharacterPortraitRepository? repo;
        lock (BindLock) repo = _portraits;
        if (repo != null)
        {
            string? uri = repo.GetDataUri(key);
            if (!string.IsNullOrEmpty(uri))
                return uri;
        }

        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string charDir = CharacterCatalog.ResolveCharactersDirectory();
        string[] candidates = new[]
        {
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", key + ".png"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", key + ".jpg"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", key + ".jpeg"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", cardId, normEmotion + ".png"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", cardId, normEmotion + ".jpg"),
            System.IO.Path.Combine(charDir, key + ".png"),
            System.IO.Path.Combine(charDir, key + ".jpg"),
            System.IO.Path.Combine(charDir, cardId, normEmotion + ".png"),
            System.IO.Path.Combine(charDir, cardId, normEmotion + ".jpg")
        };

        foreach (var file in candidates)
        {
            if (System.IO.File.Exists(file))
            {
                try
                {
                    byte[] bytes = System.IO.File.ReadAllBytes(file);
                    string mime = file.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? "image/png" : "image/jpeg";
                    if (repo != null)
                        return SavePortrait(key, bytes, mime);
                    else
                        return $"data:{mime};base64,{Convert.ToBase64String(bytes)}";
                }
                catch { }
            }
        }

        return null;
    }

    /// <summary>
    /// Resolves best available display URI for a character:
    /// Emotion sprite URI if available -> Base character portrait URI -> null.
    /// </summary>
    public static string? GetBestPortraitUri(string cardId, string? emotion = null)
    {
        if (string.IsNullOrWhiteSpace(cardId)) return null;

        if (!string.IsNullOrWhiteSpace(emotion))
        {
            string? exprUri = TryGetExpressionDataUri(cardId, emotion);
            if (!string.IsNullOrEmpty(exprUri))
                return exprUri;
        }

        return TryGetStoredDataUri(cardId);
    }

    /// <summary>
    /// Resolve display URI for a card: DB BLOB → data URI; else disk cache file → auto-import to DB; else null.
    /// </summary>
    public static string? TryGetStoredDataUri(string cardId)
    {
        if (string.IsNullOrWhiteSpace(cardId)) return null;

        CharacterPortraitRepository? repo;
        lock (BindLock) repo = _portraits;

        if (repo != null)
        {
            string? uri = repo.GetDataUri(cardId);
            if (!string.IsNullOrEmpty(uri))
                return uri;
        }

        // Check cache files under Assets/Portraits or Characters/
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string charDir = CharacterCatalog.ResolveCharactersDirectory();
        string[] candidates = new[]
        {
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", cardId + ".jpg"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", cardId + ".png"),
            System.IO.Path.Combine(baseDir, "Assets", "Portraits", cardId + ".jpeg"),
            System.IO.Path.Combine(charDir, cardId + ".jpg"),
            System.IO.Path.Combine(charDir, cardId + ".png"),
            System.IO.Path.Combine(charDir, cardId + ".jpeg")
        };

        foreach (var file in candidates)
        {
            if (System.IO.File.Exists(file))
            {
                try
                {
                    byte[] bytes = System.IO.File.ReadAllBytes(file);
                    string mime = file.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? "image/png" : "image/jpeg";
                    if (repo != null)
                    {
                        return SavePortrait(cardId, bytes, mime);
                    }
                    else
                    {
                        return $"data:{mime};base64,{Convert.ToBase64String(bytes)}";
                    }
                }
                catch { }
            }
        }

        return null;
    }

    /// <summary>
    /// Save generated (or imported) portrait bytes for a card; updates catalog marker.
    /// </summary>
    public static string SavePortrait(
        string cardId,
        byte[] imageBytes,
        string mimeType = "image/jpeg",
        string? prompt = null,
        string? engine = null)
    {
        if (string.IsNullOrWhiteSpace(cardId))
            throw new ArgumentException("cardId required", nameof(cardId));
        if (imageBytes == null || imageBytes.Length == 0)
            throw new ArgumentException("image bytes required", nameof(imageBytes));

        CharacterPortraitRepository? repo;
        CharacterCatalogRepository? catalog;
        lock (BindLock)
        {
            repo = _portraits;
            catalog = _catalog;
        }

        if (repo == null)
            throw new InvalidOperationException("Portrait store not bound (ProfileService not initialized).");

        repo.UpsertBytes(cardId, imageBytes, mimeType, prompt, engine);
        CharacterPortraitRepository.WriteCacheFile(cardId, imageBytes,
            mimeType.Contains("png", StringComparison.OrdinalIgnoreCase) ? ".png" : ".jpg");

        // Catalog phone book: marker so ListCards knows a portrait exists
        try
        {
            var row = catalog?.GetByCardId(cardId);
            if (row != null)
            {
                row.AvatarPath = CharacterPortraitRepository.AvatarMarker(cardId);
                catalog!.Upsert(row);
            }
        }
        catch { /* catalog optional */ }

        return repo.GetDataUri(cardId) ?? "";
    }

    /// <summary>
    /// On character load: if portrait in SQLite or disk cache, return it; otherwise generate, store, return.
    /// Returns empty string if generation fails or cardId invalid.
    /// </summary>
    public static async Task<string> EnsurePortraitAsync(
        string cardId,
        string appearancePrompt,
        ImageGeneratorEngine engine = ImageGeneratorEngine.PollinationsAI,
        bool generateIfMissing = true,
        CancellationToken ct = default,
        string? modelId = null)
    {
        if (string.IsNullOrWhiteSpace(cardId))
            return "";

        // Fast path: already in DB or disk cache
        string? existing = TryGetStoredDataUri(cardId);
        if (!string.IsNullOrEmpty(existing))
            return existing;

        if (!generateIfMissing)
            return "";

        CharacterPortraitRepository? repo;
        lock (BindLock) repo = _portraits;

        if (!generateIfMissing)
            return "";

        var gate = Locks.GetOrAdd(cardId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // Re-check after lock (another load may have finished)
            if (repo != null)
            {
                string? stored = repo.GetDataUri(cardId);
                if (!string.IsNullOrEmpty(stored))
                    return stored;
            }

            string? artStyleId = null;
            try { artStyleId = AppConfigService.LoadSettings()?.ImageArtStyle; }
            catch { /* optional */ }

            var result = await AiImageGeneratorService.GeneratePortraitDetailedAsync(
                appearancePrompt,
                cardId,
                engine,
                ct,
                modelId,
                allowPollinationsFallback: true,
                artStyleId: artStyleId).ConfigureAwait(false);

            if (result.ImageBytes != null && result.ImageBytes.Length > 0 && repo != null)
            {
                return SavePortrait(
                    cardId,
                    result.ImageBytes,
                    result.MimeType,
                    appearancePrompt,
                    engine.ToString());
            }

            if (!string.IsNullOrEmpty(result.DisplayUri))
            {
                string? saved = await SaveFromDataUriOrUrlAsync(cardId, result.DisplayUri, appearancePrompt, engine.ToString(), ct)
                    .ConfigureAwait(false);
                if (!string.IsNullOrEmpty(saved))
                    return saved;
            }

            return result.DisplayUri ?? "";
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[CharacterPortraitService] Ensure failed for {cardId}: {ex.Message}");
            return "";
        }
        finally
        {
            gate.Release();
        }
    }

    /// <summary>
    /// Persist a data-URI or raw bytes from the manual Generate modal.
    /// </summary>
    public static string? SaveFromDataUriOrUrl(
        string cardId,
        string dataUriOrUrl,
        string? prompt = null,
        string? engine = null)
    {
        if (string.IsNullOrWhiteSpace(cardId) || string.IsNullOrWhiteSpace(dataUriOrUrl))
            return null;

        if (dataUriOrUrl.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            // data:image/jpeg;base64,....
            int comma = dataUriOrUrl.IndexOf(',');
            if (comma < 0) return null;
            string header = dataUriOrUrl[..comma];
            string b64 = dataUriOrUrl[(comma + 1)..];
            string mime = "image/jpeg";
            int mimeStart = header.IndexOf(':');
            int mimeEnd = header.IndexOf(';');
            if (mimeStart >= 0 && mimeEnd > mimeStart)
                mime = header[(mimeStart + 1)..mimeEnd];

            try
            {
                byte[] bytes = Convert.FromBase64String(b64);
                return SavePortrait(cardId, bytes, mime, prompt, engine);
            }
            catch
            {
                return null;
            }
        }

        // Non-data URI: leave as remote src; no BLOB without download
        return dataUriOrUrl;
    }

    /// <summary>
    /// Persist a data-URI or download a remote http/https URL and store as SQLite BLOB & cache file.
    /// </summary>
    public static async Task<string?> SaveFromDataUriOrUrlAsync(
        string cardId,
        string dataUriOrUrl,
        string? prompt = null,
        string? engine = null,
        CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(cardId) || string.IsNullOrWhiteSpace(dataUriOrUrl))
            return null;

        string? result = SaveFromDataUriOrUrl(cardId, dataUriOrUrl, prompt, engine);
        if (result != null && result.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
            return result;

        if ((dataUriOrUrl.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
             dataUriOrUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) && HasStore)
        {
            try
            {
                using var http = new System.Net.Http.HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                byte[] bytes = await http.GetByteArrayAsync(dataUriOrUrl, ct).ConfigureAwait(false);
                if (bytes is { Length: > 0 })
                {
                    string mime = dataUriOrUrl.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? "image/png" : "image/jpeg";
                    return SavePortrait(cardId, bytes, mime, prompt, engine);
                }
            }
            catch { }
        }

        return dataUriOrUrl;
    }
}
