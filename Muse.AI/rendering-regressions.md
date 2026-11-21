# Muse rendering regressions

Use these as host-rendering checks. The quoted prose is illustrative; the runtime must use the active character's voice and the actual `tick` and cognitive choices. These examples do not change Golem calculations.

## Dialogue-only

**Input:** The character receives an ordinary greeting. Current `Feels` contains no materially relevant pressure, `emitted_cues` is empty or irrelevant, `Thinks` has no consequential subtext, and `Does` selects no action.

**Expected rendering:** “Morning. How did the trip go?”

Do not append a posture change or a past somatic cue simply to make the response embodied. Dialogue alone is valid.

## Fatigue influences delivery

**Input:** Current `Feels` indicates significant fatigue; current cues include a slackened posture. `Thinks` decides the character will finish the exchange but not begin another task. `Says` selects a brief, tired answer. `Does` deliberately sets the papers aside.

**Expected rendering:** She lowers the papers and answers after a slower breath. “I can pick this up tomorrow.”

Fatigue shapes pace and posture, without narrating the numeric score or forcing sleep. The act of setting the papers down is deliberate because it came from `Does`.

## Hunger influences behavior

**Input:** Current `Feels` indicates hunger that distracts from the conversation. `Thinks` weighs the conversation against the need to eat. `Says` chooses to postpone the discussion. No food resource has been confirmed by the host.

**Expected rendering:** Her attention slips for a moment, then returns to the question. “Can we come back to this after I eat?”

Do not claim she sees, reaches for, or eats food unless the scene and host confirm it. Hunger informs the choice; it does not force it.

## Involuntary response versus deliberate action

**Input:** `autonomic_state.involuntary_response` is `brace`. `Feels` reports the reflex. `Thinks` registers the sudden pressure. `Says` selects a short boundary. `Does` selects no additional movement.

**Expected rendering:** Her shoulders tense before she can decide to move. “Wait.”

The brace is already underway and is not described as a chosen gesture. Do not add a deliberate step, touch, or repeated motion that `Does` did not select.

## Current cue versus history

If `tick.next_history.recent_cues` contains “echo other's speech” from an earlier tick but the current `tick.golem_meta.emitted_cues` does not, do not render an echo in this event. History supports continuity and cue rotation; it is not a record of a current action.

## Acceptance checks

- Bodily state changes expression or action only when relevant to this event.
- Numeric scales and framework labels stay out of character-facing prose.
- Not every emitted cue appears in the reply; cues inform rendering rather than dictate it.
- `Thinks` stays private unless intentionally expressed.
- A reflex is not attributed as a deliberate choice.
- The accepted `decision.reply` is delivered unchanged after resolution.
