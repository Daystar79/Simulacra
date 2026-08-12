using System;
using System.Collections.Generic;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Data.Db;

public class DbSession
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string ProfileId { get; set; } = "";
    public string Title { get; set; } = "Roleplay Session";
    public string Scene { get; set; } = "";
    public string Genre { get; set; } = "";
    public string Mode { get; set; } = "AutoPlay";
    public string Status { get; set; } = "Active";
    public DateTime StartedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

public class DbSessionTurn
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string SessionId { get; set; } = "";
    public int TurnIndex { get; set; }
    public string Speaker { get; set; } = "";
    public string Target { get; set; } = "";
    public string Dialogue { get; set; } = "";
    public string SomaticJson { get; set; } = "";
    public int BondDelta { get; set; }
    public int CurrentBond { get; set; }
    public string SpeakerEmotion { get; set; } = "";
    public string MetaJson { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}

public class SessionRepository
{
    private readonly SqliteConnection _conn;

    public SessionRepository(SqliteConnection conn)
    {
        _conn = conn;
    }

    public DbSession CreateSession(string profileId, string title, string scene, string genre, string mode, List<string> characterSlugs)
    {
        var session = new DbSession
        {
            Id = Guid.NewGuid().ToString("N"),
            ProfileId = profileId,
            Title = title,
            Scene = scene,
            Genre = genre,
            Mode = mode,
            Status = "Active",
            StartedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow
        };

        lock (_conn)
        {
            using var tx = _conn.BeginTransaction();
            try
            {
                using (var cmd = _conn.CreateCommand())
                {
                    cmd.Transaction = tx;
                    cmd.CommandText = @"
                        INSERT INTO sessions (id, profile_id, title, scene, genre, mode, status, started_at, updated_at)
                        VALUES (@id, @pid, @title, @scene, @genre, @mode, @status, @started, @updated);";
                    cmd.Parameters.AddWithValue("@id", session.Id);
                    cmd.Parameters.AddWithValue("@pid", session.ProfileId);
                    cmd.Parameters.AddWithValue("@title", session.Title);
                    cmd.Parameters.AddWithValue("@scene", session.Scene);
                    cmd.Parameters.AddWithValue("@genre", session.Genre);
                    cmd.Parameters.AddWithValue("@mode", session.Mode);
                    cmd.Parameters.AddWithValue("@status", session.Status);
                    cmd.Parameters.AddWithValue("@started", session.StartedAt.ToString("o"));
                    cmd.Parameters.AddWithValue("@updated", session.UpdatedAt.ToString("o"));
                    cmd.ExecuteNonQuery();
                }

                for (int i = 0; i < characterSlugs.Count; i++)
                {
                    using var pCmd = _conn.CreateCommand();
                    pCmd.Transaction = tx;
                    pCmd.CommandText = @"
                        INSERT INTO session_participants (session_id, character_slug, slot_order)
                        VALUES (@sid, @slug, @order);";
                    pCmd.Parameters.AddWithValue("@sid", session.Id);
                    pCmd.Parameters.AddWithValue("@slug", characterSlugs[i]);
                    pCmd.Parameters.AddWithValue("@order", i);
                    pCmd.ExecuteNonQuery();
                }

                tx.Commit();
            }
            catch
            {
                tx.Rollback();
                throw;
            }
        }

        return session;
    }

