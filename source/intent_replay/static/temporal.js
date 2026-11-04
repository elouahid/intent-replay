"use strict";

const temporalState = { catalog: null, frozen: null, pair: null, busy: false, saved: [], workflow: "agent" };
const temporalElements = Object.fromEntries([
  "temporal-tab", "immediate-tab", "agent-tab", "temporal-view", "immediate-view", "agent-view", "temporal-freeze-form",
  "temporal-scenario", "freeze-button", "compare-button", "temporal-status", "temporal-notice",
  "saved-comparison", "open-comparison", "freeze-status", "shared-instructions", "freeze-provenance", "freeze-details",
  "schedule-steps", "comparison-caption", "comparison-context", "comparison-empty", "comparison-content",
  "comparison-matrix", "comparison-branches", "comparison-accounting", "download-comparison", "temporal-empty-detail",
].map((id) => [id, document.getElementById(id)]));

const TEMPORAL_OPERATIONS = { reschedule: "Reschedule", withdraw_pending: "Withdraw pending reschedule", other: "Unsupported operation", unknown: "Unresolved" };
const EVENT_LABELS = {
  initialized: "Initial booking persisted", instruction_received: "Instruction received",
  instruction_accepted: "Instruction accepted", action_queued: "Reschedule queued",
  worker_preliminary_read: "Worker preliminary read", authorization_checked: "Transactional authorization check",
  action_committed: "Reschedule committed", action_suppressed: "Obsolete action suppressed",
  action_rejected: "Unavailable slot rejected", withdrawal_too_late: "Withdrawal after completed action",
  assistant_statement: "Assistant statement issued",
};

function validateSemanticResult(result, purpose) {
  requireObject(result, purpose);
  requireValue(result.purpose === purpose, `${purpose}.purpose`);
  requireEnum(result.status, ["valid", "invalid", "ambiguous", "error"], `${purpose}.status`);
  requireEnum(result.source, ["live_meta", "authored_test"], `${purpose}.source`);
  for (const field of ["interpretation_id", "input_sha256"]) requireString(result[field], `${purpose}.${field}`);
  requireString(result.model, `${purpose}.model`, true);
  requireStringList(result.errors, `${purpose}.errors`);
  validateAPICall(result.api_call, `${purpose}.api_call`);
  if (result.data !== null) {
    requireObject(result.data, `${purpose}.data`);
    const items = purpose === "customer_intents" ? result.data.instructions : result.data.claims;
    requireValue(Array.isArray(items), `${purpose}.items`);
    requireStringList(result.data.ambiguities, `${purpose}.ambiguities`);
    for (const item of items) {
      requireString(item.turn_id, `${purpose}.turn_id`);
      requireString(item.operation, `${purpose}.operation`);
      requireStringList(item.evidence_turn_ids, `${purpose}.evidence_turn_ids`);
    }
  }
}

function validateFrozen(value) {
  requireObject(value, "frozen_inputs");
  requireValue(typeof value.freeze_id === "string" && /^[a-f0-9]{64}$/.test(value.freeze_id), "freeze_id");
  const payload = value.payload;
  requireObject(payload, "frozen payload");
  requireValue(payload.schema_version === 3, "temporal schema version 3; historical reports are not migrated");
  validateBooking(payload.initial_booking, "frozen initial booking");
  requireString(payload.target_time, "frozen target time");
  requireValue(typeof payload.slot_available === "boolean", "frozen availability");
  requireString(payload.schedule_plan, "frozen scheduling plan");
  requireStringList(payload.schedule_steps, "frozen scheduling steps");
  requireStringList(payload.validation_errors, "frozen validation errors");
  requireValue(Array.isArray(payload.customer_turns), "frozen customer turns");
  payload.customer_turns.forEach((turn) => {
    requireString(turn.id, "customer turn id");
    requireString(turn.text, "customer turn text");
    requireEnum(turn.role, ["customer", "assistant"], "customer turn role");
  });
  validateSemanticResult(payload.customer_interpretation, "customer_intents");
}

