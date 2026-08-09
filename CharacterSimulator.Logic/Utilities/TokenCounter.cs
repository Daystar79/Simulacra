using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CharacterSimulator.Logic.Utilities;

/// <summary>
/// Simple token counter for estimating token counts in text.
/// Uses a basic heuristic: count words + punctuation as rough token estimate.
/// For more accurate counting, models should use their native tokenizers.
/// </summary>
public static class TokenCounter
{
    // Common token patterns to split on (simplified wordpiece-like tokenization)
    private static readonly char[] WordSeparators = new[]
    {
        ' ', '\t', '\n', '\r',
        '.', ',', '!', '?', ';', ':',
        '"', '\'', '(', ')', '[', ']', '{', '}',
        '-', '_', '/', '\\',
        '(', ')', '<', '>',
        '|', '&', '*', '+', '=', '~', '`',
        '$', '%', '#', '@',
    };

    private static readonly HashSet<string> CommonPunctuation = new HashSet<string>
    {
        ".", ",", "!", "?", ";", ":", "'", "\"", "(", ")", "[", "]", "{", "}",
        "-", "_", "/", "\\", "|", "&", "*", "+", "=", "~", "`",
        "$", "%", "#", "@"
    };

    /// <summary>
    /// Estimates the number of tokens in text using a simple heuristic.
    /// This is NOT as accurate as model-specific tokenizers but works for rough estimates.
    /// </summary>
    public static int EstimateTokenCount(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
            return 0;

        // Simple estimate: split on whitespace and common punctuation
        var tokens = new List<string>();
        var current = new StringBuilder();
        
        foreach (char c in text)
        {
            if (WordSeparators.Contains(c))
            {
                if (current.Length > 0)
                {
                    tokens.Add(current.ToString());
                    current.Clear();
                }
                // Add punctuation as separate tokens
                if (!char.IsWhiteSpace(c))
                {
                    tokens.Add(c.ToString());
                }
            }
            else
            {
                current.Append(c);
            }
        }
        
        if (current.Length > 0)
        {
            tokens.Add(current.ToString());
        }

        return tokens.Count;
    }

    /// <summary>
    /// Estimates the number of tokens using a character-based ratio.
    /// Approximation: 1 token ≈ 4 characters for English text.
    /// This is faster but less accurate than word-based estimation.
    /// </summary>
    public static int EstimateTokenCountFast(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
            return 0;
        
        // Rough estimate: 1 token ≈ 4 characters (English text average)
        // This varies by language and content type
        return text.Length / 4;
    }

    /// <summary>
    /// Checks if the prompt is within the model's context limit.
    /// Returns true if the prompt is within limits, false if it exceeds.
    /// </summary>
    public static bool IsWithinContextLimit(string prompt, int contextSize, int reservedForResponse = 512)
    {
        if (string.IsNullOrWhiteSpace(prompt))
            return true;

        int estimatedTokens = EstimateTokenCountFast(prompt);
        return estimatedTokens + reservedForResponse <= contextSize;
    }

    /// <summary>
    /// Truncates the prompt to fit within the context limit, preserving system identity at start and user turn + trigger tag at end.
    /// </summary>
    public static string TruncateToContextLimit(string prompt, int contextSize, int reservedForResponse = 512)
    {
        if (string.IsNullOrWhiteSpace(prompt))
            return prompt;

        int availableForPrompt = contextSize - reservedForResponse;
        if (availableForPrompt <= 256)
            availableForPrompt = 256;

        int estimatedTokens = EstimateTokenCountFast(prompt);
        if (estimatedTokens <= availableForPrompt)
            return prompt;

        int maxChars = availableForPrompt * 4;
        if (prompt.Length <= maxChars)
            return prompt;

        // Find where user turn or situation block starts to preserve head and tail
        int userBlockIdx = -1;
        string[] userMarkers = new[] { "<|im_start|>user", "<|start_header_id|>user", "### Instruction:", "CONVERSATION SO FAR", "SITUATION:" };
        foreach (var marker in userMarkers)
        {
            int idx = prompt.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (idx > 0)
            {
                userBlockIdx = idx;
                break;
            }
        }

        if (userBlockIdx > 0 && userBlockIdx < prompt.Length)
        {
            string head = prompt[..userBlockIdx];
            string tail = prompt[userBlockIdx..];

            int headTarget = maxChars / 2;
            int tailTarget = maxChars - headTarget;

            string truncatedHead = head.Length > headTarget ? head[..headTarget].TrimEnd() + "\n..." : head;
            string truncatedTail = tail.Length > tailTarget ? "..." + tail[^tailTarget..].TrimStart() : tail;

            return truncatedHead + "\n" + truncatedTail;
        }

        // Fallback: keep head & tail equally, preserving completion trigger tag at the end
        int half = maxChars / 2;
        string startPart = prompt[..half].TrimEnd();
        string endPart = prompt[^half..].TrimStart();
        return startPart + "\n...\n" + endPart;
    }

    /// <summary>
    /// Simple cache for token counts to avoid re-counting the same prompts.
    /// </summary>
    private static readonly Dictionary<string, int> TokenCountCache = new Dictionary<string, int>();
    private static readonly object CacheLock = new object();

    /// <summary>
    /// Gets the cached token count for a prompt, or estimates it if not cached.
    /// </summary>
    public static int GetCachedTokenCount(string prompt)
    {
        if (string.IsNullOrWhiteSpace(prompt))
            return 0;

        lock (CacheLock)
        {
            if (TokenCountCache.TryGetValue(prompt, out int cached))
                return cached;

            int count = EstimateTokenCountFast(prompt);
            TokenCountCache[prompt] = count;
            return count;
        }
    }

    /// <summary>
    /// Clears the token count cache.
    /// </summary>
    public static void ClearCache()
    {
        lock (CacheLock)
        {
            TokenCountCache.Clear();
        }
    }

    /// <summary>
    /// Gets the number of cached entries.
    /// </summary>
    public static int CacheCount
    {
        get
        {
            lock (CacheLock)
            {
                return TokenCountCache.Count;
            }
        }
    }
}
