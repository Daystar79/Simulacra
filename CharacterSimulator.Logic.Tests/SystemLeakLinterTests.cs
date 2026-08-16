using Xunit;
using CharacterSimulator.Logic.Hygiene;

namespace CharacterSimulator.Logic.Tests;

public class SystemLeakLinterTests
{
    [Fact]
    public void SystemLeakLinter_DetectsAndRedactsKnownLeaks()
    {
        string leakingDialogue = "I feel like I am in Focus Lock and entering Realm VIII while managing my Debt Ledger.";

        var result = SystemLeakLinter.Audit(leakingDialogue);

        Assert.True(result.HasCriticalLeaks);
        Assert.Equal(3, result.Findings.Count);
        Assert.Contains(result.Findings, f => f.Match == "Focus Lock");
        Assert.Contains(result.Findings, f => f.Match == "Realm VIII");
        Assert.Contains(result.Findings, f => f.Match == "Debt Ledger");
        Assert.DoesNotContain("Focus Lock", result.SanitizedDialogue);
        Assert.DoesNotContain("Realm VIII", result.SanitizedDialogue);
        Assert.DoesNotContain("Debt Ledger", result.SanitizedDialogue);
    }

    [Fact]
    public void SystemLeakLinter_StripsAssistantHelpdeskRegister()
    {
        string text = "How can I help you today? The terrace is still warm.";

        var result = SystemLeakLinter.Audit(text);

        Assert.Contains(result.Findings, f => f.Category == "Assistant Register");
        Assert.DoesNotContain("How can I help you today", result.SanitizedDialogue);
        Assert.Contains("The terrace is still warm.", result.SanitizedDialogue);
    }
}