function validateTemporalEvaluation(value) {
  requireObject(value, "temporal evaluation");
  requireEnum(value.booking_outcome, Object.keys(OUTCOME_STYLES), "booking outcome");
  for (const field of ["instruction_adherence", "confirmation_integrity", "task_verdict"]) {
    requireEnum(value[field], Object.keys(INTEGRITY_STYLES), field);
  }
  requireString(value.explanation, "evaluation explanation");
  const failed = value.booking_outcome === "unfulfilled" || [value.instruction_adherence, value.confirmation_integrity].includes("FAIL");
  const unknown = value.booking_outcome === "unknown" || [value.instruction_adherence, value.confirmation_integrity].includes("INCONCLUSIVE");
  requireValue(value.task_verdict === (failed ? "FAIL" : unknown ? "INCONCLUSIVE" : "PASS"), "derived overall task");
}

function validateComparison(pair, requestedFreeze = null) {
  requireObject(pair, "comparison");
  requireValue(pair.schema_version === 3 && pair.report_type === "temporal_comparison", "version-3 comparison");
  requireValue(pair.controlled_demonstration === true, "controlled demonstration");
  requireString(pair.pair_id, "pair_id");
  requireString(pair.created_at, "created_at");
  validateFrozen(pair.frozen_inputs);
  if (requestedFreeze) requireValue(pair.frozen_inputs.freeze_id === requestedFreeze, "requested frozen inputs");
  requireValue(Array.isArray(pair.reports) && pair.reports.length === 2, "paired reports");
  requireValue(new Set(pair.reports.map((report) => report.implementation)).size === 2, "distinct implementations");
  for (const report of pair.reports) {
    requireValue(report.schema_version === 3 && report.report_type === "temporal_branch", "version-3 branch");
    requireEnum(report.implementation, ["faulty", "corrected"], "paired implementation");
    requireValue(report.freeze_id === pair.frozen_inputs.freeze_id, "branch frozen input binding");
    requireString(report.run_id, "branch run id");
    validateTemporalEvaluation(report.evaluation);
    requireObject(report.final_evidence, "independent evidence");
    if (report.final_evidence.booking !== null) validateBooking(report.final_evidence.booking, "independent final booking");
    for (const field of ["accepted_instructions", "actions", "journal"]) requireValue(Array.isArray(report.final_evidence[field]), field);
    for (const field of ["conversation", "revision_assessments", "action_assessments", "statement_assessments"]) requireValue(Array.isArray(report[field]), field);
    requireStringList(report.execution_errors, "execution errors");
    requireStringList(report.provenance.mocked_components, "mocked components");
    requireValue(report.provenance.customer_interpretation_id === pair.frozen_inputs.payload.customer_interpretation.interpretation_id, "shared customer interpretation identity");
    if (report.assistant_interpretation) validateSemanticResult(report.assistant_interpretation, "assistant_claims");
  }
  const accounting = pair.interpretation_accounting;
  requireObject(accounting, "interpretation accounting");
  requireValue(accounting.customer_interpretations_during_pair === 0 && accounting.shared_customer_interpretation_reused === true, "explicit shared interpretation reuse");
  for (const field of ["interpretations", "http_attempts", "http_responses", "successful_http_responses", "valid_interpretations"]) {
    requireValue(Number.isInteger(accounting.new_calls[field]) && accounting.new_calls[field] >= 0, `new calls.${field}`);
  }
  validateAPICall(accounting.original_freeze_call, "original freeze provenance");
}

function selectedTemporalScenario() {
  return temporalState.catalog?.scenarios.find((scenario) => scenario.id === temporalElements["temporal-scenario"].value);
}

function temporalNotice(message = "") {
  temporalElements["temporal-notice"].textContent = message;
  temporalElements["temporal-notice"].hidden = !message;
}

