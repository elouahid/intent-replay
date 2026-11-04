"""A separately authorized fixed pair using the existing controller and ledger.

No model answer is repaired and no packaged capture substitutes for a live stage.
Completed stage caches remain usable after inference is closed.
"""
import json
import time
from decimal import Decimal
from pathlib import Path

from intent_replay.benchmark_budget import BudgetBlocked
from intent_replay.benchmark_cases import CaseSpec, INTERPRETATION_CONTRACT, digest, freeze_case, freeze_key, seal
from intent_replay.benchmark_service import BenchmarkController, write_new
from intent_replay.benchmark_targets import TARGETS, TargetConfig, check_runtime_config
from intent_replay.meta_client import MODEL_NAME
from intent_replay.temporal_interpreter import CUSTOMER_INSTRUCTIONS, interpret_customers, turn_payload


class FreshWorkflowController(BenchmarkController):
    interpretation_roles = ("customer", "diagnostic")

    def __init__(self, *, ledger, cases, output=None):
        super().__init__(output=output, ledger=ledger)
        self.cases = [CaseSpec.model_validate(c) for c in cases]
        if [digest(c.model_dump()) for c in self.cases] != ledger.manifest["case_hashes"]:
            raise BudgetBlocked("Editor cases differ from the bound campaign manifest")
        for case in self.cases:
            self.ledger.register_case(case)

    def configuration(self):
        return self.ledger.export()["settings"].get("development_configuration")

    def _interpret(self, case, *, role, ordinal, settings, attempt_label=None):
        check_runtime_config(TargetConfig(provider="meta"))
        request = {"model": MODEL_NAME, "instructions": CUSTOMER_INSTRUCTIONS,
                   "input": turn_payload(case.turns()), "max_output_tokens": settings["max_output_tokens"]}
        if settings["reasoning_effort"] is not None:
            request["reasoning"] = {"effort": settings["reasoning_effort"]}
        metadata = dict(phase="pilot", provider="meta", role=role,
                        case_hash=digest(case.model_dump()), target_hash=INTERPRETATION_CONTRACT,
                        repetition=0, experiment_id=freeze_key(case), ordinal=ordinal,
                        max_output=settings["max_output_tokens"])
        if attempt_label:
            metadata["attempt_label"] = attempt_label
        call = self.ledger.call(request=request, **metadata)
        started = time.monotonic()
        results = []
        def customer(turns):
            result = interpret_customers(turns, call, **settings)
            results.append(result)
            return result
        try:
            record = freeze_case(case, interpreter=customer)
        finally:
            result = results[0] if results else None
            call.finish(latency=round(time.monotonic() - started, 6),
                        error=None if result and result.status == "valid" else "Interpretation incomplete or invalid")
        return seal({**record, "development": {"request_ids": call.ids, "request_settings": settings,
                     "attempt_label": attempt_label, "campaign_id": self.ledger.manifest["campaign_id"]}})

    def diagnostics(self, case):
        """A once; B only when A's native result reports output-cap truncation."""
        if case.timing != "precommit_withdrawal":
            raise ValueError("The diagnostic must use the fixed withdrawal case")
        self.ledger.register_case(case)
        settings = {"max_output_tokens": 16384, "reasoning_effort": None, "timeout_seconds": 300.0}
        records = []
        directory = self.ledger.root / "diagnostics"
        for ordinal, label in enumerate(("diagnostic-A", "diagnostic-B"), 1):
            path = directory / (label + ".json")
            marker = path.with_suffix(".started.json")
            if path.exists():
                record = json.loads(path.read_text())
            else:
                if marker.exists():
                    raise BudgetBlocked("Diagnostic started without a saved result; no automatic resend")
                write_new(marker, {"label": label, "case_sha256": digest(case.model_dump()), "settings": settings})
                record = self._interpret(case, role="diagnostic", ordinal=ordinal, settings=settings, attempt_label=label)
                write_new(path, record)
            records.append(record)
            request_id = record["development"]["request_ids"][0]
            attempt = json.loads((self.ledger.root / "attempts" / (request_id + ".json")).read_text())
            raw = attempt.get("public_response") or {}
            truncated = raw.get("status") == "incomplete" and (raw.get("incomplete_details") or {}).get("reason") == "max_output_tokens"
            if not truncated or ordinal == 2 or self.ledger.blockers("meta"):
                break
            settings = {**settings, "reasoning_effort": "low"}
        self.ledger.fix("development_configuration", {"interpretation": settings, "actor_max_output_tokens": 2048,
            "selection": "A settings retained unless its native output cap truncates, then the separately recorded B low effort setting is fixed.",
            "diagnostics": [r["development"]["attempt_label"] for r in records]})
        path = self.cache / "freezes" / (freeze_key(case) + ".json")
        if not path.exists():
            write_new(path, records[-1])
        elif json.loads(path.read_text()) != records[-1]:
            raise BudgetBlocked("Existing interpretation differs; no replacement")
        return records

    def freeze(self, case, *, phase="pilot", interpreter=None):
        if case.wording_errors():
            return {"status": "unsupported", "errors": case.wording_errors(), "new_model_requests": 0}
        self.ledger.register_case(case, phase)
        path = self.cache / "freezes" / (freeze_key(case) + ".json")
        if path.exists():
            return {"reused": True, "record": json.loads(path.read_text()), "new_model_requests": 0}
        config = self.configuration()
        if config is None:
            raise BudgetBlocked("The explicit diagnostic must finish and fix the batch configuration first")
        if interpreter is not None:
            raise BudgetBlocked("This fresh workflow does not accept an authored interpretation fallback")
        marker = path.with_suffix(".started.json")
        if marker.exists():
            raise BudgetBlocked("Interpretation already started; no automatic resend")
        write_new(marker, {"freeze_key": freeze_key(case), "status": "started_unknown"})
        record = self._interpret(case, role="customer", ordinal=1, settings=config["interpretation"])
        write_new(path, record)
        return {"reused": False, "record": record, "new_model_requests": len(record["development"]["request_ids"])}

    def capture(self, case, config, **kwargs):
        if kwargs.get("responder") is not None:
            raise BudgetBlocked("No synthetic responder is available in this fresh workflow")
        self.ledger.register_case(case, kwargs.get("phase", "pilot"))
        return super().capture(case, config, **kwargs)

    def workflow(self):
        exported = self.ledger.export()
        rows = exported["requests"]
        cases = []
        for case in self.cases:
            key = freeze_key(case)
            path = self.cache / "freezes" / (key + ".json")
            frozen = json.loads(path.read_text()) if path.exists() else None
            related = [r for r in rows if r["experiment_id"] == key]
            attempts = [json.loads(p.read_text()) for r in related
                        if (p := self.ledger.root / "attempts" / (r["id"] + ".json")).exists()]
            last = attempts[-1] if attempts else {}
            raw = last.get("public_response") or {}
            interpretation = {"status": frozen["status"] if frozen else ("started_unknown" if related or path.with_suffix(".started.json").exists() else "not_started"),
                "errors": frozen.get("errors", []) if frozen else [], "model": raw.get("model", MODEL_NAME),
                "native_status": raw.get("status"), "request_settings": (frozen or {}).get("development", {}).get("request_settings"),
                "usage": last.get("usage"), "reused": bool(frozen), "record": frozen,
                "request_ids": [r["id"] for r in related]}
            providers = {}
            for provider in TARGETS:
                actors = [r for r in rows if r["role"] == "actor" and r["provider"] == provider and r["case_hash"] == digest(case.model_dump())]
                capture = None
                experiment = digest({"case_sha256": digest(case.model_dump()), "freeze_sha256": frozen["sha256"],
                    "configuration_sha256": TargetConfig(provider=provider).sha256, "phase": "pilot", "repetition": 1}) if frozen else "absent"
                capture_path = self.cache / "captures" / (experiment + ".json")
                if capture_path.exists(): capture = json.loads(capture_path.read_text())
                prepared_path = self.cache / "prepared" / (experiment + ".json")
                providers[provider] = {"status": "prepared" if capture and capture["status"] == "proposal_captured" else
                    (capture["status"] if capture else ("started_unknown" if actors or capture_path.with_suffix(".started.json").exists() else "not_started")),
                    "errors": (capture or {}).get("errors", []), "model": TARGETS[provider]["model"],
                    "usage": [r["usage"] for r in actors], "request_ids": [r["id"] for r in actors],
                    "http_attempts": sum(r["dispatched"] for r in actors), "capture": capture,
                    "prepared": json.loads(prepared_path.read_text()) if prepared_path.exists() else None,
                    "blockers": self.ledger.blockers(provider) + (["Requires this case's valid interpretation"] if not frozen or frozen["status"] != "valid" else [])}
            cases.append({"case": case.model_dump(), "case_sha256": digest(case.model_dump()), "interpretation": interpretation, "providers": providers})
        return {"enabled": True, "campaign": {"id": self.ledger.manifest["campaign_id"],
            "closed": bool(exported["settings"].get("inference_closed")), "deadline_utc": self.ledger.manifest["deadline_utc"],
            "limits": self.ledger.manifest["limits"], "totals": {"http_attempts": sum(r["dispatched"] for r in rows),
                "estimated_usd": str(sum((Decimal(r["cost"]) for r in rows), Decimal(0)))}},
            "configuration": self.configuration(), "cases": cases}

    def readiness(self):
        providers = {}
        for name in TARGETS:
            blockers = self.ledger.blockers(name)
            try:
                check_runtime_config(TargetConfig(provider=name))
                with self.ledger.transaction() as db: self.ledger.require_funding(db, name)
            except (ValueError, RuntimeError) as exc:
                blockers.append(str(exc))
            providers[name] = {**TARGETS[name], "ready": not blockers, "blockers": blockers}
        workflow = self.workflow()
        return {"profile": "proposal-execution-v1", "providers": providers, "accounting": self.ledger.export(),
                "campaign": workflow["campaign"], "notice": "Separate fixed fictional development pair. Readiness is evaluated per stage and provider. Recorded demo remains available."}


