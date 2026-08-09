namespace CharacterSimulator.Logic;

/// <summary>
/// Constants for simulation-related strings to avoid magic strings.
/// </summary>
public static class SimulationConstants
{
    // Roleplay mode strings
    public const string ModeAutoPlay = "AutoPlay";
    public const string ModePlayerGuided = "PlayerGuided";
    
    // Mode display strings
    public const string ModeDisplayAutoPlay = "🤖 Auto-Play";
    public const string ModeDisplayPlayerGuided = "🎮 Player-Guided";
    public const string ModeDescriptionAutoPlay = "Mode: Auto-Play (turns advance on delay).";
    public const string ModeDescriptionPlayerGuided = "Mode: Player-Guided (pauses after each turn; Send or Step to continue).";
    
    // Default role names
    public const string RolePlayer = "Player";
    public const string RoleSystem = "System";
}