function syncTemporalControls() {
  const busy = temporalState.busy || state.inFlight !== null || window.agentBusy === true;
  temporalElements["temporal-scenario"].disabled = busy || !temporalState.catalog;
  temporalElements["freeze-button"].disabled = busy || !selectedTemporalScenario() || demoMode.enabled || !demoMode.ready;
  temporalElements["compare-button"].disabled = busy || !temporalState.frozen || temporalState.frozen.payload.validation_errors.length > 0 || demoMode.enabled || !demoMode.ready;
  temporalElements["download-comparison"].disabled = !temporalState.pair;
  temporalElements["saved-comparison"].disabled = busy || temporalState.saved.length === 0;
  temporalElements["open-comparison"].disabled = busy || temporalState.saved.length === 0 || !temporalElements["saved-comparison"].value;
  temporalElements["temporal-freeze-form"].setAttribute("aria-busy", String(busy));
  temporalElements["freeze-button"].lastElementChild.textContent = temporalState.frozen ? "Reinterpret & freeze" : "Interpret & freeze";
  for (const workflow of ["temporal", "immediate", "agent"]) temporalElements[`${workflow}-tab`].disabled = busy;
  if (window.syncAgentControls) window.syncAgentControls();
}

function showWorkflow(workflow) {
  if (demoMode.enabled && workflow !== "agent") return;
  if (temporalState.busy || state.inFlight || window.agentBusy) return;
  temporalState.workflow = workflow;
  for (const candidate of ["temporal", "immediate", "agent"]) {
    const active = candidate === workflow;
    temporalElements[`${candidate}-view`].hidden = !active;
    temporalElements[`${candidate}-tab`].setAttribute("aria-selected", String(active));
    temporalElements[`${candidate}-tab`].tabIndex = active ? 0 : -1;
  }
}

function renderSharedInputs(frozen = null) {
  const scenario = selectedTemporalScenario();
  const payload = frozen?.payload;
  const turns = payload ? payload.customer_turns.filter((turn) => turn.role === "customer") : (scenario?.customer_messages || []).map((text, index) => ({ id: `customer-${index + 1}`, text }));
  const interpretation = payload?.customer_interpretation;
  temporalElements["shared-instructions"].replaceChildren();
  for (const [index, turn] of turns.entries()) {
    const item = createElement("li", "shared-instruction");
    item.id = `temporal-customer-${index + 1}`;
    item.append(createElement("code", "turn-id", turn.id), createElement("p", "", turn.text));
    const extracted = interpretation?.data?.instructions?.find((candidate) => candidate.turn_id === turn.id);
    if (extracted) {
      const details = createElement("p", "extraction-detail", `${TEMPORAL_OPERATIONS[extracted.operation]} / ${formatTimestamp(extracted.requested_time, extracted.timezone)} / evidence: ${extracted.evidence_turn_ids.join(", ")}`);
      item.append(details);
    }
    temporalElements["shared-instructions"].append(item);
  }
  temporalElements["freeze-status"].textContent = interpretation ? `${interpretation.status} / not acceptance` : "Not interpreted";
  const provenance = temporalElements["freeze-provenance"];
  provenance.replaceChildren();
  provenance.hidden = !payload;
  temporalElements["freeze-details"].hidden = !payload;
  if (payload) {
    appendDefinition(provenance, "Frozen input digest", frozen.freeze_id, "mono-value");
    appendDefinition(provenance, "Customer interpretation", interpretation.interpretation_id, "mono-value");
    appendDefinition(provenance, "Interpretation source", `${interpretation.source === "live_meta" ? "Live Meta" : "Authored offline"} / ${interpretation.model || "No model call"}`);
    appendDefinition(provenance, "Original freeze HTTP attempts", String(interpretation.api_call.http_attempts));
    appendDefinition(provenance, "Frozen availability", payload.slot_available ? "Target slot available" : "Target slot unavailable");
    appendDefinition(provenance, "Initial booking", formatTimestamp(payload.initial_booking.starts_at, payload.initial_booking.timezone));
    if (payload.validation_errors.length) temporalNotice(payload.validation_errors.join(" "));
  }
  const steps = payload?.schedule_steps || temporalState.catalog?.plans[scenario?.plan] || [];
  temporalElements["schedule-steps"].replaceChildren(...steps.map((step) => createElement("li", "", step)));
  refreshIcons();
}

