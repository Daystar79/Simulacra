"""Persistent cue lookup and salience for one character's memories."""
import json
import re
from datetime import datetime, timezone


def key_point(summary):
    sentence = re.split(r"(?<=[.!?])\s+|\n", summary.strip(), maxsplit=1)[0]
    if len(sentence) <= 160:
        return sentence
    return sentence[:159].rsplit(" ", 1)[0] + "…"


def retention_fields(entry):
    result = {}
    for field in ("emotional_intensity", "physical_intensity"):
        if field not in entry:
            continue
        weight = entry[field]
        if type(weight) is not int or not 0 <= weight <= 100:
            raise ValueError(f"Memory {field} must be an integer from 0 to 100")
        result[field] = weight
    if "remember_by_choice" in entry:
        if type(entry["remember_by_choice"]) is not bool:
            raise ValueError("Memory remember_by_choice must be boolean")
        result["remember_by_choice"] = entry["remember_by_choice"]
    if "key_point" in entry:
        point = entry["key_point"]
        if not isinstance(point, str) or not 1 <= len(point.strip()) <= 240:
            raise ValueError("Memory key_point must contain 1–240 characters")
        result["key_point"] = point.strip()
    return result


def physical_intensity(body):
    """Salience of the strongest registered sensation at encoding."""
    regional = (level for sensations in body.get("somatic_map", {}).values() for level in sensations.values())
    return max(body.get("physical_pain", 0), body.get("physical_pleasure", 0),
               body.get("sexual_pleasure", 0), max(regional, default=0))


def index_entry(db, entry, source, recorded):
    ident = entry["id"]
    db.execute("DELETE FROM memory_cues WHERE memory_id=?", (ident,))
    db.execute("""INSERT OR REPLACE INTO recall_cards
        (id,source,kind,summary,point,emotional_intensity,recorded,physical_intensity,remember_by_choice) VALUES(?,?,?,?,?,?,?,?,?)""",
        (ident, source, entry["kind"], entry["summary"], entry.get("key_point") or key_point(entry["summary"]),
         entry.get("emotional_intensity", 50), recorded, entry.get("physical_intensity", 0), entry.get("remember_by_choice", False)))
    rows = []
    for cue in entry["cues"]:
        cue = cue.strip().casefold()
        if cue:
            words = re.findall(r"\w+", cue)
            anchor = max(words, key=len) if words else cue[0]
            rows.append((ident, cue, anchor))
    db.executemany("INSERT OR IGNORE INTO memory_cues VALUES(?,?,?)", rows)


