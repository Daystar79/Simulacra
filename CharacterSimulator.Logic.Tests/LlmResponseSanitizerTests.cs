using CharacterSimulator.Logic;
using Xunit;

namespace CharacterSimulator.Logic.Tests;

public class LlmResponseSanitizerTests
{
    [Fact]
    public void ClampToFirstReply_CutsSecondSomaticBlock()
    {
        string raw =
            """
            [Somatic: Slow breath, pulse calms] "Music... it is a quiet companion." She leans back against the balustrade.

            [Somatic: Slow breath, pulse calms] "Music... it is a quiet companion." She leans back against the balustrade.
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw);

        Assert.Contains("quiet companion", clamped);
        Assert.Equal(1, CountOccurrences(clamped, "[Somatic:"));
        Assert.DoesNotContain("Current Situation", clamped);
    }

    [Fact]
    public void ClampToFirstReply_CutsPromptLeakTail()
    {
        string raw =
            """
            [Somatic: Slow breath, pulse calms] "Music... it is a quiet companion." She leans back against the balustrade.

            The night air carries her words.
            You are physically present in this place, but you have not yet spoken.
            Current Situation:
            Active Focus / State: Realm IX
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw);

        Assert.Contains("quiet companion", clamped);
        Assert.DoesNotContain("You are physically present", clamped);
        Assert.DoesNotContain("Current Situation", clamped);
        Assert.DoesNotContain("Active Focus", clamped);
    }

    [Fact]
    public void ClampToFirstReply_RemovesDuplicateQuotedParagraphs()
    {
        string raw =
            """
            [Somatic: Slow breath] "Hello there." She nods.

            [spoken] "Hello there." She nods again.
            FORMATTING RULE: Put all spoken words inside double quotes.
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw);

        Assert.Contains("Hello there", clamped);
        Assert.DoesNotContain("FORMATTING RULE", clamped);
        Assert.DoesNotContain("[spoken]", clamped);
    }

    [Fact]
    public void PromptBuilder_IncludesTranscriptAndContinueGuidance()
    {
        var character = new Character { Name = "Serena", CurrentState = "Calm", BiasState = "DORMANT", Bond = 0 };
        string history = PromptBuilder.FormatTranscript(new[]
        {
            "Serena: \"Music... it is a quiet companion.\" She leans back against the balustrade."
        });

        string situation = PromptBuilder.BuildSituationBlock(character, "", "", history);

        Assert.Contains("CONVERSATION SO FAR", situation);
        Assert.Contains("quiet companion", situation);
        Assert.Contains("volitional beat", situation);
        Assert.DoesNotContain("Open the scene in character", situation);
    }

    [Fact]
    public void PromptBuilder_FormatExample_IsNotConcreteMusicBalustrade()
    {
        var character = new Character { Name = "Serena" };
        string full = PromptBuilder.BuildFullPrompt(character, "", "A quiet room", "");
        string chat = PromptBuilder.BuildChatMlPrompt(character, "", "A quiet room", "");

        Assert.DoesNotContain("Music... it is a quiet companion", full);
        Assert.DoesNotContain("leans back against the balustrade", full);
        Assert.DoesNotContain("Music... it is a quiet companion", chat);
        Assert.Contains("[Somatic: brief internal tell]", full);
        Assert.DoesNotContain("Opening physical action beat", full);
    }

    [Fact]
    public void ClampToFirstReply_StripsPlayerTagLeak()
    {
        string raw =
            """
            [Somatic: Slow breath] "This is just an internal quirk for now." She pauses briefly before adding softly.
            [Player]: - Looks like the parsers are not handling the output properly.
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw);

        Assert.Contains("internal quirk", clamped);
        Assert.DoesNotContain("[Player]:", clamped);
        Assert.DoesNotContain("parsers are not handling", clamped);
    }

    [Fact]
    public void ClampToFirstReply_StripsLeadingUserParrotEcho()
    {
        string userInput = "Where did you hide the ledger?";
        string raw =
            """
            User input: "Where did you hide the ledger?"
            [Somatic: Deep breath, pulse quickens] "It is locked safely behind the portrait in the study." She turns away calmly.
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw, userInput);

        Assert.StartsWith("[Somatic:", clamped);
        Assert.Contains("locked safely behind the portrait", clamped);
        Assert.DoesNotContain("User input:", clamped);
    }

    [Fact]
    public void ClampToFirstReply_StripsDuplicatePastTurnDialogue()
    {
        string history = "Serena: \"Moonlight has been my sanctuary for as long as I can remember. It’s an invitation only few dare cross.\"";
        string raw =
            """
            "Moonlight has been my sanctuary for as long as I can remember. It’s an invitation only few dare cross." She gestures softly towards the terrace.

            [Somatic: Soft sigh] "The evening air is cooling down. Should we move inside?" She steps toward the archway.
            """;

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw, userInput: null, conversationHistory: history);

        Assert.Contains("evening air is cooling down", clamped);
        Assert.DoesNotContain("Moonlight has been my sanctuary", clamped);
    }

    [Fact]
    public void ClampToFirstReply_StripsBracketedSpeakerPrefix()
    {
        string raw = "[Serena] *gently traces a line from her nape to the crown of her head*";
        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw);
        Assert.StartsWith("*gently traces", clamped);
        Assert.DoesNotContain("[Serena]", clamped);
    }

    [Fact]
    public void ClampToFirstReply_StripsUnquotedRepeatedActionBeatFromHistory()
    {
        string history = "Serena: *gently traces a line from her nape to the crown of her head with fingers that are long and tapered*";
        string raw = "[Serena] *gently traces a line from her nape to the crown of her head with fingers that are long and tapered*\n\n\"The night is calm.\"";

        string clamped = LlmResponseSanitizer.ClampToFirstReply(raw, userInput: null, conversationHistory: history);

        Assert.Equal("\"The night is calm.\"", clamped);
        Assert.DoesNotContain("gently traces a line", clamped);
    }

    private static int CountOccurrences(string haystack, string needle)
    {
        int count = 0;
        int idx = 0;
        while ((idx = haystack.IndexOf(needle, idx, System.StringComparison.OrdinalIgnoreCase)) >= 0)
        {
            count++;
            idx += needle.Length;
        }
        return count;
    }
}
