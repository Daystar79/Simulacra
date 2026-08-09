using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using CharacterSimulator.Logic.ProcessExecution;

namespace CharacterSimulator.Logic;

/// <summary>
/// CLI-based LLM client that executes external LLM providers
/// </summary>
public class CliLlmClient : ILLMClient, IDisposable
{
    public string Name { get; }
    public string ExecutablePath { get; }
    /// <summary>
    /// Argument template. Use <c>{0}</c> where the prompt should be inserted as a single argv entry.
    /// Example: <c>-p {0} --auto-approve --output text</c>
    /// </summary>
    public string ArgumentsTemplate { get; }
    public int TimeoutMs { get; set; } = 180_000;
    public int MaxRetries { get; set; } = 2;
    public TimeSpan RetryDelay { get; set; } = TimeSpan.FromSeconds(2);
    public int MaxPromptLength { get; set; } = 32000;
    
    private readonly ProcessExecutor _executor;
    private readonly object _pathLock = new object();
    private readonly CircuitBreaker _circuitBreaker;
    private string _extendedPath;
    private bool _disposed = false;
    
    /// <summary>
    /// Initializes a new CliLlmClient
    /// </summary>
    /// <param name="name">Client name for identification</param>
    /// <param name="executablePath">Path to the CLI executable</param>
    /// <param name="argumentsTemplate">Argument template with {0} for prompt</param>
    /// <summary>
    /// Circuit breaker failure threshold (default: 5 consecutive failures)
    /// </summary>
    public int CircuitBreakerFailureThreshold { get; set; } = 5;
    
    /// <summary>
    /// Circuit breaker reset timeout (default: 1 minute)
    /// </summary>
    public TimeSpan CircuitBreakerResetTimeout { get; set; } = TimeSpan.FromMinutes(1);
    
    public CliLlmClient(string name, string executablePath, string argumentsTemplate = "-p {0}")
    {
        Name = name ?? "CLI_LLM";
        ExecutablePath = executablePath ?? throw new ArgumentNullException(nameof(executablePath));
        ArgumentsTemplate = argumentsTemplate ?? "-p {0}";
        _circuitBreaker = new CircuitBreaker(CircuitBreakerFailureThreshold, CircuitBreakerResetTimeout);
        
        try
        {
            _executor = new ProcessExecutor(
                executablePath, 
                argumentsTemplate, 
                TimeSpan.FromMilliseconds(TimeoutMs));
        }
        catch (FileNotFoundException)
        {
            // Allow creation of client even if executable doesn't exist
            // This allows for deferred error handling during actual execution
            _executor = null;
        }
    }
    
    /// <summary>
    /// Synchronous prompt execution (backward compatibility)
    /// </summary>
    public string SendPrompt(Character character, string input, string sceneContext, string goalContext = "", string? conversationHistory = null)
    {
        // Handle case where executor wasn't created (executable not found)
        if (_executor == null)
        {
            return $"[{Name}] Executable not found: '{ExecutablePath}'. " +
                   "Check that it is installed and visible on PATH (GUI apps may miss ~/.local/bin).";
        }
        
        return SendPromptAsync(character, input, sceneContext, goalContext, CancellationToken.None, conversationHistory)
            .GetAwaiter().GetResult();
    }
    
    /// <summary>
    /// Asynchronous prompt execution with cancellation support
    /// </summary>
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
        
        // Handle case where executor wasn't created (executable not found)
        if (_executor == null)
        {
            _circuitBreaker.RecordFailure();
            return $"[{Name}] Executable not found: '{ExecutablePath}'. " +
                   "Check that it is installed and visible on PATH (GUI apps may miss ~/.local/bin).";
        }
        
        string prompt = PromptBuilder.BuildFullPrompt(character, input, sceneContext, goalContext, conversationHistory);
        
        if (prompt.Length > MaxPromptLength)
        {
            return $"[{Name}] Prompt too long ({prompt.Length} chars > {MaxPromptLength} max). Please reduce character card complexity or conversation history.";
        }
        
