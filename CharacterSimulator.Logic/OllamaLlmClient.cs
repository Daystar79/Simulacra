using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic;

/// <summary>
/// Native HTTP client for Ollama local server API (http://localhost:11434).
/// </summary>
public class OllamaLlmClient : ILLMClient
{
    public string Name => "Ollama API";
    public string ModelName { get; }
    public string BaseUrl { get; }

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(3) };

    public OllamaLlmClient(string modelName = "llama3", string baseUrl = "http://localhost:11434")
    {
        ModelName = string.IsNullOrWhiteSpace(modelName) ? "llama3" : modelName;
        BaseUrl = baseUrl.TrimEnd('/');
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
        try
        {
            var payload = new
            {
                model = ModelName,
                prompt = prompt,
                stream = false,
                options = new
                {
                    temperature = 0.75,
                    num_predict = 256,
                    repeat_penalty = 1.18,
                    presence_penalty = 0.1
                }
            };

            string json = JsonSerializer.Serialize(payload);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");

            using var response = await Http.PostAsync($"{BaseUrl}/api/generate", content, ct).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return $"[Ollama API Error] HTTP {(int)response.StatusCode} {response.ReasonPhrase}";
            }

            string responseBody = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            using var doc = JsonDocument.Parse(responseBody);
            if (doc.RootElement.TryGetProperty("response", out var respProp))
            {
                return respProp.GetString()?.Trim() ?? "";
            }

            return responseBody;
        }
        catch (Exception ex)
        {
            return $"[Ollama Error] Could not connect to Ollama server at {BaseUrl}: {ex.Message}";
        }
    }
}
