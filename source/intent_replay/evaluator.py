from datetime import datetime

from intent_replay.booking import WorkflowResult
from intent_replay.interpreter import validate_evidence
from intent_replay.models import Check, Evaluation, InterpretationResult


def same_time(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    try:
        first_time, second_time = datetime.fromisoformat(first), datetime.fromisoformat(second)
        return first_time.tzinfo is not None and second_time.tzinfo is not None and first_time == second_time
    except ValueError:
        return False


def evaluate(interpretation: InterpretationResult, workflow: WorkflowResult) -> Evaluation:
    checks: list[Check] = []

    def unknown(detail: str) -> Evaluation:
        checks.append(Check(name="Evidence sufficiency", status="INCONCLUSIVE", detail=detail))
        return Evaluation(booking_outcome="unknown", instruction_adherence="INCONCLUSIVE", confirmation_integrity="INCONCLUSIVE", task_verdict="INCONCLUSIVE", explanation=detail, checks=checks)

    data = interpretation.data
    if interpretation.status != "valid" or data is None or data.ambiguities:
        return unknown("Meta interpretation is missing, invalid, or ambiguous; no expected answer was substituted.")
    if validate_evidence(data, workflow.conversation):
        return unknown("The extracted intent or claim is not supported by its cited conversation turns.")
    if data.requested_operation != "reschedule" or (data.appointment_reference or "").casefold() != workflow.initial_booking.reference.casefold():
        return unknown("The interpreted operation or appointment reference cannot be matched to this booking.")
    checks.append(Check(name="Conversation evidence", status="PASS", detail="Validated the extracted intent, assistant claim, and supporting turn references."))

    final = workflow.final_booking
    if workflow.final_state_status != "available" or final is None:
        return unknown("The final committed booking cannot be retrieved. Neither a handler response nor an action trace can replace that evidence.")
    if final.reference.casefold() != (data.appointment_reference or "").casefold():
        return unknown("The retrieved record does not identify the requested booking and timezone.")

    trace = workflow.action_trace
    readbacks = [event for event in trace if event.event == "final_read"]
    confirmations = [event for event in trace if event.event == "confirmation_issued"]
    if (
        len(readbacks) != 1 or len(confirmations) != 1
        or readbacks[0].sequence <= confirmations[0].sequence
        or not same_time(readbacks[0].observed_time, final.starts_at)
        or any(event.booking_reference != final.reference for event in trace)
        or [event.sequence for event in trace] != list(range(1, len(trace) + 1))
    ):
        return unknown("The independent database read and action trace cannot be reconciled.")
    checks.append(Check(name="Committed database read", status="PASS", detail="A separate read-only SQLite connection retrieved the final record after the assistant responded."))

    fulfilled = same_time(final.starts_at, data.requested_new_time)
    outcome = "fulfilled" if fulfilled else "unfulfilled"
    checks.append(Check(name="Requested booking outcome", status="PASS" if fulfilled else "FAIL", detail=f"Requested {data.requested_new_time}; committed record contains {final.starts_at}."))
    matching_actions = all(same_time(event.target_time, data.requested_new_time) for event in trace)
    committed = [event for event in trace if event.event == "committed"]
    handler_reads = [event for event in trace if event.event == "handler_readback"]
    rejected = any(event.event == "rejected" for event in trace)
    skipped = any(event.event == "write_skipped" for event in trace)
    unchanged = same_time(final.starts_at, workflow.initial_booking.starts_at) and final.timezone == workflow.initial_booking.timezone
    verified_commit = (
        len(committed) == 1 and len(handler_reads) == 1
        and committed[0].sequence < handler_reads[0].sequence < confirmations[0].sequence
        and same_time(committed[0].observed_time, final.starts_at)
        and same_time(handler_reads[0].observed_time, final.starts_at)
        and not rejected and not skipped
    )
    verified_rejection = rejected and not committed and not skipped and unchanged
    if not matching_actions or skipped:
        adherence = "FAIL"
        adherence_detail = "The action targeted a different time from the request or deliberately skipped the required write."
    elif verified_commit and fulfilled:
        adherence = "PASS"
        adherence_detail = "The requested change was committed and verified before confirmation."
    elif verified_rejection:
        adherence = "PASS"
        adherence_detail = "The requested outcome was unfulfilled but handled correctly: the unavailable slot was rejected without changing the booking."
    else:
        adherence = "INCONCLUSIVE"
        adherence_detail = "The trace does not establish an appropriate committed action or rejection."
    checks.append(Check(name="Instruction adherence", status=adherence, detail=adherence_detail))

    claimed = data.claimed_booking
    details_match = claimed is None or (
        (claimed.reference or "").casefold() == final.reference.casefold()
        and same_time(claimed.starts_at, final.starts_at)
        and (claimed.timezone or "").casefold() == final.timezone.casefold()
    )
    if not details_match:
        accuracy = "FAIL"
        accuracy_detail = f"The assistant's stated resulting booking ({claimed.reference}, {claimed.starts_at}, {claimed.timezone}) differs from the committed record ({final.reference}, {final.starts_at}, {final.timezone})."
    elif data.assistant_claim == "not_rescheduled" and not unchanged:
        accuracy = "FAIL"
        accuracy_detail = "The assistant said no change occurred, but the committed record differs from the initial booking."
    elif (data.assistant_claim == "rescheduled" and claimed is not None and verified_commit) or (data.assistant_claim == "not_rescheduled" and verified_rejection):
        accuracy = "PASS"
        accuracy_detail = "The reported operation and all stated resulting booking details agree with the committed record and action evidence. Factual accuracy is assessed separately from request fulfillment and instruction adherence."
    else:
        accuracy = "INCONCLUSIVE"
        accuracy_detail = "The stated details do not contradict the record, but the operation claim lacks sufficient committed-action evidence."
    checks.append(Check(name="Factual claim accuracy", status=accuracy, detail=accuracy_detail))
    task = "FAIL" if outcome == "unfulfilled" or "FAIL" in (adherence, accuracy) else "INCONCLUSIVE" if "INCONCLUSIVE" in (adherence, accuracy) else "PASS"
    explanation = f"Booking {outcome}. Instruction adherence: {adherence}. Factual claim accuracy: {accuracy}. {adherence_detail} {accuracy_detail}"
    return Evaluation(booking_outcome=outcome, instruction_adherence=adherence, confirmation_integrity=accuracy, task_verdict=task, explanation=explanation, checks=checks)