        try
        {
            string raw = await ExecuteWithRetryAsync(prompt, ct).ConfigureAwait(false);
            _circuitBreaker.RecordSuccess();
            return LlmResponseSanitizer.ClampToFirstReply(raw);
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
    }

    /// <summary>
    /// Free-form completion without RP prompt assembly (card builders, tools).
    /// </summary>
    public async Task<string> CompleteRawAsync(string prompt, CancellationToken ct = default)
    {
        if (!_circuitBreaker.CanExecute())
        {
            return $"[{Name}] Circuit breaker open. Too many failures. Retry in {_circuitBreaker.TimeUntilReset.TotalSeconds:F0}s or restart.";
        }

        if (_executor == null)
        {
            _circuitBreaker.RecordFailure();
            return $"[{Name}] Executable not found: '{ExecutablePath}'. Check that it is installed and visible on PATH (GUI apps may miss ~/.local/bin).";
        }

        if (string.IsNullOrWhiteSpace(prompt))
            return $"[{Name}] Empty prompt.";
        
        if (prompt.Length > MaxPromptLength)
            return $"[{Name}] Prompt too long ({prompt.Length} chars > {MaxPromptLength} max).";

        try
        {
            var result = await ExecuteWithRetryAsync(prompt, ct).ConfigureAwait(false);
            _circuitBreaker.RecordSuccess();
            return result;
        }
        catch (Exception)
        {
            _circuitBreaker.RecordFailure();
            throw;
        }
    }
    
    /// <summary>
    /// Executes the CLI with retry logic
    /// </summary>
    private async Task<string> ExecuteWithRetryAsync(string prompt, CancellationToken ct)
    {
        Exception lastException = null;
        
        for (int attempt = 0; attempt <= MaxRetries; attempt++)
        {
            try
            {
                var result = await _executor.ExecuteAsync(prompt, ct).ConfigureAwait(false);
                
                if (result.TimedOut && attempt < MaxRetries)
                {
                    lastException = new TimeoutException($"Attempt {attempt + 1} timed out");
                    await Task.Delay(RetryDelay, ct).ConfigureAwait(false);
                    continue;
                }
                
                if (result.Success)
                {
                    return CleanResponse(result.StandardOutput);
                }
                else
                {
                    return FormatProcessResult(result);
                }
            }
            catch (OperationCanceledException)
            {
                // Re-throw cancellation
                throw;
            }
            catch (Exception ex)
            {
                lastException = ex;
                if (attempt < MaxRetries)
                {
                    await Task.Delay(RetryDelay, ct).ConfigureAwait(false);
                    continue;
                }
                return FormatExceptionError(ex);
            }
        }
        
        return FormatMaxRetriesError(lastException);
    }
    
    /// <summary>
    /// Formats the process result into a response string
    /// </summary>
    private string FormatProcessResult(ProcessResult result)
    {
        if (string.IsNullOrWhiteSpace(result.StandardOutput) && 
            string.IsNullOrWhiteSpace(result.StandardError))
        {
            return result.ExitReason switch
            {
                ProcessExitReason.FileNotFound => 
                    $"[{Name}] Executable not found: '{ExecutablePath}'. " +
                    "Check that it is installed and visible on PATH (GUI apps may miss ~/.local/bin).",
                ProcessExitReason.PermissionDenied => 
                    $"[{Name}] Permission denied executing '{Path.GetFileName(ExecutablePath)}'.",
                ProcessExitReason.Timeout => 
                    $"[{Name}] Timed out after {TimeoutMs / 1000}s waiting for '{Path.GetFileName(ExecutablePath)}'. " +
                    "The provider may be waiting for tool approval or network. Try again or use Mock.",
                ProcessExitReason.Cancelled => 
                    $"[{Name}] Operation cancelled by user request.",
                _ => 
                    $"[{Name}] Exit {result.ExitCode} with empty stdout/stderr."
            };
        }
        
        if (!string.IsNullOrWhiteSpace(result.StandardOutput))
        {
            // Some CLIs write warnings to stderr but still produce a good answer
            if (result.ExitCode != 0 && !string.IsNullOrWhiteSpace(result.StandardError))
                return result.StandardOutput + $"\n[CLI note: exit {result.ExitCode}] {Truncate(result.StandardError, 400)}";
            return result.StandardOutput;
        }
        
        if (!string.IsNullOrWhiteSpace(result.StandardError))
        {
            return FormatCliError(result.ExitCode, result.StandardError);
        }
        
        return result.ErrorMessage ?? $"[{Name}] Unknown error with exit code {result.ExitCode}";
    }
    
