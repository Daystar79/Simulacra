using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace CharacterSimulator.Logic;

public class LlmProviderInfo
{
    public string Name { get; set; } = string.Empty;
    public string ExecutablePath { get; set; } = string.Empty;
    /// <summary>Argv template; <c>{0}</c> is replaced by the prompt as a single argument.</summary>
    public string ArgumentsTemplate { get; set; } = "-p {0}";
    public bool IsAvailable { get; set; }
    /// <summary>Extra names that map to this provider (e.g. "mistral" → Vibe).</summary>
    public List<string> Aliases { get; set; } = new();
}

public static class LlmDiscoveryService
{
    private static readonly List<LlmProviderInfo> KnownProviders = new()
    {
        new LlmProviderInfo
        {
            Name = "Agy (Gemini CLI)",
            ExecutablePath = "agy",
            // print mode + generous timeout for full character cards
            ArgumentsTemplate = "-p {0} --print-timeout 3m",
            Aliases = { "agy", "gemini", "gemini cli", "agy (gemini cli)" }
        },
        new LlmProviderInfo
        {
            // Mistral's CLI is `vibe` (Mistral Vibe), not a binary named mistral
            Name = "Mistral Vibe",
            ExecutablePath = "vibe",
            // auto-approve, trust, and disable tools so programmatic roleplay never blocks on trust prompts or tool calls
            ArgumentsTemplate = "-p {0} --trust --disabled-tools \"*\" --auto-approve --output text",
            Aliases = { "vibe", "vibe cli", "mistral", "mistral vibe", "mistral-vibe", "mistral vibe cli" }
        },
        new LlmProviderInfo
        {
            // Grok Build TUI: headless single-turn or it opens an interactive session.
            Name = "Grok CLI",
            ExecutablePath = "grok",
            ArgumentsTemplate =
                "--always-approve --output-format plain --permission-mode bypassPermissions --disable-web-search --no-subagents --no-alt-screen -p {0}",
            Aliases = { "grok", "grok cli", "xai", "grok build", "grok tui" }
        },
        new LlmProviderInfo
        {
            Name = "Ollama CLI",
            ExecutablePath = "ollama",
            ArgumentsTemplate = "run llama3 {0}",
            Aliases = { "ollama", "ollama cli", "llama", "llama3" }
        },
        new LlmProviderInfo
        {
            Name = "Claude CLI",
            ExecutablePath = "claude",
            ArgumentsTemplate = "-p {0}",
            Aliases = { "claude", "claude cli", "anthropic" }
        },
        new LlmProviderInfo
        {
            Name = "SGPT CLI",
            ExecutablePath = "sgpt",
            ArgumentsTemplate = "{0}",
            Aliases = { "sgpt", "shell-gpt" }
        }
    };

    public static List<LlmProviderInfo> DiscoverInstalledProviders()
    {
        var installed = new List<LlmProviderInfo>();

        foreach (var provider in KnownProviders)
        {
            string? fullPath = FindExecutableInPath(provider.ExecutablePath);
            if (!string.IsNullOrEmpty(fullPath))
            {
                installed.Add(new LlmProviderInfo
                {
                    Name = provider.Name,
                    ExecutablePath = fullPath,
                    ArgumentsTemplate = provider.ArgumentsTemplate,
                    IsAvailable = true,
                    Aliases = new List<string>(provider.Aliases)
                });
            }
        }

        return installed;
    }

    public static List<string> GetAvailableProviderNames()
    {
        var names = new List<string> { "Embedded C# SLM (LLamaSharp)", "Mock / Simulation" };
        foreach (var p in DiscoverInstalledProviders())
            names.Add(p.Name);
        return names;
    }

    public static ILLMClient CreateClient(string providerName) => CreateClient(providerName, null);

