"""Bounded new-development authority using the existing benchmark ledger.

No default authority, network operation, historical limit change, or retry is
introduced here. The controller supplies a fixed plan and source binding before
any request. Semantic rejection belongs to its case, not a provider stop.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from intent_replay.benchmark_budget import AUTHORITY, BudgetBlocked, Ledger, LedgerCall
from intent_replay.benchmark_cases import digest, now
from intent_replay.benchmark_targets import TARGETS, public_response


CONTEXT = 1_048_576
DEADLINE = datetime.fromisoformat("2026-11-03T06:01:48+00:00")
LIMITS = {"total_attempts": 40, "provider_attempts": {"meta": 24, "baseten": 20},
          "combined_usd": "15", "provider_usd": {"meta": "10", "baseten": "10"},
          "input_reservation_tokens": CONTEXT, "max_output_tokens": 16384,
          "diagnostic_attempts": 2}
MODELS = {provider: target["model"] for provider, target in TARGETS.items()}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def public_request(value):
    """Fictional request evidence, without private continuation reasoning."""
    if isinstance(value, list):
        return [public_request(v) for v in value]
    if isinstance(value, dict):
        return {k: public_request(v) for k, v in value.items()
                if k not in ("encrypted_content", "reasoning_content", "encrypted_reasoning")}
    return value


def strict_usage(provider, raw, maximum):
    """Output totals already include reasoning; never add it a second time.

    Missing usage retains the conservative reserve. Present but contradictory
    usage is an accounting integrity failure, distinct from missing evidence.
    """
    if not isinstance(raw, dict):
        return None, "usage_unknown"
    if raw.get("model") != MODELS[provider] or not isinstance(raw.get("id"), str) or not raw["id"]:
        return None, "model_identity_mismatch"
    usage = raw.get("usage")
    if usage is None:
        return None, "usage_unknown"
    if not isinstance(usage, dict):
        return None, "accounting_corruption"
    a, b, details = (("input_tokens", "output_tokens", "output_tokens_details") if provider == "meta"
                     else ("prompt_tokens", "completion_tokens", "completion_tokens_details"))
    if any(k not in usage for k in (a, b)):
        return None, "usage_unknown"
    if any(type(usage[k]) is not int or usage[k] < 0 for k in (a, b)):
        return None, "accounting_corruption"
    total = usage.get("total_tokens")
    if total is not None and (type(total) is not int or total != usage[a] + usage[b]):
        return None, "accounting_corruption"
    detail = usage.get(details)
    if detail is not None and not isinstance(detail, dict):
        return None, "accounting_corruption"
    reasoning = (detail or {}).get("reasoning_tokens")
    if reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= usage[b]):
        return None, "accounting_corruption"
    normalized = {"input_tokens": usage[a], "output_tokens": usage[b], "reasoning_tokens": reasoning,
                  "reasoning_already_in_output_total": True, "native_usage": deepcopy(usage)}
    if usage[a] > CONTEXT or usage[b] > maximum:
        return normalized, "accounting_bound_exceeded"
    return normalized, None


class DevelopmentLedger(Ledger):
    def __init__(self, root, manifest, *, source_binding, clock=None):
        # Copy before binding so a caller cannot edit the live plan in place.
        self.manifest = deepcopy(manifest)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.source_binding = source_binding
        self.current = None
        root = Path(root).resolve()
        expected = Path(manifest["authority_path"]).resolve()
        if (root != expected or root == AUTHORITY.resolve() or root.name != "campaign"
                or ".local" not in root.parts or "fresh-case-development" not in root.parts):
            raise BudgetBlocked("Explicit new fresh-development campaign authority required")
        required = {"schema_version", "campaign_id", "authority_path", "deadline_utc", "case_hashes",
                    "limits", "models", "automatic_retries"}
        hashes = manifest.get("case_hashes", [])
        deadline = datetime.fromisoformat(manifest["deadline_utc"])
        if (not required <= manifest.keys() or manifest["schema_version"] != "fresh-development-campaign-v1"
                or not isinstance(manifest["campaign_id"], str) or not manifest["campaign_id"]
                or manifest["limits"] != LIMITS or manifest["models"] != MODELS
                or manifest["automatic_retries"] != 0 or deadline.utcoffset() is None
                or deadline > DEADLINE or len(hashes) not in (1, 2) or len(set(hashes)) != len(hashes)
                or any(not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in hashes)):
            raise BudgetBlocked("Development plan differs from the authorized bounded scope")
        self.deadline = deadline
        super().__init__(root)
        self.fix("development_manifest", self.manifest)
        self.fix("development_source_binding", self._source())

    def _source(self):
        value = self.source_binding() if callable(self.source_binding) else self.source_binding
        if not isinstance(value, dict) or not value:
            raise BudgetBlocked("Explicit nonempty source binding required")
        return deepcopy(value)

    def check_source(self):
        with self.transaction() as db:
            mismatch = (self.setting(db, "development_source_binding") != self._source()
                        or self.setting(db, "development_manifest") != self.manifest)
        if mismatch:
            self.stop("source_or_manifest_identity_mismatch")
            raise BudgetBlocked("Development source or manifest changed after binding")

    def stop(self, reason, provider=None):
        if provider is not None and provider not in MODELS:
            raise ValueError("Unknown provider")
        with self.transaction() as db:
            key = "stopped:" + provider if provider else "inference_closed"
            db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, json.dumps(reason)))
            self.event(db, "development_stop", {"provider": provider, "reason": reason})

    def close(self, reason):
        self.stop(reason)

    def stop_provider(self, provider, reason):
        self.stop(reason, provider)

    def blockers(self, provider):
        with self.transaction() as db:
            values = [self.setting(db, "inference_closed"), self.setting(db, "stopped:" + provider)]
        return [v for v in values if v] + (["Development deadline reached"] if self.clock() >= self.deadline else [])

    def funding(self, provider, proof=None):
        if provider not in MODELS:
            raise BudgetBlocked("Only the two authorized inference providers are allowed")
        if proof is not None:
            with self.transaction() as db:
                old = self.setting(db, "funding:" + provider)
                used = db.execute("SELECT 1 FROM requests WHERE provider=?", (provider,)).fetchone()
                if used and old != proof:
                    raise BudgetBlocked("Funding/rates are fixed after the first provider reservation")
        return super().funding(provider, proof)

    def register_case(self, case, phase="pilot"):
        if phase != "pilot" or digest(case.model_dump()) not in self.manifest["case_hashes"]:
            raise BudgetBlocked("Case not listed in the new fixed pair")
        pair = {k: case.model_dump()[k] for k in ("initial_booking", "requested_time", "slot_available", "request")}
        self.fix("development_pair_base", pair)
        return super().register_case(case, phase)

    def _reserve(self, db, meta, request_id, logical_id, input_bound):
        provider, role = meta["provider"], meta["role"]
        if self.clock() >= self.deadline or self.setting(db, "inference_closed") or self.setting(db, "stopped:" + provider):
            raise BudgetBlocked("Deadline or campaign/provider stop prevents reservation")
        if (provider not in MODELS or role not in ("customer", "actor", "diagnostic") or meta["phase"] != "pilot"
                or meta["repetition"] not in (0, 1) or input_bound != CONTEXT
                or type(meta["max_output"]) is not int or not 0 < meta["max_output"] <= 16384):
            raise BudgetBlocked("Unlisted development role, cap, repetition, or provider")
        if db.execute("SELECT 1 FROM requests WHERE id=? OR logical_id=?", (request_id, logical_id)).fetchone():
            raise BudgetBlocked("Logical request already reserved; automatic retry is prohibited")
        cases = self.setting(db, "cases:pilot") or []
        if meta["case_hash"] not in self.manifest["case_hashes"] or meta["case_hash"] not in [c["sha256"] for c in cases]:
            raise BudgetBlocked("Request case is not registered in the fixed pair")
        count = lambda sql, args=(): db.execute(sql, args).fetchone()[0]
        if role in ("customer", "diagnostic") and provider != "meta":
            raise BudgetBlocked("Interpretation/diagnostic provider remains Meta")
        if role == "diagnostic":
            if meta.get("attempt_label") not in ("diagnostic-A", "diagnostic-B") or count("SELECT COUNT(*) FROM requests WHERE role='diagnostic'") >= 2:
                raise BudgetBlocked("At most two explicitly labelled diagnostics are allowed")
            prior = [json.loads(row[0]) for row in db.execute("SELECT data FROM events WHERE event='request_reserved'")]
            if any(row.get("role") == "diagnostic" and row.get("attempt_label") == meta["attempt_label"] for row in prior):
                raise BudgetBlocked("This explicit diagnostic label was already reserved; no retry")
        if role == "actor":
            if (self.setting(db, "targets") or {}).get(provider) != meta["target_hash"]:
                raise BudgetBlocked("Native target configuration is not fixed")
            if provider == "baseten" and not (self.setting(db, "capability:baseten") or {}).get("valid_native_proposal"):
                raise BudgetBlocked("Baseten native capability must be established")
            if count("SELECT COUNT(*) FROM requests WHERE role='actor' AND experiment_id=?", (meta["experiment_id"],)) >= 4:
                raise BudgetBlocked("Four native actor rounds per explicit comparison exhausted")
        if count("SELECT COUNT(*) FROM requests") >= LIMITS["total_attempts"]:
            raise BudgetBlocked("Forty-attempt campaign ceiling reached")
        if count("SELECT COUNT(*) FROM requests WHERE provider=?", (provider,)) >= LIMITS["provider_attempts"][provider]:
            raise BudgetBlocked("Provider attempt ceiling reached")
        proof = self.require_funding(db, provider)
        reserve = (Decimal(input_bound) * Decimal(proof["input_per_million"]) + Decimal(meta["max_output"]) * Decimal(proof["output_per_million"])) / Decimal(1_000_000)
        combined = sum((Decimal(r[0]) for r in db.execute("SELECT cost FROM requests")), Decimal(0))
        spent = sum((Decimal(r[0]) for r in db.execute("SELECT cost FROM requests WHERE provider=?", (provider,))), Decimal(0))
        if combined + reserve > Decimal(LIMITS["combined_usd"]):
            raise BudgetBlocked("Combined fifteen-dollar conservative ceiling would be exceeded")
        if spent + reserve > min(Decimal(LIMITS["provider_usd"][provider]), Decimal(proof["balance_usd"])):
            raise BudgetBlocked("Provider ten-dollar cost/credit envelope would be exceeded")
        db.execute("""INSERT INTO requests(id,logical_id,provider,role,phase,case_hash,target_hash,repetition,
          experiment_id,max_output,input_bound,reservation,cost,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (request_id, logical_id, provider, role, meta["phase"], meta["case_hash"], meta["target_hash"], meta["repetition"],
           meta["experiment_id"], meta["max_output"], input_bound, str(reserve), str(reserve), "reserved_unknown", now()))
        self.event(db, "request_reserved", {"request_id": request_id, "reservation_usd": str(reserve), **meta})

    def call(self, *, request, **meta):
        self.check_source()
        if self.current is not None and not self.current.finished:
            raise BudgetBlocked("Previous request must be finalized before another logical attempt")
        provider = meta.get("provider")
        if provider not in MODELS:
            raise BudgetBlocked("Unlisted provider")
        cap = "max_output_tokens" if provider == "meta" else "max_tokens"
        if (len(json.dumps(request, ensure_ascii=True).encode()) > 65536 or request.get("model") != MODELS[provider]
                or request.get(cap) != meta.get("max_output") or request.get("stream", False)):
            self.stop("request_identity_or_envelope_mismatch")
            raise BudgetBlocked("Request model, output bound, stream, or size differs from authorized envelope")
        logical_id = digest(meta)
        checkpoint = {"schema_version": "development-request-checkpoint-v1", "created_at": now(),
                      "campaign_id": self.manifest["campaign_id"], "request_id": logical_id,
                      "request_sha256": digest(request), "provider": provider, "model": request["model"],
                      "endpoint": TARGETS[provider]["base_url"] + ("/responses" if provider == "meta" else "/chat/completions"),
                      "metadata": meta, "max_output_includes_reasoning": True,
                      "input_reservation_tokens": CONTEXT, "headers_retained": False,
                      "private_reasoning_retained": False, "public_request": public_request(request)}
        with self.transaction() as db:
            self._reserve(db, meta, logical_id, logical_id, CONTEXT)
            self.event(db, "no_send_checkpoint", checkpoint)
        try:
            write_new(self.root / "checkpoints" / (logical_id + ".json"), checkpoint)
        except Exception:
            self.stop("checkpoint_persistence_failure")
            raise
        self.current = DevelopmentCall(self, meta, logical_id, CONTEXT, checkpoint)
        return self.current


