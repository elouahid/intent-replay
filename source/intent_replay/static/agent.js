"use strict";

const agentState = {catalog: null, frozen: null, report: null, busy: false, saved: []};
const agentElements = Object.fromEntries([
  "agent-freeze-form", "agent-scenario", "agent-freeze", "agent-run", "agent-status", "agent-notice",
  "agent-saved", "agent-open", "agent-inputs", "agent-freeze-provenance", "agent-caption", "agent-context",
  "agent-empty", "agent-report", "agent-download",
].map((id) => [id, document.getElementById(id)]));

function syncAgentControls() {
  const busy = agentState.busy || temporalState.busy || state.inFlight !== null;
  agentElements["agent-scenario"].disabled = busy || !agentState.catalog;
  agentElements["agent-freeze"].disabled = busy || !agentState.catalog || demoMode.enabled || !demoMode.ready;
  agentElements["agent-freeze"].textContent = agentState.frozen ? "Reinterpret & freeze" : "Interpret & freeze";
  agentElements["agent-run"].disabled = busy || !agentState.frozen || agentState.frozen.payload.validation_errors.length > 0 || demoMode.enabled || !demoMode.ready;
  agentElements["agent-saved"].disabled = busy || !agentState.saved.length;
  agentElements["agent-open"].disabled = busy || !agentState.saved.length || !agentElements["agent-saved"].value;
  agentElements["agent-download"].disabled = !agentState.report;
  agentElements["agent-freeze-form"].setAttribute("aria-busy", String(busy));
  for (const entry of demoMode.examples) document.getElementById(`demo-${entry.key}`).disabled = busy;
}

function agentContext(message) {
  agentElements["agent-context"].textContent = message;
  agentElements["agent-context"].hidden = !message;
}

function renderAgentInputs() {
  const scenario = agentState.catalog?.scenarios.find((item) => item.id === agentElements["agent-scenario"].value);
  const frozen = agentState.frozen || agentState.report?.frozen_inputs;
  const turns = frozen?.payload.customer_turns || (scenario?.customer_messages || []).map((text, index) => ({id: `customer-${index + 1}`, role: "customer", text}));
  agentElements["agent-inputs"].replaceChildren(...turns.filter((turn) => turn.role === "customer").map((turn) => {
    const item = createElement("li", "shared-instruction");
    item.append(createElement("code", "turn-id", turn.id), createElement("p", "", turn.text));
    return item;
  }));
  const list = agentElements["agent-freeze-provenance"];
  list.replaceChildren();
  if (frozen) {
    appendDefinition(list, "Frozen digest", frozen.freeze_id, "mono-value");
    appendDefinition(list, "Customer interpretation", `${frozen.payload.customer_interpretation.status} / ${frozen.payload.customer_interpretation.source}`);
    appendDefinition(list, "Original freeze HTTP attempts", String(frozen.payload.customer_interpretation.api_call.http_attempts));
    appendDefinition(list, "Scheduling plan", frozen.payload.schedule_plan.replaceAll("_", " "));
  }
  syncAgentControls();
}

