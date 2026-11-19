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
            self.assertGreater(estimates["benefit"], 40)
            self.assertGreater(estimates["cost"], 30)
            assessment = requests[1]["recent"][-1]["assessment"]
            self.assertEqual(assessment["forecast"], event["expectation"])
            self.assertGreater(assessment["after"]["stress"], assessment["before"]["stress"])
            self.assertEqual(assessment["before"]["stress"],
                             original["tick"]["psychosomatic_snapshot"]["autonomic_state"]["stress"])
            with golem_loop.transaction(db) as connection:
                self.assertEqual(golem_loop.runtime_config(connection)["expectations"]["performing"], estimates)

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
