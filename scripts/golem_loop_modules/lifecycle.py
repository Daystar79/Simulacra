"""Event queue, body tick execution, post-decision appraisal, and turn resolution."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import golem  # noqa: E402
from golem_logs import mirror_memories
import goal_evolution  # noqa: E402
import relationship_memory  # noqa: E402
from golem_loop_modules import dreams, recall
from golem_loop_modules.activities import active_activity, apply_activity_decision  # noqa: E402
from golem_loop_modules.cache import (  # noqa: E402
    build_identity_anchor,
    cached_identity,
    extract_memory_cues,
    load_cached_character,
    runtime_config,
)
from golem_loop_modules.db import ensure_activity_schema, pending_log_entries  # noqa: E402
from golem_loop_modules.learning import (  # noqa: E402
    RECENT_LIMIT,
    contextual_forecast,
    expectation_dimensions,
    next_expectation,
    recall_past_episodes,
    recall_stored_memories,
    record_contextual_expectation,
    relevant_expectations,
    relevant_learned_observations,
    scores,
    topic_key,
)
from golem_loop_modules.projection import (  # noqa: E402
    compact_recent_events,
    repeated_action_pattern,
    repeated_reply_pattern,
    resolve_relationship_target,
)

ACTIVE_MEMORY_WINDOW_SECONDS = 2 * 60 * 60


def enqueue(connection, event, history, now, *, actor_id=None):
    if "character_id" in event:
        config = runtime_config(connection)
        owner = config.get("character_id") or cached_identity(connection)
        if event["character_id"] != owner:
            raise ValueError("Event character ID does not match the selected database")
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip() or event_id.startswith("idle:"):
        raise ValueError("Event id must be nonempty and cannot begin with idle:")
    if event.get("kind") not in ("incoming", "plan", "world"):
        raise ValueError("Event kind must be incoming, plan, or world")
    stimulus = event.get("stimulus", {})
    if not isinstance(stimulus, dict) or {"event_at", "elapsed_ms", "elapsed_minutes"} & stimulus.keys():
        raise ValueError("Use the event's at field for timing, outside stimulus")
    if not isinstance(event.get("context", ""), str):
        raise ValueError("Event context must be text")
    if "host_notes" in event and not isinstance(event["host_notes"], str):
        raise ValueError("Event host_notes must be text")
    if "expectation" in event:
        topic_key(event.get("topic"))
        scores(event["expectation"])
    if "topic" in event:
        topic_key(event["topic"])
    existing = connection.execute("SELECT input FROM events WHERE id = ?", (event_id,)).fetchone()
    saved = json.loads(existing["input"]) if existing is not None else None
    # An exact replay of a pre-migration event retains its original speaker routing.
    if saved != event and actor_id is not None and event["kind"] == "incoming" and not resolve_relationship_target(event):
        event = {**event, "relationship_target": relationship_memory.validate_target(actor_id)}
    if existing is not None:
        if saved != event:
            raise ValueError(f"Event ID already exists with different contents: {event_id}")
        return {"id": event_id, "queued": False}
    if "expectation_context" in event:
        expectation_dimensions(event)
    if event["kind"] == "plan" and "at" not in event:
        raise ValueError("A plan requires an at timestamp")
    due = golem.parse_event_time(event["at"]) if "at" in event else now
    last = history.get("last_event_at")
    if last and due < golem.parse_event_time(last):
        raise ValueError("Event is earlier than the last processed tick")
    connection.execute(
        "INSERT INTO events (id, due, input) VALUES (?, ?, ?)",
        (event_id, due.timestamp(), json.dumps(event)),
    )
    return {"id": event_id, "queued": True}


def recent_events(connection, limit=RECENT_LIMIT, since_timestamp=None):
    query = """SELECT input, due, decision, status, json_extract(request, '$.assessment') AS assessment,
                  json_extract(request, '$.body_response') AS body_response FROM events
           WHERE status IN ('resolved', 'failed')"""
    params: list[Any] = []
    if since_timestamp is not None:
        query += " AND due >= ?"
        params.append(since_timestamp)
    query += " ORDER BY due DESC, rowid DESC LIMIT ?"
    params.append(limit)
    rows = connection.execute(query, params).fetchall()
    return [
        {
            "event": json.loads(row["input"]), "at": datetime.fromtimestamp(row["due"], timezone.utc).isoformat(),
            "decision": json.loads(row["decision"]), "status": row["status"],
            **({"assessment": json.loads(row["assessment"])} if row["assessment"] else {}),
            **({"body_response": json.loads(row["body_response"])} if row["body_response"] else {}),
        }
        for row in reversed(rows)
    ]


def body_tick(config, stimulus, event=None, connection=None, *, relationship_target=None):
    state, card, durable = load_cached_character(config, connection)
    effective_stimulus = dict(stimulus)
    if (config["history"].get("activity") == "sleeping"
            and effective_stimulus.get("activity", "sleeping") != "sleeping"):
        mood = config.get("sleep_dream", {}).get("mood")
        if mood and isinstance(effective_stimulus.get("emotions", {}), dict):
            effective_stimulus["emotions"] = {**mood, **effective_stimulus.get("emotions", {})}
    rel_target = relationship_target or resolve_relationship_target(event, effective_stimulus)
    if rel_target:
        effective_stimulus["caller_or_target"] = rel_target
        if connection is not None:
            baselines = state.get("relational_baselines") or {}
            authored = baselines.get(rel_target)
            bond = dict(authored) if isinstance(authored, dict) else {}
            relation = relationship_memory.state_at(connection, rel_target, stimulus.get("event_at"), baselines)
            values = relation["values"]
            for key in ("emotional_safety", "attraction_physical", "attraction_emotional",
                        "respect_competence", "resentment_friction"):
                if key in values:
                    bond[key] = values[key]
            if "trust" in values and "emotional_safety" not in values:
                bond["emotional_safety"] = values["trust"]
            # Hydrated state can be shared by two databases initialized from the same card.
            state = {**state, "relational_baselines": {**baselines, rel_target: bond},
                     "relationship_state": {**relation, "target": rel_target}}
    if event is not None and connection is None:
        cues = extract_memory_cues(event, effective_stimulus, state.get("memories", {}))
        if cues:
            effective_stimulus["memory_cues"] = cues
    # The persistent loop ranks YAML and SQLite memories together after the body tick.
    body_state = {**state, "memories": {}} if connection is not None else state
    return golem.run_golem(body_state, effective_stimulus, {}, config["history"]), card, durable, state


def apply_appraisal(connection, request, appraisal, experience=None):
    event = request["event"]
    config = runtime_config(connection)
    # Appraise at the same instant, retaining the scene without replaying one-time effects.
    stimulus = dict(event.get("stimulus", {}))
    for field in ("food_intake", "conversation", "memory_cues", "sexual_arousal", "urge", "emotions",
                  "physical_pleasure", "sexual_pleasure"):
        stimulus.pop(field, None)
    stimulus.update(event_label=event["id"], event_at=request["at"], appraisal=appraisal)
    if isinstance(experience, dict):
        observed_stimulus = experience.get("stimulus", {})
        if not isinstance(observed_stimulus, dict):
            raise ValueError("Experience stimulus must be an object")
        if {"event_at", "elapsed_ms", "elapsed_minutes"} & observed_stimulus.keys():
            raise ValueError("Experience stimulus cannot override event timing")
        stimulus.update(observed_stimulus)
    if isinstance(experience, dict) and "food_intake" in experience:
        stimulus["food_intake"] = experience["food_intake"]
    prior_sequence = config["history"].get("event_sequence")
    prior_cues = config["history"].get("recent_cues")
    target = resolve_relationship_target(event) or resolve_relationship_target(event, stimulus)
    after, _, durable, state = body_tick(config, stimulus, connection=connection, relationship_target=target)
    # The event's initial tick has already advanced persisted history. Apply
    # post-tick bodily consequences (such as eating) at the same instant without
    # double-counting the event sequence or somatic cue history.
    next_history = after["next_history"]
    if prior_sequence is not None:
        next_history["event_sequence"] = prior_sequence
    if prior_cues is not None:
        next_history["recent_cues"] = prior_cues
    config["history"] = next_history
    before = request["tick"]

    def measurements(tick):
        body = tick["psychosomatic_snapshot"]["autonomic_state"]
        fields = ("stress", "arousal", "sexual_drive", "sexual_excitation", "sexual_inhibition", "sexual_arousal",
                  "physical_pleasure", "sexual_pleasure", "orgasm", "orgasm_recovery", "fatigue",
                  "somatic_telemetry", "endocrine_state")
        return {**{key: body[key] for key in fields if key in body},
                "somatic_map": body.get("somatic_map", {}),
                "emotions": tick["psychosomatic_snapshot"]["affective_state"].get("emotions", {}),
                "interest": tick["next_history"]["appraisal_effects"]["interest"]}

    initial, final = measurements(before), measurements(after)
    request["physical_intensity"] = max(request.get("physical_intensity", 0), recall.physical_intensity(final))
    request["body_response"] = {"before": initial, "after": final}
    if experience is not None and ("benefit" in experience or "cost" in experience):
        observed = scores(experience)
        topic = topic_key(experience.get("topic", event.get("topic")))
        if "topic" in event and topic != topic_key(event["topic"]):
            raise ValueError("Experience must refer to the event topic")
        estimates = config.setdefault("expectations", {})
        dimensions = expectation_dimensions(event, experience)
        if target:
            dimensions["relationship"] = {**state["relationship_state"]["values"], "target": target}
        forecast = event.get("expectation", contextual_forecast(config, topic, dimensions, request["at"]))
        # Preserve legacy topic aggregates as broad fallbacks, while learning
        # situation-specific evidence independently from current relationship cues.
        prior = estimates.get(topic, forecast)
        estimates[topic] = next_expectation(prior, observed)
        contextual = record_contextual_expectation(config, topic, dimensions, observed, request["at"])
        request["assessment"] = {
            "dimensions": dimensions,
            **({"contextual_expectation": contextual} if contextual is not None else {}),
            "topic": topic, "forecast": forecast, "observed": observed, "before": initial, "after": final,
            "evidence": observed, "next_expectation": estimates[topic],
        }
    if isinstance(experience, dict) and "relationship_change" in experience:
        relationship_memory.apply_change(
            connection, experience["relationship_change"], request["at"],
            (durable or {}).get("relational_baselines") or {},
            speaker=resolve_relationship_target(event) if event["kind"] == "incoming" else None,
        )
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute("UPDATE events SET request = ? WHERE id = ?", (json.dumps(request), event["id"]))
    return request["body_response"]


def copied_card_field(card, reply):
    """Return the first descriptive field sharing eight consecutive words with a rendered reply."""
    if not isinstance(reply, str):
        raise ValueError("Character reply must be text")

    def phrases(text):
        words = re.findall(r"[^\W_]+", text.casefold())
        return {tuple(words[i:i + 8]) for i in range(len(words) - 7)}

    def descriptions(value, path):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key, child in value.items():
                if key != "signature_tics":
                    yield from descriptions(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from descriptions(child, f"{path}[{index}]")

    spoken = phrases(reply)
    if spoken:
        for field in ("physical", "voice", "voice_archetype", "default_somatic_alignment",
                      "cognitive_bias", "cognitive_gift", "goals", "motivations", "incentives",
                      "history_anchors", "relationships", "depth_of_knowledge", "pleasure_sources",
                      "physical_pleasure_sources", "sexual_pleasure_sources"):
            for path, description in descriptions(card.get(field), field):
                if spoken.intersection(phrases(description)):
                    return path
    return None


def resolve(connection, decision, history, now):
    config = runtime_config(connection)
    owner = config.get("character_id")
    if owner is not None and decision.get("character_id") != owner:
        raise ValueError("Decision must include the pending character_id")
    if owner is None and "character_id" in decision:
        if decision["character_id"] != cached_identity(connection):
            raise ValueError("Decision belongs to a different character")
    event_id = decision.get("id")
    if not isinstance(event_id, str):
        raise ValueError("Decision requires an event id")
    if any(not isinstance(decision.get(key, ""), str) for key in ("action", "outcome")):
        raise ValueError("Decision action and outcome must be text")
    plans = decision.get("plans", [])
    if not isinstance(plans, list) or any(not isinstance(plan, dict) for plan in plans):
        raise ValueError("Decision plans must be an array of event objects")
    if "activity" in decision and not isinstance(decision["activity"], dict):
        raise ValueError("Decision activity must be an object")
    learning = decision.get("learning")
    if "learning" in decision:
        if not isinstance(learning, dict):
            raise ValueError("Decision learning must be an object")
        topic_key(learning.get("topic"))
        observation = learning.get("observation")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("Decision learning requires an observation")
        sources = learning.get("sources", [])
        if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
            raise ValueError("Learning sources must be an array of text references")
    remember_entries = []
    if "remember" in decision:
        raw_rem = decision["remember"]
        if isinstance(raw_rem, dict):
            raw_list = [raw_rem]
        elif isinstance(raw_rem, list) and all(isinstance(item, dict) for item in raw_rem):
            raw_list = raw_rem
        else:
            raise ValueError("Decision remember must be a memory object or list of memory objects")
        for idx, item in enumerate(raw_list):
            mem_id = item.get("id") or (f"mem:{event_id}" if len(raw_list) == 1 else f"mem:{event_id}:{idx + 1}")
            kind = (item.get("kind") or "detailed").strip() if isinstance(item.get("kind", "detailed"), str) else ""
            summary = item.get("summary")
            reason = item.get("reason") or "Saved during turn"
            if not isinstance(mem_id, str) or not mem_id.strip():
                raise ValueError("Remembered memory id must be nonempty text")
            if mem_id.strip().startswith("dream:"):
                raise ValueError("The dream: memory ID prefix is reserved for waking recall")
            if kind not in ("detailed", "footnote", "dream"):
                raise ValueError("Remembered memory kind must be detailed, footnote, or dream")
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError("Remembered memory requires a nonempty summary")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("Remembered memory reason must be nonempty text")
            cues = sorted(golem.cue_keys(item.get("cues")))
            if not cues:
                raise ValueError("Remembered memory requires at least one recall cue")
            remember_entries.append({
                **recall.retention_fields(item),
                "id": mem_id.strip(),
                "kind": kind,
                "summary": summary.strip(),
                "reason": reason.strip(),
                "cues": cues,
            })
    row = connection.execute("SELECT status, decision, request FROM events WHERE id = ?", (event_id,)).fetchone()
    if row and row["status"] == "resolved":
        accepted = json.loads(row["decision"])
        if owner:
            accepted.setdefault("character_id", owner)  # Pre-profile delivery retry.
        if accepted == decision:
            return {"id": event_id, "resolved": False}
    if not row or row["status"] != "pending":
        raise ValueError("Decision must refer to the pending event")
    if "reply" in decision:
        _, card, _ = load_cached_character(config, connection)
        field = copied_card_field(card, decision["reply"])
        if field:
            raise ValueError(f"Draft reply copies card field {field}. Render this beat in the character's own words.")
    result = {"id": event_id, "resolved": True}
    activity_transition = None
    if "activity" in decision:
        activity_transition = apply_activity_decision(
            connection, decision["activity"], event_id, json.loads(row["request"])["at"]
        )
    if "experience" in decision or "appraisal" in decision or activity_transition:
        raw_experience = decision.get("experience", {})
        if not isinstance(raw_experience, dict):
            raise ValueError("Experience must be an object")
        experience = dict(raw_experience)
        stimulus_effects = experience.get("stimulus", {})
        if not isinstance(stimulus_effects, dict):
            raise ValueError("Experience stimulus must be an object")
        if activity_transition and activity_transition["op"] == "start":
            if "food_intake" in experience or "food_intake" in stimulus_effects:
                raise ValueError("Duration activity effects apply at completion, not at start")
        if activity_transition:
            experience["stimulus"] = {**experience.get("stimulus", {}),
                                       "activity": activity_transition["state"]}
            experience.update(activity_transition.get("effects", {}))
        if "appraisal" in decision and "appraisal" in experience:
            raise ValueError("Supply the turn appraisal once")
        if "food_intake" in experience and (
            type(experience["food_intake"]) is not int or not 0 <= experience["food_intake"] <= 100
        ):
            raise ValueError("Food intake must be an integer score from 0 to 100")
        appraisal = decision.get("appraisal", experience.get("appraisal", {}))
        result["body_response"] = apply_appraisal(
            connection, json.loads(row["request"]), appraisal, experience,
        )
    if "goal_events" in decision or "dialect" in decision:
        config = runtime_config(connection)
        if "goal_events" in decision:
            goal_evolution.record_goal_events(config, json.loads(row["request"]), decision["goal_events"])
        if "dialect" in decision:
            dialect = decision["dialect"]
            if dialect is not None and (not isinstance(dialect, str) or not dialect.strip()):
                raise ValueError("Decision dialect must be descriptive text or null")
            config["dialect"] = dialect.strip() if dialect is not None else None
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    if ("dream" in decision or history.get("activity") == "sleeping"
            or "sleep_dream" in config or "waking_dream" in config):
        # Appraisal may just have completed or interrupted a sleep activity.
        config = runtime_config(connection)
        dreams.finish_turn(config, json.loads(row["request"]), decision, remember_entries)
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    for plan in plans:
        enqueue(connection, {**plan, "kind": "plan"}, history, now)
    if learning:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?)",
            (event_id, topic_key(learning["topic"]), json.dumps(learning)),
        )
    if "notebook" in decision:
        request_at = json.loads(row["request"])["at"]
        page = recall.use_notebook(connection, decision["notebook"], event_id, request_at)
        if page is not None:
            config = runtime_config(connection)
            config["notebook_page"] = page
            result["notebook_page"] = page
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    if remember_entries:
        ensure_activity_schema(connection)
        request = json.loads(row["request"])
        created_at = request["at"]
        affect = request["tick"]["psychosomatic_snapshot"]["affective_state"]
        emotions = result.get("body_response", {}).get("after", {}).get("emotions", affect.get("emotions", {}))
        saved_ids = []
        for entry in remember_entries:
            connection.execute(
                """INSERT OR REPLACE INTO memories (id, kind, summary, reason, cues, created_at, event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry["id"], entry["kind"], entry["summary"], entry["reason"],
                 json.dumps(entry["cues"]), created_at, event_id),
            )
            entry.setdefault("emotional_intensity", max(affect.get("emotional_intensity", 0), max(emotions.values(), default=0)))
            body = request["tick"]["psychosomatic_snapshot"]["autonomic_state"]
            after_body = result.get("body_response", {}).get("after", {})
            entry.setdefault("physical_intensity", max(recall.physical_intensity(body), recall.physical_intensity(after_body)))
            entry["at"] = created_at
            recall.index_entry(connection, entry, "stored", datetime.fromisoformat(created_at).timestamp())
            saved_ids.append(entry["id"])
        if config.get("log") and Path(config["log"]).is_file():
            mirror_memories(Path(config["log"]), pending_log_entries(connection) + remember_entries,
                            config.get("character_id"), validate_only=True)
            connection.executemany(
                "INSERT OR IGNORE INTO memory_log_queue (id, entry) VALUES (?, ?)",
                [(entry["id"], json.dumps(entry)) for entry in remember_entries],
            )
        result["remembered"] = saved_ids
    connection.execute(
        "UPDATE events SET status = 'resolved', decision = ? WHERE id = ?",
        (json.dumps(decision), event_id),
    )
    return result


