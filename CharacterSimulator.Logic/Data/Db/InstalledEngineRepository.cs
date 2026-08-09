using System;
using System.Collections.Generic;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Data.Db;

/// <summary>
/// One scanned engine row (roleplay LLM or image generator).
/// Populated after discovery; read by UI for fast dropdowns without re-probing PATH/HTTP.
/// </summary>
public class InstalledEngineRecord
{
    public const string CategoryRoleplay = "roleplay";
    public const string CategoryImage = "image";

    public string Category { get; set; } = "";
    public string EngineId { get; set; } = "";
    public string DisplayName { get; set; } = "";
    public bool IsAvailable { get; set; }
    public string StatusDetail { get; set; } = "";
    /// <summary>Image enum name (e.g. PollinationsAI); optional for roleplay.</summary>
    public string EngineType { get; set; } = "";
    public int SortOrder { get; set; }
    public DateTime ScannedAt { get; set; } = DateTime.UtcNow;
}

/// <summary>
/// Durable cache of last engine scan results (roleplay + imaging).
/// </summary>
public class InstalledEngineRepository
{
    private readonly SqliteConnection _conn;

    public InstalledEngineRepository(SqliteConnection conn)
    {
        _conn = conn ?? throw new ArgumentNullException(nameof(conn));
    }

    public bool HasCategory(string category)
    {
        if (string.IsNullOrWhiteSpace(category)) return false;
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "SELECT 1 FROM installed_engines WHERE category = @cat LIMIT 1;";
            cmd.Parameters.AddWithValue("@cat", category);
            return cmd.ExecuteScalar() != null;
        }
    }

    public DateTime? GetLastScanUtc(string category)
    {
        if (string.IsNullOrWhiteSpace(category)) return null;
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT scanned_at FROM installed_engines
                WHERE category = @cat
                ORDER BY scanned_at DESC
                LIMIT 1;";
            cmd.Parameters.AddWithValue("@cat", category);
            var val = cmd.ExecuteScalar();
            if (val == null || val == DBNull.Value) return null;
            return DateTime.TryParse(val.ToString(), null,
                System.Globalization.DateTimeStyles.RoundtripKind, out var dt)
                ? dt.ToUniversalTime()
                : null;
        }
    }

    public List<InstalledEngineRecord> ListByCategory(string category)
    {
        var list = new List<InstalledEngineRecord>();
        if (string.IsNullOrWhiteSpace(category)) return list;

        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT category, engine_id, display_name, is_available, status_detail,
                       engine_type, sort_order, scanned_at
                FROM installed_engines
                WHERE category = @cat
                ORDER BY sort_order ASC, engine_id COLLATE NOCASE;";
            cmd.Parameters.AddWithValue("@cat", category);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
                list.Add(ReadRecord(reader));
            return list;
        }
    }

    /// <summary>
    /// Atomically replace all rows for a category with a fresh scan result.
    /// </summary>
    public void ReplaceCategory(string category, IReadOnlyList<InstalledEngineRecord> rows)
    {
        if (string.IsNullOrWhiteSpace(category))
            throw new ArgumentException("Category cannot be null or empty", nameof(category));

        lock (_conn)
        {
            using var tx = _conn.BeginTransaction();
            try
            {
                using (var del = _conn.CreateCommand())
                {
                    del.Transaction = tx;
                    del.CommandText = "DELETE FROM installed_engines WHERE category = @cat;";
                    del.Parameters.AddWithValue("@cat", category);
                    del.ExecuteNonQuery();
                }

                string now = DateTime.UtcNow.ToString("o");
                int order = 0;
                foreach (var row in rows)
                {
                    if (row == null || string.IsNullOrWhiteSpace(row.EngineId))
                        continue;

                    using var ins = _conn.CreateCommand();
                    ins.Transaction = tx;
                    ins.CommandText = @"
                        INSERT INTO installed_engines (
                            category, engine_id, display_name, is_available, status_detail,
                            engine_type, sort_order, scanned_at)
                        VALUES (
                            @cat, @id, @name, @avail, @detail,
                            @type, @sort, @scanned);";
                    ins.Parameters.AddWithValue("@cat", category);
                    ins.Parameters.AddWithValue("@id", row.EngineId.Trim());
                    ins.Parameters.AddWithValue("@name", row.DisplayName ?? "");
                    ins.Parameters.AddWithValue("@avail", row.IsAvailable ? 1 : 0);
                    ins.Parameters.AddWithValue("@detail", row.StatusDetail ?? "");
                    ins.Parameters.AddWithValue("@type", row.EngineType ?? "");
                    ins.Parameters.AddWithValue("@sort", row.SortOrder > 0 ? row.SortOrder : order);
                    ins.Parameters.AddWithValue("@scanned",
                        row.ScannedAt == default ? now : row.ScannedAt.ToUniversalTime().ToString("o"));
                    ins.ExecuteNonQuery();
                    order++;
                }

                tx.Commit();
            }
            catch
            {
                try { tx.Rollback(); } catch { /* ignore */ }
                throw;
            }
        }
    }

    public void ClearCategory(string category)
    {
        if (string.IsNullOrWhiteSpace(category)) return;
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "DELETE FROM installed_engines WHERE category = @cat;";
            cmd.Parameters.AddWithValue("@cat", category);
            cmd.ExecuteNonQuery();
        }
    }

    private static InstalledEngineRecord ReadRecord(SqliteDataReader reader)
    {
        DateTime scanned = DateTime.UtcNow;
        if (!reader.IsDBNull(7) &&
            DateTime.TryParse(reader.GetString(7), null,
                System.Globalization.DateTimeStyles.RoundtripKind, out var dt))
        {
            scanned = dt.ToUniversalTime();
        }

        return new InstalledEngineRecord
        {
            Category = reader.GetString(0),
            EngineId = reader.GetString(1),
            DisplayName = reader.IsDBNull(2) ? "" : reader.GetString(2),
            IsAvailable = !reader.IsDBNull(3) && reader.GetInt64(3) != 0,
            StatusDetail = reader.IsDBNull(4) ? "" : reader.GetString(4),
            EngineType = reader.IsDBNull(5) ? "" : reader.GetString(5),
            SortOrder = reader.IsDBNull(6) ? 0 : (int)reader.GetInt64(6),
            ScannedAt = scanned
        };
    }
}