def ensure_schema(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='recall_cards'").fetchone():
        columns = {r[1] for r in db.execute("PRAGMA table_info(recall_cards)")}
        for name in ("physical_intensity", "remember_by_choice"):
            if name not in columns:
                db.execute(f"ALTER TABLE recall_cards ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
                db.execute("DELETE FROM authored_recall_version")
        return
    db.execute("""CREATE TABLE recall_cards(id TEXT PRIMARY KEY, source TEXT, kind TEXT,
        summary TEXT, point TEXT, emotional_intensity INTEGER, recorded REAL, physical_intensity INTEGER DEFAULT 0, remember_by_choice INTEGER DEFAULT 0)""")
    db.execute("""CREATE TABLE memory_cues(memory_id TEXT, cue TEXT, anchor TEXT,
        PRIMARY KEY(memory_id,cue))""")
    db.execute("CREATE INDEX cue_anchors ON memory_cues(anchor,cue)")
    db.execute("CREATE INDEX cue_matches ON memory_cues(cue,memory_id)")
    db.execute("CREATE TABLE authored_recall_version(id INTEGER PRIMARY KEY, stamp TEXT)")
    db.execute("CREATE TABLE notebook(event_id TEXT PRIMARY KEY, at TEXT, note TEXT, searchable TEXT)")
    has_events = db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone()
    # Older saves used wall time for created_at. Prefer the event's scene clock.
    timestamp = "CASE WHEN typeof(m.created_at) IN ('integer','real') THEN m.created_at ELSE unixepoch(m.created_at) END"
    query = (f"SELECT m.*,coalesce(e.due,{timestamp}) AS recorded, "
             "coalesce(json_extract(e.request,'$.emotional_intensity'),json_extract(e.request,'$.tick.psychosomatic_snapshot.affective_state.emotional_intensity')) AS intensity FROM memories m "
             "LEFT JOIN events e ON e.id=m.event_id" if has_events else
             f"SELECT m.*,{timestamp} AS recorded,NULL AS intensity FROM memories m")
    for row in db.execute(query):
        index_entry(db, {**dict(row), "emotional_intensity": row["intensity"] if row["intensity"] is not None else 50, "cues": json.loads(row["cues"])}, "stored", row["recorded"])


def sync_authored(db, memories, stamp):
    prior = db.execute("SELECT stamp FROM authored_recall_version WHERE id=1").fetchone()
    if prior and prior[0] == stamp:
        return
    db.execute("DELETE FROM memory_cues WHERE memory_id IN (SELECT id FROM recall_cards WHERE source='yaml')")
    db.execute("DELETE FROM recall_cards WHERE source='yaml'")
    stored = {r[0] for r in db.execute("SELECT id FROM memories")}
    for kind in ("detailed", "footnote", "dream"):
        for entry in memories.get(kind) or []:
            if (isinstance(entry, dict) and isinstance(entry.get("id"), str)
                    and isinstance(entry.get("summary"), str) and entry["id"] not in stored):
                recorded = datetime.fromisoformat(entry["at"]).timestamp() if entry.get("at") else None
                index_entry(db, {**entry, "kind": kind, "cues": entry.get("cues") or []}, "yaml", recorded)
    db.execute("INSERT OR REPLACE INTO authored_recall_version VALUES(1,?)", (stamp,))


def ranked(db, haystack, explicit, at, limit):
    matched = set(explicit)
    if haystack:
        anchors = set(re.findall(r"\w+|[^\w\s]", haystack))
        for cue, in db.execute("""SELECT DISTINCT cue FROM memory_cues
                WHERE anchor IN (SELECT value FROM json_each(?))""", (json.dumps(sorted(anchors)),)):
            if re.search(r"(?<!\w)" + re.escape(cue) + r"(?!\w)", haystack):
                matched.add(cue)
    if not matched:
        return []
    now = datetime.fromisoformat(at).timestamp() if at else datetime.now(timezone.utc).timestamp()
    rows = db.execute("""SELECT c.*, max(emotional_intensity,physical_intensity,85*remember_by_choice) AS strength, max(0,(? - recorded)/86400.0) AS days FROM recall_cards c
        WHERE id IN (SELECT memory_id FROM memory_cues WHERE cue IN (SELECT value FROM json_each(?)))
        ORDER BY strength DESC,
                 recorded DESC, c.rowid DESC LIMIT ?""", (now, json.dumps(sorted(matched)), limit))
    result = []
    for row in rows:
        brief = (row["days"] is None or row["days"] >= 14) and row["strength"] < 80
        result.append({"id": row["id"], "kind": row["kind"],
                       "summary": row["point"] if brief else row["summary"],
                       "emotional_intensity": row["emotional_intensity"],
                       "physical_intensity": row["physical_intensity"], "remember_by_choice": bool(row["remember_by_choice"]),
                       "strength": row["strength"],
                       "at": datetime.fromtimestamp(row["recorded"], timezone.utc).isoformat() if row["recorded"] is not None else None,
                       **({"detail": "key_point"} if brief else {})})
    return result


def use_notebook(db, command, event_id, at):
    if not isinstance(command, dict) or set(command) not in ({"write"}, {"read"}):
        raise ValueError("notebook requires either write (note text) or read (search text)")
    if "write" in command:
        note = command["write"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise ValueError("Notebook entry must contain 1–4000 characters")
        db.execute("INSERT INTO notebook VALUES(?,?,?,?)", (event_id, at, note, note.casefold()))
        return None
    query = command["read"]
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Notebook search must be text of at most 200 characters")
    rows = db.execute("""SELECT event_id,at,note FROM notebook WHERE instr(searchable,?)>0
        ORDER BY at DESC,rowid DESC LIMIT 5""", (query.strip().casefold(),))
    return {"query": query, "entries": [dict(row) for row in rows]}
