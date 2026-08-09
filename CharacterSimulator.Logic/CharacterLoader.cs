using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security;
using System.Text;
using System.Text.Json;
using YamlDotNet.Serialization;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic;

public static class CharacterLoader
{
    private const long MaxCharacterFileSize = 10 * 1024 * 1024; // 10MB
    private static readonly HashSet<string> AllowedExtensions = new HashSet<string> { ".json", ".md", ".yaml", ".yml" };

    public static Character Load(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
            throw new ArgumentException("Character file path cannot be null or empty", nameof(path));

        if (!File.Exists(path))
            throw new FileNotFoundException($"Character file not found: {path}");

        var fileInfo = new FileInfo(path);
        
        // Validate it's a file, not a directory
        if ((fileInfo.Attributes & FileAttributes.Directory) != 0)
            throw new ArgumentException($"Path is a directory, not a file: {path}", nameof(path));

        // Validate file size
        if (fileInfo.Length > MaxCharacterFileSize)
            throw new ArgumentException($"Character file is too large (>{MaxCharacterFileSize / (1024*1024)}MB): {path}", nameof(path));

        // Validate file extension
        string ext = Path.GetExtension(path).ToLowerInvariant();
        if (!AllowedExtensions.Contains(ext))
            throw new ArgumentException($"Unsupported character file extension '{ext}'. Allowed: {string.Join(", ", AllowedExtensions)}", nameof(path));

        // Validate path is within allowed directories
        ValidateCharacterPath(path);

        var character = ext == ".json" ? LoadFromJson(path) : LoadFromYamlMarkdown(path);
        TryLoadDurableLog(character, path);
        return character;
    }

    /// <summary>
    /// Creates a new Character with common initialization (name, display name, path)
    /// </summary>
    private static Character CreateCharacter(string path, string legalName, string? callName)
    {
        string displayName = !string.IsNullOrWhiteSpace(callName) ? callName! : legalName;
        
        var character = new Character
        {
            Name = displayName,
            CardPath = path,
            Inventory = new List<string>(),
            SomaticZones = new List<string>()
        };
        
        if (!string.Equals(legalName, displayName, StringComparison.Ordinal))
            character.Attributes["legal_name"] = legalName;
        if (!string.IsNullOrWhiteSpace(callName))
            character.Attributes["call_name"] = callName!;
        
        return character;
    }

