using System;
using System.Collections.Generic;
using System.IO;
using CharacterSimulator.Logic.Data.Db;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Services;

public class ProfileService : IDisposable
{
    private static readonly Lazy<ProfileService> _lazyInstance = new Lazy<ProfileService>(() => new ProfileService());
    private bool _disposed = false;

    public static bool HasInstance => _lazyInstance.IsValueCreated;
    public static UserProfile? ActiveProfileOrNull => _lazyInstance.Value.ActiveProfile;

    public static ProfileService Instance => _lazyInstance.Value;

    private readonly SqliteConnection _conn;
    private readonly ProfileRepository _profileRepo;
    private readonly SessionRepository _sessionRepo;
    private readonly CharacterProgressRepository _progressRepo;
    private readonly CharacterCatalogRepository _catalogRepo;
    private readonly CharacterPortraitRepository _portraitRepo;
    private readonly InstalledEngineRepository _installedEnginesRepo;

    public event Action<UserProfile?>? OnActiveProfileChanged;

    public UserProfile? ActiveProfile { get; private set; }

    public ProfileService(string? dbPath = null)
    {
        _conn = AppDbInitializer.CreateConnection(dbPath);
        AppDbInitializer.InitializeDatabase(_conn);

        _profileRepo = new ProfileRepository(_conn);
        _sessionRepo = new SessionRepository(_conn);
        _progressRepo = new CharacterProgressRepository(_conn);
        _catalogRepo = new CharacterCatalogRepository(_conn);
        _portraitRepo = new CharacterPortraitRepository(_conn);
        _installedEnginesRepo = new InstalledEngineRepository(_conn);

        // Bind indexes only — full catalog reconcile is deferred so first UI paint is not blocked.
        CharacterCatalog.BindIndex(_catalogRepo);
        CharacterPortraitService.Bind(_portraitRepo, _catalogRepo);
        InstalledEngineStore.Bind(_installedEnginesRepo);

        EnsureDefaultProfileExists();
    }

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
                try { _conn?.Dispose(); } catch { }
            }
            _disposed = true;
        }
    }

    ~ProfileService()
    {
        Dispose(false);
    }

    private void SetActiveProfile(UserProfile? profile)
    {
        ActiveProfile = profile;
        Safety.AdultAuth.SetUserAdultAttested(profile?.IsAdultAttested ?? false);
        OnActiveProfileChanged?.Invoke(ActiveProfile);
    }

    private void EnsureDefaultProfileExists()
    {
        var profiles = _profileRepo.GetAllProfiles();
        if (profiles.Count == 0)
        {
            // Seed default player profile (adult by default)
            SetActiveProfile(_profileRepo.CreateProfile("Player 1", 1995, 1, 1, pin: null, adultAttested: false));
        }
        else
        {
            SetActiveProfile(profiles[0]);
        }
    }

    public List<UserProfile> GetAllProfiles() => _profileRepo.GetAllProfiles();

    public UserProfile CreateProfile(string name, int dobYear, int dobMonth, int dobDay, string? pin = null, bool adultAttested = false)
    {
        var profile = _profileRepo.CreateProfile(name, dobYear, dobMonth, dobDay, pin, adultAttested);
        SetActiveProfile(profile);
        return profile;
    }

    public bool SwitchProfile(string profileId, string? pin = null)
    {
        var profile = _profileRepo.GetById(profileId);
        if (profile == null) return false;

        if (!_profileRepo.VerifyPin(profile, pin ?? "")) return false;

        _profileRepo.TouchLastOpened(profileId);
        SetActiveProfile(profile);
        return true;
    }

    public bool DeleteProfile(string profileId)
    {
        bool success = _profileRepo.DeleteProfile(profileId);
        if (success && ActiveProfile?.Id == profileId)
        {
            var remaining = _profileRepo.GetAllProfiles();
            SetActiveProfile(remaining.Count > 0 ? remaining[0] : null);
        }
        return success;
    }

    public bool UpdatePin(string profileId, string? oldPin, string? newPin)
    {
        bool success = _profileRepo.UpdatePin(profileId, oldPin, newPin);
        if (success && ActiveProfile?.Id == profileId)
        {
            ActiveProfile = _profileRepo.GetById(profileId);
        }
        return success;
    }

    public bool ResetPinWithRecoveryCode(string profileId, string recoveryCode, string? newPin)
    {
        bool success = _profileRepo.ResetPinWithRecoveryCode(profileId, recoveryCode, newPin);
        if (success && ActiveProfile?.Id == profileId)
        {
            ActiveProfile = _profileRepo.GetById(profileId);
        }
        return success;
    }

    public void SetDepictionMode(string profileId, string depictionMode)
    {
        string normalized = Safety.DepictionController.NormalizeDepictionMode(ActiveProfile, depictionMode);
        _profileRepo.SetDepictionMode(profileId, normalized);
        if (ActiveProfile?.Id == profileId)
        {
            ActiveProfile.DepictionMode = normalized;
        }
    }

    public bool BackupProfileDatabase(string destinationPath)
    {
        try
        {
            string srcPath = AppDbInitializer.GetDatabasePath();
            if (!File.Exists(srcPath)) return false;

            var dir = Path.GetDirectoryName(destinationPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            File.Copy(srcPath, destinationPath, overwrite: true);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public ProfileRepository Profiles => _profileRepo;
    public SessionRepository Sessions => _sessionRepo;
    public CharacterProgressRepository Progress => _progressRepo;
    public CharacterCatalogRepository Catalog => _catalogRepo;
    public CharacterPortraitRepository Portraits => _portraitRepo;
    public InstalledEngineRepository InstalledEngines => _installedEnginesRepo;

    /// <summary>Rescan Characters/ into the SQLite catalog index (Refresh UI / post-derive).</summary>
    public int ReconcileCharacterCatalog() => CharacterCatalog.ReconcileFromDisk();
}
