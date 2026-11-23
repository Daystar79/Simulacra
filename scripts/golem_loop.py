"""Persistent event loop and host handoff for the Golem CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from . import golem, goal_evolution
else:
    import golem
    import goal_evolution

RECENT_LIMIT = 12
ACTIVE_MEMORY_WINDOW_SECONDS = 2 * 60 * 60


@contextmanager
def transaction(db: Path):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
    finally:
        connection.close()


def ensure_activity_schema(connection):
    """Non-destructive migration for persistent runtimes created before activities."""
    connection.execute("""CREATE TABLE IF NOT EXISTS activities (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        state TEXT NOT NULL,
        started_at TEXT NOT NULL,
        due_at TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL,
        ended_at TEXT,
        start_event_id TEXT NOT NULL,
        due_event_id TEXT,
        end_event_id TEXT,
        revision INTEGER NOT NULL DEFAULT 1,
        data TEXT NOT NULL DEFAULT '{}'
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(activities)")}
    if "duration_seconds" not in columns:
        connection.execute("ALTER TABLE activities ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0")
    connection.execute("CREATE INDEX IF NOT EXISTS activity_status_due ON activities(status, due_at)")


def active_activity(connection):
    row = connection.execute(
        "SELECT * FROM activities WHERE status IN ('active','due') ORDER BY started_at LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return dict(row) | {"data": json.loads(row["data"])}


def schedule_activity_due(connection, activity_id, kind, at, revision):
    due_id = f"activity:{activity_id}:due:{revision}"
    event = {"id": due_id, "kind": "plan", "at": at,
             "activity_due": activity_id,
             "context": f"The planned {kind} period has reached its scheduled end."}
    row = connection.execute("SELECT input FROM events WHERE id=?", (due_id,)).fetchone()
    if row:
        if json.loads(row["input"]) != event:
            raise ValueError(f"Activity due event ID collision: {due_id}")
    else:
        connection.execute("INSERT INTO events (id,due,input) VALUES (?,?,?)",
                           (due_id, golem.parse_event_time(at).timestamp(), json.dumps(event)))
    connection.execute("UPDATE activities SET due_event_id=? WHERE id=?", (due_id, activity_id))
    return due_id


def apply_activity_decision(connection, activity, event_id, at):
    """Persist a selected duration activity and its scheduled transition atomically."""
    if not isinstance(activity, dict):
        raise ValueError("Decision activity must be an object")
    op = activity.get("op")
    allowed_ops = {"start", "complete", "interrupt", "resume", "extend"}
    if op not in allowed_ops:
        raise ValueError("Activity op must be start, complete, interrupt, resume, or extend")
    at_dt = golem.parse_event_time(at)
    if op == "start":
        activity_id, kind = activity.get("id"), activity.get("kind")
        state, seconds = activity.get("state"), activity.get("duration_seconds")
        if not isinstance(activity_id, str) or not activity_id.strip() or not isinstance(kind, str) or not kind.strip():
            raise ValueError("Starting an activity requires stable id and kind strings")
        if state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        if type(seconds) is not int or seconds < 1:
            raise ValueError("Activity duration_seconds must be a positive integer")
        if connection.execute("SELECT 1 FROM activities WHERE status IN ('active','due')").fetchone():
            raise ValueError("An activity is already active; interrupt or complete it first")
        due_at = (at_dt + timedelta(seconds=seconds)).isoformat()
        data = activity.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("Activity data must be an object")
        effects = data.get("effects", {})
        if not isinstance(effects, dict):
            raise ValueError("Activity effects must be an object")
        if set(effects) - {"food_intake"}:
            raise ValueError("Activity effects currently support food_intake only")
        if "food_intake" in effects and (type(effects["food_intake"]) is not int
                                          or not 0 <= effects["food_intake"] <= 100):
            raise ValueError("Activity food_intake must be an integer from 0 to 100")
        connection.execute("""INSERT INTO activities
            (id,kind,status,state,started_at,due_at,duration_seconds,start_event_id,revision,data)
            VALUES (?,?, 'active', ?,?,?,?,?,1,?)""",
                           (activity_id, kind, state, at_dt.isoformat(), due_at, seconds, event_id,
                            json.dumps(data)))
        schedule_activity_due(connection, activity_id, kind, due_at, 1)
        return {"state": state, "op": op, "activity_id": activity_id}

    activity_id = activity.get("id")
    row = connection.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    if not row:
        raise ValueError("Unknown activity id")
    if op == "complete":
        if row["status"] != "due":
            raise ValueError("An activity can be completed only after its due event")
        next_state = activity.get("state", "awake")
        if next_state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE activities SET status='completed',ended_at=?,end_event_id=? WHERE id=?",
                           (at_dt.isoformat(), event_id, activity_id))
        return {"state": next_state, "op": op, "activity_id": activity_id,
                "effects": json.loads(row["data"]).get("effects", {})}
    if op == "interrupt":
        if row["status"] not in ("active", "due"):
            raise ValueError("Only an active activity can be interrupted")
        next_state = activity.get("state", "awake")
        if next_state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE events SET status='cancelled' WHERE id=? AND status='queued'",
                           (row["due_event_id"],))
        connection.execute("UPDATE activities SET status='interrupted',ended_at=?,end_event_id=? WHERE id=?",
                           (at_dt.isoformat(), event_id, activity_id))
        return {"state": next_state, "op": op, "activity_id": activity_id}
    if op in ("resume", "extend"):
        permitted = "interrupted" if op == "resume" else "due"
        if row["status"] != permitted:
            raise ValueError(f"Activity {op} requires status {permitted}")
        seconds = activity.get("duration_seconds")
        if type(seconds) is not int or seconds < 1:
            raise ValueError(f"Activity {op} requires positive duration_seconds")
        state = activity.get("state", row["state"])
        if state not in ("awake", "resting", "sleeping"):
            raise ValueError("Activity state must be awake, resting, or sleeping")
        connection.execute("UPDATE events SET status='cancelled' WHERE id=? AND status='queued'",
                           (row["due_event_id"],))
        due_at = (at_dt + timedelta(seconds=seconds)).isoformat()
        revision = row["revision"] + 1
        connection.execute("""UPDATE activities SET status='active',state=?,due_at=?,duration_seconds=?,
            ended_at=NULL,end_event_id=NULL,revision=? WHERE id=?""",
                           (state, due_at, seconds, revision, activity_id))
        schedule_activity_due(connection, activity_id, row["kind"], due_at, revision)
        return {"state": state, "op": op, "activity_id": activity_id}


