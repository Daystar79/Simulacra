using System;
using System.IO;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Data.Db;

public static class AppDbInitializer
{
    public static string GetDatabasePath(string? customDir = null)
    {
        string baseDir = customDir ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Profiles");
        if (!Directory.Exists(baseDir))
        {
            Directory.CreateDirectory(baseDir);
        }
        return Path.Combine(baseDir, "app_data.db");
    }

    public static SqliteConnection CreateConnection(string? dbPath = null)
    {
        string path = dbPath ?? GetDatabasePath();
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = path,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Shared
        };
        var conn = new SqliteConnection(builder.ConnectionString);
        conn.Open();

        // Foreign keys, WAL, and a busy timeout so a leftover lock doesn't hang the splash forever
        using (var cmd = conn.CreateCommand())
        {
            cmd.CommandText = "PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 3000;";
            cmd.ExecuteNonQuery();
        }

        return conn;
    }

    public static void InitializeDatabase(SqliteConnection conn)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            CREATE TABLE IF NOT EXISTS schema_info (
                version INTEGER PRIMARY KEY,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                dob_year INTEGER NOT NULL,
                dob_month INTEGER NOT NULL,
                dob_day INTEGER NOT NULL,
                pin_hash TEXT,
                pin_salt TEXT,
                recovery_code TEXT,
                is_adult_attested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_opened_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                title TEXT NOT NULL,
                scene TEXT NOT NULL,
                genre TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_participants (
                session_id TEXT NOT NULL,
                character_slug TEXT NOT NULL,
                slot_order INTEGER NOT NULL,
                PRIMARY KEY (session_id, character_slug),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                speaker TEXT NOT NULL,
                target TEXT NOT NULL,
                dialogue TEXT NOT NULL,
                somatic_json TEXT,
                bond_delta INTEGER NOT NULL DEFAULT 0,
                current_bond INTEGER NOT NULL DEFAULT 0,
                speaker_emotion TEXT,
                meta_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_progress (
                profile_id TEXT NOT NULL,
                character_slug TEXT NOT NULL,
                bias_strength INTEGER NOT NULL DEFAULT 0,
                active_focus TEXT,
                bias_state TEXT,
                snapshot_json TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (profile_id, character_slug),
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_history (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                character_slug TEXT NOT NULL,
                movement_id TEXT,
                pressure TEXT,
                delta TEXT,
                permanence TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );

            -- UI phone book for opaque card files (full identity remains on disk JSON).
            CREATE TABLE IF NOT EXISTS character_catalog (
                card_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                call_name TEXT,
                age INTEGER,
                canon_adult INTEGER NOT NULL DEFAULT 1,
                description TEXT,
                physical_short TEXT,
                avatar_path TEXT,
                source_label TEXT,
                is_derived INTEGER NOT NULL DEFAULT 0,
                file_mtime_utc TEXT,
                content_fingerprint TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_character_catalog_name
                ON character_catalog(display_name COLLATE NOCASE);

            -- Generated / assigned character portraits (BLOB lookup by card_id).
            CREATE TABLE IF NOT EXISTS character_portraits (
                card_id TEXT PRIMARY KEY,
                mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
                image_blob BLOB NOT NULL,
                prompt TEXT,
                engine TEXT,
                updated_at TEXT NOT NULL
            );

            -- Last successful scan of roleplay LLM + image engines (fast UI dropdowns).
            CREATE TABLE IF NOT EXISTS installed_engines (
                category TEXT NOT NULL,
                engine_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 0,
                status_detail TEXT,
                engine_type TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                scanned_at TEXT NOT NULL,
                PRIMARY KEY (category, engine_id)
            );

            CREATE INDEX IF NOT EXISTS idx_installed_engines_category
                ON installed_engines(category, sort_order);

            INSERT OR IGNORE INTO schema_info (version, updated_at) VALUES (1, datetime('now'));
        ";
        cmd.ExecuteNonQuery();

        try
        {
            using var alterCmd = conn.CreateCommand();
            alterCmd.CommandText = "ALTER TABLE profiles ADD COLUMN recovery_code TEXT;";
            alterCmd.ExecuteNonQuery();
        }
        catch { }

        try
        {
            using var alterDepictCmd = conn.CreateCommand();
            alterDepictCmd.CommandText = "ALTER TABLE profiles ADD COLUMN depiction_mode TEXT DEFAULT 'Explicit';";
            alterDepictCmd.ExecuteNonQuery();
        }
        catch { }

        // Forward-compatible: tables added after initial ship.
        try
        {
            using var catalogCmd = conn.CreateCommand();
            catalogCmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS character_catalog (
                    card_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    call_name TEXT,
                    age INTEGER,
                    canon_adult INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    physical_short TEXT,
                    avatar_path TEXT,
                    source_label TEXT,
                    is_derived INTEGER NOT NULL DEFAULT 0,
                    file_mtime_utc TEXT,
                    content_fingerprint TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_character_catalog_name
                    ON character_catalog(display_name COLLATE NOCASE);

                CREATE TABLE IF NOT EXISTS character_portraits (
                    card_id TEXT PRIMARY KEY,
                    mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
                    image_blob BLOB NOT NULL,
                    prompt TEXT,
                    engine TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS installed_engines (
                    category TEXT NOT NULL,
                    engine_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_available INTEGER NOT NULL DEFAULT 0,
                    status_detail TEXT,
                    engine_type TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    scanned_at TEXT NOT NULL,
                    PRIMARY KEY (category, engine_id)
                );
                CREATE INDEX IF NOT EXISTS idx_installed_engines_category
                    ON installed_engines(category, sort_order);";
            catalogCmd.ExecuteNonQuery();
        }
        catch { }
    }
}