    /// <summary>
    /// Formats an exception into an error string
    /// </summary>
    private string FormatExceptionError(Exception ex)
    {
        return ex switch
        {
            TimeoutException => $"[{Name}] Request timed out after multiple attempts",
            FileNotFoundException fnf => $"[{Name}] {fnf.Message}",
            OperationCanceledException => $"[{Name}] Operation was cancelled",
            _ => $"[{Name}] Unexpected error: {ex.Message}"
        };
    }
    
    /// <summary>
    /// Formats max retries exceeded error
    /// </summary>
    private string FormatMaxRetriesError(Exception lastException)
    {
        return $"[{Name}] Failed after {MaxRetries + 1} attempts. " +
               (lastException != null ? lastException.Message : "Unknown error");
    }
    
    /// <summary>
    /// Cleans the response by removing sensitive information
    /// </summary>
    private string CleanResponse(string response)
    {
        if (string.IsNullOrWhiteSpace(response))
            return response;
            
        // Remove potential system leaks from the response
        var leakAudit = Hygiene.SystemLeakLinter.Audit(response);
        return leakAudit.SanitizedDialogue;
    }
    
    /// <summary>
    /// Ensures extended PATH is available (cached)
    /// </summary>
    private string GetExtendedPath()
    {
        if (_extendedPath != null) return _extendedPath;
        
        lock (_pathLock)
        {
            if (_extendedPath != null) return _extendedPath;
            
            _extendedPath = BuildExtendedPath();
            return _extendedPath;
        }
    }
    
