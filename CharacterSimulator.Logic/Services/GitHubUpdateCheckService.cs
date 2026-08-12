using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.Services;

public class UpdateCheckResult
{
    public bool IsUpdateAvailable { get; set; }
    public string LatestVersion { get; set; } = "";
    public string CurrentVersion { get; set; } = AppVersionInfo.CurrentVersion;
    public string ReleaseUrl { get; set; } = "";
    public string ReleaseNotes { get; set; } = "";
    public string? ErrorMessage { get; set; }
    public DateTime CheckedAt { get; set; } = DateTime.UtcNow;
}

public static class GitHubUpdateCheckService
{
    private static UpdateCheckResult? _cachedResult;
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(30);

    public static async Task<UpdateCheckResult> CheckForUpdatesAsync(string? customRepoSlug = null)
    {
        if (_cachedResult != null && (DateTime.UtcNow - _cachedResult.CheckedAt) < CacheDuration)
        {
            return _cachedResult;
        }

        string repoSlug = customRepoSlug ?? $"{AppVersionInfo.RepoOwner}/{AppVersionInfo.RepoName}";
        string url = $"https://api.github.com/repos/{repoSlug}/releases/latest";

        var result = new UpdateCheckResult
        {
            CurrentVersion = AppVersionInfo.CurrentVersion,
            CheckedAt = DateTime.UtcNow
        };

        try
        {
            using var client = new HttpClient();
            client.Timeout = TimeSpan.FromSeconds(5);
            client.DefaultRequestHeaders.Add("User-Agent", $"Simulacra-DesktopApp/{AppVersionInfo.CurrentVersion}");

            var response = await client.GetAsync(url);
            if (!response.IsSuccessStatusCode)
            {
                result.ErrorMessage = $"HTTP {(int)response.StatusCode}: {response.ReasonPhrase}";
                _cachedResult = result;
                return result;
            }

            string json = await response.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            if (root.TryGetProperty("tag_name", out var tagProp))
            {
                string tag = tagProp.GetString() ?? "";
                string latestSemver = tag.TrimStart('v', 'V');
                result.LatestVersion = latestSemver;

                if (root.TryGetProperty("html_url", out var urlProp))
                {
                    result.ReleaseUrl = urlProp.GetString() ?? "";
                }

                if (root.TryGetProperty("body", out var bodyProp))
                {
                    result.ReleaseNotes = bodyProp.GetString() ?? "";
                }

                if (IsNewerVersion(latestSemver, AppVersionInfo.CurrentVersion))
                {
                    result.IsUpdateAvailable = true;
                }
            }
        }
        catch (Exception ex)
        {
            // Fail open on network or API error
            result.ErrorMessage = ex.Message;
        }

        _cachedResult = result;
        return result;
    }

    private static bool IsNewerVersion(string latestStr, string currentStr)
    {
        if (Version.TryParse(latestStr, out var latest) && Version.TryParse(currentStr, out var current))
        {
            return latest > current;
        }
        return string.Compare(latestStr, currentStr, StringComparison.OrdinalIgnoreCase) > 0;
    }
}
