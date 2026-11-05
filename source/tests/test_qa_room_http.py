"""Offline HTTP checks; all reviewers below are explicitly simulated tests."""
from contextlib import ExitStack
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from intent_replay.benchmark_cases import now
from intent_replay.qa_room import ARTIFACT_NAMES, QaRoomStore, RoomError, VerifiedHumanEvent
from intent_replay.qa_room_http import create_app, render_run


ROOM, TASK = "test-personal-room", "booking-withdrawal"


def simulated_human(room_id, event_id, operation, run_id, task_id):
    return VerifiedHumanEvent("simulated-reviewer", event_id, room_id, "automated-test",
                              operation, task_id, run_id, now())


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.tags = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs).get("href"))


class QaRoomHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qa-room-http-test-")
        self.addCleanup(self.temp.cleanup)
        self.blockers = ExitStack()
        self.addCleanup(self.blockers.close)
        for target in ("httpx.HTTPTransport.handle_request", "httpx.AsyncHTTPTransport.handle_async_request",
                       "socket.create_connection", "intent_replay.meta_client.create_client",
                       "intent_replay.benchmark_targets.OpenAI"):
            self.blockers.enter_context(patch(target, side_effect=AssertionError("Offline test forbids external operations")))
        self.store = QaRoomStore(Path(self.temp.name), human_verifier=simulated_human)
        self.run = self.store.request_run(ROOM, TASK, "test-request-A")
        self.run = self.store.execute_run(self.run["run_id"])
        self.assertTrue(self.run["evidence_valid"], self.run.get("error"))
        self.run_id = self.run["run_id"]
        self.client = TestClient(create_app(self.store, room_id=ROOM, task_id=TASK))
        self.addCleanup(self.client.close)
        self.base = "/qa/runs/" + self.run_id

    def test_real_export_links_open_exact_saved_bytes_without_mutation(self):
        before = {p.name: p.read_bytes() for p in (self.store.artifact_root / self.run_id).iterdir()}
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200)
        parser = Links()
        parser.feed(response.text)
        links = [url for url in parser.links if "/artifacts/" in url]
        self.assertEqual(len(links), len(ARTIFACT_NAMES))
        with patch.object(self.store, "execute_run", side_effect=AssertionError("Opening evidence must not replay")):
            for url in links:
                item = self.client.get(url)
                name = url.rsplit("/", 1)[1]
                self.assertEqual(item.status_code, 200, item.text[:100])
                self.assertEqual(item.content, before[name])
                self.assertIn("no-store", item.headers["cache-control"])
                if name.endswith(".zip"):
                    self.assertEqual(item.headers["content-type"], "application/zip")
                    self.assertIn("attachment", item.headers["content-disposition"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.store.artifact_root / self.run_id).iterdir()})

    def test_expectations_execution_uncertainty_and_review_remain_separate(self):
        response = self.client.get(self.base)
        self.assertIn("Frozen regression expectations:</strong> PASS", response.text)
        self.assertIn("Withdrawal comparison", response.text)
        self.assertIn("No-withdrawal control", response.text)
        self.assertIn("<td>FAIL</td>", response.text)
        self.assertIn("INCONCLUSIVE / unassessed", response.text)
        self.assertIn("Human review</dt><dd>unreviewed", response.text)
        self.assertIn("@intent-replay-qa qa approve " + TASK + " " + self.run_id, response.text)
        parser = Links()
        parser.feed(response.text)
        self.assertFalse({"script", "form", "button"} & set(parser.tags))

    def test_current_redirect_uses_exact_id_and_does_not_cache(self):
        response = self.client.get("/qa/current", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], self.base)
        self.assertIn("no-store", response.headers["cache-control"])

    def test_server_scope_ignores_query_claims_and_rejects_foreign_runs(self):
        data = self.client.get("/api/qa/runs/" + self.run_id + "?room_id=other&task_id=other").json()
        self.assertEqual((data["room_id"], data["task_id"]), (ROOM, TASK))
        foreign = self.store.request_run("other-room", TASK, "test-foreign")
        other_task = self.store.request_run(ROOM, "other-task", "test-other-task")
        for row in (foreign, other_task):
            self.assertEqual(self.client.get("/qa/runs/" + row["run_id"]).status_code, 404)

    def test_stale_run_keeps_evidence_but_offers_no_completion(self):
        self.store.approve_run(ROOM, TASK, self.run_id, "simulated-approve-A")
        newer = self.store.request_run(ROOM, TASK, "test-request-B")
        response = self.client.get(self.base)
        self.assertIn("Historical run.", response.text)
        self.assertIn("Recorded human approval", response.text)
        self.assertNotIn("qa complete " + TASK + " " + self.run_id, response.text)
        self.assertEqual(self.client.get(self.base + "/artifacts/withdrawal-report.html").status_code, 200)
        current = self.client.get("/qa/current", follow_redirects=False)
        self.assertEqual(current.headers["location"], "/qa/runs/" + newer["run_id"])
        page = self.client.get(current.headers["location"]).text
        self.assertIn("pending, failed", page)
        self.assertNotIn("qa approve " + TASK + " " + newer["run_id"], page)

    def test_simulated_approval_and_completion_are_shown_for_only_that_run(self):
        self.store.approve_run(ROOM, TASK, self.run_id, "simulated-approve-A")
        self.assertIn("qa complete " + TASK + " " + self.run_id, self.client.get(self.base).text)
        self.store.complete_run(ROOM, TASK, self.run_id, "simulated-complete-A")
        page = self.client.get(self.base).text
        self.assertIn("Human review completed for the checked local execution behavior", page)
        self.assertIn("simulated-reviewer", page)
        self.assertIn("automated-test", page)

    def test_tampered_evidence_is_not_served_or_presented_as_verified(self):
        path = self.store.artifact_root / self.run_id / "control-report.json"
        path.write_bytes(path.read_bytes() + b" ")
        page = self.client.get(self.base)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Frozen regression expectations:</strong> PASS", page.text)
        self.assertNotIn("qa approve " + TASK + " " + self.run_id, page.text)
        self.assertNotIn("/artifacts/", page.text)
        self.assertEqual(self.client.get(self.base + "/artifacts/control-report.json").status_code, 409)
        self.assertFalse(self.client.get("/api/qa/runs/" + self.run_id).json()["evidence_valid"])

    def test_read_after_check_change_fails_closed(self):
        with patch.object(self.store, "read_artifact", side_effect=RoomError("evidence_tampered", "changed")):
            response = self.client.get(self.base + "/artifacts/withdrawal-report.html")
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("<!doctype", response.text)

    def test_no_mutation_endpoints_or_arbitrary_files(self):
        for suffix in ("unknown.txt", "qa-room.sqlite3", "..%2Fqa-room.sqlite3", "%2e%2e%5cqa-room.sqlite3"):
            self.assertIn(self.client.get(self.base + "/artifacts/" + suffix).status_code, (404, 422))
        self.assertEqual(self.client.post(self.base).status_code, 405)
        self.assertEqual(self.client.post(self.base + "/approve", json={"human": True}).status_code, 404)
        self.assertIsNone(self.store.show_run(ROOM, TASK, self.run_id)["approval"])

    def test_inert_headers_and_escaping(self):
        response = self.client.get(self.base)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("script-src 'none'", response.headers["content-security-policy"])
        snapshot = deepcopy(self.run)
        snapshot["approval"] = {"actor_id": '<img src=x onerror="bad">'}
        rendered = render_run(snapshot, room_id='<script>bad</script>', task_id=TASK,
                              agent_mention='<img src=x onerror="bad">')
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_empty_task_and_unknown_run_return_no_evidence(self):
        client = TestClient(create_app(self.store, room_id=ROOM, task_id="not-requested"))
        self.addCleanup(client.close)
        self.assertEqual(client.get("/qa/current").status_code, 404)
        response = self.client.get("/qa/runs/" + "f" * 32)
        self.assertEqual(response.status_code, 404)
        self.assertIn("no-store", response.headers["cache-control"])