    public static ILLMClient CreateClient(string providerName, string? modelIdentifier)
    {
        if (string.IsNullOrWhiteSpace(providerName) ||
            providerName.Contains("Mock", StringComparison.OrdinalIgnoreCase))
        {
            return new MockLLMClient();
        }

        if (providerName.Contains("LLamaSharp", StringComparison.OrdinalIgnoreCase) ||
            providerName.Contains("Embedded C# SLM", StringComparison.OrdinalIgnoreCase) ||
            providerName.Contains("C# SLM", StringComparison.OrdinalIgnoreCase) ||
            providerName.Equals("LlamaSharp", StringComparison.OrdinalIgnoreCase))
        {
            return new LlamaSharpLlmClient("Embedded C# SLM (LLamaSharp)", modelIdentifier);
        }

        if (providerName.Contains("Ollama", StringComparison.OrdinalIgnoreCase))
        {
            return new OllamaLlmClient(modelIdentifier ?? "llama3");
        }

        // 1) Prefer currently-discoverable install with correct template
        var discovered = DiscoverInstalledProviders();
        var found = MatchProvider(discovered, providerName);
        if (found != null)
            return new CliLlmClient(found.Name, found.ExecutablePath, found.ArgumentsTemplate);

        // 2) Known provider by name/alias even if PATH was incomplete at first glance
        var known = MatchProvider(KnownProviders, providerName);
        if (known != null)
        {
            string? path = FindExecutableInPath(known.ExecutablePath);
            if (!string.IsNullOrEmpty(path))
                return new CliLlmClient(known.Name, path, known.ArgumentsTemplate);

            return new CliLlmClient(
                known.Name,
                known.ExecutablePath,
                known.ArgumentsTemplate); // will surface clear "not found" from CliLlmClient
        }

        // 3) Legacy display names from older configs
        if (providerName.Contains("Vibe", StringComparison.OrdinalIgnoreCase) ||
            providerName.Contains("Mistral", StringComparison.OrdinalIgnoreCase))
        {
            string? vibePath = FindExecutableInPath("vibe");
            return new CliLlmClient(
                "Mistral Vibe",
                vibePath ?? "vibe",
                "-p {0} --trust --disabled-tools \"*\" --auto-approve --output text");
        }

        if (providerName.Contains("Agy", StringComparison.OrdinalIgnoreCase) ||
            providerName.Contains("Gemini", StringComparison.OrdinalIgnoreCase))
        {
            string? agyPath = FindExecutableInPath("agy");
            return new CliLlmClient(
                "Agy (Gemini CLI)",
                agyPath ?? "agy",
                "-p {0} --print-timeout 3m");
        }

        // 4) Last resort: treat the string as an executable name
        string? fallbackPath = FindExecutableInPath(providerName);
        return new CliLlmClient(providerName, fallbackPath ?? providerName, "-p {0}");
    }

    private static LlmProviderInfo? MatchProvider(IEnumerable<LlmProviderInfo> providers, string providerName)
    {
        string key = providerName.Trim();

        // Exact display name
        var exact = providers.FirstOrDefault(p => p.Name.Equals(key, StringComparison.OrdinalIgnoreCase));
        if (exact != null) return exact;

        // Alias exact
        var alias = providers.FirstOrDefault(p =>
            p.Aliases.Any(a => a.Equals(key, StringComparison.OrdinalIgnoreCase)));
        if (alias != null) return alias;

        // Fuzzy contains (e.g. saved "Vibe CLI" vs new "Mistral Vibe")
        var fuzzy = providers.FirstOrDefault(p =>
            p.Name.Contains(key, StringComparison.OrdinalIgnoreCase) ||
            key.Contains(p.Name, StringComparison.OrdinalIgnoreCase) ||
            p.Aliases.Any(a =>
                key.Contains(a, StringComparison.OrdinalIgnoreCase) ||
                a.Contains(key, StringComparison.OrdinalIgnoreCase)));

        return fuzzy;
    }

    public static string? FindExecutableInPath(string executableName)
    {
        if (string.IsNullOrWhiteSpace(executableName))
            return null;

        // Absolute / relative path already given
        if (executableName.Contains(Path.DirectorySeparatorChar) ||
            executableName.Contains(Path.AltDirectorySeparatorChar))
        {
            if (File.Exists(executableName))
                return Path.GetFullPath(executableName);
        }
        else if (File.Exists(executableName))
        {
            return Path.GetFullPath(executableName);
        }

        var searchDirs = new List<string>();

        string? pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (!string.IsNullOrEmpty(pathEnv))
            searchDirs.AddRange(pathEnv.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries));

        // GUI apps often miss user-local bins
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (!string.IsNullOrEmpty(home))
            searchDirs.Insert(0, Path.Combine(home, ".local", "bin"));

        searchDirs.Add("/usr/local/bin");
        searchDirs.Add("/usr/bin");
        searchDirs.Add("/bin");

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var dir in searchDirs)
        {
            if (string.IsNullOrWhiteSpace(dir) || !seen.Add(dir))
                continue;

            string fullPath = Path.Combine(dir, executableName);
            if (File.Exists(fullPath))
                return fullPath;

            // Windows-style fallback when running under wine/etc.
            string exePath = fullPath + ".exe";
            if (File.Exists(exePath))
                return exePath;
        }

        return null;
    }
}
