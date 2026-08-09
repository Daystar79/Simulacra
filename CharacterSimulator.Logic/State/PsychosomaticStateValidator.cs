using System;
using System.Collections.Generic;
using System.Text.Json;

using static CharacterSimulator.Logic.AppLogger;

namespace CharacterSimulator.Logic.State;

public class ValidationResult
{
    public bool IsValid => Errors.Count == 0;
    public List<string> Errors { get; } = new();
}

public static class PsychosomaticStateValidator
{
    public static ValidationResult Validate(PsychosomaticStateSnapshot snapshot)
    {
        var result = new ValidationResult();

        if (string.IsNullOrWhiteSpace(snapshot.CharacterId))
            result.Errors.Add("$: missing or empty required property 'character_id'");

        // Autonomic State
        if (snapshot.AutonomicState == null)
        {
            result.Errors.Add("autonomic_state: expected object");
        }
        else
        {
            CheckScale(snapshot.AutonomicState.Arousal, "autonomic_state.arousal", result.Errors);
            CheckScale(snapshot.AutonomicState.Stress, "autonomic_state.stress", result.Errors);
            CheckScale(snapshot.AutonomicState.Fatigue, "autonomic_state.fatigue", result.Errors);
            CheckScale(snapshot.AutonomicState.Pain, "autonomic_state.pain", result.Errors);

            if (snapshot.AutonomicState.PrimarySomaticZones == null)
            {
                result.Errors.Add("autonomic_state: missing required property 'primary_somatic_zones'");
            }
            else
            {
                foreach (var zone in snapshot.AutonomicState.PrimarySomaticZones)
                {
                    if (!SomaticZoneEnum.AllowedZones.Contains(zone))
                    {
                        result.Errors.Add($"autonomic_state.primary_somatic_zones: invalid zone '{zone}'");
                    }
                }
            }
        }

        // Affective State
        if (snapshot.AffectiveState == null)
        {
            result.Errors.Add("affective_state: expected object");
        }
        else
        {
            CheckScale(snapshot.AffectiveState.EmotionalIntensity, "affective_state.emotional_intensity", result.Errors);
        }

        // Subconscious Bias
        if (snapshot.SubconsciousBias == null)
        {
            result.Errors.Add("subconscious_bias: expected object");
        }
        else
        {
            if (!BiasStateEnum.AllowedStates.Contains(snapshot.SubconsciousBias.BiasState))
            {
                result.Errors.Add($"subconscious_bias.bias_state: invalid value '{snapshot.SubconsciousBias.BiasState}'");
            }
        }

        // Relational Vectors
        if (snapshot.RelationalVectors == null)
        {
            result.Errors.Add("relational_vectors: expected object");
        }
        else
        {
            foreach (var (target, vec) in snapshot.RelationalVectors)
            {
                if (vec == null)
                {
                    result.Errors.Add($"relational_vectors.{target}: expected object");
                    continue;
                }
                CheckScale(vec.EmotionalSafety, $"relational_vectors.{target}.emotional_safety", result.Errors);
                CheckScale(vec.AttractionPhysical, $"relational_vectors.{target}.attraction_physical", result.Errors);
                CheckScale(vec.AttractionEmotional, $"relational_vectors.{target}.attraction_emotional", result.Errors);
                CheckScale(vec.RespectCompetence, $"relational_vectors.{target}.respect_competence", result.Errors);
                CheckScale(vec.ResentmentFriction, $"relational_vectors.{target}.resentment_friction", result.Errors);

                if (!string.IsNullOrEmpty(vec.StatusDynamic) && !StatusDynamicEnum.AllowedDynamics.Contains(vec.StatusDynamic))
                {
                    result.Errors.Add($"relational_vectors.{target}.status_dynamic: invalid dynamic '{vec.StatusDynamic}'");
                }

                if (vec.PerceivedReciprocity != null)
                {
                    CheckScale(vec.PerceivedReciprocity.PerceivedLiking, $"relational_vectors.{target}.perceived_reciprocity.perceived_liking", result.Errors);
                    CheckScale(vec.PerceivedReciprocity.PerceivedThreat, $"relational_vectors.{target}.perceived_reciprocity.perceived_threat", result.Errors);
                }
            }
        }

        // Priority Arbitration
        if (snapshot.PriorityArbitration == null)
        {
            result.Errors.Add("priority_arbitration: expected object");
        }
        else
        {
            CheckScale(snapshot.PriorityArbitration.SalienceScore, "priority_arbitration.salience_score", result.Errors);
        }

        return result;
    }

