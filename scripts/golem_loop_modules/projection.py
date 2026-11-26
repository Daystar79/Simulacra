"""Host decision-context projection, repetition signals, and rendering guidance."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import golem  # noqa: E402
from golem_loop_modules.db import character_database  # noqa: E402


def message_text(event):
    """Read the utterance from the current transport field or an older alias."""
    for value in (event.get("text"), event.get("message"), (event.get("stimulus") or {}).get("text"),
                  event.get("context")):
        if isinstance(value, str) and value.strip():
            return value
    return ""


def resolve_relationship_target(event, stimulus=None):
    """Extract a relationship target from event.relationship_target or stimulus.caller_or_target."""
    if isinstance(event, dict):
        explicit = event.get("relationship_target")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
    stim = stimulus if isinstance(stimulus, dict) else (event.get("stimulus") if isinstance(event, dict) else None)
    if isinstance(stim, dict):
        caller = stim.get("caller_or_target")
        if isinstance(caller, str) and caller.strip() and caller.strip() != "caller":
            return caller.strip()
    return None


def compact_recent_events(events, older_limit=None):
    """Decision-context projection; the complete event ledger remains in SQLite.

    With ``older_limit``, every entry except the most recent one has its
    history-bearing text (context, text, action, outcome, reply) capped at that
    many characters, since the projection already flags verbatim repetition
    separately and the current turn is the one the host must read in full.
    """
    compact = []
    for index, entry in enumerate(events):
        event, decision = entry.get("event") or {}, entry.get("decision") or {}
        item = {"id": event.get("id"), "kind": event.get("kind"), "at": entry.get("at"),
                "status": entry.get("status")}
        target = resolve_relationship_target(event)
        if target:
            item["relationship_target"] = target
        if event.get("topic"):
            item["topic"] = event["topic"]
        limit = 320 if older_limit is None or index == len(events) - 1 else older_limit
        utterance = message_text(event)
        context = event.get("context") or utterance
        if context:
            item["context"] = context[:limit]
        if utterance and utterance != context:
            item["text"] = utterance[:limit]
        for key in ("action", "outcome", "reply"):
            if isinstance(decision.get(key), str) and decision[key]:
                item[key] = decision[key][:limit]
        assessment = entry.get("assessment") or {}
        for key in ("topic", "forecast", "observed", "next_expectation"):
            if key in assessment:
                item[key] = assessment[key]
        compact.append(item)
    return compact


def repeated_action_pattern(events, window=5):
    """Describe consecutive duplicate actions without changing or rejecting them."""
    actions = [
        re.sub(r"\W+", " ", (entry.get("decision") or {}).get("action", "").casefold()).strip()
        for entry in events[-window:]
    ]
    actions = [action for action in actions if action]
    if len(actions) < 2:
        return {"repeated": False, "consecutive_count": 0}
    count = 1
    for action in reversed(actions[:-1]):
        if action != actions[-1]:
            break
        count += 1
    return {"repeated": count >= 2, "consecutive_count": count,
            **({"action": actions[-1]} if count >= 2 else {})}


def repeated_reply_pattern(events, window=5):
    """Flag consecutive duplicate reply openers/somatic beats or user-echoing."""
    replies = []
    for entry in events[-window:]:
        reply = (entry.get("decision") or {}).get("reply")
        if isinstance(reply, str) and reply.strip():
            replies.append((reply.strip(), entry.get("event") or {}))
    if not replies:
        return {"repeated_opener": False, "consecutive_count": 0, "echoing_user": False}

    def opener_key(text):
        stage = re.match(r"^\*([^*]+)\*", text)
        if stage:
            return re.sub(r"\W+", " ", stage.group(1).casefold()).strip()
        words = re.findall(r"[a-z0-9']+", text.casefold())[:4]
        return " ".join(words)

    openers = [opener_key(text) for text, _ in replies]
    count = 1
    if len(openers) >= 2 and openers[-1]:
        for key in reversed(openers[:-1]):
            if key != openers[-1]:
                break
            count += 1

    latest_reply, latest_event = replies[-1]
    user_text = message_text(latest_event)
    user_words = {w for w in re.findall(r"[a-z0-9']+", user_text.casefold()) if len(w) >= 4}
    reply_head_words = re.findall(r"[a-z0-9']+", latest_reply.casefold())[:16]
    echoing = False
    if len(user_words) >= 3 and reply_head_words:
        overlap = user_words.intersection(reply_head_words)
        echoing = len(overlap) / len(user_words) >= 0.6

    return {
        "repeated_opener": count >= 2,
        "consecutive_count": count if count >= 2 else 0,
        **({"opener": openers[-1]} if count >= 2 else {}),
        "echoing_user": echoing,
    }


def expression_guidance(snapshot, medium=None):
    """Translate measured body constraints into options for the host's rendering."""
    body = snapshot["autonomic_state"]
    telemetry = body.get("somatic_telemetry")
    if not telemetry:  # Older pending snapshots can finish on the previous contract.
        return None
    if body.get("activity") == "sleeping":
        return "Use the sleeping posture and breathing. Deliberate gaze, speech and approach require waking."
    # Each tick carries the current interlocutor's vector only.
    bond = next(iter(snapshot.get("relational_vectors", {}).values()), {})
    if body.get("involuntary_response") == "freeze":
        cue = "Let stillness or a delayed answer carry the moment."
    elif telemetry["postural_bracing"] >= 40:
        cue = "Consider a held stance, a delayed step, or the effort it takes to sustain eye contact."
    elif telemetry["energy_expenditure"] >= 40 or telemetry["register_shift"] >= 56:
        cue = "Consider where breath interrupts a phrase or effort shifts the speaker’s usual register."
    elif bond.get("emotional_safety", 50) < 35:
        cue = "Consider preserving distance, looking back to the task, or letting a question go unanswered."
    elif body.get("lingering_arousal"):
        cue = "Residual warmth can stay private while attention returns to the current topic or task."
    elif telemetry["peripheral_perfusion"] >= 62 and bond.get("intimacy", 0) >= 50:
        cue = "If closeness is welcome in this scene, consider staying within reach or letting eye contact linger."
    elif telemetry["peripheral_perfusion"] >= 62:
        cue = "Consider whether warmth is felt privately or becomes visible in the scene."
    else:
        cue = "An ordinary pause or an unremarked movement can be enough."
    if medium == "text":
        if body.get("involuntary_response") == "freeze" or telemetry["postural_bracing"] >= 40:
            cue = "In text, pressure might shorten an answer or leave the message unanswered."
        elif bond.get("emotional_safety", 50) < 35:
            cue = "Keep private details off the page if the character would answer only the practical question."
        else:
            cue = "In text, a specific remembered detail or a second question can carry interest when it fits."
    elif medium == "voice":
        if telemetry["energy_expenditure"] >= 40 or telemetry["register_shift"] >= 56:
            cue = "On a voice call, breath may break a phrase early or shift its pitch."
        else:
            cue = "On a voice call, use a pause, a change of subject, or an unhurried reply if it fits."
    if snapshot.get("affective_state", {}).get("emotions", {}).get("pleasure", 0) >= 40:
        cue += " If enjoyment matters here, let it show in what the character savors or returns to."
    if body.get("physical_pleasure", 0) >= 40:
        cue += " Bodily comfort may show in how the character settles into the current activity."
    if body.get("sexual_pleasure", 0) >= 40:
        cue += " Sexual enjoyment is private. The character chooses whether to communicate it."
    if body.get("orgasm"):
        cue += " A brief involuntary peak may interrupt a movement or breath. Choose what is perceptible here."
    elif body.get("orgasm_recovery"):
        cue += " Let the recovery affect pacing only as far as the character and scene warrant."
    if body.get("lingering_arousal"):
        cue += " Carryover can outlast its original cue or listener. Let the current relationship and purpose guide the reply."
    return (cue + " Choose at most one salient beat, or leave it private. Use only cues the listener "
            "could perceive. Decide what the character would say or leave "
            "unsaid. For welcome flirting or affection, let a particular action carry the subtext. "
            "Use a pet name only when established for this speaker and listener. "
            "A bodily response alone establishes neither intent nor consent.")


