using System.Linq;
using Xunit;
using CharacterSimulator.Logic;

namespace CharacterSimulator.Logic.Tests;

public class DialogueSegmentParserTests
{
    [Fact]
    public void Parse_IdealTaggedReply_SplitsSomaticSpeechAndNarration()
    {
        string raw = """
            [Somatic: Slow breath, pulse calms] She leans back against the balustrade. "The night is calm."
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains("Slow breath", parsed.SomaticText);
        Assert.DoesNotContain("Slow breath", parsed.CanonicalDialogue);
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Somatic && s.Text.Contains("Slow breath"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("leans back"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("night is calm"));
        Assert.Contains("\"The night is calm.\"", parsed.CanonicalDialogue);
    }

    [Fact]
    public void Parse_OrphanCloseQuote_PromotesLeadingSpeech()
    {
        string raw = """
            I appreciate your boldness, but I'm not inclined to indulge such desires right now." She takes a step back, sliding her fingers through the sash of her robe before continuing. "My sanctuary is about offering refuge from worldly temptations rather than succumbing to them.
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("appreciate your boldness"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("takes a step back"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("My sanctuary"));
        Assert.DoesNotContain(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("takes a step"));
    }

    [Fact]
    public void Parse_QuotedSpeechWithAttribution()
    {
        string raw = "\"Of course,\" I say warmly as I tilt my head slightly in acknowledgment.";

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text == "Of course,");
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("I say warmly"));
    }

    [Fact]
    public void Parse_StripsUnlabeledSomaticAndActionBeatLabels()
    {
        string raw = """
            Yes, dance," I confirm with a warm smile as the gentle breeze carries whispers of jasmine to us.

            Somatic: Heart rate quickens at the thought of closeness and movement.
            Action beat: Rising from where I sit, extending a hand toward Anastasia as if inviting her to rise with me. "Shall we?
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains("Heart rate quickens", parsed.SomaticText);
        Assert.DoesNotContain("Somatic:", parsed.CanonicalDialogue);
        Assert.DoesNotContain("Action beat:", parsed.CanonicalDialogue);
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("Yes, dance"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("Shall we"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("Rising from where I sit"));
    }

    [Fact]
    public void Parse_StripsOpeningActionBeatLabelAndInterlocutor()
    {
        string raw = """
            [Somatic: Serena takes a deep breath, her chest expanding with warmth and lavender scent.]

            Opening action beat: "Your proposition is indeed intriguing," she begins slowly, eyes sparkling with intrigue as they lock onto yours. -
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains("takes a deep breath", parsed.SomaticText);
        Assert.DoesNotContain("lavender", parsed.SomaticText);
        Assert.DoesNotContain("Opening action beat", parsed.CanonicalDialogue);
        Assert.DoesNotContain("interlocutor", parsed.CanonicalDialogue);
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("intriguing"));
    }

    [Fact]
    public void Parse_RewritesThirdPersonSelfAndInterlocutor()
    {
        string raw = """
            Serena looks thoughtfully at the interlocutor from beneath heavy lids.
            "An intriguing proposition," she murmurs softly.
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.DoesNotContain("interlocutor", parsed.CanonicalDialogue);
        Assert.Contains("you", parsed.CanonicalDialogue);
        Assert.DoesNotContain(parsed.Segments, s => s.Text.StartsWith("Serena looks", StringComparison.Ordinal));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("intriguing proposition"));
    }

    [Fact]
    public void Parse_AsteriskActionThenSpeech()
    {
        string raw = "*gently traces a line from her nape* \"The night is calm.\"";

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("gently traces"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text == "The night is calm.");
    }

    [Fact]
    public void Parse_DropsCardZoneVocabularyDumpFromSomaticDisplay()
    {
        string raw = """
            [Somatic: Face/Eyes: steady ice-blue gaze; holds your face in both hands, Throat/Neck: voice slows and drops an octave, Chest/Breath: open posture, Hands/Arms: cupping face, Spine/Posture: dancer's fluidity, Feet/Staging: bare feet] "Very well," she responds. "This evening feels held."
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.True(DialogueSegmentParser.IsZoneVocabularyDump(parsed.SomaticTells));
        Assert.Equal("", parsed.SomaticText);
        Assert.DoesNotContain("Face/Eyes", parsed.CanonicalDialogue);
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("Very well"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Narration && s.Text.Contains("she responds"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("This evening"));
    }

    [Fact]
    public void Parse_StripsSpeakerPrefixAndFirstPersonMeta()
    {
        string raw = """
            Serena: [Serena's voice is warm, heavy gravity. She slowly opens her eyes.]
            "Very well," she responds in 1st person. "This evening... it feels like a dream."
            """;

        var parsed = DialogueSegmentParser.Parse(raw, "Serena");

        Assert.DoesNotContain("in 1st person", parsed.CanonicalDialogue, System.StringComparison.OrdinalIgnoreCase);
        Assert.False(parsed.CanonicalDialogue.StartsWith("Serena:", System.StringComparison.OrdinalIgnoreCase));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("Very well"));
        Assert.Contains(parsed.Segments, s => s.Kind == DialogueSegmentKind.Speech && s.Text.Contains("This evening"));
    }

    [Fact]
    public void Parse_PlayerQuestion_IsSpeech()
    {
        var segs = DialogueSegmentParser.Parse("Where did you hide the ledger?");
        Assert.Single(segs);
        Assert.Equal(DialogueSegmentKind.Speech, segs[0].Kind);
        Assert.Contains("ledger", segs[0].Text);
    }

    [Fact]
    public void FormatSomaticForDisplay_TruncatesLongProseTell()
    {
        string tell = string.Join(" ", Enumerable.Repeat("blush rises in her cheeks", 20));
        string display = DialogueSegmentParser.FormatSomaticForDisplay(new[] { tell });
        Assert.True(display.Length <= 181);
        Assert.EndsWith("…", display);
    }
}
