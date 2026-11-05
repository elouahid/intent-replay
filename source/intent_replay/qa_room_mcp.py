"""One stdio MCP tool transporting an original message ID to the local QA bridge.

The bridge remains responsible for authoritative Switch events and every review
guard. This wrapper cannot choose an actor, operation, run, room, URL or token.
The optional MCP dependency is imported only when building the stdio server.
"""
import json
from pathlib import Path
import re
import sys

import httpx


BRIDGE_URL = "http://127.0.0.1:8054/api/qa/dispatch"
TOKEN_PATH = Path(__file__).resolve().parents[2] / ".local/qa-room/dispatch-token"
TOOL_NAME = "dispatch_original_message"
MESSAGE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}"
MAX_RECEIPT_BYTES = 16_384
REFUSAL_CODES = frozenset({
    "stale_run", "unapproved_run", "premature_review", "run_not_ready", "event_conflict",
    "out_of_order_request", "event_sequence_required", "wrong_run_scope", "wrong_room",
    "wrong_task", "wrong_review_event", "event_not_found", "human_required",
    "reviewer_not_allowed", "reviewer_not_configured", "unsupported_command",
    "unsupported_case", "invalid_run", "invalid_identity", "human_event_invalid",
    "evidence_tampered", "evidence_binding", "evidence_assessment", "required_checks_failed",
    "missing_control", "execution_version_changed", "review_binding", "unknown_run",
    "switch_unavailable", "switch_http_error", "switch_invalid_response", "switch_auth_failed",
    "switch_version_mismatch", "post_unconfirmed", "dispatch_failed", "dispatch_refused",
    "human_verification_unavailable", "input_changed", "switch_credentials_unavailable",
    "agent_credentials_mismatch", "invalid_configuration", "invalid_task", "unsupported_input",
    "control_binding", "unsupported_case_set", "invalid_event_sequence", "unknown_task",
    "unknown_artifact", "ambiguous_event",
})


def _failure(code, *, status=None):
    result = {"ok": False, "error_code": code,
              "message": "No confirmed room result was returned. Inspect the original event, current run and delivery state before retrying."}
    if status is not None:
        result["http_status"] = status
    return result


def _read_token():
    try:
        with TOKEN_PATH.open("r", encoding="utf-8") as stream:
            text = stream.read(1025)
        token = text.strip()
        if len(text) > 1024 or not re.fullmatch(r"[A-Za-z0-9._~-]{32,256}", token):
            return None
        return token
    except (OSError, UnicodeError):
        return None


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate receipt property")
        result[key] = value
    return result


def _receipt(data, original_message_id, status):
    if not isinstance(data, dict):
        return _failure("bridge_invalid_response", status=status)
    if status != 200:
        code = data.get("error_code")
        return _failure(code if isinstance(code, str) and code in REFUSAL_CODES else "bridge_refused", status=status)
    if (data.get("event_id") != original_message_id
            or not (data.get("ok") is True or data.get("duplicate") is True)):
        return _failure("bridge_invalid_receipt", status=status)
    # Do not relay arbitrary response text, exception bodies, tokens or paths.
    result = {"event_id": original_message_id, "http_status": status}
    for field in ("ok", "duplicate"):
        if type(data.get(field)) is bool:
            result[field] = data[field]
    if data.get("operation") in {"verify", "show", "approve", "complete"}:
        result["operation"] = data["operation"]
    if isinstance(data.get("run_id"), str) and re.fullmatch(r"[a-f0-9]{32}", data["run_id"]):
        result["run_id"] = data["run_id"]
    if isinstance(data.get("posted_event_id"), str) and re.fullmatch(MESSAGE_PATTERN, data["posted_event_id"]):
        result["posted_event_id"] = data["posted_event_id"]
    if data.get("delivery_status") in {"accepted", "posting", "posted", "processed", "execution_in_progress"}:
        result["delivery_status"] = data["delivery_status"]
    if result.get("ok") is True and not result.get("duplicate") and "posted_event_id" not in result:
        return _failure("bridge_unconfirmed_post", status=status)
    return result


def dispatch_original_message(original_message_id):
    """Dispatch only an actual original Switch message, never a consent claim."""
    if not isinstance(original_message_id, str) or not re.fullmatch(MESSAGE_PATTERN, original_message_id):
        return _failure("invalid_message_id")
    token = _read_token()
    if token is None:
        return _failure("dispatch_token_unavailable")
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=60.0) as client:
            with client.stream("POST", BRIDGE_URL,
                               headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                               json={"message_id": original_message_id}) as response:
                status = response.status_code
                if status < 200 or status >= 500 or 300 <= status < 400:
                    return _failure("bridge_http_error", status=status)
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RECEIPT_BYTES:
                        return _failure("bridge_response_too_large", status=status)
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=_unique_json)
                result = _receipt(data, original_message_id, status)
                # Even a malformed local service must not echo our secret in an
                # otherwise syntactically valid identifier field.
                if token in json.dumps(result):
                    return _failure("bridge_invalid_response", status=status)
                return result
    except httpx.TimeoutException:
        return _failure("bridge_timeout")
    except httpx.HTTPError:
        return _failure("bridge_unavailable")
    except (ValueError, UnicodeError, TypeError, RecursionError):
        return _failure("bridge_invalid_response")


def build_server():
    """Build the official SDK server with one strictly validated tool."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.tools import Tool
    from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata
    from mcp.types import ToolAnnotations
    from pydantic import ConfigDict, Field

    class DispatchArguments(ArgModelBase):
        model_config = ConfigDict(extra="forbid", strict=True)
        original_message_id: str = Field(min_length=1, max_length=200,
                                         pattern="^" + MESSAGE_PATTERN + "$",
                                         description="Exact original incoming Switch room message ID; never a run ID or invented event.")

    tool = Tool(fn=dispatch_original_message, name=TOOL_NAME, title="Dispatch original QA room message",
                description="Pass an original message ID to the fixed local QA bridge. The bridge fetches the authenticated human event and enforces the current-run review rules. Do not supply body, actor or consent. The bridge itself posts the room result; do not duplicate it.",
                parameters=DispatchArguments.model_json_schema(),
                fn_metadata=FuncMetadata(arg_model=DispatchArguments), is_async=False,
                annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                            idempotentHint=True, openWorldHint=False))
    return FastMCP("Intent Replay QA transport", tools=[tool], log_level="ERROR",
                   instructions="Use the single tool only with the original Switch message ID. Transport does not create human approval; the authenticated event and existing QA bridge decide every operation.")


def main():
    if len(sys.argv) != 1:
        print("This stdio server accepts no command-line options.", file=sys.stderr)
        return 2
    try:
        server = build_server()
    except ImportError:
        print("The optional pinned QA MCP dependency is unavailable. Use the configured MCP environment.", file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
