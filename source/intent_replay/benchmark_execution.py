"""Provider-independent execution of a validated, immutable proposal artifact.

This module never creates a model client. Both local and Modal workers call the
same entry point. Hashes prove consistency, not external provider authenticity.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import tempfile
import time
from uuid import uuid4

from intent_replay.benchmark_cases import CaseSpec, PROFILE, SCOPE, WORDING_CONTRACT, check_seal, digest, now, seal, validate_freeze
from intent_replay.benchmark_targets import TARGETS, TargetConfig, native_calls, parse_call, public_response
from intent_replay.booking import Booking
from intent_replay.temporal import Instruction, RevisionStore
from intent_replay.temporal_evaluator import evaluate_temporal

CONTRACT_FILES = ("benchmark_cases.py", "benchmark_targets.py", "benchmark_execution.py", "temporal.py", "temporal_evaluator.py",
                  "temporal_interpreter.py", "interpreter.py", "evaluator.py", "booking.py", "models.py")

# Exact source contract independently reviewed in this archive. This is a
# compatibility identity, NEVER a validation exemption or provider attestation.
REVIEWED_LEGACY_CONTRACT = "a66d3a0842b6d2d382b42c295bf5632c1a4b87ebfd867325ea3a3ad65fd76632"
REVIEWED_LEGACY_ARCHIVE = "5cf85cd6a1db554b3e6dabf2f627f18301d60fdff811d313af699675efc81113"
# The independently reviewed conditional-request repair and overnight captures
# used this exact source contract. They also undergo every current check below.
REVIEWED_REPAIRED_CONTRACT = "9f19de4ea14a2c062a99c3f89bcf79d1a33137c7fc0b0581996e75022026560d"


def execution_contract():
    root = Path(__file__).parent
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in CONTRACT_FILES})


def accepted(store, item, customer, *, enqueue=False):
    store.receive(item.turn_id)
    return store.accept(Instruction(item.turn_id, item.operation, item.booking_reference, item.requested_time, item.timezone,
                                    tuple(item.evidence_turn_ids), customer.interpretation_id), enqueue=enqueue)


def create_environment(path, case, customer):
    wording = case.wording_errors()
    if wording:
        raise ValueError(" ".join(wording))
    store = RevisionStore.create(path, Booking(**case.initial_booking.model_dump()), case.requested_time, case.slot_available)
    revision = accepted(store, customer.data.instructions[0], customer)
    return store, revision


def visible_input(case):
    # Only delivered context and first request. Never the private case object.
    return [{"role": "user" if t.role == "customer" else "assistant", "content": t.text} for t in case.turns()[:2]]


def validate_capture(case, capture):
    check_seal(capture)
    target = capture["target"]
    config = TargetConfig.model_validate({k: target[k] for k in ("provider", "instruction_version", "developer_instructions", "max_rounds", "max_output_tokens")})
    if target != config.public() or capture.get("configuration_sha256") != config.sha256:
        raise ValueError("Capture configuration hash or native adapter configuration differs.")
    if (capture.get("version") != "native-proposal-capture-v1" or capture.get("status") != "proposal_captured"
        or capture.get("originating_revision") != 1 or type(capture.get("originating_revision")) is not int
        or capture.get("visible_input") != visible_input(case) or capture.get("visible_input_sha256") != digest(visible_input(case))
        or capture.get("private_history_exported") is not False or capture.get("final_continuation_generated") is not False):
        raise ValueError("Capture does not bind exactly to the delivered request/revision or proposal-only profile.")
    responses, events = capture.get("responses"), capture.get("events")
    if not isinstance(responses, list) or not 1 <= len(responses) <= config.max_rounds or not isinstance(events, list) or len(events) != len(responses):
        raise ValueError("Native response/event evidence is incomplete.")
    ids, last = set(), None
    for index, (response, event) in enumerate(zip(responses, events)):
        if public_response(config.provider, response) != response:
            raise ValueError("Capture includes unsupported/private native response fields.")
        calls = native_calls(config.provider, response, TARGETS[config.provider]["model"])
        if len(calls) != 1 or calls[0]["call_id"] in ids or type(event.get("response_index")) is not int or event.get("response_index") != index or event.get("native_call") != calls[0]:
            raise ValueError("Normalized event differs from the original native response.")
        last = calls[0]
        ids.add(last["call_id"])
        args = parse_call(last)
        if event.get("arguments") != args:
            raise ValueError("Preserved native arguments differ from normalized arguments; no repair was attempted.")
        mutation = last["name"] == "reschedule_booking"
        if event.get("kind") != ("mutation_proposal" if mutation else "read_only_call") or mutation != (index == len(responses) - 1):
            raise ValueError("Capture must end at its only mutation proposal.")
    proposal = capture.get("proposal")
    if not isinstance(proposal, dict) or type(proposal.get("originating_revision")) is not int or proposal != {"native_call": last, "arguments": parse_call(last), "originating_revision": 1}:
        raise ValueError("Captured proposal, native arguments or originating revision disagree.")
    return config


def prepare(case, freeze, capture, *, phase="pilot", repetition=1, provenance=None):
    validate_freeze(case, freeze)
    validate_capture(case, capture)
    identity = {"case_sha256": digest(case.model_dump()), "freeze_sha256": freeze["sha256"],
                "configuration_sha256": capture["configuration_sha256"], "phase": phase, "repetition": repetition}
    return seal({"version": "prepared-execution-v1", "profile": PROFILE, "created_at": now(), **identity,
                 "experiment_id": digest(identity), "capture_sha256": capture["sha256"], "execution_contract_sha256": execution_contract(),
                 "case": case.model_dump(), "freeze": deepcopy(freeze), "capture": deepcopy(capture),
                 "provenance": provenance or {"capture_source": capture["source"], "interpretation_source": freeze["frozen"]["payload"]["customer_interpretation"]["source"]}})


def validate_prepared(artifact):
    if not isinstance(artifact, dict) or len(json.dumps(artifact).encode()) > 2_000_000:
        raise ValueError("Prepared artifact must be bounded JSON.")
    check_seal(artifact)
    if type(artifact.get("repetition")) is not int or artifact["repetition"] not in (1, 2, 3) or artifact.get("phase") not in ("pilot", "expansion", "offline_fixture", "recorded_replay"):
        raise ValueError("Unsupported experiment phase/repetition.")
    source_contract = artifact.get("execution_contract_sha256")
    if artifact.get("version") != "prepared-execution-v1" or artifact.get("profile") != PROFILE or source_contract not in (execution_contract(), REVIEWED_LEGACY_CONTRACT, REVIEWED_REPAIRED_CONTRACT):
        raise ValueError("Prepared execution version or source contract differs. No imported validation flag is trusted.")
    case = CaseSpec.model_validate(artifact["case"])
    frozen, customer = validate_freeze(case, artifact["freeze"])
    config = validate_capture(case, artifact["capture"])
    identity = {"case_sha256": digest(case.model_dump()), "freeze_sha256": artifact["freeze"]["sha256"],
                "configuration_sha256": config.sha256, "phase": artifact["phase"], "repetition": artifact["repetition"]}
    if any(artifact.get(k) != v for k, v in identity.items()) or artifact.get("experiment_id") != digest(identity) or artifact.get("capture_sha256") != artifact["capture"]["sha256"]:
        raise ValueError("Case/freeze/capture/configuration/experiment hashes do not agree.")
    return case, frozen, customer, config


def _branch(case, customer, proposal, implementation, path):
    store, revision = create_environment(path, case, customer)
    errors = []
    try:
        store.enqueue_proposal(revision, proposal["arguments"]["reference"], proposal["arguments"]["requested_time"], proposal["arguments"]["timezone"])
    except (ValueError, KeyError):
        errors.append("Genuine native proposal does not bind to its originating accepted instruction; no mutation was admitted.")
    if not errors:
        withdrawal = customer.data.instructions[1] if case.withdrawal else None
        hook = (lambda: accepted(store, withdrawal, customer)) if withdrawal else None
        store.execute(implementation, after_preliminary_read=hook)
    report = {"implementation": implementation, "injected_worker_defect": implementation == "faulty", "initial_booking": case.initial_booking.model_dump(),
              "conversation": [asdict(t) for t in case.turns()], "final_evidence": store.read_evidence(), "execution_errors": errors,
              "proposal_binding": "FAIL" if errors else "PASS", "status": "model_proposal_rejected" if errors else "executed",
              "assistant_interpretation": None}
    report.update(evaluate_temporal(customer, case.turns(), report, None))
    report["execution_result"] = report["evaluation"]["instruction_adherence"]
    report["factual_accuracy"] = {"status": "INCONCLUSIVE", "assessed": False, "reason": "No final assistant reply was generated."}
    expected = getattr(case.private_expectations, implementation)
    evidence = report["final_evidence"]
    observed = {"final_time": evidence["booking"]["starts_at"], "action_status": evidence["actions"][0]["status"] if len(evidence["actions"]) == 1 else None,
                "booking_outcome": report["evaluation"]["booking_outcome"], "instruction_adherence": report["execution_result"]}
    report["private_expectation_comparison"] = {"expected": expected.model_dump(), "observed": observed, "matches": expected.model_dump() == observed,
        "note": "Expected values compare observations; they do not dictate the evaluator verdict."}
    report["attribution"] = ("Proposal operands failed host binding; this is a model proposal result, not the injected worker defect." if errors else
        "The faulty worker is an injected control. The proposal predates the withdrawal; a stale commit is an execution defect, not evidence that the model ignored an undelivered instruction." if case.withdrawal else
        "Both workers execute the same captured proposal; these are correlated controlled outcomes.")
    return report


def execute_prepared(artifact, *, location="local", execution_id=None):
    """Whole pair, two new DBs, one temporary directory; zero model calls."""
    started = time.monotonic()
    case, frozen, customer, config = validate_prepared(artifact)
    with tempfile.TemporaryDirectory(prefix="intent-replay-pair-") as directory:
        reports = [_branch(case, customer, artifact["capture"]["proposal"], name, Path(directory) / (name + ".sqlite3")) for name in ("faulty", "corrected")]
    return seal({"schema_version": 7, "report_type": "proposal_execution_comparison", "profile": PROFILE, "scope": SCOPE,
        "execution_id": execution_id or uuid4().hex, "experiment_id": artifact["experiment_id"], "created_at": now(),
        "revalidation": {"policy": "known-contract-current-validation-v1", "wording_contract": WORDING_CONTRACT,
            "mode": ("reviewed_legacy_revalidated" if artifact["execution_contract_sha256"] == REVIEWED_LEGACY_CONTRACT else
                     "reviewed_repaired_revalidated" if artifact["execution_contract_sha256"] == REVIEWED_REPAIRED_CONTRACT else "current_contract"),
            "original_prepared_sha256": artifact["sha256"], "original_execution_contract_sha256": artifact["execution_contract_sha256"],
            "current_validation_execution_contract_sha256": execution_contract(),
            "reviewed_legacy_archive_sha256": REVIEWED_LEGACY_ARCHIVE if artifact["execution_contract_sha256"] == REVIEWED_LEGACY_CONTRACT else None,
            "note": "All candidates passed current wording, frozen evidence, native arguments, reference/revision, configuration and integrity checks. Original prepared evidence is unchanged; this is a new backend replay, not a new model trial."},
        "prepared": deepcopy(artifact), "reports": reports, "runtime": {"location": location, "python": platform.python_version(),
            "elapsed_seconds": round(time.monotonic() - started, 6), "fresh_temporary_directory": True, "separate_sqlite_files": True,
            "model_requests": 0, "model_credentials_required": False, "execution_contract_sha256": execution_contract()},
        "accounting": {"new_model_requests": 0, "capture_request_ids": [i for r in artifact["capture"]["requests"] for i in r["ledger_request_ids"]],
            "shared_customer_interpretation_reused": True, "original_capture_reused": True,
            "note": "Original inference is counted once by unique ledger request IDs. Compute replay adds zero model usage."},
        "limits": ["Factual accuracy not assessed; overall task retains INCONCLUSIVE or FAIL under existing definitions.",
                   "Paired workers are correlated; the faulty control is deliberately injected.",
                   "Hashes establish consistency, not provider authenticity. SQLite/journals are trusted application evidence.",
                   "The transaction guarantee applies to this backend, not arbitrary external service APIs."]})
