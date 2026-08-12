using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// Represents a model available from an LLM provider.
/// </summary>
public record LlmModel(
    string Id,
    string DisplayName,
    string ProviderId,
    string Description = "",
    bool IsDefault = false,
    int ContextSize = 32768,
    int MaxTokens = 512);

/// <summary>
/// Fetches available models per roleplay LLM provider (API when possible, static fallbacks always).
/// Never returns empty for known providers — UI dropdowns stay usable offline.
/// </summary>
public static class LlmModelFetcher
{
    private static readonly HttpClient Http = new()
    {
        Timeout = TimeSpan.FromSeconds(8)
    };

    private static readonly object CacheLock = new();
    private static readonly Dictionary<string, (DateTime Utc, List<LlmModel> Models)> Cache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly TimeSpan CacheDuration = TimeSpan.FromHours(1);

    public static async Task<List<LlmModel>> GetModelsForProviderAsync(string providerId, bool forceRefresh = false)
    {
        string key = NormalizeProviderId(providerId);

        if (!forceRefresh)
        {
            lock (CacheLock)
            {
                if (Cache.TryGetValue(key, out var hit) &&
                    DateTime.UtcNow - hit.Utc < CacheDuration &&
                    hit.Models.Count > 0)
                {
                    return hit.Models.ToList();
                }
            }
        }

        List<LlmModel> models;
        try
        {
            models = await FetchModelsFromProviderAsync(key).ConfigureAwait(false);
        }
        catch
        {
            models = new List<LlmModel>();
        }

        if (models.Count == 0)
            models = GetFallbackModels(key);

        lock (CacheLock)
        {
            Cache[key] = (DateTime.UtcNow, models);
        }

        return models.ToList();
    }

    public static void ClearCache(string? providerId = null)
    {
        lock (CacheLock)
        {
            if (string.IsNullOrWhiteSpace(providerId))
                Cache.Clear();
            else
                Cache.Remove(NormalizeProviderId(providerId));
        }
    }

