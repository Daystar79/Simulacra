using System;
using System.Collections.Generic;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Data.Db;

public class CharacterProgressRecord
{
    public string ProfileId { get; set; } = "";
    public string CharacterSlug { get; set; } = "";
    public int BiasStrength { get; set; }
    public string ActiveFocus { get; set; } = "";
    public string BiasState { get; set; } = "";
    public string SnapshotJson { get; set; } = "";
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

public class CharacterProgressRepository
{
    private readonly SqliteConnection _conn;

    public CharacterProgressRepository(SqliteConnection conn)
    {
        _conn = conn;
    }

    public void SaveProgress(CharacterProgressRecord record)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                INSERT INTO character_progress (profile_id, character_slug, bias_strength, active_focus, bias_state, snapshot_json, updated_at)
                VALUES (@pid, @slug, @strength, @focus, @bstate, @snapshot, @updated)
                ON CONFLICT(profile_id, character_slug) DO UPDATE SET
                    bias_strength = excluded.bias_strength,
                    active_focus = excluded.active_focus,
                    bias_state = excluded.bias_state,
                    snapshot_json = excluded.snapshot_json,
                    updated_at = excluded.updated_at;";

            cmd.Parameters.AddWithValue("@pid", record.ProfileId);
            cmd.Parameters.AddWithValue("@slug", record.CharacterSlug);
            cmd.Parameters.AddWithValue("@strength", record.BiasStrength);
            cmd.Parameters.AddWithValue("@focus", (object?)record.ActiveFocus ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@bstate", (object?)record.BiasState ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@snapshot", (object?)record.SnapshotJson ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@updated", DateTime.UtcNow.ToString("o"));

            cmd.ExecuteNonQuery();
        }
    }

    public CharacterProgressRecord? GetProgress(string profileId, string characterSlug)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT profile_id, character_slug, bias_strength, active_focus, bias_state, snapshot_json, updated_at
                FROM character_progress
                WHERE profile_id = @pid AND character_slug = @slug LIMIT 1;";
            cmd.Parameters.AddWithValue("@pid", profileId);
            cmd.Parameters.AddWithValue("@slug", characterSlug);

            using var reader = cmd.ExecuteReader();
            if (reader.Read())
            {
                return new CharacterProgressRecord
                {
                    ProfileId = reader.GetString(0),
                    CharacterSlug = reader.GetString(1),
                    BiasStrength = reader.GetInt32(2),
                    ActiveFocus = reader.IsDBNull(3) ? "" : reader.GetString(3),
                    BiasState = reader.IsDBNull(4) ? "" : reader.GetString(4),
                    SnapshotJson = reader.IsDBNull(5) ? "" : reader.GetString(5),
                    UpdatedAt = DateTime.Parse(reader.GetString(6))
                };
            }
            return null;
        }
    }

    public List<CharacterProgressRecord> GetAllProgressForProfile(string profileId)
    {
        lock (_conn)
        {
            var list = new List<CharacterProgressRecord>();
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT profile_id, character_slug, bias_strength, active_focus, bias_state, snapshot_json, updated_at
                FROM character_progress
                WHERE profile_id = @pid
                ORDER BY updated_at DESC;";
            cmd.Parameters.AddWithValue("@pid", profileId);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(new CharacterProgressRecord
                {
                    ProfileId = reader.GetString(0),
                    CharacterSlug = reader.GetString(1),
                    BiasStrength = reader.GetInt32(2),
                    ActiveFocus = reader.IsDBNull(3) ? "" : reader.GetString(3),
                    BiasState = reader.IsDBNull(4) ? "" : reader.GetString(4),
                    SnapshotJson = reader.IsDBNull(5) ? "" : reader.GetString(5),
                    UpdatedAt = DateTime.Parse(reader.GetString(6))
                });
            }
            return list;
        }
    }
}
