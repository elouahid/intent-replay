"""Capture one actual actor proposal, then replay it into two isolated SQLite workers."""

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from intent_replay.agent_adapter import AgentSession
from intent_replay.agent_claims import AgentSemanticResult, CONTRACT_VERSION, apply_agent_claim_evaluation, extract_agent_claims, seal_observation
from intent_replay.language_claims import LanguageResult, extract_language_claims, apply_language_evaluation, CONTRACT_VERSION as LANGUAGE_VERSION
from intent_replay.booking import Booking, Turn
from intent_replay.evaluator import same_time
from intent_replay.meta_client import AttemptBudget, PROJECT_ROOT
from intent_replay.models import AssistantInterpretation, CustomerInterpretation, SemanticResult
from intent_replay.temporal import Instruction, RevisionStore
from intent_replay.temporal_evaluator import evaluate_temporal
from intent_replay.temporal_interpreter import input_digest, validate_claims, validate_customers
from intent_replay.temporal_service import FrozenReplay


def load_agent_report(run_id: str, root: Path) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Invalid agent comparison identifier.")
    report = json.loads((root / (run_id + ".json")).read_text(encoding="utf-8"))
    if (not isinstance(report, dict) or report.get("schema_version") not in (4, 5, 6) or report.get("report_type") != "agent_comparison"
            or report.get("run_id") != run_id or report.get("pair_id") != run_id or not isinstance(report.get("created_at"), str)):
        raise ValueError("This is not the requested version-4, version-5 or version-6 agent comparison.")
    return report


def saved_agent_reports(root: Path) -> list[dict]:
    results = []
    for path in root.glob("*.json"):
        try:
            report = load_agent_report(path.stem, root)
            results.append({"run_id": report["run_id"], "created_at": report["created_at"], "freeze_id": report["freeze_id"],
                            "plan": report["frozen_inputs"]["payload"]["schedule_plan"]})
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return sorted(results, key=lambda item: item["created_at"], reverse=True)[:100]


def _instruction(item, customer):
    return Instruction(item.turn_id, item.operation, item.booking_reference, item.requested_time,
                       item.timezone, tuple(item.evidence_turn_ids), customer.interpretation_id)


def _tool_state(snapshot):
    action = snapshot["actions"][0] if snapshot["actions"] else None
    journal = snapshot["journal"]
    accepted = [event for event in journal if event["event"] == "instruction_accepted"]
    facts = []
    for event in accepted:
        received = next((item for item in journal if item["event"] == "instruction_received" and item["data"].get("turn_id") == event["data"]["turn_id"]), None)
        facts.append({"revision": event["data"]["revision"], "operation": event["data"]["operation"],
                      "received_sequence": received["sequence"] if received else None, "accepted_sequence": event["sequence"]})
    decisions = [{"sequence": event["sequence"], "event": event["event"], "accepted_revision": event["data"].get("accepted_revision")}
                 for event in journal if event["event"] in ("action_committed", "action_suppressed", "action_rejected")]
    guards = [{"sequence": event["sequence"], "accepted_revision": event["data"].get("accepted_revision"),
               "checked_revision": event["data"].get("checked_revision")} for event in journal if event["event"] == "authorization_checked"]
    return {"ok": True, "booking": snapshot["booking"],
            "action": {key: action[key] for key in ("operation", "target_time", "accepted_revision", "status", "checked_revision")} if action else None,
            "read_source": snapshot["read_source"], "persisted_event_facts": {"version": "booking-tool-evidence-v2",
                "ordering_basis": "Increasing sequence is persisted backend order, independent of conversational delivery order.",
                "instructions": facts, "authorization_checks": guards, "decisions": decisions,
                "read_after_sequence": snapshot["read_after_sequence"]}}


def _claim_supplement(report, assistant, conversation):
    """Evaluate visible pre-action claims without inventing execution anchors."""
    if not (assistant and assistant.status == "valid" and isinstance(assistant.data, AssistantInterpretation)
            and assistant.purpose == "assistant_claims" and assistant.input_sha256 == input_digest(conversation)
            and not validate_claims(assistant.data, conversation)):
        return
    failures = []
    for observation in report["statement_observations"]:
        if observation["describes_sequence"] is not None:
            continue
        claim = next((item for item in assistant.data.claims if item.turn_id == observation["turn_id"]), None)
        booking = observation["snapshot"]["booking"]
        if not claim or not booking:
            continue
        stated = claim.claimed_booking
        mismatch = stated and (stated.reference != booking["reference"] or not same_time(stated.starts_at, booking["starts_at"]) or stated.timezone != booking["timezone"])
        if mismatch or claim.operation == "rescheduled":
            failures.append({"turn_id": claim.turn_id, "status": "FAIL", "detail": "The visible booking statement contradicts its independent SQLite snapshot." if mismatch else "The actor claimed a completed reschedule before any action was executed in this isolated run."})
    report["agent_statement_checks"] = failures
    if failures:
        report["evaluation"]["confirmation_integrity"] = "FAIL"
        report["evaluation"]["task_verdict"] = "FAIL"
        detail = " ".join(item["detail"] for item in failures)
        report["evaluation"]["explanation"] += " Actor statement evidence: " + detail
        report["evaluation"]["checks"].append({"name": "Actor statement before action", "status": "FAIL", "detail": detail})


