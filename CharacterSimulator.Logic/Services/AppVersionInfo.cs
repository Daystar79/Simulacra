using System;
using System.Reflection;

namespace CharacterSimulator.Logic.Services;

public static class AppVersionInfo
{
    public const string AppName = "Simulacra";
    public const string CurrentVersion = "1.0.0";
    public const string RepoOwner = "Daystar79";
    public const string RepoName = "Simulacra";

    public static string DisplayVersion => $"v{CurrentVersion}";

    public static string FullVersionString
    {
        get
        {
            var asm = Assembly.GetExecutingAssembly();
            var infoVer = asm.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
            return string.IsNullOrWhiteSpace(infoVer) ? DisplayVersion : $"v{infoVer}";
        }
    }
}