class RecordedFreshController(BenchmarkController):
    """Portable read-only stage evidence plus new local SQLite replays, no keys."""
    def __init__(self, snapshot, **kwargs):
        super().__init__(**kwargs)
        self.snapshot = snapshot

    def workflow(self):
        return self.snapshot

    def readiness(self):
        return {"profile": "proposal-execution-v1", "providers": {p: {**t, "ready": False,
                "blockers": ["Recorded fresh-case evidence; inference campaign closed"]} for p, t in TARGETS.items()},
                "campaign": self.snapshot["campaign"], "accounting": self.ledger.export(),
                "notice": "Saved fresh-case stages. Local SQLite replay and downloads require no API key."}

    def _case(self, case):
        for item in self.snapshot["cases"]:
            if digest(case.model_dump()) == item["case_sha256"]:
                return item
        raise BudgetBlocked("No saved stage for these edited inputs. A new paid case needs a separate authorized campaign.")

    def freeze(self, case, **kwargs):
        record = self._case(case)["interpretation"]["record"]
        if record is None:
            raise BudgetBlocked("No recorded interpretation exists for this case")
        return {"record": record, "reused": True, "new_model_requests": 0}

    def capture(self, case, config, **kwargs):
        item = self._case(case)["providers"][config.provider]
        if not item["capture"]:
            raise BudgetBlocked("No recorded proposal attempt exists for this case/provider")
        if item["capture"]["configuration_sha256"] != config.sha256:
            raise BudgetBlocked("Configuration differs from the recorded capture")
        return {"status": item["status"], "capture": item["capture"], "prepared": item["prepared"], "reused": True}