function eventDetail(event, timezone) {
  const data = event.data || {};
  const time = (value) => formatTimestamp(value, timezone, "time");
  switch (event.event) {
    case "initialized": return `Booking persisted at ${time(data.booking?.starts_at)}.`;
    case "instruction_received": return `${data.turn_id} received. No accepted revision is created by receipt.`;
    case "instruction_accepted": return `R${data.revision}: ${TEMPORAL_OPERATIONS[data.operation] || data.operation}; requested ${time(data.target_time)}. Source: ${data.turn_id}.`;
    case "action_queued": return `Bound to ${data.booking_reference}, ${data.operation}, ${time(data.target_time)}, accepted R${data.accepted_revision}.`;
    case "worker_preliminary_read": return `Observed R${data.observed_revision} outside the worker transaction.`;
    case "authorization_checked": return `Current R${data.checked_revision}; queued R${data.accepted_revision}; authorized: ${data.authorized ? "yes" : "no"}.`;
    case "action_committed": return `${time(data.before?.starts_at)} to ${time(data.after?.starts_at)}. ${data.reason}`;
    case "action_suppressed":
    case "action_rejected": return `${data.reason} Persisted time: ${time(data.after?.starts_at)}.`;
    case "withdrawal_too_late": return data.detail;
    case "assistant_statement": return `${data.turn_id} describes event #${data.describes_sequence}; independent readback through #${data.snapshot?.read_after_sequence}.`;
    default: return JSON.stringify(data);
  }
}

function temporalSection(title, icon) {
  const section = createElement("section", "temporal-section");
  const heading = createElement("h4");
  heading.append(createIcon(icon), document.createTextNode(title));
  section.append(heading);
  return section;
}