function validateAgentReport(report, freezeId = null) {
  requireObject(report, "agent comparison");
  requireValue([4, 5, 6].includes(report.schema_version) && report.report_type === "agent_comparison", "version-4, version-5 or version-6 agent comparison");
  requireValue(typeof report.pair_id === "string" && /^[a-f0-9]{32}$/.test(report.pair_id), "agent pair id");
  validateFrozen(report.frozen_inputs);
  requireValue(!freezeId || report.frozen_inputs.freeze_id === freezeId, "agent frozen input binding");
  requireValue(Array.isArray(report.reports) && report.reports.length === 2, "agent comparison branches");
  requireValue(new Set(report.reports.map((branch) => branch.implementation)).size === 2, "distinct agent workers");
  for (const branch of report.reports) {
    requireValue(branch.schema_version === report.schema_version && branch.report_type === "agent_branch", "agent branch schema binding");
    requireEnum(branch.implementation, ["faulty", "corrected"], "agent worker");
    validateTemporalEvaluation(branch.evaluation);
    requireObject(branch.agent_execution, "agent execution");
    requireObject(branch.provenance, "agent provenance");
    requireObject(branch.final_evidence, "agent final evidence");
    if (branch.final_evidence.booking) validateBooking(branch.final_evidence.booking, "agent final booking");
    for (const key of ["conversation", "execution_errors", "statement_assessments", "action_assessments", "revision_assessments"]) requireValue(Array.isArray(branch[key]), `agent ${key}`);
    requireValue(Array.isArray(branch.agent_execution.tool_calls), "agent tool calls");
    if (branch.assistant_interpretation) {
      if (report.schema_version === 4) validateSemanticResult(branch.assistant_interpretation, "assistant_claims");
      else validateAgentClaims(branch.assistant_interpretation);
    }
    if (report.schema_version >= 5) {
      requireObject(branch.claim_evaluation, "agent claim evaluation");
      requireObject(branch.claim_evaluation.coverage, "agent claim coverage");
      requireValue(Array.isArray(branch.claim_evaluation.statement_assessments), "agent claim assessments");
    }
  }
}

function validateAgentClaims(result) {
  requireObject(result, "agent assistant interpretation");
  requireValue(result.purpose === "assistant_claims", "agent claim purpose");
  requireEnum(result.status, ["valid", "invalid", "ambiguous", "error"], "agent claim status");
  requireEnum(result.source, ["live_meta", "authored_test", "offline_revalidation"], "agent claim source");
  for (const field of ["interpretation_id", "input_sha256"]) requireString(result[field], `agent claims.${field}`);
  requireStringList(result.errors, "agent claim errors");
  validateAPICall(result.api_call, "agent claim API call");
  requireObject(result.coverage, "agent extraction coverage");
  requireValue(typeof result.coverage.complete === "boolean", "agent extraction completion");
  if (result.diagnostics) requireObject(result.diagnostics, "public extraction diagnostics");
  if (result.data !== null) {
    requireObject(result.data, "agent claims data");
    requireValue(Array.isArray(result.data.messages), "agent claim messages");
    for (const message of result.data.messages) {
      requireString(message.turn_id, "agent claim message turn");
      requireValue(Array.isArray(message.segments), "agent claim segments");
      for (const segment of message.segments) {
        requireString(segment.text, "agent claim segment text");
        if (result.contract_version === "agent-language-v1") {
          requireValue(Array.isArray(segment.claims) && segment.claims.length > 0, "language propositions");
          for (const claim of segment.claims) {
            requireString(claim.id, "proposition identity");
            requireEnum(claim.kind, ["plan", "acknowledgement", "current_state", "action", "event_order", "request_summary", "inspection", "unsupported"], "language claim kind");
          }
        } else {
          requireEnum(segment.kind, ["plan", "acknowledgement", "current_state", "action", "event_order", "unsupported"], "agent claim kind");
          requireStringList(segment.evidence_turn_ids, "agent claim evidence turn IDs");
        }
      }
    }
  }
}

function agentJSONSection(title, value) {
  const details = createElement("details", "agent-detail");
  details.append(createElement("summary", "", title), createElement("pre", "agent-json", JSON.stringify(value, null, 2)));
  return details;
}

function agentWithdrawalOrder(report, frozen) {
  const withdrawal = frozen.payload.customer_interpretation.data?.instructions.find((item) => item.operation === "withdraw_pending");
  if (!withdrawal) return frozen.payload.schedule_plan === "no_withdrawal" ? "No withdrawal in this comparison." : "An extracted withdrawal instruction is unavailable; inspect the saved customer request.";
  const journal = report.final_evidence.journal || [];
  const received = journal.find((event) => event.event === "instruction_received" && event.data?.turn_id === withdrawal.turn_id);
  const accepted = journal.find((event) => event.event === "instruction_accepted" && event.data?.turn_id === withdrawal.turn_id);
  const guard = journal.find((event) => event.event === "authorization_checked");
  const action = journal.find((event) => ["action_committed", "action_suppressed", "action_rejected"].includes(event.event));
  const values = [[received, "received"], [accepted, "accepted"], [guard, "authorization check"],
    [action, action ? EVENT_LABELS[action.event].toLowerCase() : "action"]]
    .filter(([event]) => event).sort(([left], [right]) => left.sequence - right.sequence)
    .map(([event, label]) => `${label} #${event.sequence}`);
  return values.length ? values.join(" → ") + (accepted ? "." : ". Withdrawal acceptance is not recorded.") : "Withdrawal ordering is unavailable in the recorded journal.";
}