def setup(connection, args, now):
    ensure_activity_schema(connection)
    card = args.card.resolve(strict=True)
    log = args.log.resolve(strict=True) if args.log else None
    golem.overlay_log(golem.load_character(card, args.slug), log)
    history = read_object(args.import_history) if args.import_history else {}
    if args.history_at:
        if history.get("last_event_at"):
            raise ValueError("Imported history already has a timestamp")
        history["last_event_at"] = golem.parse_event_time(args.history_at).isoformat()
    elif history.get("last_event_at"):
        history["last_event_at"] = golem.parse_event_time(history["last_event_at"]).isoformat()
    else:
        history["last_event_at"] = now.isoformat()
    if args.idle_seconds < 1:
        raise ValueError("--idle-seconds must be at least 1")
    config = {
        "card": str(card), "log": str(log) if log else None, "slug": args.slug,
        "idle_seconds": args.idle_seconds, "history": history,
        "idle_at": (now + timedelta(seconds=args.idle_seconds)).timestamp(),
    }
    load_cached_character(config)
    connection.execute("CREATE TABLE runtime (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)")
    connection.execute("""
        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            due REAL NOT NULL,
            input TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            request TEXT,
            decision TEXT
        )
    """)
    connection.execute("CREATE INDEX due_events ON events (status, due)")
    connection.execute("CREATE TABLE observations (event_id TEXT PRIMARY KEY, topic TEXT NOT NULL, data TEXT NOT NULL)")
    connection.execute("CREATE INDEX observation_topics ON observations (topic)")
    connection.execute("INSERT INTO runtime VALUES (1, ?)", (json.dumps(config),))
    return {"initialized": True}


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def enqueue(connection, event, history, now):
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
    if existing is not None:
        if json.loads(existing["input"]) != event:
            raise ValueError(f"Event ID already exists with different contents: {event_id}")
        return {"id": event_id, "queued": False}
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
    user_text = " ".join(
        str(val) for val in (
            latest_event.get("text"),
            latest_event.get("message"),
            (latest_event.get("stimulus") or {}).get("text"),
        ) if isinstance(val, str) and val.strip()
    )
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


