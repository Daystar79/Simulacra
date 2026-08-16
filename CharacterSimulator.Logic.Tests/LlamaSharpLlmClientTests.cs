using System;
using System.IO;
using System.Threading.Tasks;
using CharacterSimulator.Logic;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

public class LlamaSharpLlmClientTests
{
    [Fact]
    public void DiscoverGgufModels_FindsExistingModels()
    {
        var models = LlamaSharpLlmClient.DiscoverGgufModels();
        Assert.NotNull(models);
    }

    [Fact]
    public void DefaultGpuLayerCount_IsCpuOnly()
    {
        var client = new LlamaSharpLlmClient("TestLlamaSharp", "missing-model.gguf");
        Assert.Equal(0, client.GpuLayerCount);
        Assert.Equal(new[] { 0 }, LlamaSharpLlmClient.GpuLayerFallbackPlan(client.GpuLayerCount));
    }

    [Fact]
    public void GpuLayerFallbackPlan_AlwaysEndsOnCpu()
    {
        Assert.Equal(new[] { 0 }, LlamaSharpLlmClient.GpuLayerFallbackPlan(0));
        Assert.Equal(new[] { 20, 0 }, LlamaSharpLlmClient.GpuLayerFallbackPlan(20));
        Assert.Equal(new[] { 99, 20, 0 }, LlamaSharpLlmClient.GpuLayerFallbackPlan(99));
        Assert.Equal(0, LlamaSharpLlmClient.GpuLayerFallbackPlan(32)[^1]);
    }

    [Fact]
    public void ResolveThreadCount_LeavesRoomForUi()
    {
        int threads = LlamaSharpLlmClient.ResolveThreadCount();
        Assert.InRange(threads, 1, Environment.ProcessorCount);
        if (Environment.ProcessorCount > 2)
            Assert.True(threads < Environment.ProcessorCount);
    }

    [Fact]
    public void CountSharedPrefix_StopsAtFirstDivergence()
    {
        Assert.Equal(0, LlamaSharpLlmClient.CountSharedPrefix(Array.Empty<int>(), new[] { 1 }));
        Assert.Equal(3, LlamaSharpLlmClient.CountSharedPrefix(new[] { 1, 2, 3, 4 }, new[] { 1, 2, 3, 9 }));
        Assert.Equal(2, LlamaSharpLlmClient.CountSharedPrefix(new[] { 1, 2 }, new[] { 1, 2, 3 }));
        Assert.Equal(0, LlamaSharpLlmClient.CountSharedPrefix(new[] { 9, 2 }, new[] { 1, 2 }));
    }

    [Fact]
    public void ReleaseCachedRuntime_DoesNotThrowForUnknownPath()
    {
        LlamaSharpLlmClient.ReleaseCachedRuntime(null);
        LlamaSharpLlmClient.ReleaseCachedRuntime("/tmp/does-not-exist.gguf");
    }

    [Fact]
    public async Task SendPromptAsync_WithDolphinModel_ExecutesInference()
    {
        string modelPath = "/mnt/Books/Source/CharacterSimulator.UI/CharacterSimulator.GUI/bin/Debug/net10.0/Models/Dolphin3.0-Llama3.2-1B.Q4_K_M.gguf";
        if (File.Exists(modelPath))
        {
            var character = new Character { Name = "Serena" };
            var client = new LlamaSharpLlmClient("TestLlamaSharp", modelPath);
            string response = await client.SendPromptAsync(character, "Hello Serena", "A quiet garden");
            Assert.False(string.IsNullOrWhiteSpace(response));
        }
    }
}
