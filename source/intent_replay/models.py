from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from intent_replay.booking import Booking


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Contract):
    request_turn_ids: list[str] = Field(max_length=8)
    appointment_reference_turn_ids: list[str] = Field(max_length=8)
    requested_time_turn_ids: list[str] = Field(max_length=8)
    assistant_claim_turn_ids: list[str] = Field(max_length=8)


class ClaimedBooking(Contract):
    reference: str | None = Field(max_length=80)
    starts_at: str | None = Field(max_length=64)
    timezone: str | None = Field(max_length=80)


class Interpretation(Contract):
    requested_operation: Literal["reschedule", "other", "unknown"]
    appointment_reference: str | None = Field(max_length=80)
    requested_new_time: str | None = Field(max_length=64)
    assistant_claim: Literal["rescheduled", "not_rescheduled", "unclear"]
    claimed_booking: ClaimedBooking | None
    evidence: Evidence
    ambiguities: list[str] = Field(max_length=8)


class APICall(Contract):
    status: Literal["not_called", "failed_preflight", "attempted", "transport_failed", "http_error", "response_received"] = "not_called"
    http_attempts: int = Field(default=0, ge=0)
    http_responses: int = Field(default=0, ge=0)
    successful_http_responses: int = Field(default=0, ge=0)
    usage: dict[str, int] | None = None

    @model_serializer(mode="wrap")
    def serialize_usage_when_returned(self, handler):
        result = handler(self)
        if self.usage is None:
            result.pop("usage", None)
        return result


class InterpretationResult(Contract):
    status: Literal["valid", "invalid", "ambiguous", "error"]
    model: str | None = None
    data: Interpretation | None = None
    errors: list[str] = Field(default_factory=list)
    api_call: APICall = Field(default_factory=APICall)


class Scenario(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    description: str
    customer_request: str
    slot_available: bool
    final_read_available: bool


class ScenarioCatalog(Contract):
    initial_booking: Booking
    requested_new_time: str
    scenarios: list[Scenario]


class RunRequest(Contract):
    scenario_id: str = Field(min_length=1, max_length=80)
    implementation: Literal["faulty", "corrected"]


class Check(Contract):
    name: str
    status: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    detail: str


class Evaluation(Contract):
    booking_outcome: Literal["fulfilled", "unfulfilled", "unknown"]
    instruction_adherence: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    confirmation_integrity: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    task_verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    explanation: str
    checks: list[Check]


class TemporalCustomerIntent(Contract):
    turn_id: str
    operation: Literal["reschedule", "withdraw_pending", "other", "unknown"]
    booking_reference: str | None
    requested_time: str | None
    timezone: str | None
    withdraws_turn_id: str | None
    evidence_turn_ids: list[str] = Field(min_length=1, max_length=8)


class CustomerInterpretation(Contract):
    instructions: list[TemporalCustomerIntent] = Field(min_length=1, max_length=2)
    ambiguities: list[str] = Field(max_length=8)


class TemporalAssistantClaim(Contract):
    turn_id: str
    operation: Literal["rescheduled", "not_rescheduled", "not_restored", "unclear"]
    claimed_booking: ClaimedBooking | None
    evidence_turn_ids: list[str] = Field(min_length=1, max_length=8)


class AssistantInterpretation(Contract):
    claims: list[TemporalAssistantClaim] = Field(min_length=1, max_length=2)
    ambiguities: list[str] = Field(max_length=8)


class SemanticResult(Contract):
    interpretation_id: str
    purpose: Literal["customer_intents", "assistant_claims"]
    input_sha256: str
    source: Literal["live_meta", "authored_test"]
    status: Literal["valid", "invalid", "ambiguous", "error"]
    model: str | None = None
    data: CustomerInterpretation | AssistantInterpretation | None = None
    errors: list[str] = Field(default_factory=list)
    api_call: APICall = Field(default_factory=APICall)


class FreezeRequest(Contract):
    scenario_id: str = Field(min_length=1, max_length=80)


class ComparisonRequest(Contract):
    freeze_id: str = Field(pattern=r"^[a-f0-9]{64}$")
