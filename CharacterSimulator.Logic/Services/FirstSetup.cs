using CharacterSimulator.Logic.Data.Db;

namespace CharacterSimulator.Logic.Services;

/// <summary>
/// First-launch wizard gate. Separate from <see cref="AppSettings.IsConfigured"/> so
/// incidental settings writes (scene blur, theme) cannot skip onboarding.
/// </summary>
public static class FirstSetup
{
    public static bool NeedsWizard(AppSettings? settings)
    {
        return settings == null || !settings.FirstSetupComplete;
    }

    /// <summary>
    /// Silent seed created by older builds ("Player 1" / 1995-01-01, no PIN).
    /// The wizard replaces this instead of stacking a second profile.
    /// </summary>
    public static bool IsPlaceholderProfile(UserProfile? profile)
    {
        if (profile == null) return false;
        if (!string.IsNullOrEmpty(profile.PinHash)) return false;

        bool defaultName = profile.DisplayName.Equals("Player 1", StringComparison.OrdinalIgnoreCase)
            || profile.DisplayName.Equals("Default Player", StringComparison.OrdinalIgnoreCase);
        bool defaultDob = profile.DobYear == 1995 && profile.DobMonth == 1 && profile.DobDay == 1;

        return defaultName && defaultDob;
    }

    public static SlmModelOption RecommendedModel()
    {
        return SlmModelDownloaderService.AvailableModels.FirstOrDefault(m => m.IsDefault)
            ?? SlmModelDownloaderService.AvailableModels.OrderBy(m => m.ApproxSizeMb).First();
    }
}
