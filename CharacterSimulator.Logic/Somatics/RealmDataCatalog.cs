using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic.Somatics;

public class VocalBehavior
{
    public string micro { get; set; } = string.Empty;
    public string moderate { get; set; } = string.Empty;
    public string macro { get; set; } = string.Empty;
    public string release { get; set; } = string.Empty;
}

public class RealmData
{
    public string key { get; set; } = string.Empty;
    public string name { get; set; } = string.Empty;
    public string zone { get; set; } = string.Empty;
    public List<string> micro { get; set; } = new();
    public List<string> moderate { get; set; } = new();
    public List<string> macro { get; set; } = new();
    public List<string> release { get; set; } = new();
    public VocalBehavior vocal_behavior { get; set; } = new();
}

public class RealmYamlRoot
{
    public Dictionary<string, RealmData> realms { get; set; } = new(StringComparer.OrdinalIgnoreCase);
}

public static class RealmDataCatalog
{
    private static readonly Dictionary<string, RealmData> Realms = new(StringComparer.OrdinalIgnoreCase);
    private static bool _loaded = false;
    private static readonly object SyncLock = new();

    public static void Initialize(string? customFilePath = null)
    {
        lock (SyncLock)
        {
            if (_loaded && customFilePath == null) return;

            var candidates = new List<string>();
            if (!string.IsNullOrWhiteSpace(customFilePath))
                candidates.Add(customFilePath);
            
            // Prefer output directory where files are copied by build
            candidates.Add(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "realm_data.yaml"));
            
            // Fallback: relative paths from current directory
            candidates.Add(Path.Combine(Directory.GetCurrentDirectory(), "Data", "realm_data.yaml"));
            candidates.Add(Path.Combine(Directory.GetCurrentDirectory(), "CharacterSimulator.Logic", "Data", "realm_data.yaml"));
            
            // Relative to solution root
            candidates.Add(Path.Combine(Directory.GetCurrentDirectory(), "..", "CharacterSimulator.Logic", "Data", "realm_data.yaml"));

            string? selectedPath = candidates.FirstOrDefault(p => !string.IsNullOrWhiteSpace(p) && File.Exists(p));

            if (selectedPath != null)
            {
                try
                {
                    string yamlText = File.ReadAllText(selectedPath);
                    var deserializer = new DeserializerBuilder()
                        .WithNamingConvention(UnderscoredNamingConvention.Instance)
                        .IgnoreUnmatchedProperties()
                        .Build();
                    var root = deserializer.Deserialize<RealmYamlRoot>(yamlText);
                    if (root?.realms != null)
                    {
                        Realms.Clear();
                        foreach (var (k, v) in root.realms)
                        {
                            v.key = k;
                            Realms[k] = v;
                            if (!string.IsNullOrWhiteSpace(v.name))
                            {
                                Realms[v.name] = v;
                            }
                        }
                        _loaded = true;
                        AppLogger.Warning($"[RealmDataCatalog] Loaded realm_data.yaml from: {selectedPath}");
                    }
                }
                catch (Exception ex)
                {
                    AppLogger.Warning($"[RealmDataCatalog] Failed loading realm_data.yaml: {ex.Message}");
                }
            }
            else
            {
                AppLogger.Warning($"[RealmDataCatalog] Warning: No realm_data.yaml found in any search path");
            }
        }
    }

    public static RealmData? GetRealm(string realmOrFocusKey)
    {
        Initialize();
        if (string.IsNullOrWhiteSpace(realmOrFocusKey)) return null;

        string key = realmOrFocusKey.Trim();
        if (Realms.TryGetValue(key, out var exact)) return exact;

        // Extract longest matching Roman numeral (e.g., "VIII" before "V" or "I")
        var match = System.Text.RegularExpressions.Regex.Match(key, @"\b(VIII|VII|III|VI|IV|IX|II|V|X|I)\b", 
            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        if (match.Success)
        {
            string matchedNum = match.Value.ToUpperInvariant();
            if (Realms.TryGetValue(matchedNum, out var found)) return found;
        }

        return null;
    }

    public static string BuildPromptSomaticGuidance(string activeFocus)
    {
        var realm = GetRealm(activeFocus);
        if (realm == null) return string.Empty;

        return $"Somatic Alignment ({realm.name} Realm — {realm.zone}): " +
               $"Micro tells: [{string.Join(", ", realm.micro.Take(3))}]. Vocal cadence: {realm.vocal_behavior?.micro ?? ""}";
    }
}
