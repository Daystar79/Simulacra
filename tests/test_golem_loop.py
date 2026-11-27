"""Exercise the persistent loop with an injected clock and no live host."""

import json
import sqlite3
import subprocess
import sys
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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
                # At rest the compact body omits the field: absent means 0.
                self.assertEqual(request["body"].get("sexual_arousal", 0), 0)
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
                self.assertEqual(request["body"].get("sexual_pleasure", 0), 0)
                return {"id": "observe", "experience": {"stimulus": {"sexual_pleasure": 44}}}

            event = {"id": "observe", "kind": "incoming", "at": start.isoformat(),
                     "stimulus": {"physical_pleasure": 70}}
            first = golem_loop.wake_character(db, observe, compact=True, event=event)["events"][0]
            self.assertEqual(first["body_response"]["after"]["physical_pleasure"], 70)
            self.assertEqual(first["body_response"]["after"]["sexual_pleasure"], 44)
            # Direct stimulation of a private preference raises a modest genital
            # response on its own (tactile_excitation, default gain 0.5): the body
            # responds to touch without an interpersonal attraction appraisal.
            self.assertEqual(first["body_response"]["after"]["sexual_arousal"], 22)

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
                self.assertFalse(request["body"].get("orgasm", False))
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
                self.assertFalse(request["body"].get("orgasm", False))
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
                    golem_loop.wake_character(db, decide, compact=False, event=event)

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

    def test_compact_is_the_default_and_omits_resting_body_values(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            seen = []

            def decide(request):
                seen.append(request)
                return {"id": request["event"]["id"]}

            # No compact flag: the default already delivers the compact context.
            golem_loop.wake_character(db, decide, event={"kind": "incoming", "id": "quiet",
                                                        "stimulus": {"appraisal": {"interest": 30}}})
            self.assertEqual(len(seen), 1)
            request = seen[0]
            self.assertNotIn("tick", request)
            self.assertIn("winning_drive", request)
            body = request["body"]
            # At rest, markers at their resting value are absent, not zero.
            self.assertNotIn("sexual_arousal", body)
            self.assertNotIn("lingering_arousal", body)
            self.assertIn("activity", body)
            self.assertGreater(body["arousal"], 0)  # Appraised interest raised activation.

    def test_older_recent_history_is_truncated_more_than_the_current_turn(self):
        older = ("an older turn " + "x" * 400, "an older reply " + "y" * 400)
        current = ("the current turn " + "x" * 400, "the current reply " + "y" * 400)
        def entry(context, reply):
            return {"event": {"id": context[:8], "kind": "incoming", "context": context},
                    "decision": {"action": "answers", "outcome": "moves on", "reply": reply}}
        compact = golem_loop.compact_recent_events([entry(*older), entry(*current)], older_limit=120)
        self.assertEqual(len(compact[0]["context"]), 120)
        self.assertEqual(len(compact[0]["reply"]), 120)
        self.assertEqual(len(compact[1]["context"]), 320)
        self.assertEqual(len(compact[1]["reply"]), 320)
        # Without older_limit the original caps stay uniform at 320.
        legacy = golem_loop.compact_recent_events([entry(*older)])
        self.assertEqual(len(legacy[0]["context"]), 320)

    def test_character_can_adopt_revise_and_clear_dialect(self):
        with TemporaryDirectory() as directory:
            db = Path(directory) / "character.sqlite3"
            golem_loop.initialize_character(db, golem.ROOT / "Characters/_template.yaml")
            turns = [(None, {"dialect": "Scots at home"}), ("Scots at home", {}),
                     ("Scots at home", {"dialect": "Mostly Glaswegian"}),
                     ("Mostly Glaswegian", {"dialect": None}), (None, {})]
            for i, (expected, change) in enumerate(turns):
                def decide(request):
                    # An absent dialect in the compact context means none.
                    self.assertEqual(request.get("dialect"), expected)
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

            golem_loop.wake_character(db, host, compact=False, event=event)
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
                compact=False,
                event={"id": "e1", "kind": "incoming", "at": (start + timedelta(minutes=10)).isoformat(), "text": "Hello"},
            )
            golem_loop.wake_character(
                db, decide,
                compact=False,
                event={"id": "e2", "kind": "incoming", "at": (start + timedelta(hours=1)).isoformat(), "text": "Still here"},
            )
            golem_loop.wake_character(
                db, decide,
                compact=False,
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

    def test_episodic_recall_recovers_multi_day_events_on_cue_without_bloating_recent(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "loop.sqlite3"
            card = Path(tmp) / "card.yaml"
            card.write_text(
                "name: Talia\ncall_name: Talia\ncharacter_id: talia\nage: 29\n"
                "default_somatic_alignment: {focus: 'Realm I'}\n"
                "cognitive_bias: {name: 'Debt Ledger'}\n"
                "cognitive_gift: {name: 'Sacred Stewardship'}\n",
                encoding="utf-8",
            )
            start = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, history_at=start.isoformat())

            seen = []

            def decide(req):
                seen.append(req)
                eid = req["event"]["id"]
                if eid == "day1":
                    return {"id": eid, "reply": "I tightened the bicycle brake cable on Elm Street."}
                return {"id": eid, "reply": "Okay."}

            golem_loop.wake_character(
                db, decide,
                event={"id": "day1", "kind": "incoming", "at": (start + timedelta(minutes=10)).isoformat(),
                       "relationship_target": "alex", "text": "Did you fix the bicycle brake on Elm Street?"},
            )
            # Next day, unrelated greeting: recent is empty and no unrelated episode is pulled in.
            golem_loop.wake_character(
                db, decide,
                event={"id": "day2", "kind": "incoming", "at": (start + timedelta(days=1)).isoformat(),
                       "relationship_target": "alex", "text": "Good morning!"},
            )
            self.assertEqual(seen[-1]["recent"], [])
            self.assertNotIn("recalled_memories", seen[-1])

            # Day 3, cue matches Day 1: recent stays empty (beyond 2h), Day 1 episode is recalled on demand.
            golem_loop.wake_character(
                db, decide,
                event={"id": "day3", "kind": "incoming", "at": (start + timedelta(days=2)).isoformat(),
                       "relationship_target": "alex", "text": "How is the bicycle brake holding up?"},
            )
            self.assertEqual(seen[-1]["recent"], [])
            recalled = seen[-1].get("recalled_memories", [])
            self.assertTrue(any(m["id"] == "episode:day1" and m["kind"] == "episode" for m in recalled))

    def test_no_recall_query_without_cues(self):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("CREATE TABLE memories (id, kind, summary, cues, created_at)")
            connection.execute("""INSERT INTO memories VALUES ('m','detailed','A rainy day','["rain"]',0)""")
            statements = []
            connection.set_trace_callback(statements.append)
            self.assertEqual(golem_loop.recall_stored_memories(connection, {"kind": "idle"}), [])
            self.assertEqual(statements, [])
            event = {"stimulus": {"memory_cues": ["RAIN"]}}
            self.assertEqual(golem_loop.recall_stored_memories(connection, event)[0]["id"], "m")

    def test_memory_batch_rollback_and_post_commit_mirror_recovery(self):
        with TemporaryDirectory() as directory:
            card, log, db = (Path(directory) / name for name in ("card.yaml", "log.yaml", "db.sqlite3"))
            card.write_text("name: Rowan\n")
            original = "revision: 0\n"
            log.write_text(original)
            golem_loop.initialize_character(db, card, log=log)
            event = {"kind": "incoming", "id": "rain"}
            memory = {"id": "walk", "summary": "Walked in the rain", "cues": ["rain"]}
            other = {**memory, "summary": "Stayed inside"}
            def save(entries):
                return golem_loop.wake_character(db, lambda _: {"id": "rain", "remember": entries}, event=event)
            with self.assertRaisesRegex(ValueError, "Memory ID already exists"):
                save([memory, other])
            self.assertEqual(log.read_text(), original)
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM memories").fetchone()[0], 0)
                connection.execute("""CREATE TRIGGER reject_resolution BEFORE UPDATE OF status ON events
                    WHEN NEW.status='resolved' BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
                save([memory])
            self.assertEqual(log.read_text(), original)
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM memory_log_queue").fetchone()[0], 0)
                connection.execute("DROP TRIGGER reject_resolution")

            with patch.object(golem_loop, "mirror_memories", side_effect=OSError("mirror unavailable")):
                with self.assertRaisesRegex(OSError, "mirror unavailable"):
                    save([memory])
            self.assertEqual(log.read_text(), original)
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute("SELECT status FROM events").fetchone()[0], "resolved")
                self.assertEqual(connection.execute("SELECT id FROM memories").fetchone()[0], "walk")
            for _ in range(2):
                golem_loop.wake_character(db, self.fail, event=event)
            self.assertEqual(log.read_text().count("Walked in the rain"), 1)
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM memory_log_queue").fetchone()[0], 0)

    def test_in_turn_remember_persists_to_sqlite_and_log_and_recalls_later(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "loop.sqlite3"
            card = Path(tmp) / "card.yaml"
            log = Path(tmp) / "log.yaml"
            card.write_text(
                "name: Talia\ncall_name: Talia\ncharacter_id: talia\nage: 29\n"
                "default_somatic_alignment: {focus: 'Realm I'}\n",
                encoding="utf-8",
            )
            log.write_text("character_id: talia\n", encoding="utf-8")
            start = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, log=log, history_at=start.isoformat())

            seen = []

            def decide(req):
                seen.append(req)
                eid = req["event"]["id"]
                if eid == "t1":
                    return {
                        "id": eid,
                        "reply": "Noted, dark roast it is.",
                        "remember": {
                            "id": "mem_elena_coffee",
                            "summary": "Elena prefers dark roast espresso.",
                            "cues": ["coffee", "espresso", "elena"],
                        },
                    }
                return {"id": eid, "reply": "Sure."}

            out = golem_loop.wake_character(
                db, decide,
                event={"id": "t1", "kind": "incoming", "at": (start + timedelta(minutes=5)).isoformat(),
                       "text": "I like dark roast espresso."},
            )
            self.assertEqual(out["events"][0]["remembered"], ["mem_elena_coffee"])
            self.assertIn("mem_elena_coffee", log.read_text(encoding="utf-8"))

            # Two days later, asking about coffee recalls the durable memory.
            golem_loop.wake_character(
                db, decide,
                event={"id": "t2", "kind": "incoming", "at": (start + timedelta(days=2)).isoformat(),
                       "text": "Should I grab coffee?"},
            )
            recalled_ids = [m["id"] for m in seen[-1].get("recalled_memories", [])]
            self.assertIn("mem_elena_coffee", recalled_ids)

    def test_prompt_cache_split_keeps_static_prefix_hash_stable_across_turns(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "loop.sqlite3"
            card = Path(tmp) / "card.yaml"
            card.write_text(
                "name: Talia\ncall_name: Talia\ncharacter_id: talia\nage: 29\n"
                "default_somatic_alignment: {focus: 'Realm I'}\n",
                encoding="utf-8",
            )
            start = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
            golem_loop.initialize_character(db, card, history_at=start.isoformat())

            splits = []

            def decide(req):
                splits.append(req)
                eid = req["dynamic_turn"]["event"]["id"]
                if eid == "s2":
                    return {"id": eid, "reply": "Switching tone.", "dialect": "terse"}
                return {"id": eid, "reply": "Steady."}

            golem_loop.wake_character(
                db, decide, split_cache=True,
                event={"id": "s1", "kind": "incoming", "at": (start + timedelta(minutes=5)).isoformat(), "text": "Hi"},
            )
            golem_loop.wake_character(
                db, decide, split_cache=True,
                event={"id": "s2", "kind": "incoming", "at": (start + timedelta(minutes=25)).isoformat(),
                       "text": "Second turn", "stimulus": {"stress_delta": 30}},
            )
            golem_loop.wake_character(
                db, decide, split_cache=True,
                event={"id": "s3", "kind": "incoming", "at": (start + timedelta(minutes=40)).isoformat(), "text": "Third"},
            )

            # Turns 1 and 2 have different timestamps/body/events, but byte-identical static_prefix and prefix_hash.
            self.assertEqual(splits[0]["prefix_hash"], splits[1]["prefix_hash"])
            self.assertEqual(splits[0]["static_prefix"], splits[1]["static_prefix"])
            self.assertIn("identity_anchor", splits[0]["static_prefix"])
            self.assertNotIn("at", splits[0]["static_prefix"])
            self.assertNotIn("event", splits[0]["static_prefix"])
            self.assertIn("event", splits[0]["dynamic_turn"])
            self.assertIn("at", splits[0]["dynamic_turn"])
            # Turn 3 reflects the updated dialect, invalidating the prefix_hash cleanly.
            self.assertNotEqual(splits[1]["prefix_hash"], splits[2]["prefix_hash"])
            self.assertEqual(splits[2]["static_prefix"]["dialect"], "terse")
