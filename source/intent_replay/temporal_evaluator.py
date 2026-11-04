from intent_replay.booking import Turn
from intent_replay.evaluator import same_time
from intent_replay.models import AssistantInterpretation, Check, CustomerInterpretation, Evaluation, SemanticResult
from intent_replay.temporal_interpreter import input_digest, validate_claims, validate_customers


def _assessment(outcome, adherence, accuracy, explanation, checks=()):
    task = "FAIL" if outcome == "unfulfilled" or "FAIL" in (adherence, accuracy) else "INCONCLUSIVE" if outcome == "unknown" or "INCONCLUSIVE" in (adherence, accuracy) else "PASS"
    return Evaluation(
        booking_outcome=outcome, instruction_adherence=adherence, confirmation_integrity=accuracy,
        task_verdict=task, explanation=explanation, checks=list(checks),
    ).model_dump()


def _combined(statuses):
    return "FAIL" if "FAIL" in statuses else "INCONCLUSIVE" if not statuses or "INCONCLUSIVE" in statuses else "PASS"


def _same_booking(first, second):
    return bool(first and second and first.get("reference") == second.get("reference") and same_time(first.get("starts_at"), second.get("starts_at")) and first.get("timezone") == second.get("timezone"))


def evaluate_temporal(customer: SemanticResult, customer_turns: list[Turn], report: dict, assistant: SemanticResult | None) -> dict:
    evidence = report.get("final_evidence") or {}
    journal = evidence.get("journal", [])
    rows = evidence.get("accepted_instructions", [])
    actions = evidence.get("actions", [])
    sequence_values = [event.get("sequence") for event in journal]
    ordered = bool(sequence_values) and all(isinstance(value, int) and value > 0 for value in sequence_values)
    ordered = ordered and sequence_values == sorted(set(sequence_values))
    events = {event.get("sequence"): event for event in journal}
    acceptance = [event for event in journal if event.get("event") == "instruction_accepted"]
    customer_valid = (
        customer.status == "valid" and isinstance(customer.data, CustomerInterpretation)
        and customer.purpose == "customer_intents" and customer.input_sha256 == input_digest(customer_turns)
        and not validate_customers(customer.data, customer_turns)
    )
    interpretations = {item.turn_id: item for item in customer.data.instructions} if customer_valid else {}
    accepted_valid = customer_valid and ordered and bool(rows) and len(rows) == len(acceptance)
    accepted_by_revision = {}
    for row in rows:
        item = interpretations.get(row.get("turn_id"))
        matches = [event for event in acceptance if event["data"].get("revision") == row.get("revision")]
        valid = item is not None and len(matches) == 1
        if valid:
            payload = matches[0]["data"]
            valid = (
                row.get("operation") == item.operation and row.get("booking_reference") == item.booking_reference
                and same_time(row.get("target_time"), item.requested_time) and row.get("timezone") == item.timezone
                and row.get("interpretation_id") == customer.interpretation_id
                and row.get("evidence_turn_ids") == item.evidence_turn_ids
                and all(payload.get(key) == value for key, value in row.items())
            )
        accepted_valid = accepted_valid and valid
        if valid:
            accepted_by_revision[row["revision"]] = {**row, "sequence": matches[0]["sequence"]}
    if accepted_valid:
        revisions = [row["revision"] for row in rows]
        accepted_valid = revisions == list(range(1, len(rows) + 1)) and [accepted_by_revision[revision]["sequence"] for revision in revisions] == sorted(accepted_by_revision[revision]["sequence"] for revision in revisions)
    latest = accepted_by_revision.get(rows[-1]["revision"]) if accepted_valid else None
    final = evidence.get("booking")
    final_valid = bool(
        final and latest and evidence.get("read_source") == "independent read-only SQLite transaction"
        and evidence.get("read_after_sequence") == max(sequence_values, default=None)
        and final.get("reference") == latest["booking_reference"] and final.get("timezone") == latest["timezone"]
        and same_time(final.get("starts_at"), final.get("starts_at"))
    )
    outcome = "fulfilled" if final_valid and same_time(final["starts_at"], latest["target_time"]) else "unfulfilled" if final_valid else "unknown"
    checks = [Check(name="Accepted instruction evidence", status="PASS" if accepted_valid else "INCONCLUSIVE", detail="Accepted revisions match validated customer evidence and durable journal order." if accepted_valid else "Accepted revision evidence is missing, contradictory, or unsupported; receipt and interpretation are not acceptance.")]
    checks.append(Check(name="Applicable booking outcome", status="PASS" if outcome == "fulfilled" else "FAIL" if outcome == "unfulfilled" else "INCONCLUSIVE", detail=f"Latest accepted revision {latest['revision']} requests {latest['target_time']}; independent readback contains {final['starts_at']}." if final_valid else "Applicable accepted intent or independent final state cannot be established."))
    action_assessments = []
    for action in actions:
        decision = events.get(action.get("decision_sequence"))
        queued = [event for event in journal if event.get("event") == "action_queued" and event["data"].get("action_id") == action.get("action_id")]
        original = accepted_by_revision.get(action.get("accepted_revision"))
        binding = bool(accepted_valid and original and len(queued) == 1 and decision and decision.get("event") == "action_" + action.get("status", ""))
        if binding:
            binding = (
                original["operation"] == "reschedule"
                and original["sequence"] < queued[0]["sequence"] < decision["sequence"]
                and all(queued[0]["data"].get(key) == action.get(key) == decision["data"].get(key) for key in ("action_id", "booking_reference", "operation", "target_time", "accepted_revision"))
                and original["booking_reference"] == action["booking_reference"]
                and same_time(original["target_time"], action["target_time"])
            )
        current = max((row for row in accepted_by_revision.values() if binding and row["sequence"] < decision["sequence"]), key=lambda row: row["revision"], default=None)
        authorized = bool(current and current["revision"] == action.get("accepted_revision") and current["operation"] == "reschedule") if binding else None
        status, detail = "INCONCLUSIVE", "Queued binding, acceptance/commit order, or atomic decision evidence is insufficient."
        atomic = False
        if binding:
            guards = [event for event in journal if event.get("event") == "authorization_checked" and event["data"].get("action_id") == action["action_id"]]
            if len(guards) == 1:
                guard = guards[0]
                atomic = (
                    guard["transaction_id"] == decision["transaction_id"] and guard["sequence"] + 1 == decision["sequence"]
                    and guard["data"].get("checked_revision") == decision["data"].get("checked_revision") == action.get("checked_revision") == current["revision"]
                    and guard["data"].get("accepted_revision") == action["accepted_revision"]
                    and guard["data"].get("authorized") is authorized and decision["data"].get("authorized") is authorized
                )
            if action["status"] == "committed" and authorized is False:
                status, detail = "FAIL", f"Revision {current['revision']} was durably accepted before this commit. The queued action was bound to obsolete revision {action['accepted_revision']}."
            elif atomic and action["status"] == "committed" and authorized:
                status, detail = "PASS", f"Revision {action['accepted_revision']} still authorized this action when it committed. A later acceptance cannot invalidate this earlier commit."
            elif atomic and action["status"] == "suppressed" and not authorized and _same_booking(decision["data"].get("before"), decision["data"].get("after")):
                status, detail = "PASS", f"The transaction observed revision {current['revision']} and suppressed obsolete revision {action['accepted_revision']} without changing the booking."
            elif atomic and action["status"] == "rejected" and authorized and _same_booking(decision["data"].get("before"), decision["data"].get("after")):
                status, detail = "PASS", "The authorized action was rejected because its slot was unavailable; no booking mutation occurred."
        action_assessments.append({"action_id": action.get("action_id"), "accepted_revision": action.get("accepted_revision"), "current_revision_at_decision": current["revision"] if current else None, "decision_sequence": action.get("decision_sequence"), "authorized_at_decision": authorized, "atomic_evidence": atomic, "status": status, "detail": detail})
    adherence = _combined([item["status"] for item in action_assessments])
    checks.append(Check(name="Action authorization", status=adherence, detail=" ".join(item["detail"] for item in action_assessments) or "No resolved action evidence is available."))
    conversation = [Turn(**turn) for turn in report.get("conversation", [])]
    semantic_valid = bool(
        assistant and assistant.status == "valid" and isinstance(assistant.data, AssistantInterpretation)
        and assistant.purpose == "assistant_claims" and assistant.input_sha256 == input_digest(conversation)
        and not validate_claims(assistant.data, conversation)
    )
    statement_assessments = []
    if semantic_valid:
        for claim in assistant.data.claims:
            matches = [event for event in journal if event.get("event") == "assistant_statement" and event["data"].get("turn_id") == claim.turn_id]
            status, detail = "INCONCLUSIVE", "Statement-scoped state or execution evidence is missing or contradictory."
            source_sequence = None
            if len(matches) == 1:
                statement = matches[0]
                payload = statement["data"]
                snapshot = payload.get("snapshot") or {}
                source_sequence = payload.get("describes_sequence")
                source_event = events.get(source_sequence)
                turn = next((turn for turn in conversation if turn.id == claim.turn_id), None)
                state = snapshot.get("booking")
                linked = bool(
                    turn and turn.text == payload.get("text") and state
                    and state.get("reference") and state.get("timezone") and same_time(state.get("starts_at"), state.get("starts_at"))
                    and snapshot.get("read_source") == "independent read-only SQLite transaction"
                    and isinstance(source_sequence, int) and isinstance(snapshot.get("read_after_sequence"), int)
                    and isinstance(statement.get("sequence"), int)
                    and source_sequence <= snapshot["read_after_sequence"] < statement["sequence"]
                )
                claimed = claim.claimed_booking.model_dump() if claim.claimed_booking else None
                if linked and claimed and not _same_booking(claimed, state):
                    status, detail = "FAIL", "The stated booking differs from the independent readback linked to this statement, regardless of later state."
                elif linked and source_event:
                    operation = source_event["event"]
                    source_data = source_event["data"]
                    if claim.operation == "rescheduled" and operation == "action_committed" and _same_booking(source_data.get("after"), state):
                        status, detail = "PASS", "The completed-change statement matches its committed action and independent state snapshot. Factual accuracy is assessed separately from authorization and fulfillment."
                    elif claim.operation == "not_rescheduled" and operation in ("action_suppressed", "action_rejected") and _same_booking(source_data.get("before"), state) and _same_booking(source_data.get("after"), state):
                        status, detail = "PASS", "The unchanged-booking statement matches its suppression/rejection and independent state snapshot."
                    elif claim.operation == "not_restored" and operation == "withdrawal_too_late":
                        commits = [event for event in journal if event.get("event") == "action_committed" and isinstance(event.get("sequence"), int) and event["sequence"] < source_sequence]
                        if len(commits) == 1 and _same_booking(commits[0]["data"].get("after"), state):
                            status, detail = "PASS", "The later statement reports the still-committed booking; no restoration action or rollback is claimed."
                    elif claim.operation == "rescheduled" and operation in ("action_suppressed", "action_rejected"):
                        status, detail = "FAIL", "The assistant claimed execution, but the linked action was suppressed or rejected."
                    elif claim.operation == "not_rescheduled" and operation == "action_committed":
                        status, detail = "FAIL", "The assistant denied execution, but the linked action committed."
            statement_assessments.append({"turn_id": claim.turn_id, "describes_sequence": source_sequence, "status": status, "detail": detail})
    accuracy = _combined([item["status"] for item in statement_assessments])
    checks.append(Check(name="Statement-scoped factual accuracy", status=accuracy, detail=" ".join(item["detail"] for item in statement_assessments) or "Assistant interpretation or statement evidence is unavailable; no claim was substituted."))
    late = bool(latest and any(event.get("event") == "withdrawal_too_late" and event["data"].get("revision") == latest["revision"] for event in journal))
    explanation = f"Booking {outcome}. Instruction adherence: {adherence}. Factual claim accuracy: {accuracy}. "
    explanation += " ".join(item["detail"] for item in action_assessments)
    if late:
        explanation += " The later withdrawal is assessed separately: the prior action was already complete and no database action restored the original time."
    evaluation = _assessment(outcome, adherence, accuracy, explanation, checks)
    revision_assessments = []
    for row in rows:
        if latest and row["revision"] == latest["revision"]:
            revision_assessments.append({"revision": row["revision"], "turn_id": row["turn_id"], "scope": "applicable_at_final_read", "evaluation": evaluation})
        elif accepted_valid and action_assessments and action_assessments[0]["current_revision_at_decision"] == row["revision"]:
            decision = events.get(action_assessments[0]["decision_sequence"])
            state = decision["data"].get("after") if decision else None
            prior_outcome = "fulfilled" if state and same_time(state.get("starts_at"), row["target_time"]) else "unfulfilled" if state else "unknown"
            prior_accuracy = _combined([item["status"] for item in statement_assessments if item["describes_sequence"] == action_assessments[0]["decision_sequence"]])
            revision_assessments.append({"revision": row["revision"], "turn_id": row["turn_id"], "scope": "completed_before_later_request", "evaluation": _assessment(prior_outcome, action_assessments[0]["status"], prior_accuracy, "This accepted request is assessed at its own completed action, not against a later request.")})
        else:
            revision_assessments.append({"revision": row.get("revision"), "turn_id": row.get("turn_id"), "scope": "superseded_before_execution" if accepted_valid else "ordering_unresolved", "evaluation": None})
    return {"evaluation": evaluation, "action_assessments": action_assessments, "statement_assessments": statement_assessments, "revision_assessments": revision_assessments}