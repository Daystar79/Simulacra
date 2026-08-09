using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// Service to auto-download and verify default GGUF Small Language Models from Hugging Face into Models/
/// </summary>
public static class SlmModelDownloaderService
{
    public const string DefaultModelName = "qwen2.5-3b-instruct-q4_k_m.gguf";
    public const string DefaultDownloadUrl = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf";

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

    public static async Task<bool> DownloadDefaultModelAsync(Action<double, string>? onProgress = null, CancellationToken ct = default)
    {
        string targetPath = GetDefaultModelPath();
        if (File.Exists(targetPath))
        {
            onProgress?.Invoke(1.0, "Default GGUF model is already downloaded!");
            return true;
        }

        string tempPath = targetPath + ".download";
        using var client = new HttpClient { Timeout = TimeSpan.FromHours(2) };

        try
        {
            onProgress?.Invoke(0.01, "Connecting to Hugging Face…");

            using var response = await client.GetAsync(DefaultDownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
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
                    onProgress?.Invoke(percent, $"Downloading Qwen 2.5 3B ({mb:F1} MB / {totalMb:F1} MB)");
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

            onProgress?.Invoke(1.0, "Model download complete! Ready for local C# SLM roleplay.");
            return true;
        }
        catch (Exception ex)
        {
            try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch { }
            onProgress?.Invoke(0, $"Download failed: {ex.Message}");
            return false;
        }
    }
}
