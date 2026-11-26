"""Learned observations, contextual expectations, and expectation recalculation."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_scripts_dir = str(Path(__file__).resolve().parents[1])
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from golem_loop_modules.projection import message_text, resolve_relationship_target  # noqa: E402

RECENT_LIMIT = 12

_OBSERVATION_STOPWORDS = {
    "about", "after", "again", "before", "being", "between", "both", "Could", "could",
    "every", "first", "from", "have", "into", "just", "like", "made", "make", "more",
    "most", "Never", "never", "only", "other", "over", "same", "some", "still", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "very", "what", "when", "where", "which", "while", "with", "would",
}


def relevant_expectations(expectations, event, recent, limit=12):
    """Surface matching learned topics, not the entire cumulative expectation map."""
    topics = []
    for candidate in [event.get("topic"), *(item.get("topic") for item in reversed(recent))]:
        if isinstance(candidate, str):
            key = candidate.strip().casefold()
            if key and key not in topics and key in expectations:
                topics.append(key)
        if len(topics) >= limit:
            break
    if len(topics) < limit and isinstance(event, dict):
        haystack = " ".join(
            str(t) for t in (message_text(event), event.get("context")) if isinstance(t, str) and t.strip()
        ).casefold()
        if haystack:
            for key in expectations:
                if key not in topics and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", haystack):
                    topics.append(key)
                    if len(topics) >= limit:
                        break
    return {key: expectations[key] for key in topics}


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


def relevant_learned_observations(connection, event, limit=RECENT_LIMIT):
    """Retrieve exact topic observations when event.topic is set, or utterance-relevant observations otherwise."""
    if "topic" in event:
        return learned_observations(connection, event["topic"], limit)
    haystack = " ".join(
        str(t) for t in (message_text(event), event.get("context")) if isinstance(t, str) and t.strip()
    ).casefold()
    if not haystack:
        return []
    haystack_words = {
        w for w in re.findall(r"[a-z0-9']+", haystack)
        if len(w) >= 4 and w not in _OBSERVATION_STOPWORDS
    }
    if not haystack_words:
        return []
    topic_scores = {}
    for (obs_topic,) in connection.execute("SELECT DISTINCT topic FROM observations"):
        if not obs_topic:
            continue
        normalized_topic = re.sub(r"[-_]+", " ", obs_topic).strip()
        if len(normalized_topic) >= 4 and re.search(rf"(?<!\w){re.escape(normalized_topic)}(?!\w)", haystack):
            score = 100
        else:
            topic_words = {
                w for w in re.findall(r"[a-z0-9']+", normalized_topic)
                if len(w) >= 4 and w not in _OBSERVATION_STOPWORDS
            }
            if not topic_words:
                continue
            overlap = topic_words & haystack_words
            required = 1 if len(topic_words) == 1 else 2
            if len(overlap) < required:
                continue
            score = len(overlap) * 10 + int(10 * len(overlap) / len(topic_words))
        topic_scores[obs_topic] = score
    if not topic_scores:
        return []
    # Fetch only the winning observations' bodies, even on a long-lived database.
    rows = connection.execute(
        """SELECT id, data FROM (
               SELECT events.id, observations.data, events.due, events.rowid AS sequence
               FROM json_each(?) AS scores
               JOIN observations ON observations.topic = scores.key
               JOIN events ON events.id = observations.event_id
               ORDER BY scores.value DESC, events.due DESC, events.rowid DESC LIMIT ?
           ) ORDER BY due, sequence""",
        (json.dumps(topic_scores), limit),
    )
    return [{**json.loads(row["data"]), "event_id": row["id"]} for row in rows]


def scores(value):
    if not isinstance(value, dict) or any(
        type(value.get(key)) is not int or not 0 <= value[key] <= 100 for key in ("benefit", "cost")
    ):
        raise ValueError("Benefit and cost must each be integer scores from 0 to 100")
    return {key: value[key] for key in ("benefit", "cost")}


def next_expectation(prior, observed):
    if prior is None:
        return dict(observed)
    return {key: round(0.75 * prior[key] + 0.25 * value, 2) for key, value in observed.items()}


def expectation_dimensions(event, experience=None):
    """Relational, situational and contextual cues; no static relationship assumptions."""
    experience = experience or {}
    supplied = experience.get("expectation_context", event.get("expectation_context", {}))
    if not isinstance(supplied, dict):
        raise ValueError("expectation_context must be a mapping")
    result = {}
    for dimension in ("relationship", "situation", "context"):
        value = supplied.get(dimension)
        if isinstance(value, (str, int, float, bool)):
            result[dimension] = str(value).strip().casefold()[:120]
        elif isinstance(value, dict):
            # Canonicalize a small set of explicit current-state cues; no snapshots.
            result[dimension] = {str(k)[:60]: str(v).strip().casefold()[:120]
                                 for k, v in sorted(value.items()) if isinstance(v, (str, int, float, bool))}
        elif value is not None:
            raise ValueError(f"expectation_context.{dimension} must be a scalar or mapping")
    return {key: value for key, value in result.items() if value}


def expectation_matches(entry, dimensions):
    """Rank matching situational evidence without treating past relationship states as current."""
    old = entry.get("dimensions") or {}
    if not old or not dimensions:
        return 0
    score = 0
    for dimension, weight in (("relationship", 4), ("situation", 3), ("context", 2)):
        prior, current = old.get(dimension), dimensions.get(dimension)
        if prior is None or current is None:
            continue
        if isinstance(prior, dict) and isinstance(current, dict):
            overlap = set(prior) & set(current)
            if overlap:
                score += weight * sum(prior[k] == current[k] for k in overlap) / len(overlap)
        elif prior == current:
            score += weight
    return score


def contextual_forecast(config, topic, dimensions, at=None):
    """Return matching observed evidence, falling back to legacy topic estimates."""
    records = config.get("contextual_expectations", {}).get(topic, [])
    if not isinstance(records, list):
        records = []
    ranked = sorted((entry for entry in records if isinstance(entry, dict)),
                    key=lambda entry: expectation_matches(entry, dimensions), reverse=True)
    if ranked and expectation_matches(ranked[0], dimensions) > 0:
        return ranked[0].get("predicted")
    return config.get("expectations", {}).get(topic)


def record_contextual_expectation(config, topic, dimensions, observed, at):
    """Bounded evidence per topic, retaining the relationship state at observation time."""
    if not dimensions:
        return None
    all_records = config.setdefault("contextual_expectations", {})
    records = all_records.setdefault(topic, [])
    if not isinstance(records, list):
        records = []
        all_records[topic] = records
    for entry in records:
        if entry.get("dimensions") == dimensions:
            entry["predicted"] = next_expectation(entry.get("predicted"), observed)
            entry["observations"] = entry.get("observations", 1) + 1
            entry["last_observed_at"] = at
            return entry["predicted"]
    records.append({"dimensions": dimensions, "predicted": dict(observed),
                    "observations": 1, "last_observed_at": at})
    # Cap stored contexts per topic; full episode evidence remains in the ledger.
    if len(records) > 24:
        records.sort(key=lambda item: item.get("last_observed_at", ""))
        del records[:-24]
    return dict(observed)


def recalculate_expectations(connection, config):
    """Replay recorded outcome scores, retaining each topic's original starting forecast and contextual dimensions."""
    rebuilt = {}
    contextual_scratch: dict[str, Any] = {}
    rows = connection.execute(
        """SELECT json_extract(request, '$.assessment'), json_extract(request, '$.at') FROM events
           WHERE status = 'resolved' AND json_type(request, '$.assessment') = 'object'
           ORDER BY due, rowid"""
    )
    for data, event_at in rows:
        assessment = json.loads(data)
        topic = assessment["topic"]
        observed = scores(assessment["observed"])
        prior = rebuilt.get(topic, assessment["forecast"])
        rebuilt[topic] = next_expectation(prior, observed)
        dimensions = assessment.get("dimensions")
        if isinstance(dimensions, dict) and dimensions:
            record_contextual_expectation(contextual_scratch, topic, dimensions, observed, event_at or "")
    if rebuilt:
        estimates = config.setdefault("expectations", {})
        estimates.update(rebuilt)
        if contextual_scratch.get("contextual_expectations"):
            config["contextual_expectations"] = contextual_scratch["contextual_expectations"]
        connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
        # Refresh only the active event's relevant topics, not the entire map.
        pending = connection.execute(
            "SELECT id, input, request FROM events WHERE status='pending'"
        ).fetchone()
        if pending and pending["request"]:
            active_event = json.loads(pending["input"])
            active_request = json.loads(pending["request"])
            active_request["expectations"] = relevant_expectations(
                estimates, active_event, active_request.get("recent", []))
            dimensions = expectation_dimensions(active_event)
            relation = active_request.get("relationship_state")
            if relation:
                dimensions["relationship"] = {**relation["values"], "target": resolve_relationship_target(active_event)}
            active_request["situational_expectations"] = {
                topic: contextual_forecast(config, topic, dimensions)
                for topic in active_request["expectations"]
            }
            connection.execute("UPDATE events SET request=? WHERE id=?",
                               (json.dumps(active_request, separators=(",", ":")), pending["id"]))
    return {
        "expectations": config.get("expectations", {}),
        "contextual_expectations": config.get("contextual_expectations", {}),
    }


