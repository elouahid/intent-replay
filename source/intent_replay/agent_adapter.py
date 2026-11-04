"""Bounded native Responses tool execution; no text-to-tool fallback."""

import json
from copy import deepcopy
import hashlib

from openai import APIConnectionError, APIStatusError, APITimeoutError

from intent_replay.meta_client import AttemptBudget, HTTPAttemptLimitError, MissingAPIKeyError, MODEL_NAME, create_client
from intent_replay.models import APICall


AGENT_INSTRUCTIONS = """You operate a local fictional booking demonstration. Use only the supplied
tools to inspect the booking and reschedule it when requested. Never
claim a mutation merely because it was requested. Never attempt external contact or other
operations. After tools, return one concise
English booking statement with the reference, ISO date, numeric time, and named timezone.
State whether the reschedule occurred. Use persisted_event_facts in tool results for
event ordering: increasing sequence is backend order. A customer message delivered
after a function result may already have been received and accepted before its action
decision. Conversational delivery order is not evidence of backend order. Report
completion, suppression, rejection and restoration only when supported by the returned
persisted records. Give the current booking details. Do not invent results.
"""

TOOLS = [
    {"type": "function", "name": "get_booking", "description": "Read the committed booking from local SQLite.",
     "parameters": {"type": "object", "properties": {"reference": {"type": "string"}}, "required": ["reference"], "additionalProperties": False}, "strict": True},
    {"type": "function", "name": "reschedule_booking", "description": "Request a booking reschedule. Describe the returned outcome accurately; a request alone does not prove the booking changed.",
     "parameters": {"type": "object", "properties": {"reference": {"type": "string"}, "requested_time": {"type": "string", "description": "Complete ISO 8601 date and time including an explicit UTC offset."}, "timezone": {"type": "string", "description": "Named IANA timezone of the booking."}}, "required": ["reference", "requested_time", "timezone"], "additionalProperties": False}, "strict": True},
]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not accepted.")
        result[key] = value
    return result


def public_response(response):
    """Never retain private reasoning text or encrypted reasoning in evidence exports."""
    result = {key: deepcopy(response.get(key)) for key in ("id", "model", "status", "usage", "incomplete_details") if key in response}
    output = response.get("output")
    result["output"] = [deepcopy(item) for item in output if isinstance(item, dict) and item.get("type") != "reasoning"] if isinstance(output, list) else []
    if not isinstance(output, list):
        result["invalid_output_type"] = type(output).__name__
    return result