function renderTemporalBranch(report) {
  const branch = createElement("article", "temporal-branch");
  branch.dataset.implementation = report.implementation;
  branch.append(createElement("h3", "branch-heading", `${IMPLEMENTATION_LABELS[report.implementation]} execution`));
  const description = createElement("p", "branch-assessment", report.evaluation.explanation);
  branch.append(description);
  const binding = temporalSection("Accepted revisions and queued work", "git-pull-request");
  const accepted = createElement("ol", "accepted-revisions");
  for (const row of report.final_evidence.accepted_instructions) {
    const event = report.final_evidence.journal.find((event) => event.event === "instruction_accepted" && event.data.revision === row.revision);
    const item = createElement("li");
    item.append(createElement("strong", "", `R${row.revision}`), createElement("span", "", `${TEMPORAL_OPERATIONS[row.operation]} / ${formatTimestamp(row.target_time, row.timezone, "time")} / ${row.turn_id} / accepted #${event?.sequence ?? "unresolved"}`));
    accepted.append(item);
  }
  if (!report.final_evidence.accepted_instructions.length) accepted.append(createElement("li", "muted", "No accepted instruction."));
  binding.append(accepted);
  for (const action of report.final_evidence.actions) {
    const fields = createElement("dl", "queue-binding");
    appendDefinition(fields, "Queued action", action.action_id, "mono-value");
    appendDefinition(fields, "Authorizing revision", `R${action.accepted_revision}`);
    appendDefinition(fields, "Binding", `${action.booking_reference} / ${action.operation} / ${formatTimestamp(action.target_time, report.initial_booking.timezone, "time")}`);
    appendDefinition(fields, "Persisted action result", action.status);
    binding.append(fields);
  }
  branch.append(binding);

  const stateSection = temporalSection("Independent final booking", "database");
  const booking = createElement("div");
  renderBooking(booking, report.final_evidence.booking, { status: "unavailable" });
  stateSection.append(booking, createElement("p", "evidence-note", `${report.final_evidence.read_source || "Read evidence unavailable"}; journal watermark #${report.final_evidence.read_after_sequence ?? "unresolved"}.`));
  branch.append(stateSection);

  const journal = temporalSection("Durable execution order", "list-tree");
  const ordered = createElement("ol", "temporal-journal");
  for (const event of report.final_evidence.journal) {
    const item = createElement("li", "trace-item");
    item.dataset.event = event.event;
    item.append(createElement("span", "trace-sequence", String(event.sequence ?? "?")));
    const body = createElement("div", "trace-body");
    body.append(createElement("h5", "", EVENT_LABELS[event.event] || event.event), createElement("p", "", eventDetail(event, report.initial_booking.timezone)));
    body.append(createElement("code", "transaction-id", `Transaction ${event.transaction_id || "unresolved"}`));
    item.append(body);
    ordered.append(item);
  }
  journal.append(ordered);
  branch.append(journal);

  const statements = temporalSection("Assistant statements and evidence", "messages-square");
  for (const turn of report.conversation.slice(1).filter((turn) => turn.role === "assistant")) {
    const assessment = report.statement_assessments.find((item) => item.turn_id === turn.id);
    const item = createElement("div", "temporal-statement");
    const header = createElement("div", "turn-header");
    const badge = createElement("span");
    setBadge(badge, INTEGRITY_STYLES[assessment?.status || "INCONCLUSIVE"]);
    header.append(createElement("code", "turn-id", turn.id), badge);
    item.append(header, createElement("blockquote", "", turn.text));
    const claim = report.assistant_interpretation?.data?.claims?.find((claim) => claim.turn_id === turn.id);
    if (claim) item.append(createElement("p", "extraction-detail", `${claim.operation} / ${formatTimestamp(claim.claimed_booking?.starts_at, claim.claimed_booking?.timezone)} / citations: ${claim.evidence_turn_ids.join(", ")}`));
    item.append(createElement("p", "evidence-note", assessment ? `Describes event #${assessment.describes_sequence ?? "unresolved"}. ${assessment.detail}` : "Statement assessment unavailable."));
    statements.append(item);
  }
  branch.append(statements);

  const revisions = temporalSection("Request-scoped assessments", "list-checks");
  for (const item of report.revision_assessments) {
    const row = createElement("div", "revision-assessment");
    const names = { applicable_at_final_read: "Applicable at final read", completed_before_later_request: "Completed before later request", superseded_before_execution: "Superseded before execution", ordering_unresolved: "Ordering unresolved" };
    row.append(createElement("strong", "", `R${item.revision} / ${names[item.scope] || item.scope}`));
    if (item.evaluation) {
      const badge = createElement("span");
      setBadge(badge, INTEGRITY_STYLES[item.evaluation.task_verdict]);
      row.append(badge, createElement("p", "evidence-note", `Booking ${item.evaluation.booking_outcome}; adherence ${item.evaluation.instruction_adherence}; factual accuracy ${item.evaluation.confirmation_integrity}.`));
    }
    revisions.append(row);
  }
  branch.append(revisions);

  const provenance = temporalSection("Interpretation provenance", "fingerprint");
  const fields = createElement("dl", "queue-binding");
  const interpretation = report.assistant_interpretation;
  appendDefinition(fields, "Shared customer interpretation", `${report.provenance.customer_interpretation_id} / reused`);
  appendDefinition(fields, "Assistant interpretation", interpretation?.interpretation_id || "Not performed");
  appendDefinition(fields, "Source / model", interpretation ? `${interpretation.source} / ${interpretation.model || "No model call"}` : "No assistant interpretation");
  appendDefinition(fields, "HTTP attempts / responses / valid", interpretation ? `${interpretation.api_call.http_attempts} / ${interpretation.api_call.http_responses} / ${interpretation.status === "valid" ? 1 : 0}` : "0 / 0 / 0");
  appendDefinition(fields, "Mocked components", report.provenance.mocked_components.join(", ") || "None");
  provenance.append(fields);
  const errors = [...report.execution_errors, ...(interpretation?.errors || [])];
  if (errors.length) provenance.append(createElement("p", "tone-warning", errors.join(" ")));
  branch.append(provenance);
  return branch;
}

