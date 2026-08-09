using System;
using System.Collections.Generic;
using System.IO;

namespace CharacterSimulator.Logic;

public class Logger
{
    private readonly string _logPath;
    private readonly object _fileLock = new object();

    public Logger(string logPath)
    {
        try
        {
            var dir = Path.GetDirectoryName(logPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            _logPath = logPath;
            File.WriteAllText(_logPath, $"[LOG START] {DateTime.Now}\n\n");
        }
        catch (Exception ex)
        {
            // If we can't initialize the logger, use a fallback path
            _logPath = Path.Combine(Path.GetTempPath(), "character_simulator_fallback.log");
            try
            {
                File.WriteAllText(_logPath, $"[LOG START FALLBACK] {DateTime.Now} - Original path failed: {ex.Message}\n\n");
            }
            catch { /* If even fallback fails, give up */ }
        }
    }

    private void SafeAppend(string text)
    {
        if (string.IsNullOrEmpty(_logPath)) return;
        try
        {
            lock (_fileLock)
            {
                File.AppendAllText(_logPath, text);
            }
        }
        catch { /* Silently ignore file I/O errors */ }
    }

    public void LogScene(string scene) => SafeAppend($"[SCENE] {scene}\n");

    public void LogTurn(string character, string dialogue, List<string> somaticZones, int bond, string? goalType = null, string? goalStatus = null)
    {
        var line = $"[{character}] (Bond: {bond}, Somatic: {string.Join(", ", somaticZones)}) {dialogue}";
        if (goalType != null) line += $" [Goal: {goalType} - {goalStatus}]";
        line += "\n";
        SafeAppend(line);
    }

    public void LogGoalSuccess(string character, string goalType, string target) =>
        SafeAppend($"[GOAL SUCCESS] {character} achieved {goalType} with {target}!\n");

    public void LogGoalFailure(string character, string goalType, string target) =>
        SafeAppend($"[GOAL FAILURE] {character} failed {goalType} with {target}.\n");
}

/// <summary>
/// Centralized application logging with multiple output targets
/// </summary>
public static class AppLogger
{
    private static readonly object _consoleLock = new object();
    private static readonly object _debugLock = new object();
    
    /// <summary>
    /// Log levels for filtering
    /// </summary>
    public enum LogLevel
    {
        Debug,
        Info,
        Warning,
        Error,
        Critical
    }
    
    /// <summary>
    /// Minimum log level to output (default: Info)
    /// </summary>
    public static LogLevel MinLogLevel { get; set; } = LogLevel.Info;
    
    /// <summary>
    /// Whether to log to Debug output
    /// </summary>
    public static bool LogToDebug { get; set; } = true;
    
    /// <summary>
    /// Whether to log to console
    /// </summary>
    public static bool LogToConsole { get; set; } = true;
    
    /// <summary>
    /// Log a message with the specified level
    /// </summary>
    public static void Log(LogLevel level, string message, Exception? exception = null)
    {
        if (level < MinLogLevel) return;
        
        string formattedMessage = FormatMessage(level, message, exception);
        
        if (LogToDebug)
        {
            lock (_debugLock)
            {
                System.Diagnostics.Debug.WriteLine(formattedMessage);
            }
        }
        
        if (LogToConsole)
        {
            lock (_consoleLock)
            {
                Console.WriteLine(formattedMessage);
            }
        }
    }
    
    /// <summary>
    /// Log debug message
    /// </summary>
    public static void Debug(string message) => Log(LogLevel.Debug, message);
    
    /// <summary>
    /// Log information message
    /// </summary>
    public static void Info(string message) => Log(LogLevel.Info, message);
    
    /// <summary>
    /// Log warning message
    /// </summary>
    public static void Warning(string message) => Log(LogLevel.Warning, message);
    
    /// <summary>
    /// Log error message
    /// </summary>
    public static void Error(string message, Exception? exception = null) => Log(LogLevel.Error, message, exception);
    
    /// <summary>
    /// Log critical message
    /// </summary>
    public static void Critical(string message, Exception? exception = null) => Log(LogLevel.Critical, message, exception);
    
    private static string FormatMessage(LogLevel level, string message, Exception? exception)
    {
        string timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
        string levelStr = level.ToString().ToUpper();
        
        string baseMessage = $"[{timestamp}] [{levelStr}] {message}";
        
        if (exception != null)
        {
            baseMessage += $"\n[EXCEPTION] {exception.GetType().Name}: {exception.Message}\n{exception.StackTrace}";
        }
        
        return baseMessage;
    }
}
