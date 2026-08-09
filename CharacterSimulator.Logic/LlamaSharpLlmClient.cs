using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
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
    public int ContextSize { get; set; } = 4096;
    public int GpuLayerCount { get; set; } = 0; // 0 = CPU, >0 = Offload layers to GPU

    private static readonly ConcurrentDictionary<string, LLamaWeights> WeightsCache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly object CacheLock = new();

    public LlamaSharpLlmClient(string name = "Embedded C# SLM (LLamaSharp)", string? modelPath = null)
    {
        Name = name;
        ModelPath = modelPath ?? ResolveDefaultModelPath();
    }

    public static List<string> DiscoverGgufModels()
    {
        var results = new List<string>();
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string modelsDir = Path.Combine(baseDir, "Models");

        var searchDirs = new[] { modelsDir, baseDir, Path.Combine(baseDir, "Data", "Models") };

        foreach (var dir in searchDirs)
        {
            if (Directory.Exists(dir))
            {
                foreach (var file in Directory.GetFiles(dir, "*.gguf", SearchOption.AllDirectories))
                {
                    if (!results.Contains(file))
                        results.Add(file);
                }
            }
        }

        return results;
    }

    public static string ResolveDefaultModelPath()
    {
        var models = DiscoverGgufModels();
        return models.FirstOrDefault() ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Models", "default-slm.gguf");
    }

    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "")
    {
        return SendPromptAsync(character, input, sceneContext, goalContext).GetAwaiter().GetResult();
    }

    public async Task<string> SendPromptAsync(Character character, string input, string sceneContext, string goalContext = "", CancellationToken ct = default)
    {
        string prompt = PromptBuilder.BuildFullPrompt(character, input, sceneContext, goalContext);
        return await CompleteRawAsync(prompt, ct).ConfigureAwait(false);
    }

    public async Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(ModelPath) || !File.Exists(ModelPath))
        {
            return $"[LLamaSharp SLM Error] GGUF model file not found at '{ModelPath}'. Please place a .gguf model file (e.g. Qwen2.5-3B-Instruct.gguf or Llama-3.2-3B-Instruct.gguf) into the 'Models/' folder.";
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
                        Threads = Math.Max(1, Environment.ProcessorCount / 2)
                    };
                    weights = LLamaWeights.LoadFromFile(modelParams);
                    WeightsCache[ModelPath] = weights;
                }
            }

            var parameters = new ModelParams(ModelPath)
            {
                ContextSize = (uint)ContextSize,
                GpuLayerCount = GpuLayerCount,
                Threads = Math.Max(1, Environment.ProcessorCount / 2)
            };

            var executor = new StatelessExecutor(weights, parameters);
            var inferenceParams = new InferenceParams
            {
                MaxTokens = 512,
                AntiPrompts = new List<string> { "User:", "Player:" },
                SamplingPipeline = new LLama.Sampling.DefaultSamplingPipeline
                {
                    Temperature = 0.7f,
                    TopP = 0.9f
                }
            };

            var sb = new StringBuilder();
            await foreach (var token in executor.InferAsync(prompt, inferenceParams, ct).ConfigureAwait(false))
            {
                sb.Append(token);
            }

            return sb.ToString().Trim();
        }
        catch (Exception ex)
        {
            return $"[LLamaSharp SLM Error] Exception during C# SLM inference: {ex.Message}";
        }
    }

    public void Dispose()
    {
        // Cache retains shared weights across invocations
    }
}