def pending_request(connection):
    row = connection.execute("SELECT request FROM events WHERE status = 'pending'").fetchone()
    if not row:
        return None
    request = json.loads(row["request"])
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
    return request


def topic_key(topic):
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("A learning topic must be nonempty text")
    return topic.strip().casefold()


def learned_observations(connection, topic, limit=-1):
    records = connection.execute(
        """SELECT events.id, observations.data FROM observations
           JOIN events ON events.id = observations.event_id
           WHERE observations.topic = ? ORDER BY events.due DESC, events.rowid DESC LIMIT ?""",
        (topic_key(topic), limit),
    )
    return [{**json.loads(row["data"]), "event_id": row["id"]} for row in reversed(records.fetchall())]


def scores(value):
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or not 0 <= value[key] <= 100 for key in ("benefit", "cost")
    ):
        raise ValueError("Benefit and cost must each be integer scores from 0 to 100")
    return {key: value[key] for key in ("benefit", "cost")}


def runtime_config(connection):
    return json.loads(connection.execute("SELECT data FROM runtime WHERE id = 1").fetchone()["data"])


def next_expectation(prior, observed):
    if prior is None:
        return dict(observed)
    return {key: round(0.75 * prior[key] + 0.25 * value, 2) for key, value in observed.items()}


def recalculate_expectations(connection, config):
    """Replay recorded outcome scores, retaining each topic's original starting forecast."""
    rebuilt = {}
    rows = connection.execute(
        """SELECT json_extract(request, '$.assessment') FROM events
           WHERE status = 'resolved' AND json_type(request, '$.assessment') = 'object'
           ORDER BY due, rowid"""
    )
    for (data,) in rows:
        assessment = json.loads(data)
        topic = assessment["topic"]
        prior = rebuilt.get(topic, assessment["forecast"])
        rebuilt[topic] = next_expectation(prior, scores(assessment["observed"]))
    if rebuilt:
        estimates = config.setdefault("expectations", {})
        estimates.update(rebuilt)
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        connection.execute(
            """UPDATE events SET request=json_set(request, '$.expectations', json(?))
               WHERE status='pending'""", (json.dumps(estimates),),
        )
    return {"expectations": config.get("expectations", {})}


def load_cached_character(config):
    """Cache parsed card and overlaid log state in runtime config, refreshing when file mtimes change."""
    card_path = Path(config["card"])
    log_path = Path(config["log"]) if config.get("log") else None
    card_mtime = card_path.stat().st_mtime_ns
    log_mtime = log_path.stat().st_mtime_ns if log_path and log_path.exists() else None
    goal_changes = config.get("goal_changes") or {}
    cached = config.get("cached_character")
    if (
        isinstance(cached, dict)
        and cached.get("card_mtime") == card_mtime
        and cached.get("log_mtime") == log_mtime
        and cached.get("goal_changes") == goal_changes
    ):
        return (
            json.loads(json.dumps(cached["state"])),
            cached["card"],
            cached["durable"],
        )
    card = golem.load_character(card_path, config.get("slug"))
    state, durable = golem.overlay_log(card, log_path, goal_changes=goal_changes)
    config["cached_character"] = {
        "card_mtime": card_mtime,
        "log_mtime": log_mtime,
        "goal_changes": json.loads(json.dumps(goal_changes)),
        "card": card,
        "state": state,
        "durable": durable,
    }
    return json.loads(json.dumps(state)), card, durable


