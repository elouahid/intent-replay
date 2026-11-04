"""One separately authorized Meta proposal; all replay semantics stay unchanged.

There is no retry, recovery inference, customer interpretation or audio request.
Legacy forced-tool evidence remains readable. New requests use Meta's supported
automatic tool selection; a returned proposal is required before local replay.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import threading

from intent_replay.agent_adapter import TOOLS
from intent_replay.benchmark_cases import CaseSpec, check_seal, digest, now, seal, validate_freeze
from intent_replay.benchmark_execution import execution_contract, prepare, validate_prepared, visible_input
from intent_replay.benchmark_targets import NativeCapture, TargetConfig, TARGETS, PROPOSAL_INSTRUCTIONS, public_response
from intent_replay.development_budget import strict_usage


SCHEMA = "live-proposal-status-v1"
MODEL = TARGETS["meta"]["model"]
ENDPOINT = TARGETS["meta"]["base_url"] + "/responses"
MAX_OUTPUT = 2048
INPUT_BOUND = 1_048_576
INPUT_RATE = Decimal("1.25")
OUTPUT_RATE = Decimal("4.25")
RESERVATION = (INPUT_BOUND * INPUT_RATE + MAX_OUTPUT * OUTPUT_RATE) / 1_000_000
CEILING = Decimal("2")
FORCED_CHOICE = {"type": "function", "name": "reschedule_booking"}
NOTE = "Reschedule tool preselected; Meta generates the proposal arguments. One attempt; no retry. Saved customer interpretation is reused."
LEGACY_PROFILE = "legacy-forced-v1"
AUTO_PROFILE = "auto-direct-v2"
PROFILES = (LEGACY_PROFILE, AUTO_PROFILE)
DIRECT_INSTRUCTIONS = PROPOSAL_INSTRUCTIONS + """
For this single-response proposal, the supplied booking context is sufficient.
Do not call get_booking. Return the reschedule_booking proposal directly using
the customer's request, then stop. Do not perform further actions.
"""
AUTO_NOTE = "Meta chooses whether to call a tool with tool_choice auto. The direct-proposal prompt uses the supplied booking context. One attempt; no retry. Saved customer interpretation is reused."


def public_http_error(body):
    """Retain bounded allowlisted diagnostics, never arbitrary echoed content.

    Follows the historical call-review error policy without importing its pilot
    authority. The original response-byte hash is retained separately.
    """
    diagnostic = {"policy": "allowlisted-api-error-v1", "body_available": body is not None,
                  "full_body_retained": False, "withheld_fields": []}
    fields = body.get("error", body) if isinstance(body, dict) else None
    if not isinstance(fields, dict):
        return diagnostic
    allowed = {
        "type": {"invalid_request_error", "authentication_error", "permission_error", "rate_limit_error", "server_error", "api_error"},
        "code": {"invalid_value", "unsupported_value", "invalid_parameter", "invalid_request_error", "bad_request", "invalid_api_key", "rate_limit_exceeded", "insufficient_quota", "context_length_exceeded", "model_not_found"},
        "param": {"tool_choice", "tools", "model", "input", "instructions", "messages", "max_output_tokens", "max_tokens", "store", "stream", "n", "parallel_tool_calls", "include"},
    }
    for field, values in allowed.items():
        value = fields.get(field)
        if field in fields and value is None:
            diagnostic[field] = None
        elif isinstance(value, str) and len(value) <= 64 and value in values:
            diagnostic[field] = value
        elif field in fields:
            diagnostic["withheld_fields"].append(field)
    message = fields.get("message")
    if isinstance(message, str) and len(message) <= 256:
        normalized = " ".join(message.lower().translate(str.maketrans("", "", "\"'`")).split()).rstrip(".")
        if normalized == "only auto is supported for tool_choice":
            diagnostic["message"] = message
    if "message" in fields and "message" not in diagnostic:
        diagnostic["withheld_fields"].append("message")
        diagnostic["message_exceeds_limit"] = isinstance(message, str) and len(message) > 256
    return diagnostic


def private_http_error(body):
    """Local-only bounded diagnostic; never returned in workflow/public output.

    Only four error fields are eligible. Redact configured credentials and
    common bearer/key forms before truncating, so a cut cannot expose a partial
    known credential. Headers, request payloads and arbitrary fields are omitted.
    """
    result = {"policy": "private-redacted-api-error-v1", "public_export_allowed": False,
              "full_body_retained": False, "truncated_fields": []}
    fields = body.get("error", body) if isinstance(body, dict) else None
    if not isinstance(fields, dict):
        result["error_fields_available"] = False
        return result
    result["error_fields_available"] = True
    secrets = [os.getenv(key, "").strip() for key in ("MODEL_API_KEY", "BASETEN_API_KEY")]
    for key, limit in (("type", 128), ("code", 128), ("param", 256), ("message", 4096)):
        value = fields.get(key)
        if value is None and key in fields:
            result[key] = None
        elif isinstance(value, str):
            for secret in secrets:
                if secret:
                    value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/|=\-]+", "Bearer [REDACTED]", value)
            value = re.sub(r"\bLLM[|_][A-Za-z0-9|_\-]+", "[REDACTED]", value)
            value = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}", "[REDACTED]", value)
            value = "".join(ch for ch in value if ch in "\n\t" or ord(ch) >= 32)
            # Byte limits also bound non-ASCII diagnostic text and the final JSON.
            encoded = value.encode("utf-8")
            if len(encoded) > limit:
                value = encoded[:limit].decode("utf-8", errors="ignore") + " [TRUNCATED]"
                result["truncated_fields"].append(key)
            result[key] = value
    return result


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expected_request(config, case, profile=LEGACY_PROFILE):
    return {"model": MODEL, "instructions": config.developer_instructions,
            "input": visible_input(case), "tools": deepcopy(TOOLS), "max_output_tokens": MAX_OUTPUT,
            "parallel_tool_calls": False, "store": False,
            "tool_choice": deepcopy(FORCED_CHOICE) if profile == LEGACY_PROFILE else "auto",
            "include": ["reasoning.encrypted_content"]}


class OneShotCall:
    def __init__(self, owner, request):
        self.owner, self.request = owner, deepcopy(request)
        self.ids = [owner.request_id]
        self.thread_id = threading.get_ident()
        self.transport_checked = False
        self.reserved = False
        self.finished = False
        self.raw = None
        self.http_status = None
        self.transport_error = None
        self.response_hash = None
        self.usage = None
        self.accounting_issue = None
        self.latency = None
        self.provider_error = None

    def reserve(self):
        # Called by the SDK request hook immediately before physical dispatch.
        if not self.transport_checked or self.reserved or self.finished:
            raise RuntimeError("One-shot transport reservation rejected; no retry or redirect.")
        self.owner.check_binding()
        write_once(self.owner.root / "dispatch-reserved.json", {
            "schema_version": "live-proposal-dispatch-v1", "reserved_at": now(),
            "request_id": self.ids[0], "request_sha256": digest(self.request),
            "endpoint": ENDPOINT, "reservation_usd": str(RESERVATION),
            "input_bound": INPUT_BOUND, "max_output_tokens": MAX_OUTPUT,
            "request": self.request, "forced_tool_choice": self.owner.profile == LEGACY_PROFILE,
        })
        self.reserved = True

    def finish(self, *, latency=None, error=None, **unused):
        if self.finished:
            raise RuntimeError("One-shot result already finalized.")
        self.usage, self.accounting_issue = strict_usage("meta", self.raw, MAX_OUTPUT)
        self.latency = latency
        write_once(self.owner.root / "native-attempt.json", seal({
            "schema_version": "live-proposal-attempt-v1", "finished_at": now(),
            "request_id": self.ids[0], "http_attempts": int(self.reserved),
            "http_status": self.http_status, "response_sha256": self.response_hash,
            "public_response": public_response("meta", self.raw) if self.raw is not None else None,
            "usage": self.usage, "accounting_issue": self.accounting_issue,
            "latency_seconds": latency, "caller_reported_error": bool(error),
            "transport_error_type": self.transport_error, "private_reasoning_retained": False,
            "provider_error": self.provider_error,
            "private_error_diagnostic_saved": (self.owner.root / "private-provider-error.json").is_file(),
        }))
        self.finished = True


class LiveProposal:
    """Durable single-use authority, separate from every historical campaign."""
    def __init__(self, root, snapshot, *, retained=False, profile=LEGACY_PROFILE):
        if profile not in PROFILES:
            raise ValueError("Unsupported live proposal request profile.")
        self.profile = profile
        self.request_id = "live-meta-proposal-1" if profile == LEGACY_PROFILE else "live-meta-auto-proposal-1"
        self.root = Path(root).resolve()
        self.retained = retained
        if retained:
            if not self.root.is_dir():
                raise ValueError("Retained live-capture directory is missing; no inference fallback.")
        else:
            self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot = deepcopy(snapshot)
        self.config = (TargetConfig(provider="meta", max_rounds=1) if profile == LEGACY_PROFILE else
                       TargetConfig(provider="meta", max_rounds=1, instruction_version="direct-proposal-v2",
                                    developer_instructions=DIRECT_INSTRUCTIONS))
        self.current = None
        self.active = False
        self.lock = threading.Lock()
        self.rows = {r["case"]["case_id"]: r for r in self.snapshot["cases"]}
        if set(self.rows) != {"fresh-withdrawal", "fresh-control"}:
            raise ValueError("Only the exact existing withdrawal/control pair is supported.")
        self.cases = {key: CaseSpec.model_validate(row["case"]) for key, row in self.rows.items()}
        for key, case in self.cases.items():
            validate_freeze(case, self.rows[key]["interpretation"]["record"])
        inputs = [visible_input(c) for c in self.cases.values()]
        if inputs[0] != inputs[1]:
            raise ValueError("The pair does not share an identical delivered context and request.")
        self.request = expected_request(self.config, self.cases["fresh-withdrawal"], profile)
        self.binding = {"schema_version": "live-proposal-authority-v1", "request_limit": 1,
                        "provider": "meta", "model": MODEL, "endpoint": ENDPOINT,
                        "ceiling_usd": str(CEILING), "reservation_usd": str(RESERVATION),
                        "input_usd_per_million": str(INPUT_RATE), "output_usd_per_million": str(OUTPUT_RATE),
                        "pricing_source": "https://dev.meta.ai/docs/pricing-rate-limits",
                        "pricing_checked_date": "2026-11-04", "pricing_tier": "Standard Muse Spark 1.3",
                        "input_bound": INPUT_BOUND, "max_output_tokens": MAX_OUTPUT,
                        "automatic_retries": 0, "forced_tool_choice": FORCED_CHOICE,
                        "request_sha256": digest(self.request), "configuration_sha256": self.config.sha256,
                        "execution_contract_sha256": execution_contract(),
                        "cases": {k: {"case_sha256": digest(c.model_dump()),
                                      "freeze_sha256": self.rows[k]["interpretation"]["record"]["sha256"]}
                                  for k, c in self.cases.items()}}
        # Do not add fields to the legacy authority: its original seal and
        # request/configuration bindings must remain exactly replayable.
        if profile == AUTO_PROFILE:
            self.binding.update(request_profile=profile, forced_tool_choice=None, tool_choice="auto")
        if RESERVATION > CEILING:
            raise ValueError("Conservative reservation exceeds the separate ceiling.")
        if not (self.root / "authority.json").exists():
            if retained:
                raise ValueError("Retained authority is missing; no source file was created.")
            write_once(self.root / "authority.json", self.binding)
        self.check_binding()
        if retained and self.status()["status"] not in ("captured", "failed"):
            raise ValueError("Retained live capture is incomplete or invalid; no inference fallback.")

    def check_binding(self):
        if read(self.root / "authority.json") != self.binding or execution_contract() != self.binding["execution_contract_sha256"]:
            raise RuntimeError("One-shot source or authority binding changed; dispatch is blocked.")

    def call(self, *, request, ordinal, max_output, **unused):
        if (not self.active or self.current is not None or ordinal != 1 or max_output != MAX_OUTPUT
                or request != self.request):
            raise RuntimeError("Only the one exact bound native request is authorized.")
        self.check_binding()
        self.current = OneShotCall(self, request)
        return self.current

    def _stored(self):
        result = read(self.root / "result.json")
        check_seal(result)
        if result.get("authority_sha256") != digest(self.binding):
            raise ValueError("Saved result authority binding differs.")
        capture = read(self.root / "capture.json")
        check_seal(capture)
        if (capture["sha256"] != result["capture_sha256"] or capture["status"] != result["capture_status"]
                or capture["visible_input"] != self.request["input"]
                or capture["configuration_sha256"] != self.config.sha256
                or capture["target"] != self.config.public() or result["attempts"] != 1):
            raise ValueError("Saved capture binding differs.")
        marker = read(self.root / "attempt-started.json")
        if marker.get("authority_sha256") != digest(self.binding):
            raise ValueError("Saved attempt marker binding differs.")
        if result["http_attempts"] == 1:
            dispatch = read(self.root / "dispatch-reserved.json")
            attempt = read(self.root / "native-attempt.json")
            check_seal(attempt)
            if (dispatch.get("request") != self.request or dispatch.get("request_sha256") != digest(self.request)
                    or dispatch.get("endpoint") != ENDPOINT or attempt.get("http_attempts") != 1
                    or attempt.get("http_status") != result["http_status"] or attempt.get("usage") != result["usage"]
                    or attempt.get("accounting_issue") != result["accounting_issue"]):
                raise ValueError("Saved dispatch and native attempt differ from the result.")
            if self.profile == AUTO_PROFILE and attempt.get("provider_error") != result.get("provider_error"):
                raise ValueError("Saved provider diagnostics differ from the result.")
        elif result["http_attempts"] != 0:
            raise ValueError("Saved attempt count is unsupported.")
        if result["status"] == "failed" and result["prepared_sha256"]:
            raise ValueError("Failed proposal must not expose prepared replay evidence.")
        if result["status"] == "captured":
            for key in self.cases:
                prepared = read(self.root / "prepared" / (key + "-meta.json"))
                validate_prepared(prepared)
                if (prepared["capture"] != capture or prepared["case"] != self.cases[key].model_dump()
                        or prepared["freeze"] != self.rows[key]["interpretation"]["record"]
                        or result["prepared_sha256"][key] != prepared["sha256"]):
                    raise ValueError("Saved prepared artifact differs from the exact live binding.")
        return result

    def status(self):
        base = {"schema_version": SCHEMA, "status": "ready", "can_generate": not self.retained,
                "attempts": 0, "request_limit": 1, "model": MODEL,
                "request_profile": self.profile, "note": NOTE if self.profile == LEGACY_PROFILE else AUTO_NOTE,
                "retained_capture_mode": self.retained,
                "forced_tool_choice": deepcopy(FORCED_CHOICE) if self.profile == LEGACY_PROFILE else None,
                "tool_choice": deepcopy(self.request["tool_choice"]), "reservation_usd": str(RESERVATION),
                "ceiling_usd": str(CEILING), "estimated_cost_usd": None,
                "usage": None, "native_status": None, "error": None, "provider_error": None,
                "backup_url": "http://127.0.0.1:8048/demo"}
        try:
            self.check_binding()
            if (self.root / "result.json").exists():
                return {**base, **self._stored(), "can_generate": False}
            if (self.root / "attempt-started.json").exists():
                return {**base, "status": "generating" if self.active else "unknown", "can_generate": False,
                        "attempts": 1, "http_attempts": int((self.root / "dispatch-reserved.json").exists()),
                        "error": None if self.active else "Attempt was started without a complete retained result; no resend.",
                        "estimated_cost_usd": str(RESERVATION), "cost_basis": "conservative reservation; actual usage unknown"}
        except (OSError, ValueError, KeyError, RuntimeError, TypeError):
            return {**base, "status": "unknown", "can_generate": False,
                    "attempts": int((self.root / "attempt-started.json").exists()),
                    "error": "Saved authority/evidence validation failed; retained files were not changed."}
        return base

    def workflow(self):
        snapshot = deepcopy(self.snapshot)
        status = self.status()
        for row in snapshot["cases"]:
            key = row["case"]["case_id"]
            prepared = read(self.root / "prepared" / (key + "-meta.json")) if status["status"] == "captured" else None
            row["providers"] = {"meta": {"status": "prepared" if prepared else "awaiting_live_proposal",
                "model": MODEL, "capture": prepared["capture"] if prepared else None, "prepared": prepared,
                "usage": [status["usage"]] if status["usage"] else [], "request_ids": [self.request_id] if status["attempts"] else [],
                "http_attempts": status.get("http_attempts", 0), "errors": [status["error"]] if status["error"] else [],
                "blockers": [] if prepared else ["One explicit live Meta proposal is required."]}}
            row["interpretation"]["reused"] = True
        snapshot["campaign"] = {"id": "single-live-meta-proposal-20261104" if self.profile == LEGACY_PROFILE else "single-live-meta-auto-proposal-repair-20261104", "closed": not status["can_generate"],
            "limits": {"total_attempts": 1, "combined_usd": str(CEILING)},
            "totals": {"http_attempts": status.get("http_attempts", 0), "estimated_usd": status["estimated_cost_usd"] or "0"}}
        snapshot["live_proposal"] = status
        return snapshot

    def generate(self):
        if self.retained:
            raise ValueError("Retained evidence mode has no inference operation.")
        if not self.lock.acquire(blocking=False):
            raise ValueError("The one attempt is already running.")
        try:
            if not self.status()["can_generate"]:
                raise ValueError("The one logical attempt was already consumed or evidence is unavailable; no retry.")
            write_once(self.root / "attempt-started.json", {"started_at": now(), "authority_sha256": digest(self.binding)})
            self.active = True
            # A lookup-only response is retained as a non-proposal. ValueError
            # is handled by the unchanged native adapter, so no continuation,
            # local tool dispatch or extra provider request can occur.
            capture = NativeCapture(self.config, lambda *args: (_ for _ in ()).throw(ValueError("Lookup requested but not dispatched in this one-request direct-proposal profile.")),
                                    ledger=self, metadata={}).run(self.cases["fresh-withdrawal"].turns()[:2],
                                                                 capability=self.profile == LEGACY_PROFILE)
            write_once(self.root / "capture.json", capture)
            call = self.current
            issue = call.accounting_issue if call else "not_dispatched"
            usage = call.usage if call else None
            known_cost = usage is not None and issue is None
            cost = ((usage["input_tokens"] * INPUT_RATE + usage["output_tokens"] * OUTPUT_RATE) / 1_000_000) if known_cost else RESERVATION
            dispatched = bool(call and call.reserved)
            if not dispatched:
                cost = Decimal("0")
            result = {"authority_sha256": digest(self.binding), "status": "failed", "attempts": 1,
                      "captured_at": now(), "capture_sha256": capture["sha256"], "capture_status": capture["status"],
                      "http_attempts": int(call.reserved) if call else 0, "http_status": call.http_status if call else None,
                      "native_status": (call.raw or {}).get("status") if call else None,
                      "provider_error": call.provider_error if call else None,
                      "usage": usage, "estimated_cost_usd": str(cost), "accounting_issue": issue,
                      "cost_basis": ("no physical request was dispatched" if not dispatched else
                                     "verified native token totals; reasoning included in output" if known_cost else
                                     "conservative reservation; actual usage unknown"),
                      "latency_seconds": call.latency if call else None,
                      "error": "; ".join(capture.get("errors", [])) or issue, "prepared_sha256": {}}
            if call and call.provider_error and call.provider_error.get("message"):
                result["error"] = (result["error"] or "Provider request rejected.") + " " + call.provider_error["message"]
            if call and call.reserved and call.http_status is None:
                result["status"] = "unknown"
            if capture["status"] == "proposal_captured" and issue is None and call and call.reserved:
                for key, case in self.cases.items():
                    artifact = prepare(case, self.rows[key]["interpretation"]["record"], capture, provenance={
                        "capture_source": "live_meta", "interpretation_source": "existing_saved_customer_interpretation",
                        "forced_tool_choice": FORCED_CHOICE if self.profile == LEGACY_PROFILE else None,
                        "tool_choice": deepcopy(self.request["tool_choice"]), "request_profile": self.profile,
                        "request_sha256": digest(self.request),
                        "shared_capture_for_withdrawal_and_control": True, "new_model_requests": 1})
                    validate_prepared(artifact)
                    write_once(self.root / "prepared" / (key + "-meta.json"), artifact)
                    result["prepared_sha256"][key] = artifact["sha256"]
                result.update(status="captured", error=None)
            write_once(self.root / "result.json", seal(result))
        finally:
            self.active = False
            self.lock.release()
        return self.status()


def checked_transport(owner, original_send):
    """Deny all outbound HTTP except this exact active, checkpointed SDK POST."""
    def send(client, request, *args, **kwargs):
        call = owner.current
        if (not owner.active or call is None or call.finished or call.transport_checked
                or call.thread_id != threading.get_ident() or request.method != "POST"
                or str(request.url) != ENDPOINT):
            raise RuntimeError("Outbound HTTP blocked outside the single bound Meta request.")
        try:
            actual = json.loads(request.content)
        except (ValueError, TypeError):
            raise RuntimeError("Serialized native request is unreadable; no dispatch.") from None
        if actual != call.request or digest(actual) != owner.binding["request_sha256"]:
            raise RuntimeError("Serialized native request differs from its bound proposal; no dispatch.")
        owner.check_binding()
        call.transport_checked = True
        kwargs["follow_redirects"] = False
        try:
            response = original_send(client, request, *args, **kwargs)
            call.http_status = response.status_code
            response.read()
            call.response_hash = hashlib.sha256(response.content).hexdigest()
            if response.is_success:
                try:
                    call.raw = response.json()
                except ValueError:
                    pass
            elif len(response.content) <= 16_384:
                try:
                    error_body = response.json()
                    call.provider_error = public_http_error(error_body)
                    write_once(owner.root / "private-provider-error.json", private_http_error(error_body))
                except ValueError:
                    call.provider_error = public_http_error(None)
            else:
                call.provider_error = {"policy": "allowlisted-api-error-v1", "body_available": True,
                                       "full_body_retained": False, "body_exceeds_limit": True,
                                       "withheld_fields": ["body"]}
            return response
        except Exception as exc:
            call.transport_error = type(exc).__name__
            raise
    return send


async def deny_async_http(*args, **kwargs):
    raise RuntimeError("Async outbound HTTP is disabled in the one-shot demo.")