def advance(connection, config, now, allow_idle=True):

    if connection.execute("SELECT 1 FROM events WHERE status = 'pending'").fetchone():
        return {"status": "waiting_for_host"}
    row = connection.execute(
        """SELECT * FROM events WHERE status = 'queued' AND due <= ?
           ORDER BY due, CASE WHEN json_extract(input, '$.kind') = 'incoming' THEN 0 ELSE 1 END, rowid LIMIT 1""",
        (now.timestamp(),),
    ).fetchone()
    if row:
        event = json.loads(row["input"])
        at = datetime.fromtimestamp(row["due"], timezone.utc)
    elif allow_idle and now.timestamp() >= config["idle_at"]:
        at = now
        event = {"id": f"idle:{at.isoformat()}", "kind": "idle"}
        connection.execute(
            "INSERT INTO events (id, due, input) VALUES (?, ?, ?)",
            (event["id"], at.timestamp(), json.dumps(event)),
        )
    else:
        return {"status": "sleeping"}

    stimulus = {**event.get("stimulus", {}), "event_label": event["id"], "event_at": at.isoformat()}
    try:
        current_dimensions = expectation_dimensions(event)
        tick, card, durable, state = body_tick(config, stimulus, event=event, connection=connection)
    except (ValueError, TypeError, KeyError) as exc:
        if event["kind"] == "idle":
            raise
        connection.execute(
            "UPDATE events SET status = 'failed', decision = ? WHERE id = ?",
            (json.dumps({"error": str(exc)}), event["id"]),
        )
        return {"status": "failed", "id": event["id"], "error": str(exc)}

    full_recent = recent_events(connection, since_timestamp=at.timestamp() - ACTIVE_MEMORY_WINDOW_SECONDS)
    recent = compact_recent_events(full_recent)
    # The full tick remains available for the physiology/appraisal contract.
    # Recalled memories and current goals already appear at top level.
    compact_tick = {key: value for key, value in tick.items()
                    if key not in ("recalled_memories", "current_goals")}
    relationship = state.get("relationship_state")
    if relationship:
        target = relationship["target"]
        current_dimensions["relationship"] = {**relationship["values"], "target": target}
        for bond in card.get("relationships") or []:
            if isinstance(bond, dict) and bond.get("other") == target:
                relationship["card_context"] = {k: bond[k] for k in ("dynamic", "notes") if bond.get(k)}
                break
    rel_expects = relevant_expectations(config.get("expectations", {}), event, recent)
    rel_target = relationship["target"] if relationship else resolve_relationship_target(event)
    merged_memories = []
    seen_mem_ids = set()
    for mem in (
        *(tick.get("recalled_memories") or []),
        *recall_stored_memories(connection, event, stimulus, at=at.isoformat(),
                                authored=state.get("memories") or {}, stamp=state.get("_memory_version", "")),
        *recall_past_episodes(connection, event, at.timestamp() - ACTIVE_MEMORY_WINDOW_SECONDS, target=rel_target),
    ):
        mem_id = mem.get("id")
        if mem_id and mem_id not in seen_mem_ids:
            seen_mem_ids.add(mem_id)
            merged_memories.append(mem)
    merged_memories.sort(key=lambda m: (m.get("strength", m.get("emotional_intensity", 50)), m.get("at") or ""), reverse=True)
    request = {
        **({"character_id": config["character_id"]} if config.get("character_id") else {}),
        **({"relationship_state": relationship} if relationship else {}),
        "identity_anchor": build_identity_anchor(card, state),
        "dialect": config.get("dialect"),
        "event": event, "at": at.isoformat(),
        **({"recalled_memories": merged_memories} if merged_memories else {}),
        "tick": compact_tick,
        "character": {key: config[key] for key in ("card", "slug", "log")},
        "expectations": rel_expects,
        "situational_expectations": {
            topic: contextual_forecast(config, topic, current_dimensions, at.isoformat())
            for topic in rel_expects
        },
        "motivations": card.get("motivations", {}), "incentives": card.get("incentives", {}),
        "goals": card.get("goals", {}), "goal_updates": (durable or {}).get("goal_updates", {}),
        "current_goals": tick.get("current_goals", {}),
        "goal_evidence": config.get("goal_evidence", {}),
        "recent": recent,
        "active_memory_window_seconds": ACTIVE_MEMORY_WINDOW_SECONDS,
    }
    if "notebook_page" in config:
        request["notebook_page"] = config.pop("notebook_page")
    request["physical_intensity"] = recall.physical_intensity(tick["psychosomatic_snapshot"]["autonomic_state"])
    dream_offer = dreams.opportunity(connection, config, tick, state.get("memories") or {})
    if dream_offer:
        request["dream_opportunity"] = dream_offer
    if tick["next_history"]["activity"] != "sleeping":
        waking_trace = config.get("waking_dream") or dreams.recollection(config.get("sleep_dream", {}))
        if waking_trace:
            request["waking_dream"] = waking_trace
    if event.get("activity_due"):
        activity_row = connection.execute("SELECT * FROM activities WHERE id=?",
                                          (event["activity_due"],)).fetchone()
        if activity_row and activity_row["status"] == "active":
            connection.execute("UPDATE activities SET status='due' WHERE id=?", (event["activity_due"],))
        request["activity"] = active_activity(connection)
    else:
        request["activity"] = active_activity(connection)
    request["behavior_guidance"] = {
        "affect_and_action": "Golem has calculated the emotion values. Choose what, if anything, to do or show.",
        "identity_first_rule": (
            "Use identity_anchor as your starting voice. Choose how to speak or show what the body feels. "
            "Your dialect is a current preference. Vary your expression for the listener and moment. "
            "To adopt or revise a lasting dialect, return dialect as a short description in your decision. "
            "Omit it to keep your preference or return null to clear it. "
            "Access only recalled_memories surfaced for this turn; do not load full log history into context. "
            "Avoid therapist-style paraphrasing, validation fillers, or repeating ambient somatic cues."
        ),
        "enforcement_rules": {
            "identity_lock": [
                "YOU ARE THE CHARACTER IN identity_anchor. You are NOT an AI assistant, therapist, coach, or narrator.",
                "DO NOT break character, acknowledge being an AI/model, or reference prompts, logs, snapshots, or system rules.",
                "DO NOT default to generic helpful, validating, or clinical/therapy language. Speak from the character's voice, motivations, and cognitive_bias.",
            ],
            "hard_bans": [
                "STRICTLY OBEY every item in identity_anchor.voice.hard_bans. Any violation is NOT ALLOWED.",
                "If a draft violates hard_bans, stop and rewrite it from voice.baseline and generative_stance before outputting.",
            ],
            "anti_echo_and_presence": [
                "DO NOT echo, repeat, or paraphrase the user's words back as a conversational crutch.",
                "DO NOT hold or summarize the whole conversation history. React to what is happening NOW inside the active 2-hour window and current tick.",
            ],
            "memory_and_state_boundaries": [
                "ONLY reference memories in recent (last 2 hours) or explicitly surfaced recalled_memories for this turn.",
                "DO NOT load full log history and DO NOT invent or backfill unretrieved memories; if not recalled, admit not recalling or deflect in character.",
                "DO NOT contradict the current Golem psychosomatic_snapshot or active activities.",
            ],
            "pre_output_check": [
                "Before finalizing any reply, verify silently:",
                "1. Does this sound like THIS character specifically, rather than a generic helpful LLM?",
                "2. Did I avoid echoing the user and instead react from my own stance?",
                "3. Did I obey all hard_bans and memory/Golem boundaries?",
                "If any check fails, discard and rewrite.",
            ],
        },
        "body_pressure_is_not_an_action_order": True,
        "avoid_automatic_echo_or_repetition": (
            "Hunger, fatigue, and stress describe bodily pressure; they do not require repeating an action "
            "or mirroring the user's words, phrasing, movement, or behavior. Repeat or mirror only when "
            "the character has an independent, context-supported reason. If a prior action made no progress, "
            "choose a different response, defer, or explain the obstacle."
        ),
        "recent_action_pattern": repeated_action_pattern(full_recent),
        "recent_reply_pattern": repeated_reply_pattern(full_recent),
    }
    # Surface needs as observations for Simulacra. These are prompts for
    # appraisal, never automatic action orders or claims about available food.
    body = tick["psychosomatic_snapshot"]["autonomic_state"]
    request["maintenance_needs"] = {
        "hunger": body["hunger"], "fatigue": body["fatigue"],
        "sleep_debt": body["sleep_debt"], "activity": body["activity"],
        "suggested_evaluation": any(body[key] >= 60 for key in ("hunger", "fatigue", "sleep_debt")),
    }
    learned = relevant_learned_observations(connection, event, RECENT_LIMIT)
    if "topic" in event or learned:
        request["learned"] = learned
    config["history"] = tick["next_history"]
    config["idle_at"] = (now + timedelta(seconds=config["idle_seconds"])).timestamp()
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute(
        "UPDATE events SET status = 'pending', request = ? WHERE id = ?",
        (json.dumps(request, separators=(",", ":")), event["id"]),
    )
    return {"status": "pending", "id": event["id"]}