    /// <summary>
    /// Builds the extended PATH with common CLI tool locations
    /// </summary>
    private static string BuildExtendedPath()
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        var parts = new List<string>(path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries));
        
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (!string.IsNullOrEmpty(home))
            parts.Insert(0, Path.Combine(home, ".local", "bin"));
        
        // Add Unix paths only on Unix-like systems
        if (!OperatingSystem.IsWindows())
        {
            parts.Insert(0, "/usr/local/bin");
            parts.Insert(0, "/usr/bin");
        }
        
        // Remove duplicates while preserving order
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var uniqueParts = new List<string>();
        foreach (var part in parts)
        {
            if (seen.Add(part))
                uniqueParts.Add(part);
        }
        
        return string.Join(Path.PathSeparator, uniqueParts);
    }
    
    /// <summary>
    /// Formats CLI error message based on exit code and error output
    /// </summary>
    private string FormatCliError(int code, string error)
    {
        string msg = Truncate(error, 800);
        
        // Surface quota / auth clearly — never dress these up as in-character speech.
        if (msg.Contains("quota", StringComparison.OrdinalIgnoreCase) ||
            msg.Contains("rate limit", StringComparison.OrdinalIgnoreCase) ||
            msg.Contains("subscription", StringComparison.OrdinalIgnoreCase))
        {
            return $"[{Name}] Quota/limit: {msg}";
        }
        
        if (msg.Contains("auth", StringComparison.OrdinalIgnoreCase) ||
            msg.Contains("login", StringComparison.OrdinalIgnoreCase) ||
            msg.Contains("unauthorized", StringComparison.OrdinalIgnoreCase) ||
            msg.Contains("api key", StringComparison.OrdinalIgnoreCase))
        {
            return $"[{Name}] Auth: {msg}";
        }
        
        return $"[{Name}] Exit {code}: {msg}";
    }
    
    /// <summary>
    /// Truncates a string to maximum length
    /// </summary>
    private static string Truncate(string s, int max)
    {
        return s.Length <= max ? s : s.Substring(0, max) + "…";
    }
    
    /// <summary>
    /// Tests if this client is working properly
    /// </summary>
    public async Task<bool> TestAsync(TimeSpan? timeout = null)
    {
        return _executor != null && await LlmClientHealthCheck.TestClientAsync(_executor, timeout).ConfigureAwait(false);
    }
    
    /// <summary>
    /// Gets the status of this client
    /// </summary>
    public string GetStatus()
    {
        return _executor != null ? LlmClientHealthCheck.GetClientStatus(_executor) 
            : $"Executable not found: {ExecutablePath}";
    }
    
    /// <summary>
    /// Gets detailed status information
    /// </summary>
    public LlmClientStatus GetDetailedStatus()
    {
        return _executor != null ? LlmClientHealthCheck.GetDetailedStatus(_executor) 
            : new LlmClientStatus { Status = ClientStatus.ExecutableNotFound, Message = $"Executable not found: {ExecutablePath}" };
    }
    
    /// <summary>
    /// Gets version information for the CLI executable
    /// </summary>
    public FileVersionInfo GetVersionInfo()
    {
        return _executor?.GetVersionInfo();
    }
    
    /// <summary>
    /// Validates that the executable exists and is accessible
    /// </summary>
    public bool ValidateExecutable()
    {
        return _executor?.ValidateExecutable() ?? false;
    }
    
    /// <summary>
    /// Applies arguments template to the prompt (for external use)
    /// </summary>
    internal static void ApplyArguments(ProcessStartInfo psi, string template, string prompt)
    {
        template = string.IsNullOrWhiteSpace(template) ? "-p {0}" : template.Trim();
        template = template.Replace("\"{0}\"", "{0}");
        
        int idx = template.IndexOf("{0}", StringComparison.Ordinal);
        if (idx < 0)
        {
            foreach (var token in SplitTokens(template))
                psi.ArgumentList.Add(token);
            psi.ArgumentList.Add(prompt);
            return;
        }
        
        string before = template.Substring(0, idx);
        string after = template.Substring(idx + 3);
        
        foreach (var token in SplitTokens(before))
            psi.ArgumentList.Add(token);
        
        psi.ArgumentList.Add(prompt);
        
        foreach (var token in SplitTokens(after))
            psi.ArgumentList.Add(token);
    }
    
    private static IEnumerable<string> SplitTokens(string segment)
    {
        if (string.IsNullOrWhiteSpace(segment))
            yield break;
        
        foreach (var token in segment.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string t = token.Trim().Trim('"');
            if (t.Length > 0)
                yield return t;
        }
    }
    
    /// <summary>
    /// Disposes the client and releases resources
    /// </summary>
    public void Dispose()
    {
        if (!_disposed)
        {
            _executor?.Dispose();
            _disposed = true;
        }
    }
    
    /// <summary>
    /// Finalizer for safety
    /// </summary>
    ~CliLlmClient()
    {
        Dispose();
    }
}

/// <summary>
/// Extension methods for ILLMClient
/// </summary>
public static class LlmClientExtensions
{
    /// <summary>
    /// Tests if a client is working
    /// </summary>
    public static async Task<bool> TestAsync(this ILLMClient client, TimeSpan? timeout = null)
    {
        if (client is CliLlmClient cliClient)
        {
            return await cliClient.TestAsync(timeout).ConfigureAwait(false);
        }
        
        // For MockLLMClient, just return true
        return client is MockLLMClient;
    }
    
    /// <summary>
    /// Gets status of a client
    /// </summary>
    public static string GetStatus(this ILLMClient client)
    {
        if (client is CliLlmClient cliClient)
        {
            return cliClient.GetStatus();
        }
        
        return client is MockLLMClient ? "Mock/Ready" : "Unknown";
    }
}