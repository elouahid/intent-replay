"""Focused synthetic checks; never contact a provider or use credentials."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from intent_replay.benchmark_cases import digest
from intent_replay.benchmark_execution import execute_prepared
from intent_replay.live_proposal_demo import LiveProposal, ENDPOINT, MODEL, RESERVATION, checked_transport, AUTO_PROFILE, LEGACY_PROFILE, DIRECT_INSTRUCTIONS, private_http_error
from intent_replay.regression import assess


ROOT = Path(__file__).resolve().parents[1]


def native():
    return {"id": "synthetic-response", "model": MODEL, "status": "completed", "output": [{
        "type": "function_call", "id": "synthetic-item", "status": "completed", "call_id": "synthetic-call",
        "name": "reschedule_booking", "arguments": json.dumps({"reference": "BR-OV01",
        "requested_time": "2026-11-25T15:00:00+00:00", "timezone": "Europe/London"})}],
        "usage": {"input_tokens": 500, "output_tokens": 200, "total_tokens": 700,
                  "output_tokens_details": {"reasoning_tokens": 120}}}


class LiveProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = json.loads((ROOT / "fresh_case_evidence/workflow.json").read_text())
        self.manager = LiveProposal(Path(self.temp.name) / "runtime", self.snapshot, profile=AUTO_PROFILE)

    def run_native(self, raw=None, *, timeout=False):
        raw = native() if raw is None else raw
        def request(config, payload, call, accounting):
            call.transport_checked = True
            call.reserve()
            accounting.http_attempts = 1
            if timeout:
                call.transport_error = "APITimeoutError"
                from openai import APITimeoutError
                raise APITimeoutError(request=httpx.Request("POST", ENDPOINT))
            call.raw, call.http_status = deepcopy(raw), 200
            accounting.http_responses = accounting.successful_http_responses = 1
            return deepcopy(raw)
        with patch("intent_replay.benchmark_targets.check_runtime_config"), patch("intent_replay.benchmark_targets.request_native", side_effect=request) as send:
            result = self.manager.generate()
        self.assertEqual(send.call_count, 1)
        return result

    def run_sdk(self, body, code=200):
        sent = []
        def fake_send(request):
            self.assertTrue((self.manager.root / "dispatch-reserved.json").exists())
            sent.append(request)
            return httpx.Response(code, json=body, request=request)
        def client(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(fake_send), **kwargs)
        guard = checked_transport(self.manager, httpx.Client.send)
        with patch.dict(os.environ, {"MODEL_API_KEY": "synthetic-offline-key"}), patch("intent_replay.benchmark_targets.check_runtime_config"), \
                patch("intent_replay.meta_client.load_dotenv"), patch("intent_replay.meta_client.DefaultHttpxClient", side_effect=client), \
                patch("httpx.Client.send", new=guard):
            result = self.manager.generate()
        self.assertEqual(len(sent), 1)
        self.assertEqual(json.loads(sent[0].content)["tool_choice"], "auto")
        return result

    def test_status_and_workflow_never_dispatch_and_hide_old_capture(self):
        with patch("intent_replay.benchmark_targets.request_native", side_effect=AssertionError("No request allowed")):
            self.assertEqual(self.manager.status()["status"], "ready")
            for row in self.manager.workflow()["cases"]:
                self.assertEqual(set(row["providers"]), {"meta"})
                self.assertIsNone(row["providers"]["meta"]["prepared"])
            self.assertFalse((self.manager.root / "attempt-started.json").exists())

    def test_success_shared_capture_replay_and_restart_no_retry(self):
        result = self.run_native()
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["native_status"], "completed")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["http_attempts"], 1)
        self.assertEqual(result["usage"]["reasoning_tokens"], 120)
        self.assertEqual(result["estimated_cost_usd"], "0.001475")
        prepared = [row["providers"]["meta"]["prepared"] for row in self.manager.workflow()["cases"]]
        self.assertEqual(prepared[0]["capture_sha256"], prepared[1]["capture_sha256"])
        for artifact in prepared:
            report = execute_prepared(artifact)
            self.assertTrue(all(row["matches"] for row in assess(report, artifact)))
        restarted = LiveProposal(self.manager.root, self.snapshot, profile=AUTO_PROFILE)
        self.assertEqual(restarted.status()["status"], "captured")
        with self.assertRaises(ValueError):
            restarted.generate()

    def test_wrong_model_retained_without_prepared(self):
        raw = native()
        raw["model"] = "unexpected-model"
        result = self.run_native(raw)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["accounting_issue"], "model_identity_mismatch")
        self.assertFalse((self.manager.root / "prepared").exists())
        stored = json.loads((self.manager.root / "native-attempt.json").read_text())
        self.assertEqual(stored["public_response"]["model"], "unexpected-model")

    def test_missing_usage_retains_full_reservation(self):
        raw = native()
        raw.pop("usage")
        result = self.run_native(raw)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["accounting_issue"], "usage_unknown")
        self.assertEqual(result["estimated_cost_usd"], str(RESERVATION))
        self.assertFalse((self.manager.root / "prepared").exists())

    def test_missing_configuration_never_dispatches_and_preserves_failed_attempt(self):
        from intent_replay.meta_client import MissingAPIKeyError
        with patch("intent_replay.benchmark_targets.check_runtime_config", side_effect=MissingAPIKeyError("MODEL_API_KEY is missing.")), \
                patch("intent_replay.benchmark_targets.request_native", side_effect=AssertionError("No request allowed")):
            result = self.manager.generate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["http_attempts"], 0)
        self.assertEqual(result["estimated_cost_usd"], "0")
        self.assertFalse(result["can_generate"])

    def test_native_incomplete_is_retained_and_not_retried(self):
        raw = native()
        raw.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        result = self.run_native(raw)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["native_status"], "incomplete")
        self.assertIn("incomplete", result["error"])
        with self.assertRaises(ValueError):
            self.manager.generate()

    def test_transport_timeout_unknown_durable(self):
        result = self.run_native(timeout=True)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["estimated_cost_usd"], str(RESERVATION))
        restarted = LiveProposal(self.manager.root, self.snapshot, profile=AUTO_PROFILE)
        self.assertFalse(restarted.status()["can_generate"])
        with self.assertRaises(ValueError):
            restarted.generate()

    def test_interrupted_marker_blocks_restart(self):
        (self.manager.root / "attempt-started.json").write_text("{}")
        restarted = LiveProposal(self.manager.root, self.snapshot, profile=AUTO_PROFILE)
        self.assertEqual(restarted.status()["status"], "unknown")
        with self.assertRaises(ValueError):
            restarted.generate()

    def test_corrupt_capture_is_not_replayed_or_replaced(self):
        self.run_native()
        path = self.manager.root / "capture.json"
        path.write_text("{}")
        self.assertEqual(self.manager.status()["status"], "unknown")
        self.assertTrue(all(row["providers"]["meta"]["prepared"] is None for row in self.manager.workflow()["cases"]))

    def test_transport_denies_unrelated_async_shape_and_second_hop(self):
        sent = []
        def actual(client, request, *args, **kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            self.manager.current.reserve()
            self.assertTrue((self.manager.root / "dispatch-reserved.json").exists())
            sent.append(request)
            return httpx.Response(200, json=native(), request=request)
        guarded = checked_transport(self.manager, actual)
        with self.assertRaises(RuntimeError):
            guarded(None, httpx.Request("GET", ENDPOINT))
        self.manager.active = True
        call = self.manager.call(request=self.manager.request, ordinal=1, max_output=2048)
        for request in (httpx.Request("GET", ENDPOINT), httpx.Request("POST", "https://inference.baseten.co/v1/chat/completions", json=self.manager.request),
                        httpx.Request("POST", ENDPOINT, json={"model": MODEL})):
            with self.assertRaises(RuntimeError):
                guarded(None, request)
        self.assertFalse(sent)
        guarded(None, httpx.Request("POST", ENDPOINT, json=self.manager.request))
        self.assertEqual(len(sent), 1)
        self.assertEqual(call.http_status, 200)
        with self.assertRaises(RuntimeError):
            guarded(None, httpx.Request("POST", ENDPOINT, json=self.manager.request))

    def test_request_exact_scope_and_conservative_bound(self):
        self.assertEqual(str(RESERVATION), "1.319424")
        self.assertEqual(self.manager.request["tool_choice"], "auto")
        self.assertEqual(self.manager.binding["request_profile"], AUTO_PROFILE)
        self.assertEqual(self.manager.config.instruction_version, "direct-proposal-v2")
        self.assertEqual(self.manager.config.developer_instructions, DIRECT_INSTRUCTIONS)
        self.assertIn("Do not call get_booking", self.manager.request["instructions"])
        self.assertEqual(len(self.manager.request["input"]), 2)
        self.assertNotIn("withdrawal", json.dumps(self.manager.request["input"]).lower())
        self.assertNotIn("private_expectations", json.dumps(self.manager.request))
        self.assertEqual(digest(self.manager.request), self.manager.binding["request_sha256"])

    def test_retained_capture_read_only_no_key_and_no_retry(self):
        self.run_native()
        before = {str(p): p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()}
        with patch.dict(os.environ, {}, clear=True), patch("intent_replay.benchmark_targets.request_native", side_effect=AssertionError("No inference")):
            retained = LiveProposal(self.manager.root, self.snapshot, retained=True, profile=AUTO_PROFILE)
            self.assertTrue(retained.status()["retained_capture_mode"])
            self.assertEqual(retained.status()["status"], "captured")
            self.assertFalse(retained.status()["can_generate"])
            retained.workflow()
            with self.assertRaises(ValueError):
                retained.generate()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()})

    def test_missing_retained_capture_never_creates_source(self):
        missing = Path(self.temp.name) / "missing"
        with self.assertRaises(ValueError):
            LiveProposal(missing, self.snapshot, retained=True, profile=AUTO_PROFILE)
        self.assertFalse(missing.exists())

    def test_failed_retained_receipt_is_read_only_and_never_enables_replay(self):
        raw = native()
        raw.pop("usage")
        self.run_native(raw)
        before = {str(p): p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()}
        with patch.dict(os.environ, {}, clear=True), patch("intent_replay.benchmark_targets.request_native", side_effect=AssertionError("No inference")):
            retained = LiveProposal(self.manager.root, self.snapshot, retained=True, profile=AUTO_PROFILE)
            self.assertEqual(retained.status()["status"], "failed")
            self.assertFalse(retained.status()["can_generate"])
            self.assertTrue(all(row["providers"]["meta"]["prepared"] is None for row in retained.workflow()["cases"]))
            with self.assertRaises(ValueError):
                retained.generate()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.manager.root.rglob("*") if p.is_file()})
        capture_path = self.manager.root / "capture.json"
        capture_path.write_text("{}")
        with self.assertRaises(ValueError):
            LiveProposal(self.manager.root, self.snapshot, retained=True, profile=AUTO_PROFILE)

    def test_real_sdk_serialization_mock_transport_reserves_before_dispatch(self):
        result = self.run_sdk(native())
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["http_attempts"], 1)

    def test_original_legacy_failed_capture_remains_valid_and_read_only(self):
        original = ROOT / "live_proposal_evidence"
        before = {p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}
        retained = LiveProposal(original, self.snapshot, retained=True, profile=LEGACY_PROFILE)
        self.assertEqual(retained.binding, json.loads(before["authority.json"]))
        self.assertEqual(retained.status()["http_status"], 400)
        self.assertEqual(retained.status()["request_profile"], LEGACY_PROFILE)
        self.assertFalse(retained.status()["can_generate"])
        with self.assertRaises(ValueError):
            retained.generate()
        self.assertEqual(before, {p.name: p.read_bytes() for p in original.iterdir() if p.is_file()})

    def test_changed_profile_cannot_rebind_an_existing_authority(self):
        with self.assertRaises(RuntimeError):
            LiveProposal(self.manager.root, self.snapshot, profile=LEGACY_PROFILE)
        with patch("intent_replay.live_proposal_demo.DIRECT_INSTRUCTIONS", DIRECT_INSTRUCTIONS + " Different instructions."):
            with self.assertRaises(RuntimeError):
                LiveProposal(self.manager.root, self.snapshot, profile=AUTO_PROFILE)

    def test_plain_text_is_retained_without_replay_or_a_second_request(self):
        raw = native()
        raw["output"] = [{"type": "message", "id": "synthetic-message", "role": "assistant", "status": "completed",
                          "content": [{"type": "output_text", "text": "I can help reschedule that booking."}]}]
        result = self.run_native(raw)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["capture_status"], "invalid_or_no_proposal")
        self.assertEqual(result["http_attempts"], 1)
        capture = json.loads((self.manager.root / "capture.json").read_text())
        self.assertEqual(capture["responses"][0]["output"][0]["content"][0]["text"], "I can help reschedule that booking.")
        self.assertFalse((self.manager.root / "prepared").exists())

    def test_lookup_is_retained_without_dispatch_or_a_second_request(self):
        raw = native()
        raw["output"][0].update(name="get_booking", arguments='{"reference":"BR-OV01"}')
        result = self.run_native(raw)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["capture_status"], "invalid_or_no_proposal")
        self.assertIn("Lookup requested but not dispatched", result["error"])
        capture = json.loads((self.manager.root / "capture.json").read_text())
        self.assertEqual(len(capture["requests"]), 1)
        self.assertEqual(capture["events"][0]["kind"], "read_only_call")
        self.assertNotIn("result", capture["events"][0])
        self.assertFalse((self.manager.root / "prepared").exists())

    def test_http_400_preserves_safe_error_metadata_and_no_retry(self):
        message = 'Only "auto" is supported for tool_choice.'
        result = self.run_sdk({"error": {"type": "invalid_request_error", "code": None,
                                        "param": "tool_choice", "message": message}}, 400)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["provider_error"]["message"], message)
        self.assertEqual(result["provider_error"]["param"], "tool_choice")
        self.assertIn(message, result["error"])
        attempt = json.loads((self.manager.root / "native-attempt.json").read_text())
        self.assertEqual(attempt["provider_error"], result["provider_error"])
        self.assertEqual(len(attempt["response_sha256"]), 64)
        with self.assertRaises(ValueError):
            self.manager.generate()

    def test_error_diagnostics_withhold_credentials_and_arbitrary_content(self):
        secret = "synthetic-offline-key"
        body = {"error": {"type": "invalid_request_error", "code": secret, "param": "tool_choice",
                          "message": "Bearer " + secret, "extra": {"request": secret}}, "headers": {"Authorization": secret}}
        result = self.run_sdk(body, 400)
        public = result["provider_error"]
        self.assertEqual(public["type"], "invalid_request_error")
        self.assertEqual(public["param"], "tool_choice")
        self.assertEqual(public["withheld_fields"], ["code", "message"])
        retained = "\n".join(p.read_text() for p in self.manager.root.rglob("*.json"))
        self.assertNotIn(secret, retained)
        self.assertNotIn("Authorization", retained)
        private = json.loads((self.manager.root / "private-provider-error.json").read_text())
        self.assertFalse(private["public_export_allowed"])
        self.assertEqual(private["message"], "Bearer [REDACTED]")
        self.assertNotIn("extra", private)

    def test_private_error_redacts_before_truncation_and_never_exports_headers(self):
        secret = "synthetic-metadata-secret"
        with patch.dict(os.environ, {"MODEL_API_KEY": secret, "BASETEN_API_KEY": "synthetic-baseten-secret"}):
            private = private_http_error({"error": {"message": secret + " Bearer other-private-token LLM|123|opaque-secret sk-other-secret999 " + "x" * 5000,
                                                   "code": "synthetic-baseten-secret"},
                                          "headers": {"Authorization": secret}})
        serialized = json.dumps(private)
        for forbidden in (secret, "synthetic-baseten-secret", "other-private-token", "opaque-secret", "sk-other-secret999", "Authorization"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(private["truncated_fields"], ["message"])
        self.assertLess(len(serialized.encode()), 8192)
        self.assertIn("[TRUNCATED]", private["message"])

    def test_long_error_message_is_withheld_instead_of_partial_secret_export(self):
        result = self.run_sdk({"error": {"type": "invalid_request_error", "message": "x" * 257}}, 400)
        self.assertNotIn("message", result["provider_error"])
        self.assertTrue(result["provider_error"]["message_exceeds_limit"])

    def test_oversized_error_body_retains_hash_without_parsing_or_export(self):
        result = self.run_sdk({"error": {"message": "x" * 20_000}}, 400)
        self.assertTrue(result["provider_error"]["body_exceeds_limit"])
        self.assertEqual(result["provider_error"]["withheld_fields"], ["body"])
        attempt = json.loads((self.manager.root / "native-attempt.json").read_text())
        self.assertEqual(len(attempt["response_sha256"]), 64)


class LiveProposalAPITests(unittest.TestCase):
    def test_get_does_not_dispatch_and_post_contract_blocks_unknown_fields(self):
        from fastapi.testclient import TestClient
        from scripts.serve_live_proposal_demo import configure
        with tempfile.TemporaryDirectory() as directory:
            app = configure(Path(directory), ROOT / "fresh_case_evidence/workflow.json")
            with TestClient(app) as client, patch("intent_replay.benchmark_targets.request_native", side_effect=AssertionError("No request allowed")):
                self.assertEqual(client.get("/api/live-proposal/status").json()["status"], "ready")
                self.assertEqual(client.get("/api/benchmark/workflow").status_code, 200)
                self.assertEqual(client.post("/api/live-proposal/generate", json={"model": "other"}).status_code, 422)
                self.assertEqual(client.post("/api/live-proposal/generate", json={}, headers={"Origin": "https://other.example"}).status_code, 403)
                self.assertFalse((Path(directory) / "attempt-started.json").exists())


if __name__ == "__main__":
    unittest.main()
