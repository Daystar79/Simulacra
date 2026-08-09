using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic;

public class RoleplaySessionData
{
    public string SessionId { get; set; } = Guid.NewGuid().ToString();
    public DateTime SavedAt { get; set; } = DateTime.Now;
    public string SceneContext { get; set; } = string.Empty;
    public Character CharacterA { get; set; } = new();
    public Character CharacterB { get; set; } = new();
    public List<TurnStepEventArgs> History { get; set; } = new();
}

public static class SessionService
{
    public static bool SaveSession(string path, RoleplaySessionData sessionData)
    {
        try
        {
            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            var json = JsonSerializer.Serialize(sessionData, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(path, json);
            return true;
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[SessionService] Failed to save session: {ex.Message}");
            return false;
        }
    }

    public static RoleplaySessionData? LoadSession(string path)
    {
        try
        {
            if (!File.Exists(path)) return null;
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<RoleplaySessionData>(json);
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[SessionService] Failed to load session from {path}: {ex.Message}");
            return null;
        }
    }
}