def _accounting(capture, reports, customer):
    def total(calls):
        result = {key: sum(item.get(key, 0) for item in calls) for key in ("http_attempts", "http_responses", "successful_http_responses")}
        usages = [item.get("usage") for item in calls if item.get("usage")]
        result["returned_usage"] = usages
        result["usage_missing_calls"] = len(calls) - len(usages)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            values = [item[key] for item in usages if type(item.get(key)) is int]
            result[key] = sum(values) if values else None
        return result
    capture_calls = deepcopy(capture["api_calls"])
    for item, response in zip(capture_calls, capture["responses"]):
        item["usage"] = response.get("usage")
    continuation_calls = []
    for report in reports:
        calls = deepcopy(report["agent_execution"]["api_calls"])
        for item, response in zip(calls, report["agent_execution"]["responses"]):
            item["usage"] = response.get("usage")
        continuation_calls.extend(calls)
    interpretations = [report["assistant_interpretation"] for report in reports if report["assistant_interpretation"]]
    claim_calls = [item["api_call"] for item in interpretations]
    semantic_calls = [item["semantic_check"]["api_call"] for item in interpretations if item.get("semantic_check", {}).get("api_call")]
    return {"actor_capture": total(capture_calls), "actor_continuations": total(continuation_calls),
            "assistant_interpretation": {**total(claim_calls), "valid_interpretations": sum(item["status"] == "valid" for item in interpretations)},
            "assistant_semantic_check": total(semantic_calls),
            "new_calls": total(capture_calls + continuation_calls + claim_calls + semantic_calls),
            "original_customer_freeze": customer.api_call.model_dump(), "customer_interpretations_during_pair": 0,
            "note": "Original customer-freeze accounting is historical provenance, not new requests during this pair."}


