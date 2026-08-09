using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.ProcessExecution;

/// <summary>
/// Health check utilities for LLM clients
/// </summary>
public static class LlmClientHealthCheck
{
    private const int DefaultTestTimeoutSeconds = 30;
    private const int MaximumTestPromptLength = 100;

    /// <summary>
    /// Tests an LLM client with a simple prompt
    /// </summary>
    /// <param name="executor">The process executor to test</param>
    /// <param name="timeout">Timeout for the test</param>
    /// <returns>True if the client is healthy, false otherwise</returns>
    public static async Task<bool> TestClientAsync(ProcessExecutor executor, TimeSpan? timeout = null)
    {
        if (executor == null) return false;

        try
        {
            var testPrompt = "Respond with a single word: hello";
            var testTimeout = timeout ?? TimeSpan.FromSeconds(DefaultTestTimeoutSeconds);

            using var cts = new CancellationTokenSource(testTimeout);

            var result = await executor.ExecuteAsync(testPrompt, cts.Token).ConfigureAwait(false);

            // Client is healthy if it produced any non-error output
            return result.Success || !string.IsNullOrWhiteSpace(result.StandardOutput);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Gets the status of an LLM client
    /// </summary>
    /// <param name="executor">The process executor to check</param>
    /// <returns>Status string describing the client state</returns>
    public static string GetClientStatus(ProcessExecutor executor)
    {
        if (executor == null)
            return "Client not initialized";

        if (!executor.ValidateExecutable())
            return $"Executable not found: {executor.ExecutablePath}";

        try
        {
            var versionInfo = executor.GetVersionInfo();
            if (versionInfo != null)
            {
                return $"Ready - {versionInfo.FileVersion} (Active: {executor.ActiveProcesses} processes)";
            }

            // Try to get file info
            var fileInfo = new FileInfo(executor.ExecutablePath);
            return $"Ready - {fileInfo.LastWriteTime:yyyy-MM-dd} (Active: {executor.ActiveProcesses} processes)";
        }
        catch (Exception ex)
        {
            return $"Error: {ex.Message}";
        }
    }

    /// <summary>
    /// Gets detailed status information about a process executor
    /// </summary>
    /// <param name="executor">The process executor to check</param>
    /// <returns>Detailed status information</returns>
    public static LlmClientStatus GetDetailedStatus(ProcessExecutor executor)
    {
        if (executor == null)
        {
            return new LlmClientStatus
            {
                Status = ClientStatus.NotInitialized,
                Message = "Client not initialized"
            };
        }

        var status = new LlmClientStatus
        {
            ExecutablePath = executor.ExecutablePath,
            ArgumentsTemplate = executor.ArgumentsTemplate,
            DefaultTimeout = executor.DefaultTimeout,
            ActiveProcesses = executor.ActiveProcesses,
            Status = executor.ValidateExecutable() ? ClientStatus.Ready : ClientStatus.ExecutableNotFound
        };

        try
        {
            var versionInfo = executor.GetVersionInfo();
            if (versionInfo != null)
            {
                status.Version = versionInfo.FileVersion ?? "Unknown";
                status.ProductName = versionInfo.ProductName ?? "Unknown";
                status.Status = ClientStatus.Ready;
            }

            var fileInfo = new FileInfo(executor.ExecutablePath);
            status.FileSize = fileInfo.Length;
            status.LastModified = fileInfo.LastWriteTime;
            status.Message = "Client is ready to use";
        }
        catch (Exception ex)
        {
            status.Status = ClientStatus.Error;
            status.Message = ex.Message;
        }

        return status;
    }

    /// <summary>
    /// Validates that a CLI tool is accessible and working
    /// </summary>
    /// <param name="executablePath">Path to the executable</param>
    /// <param name="testArguments">Arguments to use for testing</param>
    /// <param name="expectedOutput">Expected output substring (optional)</param>
    /// <param name="timeout">Timeout for the validation</param>
    /// <returns>True if the tool is working, false otherwise</returns>
    public static async Task<bool> ValidateCliToolAsync(
        string executablePath,
        string testArguments = "--version",
        string expectedOutput = null,
        TimeSpan? timeout = null)
    {
        if (string.IsNullOrWhiteSpace(executablePath) || !File.Exists(executablePath))
            return false;

        try
        {
            using var executor = new ProcessExecutor(
                executablePath,
                testArguments,
                timeout ?? TimeSpan.FromSeconds(DefaultTestTimeoutSeconds));

            var result = await executor.ExecuteAsync("", CancellationToken.None).ConfigureAwait(false);

            if (!string.IsNullOrEmpty(expectedOutput))
            {
                return result.StandardOutput.Contains(expectedOutput, StringComparison.OrdinalIgnoreCase);
            }

            return result.Success || !string.IsNullOrWhiteSpace(result.StandardOutput);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Pings an LLM client to check responsiveness
    /// </summary>
    /// <param name="executor">The process executor to ping</param>
    /// <param name="timeout">Timeout for the ping</param>
    /// <returns>Ping result with latency information</returns>
    public static async Task<PingResult> PingAsync(ProcessExecutor executor, TimeSpan? timeout = null)
    {
        var pingTimeout = timeout ?? TimeSpan.FromSeconds(10);
        var stopwatch = Stopwatch.StartNew();

        try
        {
            using var cts = new CancellationTokenSource(pingTimeout);
            var result = await executor.ExecuteAsync("ping", cts.Token).ConfigureAwait(false);

            stopwatch.Stop();

            return new PingResult
            {
                Success = result.Success,
                Latency = stopwatch.Elapsed,
                TimedOut = result.TimedOut,
                ErrorMessage = result.ErrorMessage
            };
        }
        catch (Exception ex)
        {
            stopwatch.Stop();
            return new PingResult
            {
                Success = false,
                Latency = stopwatch.Elapsed,
                TimedOut = true,
                ErrorMessage = ex.Message
            };
        }
    }
}

/// <summary>
/// Client status enumeration
/// </summary>
public enum ClientStatus
{
    /// <summary>Client is not initialized</summary>
    NotInitialized,
    /// <summary>Client is ready to use</summary>
    Ready,
    /// <summary>Executable file is not found</summary>
    ExecutableNotFound,
    /// <summary>Client has an error</summary>
    Error,
    /// <summary>Client is busy</summary>
    Busy
}

/// <summary>
/// Detailed status information for an LLM client
/// </summary>
public class LlmClientStatus
{
    /// <summary>Overall status of the client</summary>
    public ClientStatus Status { get; set; }

    /// <summary>Status message</summary>
    public string Message { get; set; } = "";

    /// <summary>Path to the executable</summary>
    public string ExecutablePath { get; set; } = "";

    /// <summary>Arguments template</summary>
    public string ArgumentsTemplate { get; set; } = "";

    /// <summary>Default timeout</summary>
    public TimeSpan DefaultTimeout { get; set; }

    /// <summary>Number of active processes</summary>
    public int ActiveProcesses { get; set; }

    /// <summary>File version</summary>
    public string Version { get; set; } = "Unknown";

    /// <summary>Product name</summary>
    public string ProductName { get; set; } = "Unknown";

    /// <summary>File size in bytes</summary>
    public long FileSize { get; set; } = 0L;

    /// <summary>Last modified date</summary>
    public DateTime LastModified { get; set; }
}

/// <summary>
/// Result of a ping operation
/// </summary>
public class PingResult
{
    /// <summary>Whether the ping was successful</summary>
    public bool Success { get; set; }

    /// <summary>Latency of the ping</summary>
    public TimeSpan Latency { get; set; }

    /// <summary>Whether the ping timed out</summary>
    public bool TimedOut { get; set; }

    /// <summary>Error message if any</summary>
    public string? ErrorMessage { get; set; }
}