    public List<DbSession> GetSessionsForProfile(string profileId)
    {
        lock (_conn)
        {
            var list = new List<DbSession>();
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT id, profile_id, title, scene, genre, mode, status, started_at, updated_at
                FROM sessions
                WHERE profile_id = @pid
                ORDER BY updated_at DESC;";
            cmd.Parameters.AddWithValue("@pid", profileId);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(new DbSession
                {
                    Id = reader.GetString(0),
                    ProfileId = reader.GetString(1),
                    Title = reader.GetString(2),
                    Scene = reader.GetString(3),
                    Genre = reader.GetString(4),
                    Mode = reader.GetString(5),
                    Status = reader.GetString(6),
                    StartedAt = DateTime.Parse(reader.GetString(7)),
                    UpdatedAt = DateTime.Parse(reader.GetString(8))
                });
            }
            return list;
        }
    }

    public void AddTurn(DbSessionTurn turn)
    {
        lock (_conn)
        {
            using var tx = _conn.BeginTransaction();
            try
            {
                using (var cmd = _conn.CreateCommand())
                {
                    cmd.Transaction = tx;
                    cmd.CommandText = @"
                        INSERT INTO session_turns (id, session_id, turn_index, speaker, target, dialogue, somatic_json, bond_delta, current_bond, speaker_emotion, meta_json, created_at)
                        VALUES (@id, @sid, @index, @speaker, @target, @dialogue, @somatic, @bdelta, @cbond, @emotion, @meta, @created);";
                    cmd.Parameters.AddWithValue("@id", turn.Id);
                    cmd.Parameters.AddWithValue("@sid", turn.SessionId);
                    cmd.Parameters.AddWithValue("@index", turn.TurnIndex);
                    cmd.Parameters.AddWithValue("@speaker", turn.Speaker);
                    cmd.Parameters.AddWithValue("@target", turn.Target);
                    cmd.Parameters.AddWithValue("@dialogue", turn.Dialogue);
                    cmd.Parameters.AddWithValue("@somatic", turn.SomaticJson);
                    cmd.Parameters.AddWithValue("@bdelta", turn.BondDelta);
                    cmd.Parameters.AddWithValue("@cbond", turn.CurrentBond);
                    cmd.Parameters.AddWithValue("@emotion", turn.SpeakerEmotion);
                    cmd.Parameters.AddWithValue("@meta", turn.MetaJson);
                    cmd.Parameters.AddWithValue("@created", turn.CreatedAt.ToString("o"));
                    cmd.ExecuteNonQuery();
                }

                using (var uCmd = _conn.CreateCommand())
                {
                    uCmd.Transaction = tx;
                    uCmd.CommandText = "UPDATE sessions SET updated_at = @now WHERE id = @sid;";
                    uCmd.Parameters.AddWithValue("@now", DateTime.UtcNow.ToString("o"));
                    uCmd.Parameters.AddWithValue("@sid", turn.SessionId);
                    uCmd.ExecuteNonQuery();
                }

                tx.Commit();
            }
            catch
            {
                tx.Rollback();
                throw;
            }
        }
    }

    public List<DbSessionTurn> GetTurnsForSession(string sessionId)
    {
        lock (_conn)
        {
            var list = new List<DbSessionTurn>();
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT id, session_id, turn_index, speaker, target, dialogue, somatic_json, bond_delta, current_bond, speaker_emotion, meta_json, created_at
                FROM session_turns
                WHERE session_id = @sid
                ORDER BY turn_index ASC;";
            cmd.Parameters.AddWithValue("@sid", sessionId);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(new DbSessionTurn
                {
                    Id = reader.GetString(0),
                    SessionId = reader.GetString(1),
                    TurnIndex = reader.GetInt32(2),
                    Speaker = reader.GetString(3),
                    Target = reader.GetString(4),
                    Dialogue = reader.GetString(5),
                    SomaticJson = reader.IsDBNull(6) ? "" : reader.GetString(6),
                    BondDelta = reader.GetInt32(7),
                    CurrentBond = reader.GetInt32(8),
                    SpeakerEmotion = reader.IsDBNull(9) ? "" : reader.GetString(9),
                    MetaJson = reader.IsDBNull(10) ? "" : reader.GetString(10),
                    CreatedAt = DateTime.Parse(reader.GetString(11))
                });
            }
            return list;
        }
    }

    public List<string> GetSessionParticipants(string sessionId)
    {
        lock (_conn)
        {
            var list = new List<string>();
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT character_slug
                FROM session_participants
                WHERE session_id = @sid
                ORDER BY slot_order ASC;";
            cmd.Parameters.AddWithValue("@sid", sessionId);
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(reader.GetString(0));
            }
            return list;
        }
    }

    public bool DeleteSession(string sessionId)
    {
        lock (_conn)
        {
            using var tx = _conn.BeginTransaction();
            try
            {
                using (var cmd = _conn.CreateCommand())
                {
                    cmd.Transaction = tx;
                    cmd.CommandText = "DELETE FROM session_turns WHERE session_id = @sid;";
                    cmd.Parameters.AddWithValue("@sid", sessionId);
                    cmd.ExecuteNonQuery();
                }
                using (var cmd = _conn.CreateCommand())
                {
                    cmd.Transaction = tx;
                    cmd.CommandText = "DELETE FROM session_participants WHERE session_id = @sid;";
                    cmd.Parameters.AddWithValue("@sid", sessionId);
                    cmd.ExecuteNonQuery();
                }
                using (var cmd = _conn.CreateCommand())
                {
                    cmd.Transaction = tx;
                    cmd.CommandText = "DELETE FROM sessions WHERE id = @sid;";
                    cmd.Parameters.AddWithValue("@sid", sessionId);
                    cmd.ExecuteNonQuery();
                }
                tx.Commit();
                return true;
            }
            catch
            {
                tx.Rollback();
                return false;
            }
        }
    }

    public bool UpdateSessionTitle(string sessionId, string newTitle)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE sessions SET title = @title, updated_at = @now WHERE id = @sid;";
            cmd.Parameters.AddWithValue("@title", newTitle);
            cmd.Parameters.AddWithValue("@now", DateTime.UtcNow.ToString("o"));
            cmd.Parameters.AddWithValue("@sid", sessionId);
            return cmd.ExecuteNonQuery() > 0;
        }
    }

    public bool ArchiveSession(string sessionId)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE sessions SET status = 'Archived', updated_at = @now WHERE id = @sid;";
            cmd.Parameters.AddWithValue("@now", DateTime.UtcNow.ToString("o"));
            cmd.Parameters.AddWithValue("@sid", sessionId);
            return cmd.ExecuteNonQuery() > 0;
        }
    }
}