_EPISODE_STOPWORDS = _OBSERVATION_STOPWORDS | {
    "remember", "recalled", "yesterday", "today", "tomorrow", "earlier", "later",
    "always", "really", "think", "thought", "know", "knew", "going", "went",
    "said", "told", "asked", "about", "something", "anything", "everything",
    "nothing", "someone", "anyone", "everyone", "there", "here", "doing", "done",
    "have", "having", "been", "were", "will", "would", "should", "could", "might",
    "want", "wanted", "need", "needed", "feel", "felt", "like", "just", "very",
}


def _content_tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9']+", text.casefold())
        if len(w) >= 4 and w not in _EPISODE_STOPWORDS
    }


def recall_stored_memories(connection, event, stimulus=None, limit=8):
    """Recall cue-matched durable memories stored in the SQLite memories table."""
    try:
        rows = connection.execute(
            "SELECT id, kind, summary, cues FROM memories ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    if not rows:
        return []
    stim = stimulus if isinstance(stimulus, dict) else (event.get("stimulus") or {})
    explicit_cues = {
        c.strip().casefold() for c in (stim.get("memory_cues") or [])
        if isinstance(c, str) and c.strip()
    }
    conv = stim.get("conversation") if isinstance(stim.get("conversation"), dict) else {}
    haystack = " ".join(
        str(t) for t in (message_text(event), event.get("context"), event.get("topic"), conv.get("open_topic"))
        if isinstance(t, str) and t.strip()
    ).casefold()
    if not haystack and not explicit_cues:
        return []
    matched = []
    for row in rows:
        cues = json.loads(row["cues"])
        hit = False
        for cue in cues:
            cue_lc = str(cue).strip().casefold()
            if not cue_lc:
                continue
            if cue_lc in explicit_cues or (haystack and re.search(rf"(?<!\w){re.escape(cue_lc)}(?!\w)", haystack)):
                hit = True
                break
        if hit:
            matched.append({"id": row["id"], "summary": row["summary"], "kind": row["kind"]})
            if len(matched) >= limit:
                break
    return matched


def recall_past_episodes(connection, event, before_timestamp, *, target=None, limit=4, scan_limit=500):
    """On-demand episodic recall over resolved SQLite events older than the active window."""
    stim = event.get("stimulus") if isinstance(event.get("stimulus"), dict) else {}
    conv = stim.get("conversation") if isinstance(stim.get("conversation"), dict) else {}
    query_parts = [
        message_text(event),
        event.get("context"),
        event.get("topic"),
        conv.get("open_topic"),
        *(stim.get("memory_cues") or []),
    ]
    query_text = " ".join(str(p) for p in query_parts if isinstance(p, str) and p.strip())
    query_tokens = _content_tokens(query_text)
    event_topic = event.get("topic").strip().casefold() if isinstance(event.get("topic"), str) and event.get("topic").strip() else None
    if not query_tokens and not event_topic:
        return []

    rows = connection.execute(
        """SELECT id, due, input, decision FROM events
           WHERE status = 'resolved' AND due < ?
           ORDER BY due DESC, rowid DESC LIMIT ?""",
        (before_timestamp, scan_limit),
    ).fetchall()
    if not rows:
        return []

    scored = []
    required_overlap = 1 if len(query_tokens) <= 2 else 2
    for row in rows:
        past_event = json.loads(row["input"])
        if past_event.get("kind") == "idle":
            continue
        past_decision = json.loads(row["decision"] or "{}")
        past_topic = (
            past_event.get("topic").strip().casefold()
            if isinstance(past_event.get("topic"), str) and past_event.get("topic").strip()
            else None
        )
        past_utterance = message_text(past_event)
        past_context = past_event.get("context") or ""
        past_action = past_decision.get("action") if isinstance(past_decision.get("action"), str) else ""
        past_outcome = past_decision.get("outcome") if isinstance(past_decision.get("outcome"), str) else ""
        past_reply = past_decision.get("reply") if isinstance(past_decision.get("reply"), str) else ""

        candidate_text = " ".join(
            part for part in (past_utterance, past_context, past_topic or "", past_action, past_outcome, past_reply)
            if part
        )
        candidate_tokens = _content_tokens(candidate_text)
        overlap = query_tokens & candidate_tokens
        topic_match = bool(event_topic and past_topic and event_topic == past_topic)
        if not topic_match and len(overlap) < required_overlap:
            continue

        score = (30 if topic_match else 0) + len(overlap) * 10
        past_target = resolve_relationship_target(past_event)
        if target and past_target and target == past_target:
            score += 5

        summary_bits = []
        if past_target:
            summary_bits.append(f"with {past_target}")
        if past_utterance:
            summary_bits.append(f"heard: {past_utterance[:100]}")
        elif past_context:
            summary_bits.append(past_context[:100])
        if past_reply:
            summary_bits.append(f"replied: {past_reply[:100]}")
        elif past_outcome:
            summary_bits.append(f"outcome: {past_outcome[:100]}")
        elif past_action:
            summary_bits.append(f"did: {past_action[:100]}")
        summary = "; ".join(summary_bits)[:240]
        if not summary:
            continue
        scored.append((
            score,
            row["due"],
            {
                "id": f"episode:{row['id']}",
                "kind": "episode",
                "at": datetime.fromtimestamp(row["due"], timezone.utc).isoformat(),
                "summary": summary,
            },
        ))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [entry for _, _, entry in scored[:limit]]