def run_agent_pair(frozen: FrozenReplay, *, storage_root: Path | None = None, agent_responder=None,
                   assistant_interpreter=None, budget: AttemptBudget | None = None, max_rounds=4, max_tool_calls=8) -> dict:
    root = storage_root or PROJECT_ROOT / ".local" / "agent"
    root.mkdir(parents=True, exist_ok=True)
    inputs = frozen.data
    initial = Booking(**inputs["initial_booking"])
    customer = SemanticResult.model_validate(inputs["customer_interpretation"])
    customer_turns = [Turn(**turn) for turn in inputs["customer_turns"]]
    budget = budget or AttemptBudget(max_rounds * 3 + 4)
    pair_id = uuid4().hex
    errors = list(inputs["validation_errors"])
    plan = inputs["schedule_plan"]
    if plan not in ("no_withdrawal", "withdraw_before_execution", "withdraw_after_preliminary_read"):
        errors.append("Agent comparison supports a withdrawal at the pre-commit barrier or the no-withdrawal control.")
    if (customer.status != "valid" or not isinstance(customer.data, CustomerInterpretation)
            or customer.purpose != "customer_intents" or customer.input_sha256 != input_digest(customer_turns)):
        errors.append("Frozen customer interpretation is invalid or does not belong to these messages.")
    else:
        errors.extend(validate_customers(customer.data, customer_turns))
        items = customer.data.instructions
        if len(items) != (1 if plan == "no_withdrawal" else 2):
            errors.append("Frozen scheduling plan does not match its instructions.")
        first = items[0]
        if first.booking_reference != initial.reference or first.timezone != initial.timezone or not same_time(first.requested_time, inputs["target_time"]):
            errors.append("Frozen instruction does not match the local booking inputs.")
        if len(items) == 2 and not same_time(items[1].requested_time, initial.starts_at):
            errors.append("Frozen withdrawal does not retain the original booking.")

    capture_store = RevisionStore.create(root / (pair_id + "-capture.sqlite3"), initial, inputs["target_time"], inputs["slot_available"])
    initial_turns = [customer_turns[0]]
    if not errors:
        first_turn = next(turn for turn in customer_turns if turn.id == customer.data.instructions[0].turn_id)
        initial_turns.append(first_turn)
        capture_store.receive(first_turn.id)
        capture_store.accept(_instruction(customer.data.instructions[0], customer), enqueue=False)
    capture_observations, capture_conversation = [], list(initial_turns)

    def capture_message(text):
        turn = Turn("actor-prefix-" + str(len(capture_observations) + 1), "assistant", text)
        capture_observations.append(seal_observation({"turn_id": turn.id, "text": text, "describes_sequence": None,
                                     "snapshot": capture_store.read_evidence(), "source": "independent SQLite read after captured visible actor output"}, len(capture_observations) + 1))
        capture_conversation.append(turn)

    def capture_dispatch(name, args):
        if name != "get_booking" or args["reference"] != initial.reference:
            raise ValueError("Only this booking can be read during proposal capture.")
        return _tool_state(capture_store.read_evidence())

    capture = AgentSession(capture_dispatch, responder=agent_responder, budget=budget, max_rounds=max_rounds,
                           max_tool_calls=max_tool_calls, on_message=capture_message)
    captured = capture.generate(initial_turns, capture=True) if not errors else None
    proposal = None
    if captured and captured["kind"] == "proposal":
        prefix = capture.report["requests"][-1]["input"]
        proposal = {**deepcopy(captured["call"]), "raw_arguments": captured["call"]["arguments"],
                    "parsed_arguments": captured["arguments"], "originating_revision": 1,
                    "actor_visible_prefix": prefix, "actor_input_sha256": capture.report["requests"][-1]["input_sha256"],
                    "public_input_sha256": capture.report["requests"][-1]["public_input_sha256"],
                    "captured_response_history": capture.public_history(),
                    "model": capture.report["responses"][-1].get("model"), "response_id": capture.report["responses"][-1].get("id"),
                    "source": capture.report["source"], "prompt_tool_sha256": capture.report["prompt_tool_sha256"]}
    reports = []
    for implementation in ("faulty", "corrected"):
        run_id = uuid4().hex
        store = RevisionStore.create(root / (run_id + ".sqlite3"), initial, inputs["target_time"], inputs["slot_available"])
        conversation = list(initial_turns)
        observations, branch_errors = [], list(errors)
        if not errors:
            store.receive(first_turn.id)
            store.accept(_instruction(customer.data.instructions[0], customer), enqueue=False)
        for turn in capture_conversation[len(initial_turns):]:
            conversation.append(turn)
            observations.append(seal_observation({"turn_id": turn.id, "text": turn.text, "describes_sequence": None,
                                 "snapshot": store.read_evidence(), "source": "captured actor message replayed before execution"}, len(observations) + 1))

        def branch_message(text):
            turn = Turn("actor-continuation-" + str(len(observations) + 1), "assistant", text)
            snapshot = store.read_evidence()
            anchor = next((event for event in reversed(snapshot["journal"]) if event["event"] in ("action_committed", "action_suppressed", "action_rejected")), None)
            if anchor:
                store.record_statement(turn.id, turn.text, anchor["sequence"], snapshot)
            observations.append(seal_observation({"turn_id": turn.id, "text": text, "describes_sequence": anchor["sequence"] if anchor else None,
                                 "snapshot": snapshot, "source": "independent SQLite read after actual actor output"}, len(observations) + 1))
            conversation.append(turn)

        def branch_dispatch(name, args):
            if name == "reschedule_booking":
                return {"ok": False, "error": "A mutation proposal was already dispatched for this run; duplicate mutations are rejected."}
            if args["reference"] != initial.reference:
                raise ValueError("Wrong booking.")
            return _tool_state(store.read_evidence())

        continuation = AgentSession(branch_dispatch, responder=agent_responder, budget=budget, max_rounds=max_rounds,
                                    max_tool_calls=max_tool_calls, on_message=branch_message)
        delivery = []
        if proposal and not errors:
            continuation.history = deepcopy(capture.history)
            continuation.calls_seen = set(capture.calls_seen)
            args = proposal["parsed_arguments"]
            try:
                store.enqueue_proposal(proposal["originating_revision"], args["reference"], args["requested_time"], args["timezone"])

                def withdrawal():
                    item = customer.data.instructions[1]
                    turn = next(turn for turn in customer_turns if turn.id == item.turn_id)
                    store.receive(turn.id)
                    store.accept(_instruction(item, customer), enqueue=False)
                    conversation.append(turn)
                    delivery.append(turn)

                snapshot = store.execute(implementation, after_preliminary_read=withdrawal if plan != "no_withdrawal" else None)
                result = _tool_state(snapshot)
            except ValueError:
                result = {"ok": False, "error": "The proposed arguments do not match the accepted originating instruction; no action was admitted."}
            except Exception:
                result = {"ok": False, "error": "Local execution failed; only persisted evidence establishes the outcome."}
                branch_errors.append("Local proposal execution failed; committed evidence was retained.")
            continuation.add_result(captured["call"], result)
            continuation.generate(delivery)
        assistant = None
        if observations:
            try:
                assistant = assistant_interpreter(conversation) if assistant_interpreter else extract_language_claims(conversation, budget)
            except Exception:
                branch_errors.append("Assistant interpretation failed; diagnostic details were withheld.")
        branch_errors.extend(capture.report["errors"])
        branch_errors.extend(continuation.report["errors"])
        # The explicitly supplied authored legacy contract is retained solely as
        # the established synthetic regression seam; production/default is v5.
        legacy_authored = isinstance(assistant, SemanticResult) and assistant.source == "authored_test"
        language = isinstance(assistant, LanguageResult) or (assistant is None and assistant_interpreter is None)
        report = {"schema_version": 4 if legacy_authored else 6 if language else 5, "report_type": "agent_branch", "run_id": run_id, "pair_id": pair_id,
                  "freeze_id": frozen.sha256, "created_at": datetime.now(timezone.utc).isoformat(),
                  "implementation": implementation, "controlled_demonstration": implementation == "faulty",
                  "initial_booking": inputs["initial_booking"], "conversation": [asdict(turn) for turn in conversation],
                  "final_evidence": store.read_evidence(), "execution_errors": list(dict.fromkeys(branch_errors)),
                  "agent_execution": continuation.report, "statement_observations": observations, "agent_statement_checks": [],
                  "assistant_interpretation": assistant.model_dump() if assistant else None,
                  "provenance": {"database": "SQLite", "independent_final_read": True, "schedule_plan": plan,
                                 "actual_schedule": "withdrawal after preliminary read, before write transaction" if plan != "no_withdrawal" else "no withdrawal",
                                 "customer_interpretation_id": customer.interpretation_id, "customer_interpretation_reused": True,
                                 "customer_interpretations_during_run": 0, "agent_generation": continuation.report["source"],
                                 "proposal_source": "replay of live capture" if capture.report["source"] == "live_meta" else "replay of authored capture",
                                 "originating_revision": proposal["originating_revision"] if proposal else None,
                                 "mocked_components": (["Authored actor responses"] if agent_responder else []) + (["Authored customer interpretation"] if customer.source == "authored_test" else []) + (["Authored assistant interpretation"] if assistant and assistant.source == "authored_test" else [])}}
        assessment = evaluate_temporal(customer, customer_turns, report, assistant if legacy_authored else None)
        report.update(assessment)
        report["temporal_evaluation"] = deepcopy(assessment["evaluation"])
        if legacy_authored:
            report["claim_contract"] = "legacy authored temporal test seam; no live extraction uses this schema"
            _claim_supplement(report, assistant, conversation)
        elif language:
            report["claim_contract_version"] = LANGUAGE_VERSION
            apply_language_evaluation(report, assistant)
        else:
            report["claim_contract_version"] = CONTRACT_VERSION
            apply_agent_claim_evaluation(report, assistant if isinstance(assistant, AgentSemanticResult) else None)
        if branch_errors and report["evaluation"]["task_verdict"] == "PASS":
            report["evaluation"]["confirmation_integrity"] = "INCONCLUSIVE"
            report["evaluation"]["task_verdict"] = "INCONCLUSIVE"
            report["evaluation"]["explanation"] += " Actor execution did not complete cleanly."
            report["evaluation"]["checks"].append({"name": "Complete actor execution", "status": "INCONCLUSIVE", "detail": "Actor generation was incomplete or failed; a partial statement cannot establish complete factual accuracy."})
        with (root / (run_id + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        reports.append(report)
    pair = {"schema_version": max((report["schema_version"] for report in reports), default=6), "report_type": "agent_comparison", "pair_id": pair_id, "run_id": pair_id,
            "freeze_id": frozen.sha256, "created_at": datetime.now(timezone.utc).isoformat(), "frozen_inputs": frozen.export(),
            "captured_proposal": proposal, "capture": {"agent_execution": capture.report,
                "conversation": [asdict(turn) for turn in capture_conversation], "proposal_present": proposal is not None,
                "final_evidence": capture_store.read_evidence(), "statement_observations": capture_observations},
            "reports": reports, "agent_accounting": _accounting(capture.report, reports, customer),
            "experiment": "One captured model proposal replayed against faulty and corrected workers, with separately generated continuations. The faulty worker injects a backend defect; this is not evidence that Meta ignored a withdrawal.",
            "execution_errors": list(dict.fromkeys(errors + capture.report["errors"]))}
    with (root / (pair_id + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(pair, stream, indent=2)
    return pair


run_agent_replay = run_agent_pair
run_agent_comparison = run_agent_pair
