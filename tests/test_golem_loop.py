"""Exercise the persistent loop with an injected clock and no live host."""

import json
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import golem  # Makes the scripts directory available to the CLI modules.
from scripts import golem_loop


class TestGolemLoop(unittest.TestCase):
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
                self.assertEqual(request["recent"][0]["decision"]["action"], decision["action"])
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
            assessment = requests[1]["recent"][-1]["assessment"]
            self.assertEqual(assessment["forecast"], event["expectation"])
            self.assertGreater(assessment["after"]["stress"], assessment["before"]["stress"])
            self.assertEqual(assessment["before"]["stress"],
                             original["tick"]["psychosomatic_snapshot"]["autonomic_state"]["stress"])
            with golem_loop.transaction(db) as connection:
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
            }, event={"kind": "incoming", "id": "normal"}, actor_id="a", screen_abuse=lambda *_: None)
            self.assertTrue(allowed["events"][0]["resolved"])

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
                for table in ("events", "observations"):
                    self.assertEqual(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

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
            recent_ids = [entry["event"]["id"] for entry in latest["recent"]]
            self.assertEqual(recent_ids, ["e2"])
            recalled_ids = [m["id"] for m in latest.get("recalled_memories", [])]
            self.assertEqual(recalled_ids, ["mem_harbor"])
            rules = latest["behavior_guidance"]["enforcement_rules"]
            self.assertIn("identity_lock", rules)
            self.assertIn("hard_bans", rules)
            self.assertIn("anti_echo_and_presence", rules)
            self.assertIn("memory_and_state_boundaries", rules)
            self.assertIn("pre_output_check", rules)