def build_identity_anchor(card, state):
    """Extract core identity and voice constraints without dumping full memories or history."""
    anchor = {
        key: card[key]
        for key in ("name", "call_name", "character_id", "cognitive_bias", "cognitive_gift", "voice")
        if key in card
    }
    for key in ("active_focus", "defense_posture", "social_facade"):
        if key in state:
            anchor[key] = state[key]
    return anchor


def extract_memory_cues(event, stimulus, memories):
    """Match stored memory cues against incoming event text for on-demand recall."""
    explicit = [str(c).strip() for c in stimulus.get("memory_cues", []) if str(c).strip()]
    texts = [
        event.get("text"),
        event.get("message"),
        event.get("topic"),
        stimulus.get("text"),
        (stimulus.get("conversation") or {}).get("open_topic"),
    ]
    haystack = " ".join(str(t) for t in texts if isinstance(t, str) and t.strip()).casefold()
    if not haystack or not isinstance(memories, dict):
        return explicit
    matched = list(explicit)
    seen = {c.casefold() for c in matched}
    for bucket in ("detailed", "footnote"):
        for entry in memories.get(bucket) or []:
            for cue in entry.get("cues") or []:
                cue_text = str(cue).strip()
                if not cue_text or cue_text.casefold() in seen:
                    continue
                if re.search(rf"(?<!\w){re.escape(cue_text.casefold())}(?!\w)", haystack):
                    matched.append(cue_text)
                    seen.add(cue_text.casefold())
    return matched


def body_tick(config, stimulus, event=None):
    state, card, durable = load_cached_character(config)
    effective_stimulus = dict(stimulus)
    if event is not None:
        cues = extract_memory_cues(event, effective_stimulus, state.get("memories", {}))
        if cues:
            effective_stimulus["memory_cues"] = cues
    realm_data = yaml.safe_load(golem.REALM_DATA_PATH.read_text(encoding="utf-8"))
    return golem.run_golem(state, effective_stimulus, realm_data, config["history"]), card, durable, state


def apply_appraisal(connection, request, appraisal, experience=None):
    event = request["event"]
    config = runtime_config(connection)
    # Appraise at the same instant, retaining the scene without replaying one-time effects.
    stimulus = dict(event.get("stimulus", {}))
    for field in ("food_intake", "conversation", "memory_cues", "sexual_arousal", "urge", "emotions"):
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
    after, _, _, _ = body_tick(config, stimulus)
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
        fields = ("stress", "arousal", "sexual_drive", "sexual_excitation", "sexual_inhibition", "sexual_arousal")
        return {**{key: body[key] for key in fields if key in body},
                "somatic_map": body.get("somatic_map", {}),
                "emotions": tick["psychosomatic_snapshot"]["affective_state"].get("emotions", {}),
                "interest": tick["next_history"]["appraisal_effects"]["interest"]}

    initial, final = measurements(before), measurements(after)
    request["body_response"] = {"before": initial, "after": final}
    if experience is not None and ("benefit" in experience or "cost" in experience):
        observed = scores(experience)
        topic = topic_key(experience.get("topic", event.get("topic")))
        if "topic" in event and topic != topic_key(event["topic"]):
            raise ValueError("Experience must refer to the event topic")
        estimates = config.setdefault("expectations", {})
        forecast = event.get("expectation", estimates.get(topic))
        # A stated forecast belongs to this episode. Repeated observations update the learned prior.
        prior = estimates.get(topic, forecast)
        estimates[topic] = next_expectation(prior, observed)
        request["assessment"] = {
            "topic": topic, "forecast": forecast, "observed": observed, "before": initial, "after": final,
            "evidence": observed, "next_expectation": estimates[topic],
        }
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
                      "history_anchors", "relationships", "depth_of_knowledge"):
            for path, description in descriptions(card.get(field), field):
                if spoken.intersection(phrases(description)):
                    return path
    return None