    public static string NormalizeProviderId(string? providerId)
    {
        if (string.IsNullOrWhiteSpace(providerId)) return "MockEngine";
        string p = providerId.Trim();
        if (p.Contains("Mock", StringComparison.OrdinalIgnoreCase)) return "MockEngine";
        if (p.Contains("Vibe", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("Mistral", StringComparison.OrdinalIgnoreCase)) return "MistralVibe";
        if (p.Contains("Agy", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("Gemini", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("Antigravity", StringComparison.OrdinalIgnoreCase)) return "AGY";
        if (p.Contains("Grok", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("xAI", StringComparison.OrdinalIgnoreCase)) return "Grok";
        if (p.Contains("Ollama", StringComparison.OrdinalIgnoreCase)) return "Ollama";
        if (p.Contains("SLM", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("LLamaSharp", StringComparison.OrdinalIgnoreCase) ||
            p.Contains("LlamaSharp", StringComparison.OrdinalIgnoreCase)) return "LlamaSharp";
        return p;
    }

    public static List<LlmModel> GetFallbackModels(string providerId)
    {
        return NormalizeProviderId(providerId) switch
        {
            "LlamaSharp" => GetLlamaSharpModels(),
            "AGY" => new List<LlmModel>
            {
                new("agy-pro", "AGY Pro", "AGY", "Default AGY Pro", true),
                new("agy-pro-24b", "AGY Pro 24B", "AGY", "24B Pro"),
                new("agy-pro-32b", "AGY Pro 32B", "AGY", "32B Pro"),
                new("agy-pro-70b", "AGY Pro 70B", "AGY", "70B Pro"),
                new("agy-free", "AGY Free", "AGY", "Free tier"),
            },
            "Grok" => new List<LlmModel>
            {
                new("grok-2", "Grok 2", "Grok", "Latest Grok", true),
                new("grok-2-vision", "Grok 2 Vision", "Grok", "Vision-capable"),
                new("grok-1.5", "Grok 1.5", "Grok", "Previous gen"),
                new("grok-beta", "Grok Beta", "Grok", "Beta"),
            },
            "Ollama" => new List<LlmModel>
            {
                new("llama3", "Llama 3", "Ollama", "Meta Llama 3", true, 128000, 512),
                new("llama3:8b", "Llama 3 8B", "Ollama", "8B", false, 128000, 512),
                new("mistral", "Mistral", "Ollama", "Mistral", false, 32768, 512),
                new("phi3", "Phi 3", "Ollama", "Microsoft Phi 3", false, 128000, 512),
            },
            "MistralVibe" => new List<LlmModel>
            {
                new("mistral-large", "Mistral Large", "MistralVibe", "Large", true),
                new("mistral-small", "Mistral Small", "MistralVibe", "Small"),
                new("codestral", "Codestral", "MistralVibe", "Code"),
                new("magistral", "Magistral", "MistralVibe", "Advanced"),
            },
            "MockEngine" => new List<LlmModel>
            {
                new("mock", "Mock (offline)", "MockEngine", "No network", true),
            },
            _ => new List<LlmModel>
            {
                new("default", "Default model", providerId ?? "unknown", "Fallback", true),
            }
        };
    }

    private static async Task<List<LlmModel>> FetchModelsFromProviderAsync(string providerId)
    {
        return providerId switch
        {
            "AGY" => GetFallbackModels("AGY"), // no public model list API in-host
            "Grok" => GetFallbackModels("Grok"),
            "MistralVibe" => GetFallbackModels("MistralVibe"),
            "MockEngine" => GetFallbackModels("MockEngine"),
            "Ollama" => await FetchOllamaModelsAsync().ConfigureAwait(false),
            _ => GetFallbackModels(providerId)
        };
    }

    private static async Task<List<LlmModel>> FetchOllamaModelsAsync()
    {
        var models = new List<LlmModel>();
        try
        {
            using var res = await Http.GetAsync("http://localhost:11434/api/tags").ConfigureAwait(false);
            if (!res.IsSuccessStatusCode)
                return GetFallbackModels("Ollama");

            string content = await res.Content.ReadAsStringAsync().ConfigureAwait(false);
            using var doc = JsonDocument.Parse(content);
            if (!doc.RootElement.TryGetProperty("models", out var modelsArray))
                return GetFallbackModels("Ollama");

            bool anyDefault = false;
            foreach (var model in modelsArray.EnumerateArray())
            {
                string? name = model.TryGetProperty("name", out var n) ? n.GetString() : null;
                if (string.IsNullOrEmpty(name)) continue;

                long size = model.TryGetProperty("size", out var s) && s.ValueKind == JsonValueKind.Number
                    ? s.GetInt64() : 0;
                bool isDefault = !anyDefault && (
                    name.Contains("llama3", StringComparison.OrdinalIgnoreCase) ||
                    name.Contains("mistral", StringComparison.OrdinalIgnoreCase));
                if (isDefault) anyDefault = true;

                models.Add(new LlmModel(
                    name,
                    name,
                    "Ollama",
                    size > 0 ? $"Local · {size / (1024 * 1024)} MB" : "Local model",
                    isDefault));
            }

            if (models.Count == 0)
                return GetFallbackModels("Ollama");

            if (!anyDefault)
            {
                // mark first as default
                var first = models[0];
                models[0] = first with { IsDefault = true };
            }

            models.Sort((a, b) => string.Compare(a.Id, b.Id, StringComparison.OrdinalIgnoreCase));
            return models;
        }
        catch
        {
            return GetFallbackModels("Ollama");
        }
    }

    public static async Task<string> GetDefaultModelForProviderAsync(string providerId)
    {
        var models = await GetModelsForProviderAsync(providerId).ConfigureAwait(false);
        return models.FirstOrDefault(m => m.IsDefault)?.Id
               ?? models.FirstOrDefault()?.Id
               ?? "";
    }

    public static List<LlmModel> GetLlamaSharpModels()
    {
        var discovered = LlamaSharpLlmClient.DiscoverGgufModels();
        if (discovered.Count == 0)
        {
            return new List<LlmModel>
            {
                new(SlmModelDownloaderService.DefaultModelName, "Dolphin 2.9 Llama 3 8B (Download Required)", "LlamaSharp", "Press 'Download Model' to fetch", true)
            };
        }

        var list = new List<LlmModel>();
        bool isFirst = true;
        foreach (var path in discovered)
        {
            string fileName = System.IO.Path.GetFileName(path);
            long sizeMb = 0;
            try { sizeMb = new System.IO.FileInfo(path).Length / (1024 * 1024); } catch { }

            list.Add(new LlmModel(
                fileName,
                fileName,
                "LlamaSharp",
                $"Local GGUF Model · {sizeMb} MB",
                isFirst));
            isFirst = false;
        }

        return list;
    }

    /// <summary>
    /// Gets the model specifications for a given model ID and provider.
    /// </summary>
    public static LlmModel? GetModelSpecs(string modelId, string providerId)
    {
        var models = GetFallbackModels(providerId);
        foreach (var model in models)
        {
            if (model.Id.Equals(modelId, StringComparison.OrdinalIgnoreCase))
                return model;
        }
        return null;
    }

    /// <summary>
    /// Gets the context size for a given model, with a default fallback.
    /// </summary>
    public static int GetModelContextSize(string modelId, string providerId, int defaultContextSize = 32768)
    {
        var specs = GetModelSpecs(modelId, providerId);
        return specs?.ContextSize ?? defaultContextSize;
    }

    /// <summary>
    /// Gets the max tokens for a given model, with a default fallback.
    /// </summary>
    public static int GetModelMaxTokens(string modelId, string providerId, int defaultMaxTokens = 512)
    {
        var specs = GetModelSpecs(modelId, providerId);
        return specs?.MaxTokens ?? defaultMaxTokens;
    }
}
