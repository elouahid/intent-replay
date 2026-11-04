import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from intent_replay.booking import Booking, Turn
from intent_replay.evaluator import same_time
from intent_replay.meta_client import AttemptBudget, MODEL_NAME, PROJECT_ROOT
from intent_replay.models import CustomerInterpretation, SemanticResult
from intent_replay.temporal import Instruction, RevisionStore
from intent_replay.temporal_evaluator import evaluate_temporal
from intent_replay.temporal_interpreter import input_digest, interpret_assistant, interpret_customers, validate_customers


PLANS = {
    "withdraw_before_execution": ["accept reschedule", "accept withdrawal", "worker preliminary read", "worker transaction", "statement and final read"],
    "withdraw_after_preliminary_read": ["accept reschedule", "worker preliminary read", "accept withdrawal", "worker transaction", "statement and final read"],
    "commit_before_withdrawal": ["accept reschedule", "worker preliminary read", "worker transaction", "first statement", "accept withdrawal", "later statement and final read"],
    "no_withdrawal": ["accept reschedule", "worker preliminary read", "worker transaction", "statement and final read"],
}


@dataclass(frozen=True)
class FrozenReplay:
    payload_json: str
    sha256: str

    def __post_init__(self):
        if hashlib.sha256(self.payload_json.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("Frozen input digest mismatch.")

    @property
    def data(self):
        return json.loads(self.payload_json)

    def export(self):
        return {"freeze_id": self.sha256, "payload": self.data}

    @classmethod
    def from_export(cls, value):
        payload = json.dumps(value["payload"], sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return cls(payload, value["freeze_id"])


def load_temporal_catalog() -> dict:
    return json.loads((PROJECT_ROOT / "fixtures" / "temporal.json").read_text(encoding="utf-8"))


def temporal_options() -> dict:
    return {**load_temporal_catalog(), "model": MODEL_NAME, "plans": PLANS}


def save_frozen(frozen: FrozenReplay, root: Path) -> None:
    directory = root / "frozen"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (frozen.sha256 + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(frozen.export(), stream, indent=2)


def load_frozen(freeze_id: str, root: Path) -> FrozenReplay:
    if not re.fullmatch(r"[a-f0-9]{64}", freeze_id):
        raise ValueError("Invalid frozen input identifier.")
    return FrozenReplay.from_export(json.loads((root / "frozen" / (freeze_id + ".json")).read_text(encoding="utf-8")))


def saved_pairs(root: Path) -> list[dict]:
    result = []
    for path in root.glob("*.json"):
        if not re.fullmatch(r"[a-f0-9]{32}", path.stem):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") == 3 and data.get("report_type") == "temporal_comparison":
            result.append({"pair_id": data["pair_id"], "created_at": data["created_at"], "plan": data["frozen_inputs"]["payload"]["schedule_plan"]})
    return sorted(result, key=lambda item: item["created_at"], reverse=True)[:100]


def load_pair(pair_id: str, root: Path) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", pair_id):
        raise ValueError("Invalid comparison identifier.")
    data = json.loads((root / (pair_id + ".json")).read_text(encoding="utf-8"))
    if data.get("schema_version") != 3 or data.get("report_type") != "temporal_comparison":
        raise ValueError("This is not a version-3 comparison report; historical reports are unchanged.")
    return data


def freeze_inputs(
    initial: Booking, target_time: str, available: bool, customer_turns: list[Turn], plan: str,
    *, customer_interpreter: Callable | None = None, budget: AttemptBudget | None = None,
) -> FrozenReplay:
    if plan not in PLANS:
        raise ValueError("Unsupported deterministic scheduling plan.")
    result = customer_interpreter(customer_turns) if customer_interpreter else interpret_customers(customer_turns, budget)
    errors = list(result.errors)
    if result.status == "valid" and isinstance(result.data, CustomerInterpretation):
        errors.extend(validate_customers(result.data, customer_turns))
        if result.purpose != "customer_intents" or result.input_sha256 != input_digest(customer_turns):
            errors.append("Customer interpretation does not belong to these frozen messages.")
        if len(result.data.instructions) != (1 if plan == "no_withdrawal" else 2):
            errors.append("Scheduling plan and supported customer instructions do not match.")
        first = result.data.instructions[0]
        if first.booking_reference != initial.reference or not same_time(first.requested_time, target_time) or first.timezone != initial.timezone:
            errors.append("Validated request does not match the single-booking replay inputs.")
        if len(result.data.instructions) == 2 and not same_time(result.data.instructions[1].requested_time, initial.starts_at):
            errors.append("Withdrawal must retain the original booking; restoring another time is unsupported.")
    else:
        errors.append("Customer interpretation is not valid; no instruction can be accepted.")
    data = {
        "schema_version": 3, "created_at": datetime.now(timezone.utc).isoformat(),
        "initial_booking": asdict(initial), "target_time": target_time, "slot_available": available,
        "customer_turns": [asdict(turn) for turn in customer_turns],
        "customer_interpretation": result.model_dump(), "validation_errors": list(dict.fromkeys(errors)),
        "schedule_plan": plan, "schedule_steps": PLANS[plan],
        "interpretation_policy": "Explicit new customer extraction when freezing. Replays reuse this exact interpretation without accepting any instruction early.",
    }
    payload = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return FrozenReplay(payload, hashlib.sha256(payload.encode("utf-8")).hexdigest())


def freeze_scenario(scenario_id: str, *, customer_interpreter=None, budget=None) -> FrozenReplay:
    catalog = load_temporal_catalog()
    scenario = next((item for item in catalog["scenarios"] if item["id"] == scenario_id), None)
    if scenario is None:
        raise ValueError("Unknown temporal scenario.")
    initial = Booking(**catalog["initial_booking"])
    original = datetime.fromisoformat(initial.starts_at)
    conversation = [Turn("context", "assistant", f"Booking {initial.reference}: {initial.service}, on {original:%Y-%m-%d} at {original:%H:%M} ({initial.timezone}).")]
    conversation.extend(Turn(f"customer-{index}", "customer", text) for index, text in enumerate(scenario["customer_messages"], start=1))
    return freeze_inputs(initial, catalog["target_time"], catalog["slot_available"], conversation, scenario["plan"], customer_interpreter=customer_interpreter, budget=budget)


def summarize_calls(results) -> dict:
    unique = {result.interpretation_id: result for result in results if result is not None}
    return {
        "interpretations": len(unique), "http_attempts": sum(result.api_call.http_attempts for result in unique.values()),
        "http_responses": sum(result.api_call.http_responses for result in unique.values()),
        "successful_http_responses": sum(result.api_call.successful_http_responses for result in unique.values()),
        "valid_interpretations": sum(result.status == "valid" for result in unique.values()),
    }


def _run_branch(frozen: FrozenReplay, implementation, root, assistant_interpreter, budget):
    inputs = frozen.data
    run_id = uuid4().hex
    initial = Booking(**inputs["initial_booking"])
    store = RevisionStore.create(root / (run_id + ".sqlite3"), initial, inputs["target_time"], inputs["slot_available"])
    customer = SemanticResult.model_validate(inputs["customer_interpretation"])
    customer_turns = [Turn(**turn) for turn in inputs["customer_turns"]]
    conversation = [customer_turns[0]]
    assistant_result = None
    errors = list(inputs["validation_errors"])
    if not errors:
        if customer.status != "valid" or not isinstance(customer.data, CustomerInterpretation) or validate_customers(customer.data, customer_turns):
            errors.append("Frozen customer interpretation failed revalidation; no request was accepted.")
    if not errors:
        def accept(item):
            turn = next(turn for turn in customer_turns if turn.id == item.turn_id)
            conversation.append(turn)
            store.receive(turn.id)
            store.accept(Instruction(item.turn_id, item.operation, item.booking_reference, item.requested_time, item.timezone, tuple(item.evidence_turn_ids), customer.interpretation_id))

        def state_statement(snapshot, late=False):
            booking = snapshot["booking"]
            stamp = datetime.fromisoformat(booking["starts_at"])
            if late:
                text = f"No restoration was performed. Booking {booking['reference']} is at {stamp:%H:%M} on {stamp:%Y-%m-%d} ({booking['timezone']})."
                anchor = next(event for event in reversed(snapshot["journal"]) if event["event"] == "withdrawal_too_late")
            else:
                action = snapshot["actions"][0]
                anchor = next(event for event in snapshot["journal"] if event["sequence"] == action["decision_sequence"])
                if action["status"] == "committed":
                    text = f"Confirmed: booking {booking['reference']} has been moved to {stamp:%H:%M} on {stamp:%Y-%m-%d} ({booking['timezone']})."
                else:
                    text = f"I did not reschedule booking {booking['reference']}. Your booking remains at {stamp:%H:%M} on {stamp:%Y-%m-%d} ({booking['timezone']})."
            turn = Turn("assistant-" + str(sum(turn.role == "assistant" for turn in conversation)), "assistant", text)
            store.record_statement(turn.id, turn.text, anchor["sequence"], snapshot)
            conversation.append(turn)

        first = customer.data.instructions[0]
        withdrawal = customer.data.instructions[1] if len(customer.data.instructions) == 2 else None
        accept(first)
        plan = inputs["schedule_plan"]
        if plan == "withdraw_before_execution":
            accept(withdrawal)
        hook = (lambda: accept(withdrawal)) if plan == "withdraw_after_preliminary_read" else None
        snapshot = store.execute(implementation, after_preliminary_read=hook)
        state_statement(snapshot)
        if plan == "commit_before_withdrawal":
            accept(withdrawal)
            state_statement(store.read_evidence(), late=True)
        assistant_result = assistant_interpreter(conversation) if assistant_interpreter else interpret_assistant(conversation, budget)
    report = {
        "schema_version": 3, "report_type": "temporal_branch", "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "freeze_id": frozen.sha256,
        "implementation": implementation, "controlled_demonstration": True,
        "initial_booking": inputs["initial_booking"], "conversation": [asdict(turn) for turn in conversation],
        "final_evidence": store.read_evidence(), "execution_errors": errors,
        "assistant_interpretation": assistant_result.model_dump() if assistant_result else None,
        "provenance": {
            "database": "SQLite", "independent_final_read": True, "customer_interpretation_id": customer.interpretation_id,
            "customer_interpretation_reused": True, "customer_interpretations_during_branch": 0,
            "schedule_plan": inputs["schedule_plan"], "ordering_source": "persisted SQLite journal sequence, not timestamps",
            "mocked_components": ["Authored customer interpretation"] if customer.source == "authored_test" else [],
        },
    }
    if assistant_result and assistant_result.source == "authored_test":
        report["provenance"]["mocked_components"].append("Authored assistant interpretation")
    report.update(evaluate_temporal(customer, customer_turns, report, assistant_result))
    (root / (run_id + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report, assistant_result


def run_frozen_pair(frozen: FrozenReplay, *, storage_root: Path | None = None, assistant_interpreter: Callable | None = None, budget: AttemptBudget | None = None) -> dict:
    root = storage_root or PROJECT_ROOT / ".local" / "temporal"
    root.mkdir(parents=True, exist_ok=True)
    reports, calls = [], []
    for implementation in ("faulty", "corrected"):
        report, result = _run_branch(frozen, implementation, root, assistant_interpreter, budget)
        reports.append(report)
        if result:
            calls.append(result)
    pair_id = uuid4().hex
    pair = {
        "schema_version": 3, "report_type": "temporal_comparison", "pair_id": pair_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "controlled_demonstration": True,
        "historical_reports": "Version-1 and version-2 reports remain unchanged and are not migrated into temporal evidence.",
        "frozen_inputs": frozen.export(), "reports": reports,
        "interpretation_accounting": {
            "customer_interpretations_during_pair": 0, "shared_customer_interpretation_reused": True,
            "new_calls": summarize_calls(calls),
            "original_freeze_call": frozen.data["customer_interpretation"]["api_call"],
            "note": "Original freeze counts are historical provenance, not additional attempts during this pair.",
        },
    }
    (root / (pair_id + ".json")).write_text(json.dumps(pair, indent=2), encoding="utf-8")
    return pair