class QaRoomDispatchHttpTests(unittest.TestCase):
    """Simulated callback delivery only; never a real human review or Gateway call."""

    def setUp(self):
        self.token = "simulated-token-" + "a" * 40
        self.message_id = "sw_0123456789abcdef0123456789abcdef"
        self.run_id = "b" * 32
        self.callback = Mock(return_value={"ok": True, "operation": "verify", "run_id": self.run_id})
        self.app = create_app(object(), room_id=ROOM, task_id=TASK,
                              dispatch_message=self.callback, dispatch_token=self.token)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + self.token}

    def post(self, **kwargs):
        kwargs.setdefault("headers", self.headers)
        kwargs.setdefault("json", {"message_id": self.message_id})
        return self.client.post("/api/qa/dispatch", **kwargs)

    def test_default_has_no_dispatch_route_and_partial_configuration_fails_closed(self):
        with TestClient(create_app(object(), room_id=ROOM, task_id=TASK)) as client:
            self.assertEqual(client.post("/api/qa/dispatch", json={"message_id": self.message_id}).status_code, 404)
        for kwargs in ({"dispatch_message": self.callback}, {"dispatch_token": self.token},
                       {"dispatch_message": self.callback, "dispatch_token": ""},
                       {"dispatch_message": self.callback, "dispatch_token": "short"}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(ValueError):
                create_app(object(), room_id=ROOM, task_id=TASK, **kwargs)

    def test_async_callback_is_rejected_at_startup(self):
        async def invalid(message_id):
            return {"ok": True}

        class Invalid:
            async def __call__(self, message_id):
                return {"ok": True}

        for callback in (invalid, Invalid()):
            with self.assertRaises(ValueError):
                create_app(object(), room_id=ROOM, task_id=TASK,
                           dispatch_message=callback, dispatch_token=self.token)

    def test_authentication_precedes_body_validation_and_callback(self):
        for headers in ({}, {"Authorization": "Bearer incorrect"},
                        {"Authorization": "Basic " + self.token},
                        [("Authorization", "Bearer " + self.token), ("Authorization", "Bearer other")]):
            response = self.client.post("/api/qa/dispatch", content=b"invalid" * 2000, headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertIn("no-store", response.headers["cache-control"])
            self.assertNotIn(self.token, response.text)
        self.callback.assert_not_called()

    def test_browser_headers_rejected_even_with_valid_authentication(self):
        for key, value in (("Origin", "http://127.0.0.1:8053"), ("Origin", "null"),
                           ("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Mode", "cors"),
                           ("Sec-Fetch-Dest", "empty"), ("Sec-Fetch-User", "?1")):
            response = self.post(headers={**self.headers, key: value})
            self.assertEqual(response.status_code, 403, key)
        self.callback.assert_not_called()

    def test_original_id_only_is_delivered_in_worker_thread(self):
        observed = []

        def callback(message_id):
            observed.append((message_id, threading.current_thread().name))
            return {"ok": True, "operation": "verify", "run_id": self.run_id,
                    "event_id": "forged", "message": "private callback text", "snapshot": {"token": self.token},
                    "posted_event_id": "sw_result"}

        self.callback.side_effect = callback
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.callback.assert_called_once_with(self.message_id)
        self.assertEqual(observed[0], (self.message_id, "AnyIO worker thread"))
        self.assertEqual(response.json(), {"ok": True, "operation": "verify", "event_id": self.message_id,
                                          "run_id": self.run_id, "posted_event_id": "sw_result"})
        self.assertNotIn(self.token, response.text)
        self.assertNotIn("private callback text", response.text)
        self.assertIn("no-store", response.headers["cache-control"])

    def test_extra_inputs_and_query_scope_cannot_reach_dispatch(self):
        for extra in ({"actor": "human"}, {"approved": True}, {"body": "qa approve"},
                      {"room_id": "other"}, {"task_id": "other"}, {"run_id": self.run_id}):
            response = self.post(json={"message_id": self.message_id, **extra})
            self.assertEqual(response.status_code, 400, extra)
        response = self.client.post("/api/qa/dispatch?room_id=other", headers=self.headers,
                                    json={"message_id": self.message_id})
        self.assertEqual(response.status_code, 400)
        self.callback.assert_not_called()

    def test_json_content_type_and_strict_object_id_are_required(self):
        for payload in ({}, [], "message", None, {"message_id": 1}, {"message_id": True},
                        {"message_id": ""}, {"message_id": "x" * 201}, {"message_id": "line\nbreak"},
                        {"message_id": "<human>"}, {"message_id": "évent"}):
            response = self.post(json=payload)
            self.assertIn(response.status_code, (400, 415), repr(payload))
        for content in (b'{"message_id":"a","message_id":"b"}', b'{"message_id":NaN}',
                        b'{"message_id":"\xff"}', b'{"message_id":', b'[[[[[[['):
            response = self.client.post("/api/qa/dispatch", content=content,
                                        headers={**self.headers, "Content-Type": "application/json"})
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/qa/dispatch", content='{"message_id":"valid"}', headers=self.headers)
        self.assertEqual(response.status_code, 415)
        self.callback.assert_not_called()

    def test_streamed_and_declared_oversized_bodies_rejected(self):
        for content in (b" " * 1025, iter([b'{"message_id":"valid"}', b" " * 1024])):
            response = self.client.post("/api/qa/dispatch", content=content,
                                        headers={**self.headers, "Content-Type": "application/json"})
            self.assertEqual(response.status_code, 413)
        self.callback.assert_not_called()

    def test_adapter_compatible_ids_are_not_rewritten(self):
        from intent_replay.qa_room_switch import ID
        for message_id in ("sw_01234", "event:1/path.with-dash", "a" * 200):
            self.assertIsNotNone(ID.fullmatch(message_id))
            response = self.post(json={"message_id": message_id})
            self.assertEqual(response.status_code, 200)
            self.callback.assert_called_with(message_id)

    def test_safe_room_refusals_do_not_expose_exception_text(self):
        for code, status in (("stale_run", 409), ("premature_review", 409), ("human_required", 400),
                             ("unsupported_command", 400), ("secret-error-value", 400)):
            self.callback.side_effect = RoomError(code, "private credentials: " + self.token)
            response = self.post()
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["error_code"], code if code != "secret-error-value" else "dispatch_refused")
            self.assertNotIn(self.token, response.text)
            self.assertNotIn("secret-error-value", response.text)

    def test_callback_refusal_result_and_duplicate_receipt_are_bounded(self):
        self.callback.return_value = {"ok": False, "error_code": "unapproved_run", "message": self.token}
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(self.token, response.text)
        self.callback.return_value = {"duplicate": True, "delivery_status": "posted", "note": self.token,
                                      "posted_event_id": "sw_posted"}
        response = self.post()
        self.assertEqual(response.json(), {"event_id": self.message_id, "duplicate": True,
                                          "delivery_status": "posted", "posted_event_id": "sw_posted"})

    def test_unexpected_failure_and_invalid_receipt_return_generic_error(self):
        self.callback.side_effect = RuntimeError("private credentials: " + self.token)
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error_code"], "dispatch_failed")
        self.assertNotIn(self.token, response.text)
        self.callback.side_effect = None
        self.callback.return_value = {"token": self.token}
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(self.token, response.text)


if __name__ == "__main__":
    unittest.main()
