using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Data.Sqlite;

namespace CharacterSimulator.Logic.Data.Db;

public class ProfileRepository
{
    private readonly SqliteConnection _conn;

    public ProfileRepository(SqliteConnection conn)
    {
        _conn = conn;
    }

    public List<UserProfile> GetAllProfiles()
    {
        lock (_conn)
        {
            var list = new List<UserProfile>();
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT id, display_name, dob_year, dob_month, dob_day, pin_hash, pin_salt, is_adult_attested, created_at, last_opened_at, recovery_code, depiction_mode
                FROM profiles
                ORDER BY last_opened_at DESC;";

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                list.Add(ReadProfile(reader));
            }
            return list;
        }
    }

    public UserProfile? GetById(string profileId)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT id, display_name, dob_year, dob_month, dob_day, pin_hash, pin_salt, is_adult_attested, created_at, last_opened_at, recovery_code, depiction_mode
                FROM profiles
                WHERE id = @id LIMIT 1;";
            cmd.Parameters.AddWithValue("@id", profileId);

            using var reader = cmd.ExecuteReader();
            if (reader.Read())
            {
                return ReadProfile(reader);
            }
            return null;
        }
    }

    public UserProfile CreateProfile(string displayName, int dobYear, int dobMonth, int dobDay, string? pin = null, bool adultAttested = false)
    {
        string? salt = null;
        string? hash = null;
        if (!string.IsNullOrWhiteSpace(pin))
        {
            salt = GenerateSalt();
            hash = HashPin(pin, salt);
        }

        string recoveryCode = GenerateRecoveryCode();

        var profile = new UserProfile
        {
            Id = Guid.NewGuid().ToString("N"),
            DisplayName = displayName,
            DobYear = dobYear,
            DobMonth = dobMonth,
            DobDay = dobDay,
            PinHash = hash,
            PinSalt = salt,
            RecoveryCode = recoveryCode,
            IsAdultAttested = adultAttested,
            CreatedAt = DateTime.UtcNow,
            LastOpenedAt = DateTime.UtcNow
        };

        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                INSERT INTO profiles (id, display_name, dob_year, dob_month, dob_day, pin_hash, pin_salt, recovery_code, is_adult_attested, created_at, last_opened_at, depiction_mode)
                VALUES (@id, @name, @year, @month, @day, @hash, @salt, @rec, @adult, @created, @opened, @depict);";
            cmd.Parameters.AddWithValue("@id", profile.Id);
            cmd.Parameters.AddWithValue("@name", profile.DisplayName);
            cmd.Parameters.AddWithValue("@year", profile.DobYear);
            cmd.Parameters.AddWithValue("@month", profile.DobMonth);
            cmd.Parameters.AddWithValue("@day", profile.DobDay);
            cmd.Parameters.AddWithValue("@hash", (object?)profile.PinHash ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@salt", (object?)profile.PinSalt ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@rec", profile.RecoveryCode);
            cmd.Parameters.AddWithValue("@adult", profile.IsAdultAttested ? 1 : 0);
            cmd.Parameters.AddWithValue("@created", profile.CreatedAt.ToString("o"));
            cmd.Parameters.AddWithValue("@opened", profile.LastOpenedAt.ToString("o"));
            cmd.Parameters.AddWithValue("@depict", profile.DepictionMode);
            cmd.ExecuteNonQuery();
        }

        return profile;
    }

    public bool UpdatePin(string profileId, string? oldPin, string? newPin)
    {
        var p = GetById(profileId);
        if (p == null) return false;

        if (!VerifyPin(p, oldPin ?? "")) return false;

        string? newSalt = null;
        string? newHash = null;
        if (!string.IsNullOrWhiteSpace(newPin))
        {
            newSalt = GenerateSalt();
            newHash = HashPin(newPin, newSalt);
        }

        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE profiles SET pin_hash = @hash, pin_salt = @salt WHERE id = @id;";
            cmd.Parameters.AddWithValue("@hash", (object?)newHash ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@salt", (object?)newSalt ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@id", profileId);
            return cmd.ExecuteNonQuery() > 0;
        }
    }

    public bool ResetPinWithRecoveryCode(string profileId, string recoveryCode, string? newPin)
    {
        var p = GetById(profileId);
        if (p == null || string.IsNullOrWhiteSpace(p.RecoveryCode)) return false;

        if (!string.Equals(p.RecoveryCode.Trim(), recoveryCode.Trim(), StringComparison.OrdinalIgnoreCase))
            return false;

        string? newSalt = null;
        string? newHash = null;
        if (!string.IsNullOrWhiteSpace(newPin))
        {
            newSalt = GenerateSalt();
            newHash = HashPin(newPin, newSalt);
        }

        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE profiles SET pin_hash = @hash, pin_salt = @salt WHERE id = @id;";
            cmd.Parameters.AddWithValue("@hash", (object?)newHash ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@salt", (object?)newSalt ?? DBNull.Value);
            cmd.Parameters.AddWithValue("@id", profileId);
            return cmd.ExecuteNonQuery() > 0;
        }
    }

    public bool VerifyPin(UserProfile profile, string pin)
    {
        if (string.IsNullOrEmpty(profile.PinHash) || string.IsNullOrEmpty(profile.PinSalt))
            return true; // No PIN required for this profile

        if (pin == null) return false;

        string hash = HashPin(pin, profile.PinSalt);
        byte[] hashBytes = Encoding.UTF8.GetBytes(hash);
        byte[] expectedBytes = Encoding.UTF8.GetBytes(profile.PinHash);
        return hashBytes.Length == expectedBytes.Length && CryptographicOperations.FixedTimeEquals(hashBytes, expectedBytes);
    }

    public void TouchLastOpened(string profileId)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE profiles SET last_opened_at = @now WHERE id = @id;";
            cmd.Parameters.AddWithValue("@now", DateTime.UtcNow.ToString("o"));
            cmd.Parameters.AddWithValue("@id", profileId);
            cmd.ExecuteNonQuery();
        }
    }

    public void SetAdultAttestation(string profileId, bool attested)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE profiles SET is_adult_attested = @attested WHERE id = @id;";
            cmd.Parameters.AddWithValue("@attested", attested ? 1 : 0);
            cmd.Parameters.AddWithValue("@id", profileId);
            cmd.ExecuteNonQuery();
        }
    }

    public void SetDepictionMode(string profileId, string depictionMode)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "UPDATE profiles SET depiction_mode = @depict WHERE id = @id;";
            cmd.Parameters.AddWithValue("@depict", depictionMode);
            cmd.Parameters.AddWithValue("@id", profileId);
            cmd.ExecuteNonQuery();
        }
    }

    private static UserProfile ReadProfile(SqliteDataReader reader)
    {
        string depict = "Explicit";
        if (reader.FieldCount > 11 && !reader.IsDBNull(11))
        {
            depict = reader.GetString(11);
        }

        return new UserProfile
        {
            Id = reader.GetString(0),
            DisplayName = reader.GetString(1),
            DobYear = reader.GetInt32(2),
            DobMonth = reader.GetInt32(3),
            DobDay = reader.GetInt32(4),
            PinHash = reader.IsDBNull(5) ? null : reader.GetString(5),
            PinSalt = reader.IsDBNull(6) ? null : reader.GetString(6),
            IsAdultAttested = reader.GetInt32(7) == 1,
            CreatedAt = DateTime.Parse(reader.GetString(8)),
            LastOpenedAt = DateTime.Parse(reader.GetString(9)),
            RecoveryCode = reader.IsDBNull(10) ? null : reader.GetString(10),
            DepictionMode = depict
        };
    }

    private static string GenerateSalt()
    {
        byte[] salt = new byte[16];
        RandomNumberGenerator.Fill(salt);
        return Convert.ToBase64String(salt);
    }

    private static string HashPin(string pin, string salt)
    {
        byte[] hash = Rfc2898DeriveBytes.Pbkdf2(
            pin,
            Convert.FromBase64String(salt),
            10_000,
            HashAlgorithmName.SHA256,
            32);
        return Convert.ToBase64String(hash);
    }

    private static string GenerateRecoveryCode()
    {
        return $"REC-{Guid.NewGuid().ToString("N").Substring(0, 4).ToUpper()}-{Guid.NewGuid().ToString("N").Substring(0, 4).ToUpper()}-{Guid.NewGuid().ToString("N").Substring(0, 4).ToUpper()}";
    }

    public bool DeleteProfile(string profileId)
    {
        lock (_conn)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "DELETE FROM profiles WHERE id = @id;";
            cmd.Parameters.AddWithValue("@id", profileId);
            int rows = cmd.ExecuteNonQuery();
            return rows > 0;
        }
    }
}
