using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.Http;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.Services;

public record DetectedLlmEngine(string Id, string DisplayName, bool IsAvailable, string StatusDetail);

public class LlmEngineDetector
{
    private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };

    /// <summary>
    /// Auto-detects locally available LLM providers (CLI tools & local server APIs).
    /// When <paramref name="forceRefresh"/> is false and a prior scan is in SQLite, returns the
    /// cached list for a fast UI lookup. A full scan always writes back to the database.
    /// </summary>
    public static async Task<List<DetectedLlmEngine>> DetectAvailableEnginesAsync(bool forceRefresh = false)
    {
        if (!forceRefresh)
        {
            var cached = InstalledEngineStore.TryGetRoleplayCached();
            if (cached is { Count: > 0 })
                return cached;
        }

        var engines = await ScanLiveAsync().ConfigureAwait(false);
        InstalledEngineStore.SaveRoleplay(engines);
        return engines;
    }

    /// <summary>Live PATH / API probe only (does not read or write the DB cache).</summary>
    public static async Task<List<DetectedLlmEngine>> ScanLiveAsync()
    {
        var engines = new List<DetectedLlmEngine>();

        // 0. Check Embedded C# SLM (LLamaSharp)
        bool slmFound = SlmModelDownloaderService.HasAnyGgufModel();
        engines.Add(new DetectedLlmEngine(
            "LlamaSharp",
            "💻 Embedded C# SLM (LLamaSharp)",
            true, // C# engine is compiled natively into the host
            slmFound ? "GGUF model ready in Models/" : "No .gguf model in Models/ (Download available)"
        ));

        // 1. Check AGY (Antigravity CLI / API)
        bool agyFound = IsCommandAvailable("agy") || IsCommandAvailable("antigravity") || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("AGY_API_KEY"));
        engines.Add(new DetectedLlmEngine(
            "AGY",
            "🚀 Antigravity AGY (Engine / CLI)",
            agyFound,
            agyFound ? "AGY active in environment" : "AGY executable/key not found"
        ));

        // 2. Check Grok (xAI CLI / API)
        bool grokFound = IsCommandAvailable("grok") || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("GROK_API_KEY")) || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("XAI_API_KEY"));
        engines.Add(new DetectedLlmEngine(
            "Grok",
            "🧠 xAI Grok (API / CLI)",
            grokFound,
            grokFound ? "Grok API key/CLI detected" : "Grok key/CLI not found"
        ));

        // 3. Check Mistral Vibe CLI
        bool mistralFound = IsCommandAvailable("vibe") || IsCommandAvailable("mistral-vibe");
        engines.Add(new DetectedLlmEngine(
            "MistralVibe",
            "⚡ Mistral Vibe (Local CLI)",
            mistralFound,
            mistralFound ? "CLI detected in system PATH" : "CLI not found in PATH"
        ));

        // 4. Check Ollama Local API
        bool ollamaRunning = false;
        string ollamaStatus = "Server offline at http://localhost:11434";
        try
        {
            var res = await _httpClient.GetAsync("http://localhost:11434/api/tags");
            if (res.IsSuccessStatusCode)
            {
                ollamaRunning = true;
                ollamaStatus = "Active at http://localhost:11434";
            }
        }
        catch
        {
            ollamaStatus = "Connection refused at http://localhost:11434";
        }

        engines.Add(new DetectedLlmEngine(
            "Ollama",
            "🦙 Ollama API",
            ollamaRunning,
            ollamaStatus
        ));

        // 5. Fallback Mock Engine (Always Available)
        engines.Add(new DetectedLlmEngine(
            "MockEngine",
            "🧪 Mock LLM Engine",
            true,
            "Always ready (Offline testing)"
        ));

        return engines;
    }

    private static bool IsCommandAvailable(string command)
    {
        try
        {
            using var proc = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "which",
                    Arguments = command,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                }
            };
            proc.Start();
            proc.WaitForExit();
            return proc.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }
}
