using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
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
using LLama.Exceptions;
using LLama.Native;
using LLama.Sampling;

namespace CharacterSimulator.Logic;

/// <summary>
/// Embedded SLM client using LLamaSharp (llama.cpp in-process).
/// One model context is kept warm; later turns only re-decode tokens after the
/// shared prompt prefix instead of allocating a new KV cache every beat.
/// Default inference is CPU-only so friend-test machines without a usable GPU still load.
/// </summary>
public class LlamaSharpLlmClient : ILLMClient, IDisposable
{
    /// <summary>Enough layers to place a typical SLM entirely on GPU if VRAM allows.</summary>
    public const int AllGpuLayers = 99;

    /// <summary>
    /// Partial offload: some layers on GPU, the rest on CPU. Default because this host
    /// cannot assume enough VRAM for a GPU-only load.
    /// </summary>
    public const int HybridGpuLayers = 20;

    /// <summary>One somatic + line + close. Kept short so decode does not wander.</summary>
    public const int DefaultRoleplayMaxTokens = 160;

    public const int DefaultRawMaxTokens = 256;

    public string Name { get; }
    public string ModelPath { get; }
    public int ContextSize { get; set; } = 4096;

    /// <summary>
    /// Layers to place on GPU. 0 = CPU only (the product default).
    /// General-use installs cannot assume Vulkan or spare VRAM; GPU offload is opt-in.
    /// </summary>
    public int GpuLayerCount { get; set; } = 0;

    public int RoleplayMaxTokens { get; set; } = DefaultRoleplayMaxTokens;

    public int CircuitBreakerFailureThreshold { get; set; } = 5;
    public TimeSpan CircuitBreakerResetTimeout { get; set; } = TimeSpan.FromMinutes(1);

    private readonly CircuitBreaker _circuitBreaker;

    private static readonly ConcurrentDictionary<string, CachedRuntime> RuntimeCache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly SemaphoreSlim RuntimeGate = new(1, 1);

    public LlamaSharpLlmClient(string name = "Embedded C# SLM (LLamaSharp)", string? modelPath = null)
    {
        Name = name;
        ModelPath = ResolveModelPath(modelPath);
        _circuitBreaker = new CircuitBreaker(CircuitBreakerFailureThreshold, CircuitBreakerResetTimeout);

        if (!string.IsNullOrWhiteSpace(ModelPath) && File.Exists(ModelPath))
        {
            int modelContextSize = SlmModelDownloaderService.GetModelContextSize(ModelPath, 4096);
            ContextSize = Math.Min(modelContextSize, 4096);
        }
    }

    public static int ResolveThreadCount()
    {
        int cores = Environment.ProcessorCount;
        if (cores <= 2)
            return cores;
        // Leave a core for the Photino UI / host loop. CPU layers need the rest.
        return Math.Max(2, cores - 1);
    }

    /// <summary>
    /// Layer counts to try, most GPU first. Always ends on CPU (0) so a machine
    /// with no usable Vulkan device still loads.
    /// </summary>
    public static int[] GpuLayerFallbackPlan(int requested)
    {
        requested = Math.Max(0, requested);
        var plan = new List<int> { requested };
        if (requested > HybridGpuLayers)
            plan.Add(HybridGpuLayers);
        if (requested > 0)
            plan.Add(0);
        return plan.ToArray();
    }

    public static int CountSharedPrefix<T>(IReadOnlyList<T> left, IReadOnlyList<T> right)
    {
        if (left == null || right == null)
            return 0;

        int n = Math.Min(left.Count, right.Count);
        var comparer = EqualityComparer<T>.Default;
        int i = 0;
        for (; i < n; i++)
        {
            if (!comparer.Equals(left[i], right[i]))
                break;
        }

        return i;
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

    /// <summary>Drop a warm runtime so the GGUF file can be deleted or replaced.</summary>
    public static void ReleaseCachedRuntime(string? modelPath)
    {
        if (string.IsNullOrWhiteSpace(modelPath))
            return;

        string key = Path.GetFullPath(modelPath);
        string name = Path.GetFileName(key);
        foreach (var existing in RuntimeCache.Keys.ToArray())
        {
            if (existing.Equals(key, StringComparison.OrdinalIgnoreCase) ||
                Path.GetFileName(existing).Equals(name, StringComparison.OrdinalIgnoreCase))
            {
                if (RuntimeCache.TryRemove(existing, out var runtime))
                    runtime.Dispose();
            }
        }
    }

    public static void ReleaseAllCachedRuntimes()
    {
        foreach (var key in RuntimeCache.Keys.ToArray())
        {
            if (RuntimeCache.TryRemove(key, out var runtime))
                runtime.Dispose();
        }
    }

    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "", string? conversationHistory = null)
    {
        return SendPromptAsync(character, input, sceneContext, goalContext, CancellationToken.None, conversationHistory).GetAwaiter().GetResult();
    }

