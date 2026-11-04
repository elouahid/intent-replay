"""Local controller: immutable caches, fixed campaign, paid inference, CPU replay."""
import json
from pathlib import Path
import re
import tempfile
import time
from decimal import Decimal

from intent_replay.benchmark_budget import Ledger, BudgetBlocked
from intent_replay.benchmark_cases import CaseSpec, INTERPRETATION_CONTRACT, digest, freeze_case, freeze_key, now, seal, validate_freeze
from intent_replay.benchmark_execution import create_environment, execute_prepared, prepare, validate_prepared
from intent_replay.benchmark_targets import NativeCapture, TARGETS, TargetConfig, check_runtime_config
from intent_replay.meta_client import MODEL_NAME, PROJECT_ROOT
from intent_replay.temporal_interpreter import CUSTOMER_INSTRUCTIONS, interpret_customers, turn_payload


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)


class BenchmarkController:
    def __init__(self, output=None, ledger=None):
        self.ledger = ledger or Ledger()
        self.output = Path(output) if output is not None else PROJECT_ROOT / ".local" / "benchmark-reports"
        self.cache = self.ledger.root / "artifacts"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)

    def readiness(self):
        exported = self.ledger.export()
        providers = {}
        for name in TARGETS:
            reasons = []
            if exported["settings"].get("inference_closed"):
                reasons.append("Milestone inference is closed; saved captures/freezes remain reusable without a model request.")
            try:
                check_runtime_config(TargetConfig(provider=name))
            except (ValueError, RuntimeError) as exc:
                reasons.append(str(exc))
            with self.ledger.transaction() as db:
                try:
                    self.ledger.require_funding(db, name)
                except BudgetBlocked as exc:
                    reasons.append(str(exc))
                capability = self.ledger.setting(db, "capability:" + name)
            if name == "baseten" and not (capability or {}).get("valid_native_proposal"):
                reasons.append("Native-tool capability not yet live-verified (maximum two funded capability requests).")
            providers[name] = {**TARGETS[name], "ready": not reasons, "blockers": reasons, "capability": capability}
        pilot_comparisons = {r["experiment_id"] for r in exported["requests"] if r["phase"] == "pilot" and r["role"] == "actor"}
        expansion_comparisons = {r["experiment_id"] for r in exported["requests"] if r["phase"] == "expansion" and r["role"] == "actor"}
        campaign = {"pilot_cases_fixed": len(exported["settings"].get("cases:pilot",[])), "pilot_comparisons_started":len(pilot_comparisons),
                    "expansion_comparisons_started":len(expansion_comparisons),"pilot_full":len(pilot_comparisons)>=4,
                    "note":"Fixed campaign limits remain after delivery. Completed captures may be reused. A new case outside the fixed manifest requires a separately authorized future campaign; do not delete/reset this ledger."}
        return {"profile": "proposal-execution-v1", "providers": providers, "accounting": exported, "campaign":campaign,
                "pilot_limits": {"cases": 2, "comparisons": 4, "http_attempts": 24, "meta_usd": 5, "baseten_usd": 2},
                "notice": "New live work uses this single milestone ledger; changing report directories does not reset it."}

    def freeze(self, case, *, phase="pilot", interpreter=None):
        errors = case.wording_errors()
        if errors:
            return {"status": "unsupported", "errors": errors, "new_model_requests": 0}
        key = freeze_key(case)
        path = self.cache / "freezes" / (key + ".json")
        if path.exists():
            return {"reused": True, "record": json.loads(path.read_text()), "new_model_requests": 0}
        case_hash = self.ledger.register_case(case, phase)
        marker = path.with_suffix(".started.json")
        if marker.exists():
            raise BudgetBlocked("Freeze started previously without a completed cache; outcome unknown, no automatic resend.")
        if interpreter is not None:
            # Injection seam only for offline tests. Never selected by a UI/live fallback.
            record = freeze_case(case, interpreter=interpreter)
        else:
            check_runtime_config(TargetConfig(provider="meta"))
            request = {"model": MODEL_NAME, "instructions": CUSTOMER_INSTRUCTIONS, "input": turn_payload(case.turns()), "max_output_tokens": 4096}
            call = self.ledger.call(request=request, phase=phase, provider="meta", role="customer", case_hash=case_hash,
                target_hash=INTERPRETATION_CONTRACT, repetition=0, experiment_id=key, ordinal=1, max_output=4096)
            write_new(marker, {"freeze_key": key, "request_ids": call.ids, "status": "started_unknown"})
            started = time.monotonic()
            results = []
            def customer(turns):
                result = interpret_customers(turns, call)
                results.append(result)
                return result
            try:
                record = freeze_case(case, interpreter=customer)
            finally:
                result = results[0] if results else None
                api = result.api_call if result else None
                call.finish(usage=api.usage if api else None, responses=api.http_responses if api else 0,
                    successes=api.successful_http_responses if api else 0, latency=round(time.monotonic() - started, 6),
                    error="Customer interpretation incomplete or invalid" if result is None or result.status != "valid" else None)
        write_new(path, record)
        return {"reused": False, "record": record, "new_model_requests": 0 if interpreter else len(call.ids)}

    def capture(self, case, config, *, phase="pilot", repetition=1, responder=None):
        wording = case.wording_errors()
        if wording:
            raise ValueError(" ".join(wording))
        path = self.cache / "freezes" / (freeze_key(case) + ".json")
        if not path.exists():
            raise ValueError("Freeze this exact supported case first; interpretation is shared across targets.")
        freeze = json.loads(path.read_text())
        frozen, customer = validate_freeze(case, freeze)
        case_hash = self.ledger.register_case(case, phase)
        self.ledger.register_target(config)
        identity = {"case_sha256": case_hash, "freeze_sha256": freeze["sha256"], "configuration_sha256": config.sha256,
                    "phase": phase, "repetition": repetition}
        experiment_id = digest(identity)
        capture_path = self.cache / "captures" / (experiment_id + ".json")
        if capture_path.exists():
            capture = json.loads(capture_path.read_text())
            reused = True
        else:
            if not responder:
                check_runtime_config(config)
                with self.ledger.transaction() as db:
                    self.ledger.require_funding(db, config.provider)
                    if config.provider == "baseten" and not (self.ledger.setting(db, "capability:baseten") or {}).get("valid_native_proposal"):
                        raise BudgetBlocked("Baseten native-tool capability is not live-verified; no actor dispatch.")
            marker = capture_path.with_suffix(".started.json")
            if marker.exists():
                raise BudgetBlocked("Capture started previously without completed evidence; no automatic paid resend.")
            write_new(marker, {"experiment_id": experiment_id, "status": "started_unknown"})
            with tempfile.TemporaryDirectory(prefix="intent-replay-capture-") as directory:
                store, _ = create_environment(Path(directory) / "capture.sqlite3", case, customer)
                def read_only(name, args):
                    if name != "get_booking" or args != {"reference": case.initial_booking.reference}:
                        return {"ok": False, "error": "Read arguments do not identify this local booking."}
                    evidence = store.read_evidence()
                    return {"ok": True, "booking": evidence["booking"], "accepted_instructions": evidence["accepted_instructions"],
                            "read_source": evidence["read_source"], "read_after_sequence": evidence["read_after_sequence"]}
                session = NativeCapture(config, read_only, ledger=self.ledger, responder=responder, metadata={"provider": config.provider,
                    "role": "actor", "phase": phase, "case_hash": case_hash, "target_hash": config.sha256, "repetition": repetition, "experiment_id": experiment_id})
                capture = session.run(case.turns()[:2])
            write_new(capture_path, capture)
            reused = False
        if capture["status"] != "proposal_captured":
            return seal({"version":"proposal-attempt-v1", "profile":"proposal-execution-v1", "status":capture["status"],
                "experiment_id":experiment_id,"case_sha256":case_hash,"phase":phase,"repetition":repetition,
                "case":case.model_dump(),"freeze":freeze,"capture":capture,"reused":reused,"prepared":None,
                "scope":"Native proposal capture attempt. No paired worker execution occurred. Factual accuracy was not assessed.",
                "factual_accuracy":"INCONCLUSIVE","worker_executions":0})
        artifact = prepare(case, freeze, capture, phase=phase, repetition=repetition)
        artifact = self.with_accounting(artifact)
        prepared_path = self.cache / "prepared" / (experiment_id + ".json")
        if not prepared_path.exists():
            write_new(prepared_path, artifact)
        else:
            artifact = json.loads(prepared_path.read_text())
            validate_prepared(artifact)
            if "inference_accounting" not in artifact:
                original = artifact["sha256"]
                artifact = self.with_accounting(artifact)
                artifact = seal({**artifact, "provenance": {**artifact["provenance"], "accounting_snapshot_added_to": original,
                    "derivation": "Added original ledger accounting only; native response, frozen customer evidence and proposal unchanged. Zero inference."}})
                derivative = prepared_path.with_name(experiment_id + "-accounted.json")
                if derivative.exists():
                    artifact = json.loads(derivative.read_text())
                    validate_prepared(artifact)
                else:
                    write_new(derivative, artifact)
        return {"status": "prepared", "capture": capture, "prepared": artifact, "reused": reused}

    def with_accounting(self, artifact):
        ledger = self.ledger.export()
        actor_ids = {i for r in artifact["capture"]["requests"] for i in r["ledger_request_ids"]}
        key = freeze_key(CaseSpec.model_validate(artifact["case"]))
        rows = [r for r in ledger["requests"] if r["id"] in actor_ids or (r["role"] in getattr(self, "interpretation_roles", ("customer",)) and r["experiment_id"] == key)]
        totals = {}
        for row in rows:
            label = row["provider"] + "/" + row["role"]
            total = totals.setdefault(label, {"unique_requests": 0, "http_attempts": 0, "http_responses": 0, "input_tokens": 0,
                                               "output_tokens": 0, "latency_seconds": 0, "usage_missing": 0, "estimated_usd": "0"})
            total["unique_requests"] += 1
            total["http_attempts"] += row["dispatched"]
            total["http_responses"] += row["responses"]
            total["latency_seconds"] = round(total["latency_seconds"] + (row["latency"] or 0), 6)
            total["estimated_usd"] = str(Decimal(total["estimated_usd"]) + Decimal(row["cost"]))
            if row["usage"]:
                for name in ("input_tokens", "output_tokens"): total[name] += row["usage"][name]
            else:
                total["usage_missing"] += 1
        snapshot = {"schema_version": "inference-accounting-snapshot-v1", "requests": rows, "totals_by_provider_role": totals,
            "rates": {p: {k: v for k, v in ledger["settings"].get("funding:"+p, {}).items() if k in ("input_per_million", "output_per_million", "rate_source", "checked_at")}
                      for p in {r["provider"] for r in rows}},
            "note": "Original inference references, not new charges. Sum campaign costs by unique ledger request ID, never by adding report snapshots. Missing usage retains its reservation. Estimates, not billing receipts.",
            "new_model_requests_during_replay": 0}
        return seal({**artifact, "inference_accounting": snapshot})

    def replay(self, artifact, *, location="local"):
        if location != "local":
            raise ValueError("Use the explicitly gated Modal controller for cloud execution.")
        report = execute_prepared(artifact)
        duplicate = self.ledger.record_compute(report)
        write_new(self.output / (report["execution_id"] + ".json"), report)
        return {"report": report, "repeated_experiment": duplicate, "new_model_requests": 0}

    def report(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid execution report identifier.")
        report = json.loads((self.output / (identifier + ".json")).read_text())
        if report.get("schema_version") != 7:
            raise ValueError("Unsupported benchmark report version.")
        from intent_replay.benchmark_cases import check_seal
        check_seal(report)
        return report

    def capability(self, *, responder=None):
        config = TargetConfig(provider="baseten")
        self.ledger.register_target(config)
        existing = self.ledger.export()["settings"].get("capability:baseten")
        if existing:
            return existing
        # This single forced native call is explicitly a capability request, not a benchmark trial.
        from intent_replay.booking import Turn
        turns = [Turn("context", "assistant", "Booking CAP-700: Lens cleaning, on 2026-11-24 at 10:00 (Europe/London)."),
                 Turn("customer-1", "customer", "Please move booking CAP-700 to 11:00 on 2026-11-24, Europe/London.")]
        session = NativeCapture(config, lambda *args: {"ok": False}, ledger=self.ledger, responder=responder,
            metadata={"provider": "baseten", "role": "capability", "phase": "pilot", "case_hash": digest([t.text for t in turns]),
                      "target_hash": config.sha256, "repetition": 0, "experiment_id": "baseten-native-capability-v1"})
        capture = session.run(turns, capability=True)
        result = {"valid_native_proposal": capture["status"] == "proposal_captured" and not responder,
                  "status": capture["status"], "capture": capture, "note": "Capability evidence is separate from pilot comparisons; no automatic repair attempt."}
        # A funding preflight block can be revisited after evidence is supplied, without spending a request.
        if any(r["ledger_request_ids"] for r in capture["requests"]):
            self.ledger.fix("capability:baseten", result)
        return result

    def authorize_expansion_preparation(self, manifest, pilot_reports, *, integrity):
        """Fix all six cases before additional freezes; actor dispatch remains gated."""
        if len(manifest) != 6 or len({digest(c.model_dump()) for c in manifest}) != 6:
            raise ValueError("Expansion requires six fixed distinct cases.")
        ledger = self.ledger.export()
        cases = [{"case_id": c.case_id, "timing": c.timing, "sha256": digest(c.model_dump())} for c in manifest]
        existing = ledger["settings"].get("expansion_preparation")
        if existing:
            if cases != ledger["settings"].get("cases:expansion"):
                raise BudgetBlocked("Expansion manifest is already fixed and cannot change on restart.")
            return existing
        rows = {r["id"]: r for r in ledger["requests"]}
        demonstrated = set()
        for report in pilot_reports:
            validate_prepared(report["prepared"])
            if report["prepared"]["phase"] != "pilot":
                raise ValueError("Gate evidence must come from the actual pilot.")
            if report["prepared"]["capture"]["source"].startswith("live_"):
                provider = report["prepared"]["capture"]["target"]["provider"]
                ids = [i for request in report["prepared"]["capture"]["requests"] for i in request["ledger_request_ids"]]
                if ids and all(i in rows and rows[i]["provider"] == provider and rows[i]["role"] == "actor" and rows[i]["phase"] == "pilot"
                    and rows[i]["experiment_id"] == report["experiment_id"] and rows[i]["responses"] == 1 for i in ids):
                    demonstrated.add(provider)
        capable = (self.ledger.export()["settings"].get("capability:baseten") or {}).get("valid_native_proposal")
        pilot_cases = ledger["settings"].get("cases:pilot") or []
        attempted = {(r["provider"],r["case_hash"]) for r in rows.values() if r["phase"] == "pilot" and r["role"] == "actor" and r["dispatched"]}
        expected = {(p,c["sha256"]) for p in ("meta","baseten") for c in pilot_cases}
        required_integrity = {"known_valid_controls", "native_attribution", "fresh_public_interface", "counter_export_cost_scope", "offline_regressions", "desktop_mobile_export", "worker_allowlist"}
        if demonstrated != {"meta", "baseten"} or not capable or len(pilot_cases) != 2 or attempted != expected or set(integrity) != required_integrity or not all(v is True for v in integrity.values()):
            raise BudgetBlocked("Expansion blocked: both live adapters and all recorded harness integrity checks are required.")
        self.ledger.fix("cases:expansion", cases)
        gate = {"eligible": True, "integrity": integrity, "pilot_execution_ids": [r["execution_id"] for r in pilot_reports], "demonstrated": sorted(demonstrated), "checked_at": now()}
        self.ledger.fix("expansion_preparation", gate)
        return gate

    def expansion_gate(self, manifest):
        settings = self.ledger.export()["settings"]
        if not (settings.get("expansion_preparation") or {}).get("eligible"):
            raise BudgetBlocked("Pilot integrity/capability evidence has not authorized expansion preparation.")
        if settings.get("expansion_gate"):
            return settings["expansion_gate"]
        records = settings.get("cases:expansion") or []
        if records != [{"case_id": c.case_id, "timing": c.timing, "sha256": digest(c.model_dump())} for c in manifest]:
            raise BudgetBlocked("Expansion cases differ from the fixed six-case manifest.")
        freezes = []
        for case in manifest:
            path = self.cache / "freezes" / (freeze_key(case) + ".json")
            record = json.loads(path.read_text())
            validate_freeze(case, record)
            freezes.append(record["sha256"])
        gate = {"eligible": True, "freeze_sha256": freezes, "checked_at": now()}
        self.ledger.fix("expansion_gate", gate)
        return gate
