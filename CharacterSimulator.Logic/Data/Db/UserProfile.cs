using System;

namespace CharacterSimulator.Logic.Data.Db;

public class UserProfile
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string DisplayName { get; set; } = "Default Player";
    public int DobYear { get; set; } = 2000;
    public int DobMonth { get; set; } = 1;
    public int DobDay { get; set; } = 1;
    public string? PinHash { get; set; }
    public string? PinSalt { get; set; }
    public string? RecoveryCode { get; set; }
    public string DepictionMode { get; set; } = "Explicit";
    public bool IsAdultAttested { get; set; } = false;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime LastOpenedAt { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Derives player age at runtime using local system date.
    /// </summary>
    public int CalculateAge(DateTime? relativeTo = null)
    {
        var today = relativeTo ?? DateTime.Today;
        int age = today.Year - DobYear;
        if (today.Month < DobMonth || (today.Month == DobMonth && today.Day < DobDay))
        {
            age--;
        }
        return Math.Max(0, age);
    }

    public bool IsAdultEligible(DateTime? relativeTo = null)
    {
        return CalculateAge(relativeTo) >= 18;
    }
}
