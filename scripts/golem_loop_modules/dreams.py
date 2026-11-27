"""Private dream opportunities and waking recall for one character's runtime."""
import json

from golem_time import sleep_stage
from golem_loop_modules.projection import message_text, resolve_relationship_target


def opportunity(connection, config, tick, authored):
    """Offer one scene per sustained sleep, including a sparsely sampled wake."""
    if "sleep_dream" in config:
        return None
    history = tick["next_history"]
    minutes = history["minutes_asleep"]
    previous = config["history"]
    if history["activity"] != "sleeping" and previous.get("activity") == "sleeping":
        minutes = previous.get("minutes_asleep", 0) + tick["golem_meta"]["elapsed_ms"] / 60000
    if minutes < 20:
        return None
    # A prior conversation can matter long after it leaves the active memory window.
    row = connection.execute("""SELECT input FROM events WHERE status='resolved'
        AND json_extract(input, '$.kind')='incoming' ORDER BY due DESC, rowid DESC LIMIT 1""").fetchone()
    seed = {}
    if row:
        event = json.loads(row[0])
        seed = {"event_id": event["id"], "speaker": resolve_relationship_target(event),
                "text": message_text(event)[:320]}
    # Promoted memories are character-selected material. Fall back to authored
    # log memories on installations without any in-turn promotions.
    saved = connection.execute("""SELECT id, kind, summary FROM memories
        WHERE kind IN ('detailed','footnote') ORDER BY rowid DESC LIMIT 1""").fetchone()
    memory = dict(saved) if saved else None
    if not memory:
        for kind in ("detailed", "footnote"):
            for entry in reversed(authored.get(kind) or []):
                if isinstance(entry, dict) and isinstance(entry.get("summary"), str):
                    memory = {"kind": kind, "summary": entry["summary"]}
                    break
            if memory:
                break
    if memory:
        memory["summary"] = memory["summary"][:320]
    return {
        "stage": sleep_stage(minutes),
        **({"conversation": seed} if seed else {}),
        **({"memory": memory} if memory else {}),
        "guidance": (
            "Imagine a private dream from this character's concerns, memories, goals, or bodily feelings. "
            "Return dream.scene in your decision. For an image retained on waking, add dream.fragment "
            "and dream.cues (a short list of recall words). For lingering affect, add dream.mood "
            "as one emotion mapped to an intensity from 1 to 100. Omit both for forgotten dreams. "
            "Keep imagined events in the dream field, separate from speech, actions and factual learning."
        ),
    }


def waking_trace(dream, event_id):
    """Validate the host-authored scene and retain only what can reach waking."""
    if not isinstance(dream, dict) or set(dream) - {"scene", "fragment", "cues", "mood"}:
        raise ValueError("dream must contain a scene and optional fragment, cues or mood")
    scene = dream.get("scene")
    if not isinstance(scene, str) or not 1 <= len(scene.strip()) <= 2000:
        raise ValueError("dream.scene requires 1–2000 characters")
    trace = {"event_id": event_id}
    if "fragment" in dream or "cues" in dream:
        fragment, cues = dream.get("fragment"), dream.get("cues")
        if not isinstance(fragment, str) or not 1 <= len(fragment.strip()) <= 320:
            raise ValueError("dream.fragment requires 1–320 characters")
        if not isinstance(cues, list) or not 1 <= len(cues) <= 8 or any(
            not isinstance(c, str) or not 1 <= len(c.strip()) <= 60 for c in cues
        ):
            raise ValueError("dream.cues requires 1–8 short recall words or phrases")
        trace.update(fragment=fragment.strip(), cues=sorted({c.strip().casefold() for c in cues}))
    if "mood" in dream:
        mood = dream["mood"]
        if not isinstance(mood, dict) or len(mood) != 1:
            raise ValueError("dream.mood requires one emotion and intensity")
        name, strength = next(iter(mood.items()))
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or type(strength) is not int or not 1 <= strength <= 100:
            raise ValueError("dream.mood requires an emotion name and integer intensity from 1 to 100")
        trace["mood"] = {name.strip(): strength}
    return trace


def recollection(trace):
    return {key: trace[key] for key in ("fragment", "mood") if key in trace}


def finish_turn(config, request, decision, memories):
    """Persist sleep and release the trace once, in the event's resolve transaction."""
    if "dream" in decision:
        if not request.get("dream_opportunity"):
            raise ValueError("dream requires a sleep opportunity on this turn")
        config["sleep_dream"] = waking_trace(decision["dream"], decision["id"])
    elif request.get("dream_opportunity"):
        config["sleep_dream"] = {}
    config.pop("waking_dream", None)
    # A waking message can be followed by a decision to go straight back to
    # sleep. Close the previous bout even in that case.
    started_awake = request["tick"]["next_history"].get("activity") != "sleeping"
    if started_awake or config["history"].get("activity") != "sleeping":
        trace = config.pop("sleep_dream", {})
        recall = recollection(trace)
        if not recall:
            return
        if not request.get("waking_dream"):
            config["waking_dream"] = {**recall, "at": request["at"]}
        if "mood" in trace and not request.get("waking_dream"):
            felt = config["history"].setdefault("felt_emotions", {})
            for name, strength in trace["mood"].items():
                felt[name] = max(strength, felt.get(name, 0))
        if "fragment" in trace:
            memories.append({"id": "dream:" + trace["event_id"], "kind": "dream",
                             "summary": "Dream fragment: " + trace["fragment"],
                             "reason": "Recalled on waking", "cues": trace["cues"]})
