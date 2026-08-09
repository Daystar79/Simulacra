using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic.ProcessExecution;
using CharacterSimulator.Logic.Services;

namespace CharacterSimulator.Logic;

/// <summary>
/// Native HTTP client for Ollama local server API (http://localhost:11434).
/// </summary>
public class OllamaLlmClient : ILLMClient, IDisposable
{
    public string Name => "Ollama API";
    public string ModelName { get; }
    public string BaseUrl { get; }

    private readonly HttpClient _httpClient;
    private readonly CircuitBreaker _circuitBreaker;
    private bool _disposed = false;
    
    /// <summary>
    /// Circuit breaker failure threshold (default: 5 consecutive failures)
    /// </summary>
    public int CircuitBreakerFailureThreshold { get; set; } = 5;
    
    /// <summary>
    /// Circuit breaker reset timeout (default: 1 minute)
    /// </summary>
    public TimeSpan CircuitBreakerResetTimeout { get; set; } = TimeSpan.FromMinutes(1);

    public OllamaLlmClient(string modelName = "llama3", string baseUrl = "http://localhost:11434")
    {
        ModelName = string.IsNullOrWhiteSpace(modelName) ? "llama3" : modelName;
        BaseUrl = baseUrl.TrimEnd('/');
        _httpClient = new HttpClient { Timeout = TimeSpan.FromMinutes(3) };
        _circuitBreaker = new CircuitBreaker(CircuitBreakerFailureThreshold, CircuitBreakerResetTimeout);
    }

    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "", string? conversationHistory = null)
    {
        return SendPromptAsync(character, input, sceneContext, goalContext, CancellationToken.None, conversationHistory).GetAwaiter().GetResult();
    }

    public async Task<string> SendPromptAsync(
        Character character,
        string input,
        string sceneContext,
        string goalContext = "",
        CancellationToken ct = default,
        string? conversationHistory = null)
    {
        // Check circuit breaker
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        try
        {
            var format = LocalSlmPromptBuilder.DetectFormat(ModelName);
            string prompt = LocalSlmPromptBuilder.BuildPrompt(character, input, sceneContext, goalContext, conversationHistory, format);
            string raw = await CompleteRawAsync(prompt, ct).ConfigureAwait(false);
            _circuitBreaker.RecordSuccess();
            return LlmResponseSanitizer.ClampToFirstReply(raw, input);
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
    }

    public async Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        // Check circuit breaker
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        try
        {
            // Get model-specific context size and max tokens
            int numPredict = LlmModelFetcher.GetModelMaxTokens(ModelName, "Ollama", 512);
            int numCtx = LlmModelFetcher.GetModelContextSize(ModelName, "Ollama", 8192);
            
            var payload = new
            {
                model = ModelName,
                prompt = prompt,
                stream = false,
                raw = true,
                options = new
                {
                    temperature = 0.68,
                    top_p = 0.85,
                    top_k = 40,
                    num_ctx = numCtx,
                    num_predict = numPredict,
                    repeat_penalty = 1.18,
                    presence_penalty = 0.10,
                    stop = new[] { "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|end_of_text|>", "[Player]:", "[Player]", "\nPlayer:", "\nUser:" }
                }
            };

            string json = JsonSerializer.Serialize(payload);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");

            using var response = await _httpClient.PostAsync($"{BaseUrl}/api/generate", content, ct).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                _circuitBreaker.RecordFailure();
                return $"[Ollama] HTTP {(int)response.StatusCode} {response.ReasonPhrase}";
            }

            string responseBody = await response.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            using var doc = JsonDocument.Parse(responseBody);
            if (doc.RootElement.TryGetProperty("response", out var respProp))
            {
                _circuitBreaker.RecordSuccess();
                return respProp.GetString()?.Trim() ?? "";
            }

            _circuitBreaker.RecordSuccess();
            return responseBody;
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
    }

    /// <summary>
    /// Disposes the HttpClient and releases resources
    /// </summary>
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
                try { _httpClient?.Dispose(); } catch { }
            }
            _disposed = true;
        }
    }

    ~OllamaLlmClient()
    {
        Dispose(false);
    }
}