def resolve(connection, decision, history, now):
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
    row = connection.execute("SELECT status, decision, request FROM events WHERE id = ?", (event_id,)).fetchone()
    if row and row["status"] == "resolved" and json.loads(row["decision"]) == decision:
        return {"id": event_id, "resolved": False}
    if not row or row["status"] != "pending":
        raise ValueError("Decision must refer to the pending event")
    if "reply" in decision:
        config = runtime_config(connection)
        card = golem.load_character(Path(config["card"]), config["slug"])
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
    for plan in plans:
        enqueue(connection, {**plan, "kind": "plan"}, history, now)
    if learning:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?)",
            (event_id, topic_key(learning["topic"]), json.dumps(learning)),
        )
    connection.execute(
        "UPDATE events SET status = 'resolved', decision = ? WHERE id = ?",
        (json.dumps(decision), event_id),
    )
    return result


def advance(connection, config, now, allow_idle=True):

    if connection.execute("SELECT 1 FROM events WHERE status = 'pending'").fetchone():
        return {"status": "waiting_for_host"}
    row = connection.execute(
        "SELECT * FROM events WHERE status = 'queued' AND due <= ? ORDER BY due, rowid LIMIT 1",
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
        tick, card, durable, state = body_tick(config, stimulus, event=event)
    except (ValueError, TypeError, KeyError) as exc:
        if event["kind"] == "idle":
            raise
        connection.execute(
            "UPDATE events SET status = 'failed', decision = ? WHERE id = ?",
            (json.dumps({"error": str(exc)}), event["id"]),
        )
        return {"status": "failed", "id": event["id"], "error": str(exc)}

    request = {
        "identity_anchor": build_identity_anchor(card, state),
        "dialect": config.get("dialect"),
        "event": event, "at": at.isoformat(),
        **({"recalled_memories": tick["recalled_memories"]} if tick.get("recalled_memories") else {}),
        "tick": tick,
        "character": {key: config[key] for key in ("card", "slug", "log")},
        "expectations": config.get("expectations", {}),
        "motivations": card.get("motivations", {}), "incentives": card.get("incentives", {}),
        "goals": card.get("goals", {}), "goal_updates": (durable or {}).get("goal_updates", {}),
        "current_goals": tick.get("current_goals", {}),
        "goal_evidence": config.get("goal_evidence", {}),
        "recent": recent_events(connection, since_timestamp=at.timestamp() - ACTIVE_MEMORY_WINDOW_SECONDS),
        "active_memory_window_seconds": ACTIVE_MEMORY_WINDOW_SECONDS,
    }
    if event.get("activity_due"):
        activity_row = connection.execute("SELECT * FROM activities WHERE id=?",
                                          (event["activity_due"],)).fetchone()
        if activity_row and activity_row["status"] == "active":
            connection.execute("UPDATE activities SET status='due' WHERE id=?", (event["activity_due"],))
        request["activity"] = active_activity(connection)
    else:
        request["activity"] = active_activity(connection)
    request["behavior_guidance"] = {
        "affect_and_action": (
            "Read autonomic_state.somatic_map for localized sensations. Choose which are outwardly visible. "
            "Consider all concurrent feelings in affective_state.emotions. Choose which to show, temper, "
            "or keep private. To capture feelings you recognize, return experience.stimulus.emotions "
            "as a map of emotion names to intensities (0–100). "
            "Weigh initiative alongside current goals and available energy. Express salient emotions "
            "through this character's choices and voice. Intimacy reflects willingness to be seen "
            "by this target, including physical ease or anticipation. It does not imply permission. "
            "An impulse_override brings an urge to mind before deliberation. Decide whether to act, "
            "redirect or hold back. A felt urge alone does not establish an action or outcome."
        ),
        "identity_first_rule": (
            "Use the card as your starting voice. Choose how to speak or show what the body feels. "
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
        "recent_action_pattern": repeated_action_pattern(request["recent"]),
        "recent_reply_pattern": repeated_reply_pattern(request["recent"]),
    }
    # Surface needs as observations for Simulacra. These are prompts for
    # appraisal, never automatic action orders or claims about available food.
    body = tick["psychosomatic_snapshot"]["autonomic_state"]
    request["maintenance_needs"] = {
        "hunger": body["hunger"], "fatigue": body["fatigue"],
        "sleep_debt": body["sleep_debt"], "activity": body["activity"],
        "suggested_evaluation": any(body[key] >= 60 for key in ("hunger", "fatigue", "sleep_debt")),
    }
    if "topic" in event:
        request["learned"] = learned_observations(connection, event["topic"], RECENT_LIMIT)
    config["history"] = tick["next_history"]
    config["idle_at"] = (now + timedelta(seconds=config["idle_seconds"])).timestamp()
    connection.execute("UPDATE runtime SET data = ? WHERE id = 1", (json.dumps(config),))
    connection.execute(
        "UPDATE events SET status = 'pending', request = ? WHERE id = ?",
        (json.dumps(request), event["id"]),
    )
    return {"status": "pending", "id": event["id"]}


def execute(db, args):
    with transaction(db) as connection:
        now = datetime.now(timezone.utc)
        if args.command == "init":
            return setup(connection, args, now)
        ensure_activity_schema(connection)
        config = runtime_config(connection)
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if args.command == "run":
            return advance(connection, config, now)
        if args.command == "recalculate-expectations":
            return recalculate_expectations(connection, config)
        if args.command == "enqueue":
            event = read_object(args.event)
            if event.get("kind") == "incoming" and config.get("owned_files"):
                raise ValueError("Send incoming messages through the host boundary assessment")
            return enqueue(connection, event, config["history"], now)
        if args.command == "resolve":
            return resolve(connection, read_object(args.decision), config["history"], now)
        if args.command == "pending":
            return pending_request(connection)
        if args.command == "timeline":
            return recent_events(connection, args.limit)
        if args.command == "learned":
            return learned_observations(connection, args.topic)
        activities = [dict(row) | {"data": json.loads(row["data"])} for row in connection.execute(
            "SELECT * FROM activities ORDER BY started_at")]
        return {"history": config["history"], "expectations": config.get("expectations", {}),
                "activities": activities, "pending": pending_request(connection),
                "recent": recent_events(connection)}


def commit_goal_updates(db):
    """Merge the host-approved batch of pending goal amendments into the configured YAML log."""
    with transaction(Path(db).resolve(strict=True)) as connection:
        config = runtime_config(connection)
        if config.get("lifecycle"):
            raise ValueError("This character runtime is closed")
        changes = config.get("goal_changes", {})
        if not changes:
            return False
        if not config.get("log"):
            raise ValueError("No durable YAML log is configured")
        path = Path(config["log"])
        if path.samefile(config["card"]):
            raise ValueError("The durable log must be a separate file from the character card")
        with golem.locked_log(path) as log:
            updates = log.setdefault("goal_updates", {})
            changed = False
            for goal_id, fields in changes.items():
                existing = updates.setdefault(goal_id, {})
                if isinstance(existing, str):
                    existing = updates[goal_id] = {"objective": existing}
                if any(existing.get(key) != value for key, value in fields.items()):
                    existing.update(fields)
                    changed = True
            if changed:
                log["revision"] = log.get("revision", 0) + 1
                log["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                golem.replace_text(path, yaml.safe_dump(log, sort_keys=False))
        del config["goal_changes"]
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        return changed


def initialize_character(db, card, *, log=None, slug=None, idle_seconds=3600,
                         import_history=None, history_at=None, owned_files=()):
    """Create a new character runtime once. Existing databases are preserved."""
    args = argparse.Namespace(
        card=Path(card), log=Path(log) if log else None, slug=slug, idle_seconds=idle_seconds,
        import_history=Path(import_history) if import_history else None, history_at=history_at,
    )
    with transaction(Path(db)) as connection:
        result = setup(connection, args, datetime.now(timezone.utc))
        if owned_files:
            config = runtime_config(connection)
            directory = Path(db).resolve().parent
            names = set()
            for path in map(Path, owned_files):
                if (path.is_symlink() or path.resolve(strict=True).parent != directory
                        or not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".json", ".md"}
                        or path.name.startswith("_") or path.resolve() == Path(db).resolve()):
                    raise ValueError("Deletion requires individually owned character files beside the database")
                names.add(path.name)
            required = [Path(path).resolve() for path in (card, log, import_history) if path]
            if any(path.parent != directory or path.name not in names for path in required):
                raise ValueError("Register the character card, configured log and imported history as owned files")
            if "characters" in yaml.safe_load(Path(card).read_text(encoding="utf-8")):
                raise ValueError("A shared character pack cannot be registered for deletion")
            config["owned_files"] = sorted(names)
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        return result


def _finish_deletion(db, connection, config):
    # Only names validated at provisioning enter this manifest. Never traverse directories.
    for name in config["owned_files"]:
        path = db.parent / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Character file changed type during deletion: {name}")
        path.unlink(missing_ok=True)
    connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps({"lifecycle": "deleted"}),))


