"""Exercise the persistent loop with an injected clock and no live host."""

import json
import subprocess
import sys
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import golem  # Makes the scripts directory available to the CLI modules.
from scripts import golem_loop


class TestGolemLoop(unittest.TestCase):
    def test_authored_pleasure_source_and_felt_enjoyment_are_distinct(self):
        with TemporaryDirectory() as directory:
            card = Path(directory) / "music.yaml"
            card.write_text("name: Rowan\nage: 32\ncanon_adult: true\npleasure_sources: [playing duets]\n")
            db = Path(directory) / "music.sqlite3"
            now = datetime.now(timezone.utc) - timedelta(minutes=1)
            golem_loop.initialize_character(db, card, history_at=now.isoformat())

            def hear_music(request):
                self.assertEqual(request["identity_anchor"]["pleasure_sources"], ["playing duets"])
                self.assertNotIn("pleasure", request["emotions"])
                return {"id": request["event"]["id"], "experience": {"stimulus": {"emotions": {"pleasure": 80}}}}

            result = golem_loop.wake_character(db, hear_music, compact=True, event={
                "id": "duet", "kind": "incoming", "text": "Fancy playing duets?",
                "at": now.isoformat()})
            after = result["events"][0]["body_response"]["after"]
            self.assertEqual(after["emotions"]["pleasure"], 80)
            self.assertEqual(after["sexual_arousal"], 0)

            def hear_next_bar(request):
                self.assertEqual(request["emotions"]["pleasure"], 40)
                self.assertEqual(request["body"]["sexual_arousal"], 0)
                self.assertIn("savors", request["expression_guidance"])
                return {"id": request["event"]["id"]}

            golem_loop.wake_character(db, hear_next_bar, compact=True, event={
                "id": "next", "kind": "incoming", "at": (now + timedelta(seconds=10)).isoformat()})

    def test_body_reports_both_pleasures_across_host_wakes(self):
        with TemporaryDirectory() as directory:
            card = Path(directory) / "character.yaml"
            card.write_text("name: Rowan\nage: 32\ncanon_adult: true\n"
                            "physical_pleasure_sources: [warm water]\nsexual_pleasure_sources: [private preference]\n")
            db = Path(directory) / "runtime.sqlite3"
            start = datetime.now(timezone.utc) - timedelta(minutes=5)
            golem_loop.initialize_character(db, card, history_at=start.isoformat())

            def observe(request):
                self.assertEqual(request["identity_anchor"]["physical_pleasure_sources"], ["warm water"])
                self.assertEqual(request["identity_anchor"]["sexual_pleasure_sources"], ["private preference"])
                self.assertEqual(request["body"]["physical_pleasure"], 70)
                self.assertEqual(request["body"]["sexual_pleasure"], 0)
                return {"id": "observe", "experience": {"stimulus": {"sexual_pleasure": 44}}}

            event = {"id": "observe", "kind": "incoming", "at": start.isoformat(),
                     "stimulus": {"physical_pleasure": 70}}
            first = golem_loop.wake_character(db, observe, compact=True, event=event)["events"][0]
            self.assertEqual(first["body_response"]["after"]["physical_pleasure"], 70)
            self.assertEqual(first["body_response"]["after"]["sexual_pleasure"], 44)
            self.assertEqual(first["body_response"]["after"]["sexual_arousal"], 0)

            def clear_sensation(request):
                self.assertEqual(request["body"]["physical_pleasure"], 35)
                self.assertEqual(request["body"]["sexual_pleasure"], 22)
                return {"id": "later", "experience": {"stimulus": {"physical_pleasure": 0}}}

            later = {"id": "later", "kind": "incoming", "at": (start + timedelta(minutes=2)).isoformat()}
            last = golem_loop.wake_character(db, clear_sensation, compact=True, event=later)["events"][0]
            self.assertEqual(last["body_response"]["after"]["physical_pleasure"], 0)
            self.assertEqual(last["body_response"]["after"]["sexual_pleasure"], 22)
            with golem_loop.transaction(db) as connection:
                history = golem_loop.runtime_config(connection)["history"]
                self.assertEqual((history["physical_pleasure"], history["sexual_pleasure"]), (0, 22))

    def test_orgasm_after_appraisal_is_durable_and_retry_safe(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            db, card = root / "runtime.sqlite3", root / "card.yaml"
            card.write_text("name: Rowan\nage: 30\ncanon_adult: true\n")
            start = datetime.now(timezone.utc) - timedelta(minutes=5)
            golem_loop.initialize_character(db, card, history_at=start.isoformat())
            event = {"id": "peak", "kind": "incoming", "at": start.isoformat()}

            def observe(request):
                self.assertFalse(request["body"]["orgasm"])
                return {"id": "peak", "experience": {"stimulus": {"sexual_pleasure": 90}}}

            result = golem_loop.wake_character(db, observe, compact=True, event=event)
            after = result["events"][0]["body_response"]["after"]
            self.assertTrue(after["orgasm"])
            self.assertEqual(after["orgasm_recovery"], 100)
            golem_loop.wake_character(db, self.fail, compact=True, event=event)
            with golem_loop.transaction(db) as connection:
                history = golem_loop.runtime_config(connection)["history"]
                self.assertEqual(history["last_fatigue"], after["fatigue"])

            def later(request):
                self.assertFalse(request["body"]["orgasm"])
                self.assertEqual(request["body"]["orgasm_recovery"], 80)
                return {"id": "later"}
            golem_loop.wake_character(db, later, compact=True, event={
                "id": "later", "kind": "incoming", "at": (start + timedelta(minutes=2)).isoformat()})

    def test_depiction_ceiling_uses_cast_cards_and_leaves_body_intact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            db, pack = root / "runtime.sqlite3", root / "pack.yaml"
            pack.write_text("characters:\n  a: {name: A, age: 22, canon_adult: true}\n"
                            "  b: {age: 18, canon_adult: true}\n  c: {age: 17, canon_adult: true}\n"
                            "  d: {age: 30}\n  e: {canon_adult: true}\n")
            now = datetime.now(timezone.utc) - timedelta(minutes=1)
            golem_loop.initialize_character(db, pack, slug="a", history_at=now.isoformat())
            cases = [
                ("explicit", ["a", "b"], "explicit"), ("fade_to_black", ["a"], "fade_to_black"),
                ("sfw", ["a", "b"], "sfw"), ("explicit", ["a", "b", "c"], "sfw"),
                ("explicit", ["a", "d"], "sfw"), ("explicit", ["a", "e"], "sfw"),
                ("explicit", ["a", "missing"], "sfw"), ("explicit", [], "sfw"),
                ("explicit", ["b"], "sfw"), ("explicit", None, "sfw"),
            ]
            for index, (mode, cast, expected) in enumerate(cases):
                with self.subTest(mode=mode, cast=cast):
                    def decide(request):
                        render = request["app_render"]
                        self.assertEqual(render["depiction"], expected)
                        self.assertEqual(request["event"]["depiction"], expected)
                        self.assertEqual("guide" in render, expected != "sfw")
                        self.assertEqual(golem_loop.decision_context(request)["app_render"], render)
                        body = request["tick"]["psychosomatic_snapshot"]["autonomic_state"]
                        self.assertEqual(body["physical_pleasure"], 40)
                        return {"id": request["event"]["id"]}
                    event = {"id": str(index), "at": now.isoformat(), "kind": "incoming", "depiction": mode,
                             "scene_characters": cast, "stimulus": {"physical_pleasure": 40}}
                    golem_loop.wake_character(db, decide, event=event)

    def test_unknown_actor_age_keeps_the_scene_ordinary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            card, db = root / "actor.yaml", root / "runtime.sqlite3"
            card.write_text("name: Rowan\ncanon_adult: true\nage: null\n")
            golem_loop.initialize_character(db, card)
            def decide(request):
                self.assertEqual(request["app_render"], {"depiction": "sfw"})
                return {"id": request["event"]["id"]}
            golem_loop.wake_character(db, decide, compact=True, event={
                "id": "scene", "kind": "incoming", "scene_characters": ["rowan"], "depiction": "explicit"})

    def test_transport_message_fields_survive_recall_echo_check_and_recent_history(self):
        words = "Remember the harbor before sunrise?"
        memories = {"footnote": ["older authored note", {"cues": ["harbor"]}, {"cues": ["violin"]}]}
        for data in ({"context": words}, {"text": words}, {"message": words}, {"stimulus": {"text": words}}):
            with self.subTest(data=data):
                event = {"id": "message", "kind": "incoming", "host_notes": "violin", **data}
                recent = [{"event": event, "decision": {"reply": words}}]
                self.assertEqual(golem_loop.extract_memory_cues(event, event.get("stimulus", {}), memories),
                                 ["harbor"])
                self.assertEqual(golem_loop.compact_recent_events(recent)[0]["context"], words)
                self.assertTrue(golem_loop.repeated_reply_pattern(recent)["echoing_user"])

    def test_python_retry_retrieves_exact_accepted_reply(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            first = {"id": "a", "kind": "incoming", "context": "Tea?"}
            for event, reply in ((first, "Yes please."), ({**first, "id": "b"}, "Later.")):
                golem_loop.wake_character(db, lambda r: {"id": r["event"]["id"], "reply": reply}, event=event)
            retry = golem_loop.wake_character(db, self.fail, event=first)
            self.assertEqual(retry["events"], [{"id": "a", "status": "resolved", "resolved": False,
                                                "reply": "Yes please."}])
            with golem_loop.transaction(db) as c:
                self.assertEqual(golem_loop.runtime_config(c)["history"]["event_sequence"], 2)

    def test_malformed_queued_event_cannot_block_following_message(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            bad = {"id": "old-bad", "kind": "world", "expectation_context": []}
            with self.assertRaisesRegex(ValueError, "expectation_context"):
                golem_loop.wake_character(db, self.fail, event=bad)
            with golem_loop.transaction(db) as c:
                # Simulate a row queued by a version that accepted this input.
                c.execute("INSERT INTO events(id, due, input) VALUES (?, ?, ?)",
                          (bad["id"], datetime.now(timezone.utc).timestamp(), json.dumps(bad)))
            result = golem_loop.wake_character(db, lambda r: {"id": r["event"]["id"], "reply": "Hello."},
                                               event={"id": "valid", "kind": "incoming"})
            failed, accepted = result["events"]
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(accepted["reply"], "Hello.")
            with golem_loop.transaction(db) as c:
                self.assertEqual(golem_loop.runtime_config(c)["history"]["event_sequence"], 1)

    def test_compact_cli_delivers_computed_values_and_resumes_by_id(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            loop = [sys.executable, str(golem.ROOT / "scripts/run.py"), "golem", "loop", "--db", str(db)]

            def run(args, data=None):
                result = subprocess.run(loop + args, text=True, input=json.dumps(data), capture_output=True, check=True)
                return json.loads(result.stdout)

            first = {"id": "one", "kind": "incoming", "context": "Good morning.",
                     "stimulus": {"appraisal": {"delight": 71}, "emotions": {"pride": 24}}}
            second = {"id": "two", "kind": "incoming", "context": "Going out?"}
            prepared = run(["prepare", "--event", "-"], first)
            request = prepared["request"]
            self.assertEqual(prepared["status"], "pending")
            self.assertNotIn("tick", request)
            self.assertNotIn("stimulus", request["event"])
            self.assertIn("identity_anchor", request)
            full = run(["pending"])
            affect = full["tick"]["psychosomatic_snapshot"]["affective_state"]
            body = full["tick"]["psychosomatic_snapshot"]["autonomic_state"]
            self.assertEqual(request["body"]["somatic_map"], body["somatic_map"])
            self.assertEqual(request["body"]["somatic_telemetry"], body["somatic_telemetry"])
            self.assertEqual(request["expression_guidance"], full["expression_guidance"])
            self.assertNotIn("endocrine_state", request["body"])
            self.assertEqual(request["emotions"], affect["emotions"])
            self.assertEqual(request["emotions"]["joy"], 71)
            self.assertEqual(request["emotions"]["pride"], 24)
            del affect["emotions"]
            legacy = golem_loop.decision_context(full)
            self.assertEqual(legacy["emotions"], {affect["primary_emotion"]: affect["emotional_intensity"]})
            self.assertEqual(run(["prepare", "--event", "-"], second), prepared)
            self.assertEqual(run(["prepare"]), prepared)
            decision = {"id": "one", "reply": "Coffee?"}
            receipt = run(["resolve", "--receipt", "-"], decision)
            self.assertEqual(receipt, {"status": "resolved", **decision})
            self.assertEqual(run(["resolve", "--receipt", "-"], decision), receipt)
            self.assertEqual(run(["prepare", "--event", "-"], first), receipt)
            second_request = run(["prepare", "--event", "-"], second)["request"]
            self.assertEqual(second_request["event"]["id"], "two")
            self.assertIn("pride", second_request["emotions"])
            self.assertNotIn("reply", run(["resolve", "--receipt", "-"], {"id": "two"}))
            self.assertEqual(run(["prepare"]), {"status": "sleeping"})

    def test_prepare_preserves_incoming_boundary_screen(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            card = Path(directory) / "character.yaml"
            card.write_bytes((golem.ROOT / "Characters/_template.yaml").read_bytes())
            golem_loop.initialize_character(db, card, owned_files=[card])
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"id": "incoming", "kind": "incoming"}))
            with self.assertRaisesRegex(ValueError, "boundary assessment"):
                golem_loop.execute(db, Namespace(command="prepare", event=event))
            with golem_loop.transaction(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)

    def test_compact_python_callback_keeps_character_choice(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            seen = []

            def decide(request):
                seen.append(request["emotions"]["anger"])
                self.assertNotIn("tick", request)
                return {"id": request["event"]["id"]}

            event = {"kind": "incoming", "id": "news", "stimulus": {"appraisal": {"frustration": 84}}}
            result = golem_loop.wake_character(db, decide, compact=True, event=event)
            self.assertEqual(seen, [84])
            self.assertNotIn("reply", result["events"][0])

    def test_character_can_adopt_revise_and_clear_dialect(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            turns = [(None, {"dialect": "Scots at home"}), ("Scots at home", {}),
                     ("Scots at home", {"dialect": "Mostly Glaswegian"}),
                     ("Mostly Glaswegian", {"dialect": None}), (None, {})]
            for i, (expected, change) in enumerate(turns):
                def decide(request):
                    self.assertEqual(request["dialect"], expected)
                    return {"id": request["event"]["id"], **change}
                golem_loop.wake_character(db, decide, event={"kind": "incoming", "id": str(i)})

    def test_incoming_host_receives_private_context_separately_on_retry(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            event = {"kind": "incoming", "id": "visitor", "context": "I used to live near here.",
                     "host_notes": "The character remembers her brother leaving town."}

            def interrupted(request):
                raise RuntimeError("host interrupted")

            with self.assertRaisesRegex(RuntimeError, "host interrupted"):
                golem_loop.wake_character(db, interrupted, event=event)

            def resume(request):
                self.assertEqual(request["event"], event)
                self.assertEqual(set(request["reply_guidance"]), {"stance", "disclosure"})
                return {"id": "visitor", "reply": "Which street?"}

            result = golem_loop.wake_character(db, resume)
            self.assertEqual(result["events"][0]["reply"], "Which street?")

    def test_idle_decision_schedules_a_plan_that_survives_restart(self):
        start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            args = Namespace(
                card=golem.ROOT / "Characters" / "_template.yaml", slug=None, log=None,
                import_history=None, history_at=None, idle_seconds=60,
            )
            with golem_loop.transaction(db) as connection:
                golem_loop.setup(connection, args, start)
            with golem_loop.transaction(db) as connection:
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertEqual(golem_loop.advance(connection, config, start)["status"], "sleeping")
                first = golem_loop.advance(connection, config, start + timedelta(minutes=1))
                self.assertEqual(first["status"], "pending")

            with golem_loop.transaction(db) as connection:
                request = golem_loop.pending_request(connection)
                self.assertEqual(request["event"]["kind"], "idle")
                self.assertNotIn("reply_guidance", request)
                self.assertEqual(request["tick"]["golem_meta"]["elapsed_ms"], 60_000)
                history = request["tick"]["next_history"]
                self.assertEqual(golem_loop.advance(connection, config, start + timedelta(minutes=2))["status"],
                                 "waiting_for_host")
                decision = {
                    "id": first["id"], "action": "Starts practicing piano.",
                    "outcome": "Leaves a difficult passage for later.",
                    "learning": {"topic": "Piano", "observation": "Practicing hands separately helps."},
                    "plans": [{
                        "id": "practice", "at": (start + timedelta(minutes=2)).isoformat(),
                        "context": "Return to the difficult passage.", "topic": "piano",
                    }],
                }
                self.assertTrue(golem_loop.resolve(connection, decision, history, start)["resolved"])
                self.assertFalse(golem_loop.resolve(connection, decision, history, start)["resolved"])

            with golem_loop.transaction(db) as connection:
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                event = {
                    "id": "back-home", "kind": "incoming",
                    "at": (start + timedelta(minutes=3)).isoformat(),
                }
                self.assertTrue(golem_loop.enqueue(connection, event, config["history"], start)["queued"])
                self.assertFalse(golem_loop.enqueue(connection, event, config["history"], start)["queued"])
                self.assertEqual(golem_loop.advance(connection, config, start + timedelta(minutes=3))["id"],
                                 "practice")
                request = golem_loop.pending_request(connection)
                self.assertEqual(request["recent"][0]["action"], decision["action"])
                self.assertEqual(request["learned"], [{**decision["learning"], "event_id": first["id"]}])
                self.assertEqual(request["tick"]["next_history"]["event_sequence"], 2)
                golem_loop.resolve(connection, {"id": "practice"}, request["tick"]["next_history"], start)
                self.assertEqual(golem_loop.advance(connection, config, start + timedelta(minutes=3))["id"],
                                 "back-home")

    def test_maintenance_pressure_is_advisory_and_meal_updates_hunger_once(self):
        start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            args = Namespace(card=golem.ROOT / "Characters" / "_template.yaml", slug=None, log=None,
                             import_history=None, history_at=None, idle_seconds=60)
            with golem_loop.transaction(db) as connection:
                golem_loop.setup(connection, args, start)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                config["history"].update(hunger=65)
                connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
                result = golem_loop.advance(connection, config, start + timedelta(seconds=60))
                request = golem_loop.pending_request(connection)
                self.assertEqual(request["maintenance_needs"]["hunger"], 65)
                self.assertTrue(request["maintenance_needs"]["suggested_evaluation"])
                self.assertTrue(request["behavior_guidance"]["body_pressure_is_not_an_action_order"])
                self.assertIn("mirror", request["behavior_guidance"]["avoid_automatic_echo_or_repetition"])
                decision = {"id": result["id"], "action": "Chooses to eat after finishing work.",
                            "experience": {"food_intake": 30}}
                golem_loop.resolve(connection, decision, request["tick"]["next_history"], start)
                stored = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertAlmostEqual(stored["history"]["hunger"], 35 + 4 / 60)

    def test_repeated_action_pattern_is_reported_without_rewriting_decisions(self):
        events = [
            {"decision": {"action": "Keeps arranging the papers."}},
            {"decision": {"action": "Keeps arranging the papers!"}},
        ]
        pattern = golem_loop.repeated_action_pattern(events)
        self.assertTrue(pattern["repeated"])
        self.assertEqual(pattern["consecutive_count"], 2)
        self.assertEqual(pattern["action"], "keeps arranging the papers")

    def test_duration_activity_recovers_after_restart_and_completes_once(self):
        start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            db = Path(directory) / "persistent" / "character.sqlite3"
            db.parent.mkdir()
            args = Namespace(card=golem.ROOT / "Characters" / "_template.yaml", slug=None, log=None,
                             import_history=None, history_at=None, idle_seconds=3600)
            with golem_loop.transaction(db) as connection:
                golem_loop.setup(connection, args, start)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                golem_loop.enqueue(connection, {"id": "sleep-start", "kind": "world"},
                                   config["history"], start)
                golem_loop.advance(connection, config, start)
                request = golem_loop.pending_request(connection)
                golem_loop.resolve(connection, {
                    "id": "sleep-start", "action": "Chooses to sleep.",
                    "activity": {"op": "start", "id": "overnight", "kind": "sleep",
                                 "state": "sleeping", "duration_seconds": 8 * 3600},
                }, request["tick"]["next_history"], start)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertEqual(config["history"]["activity"], "sleeping")
                activity_row = connection.execute(
                    "SELECT status,duration_seconds FROM activities WHERE id='overnight'").fetchone()
                self.assertEqual((activity_row["status"], activity_row["duration_seconds"]),
                                 ("active", 8 * 3600))

            # Reopen the persistent database as a replacement VM would.
            due = start + timedelta(hours=8)
            with golem_loop.transaction(db) as connection:
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                result = golem_loop.advance(connection, config, due)
                self.assertEqual(result["status"], "pending")
                request = golem_loop.pending_request(connection)
                self.assertEqual(request["activity"]["status"], "due")
                self.assertEqual(request["tick"]["next_history"]["sleep_debt"], 0)
                completion = {"id": result["id"], "activity": {"op": "complete", "id": "overnight"}}
                first = golem_loop.resolve(connection, completion, request["tick"]["next_history"], due)
                again = golem_loop.resolve(connection, completion, request["tick"]["next_history"], due)
                self.assertTrue(first["resolved"])
                self.assertFalse(again["resolved"])
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertEqual(config["history"]["activity"], "awake")
                row = connection.execute("SELECT status,start_event_id,end_event_id FROM activities WHERE id='overnight'").fetchone()
                self.assertEqual((row["status"], row["start_event_id"], row["end_event_id"]),
                                 ("completed", "sleep-start", result["id"]))

    def test_interrupted_activity_can_resume_after_restart(self):
        start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            args = Namespace(card=golem.ROOT / "Characters" / "_template.yaml", slug=None, log=None,
                             import_history=None, history_at=None, idle_seconds=3600)
            with golem_loop.transaction(db) as connection:
                golem_loop.setup(connection, args, start)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                golem_loop.enqueue(connection, {"id": "rest-start", "kind": "world"}, config["history"], start)
                golem_loop.advance(connection, config, start)
                request = golem_loop.pending_request(connection)
                golem_loop.resolve(connection, {"id": "rest-start", "activity": {
                    "op": "start", "id": "break", "kind": "rest", "state": "resting",
                    "duration_seconds": 3600}}, request["tick"]["next_history"], start)
                interrupt_at = start + timedelta(minutes=20)
                golem_loop.enqueue(connection, {"id": "interruption", "kind": "incoming",
                                                "at": interrupt_at.isoformat(), "context": "A call arrives."},
                                   json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])["history"],
                                   interrupt_at)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                result = golem_loop.advance(connection, config, interrupt_at)
                request = golem_loop.pending_request(connection)
                golem_loop.resolve(connection, {"id": result["id"], "activity": {
                    "op": "interrupt", "id": "break", "state": "awake"}},
                    request["tick"]["next_history"], interrupt_at)
                row = connection.execute("SELECT status FROM activities WHERE id='break'").fetchone()
                self.assertEqual(row[0], "interrupted")
                due_status = connection.execute("SELECT status FROM events WHERE id='activity:break:due:1'").fetchone()[0]
                self.assertEqual(due_status, "cancelled")

            resume_at = start + timedelta(minutes=25)
            with golem_loop.transaction(db) as connection:
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                golem_loop.enqueue(connection, {"id": "resume-break", "kind": "world",
                                                "at": resume_at.isoformat()}, config["history"], resume_at)
                result = golem_loop.advance(connection, config, resume_at)
                request = golem_loop.pending_request(connection)
                golem_loop.resolve(connection, {"id": result["id"], "activity": {
                    "op": "resume", "id": "break", "duration_seconds": 900}},
                    request["tick"]["next_history"], resume_at)
                row = connection.execute("SELECT status,revision FROM activities WHERE id='break'").fetchone()
                self.assertEqual((row["status"], row["revision"]), ("active", 2))

    def test_completed_meal_effect_is_applied_once_and_old_database_migrates(self):
        start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            args = Namespace(card=golem.ROOT / "Characters" / "_template.yaml", slug=None, log=None,
                             import_history=None, history_at=None, idle_seconds=3600)
            with golem_loop.transaction(db) as connection:
                golem_loop.setup(connection, args, start)
                config = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                config["history"]["hunger"] = 50
                connection.execute("UPDATE runtime SET data=? WHERE id=1", (json.dumps(config),))
                golem_loop.enqueue(connection, {"id": "meal-start", "kind": "world"}, config["history"], start)
                golem_loop.advance(connection, config, start)
                request = golem_loop.pending_request(connection)
                golem_loop.resolve(connection, {"id": "meal-start", "activity": {
                    "op": "start", "id": "meal-1", "kind": "meal", "state": "awake",
                    "duration_seconds": 1800, "data": {"effects": {"food_intake": 30}}}},
                    request["tick"]["next_history"], start)
                stored = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertEqual(stored["history"]["hunger"], 50)
                due = start + timedelta(minutes=30)
                config = stored
                event = golem_loop.advance(connection, config, due)
                request = golem_loop.pending_request(connection)
                decision = {"id": event["id"], "activity": {"op": "complete", "id": "meal-1"}}
                golem_loop.resolve(connection, decision, request["tick"]["next_history"], due)
                after = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                value = after["history"]["hunger"]
                self.assertAlmostEqual(value, 50 + 4 * 0.5 - 30)
                golem_loop.resolve(connection, decision, request["tick"]["next_history"], due)
                repeated = json.loads(connection.execute("SELECT data FROM runtime").fetchone()["data"])
                self.assertEqual(repeated["history"]["hunger"], value)

            # An old runtime can acquire the activity table without resetting state.
            with golem_loop.transaction(db) as connection:
                connection.execute("DROP TABLE activities")
            result = golem_loop.execute(db, Namespace(command="status"))
            self.assertEqual(result["history"]["hunger"], value)
            with golem_loop.transaction(db) as connection:
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='activities'").fetchone())

    def test_host_retry_and_independent_benefit_and_cost(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            event = {"id": "attempt", "kind": "world", "topic": "performing",
                     "expectation": {"benefit": 40, "cost": 30},
                     "stimulus": {"food_intake": 10, "appraisal": {"unease": 40}}}

            def fail(request):
                raise RuntimeError("host unavailable")

            with self.assertRaisesRegex(RuntimeError, "host unavailable"):
                golem_loop.wake_character(db, fail, event=event)
            with golem_loop.transaction(db) as connection:
                original = golem_loop.pending_request(connection)

            def decide(request):
                self.assertEqual(request, original)
                return {"id": "attempt", "experience": {"benefit": 75, "cost": 60,
                        "appraisal": {"interest": 80, "unease": 70}},
                        "plans": [{"id": "retry", "topic": "performing", "at": request["at"]}]}

            requests = []

            def host(request):
                requests.append(request)
                if request["event"]["id"] == "attempt":
                    return decide(request)
                return {"id": "retry"}

            golem_loop.wake_character(db, host, event=event)
            self.assertEqual([r["event"]["id"] for r in requests], ["attempt", "retry"])
            estimates = requests[1]["expectations"]["performing"]
            self.assertEqual(estimates, {"benefit": 48.75, "cost": 37.5})
            self.assertEqual(requests[1]["recent"][-1]["forecast"], event["expectation"])
            with golem_loop.transaction(db) as connection:
                assessment = golem_loop.recent_events(connection)[0]["assessment"]
                self.assertGreater(assessment["after"]["stress"], assessment["before"]["stress"])
                self.assertEqual(assessment["before"]["stress"],
                                 original["tick"]["psychosomatic_snapshot"]["autonomic_state"]["stress"])
                config = golem_loop.runtime_config(connection)
                self.assertEqual(config["expectations"]["performing"], estimates)
                self.assertEqual(config["history"]["event_sequence"], 2)

    def test_strong_reaction_to_low_stakes_outcome(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            for turn, observed in enumerate([{"benefit": 5, "cost": 2}, {"benefit": 1, "cost": 0}]):
                event = {"id": str(turn), "topic": "rehearsal", "kind": "world"}
                golem_loop.wake_character(db, lambda request: {
                    "id": request["event"]["id"],
                    "experience": {**observed, "appraisal": {"interest": 80, "unease": 80}},
                }, event=event)
            with golem_loop.transaction(db) as connection:
                first, second = [row["assessment"] for row in golem_loop.recent_events(connection)]
            self.assertGreater(first["after"]["stress"], first["before"]["stress"])
            self.assertEqual(first["next_expectation"], {"benefit": 5, "cost": 2})
            self.assertEqual(second["next_expectation"], {"benefit": 4, "cost": 1.5})

    def test_overlapping_host_wakes_deliver_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        with TemporaryDirectory() as directory:
            db = Path(directory) / "runtime.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            entered, release = Event(), Event()
            deliveries = []

            def host(request):
                event_id = request["event"]["id"]
                deliveries.append(event_id)
                if event_id == "first":
                    entered.set()
                    self.assertTrue(release.wait(5))
                return {"id": event_id}

            with ThreadPoolExecutor(max_workers=2) as pool:
                def wake(event_id):
                    return golem_loop.wake_character(db, host, event={"id": event_id, "kind": "incoming"})
                first = pool.submit(wake, "first")
                self.assertTrue(entered.wait(5))
                second = pool.submit(wake, "second")
                release.set()
                first.result(timeout=5)
                second.result(timeout=5)
            self.assertEqual(deliveries, ["first", "second"])

    def test_decline_and_revise_card_echo_without_replaying_tick(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            card_path = Path(directory) / "card.yaml"
            card_path.write_text(
                "name: Rowan\nvoice:\n  baseline: Counts the minutes until the last train leaves town.\n"
                "  signature_tics: ['Put a pin in it until the next train.']\n"
            )
            golem_loop.initialize_character(db, card_path)
            event = {"id": "favor", "kind": "incoming", "stimulus": {
                "conversation": {"open_topic": "trains", "willing_to_help": False},
                "appraisal": {"interest": 90},
            }}
            with self.assertRaisesRegex(ValueError, "voice.baseline"):
                golem_loop.wake_character(db, lambda req: {
                    "id": "favor", "reply": "Counts the minutes until THE LAST TRAIN leaves town!",
                }, event=event)
            with golem_loop.transaction(db) as connection:
                request = golem_loop.pending_request(connection)
                self.assertEqual(request["tick"]["conversation_intent"]["intent"], "decline")
                self.assertEqual(request["tick"]["golem_meta"]["pressure_tier"], "Low")

            outcome = golem_loop.wake_character(db, lambda req: {"id": "favor", "reply": "Ask me tomorrow."})
            self.assertEqual(outcome["events"][0]["reply"], "Ask me tomorrow.")
            with golem_loop.transaction(db) as connection:
                self.assertEqual(golem_loop.runtime_config(connection)["history"]["event_sequence"], 1)
                self.assertEqual(golem_loop.recent_events(connection, 1)[0]["decision"]["reply"],
                                 "Ask me tomorrow.")
            self.assertIsNone(golem_loop.copied_card_field(
                golem.load_character(card_path, None), "Put a pin in it until the next train."))

    def test_boundary_end_and_repeat_deletion_are_distinct(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            card, log, db = root / "character.yaml", root / "log.yaml", root / "runtime.sqlite3"
            card.write_text("name: Rowan")
            log.write_text("memories: {}")
            neighbor = root / "other.yaml"
            neighbor.write_text("name: Another")
            golem_loop.initialize_character(db, card, log=log, owned_files=[card, log])

            def send(actor, message, screen):
                return golem_loop.wake_character(
                    db, lambda _: self.fail("Unexpected character tick"),
                    event={"kind": "incoming", "id": message}, actor_id=actor, screen_abuse=screen,
                )

            def boundary(event, context):
                self.assertIsNone(context["previous_boundary"])
                return {"action": "set_boundary", "reply": "Leave that subject alone."}

            self.assertEqual(send("a", "1", boundary)["status"], "boundary")
            self.assertEqual(send("a", "1", boundary)["status"], "boundary")
            allowed = golem_loop.wake_character(db, lambda req: {
                "id": req["event"]["id"], "learning": {"topic": "music", "observation": "a private lesson"},
                "activity": {"op": "start", "id": "practice", "kind": "practice",
                             "state": "awake", "duration_seconds": 3600},
            }, event={"kind": "incoming", "id": "normal"}, actor_id="a", screen_abuse=lambda *_: None)
            self.assertTrue(allowed["events"][0]["resolved"])
            with golem_loop.transaction(db) as connection:
                self.assertEqual(golem_loop.compact_event_requests(connection, apply=True)["eligible"], 1)

            def end(event, context):
                self.assertEqual(context["previous_boundary"]["reply"], "Leave that subject alone.")
                return {"action": "end_session"}

            self.assertEqual(send("a", "2", end)["status"], "ended")
            self.assertEqual(golem_loop.wake_character(db, self.fail)["status"], "ended")
            self.assertEqual(send("a", "2", end)["status"], "ended")
            self.assertEqual(send("b", "3", lambda *_: {"action": "end_session"})["status"], "ended")
            self.assertTrue(card.exists() and log.exists())
            self.assertEqual(send("a", "4", end)["status"], "deleted")
            self.assertFalse(card.exists() or log.exists())
            self.assertTrue(neighbor.is_file())
            self.assertEqual(golem_loop.wake_character(db, self.fail)["status"], "deleted")
            with golem_loop.transaction(db) as connection:
                self.assertEqual(golem_loop.runtime_config(connection), {"lifecycle": "deleted"})
                for table in ("events", "observations", "activities", "request_archive"):
                    self.assertEqual(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
                # Old versions could already have marked an installation deleted.
                connection.execute("INSERT INTO request_archive VALUES ('old-private', X'00')")
            self.assertEqual(golem_loop.wake_character(db, self.fail)["status"], "deleted")
            with golem_loop.transaction(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM request_archive").fetchone()[0], 0)

    def test_repeated_reports_cannot_delete_unregistered_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            card = root / "character.yaml"
            card.write_text("name: Rowan")
            db = root / "runtime.sqlite3"
            golem_loop.initialize_character(db, card)
            for incident in ("first", "second"):
                self.assertEqual(golem_loop.report_abuse(db, actor_id="a", event_id=incident)["status"], "ended")
            self.assertTrue(card.is_file())

    def test_interrupted_deletion_resumes_on_next_wake(self):
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            root = Path(directory)
            card, log, db = root / "a.yaml", root / "b.yaml", root / "runtime.sqlite3"
            card.write_text("name: Rowan")
            log.write_text("memories: {}")
            golem_loop.initialize_character(db, card, log=log, owned_files=[card, log])
            golem_loop.report_abuse(db, actor_id="a", event_id="first")
            unlink = Path.unlink

            def fail_second(path, **kwargs):
                if path == log:
                    raise OSError("Interrupted")
                return unlink(path, **kwargs)

            with patch.object(Path, "unlink", fail_second), self.assertRaises(OSError):
                golem_loop.report_abuse(db, actor_id="a", event_id="second")
            with golem_loop.transaction(db) as connection:
                self.assertEqual(golem_loop.runtime_config(connection)["lifecycle"], "deleting")
            self.assertTrue(log.exists())
            self.assertEqual(golem_loop.wake_character(db, self.fail)["status"], "deleted")
            self.assertFalse(card.exists() or log.exists())

    def test_two_hour_memory_window_enforcement_rules_and_cue_recall(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            card = root / "character.yaml"
            log = root / "character_log.yaml"
            db = root / "runtime.sqlite3"
            card.write_text(
                "name: Rowan\n"
                "character_id: rowan\n"
                "voice:\n"
                "  baseline: Direct and dry\n"
                "  hard_bans:\n"
                "    - Therapy jargon\n"
            )
            log.write_text(
                "schema_version: 2\n"
                "revision: 1\n"
                "memories:\n"
                "  detailed:\n"
                "    - id: mem_harbor\n"
                "      summary: Met at the old harbor pier.\n"
                "      reason: Anchors trust.\n"
                "      cues: [harbor, pier]\n"
                "    - id: mem_violin\n"
                "      summary: Broke a violin string before opening night.\n"
                "      reason: Sore spot.\n"
                "      cues: [violin]\n"
            )
            start = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, log=log, history_at=start.isoformat())

            seen_requests = []

            def decide(req):
                seen_requests.append(req)
                return {"id": req["event"]["id"], "action": "Responds.", "reply": "Noted."}

            golem_loop.wake_character(
                db, decide,
                event={"id": "e1", "kind": "incoming", "at": (start + timedelta(minutes=10)).isoformat(), "text": "Hello"},
            )
            golem_loop.wake_character(
                db, decide,
                event={"id": "e2", "kind": "incoming", "at": (start + timedelta(hours=1)).isoformat(), "text": "Still here"},
            )
            golem_loop.wake_character(
                db, decide,
                event={
                    "id": "e3", "kind": "incoming",
                    "at": (start + timedelta(hours=2, minutes=30)).isoformat(),
                    "text": "Remember the harbor?",
                },
            )

            latest = seen_requests[-1]
            self.assertEqual(latest["active_memory_window_seconds"], 7200)
            recent_ids = [entry["id"] for entry in latest["recent"]]
            self.assertEqual(recent_ids, ["e2"])
            recalled_ids = [m["id"] for m in latest.get("recalled_memories", [])]
            self.assertEqual(recalled_ids, ["mem_harbor"])
            rules = latest["behavior_guidance"]["enforcement_rules"]
            self.assertIn("identity_lock", rules)
            self.assertIn("hard_bans", rules)
            self.assertIn("anti_echo_and_presence", rules)
            self.assertIn("memory_and_state_boundaries", rules)
            self.assertIn("pre_output_check", rules)
