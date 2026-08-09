using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace CharacterSimulator.Logic.ProcessExecution;

/// <summary>
/// Service for executing external processes with comprehensive error handling,
/// timeout support, and resource management.
/// </summary>
public class ProcessExecutor : IDisposable
{
    private readonly string _executablePath;
    private readonly string _argumentsTemplate;
    private readonly TimeSpan _defaultTimeout;
    private readonly string _workingDirectory;
    
    private bool _disposed = false;
    private int _activeProcesses = 0;
    private readonly object _processLock = new object();
    
    public ProcessExecutor(string executablePath, string argumentsTemplate, 
                        TimeSpan defaultTimeout, 
                        string workingDirectory = null)
    {
        if (string.IsNullOrWhiteSpace(executablePath))
            throw new ArgumentException("Executable path cannot be null or empty", nameof(executablePath));
            
        if (!File.Exists(executablePath))
            throw new FileNotFoundException("Executable file not found", executablePath);
            
        _executablePath = executablePath;
        _argumentsTemplate = argumentsTemplate ?? "-p {0}";
        _defaultTimeout = defaultTimeout;
        _workingDirectory = workingDirectory ?? Directory.GetCurrentDirectory();
    }
    
    public string ExecutablePath => _executablePath;
    public string ArgumentsTemplate => _argumentsTemplate;
    public TimeSpan DefaultTimeout => _defaultTimeout;
    public int ActiveProcesses => _activeProcesses;
    
    /// <summary>
    /// Executes the process with the given input as a command line argument.
    /// Uses ReadToEndAsync for output reading, matching the original CliLlmClient behavior.
    /// </summary>
    public async Task<ProcessResult> ExecuteAsync(string input, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref _activeProcesses);
        var stopwatch = Stopwatch.StartNew();
        
        try
        {
            if (!File.Exists(_executablePath))
            {
                return new ProcessResult
                {
                    ExecutablePath = _executablePath,
                    ExitCode = -1,
                    ExitReason = ProcessExitReason.FileNotFound,
                    ErrorMessage = $"Executable not found: {_executablePath}",
                    ExecutionTime = stopwatch.Elapsed
                };
            }
            
            var psi = CreateProcessStartInfo(input);
            
            using var process = new Process { StartInfo = psi };
            
            // For cancellation with timeout
            using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            linkedCts.CancelAfter(_defaultTimeout);
            
            // Track process exit using TaskCompletionSource
            var exitTcs = new TaskCompletionSource<int>();
            process.EnableRaisingEvents = true;
            process.Exited += (sender, e) => exitTcs.TrySetResult(process.ExitCode);
            
            // Register cancellation handler
            linkedCts.Token.Register(() => 
            {
                try { process.Kill(true); } catch { }
                exitTcs.TrySetCanceled(linkedCts.Token);
            });
            
            process.Start();
            
            // Close stdin immediately to signal EOF
            try { process.StandardInput.Close(); } catch { }
            
            // Read stdout + stderr concurrently to avoid pipe deadlocks
            Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
            Task<string> stderrTask = process.StandardError.ReadToEndAsync();
            
            // Wait for process to exit
            int exitCode;
            try
            {
                exitCode = await exitTcs.Task.ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                // Timeout or cancellation - try to get partial output
                stopwatch.Stop();
                
                string partialStdout = "";
                string partialStderr = "";
                
                if (stdoutTask.IsCompleted)
                    partialStdout = stdoutTask.Result;
                if (stderrTask.IsCompleted)
                    partialStderr = stderrTask.Result;
                
                var exitReason = cancellationToken.IsCancellationRequested
                    ? ProcessExitReason.Cancelled
                    : ProcessExitReason.Timeout;
                
                return new ProcessResult
                {
                    ExecutablePath = _executablePath,
                    ExitCode = -1,
                    StandardOutput = partialStdout.Trim(),
                    StandardError = partialStderr.Trim(),
                    ExitReason = exitReason,
                    ExecutionTime = stopwatch.Elapsed,
                    ErrorMessage = exitReason == ProcessExitReason.Timeout
                        ? $"Execution timed out after {_defaultTimeout.TotalSeconds}s"
                        : "Execution was cancelled by user request"
                };
            }
            
            // Check if explicit cancellation was requested
            linkedCts.Token.ThrowIfCancellationRequested();
            
            // Drain readers to get all output
            await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);
            
            string output = stdoutTask.IsCompletedSuccessfully ? stdoutTask.Result : "";
            string error = stderrTask.IsCompletedSuccessfully ? stderrTask.Result : "";
            
            stopwatch.Stop();
            
            // Determine exit reason
            var finalExitReason = exitCode == 0 
                ? ProcessExitReason.Success 
                : ProcessExitReason.ProcessError;
            