def report_abuse(db, *, actor_id, event_id):
    """Record a host-confirmed incident. Actor and delivery IDs come from the trusted transport."""
    db = Path(db).resolve(strict=True)
    if any(not isinstance(value, str) or not value.strip() for value in (event_id, actor_id)):
        raise ValueError("A confirmed incident requires stable actor and event IDs")
    actor = hashlib.sha256(actor_id.encode()).hexdigest()
    incident = hashlib.sha256(event_id.encode()).hexdigest()
    with transaction(db) as connection:
        ensure_activity_schema(connection)
        config = runtime_config(connection)
        status = config.get("lifecycle")
        if status == "deleted":
            return {"status": status}
        if status != "deleting":
            incidents = config.setdefault("abuse_incidents", {})
            previous = incidents.get(actor)
            config["lifecycle"] = "ended"
            if previous and previous != incident and config.get("owned_files"):
                connection.execute("PRAGMA secure_delete=ON")
                connection.execute("DELETE FROM observations")
                connection.execute("DELETE FROM events")
                config = {"lifecycle": "deleting", "owned_files": config["owned_files"]}
            else:
                incidents.setdefault(actor, incident)
                connection.execute("UPDATE events SET status='cancelled', request=NULL WHERE status IN ('pending','queued')")
            connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        status = config["lifecycle"]
    if status == "deleting":
        with transaction(db) as connection:
            config = runtime_config(connection)
            if config["lifecycle"] == "deleting":
                _finish_deletion(db, connection, config)
        status = "deleted"
    return {"status": status}