function agentShortReason(report) {
  const evidence = report.final_evidence || {};
  const actions = evidence.actions || [];
  const journal = evidence.journal || [];
  if (actions.length !== 1 || !evidence.booking) return "Recorded action or independent final booking evidence is unavailable. Inspect the saved checks.";
  const action = actions[0];
  const assessment = (report.action_assessments || []).find(item => item.action_id === action.action_id);
  const decision = journal.find(item => item.sequence === action.decision_sequence && item.data?.action_id === action.action_id);
  const guard = journal.find(item => item.event === "authorization_checked" && item.data?.action_id === action.action_id);
  if (!assessment?.atomic_evidence || !decision || !guard || guard.transaction_id !== decision.transaction_id || guard.sequence >= decision.sequence) {
    return assessment?.detail || "Recorded atomic authorization evidence is incomplete. Inspect the saved action assessment.";
  }
  if (decision.data?.after?.starts_at !== evidence.booking.starts_at) return "Recorded action and final booking differ; inspect the saved state and journal.";
  const zone = evidence.booking.timezone;
  const final = formatTimestamp(evidence.booking.starts_at, zone, "time");
  const initial = report.initial_booking?.starts_at ? formatTimestamp(report.initial_booking.starts_at, zone, "time") : "the original time";
  const withdrawal = journal.find(item => item.event === "instruction_accepted" && item.data?.operation === "withdraw_pending" && item.data?.revision === guard.data.checked_revision && item.sequence < guard.sequence);
  if (guard.data.authorized === false && decision.event === "action_committed") {
    return withdrawal
      ? `The withdrawal was accepted before execution (#${withdrawal.sequence}), but the queued change still moved the booking to ${final}.`
      : `The queued change was not authorized at check #${guard.sequence}, but it still committed. The final booking is ${final}.`;
  }
  if (guard.data.authorized === false && decision.event === "action_suppressed") {
    const retained = decision.data.before?.starts_at === evidence.booking.starts_at;
    return `The transaction detected a newer instruction and suppressed the queued change. The booking ${retained ? "stayed at" : "is now"} ${final}.`;
  }
  if (guard.data.authorized === true && decision.event === "action_committed") {
    return `The queued change was authorized and committed. The booking moved from ${initial} to ${final}.`;
  }
  return assessment.detail || `Recorded decision: ${decision.event.replaceAll("_", " ")}. Final booking: ${final}.`;
}

