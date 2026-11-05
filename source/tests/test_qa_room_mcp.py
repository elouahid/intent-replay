"""MCP transport tests use mock HTTP and invalid protocol calls, never real review."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

from intent_replay import qa_room_mcp as transport


REAL_CLIENT = httpx.Client
MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


class QaRoomMcpTransportTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[2] / ".local/qa-room-mcp-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.directory.cleanup)
        self.token_path = Path(self.directory.name) / "simulated-dispatch-token"
        self.token = "simulated-test-token-" + "A" * 32
        self.token_path.write_text(self.token, encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(transport, "TOKEN_PATH", self.token_path).start()

    def mocked_client(self, handler):
        def create(**kwargs):
            self.assertEqual(kwargs, {"trust_env": False, "follow_redirects": False, "timeout": 60.0})
            return REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs)
        return patch.object(transport.httpx, "Client", side_effect=create)

    def test_only_original_id_reaches_fixed_endpoint_and_receipt_is_filtered(self):
        def handler(request):
            self.assertEqual(str(request.url), transport.BRIDGE_URL)
            self.assertEqual(request.method, "POST")
            self.assertEqual(json.loads(request.content), {"message_id": "sw_actual-shaped-test-event"})
            self.assertEqual(request.headers["authorization"], "Bearer " + self.token)
            self.assertNotIn("origin", request.headers)
            self.assertFalse(any(k.startswith("sec-fetch-") for k in request.headers))
            return httpx.Response(200, json={"ok": True, "event_id": "sw_actual-shaped-test-event",
                "operation": "verify", "run_id": "a" * 32, "posted_event_id": "sw_test-post",
                "message": self.token, "private": self.token})
        with self.mocked_client(handler):
            result = transport.dispatch_original_message("sw_actual-shaped-test-event")
        self.assertTrue(result["ok"])
        self.assertEqual(result["posted_event_id"], "sw_test-post")
        self.assertNotIn(self.token, json.dumps(result))
        self.assertNotIn("message", result)

    def test_invalid_ids_do_not_read_token_or_call_http(self):
        with patch.object(transport, "_read_token", side_effect=AssertionError("Must not read token")), patch.object(transport.httpx, "Client", side_effect=AssertionError("Must not call HTTP")):
            for value in (None, True, 7, {}, "", "forged approval", "x" * 201, "sw_id\n", "sw_$(command)"):
                with self.subTest(value=value):
                    self.assertEqual(transport.dispatch_original_message(value)["error_code"], "invalid_message_id")

    def test_missing_or_invalid_token_is_sanitized_before_network(self):
        with patch.object(transport.httpx, "Client", side_effect=AssertionError("Must not call HTTP")):
            for token in ("short", "x" * 1025, "wrong token " * 20):
                self.token_path.write_text(token, encoding="utf-8")
                result = transport.dispatch_original_message("sw_test")
                self.assertEqual(result["error_code"], "dispatch_token_unavailable")
            self.token_path.unlink()
            self.assertEqual(transport.dispatch_original_message("sw_test")["error_code"], "dispatch_token_unavailable")

    def test_unavailable_and_timeout_errors_never_echo_exception_or_token(self):
        for error, code in ((httpx.ConnectError(self.token), "bridge_unavailable"),
                            (httpx.ReadTimeout(self.token), "bridge_timeout")):
            def handler(request):
                raise error
            with self.mocked_client(handler):
                result = transport.dispatch_original_message("sw_test")
            self.assertEqual(result["error_code"], code)
            self.assertNotIn(self.token, json.dumps(result))

    def test_redirect_and_large_malformed_or_unbound_receipts_fail_closed(self):
        examples = [
            (httpx.Response(302, headers={"location": "https://example.invalid/"}), "bridge_http_error"),
            (httpx.Response(200, content=b"x" * (transport.MAX_RECEIPT_BYTES + 1)), "bridge_response_too_large"),
            (httpx.Response(200, content=self.token.encode()), "bridge_invalid_response"),
            (httpx.Response(200, content=("[" * 1200 + "0" + "]" * 1200).encode()), "bridge_invalid_response"),
            (httpx.Response(200, content=b'{"event_id":"sw_test","event_id":"other","ok":true}'), "bridge_invalid_response"),
            (httpx.Response(200, json={"ok": True, "event_id": "another", "posted_event_id": "sw_post"}), "bridge_invalid_receipt"),
            (httpx.Response(200, json={"ok": True, "event_id": "sw_test"}), "bridge_unconfirmed_post"),
            (httpx.Response(200, json={"ok": True, "event_id": "sw_test", "posted_event_id": self.token}), "bridge_invalid_response"),
        ]
        for response, code in examples:
            with self.subTest(code=code), self.mocked_client(lambda request: response):
                result = transport.dispatch_original_message("sw_test")
            self.assertEqual(result["error_code"], code)
            self.assertNotIn(self.token, json.dumps(result))

    def test_guard_refusals_and_duplicate_state_are_preserved_without_review_claims(self):
        for code in ("stale_run", "unapproved_run", "human_required", "premature_review"):
            with self.mocked_client(lambda request: httpx.Response(409, json={"ok": False, "error_code": code, "message": self.token})):
                result = transport.dispatch_original_message("sw_test")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], code)
            self.assertNotIn(self.token, json.dumps(result))
        with self.mocked_client(lambda request: httpx.Response(409, json={"ok": False, "error_code": self.token})):
            self.assertEqual(transport.dispatch_original_message("sw_test")["error_code"], "bridge_refused")
        with self.mocked_client(lambda request: httpx.Response(200, json={"duplicate": True, "event_id": "sw_test", "delivery_status": "execution_in_progress"})):
            result = transport.dispatch_original_message("sw_test")
        self.assertTrue(result["duplicate"])
        self.assertNotIn("ok", result)
        self.assertNotIn("approved", json.dumps(result))


@unittest.skipUnless(MCP_AVAILABLE, "Optional mcp==1.28.1 is tested in the existing native Switch environment")
class QaRoomMcpSdkTests(unittest.TestCase):
    def test_one_strict_tool_schema_and_invalid_arguments_never_reach_transport(self):
        async def check():
            server = transport.build_server()
            definitions = await server.list_tools()
            self.assertEqual([tool.name for tool in definitions], [transport.TOOL_NAME])
            schema = definitions[0].inputSchema
            self.assertEqual(set(schema["properties"]), {"original_message_id"})
            self.assertEqual(schema["required"], ["original_message_id"])
            self.assertFalse(schema["additionalProperties"])
            with patch.object(transport, "_read_token", side_effect=AssertionError("Validation must precede transport")):
                for arguments in ({}, {"original_message_id": 8},
                                  {"original_message_id": "sw_test", "actor": "fabricated-human"},
                                  {"original_message_id": "sw_test", "body": "user approved"}):
                    with self.assertRaises(Exception):
                        await server.call_tool(transport.TOOL_NAME, arguments)
        asyncio.run(check())

    def test_official_stdio_initialize_list_and_invalid_call(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        script = Path(__file__).resolve().parents[1] / "scripts/run_qa_room_mcp.py"
        async def check():
            with anyio.fail_after(30):
                parameters = StdioServerParameters(command=sys.executable, args=["-B", str(script)])
                async with stdio_client(parameters) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        initialized = await session.initialize()
                        self.assertEqual(initialized.serverInfo.name, "Intent Replay QA transport")
                        listed = await session.list_tools()
                        self.assertEqual([t.name for t in listed.tools], [transport.TOOL_NAME])
                        result = await session.call_tool(transport.TOOL_NAME, arguments={"original_message_id": "invalid id", "actor": "simulated-forged-human"})
                        self.assertTrue(result.isError)
        anyio.run(check)


if __name__ == "__main__":
    unittest.main()