class DevelopmentCall(LedgerCall):
    def __init__(self, ledger, meta, logical_id, bound, checkpoint):
        super().__init__(ledger, meta, logical_id, bound)
        self.checkpoint, self.raw, self.http_status = checkpoint, None, None
        self.response_hash, self.transport_checked = None, False
        self.transport_error, self.finished = None, False

    def reserve(self):
        self.ledger.check_source()
        if self.hops or self.finished:
            raise BudgetBlocked("Second transport hop or completed request prohibited; no redirect/retry")
        if self.ledger.blockers(self.meta["provider"]):
            raise BudgetBlocked("Deadline/provider stop prevents dispatch")
        with self.ledger.transaction() as db:
            self.ledger.require_funding(db, self.meta["provider"])
        if not self.transport_checked:
            raise BudgetBlocked("Actual serialized native request must be checked before dispatch")
        checkpoint_path = self.ledger.root / "checkpoints" / (self.logical_id + ".json")
        try:
            checkpoint_ok = json.loads(checkpoint_path.read_text(encoding="utf-8")) == self.checkpoint
        except (OSError, ValueError):
            checkpoint_ok = False
        if not checkpoint_ok:
            self.ledger.stop("request_checkpoint_identity_mismatch")
            raise BudgetBlocked("No-send checkpoint was altered")
        return super().reserve()

    def finish(self, *, usage=None, responses=0, successes=0, latency=None, error=None):
        if self.finished:
            raise BudgetBlocked("Attempt result is immutable after finalization")
        with self.ledger.transaction() as db:
            row = db.execute("SELECT completed_at FROM requests WHERE id=?", (self.logical_id,)).fetchone()
            if not row or row[0] is not None:
                raise BudgetBlocked("Attempt is missing or already finalized")
        verified, issue = strict_usage(self.meta["provider"], self.raw, self.meta["max_output"])
        if issue in ("model_identity_mismatch", "accounting_corruption", "accounting_bound_exceeded"):
            self.ledger.stop(issue)
        if (self.http_status in (401, 402, 403, 429) or (self.http_status is not None and self.http_status >= 500)
                or self.transport_error):
            self.ledger.stop_provider(self.meta["provider"], "provider_operational_http_failure" if self.http_status else "provider_transport_failure")
        # Native transport evidence is authoritative over a caller's guessed usage
        # or response counters. Unknown usage retains the full reservation.
        observed_responses = int(self.http_status is not None)
        observed_successes = int(self.http_status is not None and 200 <= self.http_status < 300)
        super().finish(usage=verified, responses=observed_responses, successes=observed_successes,
                       latency=latency, error=("caller_reported_error" if error else issue))
        artifact = {"schema_version": "development-attempt-v1", "campaign_id": self.ledger.manifest["campaign_id"],
                    "request_id": self.logical_id, "provider": self.meta["provider"], "role": self.meta["role"],
                    "http_attempts": self.hops, "http_responses": observed_responses, "http_status": self.http_status,
                    "latency_seconds": latency, "usage": verified, "accounting_issue": issue,
                    "caller_reported_error": bool(error), "transport_error_type": self.transport_error,
                    "response_sha256": self.response_hash,
                    "public_response": public_response(self.meta["provider"], self.raw) if isinstance(self.raw, dict) else None,
                    "private_reasoning_retained": False, "finished_at": now()}
        try:
            write_new(self.ledger.root / "attempts" / (self.logical_id + ".json"), artifact)
            with self.ledger.transaction() as db:
                self.ledger.event(db, "development_attempt_evidence", {"request_id": self.logical_id,
                    "evidence_sha256": digest(artifact), "accounting_issue": issue})
        except Exception:
            self.ledger.stop("attempt_evidence_persistence_failure")
            raise
        finally:
            self.finished = True


def checked_transport(ledger, original_send):
    """Wrap httpx.Client.send around a bounded SDK call; no headers are retained."""
    def send(client, request, *args, **kwargs):
        call = ledger.current
        if (call is None or call.transport_checked or call.finished or request.method != "POST"
                or str(request.url) != call.checkpoint["endpoint"]):
            ledger.stop("unexpected_transport_identity")
            raise BudgetBlocked("Unexpected HTTP operation outside the fixed native endpoint")
        try:
            payload = json.loads(request.content)
        except (ValueError, TypeError):
            ledger.stop("serialized_request_unreadable")
            raise BudgetBlocked("Actual serialized request is not readable JSON") from None
        if digest(payload) != call.checkpoint["request_sha256"]:
            ledger.stop("serialized_request_identity_mismatch")
            raise BudgetBlocked("Actual SDK payload differs from preserved no-send checkpoint")
        call.transport_checked = True
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
            return response
        except BudgetBlocked:
            raise
        except Exception as exc:
            # Never retain exception text, headers, or arbitrary provider bodies.
            call.transport_error = type(exc).__name__
            ledger.stop_provider(call.meta["provider"], "provider_transport_failure")
            raise
    return send
