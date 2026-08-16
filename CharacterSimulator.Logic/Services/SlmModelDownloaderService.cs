using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic.Services;

public class SlmModelOption
{
    public string Id { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string FileName { get; set; } = string.Empty;
    public string DownloadUrl { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public double ApproxSizeMb { get; set; }
    public bool IsDefault { get; set; }
    public int ContextSize { get; set; } = 8192;
    public int MaxTokens { get; set; } = 512;
}

/// <summary>
/// Service to auto-download and verify GGUF Small Language Models from Hugging Face into Models/
/// </summary>
public static class SlmModelDownloaderService
{
    public const string DefaultModelName = "Dolphin3.0-Llama3.2-1B-Q4_K_M.gguf";
    public const string DefaultDownloadUrl = "https://huggingface.co/bartowski/Dolphin3.0-Llama3.2-1B-GGUF/resolve/main/Dolphin3.0-Llama3.2-1B-Q4_K_M.gguf";

    public static readonly List<SlmModelOption> AvailableModels = new()
    {
        new SlmModelOption
        {
            Id = "dolphin-3.0-llama3.2-1b",
            DisplayName = "Dolphin 3.0 (Llama 3.2 1B) — First-run default",
            FileName = "Dolphin3.0-Llama3.2-1B-Q4_K_M.gguf",
            DownloadUrl = "https://huggingface.co/bartowski/Dolphin3.0-Llama3.2-1B-GGUF/resolve/main/Dolphin3.0-Llama3.2-1B-Q4_K_M.gguf",
            Description = "Small uncensored model (~800 MB). Best first download; good enough to talk, easy on disk.",
            ApproxSizeMb = 800,
            ContextSize = 8192,
            MaxTokens = 384,
            IsDefault = true
        },
        new SlmModelOption
        {
            Id = "dolphin-2.9-llama3-8b",
            DisplayName = "Dolphin 2.9 (Llama 3 8B) — Uncensored 8B",
            FileName = "dolphin-2.9-llama3-8b.Q4_K_M.gguf",
            DownloadUrl = "https://huggingface.co/QuantFactory/dolphin-2.9-llama3-8b-GGUF/resolve/main/dolphin-2.9-llama3-8b.Q4_K_M.gguf",
            Description = "Uncensored 8B model; handles complex character cards & full cognitive framework.",
            ApproxSizeMb = 4900,
            ContextSize = 8192,
            MaxTokens = 512,
            IsDefault = false
        },
        new SlmModelOption
        {
            Id = "qwen-2.5-7b",
            DisplayName = "Qwen 2.5 (7B Instruct) — High Precision 7B",
            FileName = "qwen2.5-7b-instruct-q4_k_m.gguf",
            DownloadUrl = "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
            Description = "High precision 7B model for strict prompt adherence.",
            ApproxSizeMb = 4500,
            ContextSize = 32768,
            MaxTokens = 512,
            IsDefault = false
        },
        new SlmModelOption
        {
            Id = "llama-3.1-8b",
            DisplayName = "Llama 3.1 (8B Instruct) — Meta Standard 8B",
            FileName = "Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            DownloadUrl = "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            Description = "Stock Meta 8B instruct model.",
            ApproxSizeMb = 4900,
            ContextSize = 128000,
            MaxTokens = 512,
            IsDefault = false
        }
    };

    public static string GetModelsDirectory()
    {
        string dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Models");
        if (!Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }
        return dir;
    }

    public static bool HasAnyGgufModel()
    {
        return LlamaSharpLlmClient.DiscoverGgufModels().Count > 0;
    }

    public static string GetDefaultModelPath()
    {
        return Path.Combine(GetModelsDirectory(), DefaultModelName);
    }

    public static Task<bool> DownloadDefaultModelAsync(Action<double, string>? onProgress = null, CancellationToken ct = default)
    {
        var defaultOption = AvailableModels.FirstOrDefault(m => m.IsDefault) ?? AvailableModels[0];
        return DownloadModelAsync(defaultOption, onProgress, ct);
    }

    public static async Task<bool> DownloadModelAsync(
        SlmModelOption modelOption,
        Action<double, string>? onProgress = null,
        CancellationToken ct = default)
    {
        if (modelOption == null) throw new ArgumentNullException(nameof(modelOption));

        string targetPath = Path.Combine(GetModelsDirectory(), modelOption.FileName);
        if (File.Exists(targetPath))
        {
            onProgress?.Invoke(1.0, $"{modelOption.FileName} is already downloaded!");
            return true;
        }

        string tempPath = targetPath + ".download";
        using var client = new HttpClient { Timeout = TimeSpan.FromHours(2) };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Simulacra/1.0");

        try
        {
            onProgress?.Invoke(0.01, $"Connecting to Hugging Face for {modelOption.DisplayName}…");

            using var response = await client.GetAsync(modelOption.DownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();

            long? totalBytes = response.Content.Headers.ContentLength;
            using var stream = await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
            using var fileStream = new FileStream(tempPath, FileMode.Create, FileAccess.Write, FileShare.None, 81920, true);

            var buffer = new byte[81920];
            long totalRead = 0;
            int read;

            while ((read = await stream.ReadAsync(buffer, 0, buffer.Length, ct).ConfigureAwait(false)) > 0)
            {
                await fileStream.WriteAsync(buffer, 0, read, ct).ConfigureAwait(false);
                totalRead += read;

                if (totalBytes.HasValue && totalBytes.Value > 0)
                {
                    double percent = (double)totalRead / totalBytes.Value;
                    double mb = totalRead / (1024.0 * 1024.0);
                    double totalMb = totalBytes.Value / (1024.0 * 1024.0);
                    onProgress?.Invoke(percent, $"Downloading {modelOption.FileName} ({mb:F1} MB / {totalMb:F1} MB)");
                }
                else
                {
                    double mb = totalRead / (1024.0 * 1024.0);
                    onProgress?.Invoke(0.5, $"Downloaded {mb:F1} MB…");
                }
            }

            fileStream.Close();
            if (File.Exists(targetPath)) File.Delete(targetPath);
            File.Move(tempPath, targetPath);

            onProgress?.Invoke(1.0, $"{modelOption.FileName} download complete! Ready for local roleplay.");
            return true;
        }
        catch (Exception ex)
        {
            try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch { }
            onProgress?.Invoke(0, $"Download failed: {ex.Message}");
            return false;
        }
    }

    /// <summary>
    /// Returns full paths of all GGUF model files currently installed on disk.
    /// </summary>
    public static List<string> GetInstalledModelFiles()
    {
        return LlamaSharpLlmClient.DiscoverGgufModels();
    }

    /// <summary>
    /// Safely deletes a GGUF model file by file name or path.
    /// </summary>
    public static bool DeleteModelFile(string modelFileNameOrPath)
    {
        if (string.IsNullOrWhiteSpace(modelFileNameOrPath)) return false;

        var installed = GetInstalledModelFiles();
        string? targetPath = installed.FirstOrDefault(p =>
            Path.GetFileName(p).Equals(modelFileNameOrPath, StringComparison.OrdinalIgnoreCase) ||
            p.Equals(modelFileNameOrPath, StringComparison.OrdinalIgnoreCase));

        if (targetPath == null)
        {
            string defaultDir = GetModelsDirectory();
            string candidate = Path.Combine(defaultDir, Path.GetFileName(modelFileNameOrPath));
            if (File.Exists(candidate))
                targetPath = candidate;
        }

        if (targetPath != null && File.Exists(targetPath))
        {
            try
            {
                LlamaSharpLlmClient.ReleaseCachedRuntime(targetPath);
                File.Delete(targetPath);
                LlmModelFetcher.ClearCache("LlamaSharp");
                return true;
            }
            catch (Exception ex)
            {
                AppLogger.Warning($"[SlmModelDownloaderService] Failed to delete model '{targetPath}': {ex.Message}");
                return false;
            }
        }

        return false;
    }

    /// <summary>
    /// Gets the model specifications (context size, max tokens) for a given model file name or ID.
    /// </summary>
    public static SlmModelOption? GetModelSpecs(string modelFileNameOrId)
    {
        if (string.IsNullOrWhiteSpace(modelFileNameOrId))
            return null;

        string normalized = Path.GetFileNameWithoutExtension(modelFileNameOrId) ?? modelFileNameOrId;
        normalized = normalized.Trim();

        // Try exact match on Id
        foreach (var model in AvailableModels)
        {
            if (model.Id.Equals(normalized, StringComparison.OrdinalIgnoreCase) ||
                model.FileName.Equals(modelFileNameOrId, StringComparison.OrdinalIgnoreCase))
            {
                return model;
            }
        }

        // Try partial match on filename
        foreach (var model in AvailableModels)
        {
            if (normalized.Contains(model.Id, StringComparison.OrdinalIgnoreCase) ||
                model.FileName.Contains(normalized, StringComparison.OrdinalIgnoreCase) ||
                normalized.Contains(Path.GetFileNameWithoutExtension(model.FileName), StringComparison.OrdinalIgnoreCase))
            {
                return model;
            }
        }

        return null;
    }

    /// <summary>
    /// Gets the context size for a given model, with a default fallback.
    /// </summary>
    public static int GetModelContextSize(string modelPathOrName, int defaultContextSize = 8192)
    {
        var specs = GetModelSpecs(modelPathOrName);
        return specs?.ContextSize ?? defaultContextSize;
    }

    /// <summary>
    /// Gets the max tokens for a given model, with a default fallback.
    /// </summary>
    public static int GetModelMaxTokens(string modelPathOrName, int defaultMaxTokens = 512)
    {
        var specs = GetModelSpecs(modelPathOrName);
        return specs?.MaxTokens ?? defaultMaxTokens;
    }
}
