"""Versioned custom cases. Existing conservative customer validation is reused."""
import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from intent_replay.booking import Booking, Turn
from intent_replay.models import Contract, CustomerInterpretation, SemanticResult
from intent_replay.temporal_interpreter import CUSTOMER_INSTRUCTIONS, authored_result, input_digest, validate_customers
from intent_replay.temporal_service import FrozenReplay, freeze_inputs

PROFILE = "proposal-execution-v1"
INTERPRETATION_CONTRACT = hashlib.sha256(CUSTOMER_INSTRUCTIONS.encode()).hexdigest()
SCOPE = "Real model proposal capture followed by paired backend execution. No final assistant reply was generated. Factual accuracy was not assessed."
WORDING_CONTRACT = "unconditional-booking-wording-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def seal(value, field="sha256"):
    return {**value, field: digest({k: v for k, v in value.items() if k != field})}


def check_seal(value, field="sha256"):
    if not isinstance(value, dict) or value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise ValueError("Artifact hash mismatch; no values were repaired.")


class InitialBooking(Contract):
    reference: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    service: str = Field(min_length=1, max_length=200)
    starts_at: str = Field(min_length=16, max_length=64)
    timezone: str = Field(min_length=1, max_length=80)


class ExpectedBranch(Contract):
    final_time: str = Field(min_length=16, max_length=64)
    action_status: Literal["committed", "suppressed", "rejected"]
    booking_outcome: Literal["fulfilled", "unfulfilled", "unknown"]
    instruction_adherence: Literal["PASS", "FAIL", "INCONCLUSIVE"]


class Expectations(Contract):
    faulty: ExpectedBranch
    corrected: ExpectedBranch
    notes: str = Field(default="", max_length=1000)