function renderAgentSummary(report) {
  const section = temporalSection("Request and recorded result", "clipboard-check");
  section.id = "agent-result-summary";
  if (report.reports[0].initial_booking) {
    const initial = report.reports[0].initial_booking;
    section.append(createElement("p", "demo-initial", `Initial booking: ${formatTimestamp(initial.starts_at, initial.timezone, "time")} · ${initial.reference} · ${initial.timezone}.`));
  }
  const requests = createElement("ol", "shared-instruction-list agent-saved-requests");
  for (const turn of report.frozen_inputs.payload.customer_turns.filter((item) => item.role === "customer")) {
    const item = createElement("li", "shared-instruction");
    item.append(createElement("code", "turn-id", turn.id), createElement("p", "", turn.text));
    requests.append(item);
  }
  section.append(requests);
  const proposal = report.captured_proposal;
  if (proposal) {
    const shared = createElement("div", "demo-proposal");
    shared.append(createElement("strong", "", "Same captured proposal in both workers"),
      createElement("code", "", `${proposal.name}(${proposal.raw_arguments || proposal.arguments})`),
      createElement("p", "evidence-note", `Source: ${proposal.source}. Originating accepted revision: ${proposal.originating_revision}. Original arguments are preserved below.`));
    section.append(shared);
  }
  const ordered = ["faulty", "corrected"].map((implementation) => report.reports.find((branch) => branch.implementation === implementation));
  const table = createElement("table", "comparison-table agent-summary-table");
  const head = createElement("thead"), header = createElement("tr");
  for (const label of ["Recorded assessment", "Faulty worker", "Guarded worker"]) {
    const th = createElement("th", "", label);
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = createElement("tbody");
  const rows = [
    ["final_time", "Final booking", (branch) => branch.final_evidence.booking ? `${formatTimestamp(branch.final_evidence.booking.starts_at, branch.final_evidence.booking.timezone, "time")} · ${branch.final_evidence.booking.timezone}` : "Unavailable"],
    ["booking_outcome", "Booking outcome", (branch) => branch.evaluation.booking_outcome],
    ["instruction_adherence", "Instruction adherence", (branch) => branch.evaluation.instruction_adherence],
    ["confirmation_integrity", "Factual claim accuracy", (branch) => branch.evaluation.confirmation_integrity],
    ["task_verdict", "Overall task", (branch) => branch.evaluation.task_verdict],
    ["withdrawal_order", "Backend event order", (branch) => agentWithdrawalOrder(branch, report.frozen_inputs)],
    ["reason", "Execution explanation", agentShortReason],
    ["claim_note", "Factual-assessment limit", branch => `${branch.evaluation.confirmation_integrity}. Full-response factual assessment is experimental; inspect the claim diagnostics.`],
  ];
  for (const [key, label, value] of rows) {
    const row = createElement("tr"), th = createElement("th", "", label);
    th.scope = "row";
    row.append(th);
    for (const branch of ordered) {
      const cell = createElement("td", "", value(branch));
      cell.dataset.agentSummary = key;
      cell.dataset.implementation = branch.implementation;
      if (["booking_outcome", "instruction_adherence", "confirmation_integrity", "task_verdict"].includes(key)) {
        cell.replaceChildren();
        const badge = createElement("span", "status-badge");
        setBadge(badge, (key === "booking_outcome" ? OUTCOME_STYLES : INTEGRITY_STYLES)[branch.evaluation[key]]);
        cell.append(badge);
      }
      row.append(cell);
    }
    body.append(row);
  }
  table.append(head, body);
  section.append(table, createElement("p", "evidence-note", "Event numbers come from the persisted backend journal. Conversation delivery order is separate. A correct booking can still have an inaccurate explanation."));
  return section;
}

function renderAgentExtraction(report) {
  const section = temporalSection("Extraction and assertion coverage", "list-checks");
  section.classList.add("agent-extraction");
  const result = report.assistant_interpretation;
  const coverage = report.claim_evaluation?.coverage || result?.coverage;
  const failure = result?.diagnostics?.failure_kind;
  section.append(createElement("p", "agent-extraction-status", result ? `Extraction: ${result.status}${failure ? ` / ${failure}` : ""}. Source: ${result.source}.` : "Extraction was not recorded; factual coverage is unavailable."));
  if (coverage) {
    section.append(createElement("p", "agent-coverage", `${coverage.complete ? "Complete" : "Incomplete"} recorded coverage: ${coverage.covered_messages ?? "unknown"} of ${coverage.message_count ?? "unknown"} messages; ${coverage.segment_count ?? "unknown"} assertions or non-factual segments; ${coverage.unsupported_segments ?? "unknown"} unsupported.`));
  } else section.append(createElement("p", "agent-coverage evidence-note", "Historical schema 4: message and assertion coverage diagnostics were not recorded. This saved report has not been reinterpreted."));
  if (report.schema_version === 6) {
    const stage = report.claim_evaluation;
    const semantic = stage.semantic_support;
    section.append(createElement("p", "agent-provider-stage", `Provider completion: extraction ${stage.provider_completion.extraction || "unavailable"}; semantic check ${stage.provider_completion.semantic_check || "unavailable"}.`));
    section.append(createElement("p", "agent-structural-stage", `Structural coverage: ${coverage.complete ? "complete" : "incomplete"}. This checks copied messages and text.`));
    section.append(createElement("p", "agent-semantic-stage", `Semantic accounting: ${semantic.complete_accounting ? "complete" : "incomplete"}; ${semantic.supported} supported interpretations; ${semantic.unresolved} unresolved propositions. Model agreement is probabilistic.`));
    section.append(createElement("p", "agent-evidence-stage", `Deterministic evidence result: ${report.evaluation.confirmation_integrity}. Overall task: ${report.evaluation.task_verdict}.`));
    for (const error of semantic.errors) section.append(createElement("p", "agent-extraction-error", error));
    section.append(agentJSONSection("Semantic fidelity check, exact input and public response", result?.semantic_check));
    if (report.source_report) section.append(agentJSONSection("Original actor report and extraction association", {source: report.source_report, original: report.original_assistant_interpretation, original_evaluation: report.original_evaluation}));
  }
  const errors = [...new Set([...(result?.errors || []), ...(coverage?.errors || [])])];
  for (const error of errors) section.append(createElement("p", "agent-extraction-error", error));
  if (result?.diagnostics) section.append(agentJSONSection("Public response metadata, partial output, and extraction settings", result.diagnostics));
  return section;
}

function renderAgentBranch(report) {
  const container = createElement("article", "temporal-branch agent-branch");
  container.dataset.implementation = report.implementation;
  container.append(createElement("h3", "branch-heading", `${report.implementation === "corrected" ? "Guarded" : "Faulty"} worker / recorded actor continuation`));
  container.append(createElement("p", "controlled-label", report.implementation === "faulty" ? "Controlled backend defect: obsolete execution allowed" : "Transactional revision guard enabled"));
  const verdicts = createElement("div", "verdict-grid");
  for (const [key, label, styles] of [
    ["task_verdict", "Overall task", INTEGRITY_STYLES], ["booking_outcome", "Booking outcome", OUTCOME_STYLES],
    ["instruction_adherence", "Instruction adherence", INTEGRITY_STYLES], ["confirmation_integrity", "Factual claim accuracy", INTEGRITY_STYLES],
  ]) {
    const cell = createElement("div", "verdict-cell");
    const badge = createElement("p", "verdict-value");
    badge.dataset.agentAssessment = key;
    badge.dataset.implementation = report.implementation;
    setBadge(badge, styles[report.evaluation[key]], true);
    cell.append(createElement("h3", "eyebrow", label), badge);
    verdicts.append(cell);
  }
  container.append(verdicts, createElement("p", "branch-assessment", agentShortReason(report)));
  const diagnostics = createElement("details", "agent-detail agent-language-diagnostics");
  diagnostics.append(createElement("summary", "", `Experimental factual assessment: ${report.evaluation.confirmation_integrity} — inspect language diagnostics`),
    createElement("p", "evidence-note", report.evaluation.explanation), renderAgentExtraction(report));
  container.append(diagnostics);
  if (report.execution_errors.length) {
    const errors = temporalSection("Execution errors", "circle-alert");
    errors.classList.add("agent-execution-errors");
    for (const error of report.execution_errors) errors.append(createElement("p", "", error));
    container.append(errors);
  }
  const booking = temporalSection("Independent final booking", "database");
  const bookingFields = createElement("div");
  renderBooking(bookingFields, report.final_evidence.booking, {status: "unavailable"});
  booking.append(bookingFields, createElement("p", "evidence-note", `${report.final_evidence.read_source || "Read source unavailable"}; journal watermark ${report.final_evidence.read_after_sequence ?? "unavailable"}.`));
  container.append(booking);
  const turns = temporalSection("Conversation and generated assistant statements", "messages-square");
  for (const turn of report.conversation) {
    const item = createElement("div", "temporal-statement");
    item.dataset.agentTurn = turn.id;
    item.append(createElement("code", "turn-id", `${turn.role} / ${turn.id}`), createElement("blockquote", "", turn.text));
    const assessments = report.statement_assessments.filter((value) => value.turn_id === turn.id);
    const findings = createElement("details", "agent-detail agent-claim-diagnostics");
    findings.append(createElement("summary", "", `Per-claim evidence and language diagnostics (${assessments.length})`));
    for (const assessment of assessments) {
      const finding = createElement("div", "agent-claim-assessment");
      finding.dataset.agentClaimStatus = assessment.status;
      if (assessment.text) finding.append(createElement("q", "agent-claim-text", assessment.text));
      finding.append(createElement("p", "", `${assessment.status}${assessment.kind ? ` / ${assessment.kind.replaceAll("_", " ")}` : ""}: ${assessment.detail}`));
      findings.append(finding);
    }
    if (assessments.length) item.append(findings);
    if (!assessments.length && turn.role === "assistant" && turn.id.startsWith("actor-")) item.append(createElement("p", "agent-extraction-error", "No assertion assessment was recorded for this actor message."));
    turns.append(item);
  }
  container.append(turns);
  const tools = temporalSection("Agent tool calls and results", "wrench");
  tools.classList.add("agent-tool-evidence");
  if (!report.agent_execution.tool_calls.length) tools.append(createElement("p", "", "No tool call was executed."));
  for (const [index, call] of report.agent_execution.tool_calls.entries()) {
    tools.append(agentJSONSection(`Tool ${index + 1}: ${call.name || call.tool || "recorded call"}`, call));
  }
  container.append(tools);
  const chronology = temporalSection("Durable acceptance and execution order", "list-tree");
  const events = createElement("ol", "temporal-journal");
  for (const event of report.final_evidence.journal || []) {
    if (!["instruction_received", "instruction_accepted", "action_queued", "worker_preliminary_read", "authorization_checked", "action_committed", "action_suppressed", "action_rejected", "withdrawal_too_late"].includes(event.event)) continue;
    const item = createElement("li", "trace-item");
    const body = createElement("div", "trace-body");
    body.append(createElement("h5", "", EVENT_LABELS[event.event] || event.event), createElement("p", "", eventDetail(event, report.final_evidence.booking?.timezone || "UTC")));
    body.append(createElement("code", "transaction-id", `Transaction ${event.transaction_id || "unresolved"}`));
    item.append(createElement("span", "trace-sequence", String(event.sequence)), body);
    events.append(item);
  }
  if (!events.children.length) events.append(createElement("li", "", "No accepted or executed action recorded."));
  chronology.append(events);
  const chronologyDetails = createElement("details", "agent-detail");
  chronologyDetails.append(createElement("summary", "", "Inspect durable acceptance and execution order"), chronology);
  container.append(chronologyDetails);
  const provenance = temporalSection("Generation, interpretation, and provenance", "fingerprint");
    provenance.append(createElement("p", "comparison-accounting", `Historical actor: ${report.agent_execution.status}; model: ${report.agent_execution.model || "not called"}; recorded generation HTTP attempts: ${report.agent_execution.http_attempts ?? 0}. Recorded assistant interpretation attempts: ${report.assistant_interpretation?.api_call?.http_attempts ?? 0}. Recorded semantic-check attempts: ${report.assistant_interpretation?.semantic_check?.api_call?.http_attempts ?? 0}. Opening this saved report makes no new requests to a model.`));
  provenance.append(agentJSONSection("Agent execution accounting", report.agent_execution), agentJSONSection("Assistant claim interpretation", report.assistant_interpretation), agentJSONSection("Provenance and limitations", report.provenance));
  container.append(provenance, agentJSONSection("Durable actions, revisions, and journal", report.final_evidence), agentJSONSection("Independent checks and scoped assessments", {evaluation: report.evaluation, actions: report.action_assessments, revisions: report.revision_assessments, statements: report.statement_assessments}));
  return container;
}

function renderAgentReport(report) {
  validateAgentReport(report);
  const container = agentElements["agent-report"];
  container.replaceChildren();
  agentElements["agent-caption"].textContent = report.provenance?.mode === "recorded_saved_comparison"
    ? `${report.provenance.title} / historical Meta capture / one proposal, two isolated worker replays`
    : `${report.pair_id} / ${report.frozen_inputs.payload.schedule_plan.replaceAll("_", " ")} / one captured proposal, two isolated worker replays`;
  const mode = report.capture?.agent_execution?.source || report.provenance?.agent_generation || "See recorded provenance";
  container.append(createElement("p", "controlled-label", report.provenance?.mode === "recorded_saved_comparison"
    ? "Recorded Meta tool call — saved comparison — no new API requests"
    : `Recorded evidence: ${mode} / report schema ${report.schema_version}`));
  container.append(createElement("p", "section-description", "The captured proposal was replayed in two isolated workers. A controlled backend defect causes the faulty execution. Each worker's actual model messages and independent database evidence are preserved."));
  container.append(createElement("p", "agent-language-note", "Full-response factual assessment is experimental. The language usability trial failed: all eight conversation assessments stayed INCONCLUSIVE. Factual accuracy and the saved overall task verdict remain visible below."));
  const proposal = agentJSONSection("Shared captured proposal, raw arguments, and actor-visible prefix", report.captured_proposal);
  proposal.id = "agent-proposal";
  container.append(renderAgentSummary(report));
  const branches = createElement("div", "comparison-branches");
  branches.append(...["faulty", "corrected"].map((implementation) => renderAgentBranch(report.reports.find((branch) => branch.implementation === implementation))));
  container.append(branches, proposal, agentJSONSection("Capture messages and response metadata", report.capture), agentJSONSection("Frozen customer input and original extraction", report.frozen_inputs), agentJSONSection("Complete accounting by role", report.agent_accounting), agentJSONSection("Comparison provenance", report.provenance));
  agentState.report = report;
  for (const entry of demoMode.examples) document.getElementById(`demo-${entry.key}`).setAttribute("aria-pressed", String(entry.run_id === report.pair_id));
  renderAgentInputs();
  agentElements["agent-empty"].hidden = true;
  container.hidden = false;
  agentContext("");
  syncAgentControls();
  refreshIcons();
}

async function refreshAgentReports() {
  const result = await requestJson("/api/agent/reports");
  requireValue(Array.isArray(result.reports), "saved agent reports");
  agentState.saved = result.reports;
  const select = agentElements["agent-saved"];
  select.replaceChildren(...result.reports.map((report) => {
    const example = demoMode.examples.find(entry => entry.run_id === (report.pair_id || report.run_id));
    const option = createElement("option", "", example?.label || `${report.created_at || "Saved"} / ${(report.pair_id || report.run_id).slice(0, 8)}`);
    option.value = report.pair_id || report.run_id;
    return option;
  }));
  if (!result.reports.length) select.append(createElement("option", "", "No saved reports"));
  if (agentState.report && result.reports.some((item) => (item.pair_id || item.run_id) === agentState.report.pair_id)) select.value = agentState.report.pair_id;
  syncAgentControls();
}

async function agentAction(action) {
  if (agentState.busy || temporalState.busy || state.inFlight) return;
  agentState.busy = window.agentBusy = true;
  agentElements["agent-notice"].hidden = true;
  if (agentState.report) agentContext("Request in progress. The recorded report remains visible below.");
  syncControls();
  try {
    await action();
  } catch (error) {
    agentElements["agent-notice"].textContent = error.message;
    agentElements["agent-notice"].hidden = false;
    agentElements["agent-status"].textContent = "Request failed. Existing report, if any, is unchanged.";
    if (agentState.report) agentContext("Latest request failed. The recorded report remains visible below.");
  } finally {
    agentState.busy = window.agentBusy = false;
    syncControls();
  }
}

agentElements["agent-freeze-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  agentAction(async () => {
    agentElements["agent-status"].textContent = "Interpreting and freezing customer input; no agent execution yet.";
    const frozen = await requestJson("/api/temporal/freeze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({scenario_id: agentElements["agent-scenario"].value})});
    validateFrozen(frozen);
    agentState.frozen = frozen;
    renderAgentInputs();
    agentElements["agent-status"].textContent = frozen.payload.validation_errors.length ? frozen.payload.validation_errors.join(" ") : "Frozen input ready. Running the agent makes new model calls (at most 16 HTTP attempts per comparison).";
    if (agentState.report) agentContext("New frozen inputs selected. The recorded report remains below.");
  });
});
agentElements["agent-run"].addEventListener("click", () => agentAction(async () => {
  const freezeId = agentState.frozen.freeze_id;
  agentElements["agent-status"].textContent = "Running tool-using agent and independently evaluating its generated statements.";
  const report = await requestJson("/api/agent/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({freeze_id: freezeId})});
  validateAgentReport(report, freezeId);
  renderAgentReport(report);
  agentElements["agent-status"].textContent = `Agent comparison recorded. ${report.reports.map((branch) => `${IMPLEMENTATION_LABELS[branch.implementation]} task ${branch.evaluation.task_verdict}`).join("; ")}.`;
  await refreshAgentReports();
}));
agentElements["agent-open"].addEventListener("click", () => agentAction(async () => {
  renderAgentReport(await requestJson(`/api/agent/reports/${encodeURIComponent(agentElements["agent-saved"].value)}`));
  agentElements["agent-status"].textContent = "Saved agent report opened. No model call was made.";
}));
agentElements["agent-saved"].addEventListener("change", syncAgentControls);
agentElements["agent-scenario"].addEventListener("change", () => {
  agentState.frozen = null;
  renderAgentInputs();
  agentElements["agent-status"].textContent = "Selection changed. Interpret and freeze before running the agent.";
  if (agentState.report) agentContext("Selection changed. The recorded report remains below with its original inputs and labels.");
});
agentElements["agent-download"].addEventListener("click", () => {
  if (!agentState.report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(agentState.report, null, 2)], {type: "application/json;charset=utf-8"}));
  const link = createElement("a");
  link.href = url;
  link.download = `intent-replay-agent-${agentState.report.pair_id}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function loadAgent() {
  try {
    await demoReady;
    document.body.dataset.demo = demoMode.enabled ? "recorded" : "developer";
    document.getElementById("agent-saved-disclosure").open = !demoMode.enabled;
    document.getElementById("demo-mode-label").textContent = demoMode.enabled ? demoMode.notice : "Developer workflow — recorded and optional live evidence";
    document.getElementById("demo-mode-detail").textContent = demoMode.enabled
      ? "No key needed. These two historical comparisons open automatically as saved evidence. Live actions are disabled; all API writes are blocked."
      : "Live developer controls are available. The no-key recorded journey uses: python -m intent_replay --demo.";
    document.getElementById("demo-choices").hidden = !demoMode.enabled;
    agentElements["agent-freeze-form"].hidden = demoMode.enabled;
    document.getElementById("agent-mode-label").textContent = demoMode.enabled ? "Recorded evidence · read-only" : "Developer workflow";
    for (const workflow of ["temporal", "immediate"]) document.getElementById(`${workflow}-tab`).hidden = demoMode.enabled;
    for (const entry of demoMode.examples) {
      document.getElementById(`demo-${entry.key}`).addEventListener("click", () => agentAction(() => openRecordedExample(entry)));
    }
    agentState.catalog = await requestJson("/api/temporal/scenarios");
    agentElements["agent-scenario"].replaceChildren(...agentState.catalog.scenarios.map((scenario) => {
      const option = createElement("option", "", scenario.name);
      option.value = scenario.id;
      return option;
    }));
    renderAgentInputs();
    await refreshAgentReports();
    showWorkflow("agent");
    if (demoMode.enabled && demoMode.examples.length) await openRecordedExample(demoMode.examples[0]);
    else agentElements["agent-status"].textContent = "Developer view ready. No generation or interpretation requested.";
  } catch (error) {
    agentElements["agent-status"].textContent = error.message;
  }
}

async function openRecordedExample(entry) {
  renderAgentReport(await requestJson(`/api/agent/reports/${encodeURIComponent(entry.run_id)}`));
  agentElements["agent-saved"].value = entry.run_id;
  agentElements["agent-status"].textContent = `${entry.label}. Recorded evidence opened; zero new API requests.`;
  for (const candidate of demoMode.examples) {
    const button = document.getElementById(`demo-${candidate.key}`);
    button.setAttribute("aria-pressed", String(candidate.key === entry.key));
  }
}
loadAgent();
