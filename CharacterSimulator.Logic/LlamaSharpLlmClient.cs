using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic.ProcessExecution;
using CharacterSimulator.Logic.Services;
using CharacterSimulator.Logic.Utilities;
using LLama;
using LLama.Common;

namespace CharacterSimulator.Logic;

/// <summary>
/// Native C# embedded SLM client using LLamaSharp (llama.cpp engine directly inside .NET process space).
/// </summary>
public class LlamaSharpLlmClient : ILLMClient, IDisposable
{
    public string Name { get; }
    public string ModelPath { get; }
    public int ContextSize { get; set; } = 8192;
    public int GpuLayerCount { get; set; } = 0; // 0 = CPU, >0 = Offload layers to GPU
    
    private readonly CircuitBreaker _circuitBreaker;
    
    /// <summary>
    /// Circuit breaker failure threshold (default: 5 consecutive failures)
    /// </summary>
    public int CircuitBreakerFailureThreshold { get; set; } = 5;
    
    /// <summary>
    /// Circuit breaker reset timeout (default: 1 minute)
    /// </summary>
    public TimeSpan CircuitBreakerResetTimeout { get; set; } = TimeSpan.FromMinutes(1);

    private static readonly ConcurrentDictionary<string, LLamaWeights> WeightsCache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly object CacheLock = new();

    public LlamaSharpLlmClient(string name = "Embedded C# SLM (LLamaSharp)", string? modelPath = null)
    {
        Name = name;
        ModelPath = ResolveModelPath(modelPath);
        _circuitBreaker = new CircuitBreaker(CircuitBreakerFailureThreshold, CircuitBreakerResetTimeout);
        
        // Auto-configure context size and max tokens based on model specs
        if (!string.IsNullOrWhiteSpace(ModelPath) && File.Exists(ModelPath))
        {
            int modelContextSize = SlmModelDownloaderService.GetModelContextSize(ModelPath, 8192);
            int modelMaxTokens = SlmModelDownloaderService.GetModelMaxTokens(ModelPath, 512);
            ContextSize = modelContextSize;
            // Note: MaxTokens is set per-request in inferenceParams, not here
        }
    }

    public static List<string> DiscoverGgufModels()
    {
        var results = new List<string>();
        var searchDirs = new List<string>();

        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string currentDir = Environment.CurrentDirectory;

        searchDirs.Add(Path.Combine(baseDir, "Models"));
        searchDirs.Add(baseDir);
        searchDirs.Add(Path.Combine(baseDir, "Data", "Models"));
        searchDirs.Add(Path.Combine(currentDir, "Models"));
        searchDirs.Add(currentDir);

        // Walk up baseDir parent hierarchy up to 5 levels (finds root repo folder Models/)
        DirectoryInfo? current = new DirectoryInfo(baseDir);
        for (int i = 0; i < 5 && current != null; i++)
        {
            searchDirs.Add(Path.Combine(current.FullName, "Models"));
            searchDirs.Add(current.FullName);
            current = current.Parent;
        }

        foreach (var dir in searchDirs)
        {
            if (Directory.Exists(dir))
            {
                try
                {
                    foreach (var file in Directory.GetFiles(dir, "*.gguf", SearchOption.TopDirectoryOnly))
                    {
                        string full = Path.GetFullPath(file);
                        if (!results.Contains(full))
                            results.Add(full);
                    }
                }
                catch { }
            }
        }

        return results;
    }

    public static string ResolveDefaultModelPath() => ResolveModelPath(null);

