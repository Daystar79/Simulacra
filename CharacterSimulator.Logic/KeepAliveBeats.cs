using System;

namespace CharacterSimulator.Logic;

/// <summary>
/// Idle-life cues and delay ranges for keep-alive turns.
/// Cues are written as scene direction the model should inhabit — never as player speech.
/// </summary>
public static class KeepAliveBeats
{
    public const int DefaultMinSeconds = 15;
    public const int DefaultMaxSeconds = 120;
    public const int DefaultMaxIdleBeats = 4;

    public static readonly string[] Cues =
    {
        "A quiet stretch of time passes. Stay in the room.",
        "Notice something small in the space or in your body.",
        "The other person is still present but silent. Do not ask if they are there.",
        "A small unprompted action that fits who you are — not a recap of what already happened.",
        "Shift, breathe, or let a thought leak into a glance. Spoken words are optional.",
        "Attend to the scene as if you live here. Do not wait to be addressed.",
    };

    public static string PickCue(Random rng)
    {
        if (rng == null) throw new ArgumentNullException(nameof(rng));
        return Cues[rng.Next(Cues.Length)];
    }

    public static TimeSpan PickDelay(Random rng, int minSeconds, int maxSeconds)
    {
        if (rng == null) throw new ArgumentNullException(nameof(rng));
        ClampRange(ref minSeconds, ref maxSeconds);
        return TimeSpan.FromSeconds(rng.Next(minSeconds, maxSeconds + 1));
    }

    public static void ClampRange(ref int minSeconds, ref int maxSeconds)
    {
        if (minSeconds < 4) minSeconds = 4;
        if (minSeconds > 180) minSeconds = 180;
        if (maxSeconds < minSeconds) maxSeconds = minSeconds;
        if (maxSeconds > 300) maxSeconds = 300;
    }

    public static int ClampMaxIdleBeats(int value)
    {
        if (value < 1) return 1;
        if (value > 12) return 12;
        return value;
    }
}