def assess_contact(db, event, actor_id, screen):
    event_id = event.get("id")
    if any(not isinstance(value, str) or not value.strip() for value in (actor_id, event_id)):
        raise ValueError("Boundary assessment requires trusted actor and message IDs")
    actor = hashlib.sha256(actor_id.encode()).hexdigest()
    with transaction(db) as connection:
        config = runtime_config(connection)
        previous = config.get("boundaries", {}).get(actor)
        if previous and previous["id"] == event_id:
            if config.get("lifecycle"):
                return {"status": config["lifecycle"]}
            return {"status": "boundary", **previous}
    verdict = screen(event, {"previous_boundary": previous, "status": config.get("lifecycle", "active")})
    if verdict is None:
        return None
    if not isinstance(verdict, dict):
        raise ValueError("Expected a host boundary decision or None")
    if verdict.get("action") == "end_session":
        return report_abuse(db, actor_id=actor_id, event_id=event_id)
    reply = verdict.get("reply")
    if verdict.get("action") != "set_boundary" or not isinstance(reply, str) or not reply.strip():
        raise ValueError("A boundary decision requires set_boundary with a reply, or end_session")
    with transaction(db) as connection:
        config = runtime_config(connection)
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        previous = {"id": event_id, "reply": reply}
        config.setdefault("boundaries", {})[actor] = previous
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
    return {"status": "boundary", **previous}


