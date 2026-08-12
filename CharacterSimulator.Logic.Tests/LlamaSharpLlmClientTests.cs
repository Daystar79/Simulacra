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