    public async Task<string> SendPromptAsync(Character character, string input, string sceneContext, string goalContext = "", CancellationToken ct = default, string? conversationHistory = null)
    {
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        var format = LocalSlmPromptBuilder.DetectFormat(ModelPath);
        string prompt = LocalSlmPromptBuilder.BuildPrompt(character, input, sceneContext, goalContext, conversationHistory, format);

        _ = TokenCounter.GetCachedTokenCount(prompt);

        int maxTokens = Math.Min(
            SlmModelDownloaderService.GetModelMaxTokens(ModelPath, RoleplayMaxTokens),
            RoleplayMaxTokens);

        string raw = await CompleteRawAsync(prompt, character?.Name, ct, maxTokens).ConfigureAwait(false);
        return LlmResponseSanitizer.ClampToFirstReply(raw, input, conversationHistory);
    }

    public Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        return CompleteRawAsync(prompt, null, ct, DefaultRawMaxTokens);
    }

    public Task<string> CompleteRawAsync(string prompt, string? characterName, CancellationToken ct = default)
    {
        return CompleteRawAsync(prompt, characterName, ct, DefaultRawMaxTokens);
    }

    public async Task<string> CompleteRawAsync(string prompt, string? characterName, CancellationToken ct, int maxTokens)
    {
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        if (string.IsNullOrWhiteSpace(ModelPath) || !File.Exists(ModelPath))
        {
            _circuitBreaker.RecordFailure();
            return $"[LlamaSharp] GGUF model file not found at '{ModelPath}'. Please place a .gguf model file (e.g. Qwen2.5-3B-Instruct.gguf or Llama-3.2-3B-Instruct.gguf) into the 'Models/' folder.";
        }

        int modelContextSize = SlmModelDownloaderService.GetModelContextSize(ModelPath, ContextSize);
        if (!TokenCounter.IsWithinContextLimit(prompt, modelContextSize))
        {
            prompt = TokenCounter.TruncateToContextLimit(prompt, modelContextSize);
        }

        await RuntimeGate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            CachedRuntime runtime = GetOrCreateRuntime();
            string raw = await InferAsync(runtime, prompt, characterName, maxTokens, ct).ConfigureAwait(false);
            _circuitBreaker.RecordSuccess();
            return raw;
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
        finally
        {
            RuntimeGate.Release();
        }
    }

    private CachedRuntime GetOrCreateRuntime()
    {
        string key = Path.GetFullPath(ModelPath);
        if (RuntimeCache.TryGetValue(key, out var existing) && !existing.IsDisposed)
            return existing;

        Exception? lastError = null;
        foreach (int gpuLayers in GpuLayerFallbackPlan(GpuLayerCount))
        {
            try
            {
                var runtime = LoadRuntime(key, gpuLayers);
                RuntimeCache[key] = runtime;
                return runtime;
            }
            catch (Exception ex)
            {
                lastError = ex;
                if (RuntimeCache.TryRemove(key, out var broken))
                    broken.Dispose();

                string next = gpuLayers > HybridGpuLayers
                    ? $"hybrid CPU+GPU ({HybridGpuLayers} layers)"
                    : gpuLayers > 0 ? "CPU-only" : "giving up";
                AppLogger.Warning($"[LlamaSharp] Load with gpu_layers={gpuLayers} failed ({ex.Message}); trying {next}.");
            }
        }

        throw lastError ?? new InvalidOperationException("[LlamaSharp] Failed to create a CPU or GPU runtime.");
    }

    private CachedRuntime LoadRuntime(string key, int gpuLayers)
    {
        var modelParams = BuildModelParams(ModelPath, gpuLayers);
        var weights = LLamaWeights.LoadFromFile(modelParams);
        LLamaContext context;
        try
        {
            context = weights.CreateContext(modelParams);
        }
        catch
        {
            weights.Dispose();
            throw;
        }

        AppLogger.Info(
            $"[LlamaSharp] Runtime ready · gpu_layers={gpuLayers} · threads={modelParams.Threads} · ctx={ContextSize} · flash={(modelParams.FlashAttention == true)} · {Path.GetFileName(ModelPath)}");

        return new CachedRuntime(key, weights, context, modelParams, gpuLayers);
    }

    private ModelParams BuildModelParams(string modelPath, int gpuLayers)
    {
        int threads = ResolveThreadCount();
        return new ModelParams(modelPath)
        {
            ContextSize = (uint)ContextSize,
            GpuLayerCount = gpuLayers,
            Threads = threads,
            BatchThreads = threads,
            BatchSize = 512,
            UBatchSize = 512,
            UseMemorymap = true,
            FlashAttention = gpuLayers > 0 ? true : null,
            NoKqvOffload = false
        };
    }

    private static async Task<string> InferAsync(
        CachedRuntime runtime,
        string prompt,
        string? characterName,
        int maxTokens,
        CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        var context = runtime.Context;
        var batch = runtime.Batch;

        var promptTokens = context.Tokenize(prompt, special: true).ToList();
        if (promptTokens.Count == 0)
            return "";

        int common = CountSharedPrefix(runtime.LastPromptTokens, promptTokens);

        // Always drop tokens after the shared prefix (old user tail + previous decode)
        // so the next prefill can sit on a clean KV suffix. Re-evaluate the last
        // shared token so logits are present for sampling.
        if (common > 0)
            common--;

        try
        {
            if (common <= 0)
            {
                context.NativeHandle.MemoryClear();
                common = 0;
            }
            else
            {
                context.NativeHandle.MemorySequenceRemove(LLamaSeqId.Zero, common, -1);
            }
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[LlamaSharp] KV trim failed ({ex.Message}); clearing context.");
            context.NativeHandle.MemoryClear();
            common = 0;
        }

        var suffix = promptTokens.Skip(common).ToList();
        int nPast = common;

        if (suffix.Count > 0)
        {
            batch.Clear();
            try
            {
                var (result, _, past) = await context.DecodeAsync(suffix, LLamaSeqId.Zero, batch, nPast).ConfigureAwait(false);
                if (result != DecodeResult.Ok)
                    throw new LLamaDecodeError(result);
                nPast = past;
            }
            catch (Exception ex) when (common > 0)
            {
                AppLogger.Warning($"[LlamaSharp] Prefix reuse decode failed ({ex.Message}); full prefill.");
                context.NativeHandle.MemoryClear();
                batch.Clear();
                var (result, _, past) = await context.DecodeAsync(promptTokens, LLamaSeqId.Zero, batch, 0).ConfigureAwait(false);
                if (result != DecodeResult.Ok)
                    throw new LLamaDecodeError(result);
                nPast = past;
                common = 0;
            }
        }

        int reused = common;
        runtime.LastPromptTokens = promptTokens;

        var antiPrompts = new List<string>
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
        };

        if (!string.IsNullOrWhiteSpace(characterName))
        {
            antiPrompts.Add($"[{characterName}]");
            antiPrompts.Add($"[{characterName}]:");
        }

        var pipeline = new DefaultSamplingPipeline
        {
            Temperature = 0.75f,
            TopP = 0.9f,
            RepeatPenalty = 1.25f,
            PresencePenalty = 0.2f
        };

        var decoder = new StreamingTokenDecoder(context);
        var antiprocessor = new AntipromptProcessor(antiPrompts);
        var sb = new StringBuilder();

        int limit = maxTokens < 0 ? 160 : maxTokens;
        for (int i = 0; i < limit && !ct.IsCancellationRequested; i++)
        {
            var id = pipeline.Sample(context.NativeHandle, batch.TokenCount - 1);
            if (id.IsEndOfGeneration(context.Vocab))
                break;

            decoder.Add(id);
            string decoded = decoder.Read();
            sb.Append(decoded);
            if (antiprocessor.Add(decoded))
                break;

            batch.Clear();
            batch.Add(id, nPast++, LLamaSeqId.Zero, true);
            var returnCode = await context.DecodeAsync(batch, ct).ConfigureAwait(false);
            if (returnCode != 0)
                throw new LLamaDecodeError(returnCode);
        }

        AppLogger.Debug(
            $"[LlamaSharp] turn {sw.ElapsedMilliseconds}ms · prompt={promptTokens.Count} · reused={reused} · decoded={nPast - promptTokens.Count}");

        return sb.ToString().Trim();
    }

    public void Dispose()
    {
        // Warm runtimes are process-wide and shared across client instances.
        GC.SuppressFinalize(this);
    }

    private sealed class CachedRuntime : IDisposable
    {
        public CachedRuntime(string key, LLamaWeights weights, LLamaContext context, ModelParams modelParams, int gpuLayers)
        {
            Key = key;
            Weights = weights;
            Context = context;
            ModelParams = modelParams;
            GpuLayers = gpuLayers;
            Batch = new LLamaBatch();
            LastPromptTokens = new List<LLamaToken>();
        }

        public string Key { get; }
        public LLamaWeights Weights { get; }
        public LLamaContext Context { get; }
        public ModelParams ModelParams { get; }
        public int GpuLayers { get; }
        public LLamaBatch Batch { get; }
        public List<LLamaToken> LastPromptTokens { get; set; }
        public bool IsDisposed { get; private set; }

        public void Dispose()
        {
            if (IsDisposed)
                return;
            IsDisposed = true;
            try { Context.Dispose(); } catch { }
            try { Weights.Dispose(); } catch { }
        }
    }
}