def intimacy_render(request, profile):
    """Resolve a host's depiction ceiling using only card identities and ages."""
    fallback = {"depiction": "sfw"}
    event = request["event"]
    mode = event.get("depiction")
    if mode not in ("fade_to_black", "explicit"):
        return fallback
    roster = event.get("scene_characters")
    tick = request["tick"]
    if "ADULT_GATE:ELIGIBLE" not in tick.get("golem_meta", {}).get("triggered_rules", []):
        return fallback
    snapshot = tick["psychosomatic_snapshot"]
    source = request["character"]
    actor = source.get("slug") or snapshot["character_id"]
    if not isinstance(roster, list) or actor not in roster or not all(isinstance(key, str) for key in roster):
        return fallback
    target = resolve_relationship_target(event)
    if target and target not in roster:
        return fallback
    try:
        card_path = Path(source["card"])
        pack = yaml.safe_load(card_path.read_text(encoding="utf-8"))
        actor_card, location = golem.selected_card(pack, source.get("slug"))
        if location and location[-1] != actor:
            return fallback
        card_id = actor_card.get("character_id")
        if (profile or card_id is not None) and card_id != snapshot["character_id"]:
            return fallback
        if not golem.canon_adult(actor_card):
            return fallback
        for key in set(roster):
            if key == actor:
                continue
            if profile:
                path = character_database(card_path.parent.parent, key).with_name("character.yaml")
                if path.resolve() != path or path.stat().st_nlink != 1:
                    return fallback
                card = golem.load_character(path, None)
                if card.get("character_id") != key:
                    return fallback
            else:
                if not location:
                    return fallback
                card = pack["characters"].get(key)
            if not isinstance(card, dict) or not golem.canon_adult(card):
                return fallback
        module = "Framework/Mechanics/erotica.md"
        registry = yaml.safe_load((golem.ROOT / "Framework/modules.yaml").read_text(encoding="utf-8")) or {}
        for entry in registry.get("modules", []):
            if (isinstance(entry, dict)
                    and entry.get("path") == module
                    and entry.get("status") == "ENABLED"
                    and "app_render" in (entry.get("hooks") or [])):
                return {"depiction": mode, "guide": (golem.ROOT / module).read_text(encoding="utf-8")}
    except (OSError, ValueError, yaml.YAMLError):
        pass
    return fallback