    private static Character LoadFromJson(string path)
    {
        string jsonText = File.ReadAllText(path);
        using var doc = JsonDocument.Parse(jsonText);
        var root = doc.RootElement;

        string legalName = GetString(root, "name") ?? Path.GetFileNameWithoutExtension(path);
        string? callName = GetString(root, "call_name");
        
        var character = CreateCharacter(path, legalName, callName);
        
        // Set state and bias fields
        character.CurrentState = GetString(root, "active_focus")
            ?? GetString(root, "current_state")
            ?? "ACTIVE";
        character.ActiveFocus = character.CurrentState;
        character.CognitiveBias = GetString(root, "cognitive_bias") ?? "";
        character.CognitiveGift = GetString(root, "cognitive_gift") ?? "";
        character.CulturalBias = GetString(root, "cultural_bias") ?? "";
        character.Bond = root.TryGetProperty("bond", out var bondProp) && bondProp.TryGetInt32(out var bondVal) ? bondVal : 0;
        character.CanonAdult = !root.TryGetProperty("canon_adult", out var caProp) || caProp.ValueKind != JsonValueKind.False;
        character.Age = root.TryGetProperty("age", out var ageProp) && ageProp.TryGetInt32(out var ageVal) ? ageVal : 25;

        if (root.TryGetProperty("physical", out var physicalProp))
        {
            if (physicalProp.ValueKind == JsonValueKind.String)
                character.Attributes["physical"] = physicalProp.GetString() ?? "";
            else if (physicalProp.ValueKind == JsonValueKind.Object)
            {
                foreach (var prop in physicalProp.EnumerateObject())
                    character.Attributes[prop.Name] = JsonValueToString(prop.Value);
            }
        }

        character.PhysicalDescription = CardFieldFormatter.FlattenPhysical(root);
        if (string.IsNullOrWhiteSpace(character.PhysicalDescription) &&
            character.Attributes.TryGetValue("physical", out var physAttr))
            character.PhysicalDescription = physAttr;
        if (!string.IsNullOrWhiteSpace(character.PhysicalDescription))
            character.Attributes["physical"] = character.PhysicalDescription;

        character.CharacterStyle = CardFieldFormatter.FlattenCharacterStyle(root);
        if (!string.IsNullOrWhiteSpace(character.CharacterStyle))
            character.Attributes["character_style"] = character.CharacterStyle;

        character.Personality = CardFieldFormatter.ReadPersonality(root);
        character.Behavior = CardFieldFormatter.ReadBehavior(root);
        if (!string.IsNullOrWhiteSpace(character.Personality))
            character.Attributes["personality"] = character.Personality;
        if (!string.IsNullOrWhiteSpace(character.Behavior))
            character.Attributes["behavior"] = character.Behavior;

        ApplyJsonVoice(root, character);

        if (root.TryGetProperty("somatic_zones", out var zonesProp) && zonesProp.ValueKind == JsonValueKind.Array)
        {
            foreach (var elem in zonesProp.EnumerateArray())
            {
                string? z = elem.GetString();
                if (!string.IsNullOrEmpty(z)) character.SomaticZones.Add(z);
            }
        }

        if (root.TryGetProperty("default_somatic_alignment", out var somaAlign))
        {
            string? align = somaAlign.GetString();
            if (!string.IsNullOrEmpty(align) && character.SomaticZones.Count == 0)
                character.SomaticZones.Add(align);
        }

        if (root.TryGetProperty("goals", out var goalsProp) && goalsProp.ValueKind == JsonValueKind.Array)
        {
            foreach (var goalElem in goalsProp.EnumerateArray())
            {
                if (goalElem.ValueKind == JsonValueKind.Object)
                    character.Goals.Add(ParseJsonGoal(goalElem));
            }
        }

        character.Bio = BuildJsonBio(root, character.Name);
        ResolvePortrait(character, path, callName, legalName);
        return character;
    }

    private static void ApplyJsonVoice(JsonElement root, Character character)
    {
        if (!root.TryGetProperty("voice", out var voiceProp) || voiceProp.ValueKind != JsonValueKind.Object)
            return;

        if (voiceProp.TryGetProperty("baseline", out var baseProp))
            character.Attributes["voice"] = baseProp.GetString() ?? "";

        var voiceBits = new List<string>();
        if (voiceProp.TryGetProperty("syntactical_engine", out var syn))
        {
            string? sVal = syn.GetString();
            if (!string.IsNullOrEmpty(sVal))
            {
                voiceBits.Add(sVal);
                character.VoiceSyntacticalEngine = sVal;
            }
        }
        if (voiceProp.TryGetProperty("conversational_stance", out var stance))
        {
            string? stVal = stance.GetString();
            if (!string.IsNullOrEmpty(stVal))
            {
                voiceBits.Add($"stance: {stVal}");
                character.ConversationalStance = stVal;
            }
        }
        if (voiceBits.Count > 0)
            character.Attributes["voice_detail"] = string.Join("; ", voiceBits.Where(s => !string.IsNullOrWhiteSpace(s)));

        if (voiceProp.TryGetProperty("hard_bans", out var bans) && bans.ValueKind == JsonValueKind.Array)
            character.Attributes["hard_bans"] = string.Join("; ", bans.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrEmpty(s)));

