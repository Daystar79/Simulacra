using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using CharacterSimulator.Logic.Data.Db;

namespace CharacterSimulator.Logic.Services;

public class CloudBlobMeta
{
    public string ProfileId { get; set; } = "";
    public string LockerToken { get; set; } = "";
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
    public string VersionVector { get; set; } = "v1";
    public string CipherTextBase64 { get; set; } = "";
    public string SaltBase64 { get; set; } = "";
    public string IVBase64 { get; set; } = "";
}

public class CloudSyncResult
{
    public bool Success { get; set; }
    public string Message { get; set; } = "";
    public CloudBlobMeta? Blob { get; set; }
}

public static class CloudSyncService
{
    public static string GenerateDeviceLockerToken()
    {
        return $"LOCKER-{Guid.NewGuid().ToString("N").Substring(0, 8).ToUpper()}-{Guid.NewGuid().ToString("N").Substring(0, 8).ToUpper()}";
    }

    /// <summary>
    /// Creates a sealed client-side encrypted blob container from profile SQLite data using AES-256.
    /// The server only receives ciphertext and salt; the PIN/passphrase is never transmitted.
    /// </summary>
    public static CloudSyncResult ExportSealedProfileBlob(UserProfile profile, SqliteConnection conn, string passphrase)
    {
        try
        {
            var pRepo = new ProfileRepository(conn);
            var freshProfile = pRepo.GetById(profile.Id) ?? profile;

            var sRepo = new SessionRepository(conn);
            var sessions = sRepo.GetSessionsForProfile(profile.Id);

            var prRepo = new CharacterProgressRepository(conn);
            var progressList = prRepo.GetAllProgressForProfile(profile.Id);

            var exportPayload = new
            {
                Profile = freshProfile,
                Sessions = sessions,
                Progress = progressList,
                ExportedAt = DateTime.UtcNow
            };

            string json = JsonSerializer.Serialize(exportPayload);
            byte[] plainBytes = Encoding.UTF8.GetBytes(json);

            byte[] salt = new byte[16];
            RandomNumberGenerator.Fill(salt);

            byte[] iv = new byte[16];
            RandomNumberGenerator.Fill(iv);

            byte[] key = Rfc2898DeriveBytes.Pbkdf2(
                passphrase,
                salt,
                20_000,
                HashAlgorithmName.SHA256,
                32);

            using var aes = Aes.Create();
            aes.Key = key;
            aes.IV = iv;

            using var ms = new MemoryStream();
            using (var cs = new CryptoStream(ms, aes.CreateEncryptor(), CryptoStreamMode.Write))
            {
                cs.Write(plainBytes, 0, plainBytes.Length);
                cs.FlushFinalBlock();
            }

            byte[] cipherBytes = ms.ToArray();

            var blob = new CloudBlobMeta
            {
                ProfileId = profile.Id,
                LockerToken = GenerateDeviceLockerToken(),
                UpdatedAt = DateTime.UtcNow,
                VersionVector = "1.0",
                CipherTextBase64 = Convert.ToBase64String(cipherBytes),
                SaltBase64 = Convert.ToBase64String(salt),
                IVBase64 = Convert.ToBase64String(iv)
            };

            return new CloudSyncResult
            {
                Success = true,
                Message = "Sealed profile blob exported successfully.",
                Blob = blob
            };
        }
        catch (Exception ex)
        {
            return new CloudSyncResult
            {
                Success = false,
                Message = $"Failed to seal profile blob: {ex.Message}"
            };
        }
    }

    /// <summary>
    /// Decrypts a sealed profile blob container using passphrase and restores data.
    /// </summary>
    public static CloudSyncResult DecryptSealedProfileBlob(CloudBlobMeta blob, string passphrase, out string? jsonPayload)
    {
        jsonPayload = null;
        try
        {
            byte[] cipherBytes = Convert.FromBase64String(blob.CipherTextBase64);
            byte[] salt = Convert.FromBase64String(blob.SaltBase64);
            byte[] iv = Convert.FromBase64String(blob.IVBase64);

            byte[] key = Rfc2898DeriveBytes.Pbkdf2(
                passphrase,
                salt,
                20_000,
                HashAlgorithmName.SHA256,
                32);

            using var aes = Aes.Create();
            aes.Key = key;
            aes.IV = iv;

            using var ms = new MemoryStream();
            using (var cs = new CryptoStream(ms, aes.CreateDecryptor(), CryptoStreamMode.Write))
            {
                cs.Write(cipherBytes, 0, cipherBytes.Length);
                cs.FlushFinalBlock();
            }

            byte[] plainBytes = ms.ToArray();
            jsonPayload = Encoding.UTF8.GetString(plainBytes);

            return new CloudSyncResult
            {
                Success = true,
                Message = "Sealed profile blob decrypted successfully.",
                Blob = blob
            };
        }
        catch (Exception ex)
        {
            return new CloudSyncResult
            {
                Success = false,
                Message = $"Decryption failed: {ex.Message}"
            };
        }
    }

    /// <summary>
    /// Conflict resolution: last-write-wins based on UpdatedAt timestamp.
    /// </summary>
    public static CloudBlobMeta ResolveConflict(CloudBlobMeta localBlob, CloudBlobMeta remoteBlob)
    {
        return remoteBlob.UpdatedAt > localBlob.UpdatedAt ? remoteBlob : localBlob;
    }
}
