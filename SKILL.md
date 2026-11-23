# Simulacra Runtime Skill

## Responsibility boundary

- Golem computes deterministic bodily state and action consequences.
- Simulacra interprets needs with the character card, goals, personality, commitments, and context, then chooses an action or postpones it.
- The host checks capabilities and real resources, executes selected actions, and persists decisions through the runtime.
- A need threshold requests cognitive evaluation; it never forces the character to eat, sleep, or stop working.

The `attraction` stimulus is a short-lived situational appraisal used for immediate response. It decays after the event. Enduring relationship attraction is the target-specific `relational_baselines` bond field and is not modified by elapsed time. The host/Simulacra layer updates it only after a qualifying interpreted relationship event.

## Supported execution modes

Run commands from any working directory; resolve paths from this installed directory (the directory containing this file). Keep each character's SQLite database and YAML log in persistent host storage.

### Native Python

When Python 3 and PyYAML are available, invoke the shared runtime directly:

```sh
python3 /absolute/path/to/Simulacra/scripts/run.py golem loop --db /persistent/character.sqlite3 init --card /persistent/card.yaml --log /persistent/log.yaml
python3 /absolute/path/to/Simulacra/scripts/run.py golem loop --db /persistent/character.sqlite3 status
```

On Windows, use `python` or the installed Python launcher (`py -3`) in place of `python3`.

### CLI wrapper

The `scripts/run.py` entry point is a Python CLI wrapper. It locates platform wrappers and Python core files relative to its own installation path; it does not require the caller's current directory to be Simulacra. Unix shell and Windows PowerShell/CMD wrappers are convenience launchers around the shared Python implementation. They are not independent Golem runtimes.

Hosts that cannot invoke Python may call this CLI only if they can launch its interpreter/wrapper and capture JSON stdout. If no compatible interpreter or process-launch capability exists, the runtime cannot execute locally: report that capability failure. Do not ask an LLM to invent Golem snapshots or state transitions. An independently executable non-Python runtime is not currently provided.

The Golem and loop commands return JSON objects on stdout. Errors go to stderr and return a nonzero exit status. Use `golem --card ... --stimulus '<JSON>'` for a stateless diagnostic tick; use the persistent loop for character runtime state. The standalone tick does not provide idempotent multi-host scheduling.

## Persistent host loop

Initialize one database per character. On incoming turns and scheduled heartbeats, invoke `scripts.golem_loop.wake_character(db_path, decide, compact=True, event=optional_event)`. `decide(request)` must run the Simulacra cognitive decision process and return the same event ID. The compact request carries computed `emotions`, current bodily cues, motivations, goals, recent events, and `maintenance_needs` (hunger, fatigue, sleep debt, activity, and an evaluation hint).

Maintenance handoff:

1. Treat the request's bodily numbers as needs and consequences, not a command. Decide whether to eat, drink if the host models hydration, rest, sleep, wake, continue work, or do something else.
   When repetition is detected, use the recent pattern and the character's own motives to decide whether to repeat the behavior. Choose the voice from the supplied identity anchor and dialect.
2. Check actual host-provided resources and constraints before representing an action as executable. Never claim food or water exists based on Golem state.
3. Record the chosen action in `decision.action` and the bodily result in `decision.experience.stimulus`. For a completed meal, for example, `{"food_intake": 30}` reduces hunger by 30 points. If the character postpones food, omit intake; elapsed time continues to affect hunger.
4. Represent a duration with the structured `decision.activity` operation: `start` stores its ID, kind, state, start time, duration, and optional completion effects in SQLite and schedules one due event. At the due event, Simulacra chooses `complete`, `extend`, or (when interrupted before due) `interrupt`; a later decision may `resume` an interrupted activity. Activity state transitions and Golem consequences commit in the same transaction. Each tick calculates recovery over elapsed time, so sleep does not need repeated LLM calls. See [Muse.AI/SKILL.md](Muse.AI/SKILL.md) for JSON examples.
5. Use stable event IDs. The SQLite loop stores pending requests before host work, deduplicates identical enqueues/resolutions, and leaves interrupted host callbacks pending for restart retry. Do not replay effects outside the loop without deduplicating by event ID.

The host owns any scheduler/heartbeat. A plan only runs when `wake_character` or `golem loop run` is called at/after its due time. For a command-line host, `golem loop run --once` is suitable for a scheduler. Failed resource checks should be returned in the character decision context/outcome so Simulacra can reconsider.

## Time and calibration

Loop time is timezone-aware elapsed wall-clock time between persisted event timestamps. Standalone ticks accept `elapsed_ms` or legacy `elapsed_minutes`. Body rates use simulated hours, and one Golem tick applies at most 24 hours of hunger/fatigue/sleep-debt progression to bound restart gaps. Defaults: hunger +4/hour awake and +2/hour asleep; fatigue +0.8/hour awake plus +0.04/hour per exertion point, recovery 2/hour resting and 5/hour sleeping; sleep debt +1.5/hour awake, +0.5/hour resting, and recovery 12/hour sleeping. Meals subtract the supplied 0–100 `food_intake` score. Cards may override these defaults under `physiology_calibration`.

Time is advanced by the loop once per persisted event. Post-decision appraisal and consequences are applied at that same timestamp and do not advance the event clock again. Do not pass explicit elapsed time into a timestamped loop event.

## Example host decision

```python
from scripts.golem_loop import wake_character

def decide(request):
    # Run the Simulacra cognitive pipeline here; resource availability must
    # come from the host environment, not from Golem.
    return {"id": request["event"]["id"]}

result = wake_character(db_path, decide, compact=True)
```

This no-action callback demonstrates transport only. A host must supply the actual cognitive pipeline for autonomous behavior.