def wake_character(db, decide, *, event=None, max_events=64, screen_abuse=None, actor_id=None):
    """Run a host heartbeat. decide(request) returns one JSON-compatible character decision."""
    db = Path(db).resolve()
    if not db.is_file():
        raise ValueError("Initialize the character database first")
    if not callable(decide) or type(max_events) is not int or max_events < 1:
        raise ValueError("wake_character requires a decision callback and a positive event limit")
    with transaction(db) as connection:
        ensure_activity_schema(connection)
    # flock is released by the VM kernel when the process exits, including after a crash.
    import fcntl

    if event is not None and event.get("kind") == "incoming":
        with transaction(db) as connection:
            config = runtime_config(connection)
        if config.get("lifecycle") == "deleted":
            return {"status": "deleted"}
        if config.get("owned_files") and screen_abuse is None and config.get("lifecycle") != "deleting":
            raise ValueError("A deletion-enabled runtime requires a host boundary assessment for incoming turns")
        if screen_abuse is not None and config.get("lifecycle") != "deleting":
            boundary = assess_contact(db, event, actor_id, screen_abuse)
            if boundary is not None:
                return boundary

    with transaction(db) as connection:
        config = runtime_config(connection)
        if config.get("lifecycle") == "deleting":
            _finish_deletion(db, connection, config)
            return {"status": "deleted"}
        if config.get("lifecycle"):
            return {"status": config["lifecycle"]}
        if event is not None:
            enqueue(connection, event, config["history"], datetime.now(timezone.utc))

    handled = []
    with db.with_name(db.name + ".wake.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(max_events):
            with transaction(db) as connection:
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                request = pending_request(connection)
                if request is None:
                    result = advance(connection, config, datetime.now(timezone.utc),
                                     allow_idle=not handled)
                    if result["status"] == "sleeping":
                        break
                    if result["status"] == "failed":
                        handled.append(result)
                        continue
                    request = pending_request(connection)
            # The event and body tick are durable before host work starts.
            event_id = request["event"]["id"]
            decision = decide(request)
            if not isinstance(decision, dict) or decision.get("id") != event_id:
                raise ValueError("Host must return a decision matching the pending event ID")
            with transaction(db) as connection:
                config = runtime_config(connection)
                if config.get("lifecycle"):
                    return {"status": config["lifecycle"]}
                result = resolve(connection, decision, config["history"], datetime.now(timezone.utc))
            if result["resolved"] and "reply" in decision:
                result["reply"] = decision["reply"]
            handled.append(result)
    return {"events": handled}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Persistent SQLite database for one character")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--card", type=Path, required=True)
    init.add_argument("--slug")
    init.add_argument("--log", type=Path)
    init.add_argument("--import-history", type=Path)
    init.add_argument("--history-at", help="Timestamp of imported untimestamped history")
    init.add_argument("--idle-seconds", type=int, default=900)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true", help="Process at most one ready event")
    commands.add_parser("pending")
    commands.add_parser("status")
    commands.add_parser("recalculate-expectations", help="Refresh current estimates from recorded outcomes")
    commands.add_parser("timeline").add_argument("--limit", type=int, default=100)
    commands.add_parser("learned").add_argument("topic")
    commands.add_parser("enqueue").add_argument("event", type=Path)
    commands.add_parser("resolve").add_argument("decision", type=Path)
    args = parser.parse_args(argv)
    if args.command == "timeline" and args.limit < 1:
        parser.error("--limit must be positive")
    if args.command != "init" and not args.db.is_file():
        parser.error("Initialize the character database first")
    try:
        if args.command != "run" or args.once:
            print(json.dumps(execute(args.db, args), ensure_ascii=False), flush=True)
            return 0
        while True:
            result = execute(args.db, args)
            if result["status"] in ("ended", "deleting", "deleted"):
                return 0
            if result["status"] in ("pending", "failed"):
                print(json.dumps(result), flush=True)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