def pending_request(connection):
    row = connection.execute("SELECT request FROM events WHERE status = 'pending'").fetchone()
    if not row:
        return None
    request = json.loads(row["request"])
    owner, profile = connection.execute(
        "SELECT json_extract(data,'$.character_id'), json_extract(data,'$.profile') FROM runtime WHERE id=1"
    ).fetchone()
    if owner:
        snapshot_id = request["tick"]["psychosomatic_snapshot"]["character_id"]
        if snapshot_id != owner:
            raise ValueError("Pending tick belongs to a different character")
        request["character_id"] = owner
    if profile:
        directory = Path(connection.execute("PRAGMA database_list").fetchone()["file"]).parent
        request["character"] = {"card": str(directory / "character.yaml"),
                                "log": str(directory / "character_log.yaml"), "slug": None}
    if request["event"]["kind"] == "incoming":
        request["reply_guidance"] = {
            "stance": (
                "What does the speaker claim, and what does the character already believe or know? "
                "Acknowledge the speaker's experience in character. Agree where it fits, keep any "
                "difference, and revise a belief only as far as the new evidence warrants."
            ),
            "disclosure": (
                "What has this listener actually heard or witnessed? Treat host_notes and recalled "
                "memories as private. Check remembered details against the card and established events. "
                "Choose what this character has reason to reveal to this listener now. A memory may "
                "affect the reply while every identifying detail stays private."
            ),
        }
        if request.get("relationship_state"):
            request["reply_guidance"]["relationship"] = (
                "Consider what this character has learned about this speaker when choosing whether "
                "to confide, challenge, help, or keep their distance. Weigh it alongside the present "
                "exchange and the character's own goals."
            )
    if "depiction" in request["event"]:
        request["app_render"] = intimacy_render(request, profile)
        request["event"]["depiction"] = request["app_render"]["depiction"]
    guidance = expression_guidance(request["tick"]["psychosomatic_snapshot"], request["event"].get("medium"))
    if guidance:
        request["expression_guidance"] = guidance
    return request