            return new ProcessResult
            {
                ExecutablePath = _executablePath,
                ExitCode = exitCode,
                StandardOutput = output.Trim(),
                StandardError = error.Trim(),
                ExitReason = finalExitReason,
                ExecutionTime = stopwatch.Elapsed
            };
        }
        catch (OperationCanceledException)
        {
            stopwatch.Stop();
            return new ProcessResult
            {
                ExecutablePath = _executablePath,
                ExitCode = -1,
                ExitReason = cancellationToken.IsCancellationRequested 
                    ? ProcessExitReason.Cancelled 
                    : ProcessExitReason.Timeout,
                ExecutionTime = stopwatch.Elapsed,
                ErrorMessage = cancellationToken.IsCancellationRequested 
                    ? "Execution was cancelled by user request" 
                    : $"Execution timed out after {_defaultTimeout.TotalSeconds}s"
            };
        }
        catch (Exception ex)
        {
            stopwatch.Stop();
            return new ProcessResult
            {
                ExecutablePath = _executablePath,
                ExitCode = -1,
                ExitReason = ProcessExitReason.Unknown,
                ExecutionTime = stopwatch.Elapsed,
                ErrorMessage = $"Process execution failed: {ex.Message}",
                StandardError = ex.ToString()
            };
        }
        finally
        {
            Interlocked.Decrement(ref _activeProcesses);
        }
    }
    
    private ProcessStartInfo CreateProcessStartInfo(string input)
    {
        var psi = new ProcessStartInfo
        {
            FileName = _executablePath,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = _workingDirectory
        };
        
        // Use ArgumentList for proper argument escaping
        ApplyArgumentsToArgumentList(psi, _argumentsTemplate, input);
        
        // Enhance PATH to include common CLI tool locations
        EnhancePath(psi);
        
        // Set environment variables for better CLI behavior / headless agents
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["TERM"] = "dumb";
        psi.Environment["NO_COLOR"] = "1";
        psi.Environment["CI"] = "1"; // many CLIs (incl. Grok Build) stay non-interactive when CI is set
        
        return psi;
    }
    
    private static void ApplyArgumentsToArgumentList(ProcessStartInfo psi, string template, string input)
    {
        template = string.IsNullOrWhiteSpace(template) ? "-p {0}" : template.Trim();
        template = template.Replace("\"{0}\"", "{0}");
        
        int idx = template.IndexOf("{0}", StringComparison.Ordinal);
        if (idx < 0)
        {
            foreach (var token in SplitTokens(template))
                psi.ArgumentList.Add(token);
            psi.ArgumentList.Add(input);
            return;
        }
        
        string before = template.Substring(0, idx);
        string after = template.Substring(idx + 3);
        
        foreach (var token in SplitTokens(before))
            psi.ArgumentList.Add(token);
        
        psi.ArgumentList.Add(input);
        
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
    
    private static void EnhancePath(ProcessStartInfo psi)
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        string localBin = !string.IsNullOrEmpty(home) 
            ? Path.Combine(home, ".local", "bin") 
            : null;
        
        var pathBuilder = new System.Text.StringBuilder();
        
        var extraPaths = new[] { "/usr/local/bin", "/usr/bin", "/bin" };
        
        if (!string.IsNullOrEmpty(localBin) && Directory.Exists(localBin))
        {
            if (pathBuilder.Length > 0) pathBuilder.Append(Path.PathSeparator);
            pathBuilder.Append(localBin);
        }
        
        foreach (var extraPath in extraPaths)
        {
            if (Directory.Exists(extraPath))
            {
                if (pathBuilder.Length > 0) pathBuilder.Append(Path.PathSeparator);
                pathBuilder.Append(extraPath);
            }
        }
        
        if (pathBuilder.Length > 0) pathBuilder.Append(Path.PathSeparator);
        pathBuilder.Append(path);
        
        var pathParts = pathBuilder.ToString().Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries);
        var uniquePaths = new HashSet<string>(pathParts, StringComparer.OrdinalIgnoreCase);
        
        psi.Environment["PATH"] = string.Join(Path.PathSeparator, uniquePaths);
    }
    
    public void Dispose()
    {
        if (!_disposed)
        {
            var timeout = TimeSpan.FromSeconds(30);
            var startTime = DateTime.UtcNow;
            
            while (_activeProcesses > 0 && (DateTime.UtcNow - startTime) < timeout)
            {
                Thread.Sleep(100);
            }
            
            _disposed = true;
        }
    }
    
    public bool ValidateExecutable()
    {
        try
        {
            if (!File.Exists(_executablePath))
                return false;
            
            try
            {
                using var stream = File.OpenRead(_executablePath);
                var buffer = new byte[1];
                return stream.Read(buffer, 0, 1) > 0;
            }
            catch
            {
                return false;
            }
        }
        catch
        {
            return false;
        }
    }
    
    public FileVersionInfo GetVersionInfo()
    {
        try
        {
            return FileVersionInfo.GetVersionInfo(_executablePath);
        }
        catch
        {
            return null;
        }
    }
}