    public static string ResolveModelPath(string? requestedPath)
    {
        var discovered = DiscoverGgufModels();
        if (!string.IsNullOrWhiteSpace(requestedPath))
        {
            if (File.Exists(requestedPath))
                return Path.GetFullPath(requestedPath);

            string requestedName = Path.GetFileName(requestedPath);
            var match = discovered.FirstOrDefault(f => Path.GetFileName(f).Equals(requestedName, StringComparison.OrdinalIgnoreCase));
            if (match != null)
                return match;
        }

        return discovered.FirstOrDefault() ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Models", SlmModelDownloaderService.DefaultModelName);
    }

    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "", string? conversationHistory = null)
    {
        return SendPromptAsync(character, input, sceneContext, goalContext, CancellationToken.None, conversationHistory).GetAwaiter().GetResult();
    }

    public async Task<string> SendPromptAsync(Character character, string input, string sceneContext, string goalContext = "", CancellationToken ct = default, string? conversationHistory = null)
    {
        // Check circuit breaker
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        var format = LocalSlmPromptBuilder.DetectFormat(ModelPath);
        string prompt = LocalSlmPromptBuilder.BuildPrompt(character, input, sceneContext, goalContext, conversationHistory, format);
        
        // Cache the token count for this prompt
        int tokenCount = TokenCounter.GetCachedTokenCount(prompt);
        int modelContextSize = SlmModelDownloaderService.GetModelContextSize(ModelPath, ContextSize);
        
        string raw = await CompleteRawAsync(prompt, ct).ConfigureAwait(false);
        return LlmResponseSanitizer.ClampToFirstReply(raw, input);
    }

    public async Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        // Check circuit breaker
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        if (string.IsNullOrWhiteSpace(ModelPath) || !File.Exists(ModelPath))
        {
            _circuitBreaker.RecordFailure();
            return $"[LlamaSharp] GGUF model file not found at '{ModelPath}'. Please place a .gguf model file (e.g. Qwen2.5-3B-Instruct.gguf or Llama-3.2-3B-Instruct.gguf) into the 'Models/' folder.";
        }

        // Check if prompt exceeds model context and truncate if needed
        int modelContextSize = SlmModelDownloaderService.GetModelContextSize(ModelPath, ContextSize);
        if (!TokenCounter.IsWithinContextLimit(prompt, modelContextSize))
        {
            prompt = TokenCounter.TruncateToContextLimit(prompt, modelContextSize);
        }

        try
        {
            LLamaWeights weights;
            lock (CacheLock)
            {
                if (!WeightsCache.TryGetValue(ModelPath, out weights!))
                {
                    var modelParams = new ModelParams(ModelPath)
                    {
                        ContextSize = (uint)ContextSize,
                        GpuLayerCount = GpuLayerCount,
                        Threads = Math.Min(Environment.ProcessorCount, 8)
                    };
                    weights = LLamaWeights.LoadFromFile(modelParams);
                    WeightsCache[ModelPath] = weights;
                }
            }

            var parameters = new ModelParams(ModelPath)
            {
                ContextSize = (uint)ContextSize,
                GpuLayerCount = GpuLayerCount,
                Threads = Math.Min(Environment.ProcessorCount, 8)
            };

            var executor = new StatelessExecutor(weights, parameters);
            
            // Get max tokens for this specific model
            int maxTokens = SlmModelDownloaderService.GetModelMaxTokens(ModelPath, 512);
            
            var inferenceParams = new InferenceParams
            {
                MaxTokens = maxTokens,
                AntiPrompts = new List<string>
                {
                    "<|im_end|>",
                    "<|im_start|>",
                    "<|eot_id|>",
                    "<|end_of_text|>",
                    "[They just said",
                    "[Player]:",
                    "User:",
                    "Player:",
                    "System:",
                    "###",
                    "SCENE:",
                    "RULES:"
                },
                SamplingPipeline = new LLama.Sampling.DefaultSamplingPipeline
                {
                    Temperature = 0.75f,
                    TopP = 0.9f,
                    RepeatPenalty = 1.18f,
                    PresencePenalty = 0.1f
                }
            };

            var sb = new StringBuilder();
            await foreach (var token in executor.InferAsync(prompt, inferenceParams, ct).ConfigureAwait(false))
            {
                sb.Append(token);
            }

            _circuitBreaker.RecordSuccess();
            return sb.ToString().Trim();
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
    }

    private bool _disposed = false;

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }
    
    protected virtual void Dispose(bool disposing)
    {
        if (!_disposed)
        {
            if (disposing)
            {
                // Note: StatelessExecutor and LLamaWeights are managed by the static cache
                // and are not disposed here as they may be shared across instances
            }
            _disposed = true;
        }
    }
    
    ~LlamaSharpLlmClient()
    {
        Dispose(false);
    }
}
