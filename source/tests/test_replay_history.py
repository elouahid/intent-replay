"""Focused offline boundaries for the guided saved-replay shelf."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from intent_replay.benchmark_cases import digest, seal
from intent_replay.benchmark_execution import execute_prepared, validate_prepared
from intent_replay.regression import assess
from intent_replay.replay_history import MAX_REPORT_BYTES, ReplayHistory, read_report
from intent_replay.temporal import RevisionStore

ROOT = Path(__file__).resolve().parents[1]


def regression(report, prepared):
    try:
        branches = assess(report, prepared)
        matched = all(row["matches"] for row in branches)
        return {"status": "PASS" if matched else "FAIL", "exit_code": 0 if matched else 1, "branches": branches}
    except Exception as exc:
        return {"status": "ERROR", "exit_code": 2, "error": str(exc), "branches": []}


class ReplayHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals = {}
        for name in ("fresh-withdrawal-meta", "fresh-control-meta", "fresh-withdrawal-baseten", "fresh-control-baseten"):
            cls.originals[name] = json.loads((ROOT / "fresh_case_evidence/executions" / (name + ".json")).read_text(encoding="utf-8"))
        cls.supported = {(r["prepared"]["case"]["case_id"], r["prepared"]["capture"]["target"]["provider"]): r["prepared"]
                         for r in cls.originals.values()}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="intent-replay-history-test-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.history = ReplayHistory(self.output, self.supported, regression)
        self.blockers = ExitStack()
        self.addCleanup(self.blockers.close)
        for target in ("httpx.HTTPTransport.handle_request", "httpx.AsyncHTTPTransport.handle_async_request",
                       "socket.create_connection", "intent_replay.meta_client.create_client", "intent_replay.benchmark_targets.OpenAI"):
            self.blockers.enter_context(patch(target, side_effect=AssertionError("External operation prohibited")))

    def report(self, name="fresh-withdrawal-meta"):
        return deepcopy(self.originals[name])

    def save(self, report, identifier=None):
        path = self.output / ((identifier or report["execution_id"]) + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return path

    def test_four_existing_records_reopen_without_execution_or_mutation(self):
        for report in self.originals.values():
            self.save(report)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with patch("intent_replay.benchmark_execution.execute_prepared", side_effect=AssertionError("Read executed a worker")):
            listing = self.history.list()
            self.assertEqual(listing["returned_count"], 4)
            self.assertFalse(listing["has_more"])
            for row in listing["items"]:
                self.assertEqual(row["status"], "ready")
                self.assertTrue(row["can_open"] and row["can_rerun"])
                saved = self.history.open(row["execution_id"], row["report_sha256"])
                self.assertEqual(saved["view_mode"], "saved")
                self.assertEqual(saved["new_executions"], 0)
                self.assertEqual(saved["new_model_requests"], 0)
                self.assertEqual(saved["regression"]["status"], "PASS")
                self.assertEqual(saved["source"]["prepared_sha256"], saved["report"]["prepared"]["sha256"])
                self.assertTrue(all(b["factual_accuracy"]["status"] == "INCONCLUSIVE" for b in saved["report"]["reports"]))
                if row["case_id"] == "fresh-withdrawal":
                    self.assertEqual(saved["report"]["reports"][0]["execution_result"], "FAIL")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_real_observed_mismatch_stays_available_without_expectation_change(self):
        prepared = self.report()["prepared"]
        before = digest(prepared)
        original = RevisionStore.execute
        def unexpectedly_commit(store, implementation, **kwargs):
            return original(store, "faulty" if implementation == "corrected" else implementation, **kwargs)
        with patch.object(RevisionStore, "execute", new=unexpectedly_commit):
            report = execute_prepared(prepared)
        self.save(report)
        row = self.history.list()["items"][0]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["regression_status"], "FAIL")
        self.assertEqual(row["regression_exit_code"], 1)
        self.assertTrue(row["can_open"] and row["can_rerun"])
        self.assertEqual(self.history.open(row["execution_id"], row["report_sha256"])["regression"]["status"], "FAIL")
        self.assertEqual(digest(prepared), before)

    def test_missing_observation_is_unavailable_and_original_retained(self):
        report = self.report()
        del report["reports"][1]["final_evidence"]["booking"]["starts_at"]
        report = seal(report)
        path = self.save(report); original = path.read_bytes()
        row = self.history.list()["items"][0]
        self.assertEqual(row["status"], "error")
        self.assertFalse(row["can_open"] or row["can_rerun"])
        self.assertIsNone(row["regression_status"])
        self.assertIn("incomplete", row["error"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.history.open(report["execution_id"], report["sha256"])
        self.assertEqual(path.read_bytes(), original)

    def test_bad_record_does_not_hide_good_record(self):
        report = self.report(); self.save(report)
        (self.output / ("a" * 32 + ".json")).write_text("{invalid", encoding="utf-8")
        listing = self.history.list()
        self.assertEqual({r["status"] for r in listing["items"]}, {"ready", "error"})
        self.assertEqual(listing["returned_count"], 2)

    def test_tampered_seal_filename_identity_runtime_and_revalidation_rejected(self):
        mutations = [
            (lambda r: r.update(created_at="tampered without resealing"), False),
            (lambda r: r.update(execution_id="a" * 32), True),
            (lambda r: r["runtime"].update(model_requests=True), True),
            (lambda r: r["runtime"].update(location="modal"), True),
            (lambda r: r.update(experiment_id="other"), True),
            (lambda r: r["revalidation"].update(original_prepared_sha256="0" * 64), True),
        ]
        for mutate, reseal in mutations:
            with self.subTest(mutate=mutate):
                report = self.report(); identifier = report["execution_id"]
                mutate(report)
                if reseal: report = seal(report)
                self.save(report, identifier)
                with self.assertRaises(ValueError): self.history.open(identifier, report["sha256"])

    def test_valid_alternative_prepared_and_unavailable_stage_rejected(self):
        prepared = self.report()["prepared"]
        prepared = seal({**prepared, "provenance": {**prepared["provenance"], "test_only_note": "alternate metadata"}})
        validate_prepared(prepared)
        report = execute_prepared(prepared)
        self.save(report)
        with self.assertRaisesRegex(ValueError, "current four"):
            self.history.open(report["execution_id"], report["sha256"])
        original = self.report(); self.save(original)
        unavailable = ReplayHistory(self.output, {}, regression)
        with self.assertRaisesRegex(ValueError, "current four"):
            unavailable.open(original["execution_id"], original["sha256"])

    def test_expected_hash_is_required_and_stale_binding_rejected(self):
        report = self.report(); self.save(report)
        for value in (None, "", "not-a-hash", "A" * 64, "0" * 64):
            with self.subTest(hash=value), self.assertRaises(ValueError):
                self.history.open(report["execution_id"], value)
        updated = seal({**report, "created_at": "2026-11-03T15:00:00+00:00"})
        self.save(updated)
        with self.assertRaisesRegex(ValueError, "binding changed"):
            self.history.open(report["execution_id"], report["sha256"])

    def test_saved_timestamp_requires_a_real_timezone_aware_iso_value(self):
        for value in ("<script>alert(1)</script>", "not-a-time", "2026-11-03T15:00:00", "2026-02-30T15:00:00+00:00"):
            report = seal({**self.report(), "created_at": value}); self.save(report)
            row = self.history.list()["items"][0]
            self.assertEqual(row["status"], "error")
            self.assertIn("timestamp", row["error"])
            self.assertFalse(row["can_open"] or row["can_rerun"])

    def test_identifiers_cannot_select_filesystem_paths(self):
        for identifier in ("../outside", "0" * 31, "0" * 33, "A" * 32, "C:\\other.json", None):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.history.open(identifier, "0" * 64)
        with self.assertRaises(FileNotFoundError): self.history.open("0" * 32, "0" * 64)

    def test_nonfinite_duplicate_invalid_utf8_and_oversized_files_rejected(self):
        path = self.output / ("a" * 32 + ".json")
        for value in (b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}', b'\xff', b'{"x":"\\ud800"}', b'[]'):
            with self.subTest(value=value):
                path.write_bytes(value)
                with self.assertRaises(ValueError): read_report(path)
        with path.open("wb") as stream: stream.truncate(MAX_REPORT_BYTES + 1)
        with patch("intent_replay.replay_history.os.open", side_effect=AssertionError("Oversized file was opened")):
            with self.assertRaisesRegex(ValueError, "8 MB"): read_report(path)

    def test_nonregular_link_and_reparse_metadata_rejected_before_open(self):
        path = self.output / ("a" * 32 + ".json"); path.mkdir()
        with self.assertRaisesRegex(ValueError, "regular"): read_report(path)
        for mode, attrs in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFREG | 0o644, 0x400)):
            info = SimpleNamespace(st_mode=mode, st_file_attributes=attrs)
            with patch.object(Path, "lstat", return_value=info), patch("intent_replay.replay_history.os.open", side_effect=AssertionError("Link opened")):
                with self.assertRaisesRegex(ValueError, "regular"): read_report(path)

    def test_changed_file_identity_is_rejected_before_content_read(self):
        report = self.report(); path = self.save(report)
        info = path.stat()
        changed = SimpleNamespace(st_mode=info.st_mode, st_dev=info.st_dev, st_ino=info.st_ino + 1,
                                  st_size=info.st_size, st_mtime_ns=info.st_mtime_ns)
        with patch("intent_replay.replay_history.os.fstat", return_value=changed):
            with self.assertRaisesRegex(ValueError, "changed"): read_report(path)

    def test_listing_has_twenty_record_cap_and_explicit_scan_truncation(self):
        report = self.report()
        for number in range(25):
            value = seal({**report, "execution_id": f"{number:032x}"})
            path = self.save(value)
            os.utime(path, ns=(1_000_000 + number, 1_000_000 + number))
        listing = self.history.list()
        self.assertEqual(listing["returned_count"], 20)
        self.assertEqual(listing["candidate_count"], 25)
        self.assertTrue(listing["has_more"])
        self.assertFalse(listing["scan_truncated"])
        self.assertEqual(listing["items"][0]["execution_id"], f"{24:032x}")
        for number in range(201): (self.output / ("ignored-" + str(number))).touch()
        bounded = self.history.list()
        self.assertEqual(bounded["scanned_entries"], 200)
        self.assertTrue(bounded["scan_truncated"] and bounded["has_more"])
        self.assertLessEqual(bounded["returned_count"], 20)


if __name__ == "__main__":
    unittest.main()