def decision_context(request):
    """Project the saved tick into the values a character needs for one decision."""
    tick = request["tick"]
    snapshot = tick["psychosomatic_snapshot"]
    affect = snapshot["affective_state"]
    body = snapshot["autonomic_state"]
    event = request["event"]
    # Keep transport context, including host-defined scene fields, outside the
    # physiological inputs. Some older hosts put the utterance in stimulus.text.
    scene = {key: value for key, value in event.items() if key != "stimulus"}
    stimulus = event.get("stimulus", {})
    for key in ("text", "caller_or_target", "conversation"):
        if key in stimulus:
            scene.setdefault(key, stimulus[key])
    recent = request.get("recent", [])
    if recent and "event" in recent[0]:
        recent = compact_recent_events(recent, older_limit=120)
    emotions = affect.get("emotions")
    if emotions is None:  # Pending ticks from before concurrent emotions.
        emotions = {affect["primary_emotion"]: affect["emotional_intensity"]}
    # At-rest projection: a body value sent at its resting constant adds no
    # guidance a host can act on, so `0`, `false`, and `none` are omitted and
    # an absent field means the resting value. `activity` always names the
    # current activity. The full snapshot in the stored request is unchanged.
    body = {key: body[key] for key in (
        "cognitive_regime", "involuntary_response", "stress", "arousal",
        "sexual_arousal", "lingering_arousal", "physical_pleasure", "sexual_pleasure",
        "orgasm", "orgasm_recovery", "somatic_map", "somatic_telemetry", "emotional_distress", "activity",
    ) if key in body}
    context_body = {"activity": body["activity"]} if "activity" in body else {}
    for key, value in body.items():
        if key != "activity" and value not in (0, False, None, "none", {}):
            context_body[key] = value
    context = {
        "event": scene, "at": request["at"], "emotions": emotions,
        "body": context_body,
        "current_cues": tick.get("golem_meta", {}).get("emitted_cues", []),
        "winning_drive": snapshot["priority_arbitration"]["winning_drive"],
        "arbitration_status": snapshot["priority_arbitration"]["arbitration_status"],
        "mask": snapshot.get("social_mask", {}),
        "relational_vectors": snapshot.get("relational_vectors", {}),
        "recent": recent,
    }
    for key in ("initiative", "impulse"):
        if key in affect:
            context[key] = affect[key]
    for key in ("character_id", "identity_anchor", "dialect", "current_goals", "motivations", "incentives",
                "recalled_memories", "learned", "activity", "maintenance_needs", "expectations",
                "situational_expectations", "relationship_state", "reply_guidance", "expression_guidance", "app_render"):
        if request.get(key):
            context[key] = request[key]
    if "identity_anchor" not in context:
        context["character"] = request["character"]
    if "conversation_intent" in tick:
        context["conversation_intent"] = tick["conversation_intent"]
    guidance = request.get("behavior_guidance", {})
    for key in ("recent_action_pattern", "recent_reply_pattern"):
        pattern = guidance.get(key, {})
        if any(pattern.get(flag) for flag in ("repeated", "repeated_opener", "echoing_user")):
            context[key] = pattern
    return context


STATIC_PREFIX_KEYS = (
    "character_id",
    "identity_anchor",
    "character",
    "dialect",
    "motivations",
    "incentives",
    "current_goals",
)


def prompt_cache_split(request):
    """Partition a decision context into an immutable KV-cache prefix and per-turn suffix.

    ``static_prefix`` contains only slow-changing identity and configuration fields
    with no timestamps, body telemetry, or rolling history, so its serialized JSON
    and ``prefix_hash`` stay byte-identical across turns for LLM KV/prefix caching.
    ``dynamic_turn`` holds the compact per-turn state to send after the cached prefix.
    """
    context = decision_context(request) if "tick" in request else dict(request)
    static_prefix = {key: context[key] for key in STATIC_PREFIX_KEYS if key in context}
    dynamic_turn = {key: value for key, value in context.items() if key not in STATIC_PREFIX_KEYS}
    canonical_prefix = json.dumps(static_prefix, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    prefix_hash = hashlib.sha256(canonical_prefix.encode("utf-8")).hexdigest()
    return {
        "prefix_hash": prefix_hash,
        "static_prefix": static_prefix,
        "dynamic_turn": dynamic_turn,
    }
