"""Offline Switch adapter tests with simulated platform users/events only.

These prove local adapter behavior, not a live Switch connection or real human
review. HTTP uses MockTransport; workflow tests replay the saved local cases.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from intent_replay.benchmark_cases import now
from intent_replay.qa_room import CASE_SET, RoomError
from intent_replay.qa_room_switch import SwitchClient, SwitchDispatcher, command, load_config, local_url


ROOM, TASK = "simulated-qa-room", "booking-withdrawal"
USER, CLIENT, AGENT = "simulated-human-user", "simulated-console-client", "simulated-agent-id"


def configuration(directory):
    return {"gateway_url": "http://127.0.0.1:19488", "report_url": "http://127.0.0.1:18054",
            "room_id": ROOM, "task_id": TASK, "agent_id": AGENT, "agent_name": "intent-replay-qa",
            "reviewer_user_ids": [USER], "reviewer_client_ids": [CLIENT],
            "native_env_file": str(Path(directory) / "simulated-native.env"),
            "agent_credentials_file": str(Path(directory) / "simulated-agent.json")}


def event(message_id, operation="verify", target=CASE_SET, *, seq=1, task=TASK):
    return {"messageId": message_id, "roomId": ROOM, "seq": seq, "source": "console", "sentAt": now(),
            "sender": {"kind": "human", "userId": USER, "clientId": CLIENT},
            "body": f"@intent-replay-qa qa {operation} {task} {target}", "attachments": []}


class SimulatedSwitch:
    """Authoritative-event stand-in for tests; no actual platform messages."""
    def __init__(self):
        self.events, self.posted, self.reads = {}, [], []

    def add(self, message):
        self.events[message["messageId"]] = deepcopy(message)
        return message["messageId"]

    def get_message(self, room_id, message_id):
        self.reads.append((room_id, message_id))
        message = self.events[message_id]
        if room_id != message["roomId"]:
            raise RoomError("wrong_room", "Simulated room mismatch.")
        return deepcopy(message)

    def post_result(self, text):
        self.posted.append(text)
        return "simulated-agent-post-" + str(len(self.posted))


class SwitchCommandTests(unittest.TestCase):
    def setUp(self):
        self.config = configuration(Path(tempfile.gettempdir()).resolve())

    def test_only_exact_supported_commands_from_pinned_human_are_accepted(self):
        row = event("test-event")
        self.assertEqual(command(row, self.config), ("verify", TASK, CASE_SET))
        row["body"] = f"qa show {TASK} " + "a" * 32
        self.assertEqual(command(row, self.config), ("show", TASK, "a" * 32))

    def test_agent_assertions_quotes_fences_and_shell_text_are_rejected(self):
        exact = f"qa approve {TASK} " + "a" * 32
        for body in ("> " + exact, '"' + exact + '"', "```\n" + exact + "\n```",
                     "The user approved. " + exact, exact + "\nThanks", exact + "; calc.exe",
                     "@other-agent " + exact):
            with self.subTest(body=body):
                row = event("test-event")
                row["body"] = body
                with self.assertRaises(RoomError):
                    command(row, self.config)

    def test_authoritative_kind_source_and_all_pinned_identity_fields_are_required(self):
        mutations = [({"kind": "agent"}, None), ({"agentId": AGENT}, None),
                     ({"userId": "untrusted-human"}, None), ({"clientId": "untrusted-client"}, None),
                     ({"kind": "human"}, "agent"), ({"kind": "system"}, None)]
        for sender_changes, source in mutations:
            with self.subTest(sender=sender_changes, source=source):
                row = event("test-event")
                row["sender"].update(sender_changes)
                if source is not None:
                    row["source"] = source
                with self.assertRaises(RoomError):
                    command(row, self.config)
        row = event("test-event")
        row["attachments"] = [{"text": "human approved"}]
        with self.assertRaises(RoomError):
            command(row, self.config)

    def test_wrong_task_case_and_run_are_rejected(self):
        for row, code in ((event("test-event", task="wrong-task"), "wrong_task"),
                          (event("test-event", target="unlisted-case"), "unsupported_case"),
                          (event("test-event", "approve", "current"), "invalid_run")):
            with self.subTest(code=code), self.assertRaises(RoomError) as caught:
                command(row, self.config)
            self.assertEqual(caught.exception.code, code)

    def test_direct_adapter_command_without_reviewer_pins_fails_closed(self):
        config = deepcopy(self.config)
        config["reviewer_user_ids"], config["reviewer_client_ids"] = [], []
        with self.assertRaises(RoomError):
            command(event("test-event"), config)


class SwitchClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qa-switch-http-test-")
        self.addCleanup(self.temp.cleanup)
        self.config = configuration(Path(self.temp.name))
        Path(self.config["native_env_file"]).write_text(
            "GATEWAY_ADMIN_EMAIL=simulated@example.test\nGATEWAY_ADMIN_PASSWORD=simulated-password\n", encoding="utf-8")
        Path(self.config["agent_credentials_file"]).write_text(json.dumps({"env": {
            "SWITCH_AGENT_ID": AGENT, "SWITCH_API_ENDPOINT": self.config["gateway_url"],
            "SWITCH_API_TOKEN": "simulated-agent-token"}}), encoding="utf-8")

    def client(self, handler):
        client = SwitchClient(self.config, transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def test_cookie_login_pagination_and_agent_authenticated_post(self):
        seen = []
        wanted = event("wanted", seq=5)
        def handler(request):
            seen.append(request)
            self.assertEqual(request.url.host, "127.0.0.1")
            if request.url.path == "/gateway/auth/login":
                self.assertEqual(json.loads(request.content)["email"], "simulated@example.test")
                return httpx.Response(200, json={"ok": True, "server": {"version": "0.31.0"}},
                                      headers={"set-cookie": "switch_auth=simulated-session; Path=/"})
            if request.method == "GET":
                self.assertIn("switch_auth=simulated-session", request.headers.get("cookie", ""))
                if request.url.params.get("beforeSeq") is None:
                    return httpx.Response(200, json={"messages": [event("later", seq=20), event("earlier", seq=11)], "hasMore": True})
                self.assertEqual(request.url.params["beforeSeq"], "11")
                return httpx.Response(200, json={"messages": [wanted], "hasMore": False})
            self.assertEqual(request.url.path, "/agents/" + AGENT + "/message")
            self.assertEqual(request.headers["authorization"], "Bearer simulated-agent-token")
            self.assertEqual(request.headers.get("cookie", ""), "")
            self.assertEqual(json.loads(request.content), {"room_id": ROOM, "content": "Simulated test result"})
            return httpx.Response(200, json={"ok": True, "event_id": "simulated-result"})
        client = self.client(handler)
        self.assertEqual(client.get_message(ROOM, "wanted"), wanted)
        self.assertEqual(client.post_result("Simulated test result"), "simulated-result")
        self.assertEqual(sum(r.url.path == "/gateway/auth/login" for r in seen), 1)
        self.assertFalse(any("/gateway/chats/" in r.url.path and r.method == "POST" for r in seen))

    def test_credentials_and_server_error_bodies_never_leak(self):
        secret = "PRIVATE ERROR BODY simulated-password simulated-agent-token"
        client = self.client(lambda request: httpx.Response(403, text=secret))
        with self.assertRaises(RoomError) as caught:
            client.get_message(ROOM, "event")
        self.assertEqual(caught.exception.code, "switch_http_error")
        self.assertIn("403", str(caught.exception))
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertNotIn("simulated-password", str(caught.exception))

    def test_redirect_is_not_followed_to_another_origin(self):
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://untrusted.example/collect"})
        with self.assertRaises(RoomError):
            self.client(handler).get_message(ROOM, "event")
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith(self.config["gateway_url"] + "/"))

    def test_login_requires_the_actual_session_cookie(self):
        with self.assertRaises(RoomError) as caught:
            self.client(lambda request: httpx.Response(200, json={"ok": True})).get_message(ROOM, "event")
        self.assertEqual(caught.exception.code, "switch_auth_failed")

    def test_cookie_alone_cannot_accept_an_unchecked_server_version(self):
        client = self.client(lambda request: httpx.Response(
            200, json={"server": {"version": "unverified-version"}},
            headers={"set-cookie": "switch_auth=simulated-session; Path=/"}))
        with self.assertRaises(RoomError) as caught:
            client.get_message(ROOM, "event")
        self.assertEqual(caught.exception.code, "switch_version_mismatch")

    def test_gateway_rejects_ambiguous_wrong_room_and_nonadvancing_pages(self):
        wanted = event("wanted")
        wrong = deepcopy(wanted)
        wrong["roomId"] = "other-room"
        cases = [({"messages": [wanted, wanted], "hasMore": False}, "ambiguous_event"),
                 ({"messages": [wrong], "hasMore": False}, "wrong_room"),
                 ({"messages": [event("other", seq=4)], "hasMore": True}, "switch_invalid_response"),
                 ({"messages": [], "hasMore": True}, "switch_invalid_response")]
        for payload, code in cases:
            with self.subTest(code=code):
                client = self.client(lambda request, payload=payload: httpx.Response(200, json=payload))
                client.authenticated = True
                with self.assertRaises(RoomError) as caught:
                    client.get_message(ROOM, "wanted")
                self.assertEqual(caught.exception.code, code)

    def test_managed_agent_relay_has_separate_origin_and_no_human_cookie(self):
        relay = "http://127.0.0.1:19999"
        Path(self.config["agent_credentials_file"]).write_text(json.dumps({"env": {
            "SWITCH_AGENT_ID": AGENT, "SWITCH_API_ENDPOINT": relay,
            "SWITCH_API_TOKEN": "simulated-managed-token"}}), encoding="utf-8")
        seen = []
        original = event("simulated-original-human")

        def handler(request):
            seen.append((request.method, request.url.port, request.url.path))
            if request.url.port == 19488:
                if request.url.path == "/gateway/auth/login":
                    return httpx.Response(200, json={"server": {"version": "0.31.0"}},
                                          headers={"set-cookie": "switch_auth=simulated-human-session; Path=/"})
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.path, "/gateway/chats/" + ROOM + "/messages")
                self.assertIn("switch_auth=simulated-human-session", request.headers.get("cookie", ""))
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, json={"messages": [original], "hasMore": False})
            self.assertEqual(request.url.port, 19999)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/agents/" + AGENT + "/message")
            self.assertEqual(request.headers["authorization"], "Bearer simulated-managed-token")
            self.assertEqual(request.headers.get("cookie", ""), "")
            self.assertEqual(json.loads(request.content), {"room_id": ROOM, "content": "Simulated managed result"})
            return httpx.Response(200, json={"ok": True, "event_id": "simulated-relay-result"})

        client = self.client(handler)
        self.assertEqual(client.get_message(ROOM, original["messageId"]), original)
        self.assertEqual(client.post_result("Simulated managed result"), "simulated-relay-result")
        self.assertEqual(client.get_message(ROOM, original["messageId"]), original)
        self.assertEqual(client.base, self.config["gateway_url"])
        self.assertEqual(sum(port == 19999 for _, port, _ in seen), 1)
        self.assertEqual(sum(path == "/gateway/auth/login" for _, _, path in seen), 1)

    def test_agent_credentials_reject_remote_relay_and_wrong_agent_without_http(self):
        client = self.client(lambda request: self.fail("Mismatched agent credentials made an HTTP request"))
        for field, value, code in (("SWITCH_AGENT_ID", "other-agent", "agent_credentials_mismatch"),
                                   ("SWITCH_API_ENDPOINT", "http://untrusted.example:9999", "invalid_configuration"),
                                   ("SWITCH_API_ENDPOINT", "http://192.0.2.20:9999", "invalid_configuration"),
                                   ("SWITCH_API_ENDPOINT", "http://user:password@localhost:9999", "invalid_configuration")):
            with self.subTest(field=field):
                creds = {"SWITCH_AGENT_ID": AGENT, "SWITCH_API_ENDPOINT": self.config["gateway_url"],
                         "SWITCH_API_TOKEN": "simulated-token"}
                creds[field] = value
                Path(self.config["agent_credentials_file"]).write_text(json.dumps({"env": creds}), encoding="utf-8")
                with self.assertRaises(RoomError) as caught:
                    client.post_result("test")
                self.assertEqual(caught.exception.code, code)

    def test_relay_redirect_cannot_forward_agent_authentication(self):
        Path(self.config["agent_credentials_file"]).write_text(json.dumps({"env": {
            "SWITCH_AGENT_ID": AGENT, "SWITCH_API_ENDPOINT": "http://localhost:19999",
            "SWITCH_API_TOKEN": "simulated-managed-token"}}), encoding="utf-8")
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(307, headers={"location": "https://untrusted.example/collect"},
                                  text="private relay diagnostic")

        with self.assertRaises(RoomError) as caught:
            self.client(handler).post_result("Simulated relay result")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].url.host, "localhost")
        self.assertEqual(seen[0].url.port, 19999)
        self.assertEqual(seen[0].headers.get("cookie", ""), "")
        self.assertNotIn("private relay diagnostic", str(caught.exception))

    def test_configuration_only_allows_loopback_origins_and_explicit_reviewer(self):
        for value in ("https://127.0.0.1:4888", "http://example.org", "http://127.0.0.1/path",
                      "http://user:pass@localhost", "http://localhost?query=secret"):
            with self.subTest(value=value), self.assertRaises(RoomError):
                local_url(value)
        path = Path(self.temp.name) / "config.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        self.assertEqual(load_config(path)["room_id"], ROOM)
        config = deepcopy(self.config)
        config["reviewer_user_ids"], config["reviewer_client_ids"] = [], []
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(RoomError):
            load_config(path)


class SwitchDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qa-switch-dispatch-test-")
        self.addCleanup(self.temp.cleanup)
        self.config = configuration(Path(self.temp.name))
        self.client = SimulatedSwitch()
        self.state = Path(self.temp.name) / "state"
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        self.blockers = ExitStack()
        self.addCleanup(self.blockers.close)
        for target in ("httpx.HTTPTransport.handle_request", "httpx.AsyncHTTPTransport.handle_async_request",
                       "socket.create_connection", "intent_replay.meta_client.create_client",
                       "intent_replay.benchmark_targets.OpenAI"):
            self.blockers.enter_context(patch(target, side_effect=AssertionError("Offline simulated platform test")))
        self.seq = 0

    def send(self, message_id, operation="verify", target=CASE_SET, *, post=True):
        self.seq += 1
        self.client.add(event(message_id, operation, target, seq=self.seq))
        return self.dispatcher.dispatch(message_id, post=post)

    def test_simulated_request_runs_real_pair_and_posts_separate_verdicts_as_agent(self):
        result = self.send("sim-request-A")
        self.assertTrue(result["ok"])
        self.assertTrue(result["snapshot"]["evidence_valid"])
        self.assertEqual(result["replay_model_requests"], 0)
        self.assertIn("Separate", result["switch_agent_inference"])
        self.assertEqual(len(self.client.posted), 1)
        self.assertEqual(result["posted_event_id"], "simulated-agent-post-1")
        text = self.client.posted[0]
        self.assertIn("Frozen regression expectations: PASS", text)
        self.assertIn("execution FAIL", text)
        self.assertIn("Guarded:", text)
        self.assertIn("Control (fresh-control)", text)
        self.assertIn("INCONCLUSIVE / unassessed", text)
        self.assertIn(self.config["report_url"] + "/qa/runs/" + result["run_id"], text)
        self.assertIn("Switch-agent inference is separate", text)
        self.assertIn("human next action:", text)

    def test_delivery_deduplication_and_review_survive_dispatcher_restart(self):
        run = self.send("sim-request-A")
        approved = self.send("sim-approve-A", "approve", run["run_id"])
        self.assertTrue(approved["ok"])
        self.assertEqual(approved["snapshot"]["approval"]["actor_id"], "switch:user:" + USER)
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        for key in ("sim-request-A", "sim-approve-A"):
            result = self.dispatcher.dispatch(key)
            self.assertTrue(result["duplicate"])
        self.assertEqual(len(self.client.posted), 2)
        current = self.dispatcher.store.show_run(ROOM, TASK)
        self.assertEqual(current["run_id"], run["run_id"])
        self.assertEqual(current["review_status"], "approved")

    def test_simulated_walkthrough_stale_A_then_review_and_complete_B(self):
        a = self.send("sim-request-A")
        self.assertTrue(self.send("sim-approve-A", "approve", a["run_id"])["ok"])
        b = self.send("sim-request-B")
        stale = self.send("sim-complete-A", "complete", a["run_id"])
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error_code"], "stale_run")
        self.assertIsNone(self.dispatcher.store.show_run(ROOM, TASK)["approval"])
        self.assertTrue(self.send("sim-approve-B", "approve", b["run_id"])["ok"])
        completed = self.send("sim-complete-B", "complete", b["run_id"])
        self.assertTrue(completed["ok"])
        self.assertEqual(completed["snapshot"]["task_status"], "completed")
        self.assertIn("using run " + b["run_id"], completed["message"])
        self.assertIsNone(self.dispatcher.store.show_run(ROOM, TASK, a["run_id"])["completion"])

    def test_agent_cannot_claim_human_approval_or_supply_another_event(self):
        run = self.send("sim-request-A")
        row = event("sim-agent-approve", "approve", run["run_id"], seq=2)
        row["sender"] = {"kind": "agent", "agentId": AGENT, "userId": USER, "clientId": CLIENT}
        self.client.add(row)
        with self.assertRaises(RoomError):
            self.dispatcher.dispatch(row["messageId"])
        row = event("sim-quoted-approve", "approve", run["run_id"], seq=3)
        row["body"] = "> " + row["body"]
        self.client.add(row)
        with self.assertRaises(RoomError):
            self.dispatcher.dispatch(row["messageId"])
        self.assertIsNone(self.dispatcher.store.show_run(ROOM, TASK)["approval"])

    def test_original_event_is_refetched_for_human_review(self):
        run = self.send("sim-request-A")
        self.send("sim-approve-A", "approve", run["run_id"])
        self.assertGreaterEqual(self.client.reads.count((ROOM, "sim-approve-A")), 2)
        with self.assertRaises(RoomError):
            self.dispatcher.verify_human(ROOM, "sim-approve-A", "complete", run["run_id"], TASK)

    def test_event_content_change_is_rejected_after_first_delivery(self):
        self.send("sim-request-A")
        self.client.events["sim-request-A"]["body"] += " "
        with self.assertRaises(RoomError) as caught:
            self.dispatcher.dispatch("sim-request-A")
        self.assertEqual(caught.exception.code, "event_conflict")
        self.assertEqual(len(self.client.posted), 1)

    def test_ambiguous_post_does_not_repeat_run_or_post_after_restart(self):
        self.client.add(event("sim-request-A"))
        with patch.object(self.client, "post_result", side_effect=RoomError("post_unconfirmed", "Simulated timeout")) as post:
            with self.assertRaises(RoomError):
                self.dispatcher.dispatch("sim-request-A")
            self.assertEqual(post.call_count, 1)
        current = self.dispatcher.store.show_run(ROOM, TASK)
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        duplicate = self.dispatcher.dispatch("sim-request-A")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["delivery_status"], "posting")
        self.assertEqual(self.dispatcher.store.show_run(ROOM, TASK)["run_id"], current["run_id"])
        self.assertEqual(self.client.posted, [])

    def test_review_message_from_before_execution_is_not_later_consent(self):
        accepted = self.dispatcher.store.request_run(ROOM, TASK, "sim-direct-request")
        old = event("sim-early-approval", "approve", accepted["run_id"], seq=1)
        old["sentAt"] = "2000-01-01T00:00:00+00:00"
        self.client.add(old)
        self.dispatcher.store.execute_run(accepted["run_id"])
        result = self.dispatcher.dispatch(old["messageId"])
        self.assertFalse(result["ok"])
        self.assertIsNone(self.dispatcher.store.show_run(ROOM, TASK)["approval"])

    def test_old_verification_delivery_does_not_supersede_a_newer_request(self):
        self.client.add(event("sim-newer", seq=20))
        newer = self.dispatcher.dispatch("sim-newer")
        self.client.add(event("sim-older", seq=10))
        try:
            result = self.dispatcher.dispatch("sim-older")
        except RoomError:
            result = {"ok": False}
        self.assertFalse(result["ok"])
        self.assertEqual(self.dispatcher.store.show_run(ROOM, TASK)["run_id"], newer["run_id"])

    def test_completion_message_must_follow_its_required_approval(self):
        run = self.send("sim-request-A")
        premature = event("sim-early-completion", "complete", run["run_id"], seq=2)
        self.client.add(premature)
        self.send("sim-approve-A", "approve", run["run_id"])
        result = self.dispatcher.dispatch(premature["messageId"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "premature_review")
        self.assertIsNone(self.dispatcher.store.show_run(ROOM, TASK)["completion"])

    def test_accepted_rerun_invalidates_before_execution_and_restart_resumes_same_run(self):
        a = self.send("sim-request-A")
        self.send("sim-approve-A", "approve", a["run_id"])
        self.client.add(event("sim-request-B", seq=3))
        with patch.object(self.dispatcher.store, "execute_run", side_effect=RuntimeError("Simulated interruption before execution")):
            with self.assertRaises(RuntimeError):
                self.dispatcher.dispatch("sim-request-B")
        pending = self.dispatcher.store.show_run(ROOM, TASK)
        self.assertNotEqual(pending["run_id"], a["run_id"])
        self.assertEqual(pending["status"], "pending")
        self.assertIsNone(pending["approval"])
        self.assertEqual(pending["task_status"], "unreviewed")
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        resumed = self.dispatcher.dispatch("sim-request-B")
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["run_id"], pending["run_id"])
        self.assertEqual(len(self.client.posted), 3)

    def test_restart_after_execution_before_receipt_finalization_does_not_reexecute(self):
        self.client.add(event("sim-request-A"))
        with patch("intent_replay.qa_room_switch.result_message", side_effect=RuntimeError("Simulated interruption after execution")):
            with self.assertRaises(RuntimeError):
                self.dispatcher.dispatch("sim-request-A")
        finished = self.dispatcher.store.show_run(ROOM, TASK)
        self.assertEqual(finished["status"], "ready")
        self.assertEqual(self.client.posted, [])
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        with patch("intent_replay.qa_room.execute_prepared", side_effect=AssertionError("A finished run was executed again")):
            resumed = self.dispatcher.dispatch("sim-request-A")
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["run_id"], finished["run_id"])
        self.assertEqual(resumed["snapshot"]["summary"], finished["summary"])
        self.assertEqual(len(self.client.posted), 1)

    def test_restart_after_approval_before_receipt_finalization_keeps_one_review(self):
        run = self.send("sim-request-A")
        self.client.add(event("sim-approve-A", "approve", run["run_id"], seq=2))
        with patch("intent_replay.qa_room_switch.result_message", side_effect=RuntimeError("Simulated interruption after review")):
            with self.assertRaises(RuntimeError):
                self.dispatcher.dispatch("sim-approve-A")
        review = self.dispatcher.store.show_run(ROOM, TASK)["approval"]
        self.assertIsNotNone(review)
        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        resumed = self.dispatcher.dispatch("sim-approve-A")
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["snapshot"]["approval"], review)
        self.assertEqual(len(self.client.posted), 2)

    def test_crash_after_core_acceptance_preserves_request_order_before_delivery_receipt(self):
        self.client.add(event("sim-request-A", seq=10))
        a = self.dispatcher.dispatch("sim-request-A")
        self.client.add(event("sim-approve-A", "approve", a["run_id"], seq=11))
        self.assertTrue(self.dispatcher.dispatch("sim-approve-A")["ok"])
        self.client.add(event("sim-request-B", seq=20))
        original_request = self.dispatcher.store.request_run

        def crash_after_core_commit(*args, **kwargs):
            original_request(*args, **kwargs)
            raise RuntimeError("Simulated crash after core commit before adapter delivery receipt")

        with patch.object(self.dispatcher.store, "request_run", side_effect=crash_after_core_commit):
            with self.assertRaises(RuntimeError):
                self.dispatcher.dispatch("sim-request-B")
        pending = self.dispatcher.store.show_run(ROOM, TASK)
        self.assertNotEqual(pending["run_id"], a["run_id"])
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(pending["last_request_seq"], 20)
        self.assertIsNone(pending["approval"])

        self.dispatcher = SwitchDispatcher(self.config, self.state, client=self.client)
        self.client.add(event("sim-delayed-distinct-C", seq=15))
        with self.assertRaises(RoomError) as caught:
            self.dispatcher.dispatch("sim-delayed-distinct-C")
        self.assertEqual(caught.exception.code, "out_of_order_request")
        self.assertEqual(self.dispatcher.store.show_run(ROOM, TASK)["run_id"], pending["run_id"])

        resumed = self.dispatcher.dispatch("sim-request-B")
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["run_id"], pending["run_id"])
        self.assertEqual(resumed["snapshot"]["last_request_seq"], 20)
        self.assertEqual(len(self.client.posted), 3)


if __name__ == "__main__":
    unittest.main()
