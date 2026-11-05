"""Workflow tests use explicitly simulated platform humans, never real approvals."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from intent_replay.benchmark_cases import now, seal
from intent_replay.benchmark_execution import execute_prepared
from intent_replay.qa_room import (
    ARTIFACT_NAMES, BASELINE_CONTRACT, CASE_SET, QaRoomStore, RoomError,
    SOURCE, VerifiedHumanEvent, _supported,
)


class SimulatedHumanVerifier:
    """Test double for authoritative platform retrieval, clearly test-only."""
    def __init__(self):
        self.times = {}
        self.lock = threading.Lock()

    def __call__(self, room_id, event_id, operation, run_id, task_id):
        if event_id.startswith(("agent-", "quoted-")):
            raise RoomError("not_human_command", "Simulated bot/quoted message is not an authenticated human command.")
        with self.lock:
            sent_at = self.times.setdefault((room_id, event_id), now())
        return VerifiedHumanEvent("simulated-test-human", event_id, room_id,
                                  "simulated-test-platform", operation, task_id, run_id, sent_at)


class QaRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = SOURCE.parent / ".local/qa-room-tests"
        cls.base.mkdir(parents=True, exist_ok=True)
        # Execute the unchanged engine once per supported case, then reuse its
        # real reports in workflow tests with fresh simulated execution IDs.
        with patch("httpx.Client.send", side_effect=AssertionError("No provider calls in workflow tests")):
            cls.engine_reports = {p["case"]["case_id"]: execute_prepared(p) for p in _supported().values()}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.base)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.store = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        self.executor = patch("intent_replay.qa_room.execute_prepared", side_effect=self.simulated_execution).start()
        self.addCleanup(patch.stopall)
        patch("httpx.Client.send", side_effect=AssertionError("No provider requests")).start()
        patch("httpx.AsyncClient.send", side_effect=AssertionError("No provider requests")).start()

    def simulated_execution(self, prepared):
        report = deepcopy(self.engine_reports[prepared["case"]["case_id"]])
        report["execution_id"] = uuid4().hex
        return seal(report)

    def request(self, event=None, *, task="booking", room="test-room", seq=None):
        return self.store.request_run(room, task, event or uuid4().hex, request_seq=seq)

    def ready(self, **kwargs):
        run = self.request(**kwargs)
        result = self.store.execute_run(run["run_id"])
        self.assertEqual(result["status"], "ready", result["error"])
        self.assertTrue(result["evidence_valid"], result["evidence_error"])
        return result

    def approve(self, run, event=None):
        return self.store.approve_run(run["room_id"], run["task_id"], run["run_id"], event or uuid4().hex)

    def complete(self, run, event=None):
        return self.store.complete_run(run["room_id"], run["task_id"], run["run_id"], event or uuid4().hex)

    def assert_error(self, code, operation):
        with self.assertRaises(RoomError) as error:
            operation()
        self.assertEqual(error.exception.code, code)
        return error.exception

    def test_supported_pair_exact_semantics_and_scoped_completion(self):
        run = self.ready()
        self.assertEqual(run["case_set"], CASE_SET)
        self.assertEqual(run["execution_contract_sha256"], BASELINE_CONTRACT)
        cases = run["summary"]["cases"]
        self.assertEqual(set(cases), {"withdrawal", "control"})
        outcomes = {(label, branch["implementation"]): branch
                    for label, case in cases.items() for branch in case["branches"]}
        self.assertEqual(outcomes["withdrawal", "faulty"]["observed"]["instruction_adherence"], "FAIL")
        self.assertEqual(outcomes["withdrawal", "corrected"]["observed"]["action_status"], "suppressed")
        for key, branch in outcomes.items():
            self.assertTrue(branch["matches"])
            self.assertEqual(branch["factual_accuracy"]["status"], "INCONCLUSIVE")
            self.assertFalse(branch["factual_accuracy"]["assessed"])
            self.assertEqual(branch["overall_task"], "FAIL" if key == ("withdrawal", "faulty") else "INCONCLUSIVE")
        self.approve(run)
        completed = self.complete(run)
        self.assertEqual(completed["task_status"], "completed")
        self.assertEqual(completed["approval"]["actor_id"], "simulated-test-human")
        self.assertEqual(completed["completion"]["binding_sha256"], run["summary"]["binding_sha256"])
        self.assertIn(run["run_id"], completed["completion"]["statement"])
        self.assertEqual(completed["summary"], run["summary"])

    def test_new_request_immediately_invalidates_completed_approval(self):
        old = self.ready()
        self.approve(old)
        self.complete(old)
        new = self.request()
        self.assertEqual(new["status"], "pending")
        self.assertEqual(new["task_status"], "unreviewed")
        self.assertIsNone(new["approval"])
        self.assertIsNone(new["completion"])
        self.assertEqual(new["revision"], old["revision"] + 1)
        self.assert_error("stale_run", lambda: self.complete(old))
        historical = self.store.show_run("test-room", "booking", old["run_id"])
        self.assertFalse(historical["is_current"])
        self.assertEqual(historical["review_status"], "completed")
        self.assertEqual(historical["task_status"], "unreviewed")
        self.assertFalse(historical["can_complete"])

    def test_current_ready_completion_requires_approval(self):
        run = self.ready()
        self.assert_error("unapproved_run", lambda: self.complete(run))
        self.assertEqual(self.store.show_run("test-room", "booking")["task_status"], "unreviewed")

    def test_wrong_task_and_room_cannot_review(self):
        run = self.ready()
        self.assert_error("wrong_run_scope", lambda: self.store.approve_run("test-room", "other-task", run["run_id"], "wrong-task"))
        self.assert_error("wrong_run_scope", lambda: self.store.complete_run("other-room", "booking", run["run_id"], "wrong-room"))

    def test_missing_human_verifier_and_agent_or_quoted_approval_refused(self):
        run = self.ready()
        unauthenticated = QaRoomStore(self.root)
        self.assert_error("human_verification_unavailable", lambda: unauthenticated.approve_run("test-room", "booking", run["run_id"], "plain-assertion"))
        self.assert_error("not_human_command", lambda: self.approve(run, "agent-claims-human-approved"))
        self.assert_error("not_human_command", lambda: self.approve(run, "quoted-human-approval"))
        self.assertIsNone(self.store.show_run("test-room", "booking")["approval"])

    def test_wrong_verified_identity_binding_refused(self):
        run = self.ready()
        self.store.human_verifier = lambda *args: VerifiedHumanEvent("simulated-test-human", args[1], "different-room", "simulated-test-platform", args[2], args[4], args[3], now())
        self.assert_error("human_event_invalid", lambda: self.approve(run))

    def test_duplicate_request_and_execution_are_idempotent_across_restart(self):
        first = self.request("same-platform-event")
        restarted = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        duplicate = restarted.request_run("test-room", "booking", "same-platform-event")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["run_id"], first["run_id"])
        restarted.execute_run(first["run_id"])
        restarted.execute_run(first["run_id"])
        self.assertEqual(self.executor.call_count, 2)  # two cases, one run

    def test_event_dedup_is_room_scoped_and_conflicts_reject(self):
        first = self.request("shared-id")
        other = self.request("shared-id", room="other-room")
        self.assertNotEqual(first["run_id"], other["run_id"])
        self.assert_error("event_conflict", lambda: self.request("shared-id", task="other-task"))

    def test_duplicate_historical_approval_and_completion_do_not_affect_new_run(self):
        old = self.ready()
        self.approve(old, "approval-event")
        self.complete(old, "completion-event")
        new = self.request()
        for response in (self.approve(old, "approval-event"), self.complete(old, "completion-event")):
            self.assertTrue(response["duplicate"])
            self.assertFalse(response["is_current"])
            self.assertEqual(response["event_acknowledgement"], "historical")
            self.assertEqual(response["task_status"], "unreviewed")
            self.assertEqual(response["current_run_id"], new["run_id"])
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM completions").fetchone()[0], 1)

    def test_rejected_pending_approval_never_activates_on_redelivery(self):
        run = self.request()
        self.assert_error("run_not_ready", lambda: self.approve(run, "early-approval"))
        self.store.execute_run(run["run_id"])
        error = self.assert_error("run_not_ready", lambda: self.approve(run, "early-approval"))
        self.assertTrue(error.duplicate)
        self.assertIsNone(self.store.show_run("test-room", "booking")["approval"])

    def test_original_approval_sent_while_pending_is_refused_when_delivered_after_result(self):
        run = self.request()
        original_sent_at = now()
        self.store.execute_run(run["run_id"])
        self.store.human_verifier = lambda room, event, operation, run_id, task: VerifiedHumanEvent(
            "simulated-test-human", event, room, "simulated-test-platform", operation, task, run_id, original_sent_at)
        self.assert_error("premature_review", lambda: self.approve(run, "originally-pending-approval"))
        self.assertIsNone(self.store.show_run("test-room", "booking")["approval"])

    def test_authoritative_review_time_requires_timezone_and_valid_timestamp(self):
        run = self.ready()
        for index, timestamp in enumerate(("2026-11-05T01:00:00", "not-a-timestamp")):
            with self.subTest(timestamp=timestamp):
                self.store.human_verifier = lambda room, event, operation, run_id, task: VerifiedHumanEvent(
                    "simulated-test-human", event, room, "simulated-test-platform", operation, task, run_id, timestamp)
                self.assert_error("premature_review", lambda: self.approve(run, "bad-timestamp-" + str(index)))
        self.assertIsNone(self.store.show_run("test-room", "booking")["approval"])

    def test_completion_timestamp_rechecked_against_concurrently_committed_approval(self):
        run = self.ready()
        entered, release = threading.Event(), threading.Event()
        original = SimulatedHumanVerifier()
        def verifier(*args):
            # Authoritative time is captured before the approval exists; only
            # original-event retrieval is delayed, not the source timestamp.
            event = original(*args)
            if args[2] == "complete":
                entered.set()
                if not release.wait(15):
                    raise RuntimeError("Test synchronization timeout")
            return event
        self.store.human_verifier = verifier
        with ThreadPoolExecutor(max_workers=1) as pool:
            completion = pool.submit(self.complete, run, "premature-completion-event")
            self.assertTrue(entered.wait(10))
            try:
                approved = self.approve(run, "concurrent-approval-event")
            finally:
                release.set()
            self.assert_error("premature_review", lambda: completion.result(timeout=20))
        current = self.store.show_run("test-room", "booking")
        self.assertEqual(current["task_status"], "approved")
        self.assertIsNone(current["completion"])
        self.assertEqual(current["approval"], approved["approval"])
        error = self.assert_error("premature_review", lambda: self.complete(run, "premature-completion-event"))
        self.assertTrue(error.duplicate)
        completed = self.complete(run, "later-actual-completion-event")
        self.assertEqual(completed["task_status"], "completed")

    def test_failed_rerun_keeps_old_approval_invalid_and_partial_evidence(self):
        old = self.ready()
        self.approve(old)
        new = self.request()
        def fail_control(prepared):
            if prepared["case"]["case_id"] == "fresh-control":
                raise RuntimeError("simulated control execution failure")
            return self.simulated_execution(prepared)
        self.executor.side_effect = fail_control
        failed = self.store.execute_run(new["run_id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["task_status"], "unreviewed")
        self.assertIsNone(failed["approval"])
        self.assertIn("withdrawal-report.json", failed["artifacts"])
        retained = json.loads(self.store.read_artifact("test-room", "booking", new["run_id"], "withdrawal-report.json"))
        self.assertEqual(retained["prepared"]["case"]["case_id"], "fresh-withdrawal")
        self.assert_error("run_not_ready", lambda: self.approve(new))
        self.assert_error("stale_run", lambda: self.complete(old))

    def test_missing_or_wrong_control_report_cannot_be_ready(self):
        def wrong_control(prepared):
            report = self.simulated_execution(prepared)
            if prepared["case"]["case_id"] == "fresh-control":
                report = self.simulated_execution(_supported()["withdrawal"])
            return report
        self.executor.side_effect = wrong_control
        run = self.request()
        result = self.store.execute_run(run["run_id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("evidence_binding", result["error"])
        self.assert_error("run_not_ready", lambda: self.approve(run))

    def test_changed_report_bytes_resealed_or_not_cannot_complete(self):
        run = self.ready()
        self.approve(run)
        path = self.store.artifact_root / run["run_id"] / "control-report.json"
        data = json.loads(path.read_text())
        data["created_at"] = "2026-01-01T00:00:00+00:00"
        path.write_text(json.dumps(seal(data)), encoding="utf-8")
        self.assert_error("evidence_tampered", lambda: self.complete(run))
        current = self.store.show_run("test-room", "booking")
        self.assertFalse(current["evidence_valid"])
        self.assertFalse(current["can_complete"])
        self.assertIsNone(current["completion"])

    def test_missing_bundle_blocks_completion_and_version_drift_blocks_review(self):
        run = self.ready()
        with patch("intent_replay.qa_room.execution_contract", return_value="0" * 64):
            self.assert_error("execution_version_changed", lambda: self.approve(run))
        self.approve(run)
        (self.store.artifact_root / run["run_id"] / "control-evidence.zip").unlink()
        self.assert_error("evidence_tampered", lambda: self.complete(run))

    def test_changed_evaluator_labels_cannot_forge_valid_evidence(self):
        def counterfeit(prepared):
            report = self.simulated_execution(prepared)
            # The unchanged evaluator's structured action assessment is evidence,
            # not a model summary. Keep other labels plausible to test recheck.
            report["reports"][1]["action_assessments"][0]["atomic_evidence"] = False
            return seal(report)
        self.executor.side_effect = counterfeit
        run = self.request()
        result = self.store.execute_run(run["run_id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("evidence_assessment", result["error"])

    def test_persistence_preserves_approval_and_exact_binding(self):
        run = self.ready()
        approved = self.approve(run, "persisted-approval")
        restarted = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        restored = restarted.show_run("test-room", "booking")
        self.assertEqual(restored["approval"], approved["approval"])
        self.assertEqual(restored["summary"]["binding_sha256"], run["summary"]["binding_sha256"])
        completed = restarted.complete_run("test-room", "booking", run["run_id"], "persisted-completion")
        self.assertEqual(completed["task_status"], "completed")

    def test_unknown_interrupted_execution_stays_running_without_resend(self):
        run = self.request()
        self.executor.side_effect = KeyboardInterrupt("simulated process interruption")
        with self.assertRaises(KeyboardInterrupt):
            self.store.execute_run(run["run_id"])
        restarted = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        self.assertEqual(restarted.show_run("test-room", "booking")["status"], "running")
        restarted.execute_run(run["run_id"])
        self.assertEqual(self.executor.call_count, 1)
        self.assert_error("run_not_ready", lambda: restarted.approve_run("test-room", "booking", run["run_id"], "no-unknown-approval"))

    def test_artifact_access_is_exact_run_and_scope_bound(self):
        old = self.ready()
        self.request()
        for name in ARTIFACT_NAMES:
            self.assertTrue(self.store.read_artifact("test-room", "booking", old["run_id"], name))
        self.assert_error("unknown_artifact", lambda: self.store.read_artifact("test-room", "booking", old["run_id"], "../qa-room.sqlite3"))
        self.assert_error("wrong_run_scope", lambda: self.store.read_artifact("other-room", "booking", old["run_id"], "control-report.json"))

    def test_supported_case_allowlist_and_identifier_validation(self):
        self.assert_error("unsupported_case_set", lambda: self.store.request_run("test-room", "booking", "event", "arbitrary-shell-command"))
        self.assert_error("invalid_task", lambda: self.request(task="../other"))
        self.assert_error("invalid_identity", lambda: self.request(room="room;run evil"))

    def test_stored_result_and_review_are_immutable(self):
        run = self.ready()
        self.approve(run)
        with closing(sqlite3.connect(self.store.path)) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE runs SET result_json='{}' WHERE run_id=?", (run["run_id"],))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE reviews SET binding_sha256='wrong' WHERE run_id=?", (run["run_id"],))

    def test_concurrent_duplicate_delivery_creates_one_run(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request("concurrent-delivery"), range(4)))
        self.assertEqual(len({r["run_id"] for r in results}), 1)
        self.assertEqual(sum(not r["duplicate"] for r in results), 1)

    def test_core_commit_preserves_sequence_after_missing_adapter_receipt_and_restart(self):
        first = self.ready(event="platform-A", seq=10)
        self.approve(first)
        newer = self.request("platform-B", seq=20)
        # Simulate the adapter process dying before its separate delivery
        # receipt commits. Only the core's accepted run has been committed.
        restarted = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        self.assert_error("out_of_order_request", lambda: restarted.request_run("test-room", "booking", "older-different-event", request_seq=10))
        self.assert_error("out_of_order_request", lambda: restarted.request_run("test-room", "booking", "equal-different-event", request_seq=20))
        current = restarted.show_run("test-room", "booking")
        self.assertEqual(current["run_id"], newer["run_id"])
        self.assertEqual(current["request_seq"], 20)
        self.assertEqual(current["last_request_seq"], 20)
        self.assertEqual(current["task_status"], "unreviewed")
        duplicate = restarted.request_run("test-room", "booking", "platform-A", request_seq=10)
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(duplicate["is_current"])
        self.assertEqual(duplicate["run_id"], first["run_id"])
        self.assert_error("event_conflict", lambda: restarted.request_run("test-room", "booking", "platform-A", request_seq=21))

    def test_unsequenced_request_cannot_supersede_sequenced_task(self):
        self.request("unsequenced-initial")
        current = self.request("trusted-event", seq=7)
        self.assert_error("event_sequence_required", lambda: self.request("unsequenced-later"))
        self.assertEqual(self.store.show_run("test-room", "booking")["run_id"], current["run_id"])
        separate = self.request("other-task-event", task="other-task", seq=1)
        self.assertEqual(separate["request_seq"], 1)
        self.assert_error("invalid_event_sequence", lambda: self.request(seq=True))
        self.assert_error("invalid_event_sequence", lambda: self.request(seq=0))

    def test_concurrent_platform_order_keeps_highest_sequence_current(self):
        barrier = threading.Barrier(2)
        def deliver(seq):
            barrier.wait(timeout=10)
            try:
                return self.request("event-" + str(seq), seq=seq)
            except RoomError as exc:
                self.assertEqual(exc.code, "out_of_order_request")
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(deliver, (10, 20)))
        latest = next(r for r in results if r and r["request_seq"] == 20)
        current = self.store.show_run("test-room", "booking")
        self.assertEqual(current["run_id"], latest["run_id"])
        self.assertEqual(current["last_request_seq"], 20)

    def test_sequence_is_bound_to_review_evidence_and_immutable(self):
        run = self.ready(seq=35)
        self.assertEqual(run["summary"]["binding"]["request_seq"], 35)
        self.approve(run)
        with closing(sqlite3.connect(self.store.path)) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE runs SET request_seq=36 WHERE run_id=?", (run["run_id"],))

    def test_old_store_schema_migrates_without_changing_existing_unsequenced_evidence(self):
        run = self.ready(event="pre-sequence-event")
        self.approve(run)
        # Recreate the two old schemas by removing only the just-added fields.
        # All original run/evidence/review/event rows remain in place.
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute("DROP TRIGGER immutable_request_sequence")
            db.execute("ALTER TABLE tasks DROP COLUMN last_request_seq")
            db.execute("ALTER TABLE runs DROP COLUMN request_seq")
            db.commit()
        migrated = QaRoomStore(self.root, human_verifier=SimulatedHumanVerifier())
        restored = migrated.show_run("test-room", "booking")
        self.assertEqual(restored["summary"], run["summary"])
        self.assertTrue(restored["evidence_valid"])
        self.assertIsNone(restored["request_seq"])
        self.assertTrue(migrated.request_run("test-room", "booking", "pre-sequence-event")["duplicate"])
        newer = migrated.request_run("test-room", "booking", "first-sequenced-event", request_seq=50)
        self.assertEqual(newer["request_seq"], 50)

    def test_late_old_execution_never_recaptures_current(self):
        old = self.request()
        entered, release = threading.Event(), threading.Event()
        def delayed(prepared):
            if threading.current_thread().name.startswith("old-run") and prepared["case"]["case_id"] == "fresh-withdrawal":
                entered.set()
                if not release.wait(15):
                    raise RuntimeError("Test synchronization timeout")
            return self.simulated_execution(prepared)
        self.executor.side_effect = delayed
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="old-run") as pool:
            previous = pool.submit(self.store.execute_run, old["run_id"])
            self.assertTrue(entered.wait(10))
            try:
                newer = self.ready()
            finally:
                release.set()
            finished = previous.result(timeout=20)
        self.assertEqual(finished["status"], "ready")
        self.assertFalse(finished["is_current"])
        self.assertEqual(self.store.show_run("test-room", "booking")["run_id"], newer["run_id"])

    def test_rerun_during_human_verification_rejects_old_approval(self):
        old = self.ready()
        entered, release = threading.Event(), threading.Event()
        def verifier(*args):
            entered.set()
            if not release.wait(15):
                raise RuntimeError("Test synchronization timeout")
            return SimulatedHumanVerifier()(*args)
        self.store.human_verifier = verifier
        with ThreadPoolExecutor(max_workers=1) as pool:
            approval = pool.submit(self.approve, old)
            self.assertTrue(entered.wait(10))
            try:
                new = self.request()
            finally:
                release.set()
            self.assert_error("stale_run", lambda: approval.result(timeout=20))
        self.assertIsNone(new["approval"])

    def test_rerun_before_completion_transaction_refuses_stale_completion(self):
        old = self.ready()
        self.approve(old)
        entered, release = threading.Event(), threading.Event()
        def verifier(*args):
            entered.set()
            if not release.wait(15):
                raise RuntimeError("Test synchronization timeout")
            return SimulatedHumanVerifier()(*args)
        self.store.human_verifier = verifier
        with ThreadPoolExecutor(max_workers=1) as pool:
            completion = pool.submit(self.complete, old)
            self.assertTrue(entered.wait(10))
            try:
                new = self.request()
            finally:
                release.set()
            self.assert_error("stale_run", lambda: completion.result(timeout=20))
        self.assertEqual(new["task_status"], "unreviewed")
        self.assertIsNone(new["completion"])

    def test_concurrent_duplicate_human_event_records_one_approval(self):
        run = self.ready()
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(lambda _: self.approve(run, "same-human-event"), range(3)))
        self.assertEqual(sum(not r["duplicate"] for r in responses), 1)
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE event_id='same-human-event'").fetchone()[0], 1)

    def test_atomic_completion_followed_by_concurrent_rerun_is_unreviewed(self):
        old = self.ready()
        self.approve(old)
        entered, release = threading.Event(), threading.Event()
        checked = self.store._checked_result
        calls = [0]
        def delayed(row):
            if threading.current_thread().name.startswith("completion") and calls[0] == 0:
                calls[0] += 1
                entered.set()
                if not release.wait(15):
                    raise RuntimeError("Test synchronization timeout")
            return checked(row)
        self.store._checked_result = delayed
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="completion") as first, ThreadPoolExecutor(max_workers=1) as second:
            completing = first.submit(self.complete, old)
            self.assertTrue(entered.wait(10))
            requesting = second.submit(self.request)
            release.set()
            completing.result(timeout=20)
            new = requesting.result(timeout=20)
        current = self.store.show_run("test-room", "booking")
        self.assertEqual(current["run_id"], new["run_id"])
        self.assertEqual(current["status"], "pending")
        self.assertEqual(current["task_status"], "unreviewed")
        self.assertIsNone(current["approval"])
        self.assertIsNone(current["completion"])


if __name__ == "__main__":
    unittest.main()