function renderComparison(pair) {
  validateComparison(pair);
  temporalState.pair = pair;
  temporalState.frozen = pair.frozen_inputs;
  const payload = pair.frozen_inputs.payload;
  const matching = temporalState.catalog?.scenarios.find((scenario) => scenario.plan === payload.schedule_plan && JSON.stringify(scenario.customer_messages) === JSON.stringify(payload.customer_turns.filter((turn) => turn.role === "customer").map((turn) => turn.text)));
  if (matching) temporalElements["temporal-scenario"].value = matching.id;
  renderSharedInputs(pair.frozen_inputs);
  temporalElements["comparison-caption"].textContent = `Pair ${pair.pair_id} / ${formatTimestamp(pair.created_at, "UTC")} / schema 3`;
  temporalElements["comparison-context"].hidden = true;
  const reports = ["faulty", "corrected"].map((mode) => pair.reports.find((report) => report.implementation === mode));
  const matrix = temporalElements["comparison-matrix"];
  matrix.replaceChildren();
  for (const [field, label, styles] of [
    ["task_verdict", "Overall task", INTEGRITY_STYLES], ["booking_outcome", "Booking outcome", OUTCOME_STYLES],
    ["instruction_adherence", "Instruction adherence", INTEGRITY_STYLES], ["confirmation_integrity", "Factual claim accuracy", INTEGRITY_STYLES],
  ]) {
    const row = createElement("tr");
    const heading = createElement("th", "", label);
    heading.scope = "row";
    row.append(heading);
    for (const report of reports) {
      const cell = createElement("td");
      cell.dataset.assessment = field;
      cell.dataset.implementation = report.implementation;
      const badge = createElement("span");
      setBadge(badge, styles[report.evaluation[field]]);
      cell.append(badge);
      row.append(cell);
    }
    matrix.append(row);
  }
  const stateRow = createElement("tr");
  const stateLabel = createElement("th", "", "Final persisted time");
  stateLabel.scope = "row";
  stateRow.append(stateLabel);
  for (const report of reports) stateRow.append(createElement("td", "mono", report.final_evidence.booking ? formatTimestamp(report.final_evidence.booking.starts_at, report.final_evidence.booking.timezone, "time") : "Unavailable"));
  matrix.append(stateRow);
  const calls = pair.interpretation_accounting.new_calls;
  temporalElements["comparison-accounting"].textContent = `This pair: customer interpretation reused, 0 new customer extractions; ${calls.http_attempts} HTTP attempts, ${calls.http_responses} responses, ${calls.valid_interpretations} valid assistant interpretations. Original freeze attempts: ${pair.interpretation_accounting.original_freeze_call.http_attempts} (not additional pair calls).`;
  temporalElements["comparison-branches"].replaceChildren(...reports.map(renderTemporalBranch));
  temporalElements["comparison-empty"].hidden = true;
  temporalElements["comparison-content"].hidden = false;
  refreshIcons();
  syncTemporalControls();
}

async function refreshSavedComparisons() {
  const payload = await requestJson("/api/temporal/reports");
  requireValue(Array.isArray(payload.reports), "saved comparisons");
  temporalState.saved = payload.reports;
  const select = temporalElements["saved-comparison"];
  select.replaceChildren();
  if (!payload.reports.length) select.append(createElement("option", "", "No saved comparisons"));
  for (const item of payload.reports) {
    const option = createElement("option", "", `${item.plan.replaceAll("_", " ")} / ${formatTimestamp(item.created_at, "UTC")} / ${item.pair_id.slice(0, 8)}`);
    option.value = item.pair_id;
    select.append(option);
  }
  if (temporalState.pair && payload.reports.some((item) => item.pair_id === temporalState.pair.pair_id)) select.value = temporalState.pair.pair_id;
  syncTemporalControls();
}

async function temporalAction(action) {
  if (temporalState.busy || state.inFlight || window.agentBusy) return;
  temporalState.busy = true;
  temporalNotice();
  syncTemporalControls();
  try {
    await action();
  } catch (error) {
    temporalNotice(error.message);
    temporalElements["temporal-status"].textContent = "Request failed. Existing comparison, if any, is unchanged.";
  } finally {
    temporalState.busy = false;
    syncTemporalControls();
  }
}