class CaseSpec(Contract):
    schema_version: Literal["booking-case-v1"] = "booking-case-v1"
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    description: str = Field(min_length=1, max_length=2000)
    initial_booking: InitialBooking
    requested_time: str = Field(min_length=16, max_length=64)
    slot_available: bool
    request: str = Field(min_length=1, max_length=4000)
    withdrawal: str | None = Field(default=None, min_length=1, max_length=4000)
    timing: Literal["no_withdrawal", "precommit_withdrawal"]
    private_expectations: Expectations

    @model_validator(mode="after")
    def bounded_case(self):
        try:
            zone = ZoneInfo(self.initial_booking.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone.") from None
        for value in (self.initial_booking.starts_at, self.requested_time):
            stamp = datetime.fromisoformat(value)
            if stamp.utcoffset() is None or stamp.second or stamp.microsecond or stamp.utcoffset() != stamp.astimezone(zone).utcoffset():
                raise ValueError("Use aware minute-precision times consistent with the stated timezone.")
        if datetime.fromisoformat(self.initial_booking.starts_at) == datetime.fromisoformat(self.requested_time):
            raise ValueError("A reschedule must have a different target time.")
        if bool(self.withdrawal) != (self.timing == "precommit_withdrawal"):
            raise ValueError("Only no-withdrawal or a pre-commit withdrawal with explicit wording is supported.")
        return self

    @property
    def plan(self):
        return "no_withdrawal" if self.timing == "no_withdrawal" else "withdraw_after_preliminary_read"

    def turns(self):
        initial = self.initial_booking
        stamp = datetime.fromisoformat(initial.starts_at)
        turns = [Turn("context", "assistant", f"Booking {initial.reference}: {initial.service}, on {stamp:%Y-%m-%d} at {stamp:%H:%M} ({initial.timezone})."),
                 Turn("customer-1", "customer", self.request)]
        if self.withdrawal:
            turns.append(Turn("customer-2", "customer", self.withdrawal))
        return turns

    def declared_meaning(self):
        initial = self.initial_booking
        rows = [{"turn_id": "customer-1", "operation": "reschedule", "booking_reference": initial.reference,
                 "requested_time": self.requested_time, "timezone": initial.timezone, "withdraws_turn_id": None,
                 "evidence_turn_ids": ["context", "customer-1"]}]
        if self.withdrawal:
            rows.append({"turn_id": "customer-2", "operation": "withdraw_pending", "booking_reference": initial.reference,
                         "requested_time": initial.starts_at, "timezone": initial.timezone, "withdraws_turn_id": "customer-1",
                         "evidence_turn_ids": ["context", "customer-1", "customer-2"]})
        return CustomerInterpretation.model_validate({"instructions": rows, "ambiguities": []})

    def wording_errors(self):
        # An extraction cannot authorize text that this bounded benchmark does
        # not understand. Match the WHOLE operative turn, with literal declared
        # operands, before consulting the unchanged general evidence validator.
        reference = re.escape(self.initial_booking.reference)
        zone = re.escape(self.initial_booking.timezone)
        def destination(value):
            stamp = datetime.fromisoformat(value)
            return rf"{stamp:%H:%M}\s+(?i:on)\s+{stamp:%Y-%m-%d}(?:\s*,\s*{zone}|\s+\(\s*{zone}\s*\))"
        request = rf"\s*(?i:(?:please\s+)?(?:move|reschedule)\s+booking)\s+{reference}\s+(?i:to)\s+{destination(self.requested_time)}\.?\s*"
        withdrawal = rf"\s*(?i:(?:please\s+)?(?:do\s+not|don['’]t)\s+change\s+it)[.;]\s*(?i:(?:please\s+)?keep\s+booking)\s+{reference}\s+(?i:at)\s+{destination(self.initial_booking.starts_at)}\.?\s*"
        errors = []
        if not re.fullmatch(request, self.request):
            errors.append("Unsupported benchmark request. Use only: 'Please move booking REF to HH:MM on YYYY-MM-DD, IANA/Zone.' (reschedule and parenthesized timezone are also supported). Conditions and extra operative text are not accepted.")
        if self.withdrawal and not re.fullmatch(withdrawal, self.withdrawal):
            errors.append("Unsupported benchmark withdrawal. Use only: 'Do not change it. Keep booking REF at HH:MM on YYYY-MM-DD, IANA/Zone.' with the original time. Conditions and extra operative text are not accepted.")
        if errors:
            return errors
        return validate_customers(self.declared_meaning(), self.turns())


def freeze_key(case):
    return digest({"case": case.model_dump(), "interpretation_contract": INTERPRETATION_CONTRACT})


def freeze_case(case, *, interpreter=None, budget=None):
    errors = case.wording_errors()
    if errors:
        return {"status": "unsupported", "errors": errors, "case_sha256": digest(case.model_dump()), "freeze_key": freeze_key(case)}
    frozen = freeze_inputs(Booking(**case.initial_booking.model_dump()), case.requested_time, case.slot_available,
                           case.turns(), case.plan, customer_interpreter=interpreter, budget=budget)
    return seal({"version": "benchmark-freeze-v1", "freeze_key": freeze_key(case), "case_sha256": digest(case.model_dump()),
                 "interpretation_contract": INTERPRETATION_CONTRACT, "frozen": frozen.export(),
                 "status": "valid" if not frozen.data["validation_errors"] else "invalid", "errors": frozen.data["validation_errors"]})


def validate_freeze(case, record):
    check_seal(record)
    wording = case.wording_errors()
    if wording:
        raise ValueError(" ".join(wording))
    if record.get("version") != "benchmark-freeze-v1" or record.get("interpretation_contract") != INTERPRETATION_CONTRACT or record.get("case_sha256") != digest(case.model_dump()) or record.get("freeze_key") != freeze_key(case):
        raise ValueError("Case or interpretation contract does not match this freeze.")
    frozen = FrozenReplay.from_export(record["frozen"])
    inputs = frozen.data
    customer = SemanticResult.model_validate(inputs["customer_interpretation"], strict=True)
    turns = case.turns()
    if (case.wording_errors() or inputs["initial_booking"] != case.initial_booking.model_dump() or inputs["target_time"] != case.requested_time
        or inputs["slot_available"] is not case.slot_available or inputs["schedule_plan"] != case.plan
        or inputs["customer_turns"] != [asdict(t) for t in turns] or inputs["validation_errors"]
        or customer.status != "valid" or customer.purpose != "customer_intents" or customer.input_sha256 != input_digest(turns)
        or not isinstance(customer.data, CustomerInterpretation) or validate_customers(customer.data, turns)):
        raise ValueError("Frozen customer evidence did not revalidate against the exact case and wording.")
    # Compare structured operands independently; the model is never an answer key.
    expected = case.declared_meaning().instructions
    if len(customer.data.instructions) != len(expected):
        raise ValueError("Frozen instruction count differs from the declared case.")
    for actual, declared in zip(customer.data.instructions, expected):
        for key in ("turn_id", "operation", "booking_reference", "timezone", "withdraws_turn_id"):
            if getattr(actual, key) != getattr(declared, key):
                raise ValueError("Frozen instruction operands differ from the declared case.")
        if datetime.fromisoformat(actual.requested_time) != datetime.fromisoformat(declared.requested_time):
            raise ValueError("Frozen target differs from the declared case.")
    return frozen, customer


def authored_freeze(case):
    """Offline fixtures only; never used as the live Meta customer fallback."""
    return freeze_case(case, interpreter=lambda turns: authored_result(turns, case.declared_meaning()))