    public static ValidationResult ValidateJson(string jsonText, out PsychosomaticStateSnapshot? snapshot)
    {
        snapshot = null;
        try
        {
            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            };
            snapshot = JsonSerializer.Deserialize<PsychosomaticStateSnapshot>(jsonText, options);
            if (snapshot == null)
            {
                var fail = new ValidationResult();
                fail.Errors.Add("Root element could not be deserialized to PsychosomaticStateSnapshot.");
                return fail;
            }
            return Validate(snapshot);
        }
        catch (Exception ex)
        {
            var fail = new ValidationResult();
            fail.Errors.Add($"JSON Parse error: {ex.Message}");
            return fail;
        }
    }

    public static void ClampInPlace(PsychosomaticStateSnapshot snapshot)
    {
        if (snapshot.AutonomicState != null)
        {
            snapshot.AutonomicState.Arousal = ScaleClamps.Clamp0To100(snapshot.AutonomicState.Arousal);
            snapshot.AutonomicState.Stress = ScaleClamps.Clamp0To100(snapshot.AutonomicState.Stress);
            snapshot.AutonomicState.Fatigue = ScaleClamps.Clamp0To100(snapshot.AutonomicState.Fatigue);
            snapshot.AutonomicState.Pain = ScaleClamps.Clamp0To100(snapshot.AutonomicState.Pain);
        }

        if (snapshot.AffectiveState != null)
        {
            snapshot.AffectiveState.EmotionalIntensity = ScaleClamps.Clamp0To100(snapshot.AffectiveState.EmotionalIntensity);
        }

        if (snapshot.RelationalVectors != null)
        {
            foreach (var vec in snapshot.RelationalVectors.Values)
            {
                if (vec == null) continue;
                vec.EmotionalSafety = ScaleClamps.Clamp0To100(vec.EmotionalSafety);
                vec.AttractionPhysical = ScaleClamps.Clamp0To100(vec.AttractionPhysical);
                vec.AttractionEmotional = ScaleClamps.Clamp0To100(vec.AttractionEmotional);
                vec.RespectCompetence = ScaleClamps.Clamp0To100(vec.RespectCompetence);
                vec.ResentmentFriction = ScaleClamps.Clamp0To100(vec.ResentmentFriction);

                if (vec.PerceivedReciprocity != null)
                {
                    vec.PerceivedReciprocity.PerceivedLiking = ScaleClamps.Clamp0To100(vec.PerceivedReciprocity.PerceivedLiking);
                    vec.PerceivedReciprocity.PerceivedThreat = ScaleClamps.Clamp0To100(vec.PerceivedReciprocity.PerceivedThreat);
                }
            }
        }

        if (snapshot.PriorityArbitration != null)
        {
            snapshot.PriorityArbitration.SalienceScore = ScaleClamps.Clamp0To100(snapshot.PriorityArbitration.SalienceScore);
        }
    }

    /// <summary>
    /// Sanitizes invalid enum values in the snapshot.
    /// Drops invalid somatic zones and forces invalid bias_state to DORMANT.
    /// </summary>
    public static void SanitizeInPlace(PsychosomaticStateSnapshot snapshot)
    {
        // Sanitize somatic zones - remove invalid ones
        if (snapshot.AutonomicState?.PrimarySomaticZones != null)
        {
            snapshot.AutonomicState.PrimarySomaticZones.RemoveAll(z => 
                !SomaticZoneEnum.AllowedZones.Contains(z));
        }

        // Sanitize bias state - force to DORMANT if invalid
        if (snapshot.SubconsciousBias != null && 
            !string.IsNullOrEmpty(snapshot.SubconsciousBias.BiasState) &&
            !BiasStateEnum.AllowedStates.Contains(snapshot.SubconsciousBias.BiasState))
        {
            snapshot.SubconsciousBias.BiasState = BiasStateEnum.Dormant;
        }

        // Sanitize status_dynamic values in relational vectors
        if (snapshot.RelationalVectors != null)
        {
            foreach (var vec in snapshot.RelationalVectors.Values)
            {
                if (vec != null && !string.IsNullOrEmpty(vec.StatusDynamic) &&
                    !StatusDynamicEnum.AllowedDynamics.Contains(vec.StatusDynamic))
                {
                    vec.StatusDynamic = StatusDynamicEnum.Equals;
                }
            }
        }
    }

    /// <summary>
    /// Extracts state JSON from text using balanced-brace parsing.
    /// Supports [State: {...}], <state>...</state>, ```json ... ``` and standalone JSON objects.
    /// </summary>
    public static string? ExtractStateJson(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;

        int stateIdx = text.IndexOf("[State:", StringComparison.OrdinalIgnoreCase);
        if (stateIdx >= 0)
        {
            int braceStart = text.IndexOf('{', stateIdx);
            if (braceStart >= 0)
            {
                string? json = ExtractBalancedBraces(text, braceStart);
                if (json != null) return json;
            }
        }

        var match = System.Text.RegularExpressions.Regex.Match(text, @"\x3cstate\x3e([\s\S]*?)\x3c/state\x3e",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        if (match.Success)
            return match.Groups[1].Value.Trim();

        match = System.Text.RegularExpressions.Regex.Match(text, @"```json\s*([\s\S]*?)```",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        if (match.Success)
            return match.Groups[1].Value.Trim();

        int firstBrace = text.IndexOf('{');
        if (firstBrace >= 0)
        {
            return ExtractBalancedBraces(text, firstBrace);
        }

        return null;
    }

    private static string? ExtractBalancedBraces(string text, int startIndex)
    {
        int depth = 0;
        bool inString = false;
        bool escape = false;

        for (int i = startIndex; i < text.Length; i++)
        {
            char c = text[i];
            if (escape) { escape = false; continue; }
            if (c == '\\' && inString) { escape = true; continue; }
            if (c == '"') { inString = !inString; continue; }

            if (!inString)
            {
                if (c == '{') depth++;
                else if (c == '}')
                {
                    depth--;
                    if (depth == 0) return text.Substring(startIndex, i - startIndex + 1);
                }
            }
        }
        return null;
    }

    /// <summary>
    /// Validates, clamps, sanitizes, re-validates, and applies a live snapshot to a runtime Character object.
    /// Returns true if applied safely, false otherwise.
    /// Never trusts unclamped free-form numbers or invalid enum values.
    /// </summary>
    public static bool ApplyToCharacter(PsychosomaticStateSnapshot snapshot, Character character)
    {
        if (snapshot == null || character == null)
            return false;

        if (string.IsNullOrWhiteSpace(snapshot.CharacterId) && !string.IsNullOrWhiteSpace(character.Name))
        {
            snapshot.CharacterId = character.Name;
        }

        // Step 1: Clamp numeric values
        ClampInPlace(snapshot);

        // Step 2: Sanitize invalid enum values
        SanitizeInPlace(snapshot);

        // Step 3: Re-validate after clamping and sanitizing
        var validationResult = Validate(snapshot);
        if (!validationResult.IsValid)
        {
            AppLogger.Warning($"[PsychosomaticStateValidator] Validation failed after sanitize: " + 
                string.Join("; ", validationResult.Errors));
            return false;
        }

        // Step 4: Apply only if valid
        try
        {
            character.Stress = snapshot.AutonomicState.Stress;
            character.Arousal = snapshot.AutonomicState.Arousal;
            character.Fatigue = snapshot.AutonomicState.Fatigue;
            character.Pain = snapshot.AutonomicState.Pain;

            if (snapshot.SubconsciousBias != null && !string.IsNullOrEmpty(snapshot.SubconsciousBias.BiasState))
            {
                character.BiasState = snapshot.SubconsciousBias.BiasState;
            }

            if (snapshot.AffectiveState != null)
            {
                if (!string.IsNullOrEmpty(snapshot.AffectiveState.PrimaryEmotion))
                    character.Emotion = snapshot.AffectiveState.PrimaryEmotion;
                if (!string.IsNullOrEmpty(snapshot.AffectiveState.Impulse))
                    character.Impulse = snapshot.AffectiveState.Impulse;
            }

            if (snapshot.AutonomicState?.PrimarySomaticZones != null && snapshot.AutonomicState.PrimarySomaticZones.Count > 0)
            {
                character.SomaticZones = new List<string>(snapshot.AutonomicState.PrimarySomaticZones);
            }

            character.LiveState = snapshot;
            return true;
        }
        catch (Exception ex)
        {
            AppLogger.Warning($"[PsychosomaticStateValidator] Apply failed: {ex.Message}");
            return false;
        }
    }

    private static void CheckScale(int val, string path, List<string> errors)
    {
        if (!ScaleClamps.IsValidScale(val))
        {
            errors.Add($"{path}: {val} out of range 0–100");
        }
    }
}