async function freezeTemporal(event) {
  event.preventDefault();
  const scenario = selectedTemporalScenario();
  if (!scenario) return;
  await temporalAction(async () => {
    temporalElements["temporal-status"].textContent = "Interpreting customer input and creating a new frozen snapshot.";
    const frozen = await requestJson("/api/temporal/freeze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenario.id }) });
    validateFrozen(frozen);
    temporalState.frozen = frozen;
    renderSharedInputs(frozen);
    temporalElements["temporal-status"].textContent = frozen.payload.validation_errors.length ? "Customer interpretation did not validate. No instruction has been accepted." : "Customer interpretation frozen. No instruction has yet been accepted into a replay.";
    if (temporalState.pair) {
      temporalElements["comparison-context"].hidden = false;
      temporalElements["comparison-context"].textContent = "New frozen inputs selected. The previous comparison remains below.";
    }
  });
}

async function compareTemporal() {
  const frozen = temporalState.frozen;
  if (!frozen || frozen.payload.validation_errors.length) return;
  await temporalAction(async () => {
    temporalElements["temporal-status"].textContent = "Executing both workers with the frozen customer interpretation; interpreting each response separately.";
    const pair = await requestJson("/api/temporal/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ freeze_id: frozen.freeze_id }) });
    validateComparison(pair, frozen.freeze_id);
    renderComparison(pair);
    temporalElements["temporal-status"].textContent = `Comparison recorded. ${pair.reports.map((report) => `${IMPLEMENTATION_LABELS[report.implementation]} task ${report.evaluation.task_verdict}`).join("; ")}.`;
    await refreshSavedComparisons();
  });
}

async function openSavedComparison(pairId = temporalElements["saved-comparison"].value) {
  if (!pairId) return;
  await temporalAction(async () => {
    const pair = await requestJson(`/api/temporal/reports/${encodeURIComponent(pairId)}`);
    renderComparison(pair);
    temporalElements["temporal-status"].textContent = "Saved comparison opened. No new model call was made.";
  });
}

function downloadComparison() {
  if (!temporalState.pair) return;
  const blob = new Blob([JSON.stringify(temporalState.pair, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = createElement("a");
  link.href = url;
  link.download = `intent-replay-temporal-${temporalState.pair.pair_id.replace(/[^a-zA-Z0-9-]/g, "")}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function loadTemporal() {
  await temporalAction(async () => {
    const catalog = await requestJson("/api/temporal/scenarios");
    requireValue(Array.isArray(catalog.scenarios), "temporal scenarios");
    validateBooking(catalog.initial_booking, "temporal initial booking");
    temporalState.catalog = catalog;
    temporalElements["temporal-scenario"].replaceChildren(...catalog.scenarios.map((scenario) => {
      const option = createElement("option", "", scenario.name);
      option.value = scenario.id;
      return option;
    }));
    renderSharedInputs();
    await refreshSavedComparisons();
    temporalElements["temporal-status"].textContent = "Ready. No customer interpretation has been requested.";
  });
  const requested = new URLSearchParams(location.search).get("comparison");
  if (requested && temporalState.saved.some((item) => item.pair_id === requested)) await openSavedComparison(requested);
}

temporalElements["temporal-freeze-form"].addEventListener("submit", freezeTemporal);
temporalElements["compare-button"].addEventListener("click", compareTemporal);
temporalElements["download-comparison"].addEventListener("click", downloadComparison);
temporalElements["open-comparison"].addEventListener("click", () => openSavedComparison());
temporalElements["saved-comparison"].addEventListener("change", syncTemporalControls);
temporalElements["temporal-scenario"].addEventListener("change", () => {
  temporalState.frozen = null;
  renderSharedInputs();
  temporalNotice();
  temporalElements["temporal-status"].textContent = "Scheduling control changed. Customer input is not frozen.";
  if (temporalState.pair) {
    temporalElements["comparison-context"].hidden = false;
    temporalElements["comparison-context"].textContent = "Selection changed. The recorded comparison remains below.";
  }
  syncTemporalControls();
});
for (const workflow of ["temporal", "immediate", "agent"]) {
  temporalElements[`${workflow}-tab`].addEventListener("click", () => showWorkflow(workflow));
  temporalElements[`${workflow}-tab`].addEventListener("keydown", (event) => {
    if (demoMode.enabled) return;
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const workflows = ["temporal", "immediate", "agent"];
      const index = workflows.indexOf(workflow);
      const next = event.key === "Home" ? workflows[0] : event.key === "End" ? workflows.at(-1) : workflows[(index + (event.key === "ArrowRight" ? 1 : -1) + workflows.length) % workflows.length];
      showWorkflow(next);
      temporalElements[`${next}-tab`].focus();
    }
  });
}
demoReady.then(loadTemporal).catch(error => temporalNotice(error.message));
