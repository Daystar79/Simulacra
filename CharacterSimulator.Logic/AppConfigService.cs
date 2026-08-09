using System;
using System.IO;
using System.Text.Json;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic;

public class AppSettings
{
    public bool IsConfigured { get; set; } = false;
    /// <summary>Opaque card filename (e.g. a1b2c3d4e5f60718.json), not the display name.</summary>
    public string SelectedCharA { get; set; } = "";
    /// <summary>Opaque card filename, empty for solo, or legacy "None (Solo Roleplay)".</summary>
    public string SelectedCharB { get; set; } = "";
    public string SelectedLlmA { get; set; } = "Mock";
    public string SelectedLlmB { get; set; } = "Mock";
    public string SelectedGenre { get; set; } = SceneGenreCatalog.DefaultGenreId;
    public string ScenePrompt { get; set; } = SceneGenreCatalog.DefaultSceneFor(SceneGenreCatalog.DefaultGenreId);
    public int MaxTurns { get; set; } = 10;
    public string RoleplayMode { get; set; } = "PlayerGuided";

    // Roleplaying Engine Settings
    public string RoleplayLlmProvider { get; set; } = "AGY";
    public string RoleplayModelIdentifier { get; set; } = "agy-pro";
    public double Temperature { get; set; } = 0.7;
    public int MaxTokens { get; set; } = 1024;

    // Imaging Engine Settings — Pollinations is the product default (free, always on).
    // Higher-quality backends (SD WebUI, agent image emit) are opt-in via Setup → Imaging.
    public string ImageEngine { get; set; } = "PollinationsAI";
    /// <summary>Engine-specific model/checkpoint (e.g. Pollinations flux, SD checkpoint title).</summary>
    public string ImageModelIdentifier { get; set; } = "flux";
    public string ImageResolution { get; set; } = "512x512";
    /// <summary>
    /// Shared visual style for portraits and scene art (see ImageArtStyleCatalog ids: anime, photoreal, …).
    /// </summary>
    public string ImageArtStyle { get; set; } = Services.ImageArtStyleCatalog.DefaultStyleId;

    /// <summary>
    /// UI Theme preset (midnight, cyberpunk, matrix, amber, obsidian).
    /// </summary>
    public string UiTheme { get; set; } = Services.ThemeCatalog.DefaultThemeId;
}

public static class AppConfigService
{
    private static readonly string ConfigPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app_config.json");

    public static bool HasConfigFile()
    {
        return File.Exists(ConfigPath);
    }

    public static AppSettings LoadSettings()
    {
        try
        {
            if (File.Exists(ConfigPath))
            {
                string json = File.ReadAllText(ConfigPath);
                var settings = JsonSerializer.Deserialize<AppSettings>(json) ?? new AppSettings();
                NormalizeSettings(settings);
                return settings;
            }
        }
        catch (Exception ex)
        {
            AppLogger.Warning("[AppConfigService] LoadSettings: " + ex.Message);
        }
        return new AppSettings();
    }

    public static void SaveSettings(AppSettings settings)
    {
        try
        {
            if (settings == null) return;
            settings.IsConfigured = true;
            NormalizeSettings(settings);
            string json = JsonSerializer.Serialize(settings, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(ConfigPath, json);
        }
        catch (Exception ex)
        {
            AppLogger.Warning("[AppConfigService] SaveSettings: " + ex.Message);
        }
    }

    /// <summary>Never throw — bad saved values must not kill app startup.</summary>
    private static void NormalizeSettings(AppSettings settings)
    {
        try
        {
            settings.SelectedGenre = SceneGenreCatalog.GetById(settings.SelectedGenre).Id;
        }
        catch
        {
            settings.SelectedGenre = SceneGenreCatalog.DefaultGenreId;
        }

        // Empty / solo placeholders are not character files
        if (IsNoneSelection(settings.SelectedCharA))
            settings.SelectedCharA = "";
        if (IsNoneSelection(settings.SelectedCharB))
            settings.SelectedCharB = "";

        if (string.IsNullOrWhiteSpace(settings.ImageEngine))
            settings.ImageEngine = "PollinationsAI";
        if (string.IsNullOrWhiteSpace(settings.ImageModelIdentifier))
            settings.ImageModelIdentifier = "flux";
        // agent-default only valid for agent engines
        if (settings.ImageModelIdentifier.Equals("agent-default", StringComparison.OrdinalIgnoreCase) &&
            !settings.ImageEngine.StartsWith("Agent", StringComparison.OrdinalIgnoreCase))
        {
            settings.ImageModelIdentifier = "flux";
        }

        try
        {
            settings.ImageArtStyle = Services.ImageArtStyleCatalog.GetById(settings.ImageArtStyle).Id;
        }
        catch
        {
            settings.ImageArtStyle = Services.ImageArtStyleCatalog.DefaultStyleId;
        }

        try
        {
            settings.UiTheme = Services.ThemeCatalog.GetById(settings.UiTheme).Id;
        }
        catch
        {
            settings.UiTheme = Services.ThemeCatalog.DefaultThemeId;
        }
    }

    private static bool IsNoneSelection(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return true;
        if (value.StartsWith('(')) return true;
        if (value.StartsWith("None", StringComparison.OrdinalIgnoreCase)) return true;
        if (value.Contains("No Character", StringComparison.OrdinalIgnoreCase)) return true;
        if (value.Contains("Not Selected", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }
}