        var tics = new List<string>();
        if (voiceProp.TryGetProperty("signature_tics", out var sig) && sig.ValueKind == JsonValueKind.Array)
            tics.AddRange(sig.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrEmpty(s))!);
        if (voiceProp.TryGetProperty("verbal_mannerisms", out var manners) && manners.ValueKind == JsonValueKind.Array)
            tics.AddRange(manners.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrEmpty(s))!);
        if (tics.Count > 0)
            character.Attributes["signature_tics"] = string.Join("; ", tics);
    }

    private static string BuildJsonBio(JsonElement root, string charName)
    {
        // Bio is background/knowledge only — personality, behavior, and physical stay separate fields.
        var sb = new StringBuilder();

        if (root.TryGetProperty("depth_of_knowledge", out var dok) && dok.ValueKind == JsonValueKind.Object)
        {
            if (dok.TryGetProperty("personal", out var personal))
                AppendLineIf(sb, personal.GetString());
            if (dok.TryGetProperty("general", out var general))
            {
                string? g = general.GetString();
                if (!string.IsNullOrEmpty(g)) sb.AppendLine($"Knowledge: {g}");
            }
        }

        if (root.TryGetProperty("history_anchors", out var history) && history.ValueKind == JsonValueKind.Array)
        {
            var anchors = history.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrEmpty(s)).ToList();
            if (anchors.Count > 0)
                sb.AppendLine("History: " + string.Join(" | ", anchors));
        }

        if (root.TryGetProperty("hobbies", out var hobbies) && hobbies.ValueKind == JsonValueKind.Array)
        {
            var list = hobbies.EnumerateArray().Select(e => e.GetString()).Where(s => !string.IsNullOrEmpty(s)).ToList();
            if (list.Count > 0)
                sb.AppendLine("Hobbies: " + string.Join("; ", list));
        }

        string? faction = GetString(root, "faction");
        string? shipClass = GetString(root, "ship_class");
        if (!string.IsNullOrEmpty(faction) || !string.IsNullOrEmpty(shipClass))
            sb.AppendLine(string.Join(" — ", new[] { faction, shipClass }.Where(s => !string.IsNullOrEmpty(s))));

        string bio = sb.ToString().Trim();
        return string.IsNullOrEmpty(bio) ? charName : bio;
    }

    private static Goal ParseJsonGoal(JsonElement goalElem)
    {
        var goal = new Goal
        {
            Type = GetString(goalElem, "type") ?? "",
            Target = GetString(goalElem, "target") ?? "",
            Intensity = goalElem.TryGetProperty("intensity", out var i) && i.TryGetInt32(out var iv) ? iv : 5,
            SuccessCondition = GetString(goalElem, "success_condition") ?? "",
            FailureCondition = GetString(goalElem, "failure_condition") ?? "",
            Cooldown = goalElem.TryGetProperty("cooldown", out var c) && c.TryGetInt32(out var cv) ? cv : 3,
            Priority = goalElem.TryGetProperty("priority", out var p) && p.TryGetInt32(out var pv) ? pv : 3
        };

        if (goalElem.TryGetProperty("strategy", out var strat) && strat.ValueKind == JsonValueKind.Array)
        {
            foreach (var s in strat.EnumerateArray())
            {
                string? text = s.GetString();
                if (!string.IsNullOrEmpty(text)) goal.Strategies.Add(text);
            }
        }

        return goal;
    }

    private static Character LoadFromYamlMarkdown(string path)
    {
        var fileContent = File.ReadAllText(path);
        var yamlStart = fileContent.IndexOf("---", StringComparison.Ordinal);
        var yamlEnd = fileContent.IndexOf("---", yamlStart + 3, StringComparison.Ordinal);

        if (yamlStart == -1 || yamlEnd == -1)
            throw new FormatException("Character file must have YAML frontmatter.");

        var yamlContent = fileContent.Substring(yamlStart + 3, yamlEnd - yamlStart - 3);
        // No naming convention — CharacterSimulator cards use snake_case keys as written.
        var deserializer = new DeserializerBuilder().Build();
        var raw = deserializer.Deserialize<object>(yamlContent);
        var root = AsStringKeyMap(raw) ?? new Dictionary<string, object?>();

        string legalName = GetMapString(root, "name") ?? Path.GetFileNameWithoutExtension(path);
        string? callName = GetMapString(root, "call_name");
        
        string markdownBody = yamlEnd + 3 < fileContent.Length
            ? fileContent.Substring(yamlEnd + 3).Trim()
            : "";

        var character = CreateCharacter(path, legalName, callName);
        
        // Set state and bias fields
        character.CurrentState = GetMapString(root, "active_focus")
            ?? GetMapString(root, "current_state")
            ?? "ACTIVE";
        character.ActiveFocus = character.CurrentState;
        character.CognitiveBias = GetMapString(root, "cognitive_bias") ?? "";
        character.CognitiveGift = GetMapString(root, "cognitive_gift") ?? "";
        character.CulturalBias = GetMapString(root, "cultural_bias") ?? "";
        character.Bond = GetMapInt(root, "bond") ?? 0;
        character.CanonAdult = !(root.TryGetValue("canon_adult", out var caVal) && caVal is bool caBool && !caBool);
        character.Age = GetMapInt(root, "age") ?? 25;

        // Physical: long string (CS cards) or nested map (Shinano / legacy)
        if (root.TryGetValue("physical", out var physicalVal) && physicalVal != null)
        {
            var physMap = AsStringKeyMap(physicalVal);
            if (physMap != null)
            {
                foreach (var kvp in physMap)
                    character.Attributes[kvp.Key] = YamlValueToString(kvp.Value);

                // Body-only display (exclude clothing/scent from identity string)
                var bodyParts = new List<string>();
                foreach (var key in new[] { "summary", "height", "build", "body_details", "hair", "eyes", "skin", "face", "distinguishing_features", "defining_features", "posture_movement" })
                {
                    if (physMap.TryGetValue(key, out var v))
                    {
                        string t = YamlValueToString(v);
                        if (!string.IsNullOrWhiteSpace(t)) bodyParts.Add(t);
                    }
                }
                character.PhysicalDescription = bodyParts.Count > 0
                    ? string.Join("; ", bodyParts)
                    : string.Join("; ", physMap
                        .Where(kv => !kv.Key.Equals("clothing", StringComparison.OrdinalIgnoreCase)
                                     && !kv.Key.Equals("scent", StringComparison.OrdinalIgnoreCase))
                        .Select(kv => YamlValueToString(kv.Value))
                        .Where(s => !string.IsNullOrWhiteSpace(s)));

                if (physMap.TryGetValue("clothing", out var clothingVal))
                    character.CharacterStyle = YamlValueToString(clothingVal);
            }
            else
            {
                character.PhysicalDescription = YamlValueToString(physicalVal);
                character.Attributes["physical"] = character.PhysicalDescription;
            }
        }

        string? personality = GetMapString(root, "personality") ?? GetMapString(root, "vibe");
        if (!string.IsNullOrWhiteSpace(personality))
            character.Personality = personality;
        else
        {
            var pParts = new List<string>();
            AppendLineIfList(pParts, GetMapString(root, "cultural_bias"));
            AppendLineIfList(pParts, GetMapString(root, "cognitive_bias"));
            AppendLineIfList(pParts, GetMapString(root, "cognitive_gift"));
            character.Personality = string.Join("\n", pParts);
        }

        string? behavior = GetMapString(root, "behavior");
        if (!string.IsNullOrWhiteSpace(behavior))
            character.Behavior = behavior;

        var styleMap = AsStringKeyMap(root.GetValueOrDefault("character_style"));
        if (styleMap != null)
        {
            character.CharacterStyle = string.Join("; ",
                styleMap.Select(kv => YamlValueToString(kv.Value)).Where(s => !string.IsNullOrWhiteSpace(s)));
        }
        else
        {
            string? styleStr = GetMapString(root, "character_style");
            if (!string.IsNullOrWhiteSpace(styleStr))
                character.CharacterStyle = styleStr;
        }

        if (!string.IsNullOrWhiteSpace(character.PhysicalDescription))
            character.Attributes["physical"] = character.PhysicalDescription;
        if (!string.IsNullOrWhiteSpace(character.CharacterStyle))
            character.Attributes["character_style"] = character.CharacterStyle;
        if (!string.IsNullOrWhiteSpace(character.Personality))
            character.Attributes["personality"] = character.Personality;

        ApplyYamlVoice(root, character);
        ApplyYamlSomatic(root, character);
        ApplyYamlGoals(root, character);
        ApplyYamlSessionVariants(root, character);

        // Behavior fallback from voice/somatics after voice is applied
        if (string.IsNullOrWhiteSpace(character.Behavior))
        {
            var bParts = new List<string>();
            AppendLineIfList(bParts, GetMapString(root, "default_somatic_alignment"));
            if (!string.IsNullOrWhiteSpace(character.VerbalDefense))
                bParts.Add("Under pressure: " + character.VerbalDefense);
            if (!string.IsNullOrWhiteSpace(character.GenerativeStance))
                bParts.Add("Under trust: " + character.GenerativeStance);
            if (character.Attributes.TryGetValue("signature_tics", out var tics) && !string.IsNullOrWhiteSpace(tics))
                bParts.Add("Mannerisms: " + tics);
            character.Behavior = string.Join("\n", bParts);
        }
        if (!string.IsNullOrWhiteSpace(character.Behavior))
            character.Attributes["behavior"] = character.Behavior;

        character.Bio = BuildYamlBio(root, character.Name, markdownBody);
        ResolvePortrait(character, path, callName, legalName);
        return character;
    }

    private static void AppendLineIfList(List<string> parts, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
            parts.Add(value.Trim());
    }

    private static void ApplyYamlSessionVariants(Dictionary<string, object?> root, Character character)
    {
        var svMap = AsStringKeyMap(root.GetValueOrDefault("session_variants"));
        if (svMap == null || !svMap.TryGetValue("variants", out var varObj) || varObj is not IEnumerable<object> varList)
            return;

        foreach (var item in varList)
        {
            var vDict = AsStringKeyMap(item);
            if (vDict == null) continue;

            string id = GetMapString(vDict, "id") ?? "";
            string label = GetMapString(vDict, "label") ?? id;
            string opening = GetMapString(vDict, "opening_beat") ?? "";

            string location = "";
            var sceneDict = AsStringKeyMap(vDict.GetValueOrDefault("scene"));
            if (sceneDict != null)
                location = GetMapString(sceneDict, "location") ?? "";

            character.SessionVariants.Add(new SessionVariant
            {
                Id = id,
                Label = label,
                Location = location,
                OpeningBeat = opening
            });
        }
    }

    private static void ApplyYamlVoice(Dictionary<string, object?> root, Character character)
    {
        var voice = AsStringKeyMap(root.GetValueOrDefault("voice"));
        if (voice == null) return;

        string? baseline = GetMapString(voice, "baseline");
        if (!string.IsNullOrEmpty(baseline))
            character.Attributes["voice"] = baseline;

        var bits = new List<string>();
        string? syn = GetMapString(voice, "syntactical_engine");
        if (!string.IsNullOrEmpty(syn))
        {
            bits.Add(syn);
            character.VoiceSyntacticalEngine = syn;
        }
        string? stance = GetMapString(voice, "conversational_stance");
        if (!string.IsNullOrEmpty(stance))
        {
            bits.Add($"stance: {stance}");
            character.ConversationalStance = stance;
        }
        if (bits.Count > 0)
            character.Attributes["voice_detail"] = string.Join("; ", bits);

        string? vDef = GetMapString(voice, "verbal_defense");
        if (!string.IsNullOrEmpty(vDef)) character.VerbalDefense = vDef;

        string? genStance = GetMapString(voice, "generative_stance");
        if (!string.IsNullOrEmpty(genStance)) character.GenerativeStance = genStance;

        if (voice.TryGetValue("hard_bans", out var bans))
            character.Attributes["hard_bans"] = YamlValueToString(bans);

        var tics = new List<string>();
        if (voice.TryGetValue("signature_tics", out var sig))
            tics.Add(YamlValueToString(sig));
        if (voice.TryGetValue("verbal_mannerisms", out var manners))
            tics.Add(YamlValueToString(manners));
        var ticText = string.Join("; ", tics.Where(t => !string.IsNullOrWhiteSpace(t)));
        if (!string.IsNullOrWhiteSpace(ticText))
            character.Attributes["signature_tics"] = ticText;

        if (voice.TryGetValue("relational_verbal_shifts", out var shiftsVal))
        {
            var shiftsMap = AsStringKeyMap(shiftsVal);
            if (shiftsMap != null && shiftsMap.Count > 0)
            {
                var shiftStr = string.Join("; ", shiftsMap.Select(kv => $"{kv.Key}: {YamlValueToString(kv.Value)}"));
                character.Attributes["relational_verbal_shifts"] = shiftStr;
            }
        }
    }

    private static void ApplyYamlSomatic(Dictionary<string, object?> root, Character character)
    {
        if (root.TryGetValue("latent_anchors", out var anchorsVal) && anchorsVal is IEnumerable<object> anchors)
        {
            foreach (var anchor in anchors)
            {
                string? a = anchor?.ToString();
                if (!string.IsNullOrEmpty(a)) character.LatentAnchors.Add(a);
            }
        }

        if (root.TryGetValue("somatic_zones", out var zonesVal) && zonesVal is IEnumerable<object> zones)
        {
            foreach (var zone in zones)
            {
                string? z = zone?.ToString();
                if (!string.IsNullOrEmpty(z)) character.SomaticZones.Add(z);
            }
        }

        string? align = GetMapString(root, "default_somatic_alignment");
        if (!string.IsNullOrEmpty(align) && character.SomaticZones.Count == 0)
            character.SomaticZones.Add(align);
    }

    private static void ApplyYamlGoals(Dictionary<string, object?> root, Character character)
    {
        if (!root.TryGetValue("goals", out var goalsVal) || goalsVal is not IEnumerable<object> goalsList)
            return;

        foreach (var goalObj in goalsList)
        {
            var goalDict = AsStringKeyMap(goalObj);
            if (goalDict == null) continue;

            var goal = new Goal
            {
                Type = GetMapString(goalDict, "type") ?? "",
                Target = GetMapString(goalDict, "target") ?? "",
                Intensity = GetMapInt(goalDict, "intensity") ?? 5,
                SuccessCondition = GetMapString(goalDict, "success_condition") ?? "",
                FailureCondition = GetMapString(goalDict, "failure_condition") ?? "",
                Cooldown = GetMapInt(goalDict, "cooldown") ?? 3,
                Priority = GetMapInt(goalDict, "priority") ?? 3
            };

            if (goalDict.TryGetValue("strategy", out var strat) && strat is IEnumerable<object> strategies)
            {
                foreach (var s in strategies)
                    if (s != null) goal.Strategies.Add(s.ToString()!);
            }

            character.Goals.Add(goal);
        }
    }

    private static string BuildYamlBio(Dictionary<string, object?> root, string displayName, string markdownBody)
    {
        // Background/knowledge only — personality, behavior, physical stay on dedicated Character fields.
        var sb = new StringBuilder();

        var dok = AsStringKeyMap(root.GetValueOrDefault("depth_of_knowledge"));
        if (dok != null)
        {
            AppendLineIf(sb, GetMapString(dok, "personal"));
            string? general = GetMapString(dok, "general");
            if (!string.IsNullOrEmpty(general)) sb.AppendLine($"General Knowledge: {general}");
            string? esoteric = GetMapString(dok, "esoteric");
            if (!string.IsNullOrEmpty(esoteric)) sb.AppendLine($"Esoteric Knowledge: {esoteric}");
        }

        if (root.TryGetValue("history_anchors", out var history))
        {
            string anchors = YamlValueToString(history);
            if (!string.IsNullOrWhiteSpace(anchors))
                sb.AppendLine("History: " + anchors.Replace(", ", " | "));
        }

        if (root.TryGetValue("hobbies", out var hobbies))
        {
            string h = YamlValueToString(hobbies);
            if (!string.IsNullOrWhiteSpace(h))
                sb.AppendLine("Hobbies: " + h);
        }

        string? faction = GetMapString(root, "faction");
        string? shipClass = GetMapString(root, "ship_class");
        if (!string.IsNullOrEmpty(faction) || !string.IsNullOrEmpty(shipClass))
            sb.AppendLine(string.Join(" — ", new[] { faction, shipClass }.Where(s => !string.IsNullOrEmpty(s))));

        string structured = sb.ToString().Trim();
        if (!string.IsNullOrWhiteSpace(structured))
            return structured;

        if (!string.IsNullOrWhiteSpace(markdownBody))
            return TruncateMarkdownBio(markdownBody);

        return displayName;
    }

    private static string TruncateMarkdownBio(string markdownBody)
    {
        // Prefer first substantial paragraph; avoid dumping entire load protocol
        var lines = markdownBody.Split('\n')
            .Select(l => l.Trim())
            .Where(l => l.Length > 0 && !l.StartsWith('#') && !l.StartsWith('-') && !l.StartsWith('1') && !l.StartsWith('2'))
            .Take(3)
            .ToList();
        if (lines.Count == 0)
        {
            string first = markdownBody.Trim();
            return first.Length > 400 ? first.Substring(0, 397) + "…" : first;
        }
        string joined = string.Join(" ", lines);
        return joined.Length > 500 ? joined.Substring(0, 497) + "…" : joined;
    }

    private static void ResolvePortrait(Character character, string cardPath, string? callName, string legalName)
    {
        if (string.Equals(character.AvatarPath, "none", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(character.AvatarPath, "false", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(character.AvatarPath, "off", StringComparison.OrdinalIgnoreCase))
        {
            character.AvatarPath = null;
            return;
        }

        if (!string.IsNullOrEmpty(character.AvatarPath) && File.Exists(character.AvatarPath))
            return;

        string baseDir = Directory.GetCurrentDirectory();
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string cardDir = Path.GetDirectoryName(cardPath) ?? baseDir;
        string stem = Path.GetFileNameWithoutExtension(cardPath);

        var nameCandidates = new[]
            {
                stem,
                callName,
                legalName,
                character.Name
            }
            .Where(s => !string.IsNullOrWhiteSpace(s))
            .Select(s => s!.ToLowerInvariant())
            .Distinct();

        foreach (var nameLower in nameCandidates)
        {
            string[] candidates =
            {
                Path.Combine(cardDir, $"{nameLower}.jpg"),
                Path.Combine(cardDir, $"{nameLower}.png"),
                Path.Combine(cardDir, $"{nameLower}.webp"),
                Path.Combine(appDir, "Assets", "Portraits", $"{nameLower}.jpg"),
                Path.Combine(appDir, "Assets", "Portraits", $"{nameLower}.png"),
                Path.Combine(baseDir, "CharacterSimulator.GUI", "Assets", "Portraits", $"{nameLower}.jpg"),
                Path.Combine(baseDir, "CharacterSimulator.GUI", "Assets", "Portraits", $"{nameLower}.png"),
                Path.Combine(baseDir, "Assets", "Portraits", $"{nameLower}.jpg"),
                Path.Combine(baseDir, "Assets", "Portraits", $"{nameLower}.png"),
            };

            foreach (var p in candidates)
            {
                if (File.Exists(p))
                {
                    character.AvatarPath = p;
                    return;
                }
            }
        }

        character.AvatarPath = null;
    }

    private static Dictionary<string, object?>? AsStringKeyMap(object? value)
    {
        if (value == null) return null;

        if (value is Dictionary<string, object?> already)
            return already;

        if (value is Dictionary<string, object> strDict)
            return strDict.ToDictionary(k => k.Key, v => (object?)v.Value);

        if (value is Dictionary<object, object> objDict)
        {
            var map = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
            foreach (var kvp in objDict)
            {
                string key = kvp.Key?.ToString() ?? "";
                if (key.Length > 0) map[key] = kvp.Value;
            }
            return map;
        }

        // YamlDotNet sometimes yields Dictionary<object, object?> variants via IDictionary
        if (value is System.Collections.IDictionary idict)
        {
            var map = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
            foreach (System.Collections.DictionaryEntry entry in idict)
            {
                string key = entry.Key?.ToString() ?? "";
                if (key.Length > 0) map[key] = entry.Value;
            }
            return map.Count > 0 ? map : null;
        }

        return null;
    }

    private static string? GetMapString(Dictionary<string, object?> map, string key)
    {
        if (!map.TryGetValue(key, out var val) || val == null) return null;
        string s = YamlValueToString(val);
        return string.IsNullOrWhiteSpace(s) ? null : s;
    }

    private static int? GetMapInt(Dictionary<string, object?> map, string key)
    {
        if (!map.TryGetValue(key, out var val) || val == null) return null;
        try { return Convert.ToInt32(val); }
        catch { return null; }
    }

    private static void AppendLineIf(StringBuilder sb, string? line)
    {
        if (!string.IsNullOrWhiteSpace(line)) sb.AppendLine(line);
    }

    private static string? GetString(JsonElement root, string property)
    {
        if (!root.TryGetProperty(property, out var prop)) return null;
        return prop.ValueKind == JsonValueKind.String ? prop.GetString() : prop.ToString();
    }

    private static string JsonValueToString(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? "",
        JsonValueKind.Array => string.Join(", ", value.EnumerateArray().Select(e => e.GetString() ?? e.ToString())),
        JsonValueKind.Number => value.ToString(),
        JsonValueKind.True => "true",
        JsonValueKind.False => "false",
        _ => value.ToString()
    };

    private static string YamlValueToString(object? value)
    {
        if (value == null) return "";
        if (value is string s) return s;
        if (value is System.Collections.IEnumerable enumerable && value is not string)
        {
            var parts = new List<string>();
            foreach (var item in enumerable)
            {
                if (item == null) continue;
                var nested = AsStringKeyMap(item);
                if (nested != null)
                    parts.Add(string.Join(", ", nested.Select(kv => $"{kv.Key}: {YamlValueToString(kv.Value)}")));
                else
                    parts.Add(item.ToString() ?? "");
            }
            return string.Join("; ", parts.Where(p => p.Length > 0));
        }
        return value.ToString() ?? "";
    }

    private static void ValidateCharacterPath(string path)
    {
        // Get the canonical full path
        string fullPath = Path.GetFullPath(path);
        
        // Get the Characters directory
        string charactersDir = CharacterCatalog.ResolveCharactersDirectory();
        string charactersFullPath = Path.GetFullPath(charactersDir);
        
        // Ensure the path is within the Characters directory or a subdirectory
        if (!fullPath.StartsWith(charactersFullPath, StringComparison.OrdinalIgnoreCase) &&
            !fullPath.StartsWith(Path.Combine(charactersFullPath, ".."), StringComparison.OrdinalIgnoreCase))
        {
            throw new SecurityException($"Character file path must be within the Characters directory: {path}");
        }
    }

    private static void TryLoadDurableLog(Character character, string cardPath)
    {
        string dir = Path.GetDirectoryName(cardPath) ?? "";
        string stem = Path.GetFileNameWithoutExtension(cardPath);

        string logPath = Path.Combine(dir, $"{stem}_log.yaml");
        if (!File.Exists(logPath))
        {
            logPath = Path.Combine(dir, $"{stem.ToLowerInvariant()}_log.yaml");
        }
        if (!File.Exists(logPath)) return;

        try
        {
            character.LogPath = logPath;
            var log = Logs.DurableLogStore.LoadLog(logPath);
            Logs.DurableLogStore.ApplyOverlay(character, log);
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[CharacterLoader] Error loading durable log {logPath}: {ex.Message}");
        }
    }
}