class AgentSession:
    def __init__(self, dispatch, *, responder=None, budget=None, max_rounds=4, max_tool_calls=8, on_message=None):
        if type(max_rounds) is not int or not 1 <= max_rounds <= 8:
            raise ValueError("Agent rounds must be between one and eight.")
        if type(max_tool_calls) is not int or not 1 <= max_tool_calls <= 16:
            raise ValueError("Tool calls must be between one and sixteen.")
        self.dispatch = dispatch
        self.responder = responder
        self.budget = budget or AttemptBudget(max_rounds + 1)
        self.max_rounds, self.max_tool_calls = max_rounds, max_tool_calls
        self.on_message = on_message
        self.history = []
        self.calls_seen = set()
        self.report = {"status": "not_started", "model": MODEL_NAME, "source": "authored_test" if responder else "live_meta",
                       "responses": [], "tool_calls": [], "api_calls": [], "errors": [], "max_rounds": max_rounds,
                       "max_tool_calls": max_tool_calls, "http_attempts": 0, "http_responses": 0, "successful_http_responses": 0,
                       "prompt_tool_sha256": hashlib.sha256((AGENT_INSTRUCTIONS + json.dumps(TOOLS, sort_keys=True)).encode()).hexdigest(),
                       "prompt_version": "booking-agent-v2", "tool_evidence_version": "booking-tool-evidence-v2",
                       "max_output_tokens": 2048, "visible_messages": [], "requests": []}

    def _error(self, message):
        self.report["status"] = "error"
        self.report["errors"].append(message)
        return None

    def _request(self):
        request = {"model": MODEL_NAME, "instructions": AGENT_INSTRUCTIONS, "input": deepcopy(self.history),
                   "tools": deepcopy(TOOLS), "max_output_tokens": 2048, "parallel_tool_calls": False,
                   "tool_choice": "auto", "store": False, "include": ["reasoning.encrypted_content"]}
        accounting = APICall()
        self.report["requests"].append({"input": self.public_history(),
            "input_sha256": hashlib.sha256(json.dumps(request["input"], sort_keys=True).encode()).hexdigest(),
            "public_input_sha256": hashlib.sha256(json.dumps(self.public_history(), sort_keys=True).encode()).hexdigest(),
            "private_reasoning_omitted": any(item.get("type") == "reasoning" for item in request["input"])})
        try:
            if self.responder:
                response = self.responder(request)
            else:
                with create_client(timeout=45.0, api_call=accounting, request_guard=self.budget.reserve) as client:
                    response = client.responses.create(**request).model_dump(mode="json")
            usage = response.get("usage") if isinstance(response, dict) else None
            if isinstance(usage, dict):
                accounting.usage = {key: value for key, value in usage.items() if key in ("input_tokens", "output_tokens", "total_tokens") and type(value) is int and value >= 0} or None
            return response
        except MissingAPIKeyError:
            self._error("MODEL_API_KEY is missing. Set it in the project-root .env file.")
        except HTTPAttemptLimitError:
            self._error("HTTP attempt budget exhausted; no further request was dispatched.")
        except APITimeoutError:
            self._error("Meta agent request timed out.")
        except APIStatusError as error:
            self._error(f"Meta agent API returned HTTP {error.status_code}.")
        except APIConnectionError as error:
            self._error("HTTP attempt budget exhausted; no further request was dispatched." if isinstance(error.__cause__, HTTPAttemptLimitError) else "Could not connect to Meta agent API.")
        except Exception:
            self._error("Agent generation failed; diagnostic details were withheld.")
        finally:
            if not self.responder and accounting.http_attempts == 0:
                accounting.status = "failed_preflight"
            elif accounting.http_attempts and not accounting.http_responses:
                accounting.status = "transport_failed"
            self.report["api_calls"].append(accounting.model_dump())
            for key in ("http_attempts", "http_responses", "successful_http_responses"):
                self.report[key] += getattr(accounting, key)
        return None

    def public_history(self):
        return [deepcopy(item) for item in self.history if item.get("type") != "reasoning"]

    def add_result(self, call, result, *, status=None):
        self.calls_seen.add(call["call_id"])
        self.report["tool_calls"].append({"call_id": call["call_id"], "name": call["name"],
            "raw_arguments": call["arguments"], "status": status or ("completed" if result.get("ok") else "rejected"), "result": result,
            "tool_result_sha256": hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
        self.history.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(result)})

    def generate(self, turns, *, capture=False):
        for turn in turns:
            self.history.append({"role": "user" if turn.role == "customer" else "assistant", "content": turn.text})
        while len(self.report["responses"]) < self.max_rounds:
            response = self._request()
            if response is None:
                return None
            # Retain bounded native output, including rejected calls; never synthesize a model answer.
            if not isinstance(response, dict) or len(json.dumps(response)) > 100_000:
                return self._error("Agent response is not a bounded native Responses object.")
            self.report["responses"].append(public_response(response))
            # Visible text is retained even when this response is incomplete or rejected.
            for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
                if isinstance(item, dict) and item.get("type") == "message":
                    for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
                        if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                            text = part["text"]
                            self.report["visible_messages"].append(text)
                            if self.on_message:
                                self.on_message(text)
            if response.get("status") != "completed" or not isinstance(response.get("model"), str) or not response["model"].strip():
                return self._error("Agent response was incomplete or omitted its model.")
            output = response.get("output")
            if not isinstance(output, list) or not output or len(output) > 16:
                return self._error("Agent response has missing or excessive output items.")
            calls, texts = [], []
            for item in output:
                if not isinstance(item, dict):
                    return self._error("Agent output item is malformed.")
                if item.get("type") in ("function_call", "message") and item.get("status") not in (None, "completed"):
                    return self._error("Agent output item is incomplete; no calls from this response were dispatched.")
                if item.get("type") == "function_call":
                    calls.append(item)
                elif item.get("type") == "message" and item.get("role") == "assistant":
                    content = item.get("content")
                    if not isinstance(content, list) or not content:
                        return self._error("Agent message content is malformed.")
                    for part in content:
                        if not isinstance(part, dict) or part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                            return self._error("Agent response contains unsupported or refused content.")
                        texts.append(part["text"])
                elif item.get("type") == "reasoning":
                    continue
                else:
                    return self._error("Agent response contains an unsupported output item.")
            if len(calls) > 1:
                return self._error("Multiple calls in one response are unsupported; no calls from this response were dispatched.")
            # Keep native phase and content for manual stateless continuation.
            for item in output:
                if item.get("type") == "reasoning" and item.get("encrypted_content"):
                    self.history.append({"type": "reasoning", "encrypted_content": item["encrypted_content"], "summary": []})
                elif item.get("type") == "message":
                    message = {"type": "message", "role": "assistant", "content": deepcopy(item["content"])}
                    if item.get("phase"):
                        message["phase"] = item["phase"]
                    self.history.append(message)
                elif item.get("type") == "function_call":
                    self.history.append({key: item.get(key) for key in ("type", "call_id", "name", "arguments")})
            if not calls:
                text = "\n".join(texts)
                if not text.strip() or len(text) > 8000:
                    return self._error("Agent final statement is missing or too long.")
                self.report["status"] = "completed"
                return {"kind": "final", "text": text}
            if len(self.report["tool_calls"]) + len(calls) > self.max_tool_calls:
                return self._error("Agent tool-call limit exhausted; this batch was not dispatched.")
            # Validate the entire batch before the first dispatch to avoid partial malformed batches.
            decoded = []
            batch_ids = set()
            for call in calls:
                call_id, name, arguments = call.get("call_id"), call.get("name"), call.get("arguments")
                try:
                    if not isinstance(call_id, str) or not 1 <= len(call_id) <= 64 or call_id in self.calls_seen or call_id in batch_ids:
                        raise ValueError()
                    if name not in ("get_booking", "reschedule_booking") or not isinstance(arguments, str) or len(arguments) > 2048:
                        raise ValueError()
                    args = json.loads(arguments, object_pairs_hook=unique_object)
                    required = {"reference"} if name == "get_booking" else {"reference", "requested_time", "timezone"}
                    if not isinstance(args, dict) or set(args) != required or any(not isinstance(value, str) or not 1 <= len(value) <= 80 for value in args.values()):
                        raise ValueError()
                except (ValueError, TypeError):
                    self.report["tool_calls"].append({"call_id": call_id, "name": name, "raw_arguments": arguments, "status": "rejected", "error": "Invalid or unknown tool call; no calls in this batch were dispatched."})
                    return self._error("Invalid or unknown tool call; no calls in this batch were dispatched.")
                batch_ids.add(call_id)
                decoded.append((call, args))
            for call, args in decoded:
                if capture and call["name"] == "reschedule_booking":
                    self.report["status"] = "proposal_captured"
                    return {"kind": "proposal", "call": deepcopy(call), "arguments": args}
                try:
                    result = self.dispatch(call["name"], args)
                except (ValueError, TypeError):
                    result = {"ok": False, "error": "Tool arguments do not identify the authorized local booking/action."}
                except Exception:
                    result = {"ok": False, "error": "Local tool failed; no success is inferred. Read committed evidence before making a claim."}
                self.add_result(call, result)
        return self._error("Agent round limit exhausted; no final statement was substituted.")
