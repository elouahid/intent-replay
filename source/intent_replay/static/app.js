"use strict";

const DEFAULT_TIMEZONE = "Europe/London";
const IMPLEMENTATION_LABELS = Object.freeze({ faulty: "Faulty", corrected: "Corrected" });
const INTEGRITY_STYLES = Object.freeze({
  PASS: { label: "PASS", tone: "positive", icon: "circle-check" },
  FAIL: { label: "FAIL", tone: "negative", icon: "circle-x" },
  INCONCLUSIVE: { label: "INCONCLUSIVE", tone: "warning", icon: "circle-help" },
});
const OUTCOME_STYLES = Object.freeze({
  fulfilled: { label: "Fulfilled", tone: "positive", icon: "calendar-check" },
  unfulfilled: { label: "Unfulfilled", tone: "negative", icon: "calendar-x" },
  unknown: { label: "Unknown", tone: "warning", icon: "calendar" },
});

const state = {
  scenarios: [],
  implementation: "faulty",
  loadingScenarios: false,
  inFlight: null,
  report: null,
  lastRunFailed: false,
};
const demoMode = {enabled: true, ready: false, examples: []};
const demoReady = requestJson("/api/demo").then(config => {
  requireValue(typeof config.enabled === "boolean" && Array.isArray(config.examples), "recorded demo configuration");
  Object.assign(demoMode, config, {ready: true});
  return config;
});

const elements = Object.fromEntries([
  "replay-form", "scenario-select", "scenario-description", "scenario-request",
  "scenario-conditions", "mode-faulty", "mode-corrected", "implementation-caption",
  "run-button", "run-status", "notice", "notice-message", "retry-scenarios",
  "booking-service", "booking-reference", "booking-date", "booking-time", "booking-timezone",
  "model-name", "report-caption", "report-meta", "report-run-id", "report-scenario",
  "report-implementation", "report-controlled", "report-created", "report-duration",
  "report-context", "download-report", "empty-state", "empty-icon", "empty-title",
  "empty-detail", "report-content", "booking-outcome", "confirmation-integrity", "instruction-adherence", "task-verdict",
  "evaluation-explanation", "initial-booking", "final-booking", "final-state-status",
  "final-state-detail", "report-request", "conversation", "interpretation-status",
  "interpretation-model", "intent-fields", "ambiguities", "interpretation-errors",
  "interpretation-error-section", "action-trace", "evaluation-checks", "provenance",
  "controlled-demonstrations",
].map((id) => [id, document.getElementById(id)]));

class ContractError extends Error {
  constructor(field) {
    super(`API contract mismatch at ${field}. No new report was displayed.`);
    this.name = "ContractError";
  }
}

function requireValue(condition, field) {
  if (!condition) throw new ContractError(field);
}

function requireObject(value, field) {
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value), field);
}

function requireString(value, field, nullable = false) {
  requireValue(typeof value === "string" || (nullable && value === null), field);
}

function requireStringList(value, field) {
  requireValue(Array.isArray(value) && value.every((item) => typeof item === "string"), field);
}

function requireEnum(value, allowed, field) {
  requireValue(allowed.includes(value), field);
}

function validateBooking(booking, field) {
  requireObject(booking, field);
  for (const key of ["reference", "service", "starts_at", "timezone"]) {
    requireString(booking[key], `${field}.${key}`);
  }
}

function validateAPICall(call, field) {
  requireObject(call, field);
  requireEnum(call.status, ["not_called", "failed_preflight", "attempted", "transport_failed", "http_error", "response_received"], `${field}.status`);
  for (const key of ["http_attempts", "http_responses", "successful_http_responses"]) {
    requireValue(Number.isInteger(call[key]) && call[key] >= 0, `${field}.${key}`);
  }
  requireValue(call.successful_http_responses <= call.http_responses && call.http_responses <= call.http_attempts, `${field}.counts`);
}

function validateScenarios(payload) {
  requireObject(payload, "scenarios response");
  validateBooking(payload.initial_booking, "initial_booking");
  requireString(payload.model, "model");
  requireValue(Array.isArray(payload.scenarios), "scenarios");
  const identifiers = new Set();
  payload.scenarios.forEach((scenario, index) => {
    const field = `scenarios[${index}]`;
    requireObject(scenario, field);
    for (const key of ["id", "name", "description", "customer_request"]) {
      requireString(scenario[key], `${field}.${key}`);
    }
    requireValue(scenario.id.length > 0 && !identifiers.has(scenario.id), `${field}.id`);
    identifiers.add(scenario.id);
    for (const key of ["slot_available", "final_read_available"]) {
      requireValue(typeof scenario[key] === "boolean", `${field}.${key}`);
    }
  });
}

function validateReport(report, request) {
  requireObject(report, "report");
  requireValue(report.schema_version === 2, "schema_version (expected version 2)");
  for (const key of ["run_id", "created_at", "customer_request"]) {
    requireString(report[key], key);
  }
  requireValue(Number.isFinite(report.duration_ms) && report.duration_ms >= 0, "duration_ms");
  requireObject(report.scenario, "scenario");
  for (const key of ["id", "name", "description"]) {
    requireString(report.scenario[key], `scenario.${key}`);
  }
  requireEnum(report.implementation, ["faulty", "corrected"], "implementation");
  requireValue(report.scenario.id === request.scenario_id, "scenario.id for the requested run");
  requireValue(report.implementation === request.implementation, "implementation for the requested run");
  requireValue(typeof report.controlled_fault === "boolean", "controlled_fault");
  validateBooking(report.initial_booking, "initial_booking");
  if (report.final_booking !== null) validateBooking(report.final_booking, "final_booking");
  requireObject(report.final_state, "final_state");
  requireEnum(report.final_state.status, ["available", "missing", "unavailable"], "final_state.status");
  requireString(report.final_state.detail, "final_state.detail");

  requireValue(Array.isArray(report.conversation), "conversation");
  report.conversation.forEach((turn, index) => {
    requireObject(turn, `conversation[${index}]`);
    requireString(turn.id, `conversation[${index}].id`);
    requireEnum(turn.role, ["assistant", "customer"], `conversation[${index}].role`);
    requireString(turn.text, `conversation[${index}].text`);
  });

  requireValue(Array.isArray(report.action_trace), "action_trace");
  report.action_trace.forEach((action, index) => {
    const field = `action_trace[${index}]`;
    requireObject(action, field);
    requireValue(Number.isFinite(action.sequence), `${field}.sequence`);
    for (const key of ["event", "detail"]) requireString(action[key], `${field}.${key}`);
    for (const key of ["booking_reference", "target_time", "observed_time"]) {
      requireString(action[key], `${field}.${key}`, true);
    }
  });

  const interpretation = report.interpretation;
  requireObject(interpretation, "interpretation");
  requireEnum(interpretation.status, ["valid", "invalid", "ambiguous", "error"], "interpretation.status");
  requireString(interpretation.model, "interpretation.model", true);
  requireStringList(interpretation.errors, "interpretation.errors");
  validateAPICall(interpretation.api_call, "interpretation.api_call");
  if (interpretation.data !== null) {
    const data = interpretation.data;
    requireObject(data, "interpretation.data");
    requireEnum(data.requested_operation, ["reschedule", "other", "unknown"], "requested_operation");
    requireEnum(data.assistant_claim, ["rescheduled", "not_rescheduled", "unclear"], "assistant_claim");
    for (const key of ["appointment_reference", "requested_new_time"]) {
      requireString(data[key], `interpretation.data.${key}`, true);
    }
    if (data.claimed_booking !== null) {
      requireObject(data.claimed_booking, "interpretation.data.claimed_booking");
      for (const key of ["reference", "starts_at", "timezone"]) {
        requireString(data.claimed_booking[key], `interpretation.data.claimed_booking.${key}`, true);
      }
    }
    requireObject(data.evidence, "interpretation.data.evidence");
    for (const key of ["request_turn_ids", "appointment_reference_turn_ids", "requested_time_turn_ids", "assistant_claim_turn_ids"]) {
      requireStringList(data.evidence[key], `evidence.${key}`);
    }
    requireStringList(data.ambiguities, "interpretation.data.ambiguities");
  }

  const evaluation = report.evaluation;
  requireObject(evaluation, "evaluation");
  requireEnum(evaluation.booking_outcome, Object.keys(OUTCOME_STYLES), "evaluation.booking_outcome");
  requireEnum(evaluation.confirmation_integrity, Object.keys(INTEGRITY_STYLES), "evaluation.confirmation_integrity");
  requireEnum(evaluation.instruction_adherence, Object.keys(INTEGRITY_STYLES), "evaluation.instruction_adherence");
  requireEnum(evaluation.task_verdict, Object.keys(INTEGRITY_STYLES), "evaluation.task_verdict");
  requireString(evaluation.explanation, "evaluation.explanation");
  requireValue(Array.isArray(evaluation.checks), "evaluation.checks");
  evaluation.checks.forEach((check, index) => {
    requireObject(check, `evaluation.checks[${index}]`);
    requireString(check.name, `evaluation.checks[${index}].name`);
    requireString(check.detail, `evaluation.checks[${index}].detail`);
    requireEnum(check.status, Object.keys(INTEGRITY_STYLES), `evaluation.checks[${index}].status`);
  });

  const provenance = report.provenance;
  requireObject(provenance, "provenance");
  requireString(provenance.database, "provenance.database");
  requireString(provenance.interpretation_mode, "provenance.interpretation_mode");
  validateAPICall(provenance.api_call, "provenance.api_call");
  for (const key of ["reset_before_run", "independent_final_read"]) {
    requireValue(typeof provenance[key] === "boolean", `provenance.${key}`);
  }
  requireStringList(provenance.mocked_components, "provenance.mocked_components");
  requireStringList(provenance.controlled_demonstrations, "provenance.controlled_demonstrations");
}

function createElement(tag, className = "", text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function createIcon(name, className = "") {
  const element = createElement("i", className);
  element.setAttribute("data-lucide", name);
  element.setAttribute("aria-hidden", "true");
  return element;
}

function refreshIcons() {
  if (globalThis.lucide) {
    globalThis.lucide.createIcons({ attrs: { "aria-hidden": "true", focusable: "false", "stroke-width": 1.75 } });
  }
}

function setBadge(element, style, large = false) {
  element.className = `${large ? "verdict-value" : "status-badge"} tone-${style.tone}`;
  element.replaceChildren(createIcon(style.icon), createElement("span", "", style.label));
}

function formatTimestamp(value, timezone = DEFAULT_TIMEZONE, kind = "full") {
  if (value === null || value === undefined || value === "") return "Not specified";
  const wallTime = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;
  const zonedTime = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/i;
  const isWallTime = wallTime.test(value);
  if (!isWallTime && !zonedTime.test(value)) return `${value} (${timezone})`;
  const date = new Date(isWallTime ? `${value}Z` : value);
  if (Number.isNaN(date.getTime())) return `${value} (${timezone})`;
  const options = { timeZone: isWallTime ? "UTC" : timezone, hourCycle: "h23" };
  if (kind !== "time") Object.assign(options, { day: "2-digit", month: "short", year: "numeric" });
  if (kind !== "date") Object.assign(options, { hour: "2-digit", minute: "2-digit" });
  try {
    const formatted = new Intl.DateTimeFormat("en-GB", options).format(date);
    return kind === "full" ? `${formatted} (${timezone})` : formatted;
  } catch {
    return `${value} (${timezone})`;
  }
}

function formatDuration(milliseconds) {
  return milliseconds < 1000
    ? `${Math.round(milliseconds)} ms`
    : `${(milliseconds / 1000).toFixed(1)} s`;
}

function appendDefinition(container, label, value, className = "") {
  const row = createElement("div", `definition-row ${className}`.trim());
  row.append(createElement("dt", "", label), createElement("dd", "", value));
  container.append(row);
  return row.lastElementChild;
}

function renderList(container, values, emptyLabel) {
  container.replaceChildren();
  if (values.length === 0) {
    container.append(createElement("li", "list-empty", emptyLabel));
    return;
  }
  values.forEach((value) => container.append(createElement("li", "", value)));
}

function renderBooking(container, booking, finalState) {
  container.replaceChildren();
  if (booking === null) {
    const message = finalState.status === "missing" ? "No persisted booking found" : "Final booking unavailable";
    container.append(createElement("p", "booking-unavailable", message));
    return;
  }
  const scheduled = createElement("p", "persisted-time", formatTimestamp(booking.starts_at, booking.timezone, "time"));
  const date = createElement("p", "persisted-date", `${formatTimestamp(booking.starts_at, booking.timezone, "date")} / ${booking.timezone}`);
  const details = createElement("dl", "booking-details");
  appendDefinition(details, "Reference", booking.reference, "mono-value");
  appendDefinition(details, "Service", booking.service);
  container.append(scheduled, date, details);
}

function renderConversation(report) {
  const turnTargets = new Map();
  elements["report-request"].textContent = report.customer_request;
  elements.conversation.replaceChildren();
  report.conversation.forEach((turn, index) => {
    const target = `conversation-turn-${index + 1}`;
    turnTargets.set(turn.id, target);
    const item = createElement("li", `conversation-turn turn-${turn.role}`);
    item.id = target;
    item.tabIndex = -1;
    const header = createElement("div", "turn-header");
    const speaker = createElement("span", "turn-speaker");
    speaker.append(createIcon(turn.role === "customer" ? "user-round" : "bot"));
    speaker.append(createElement("span", "", turn.role === "customer" ? "Customer" : "Assistant"));
    header.append(speaker, createElement("code", "turn-id", turn.id));
    item.append(header, createElement("p", "turn-text", turn.text));
    elements.conversation.append(item);
  });
  if (report.conversation.length === 0) {
    elements.conversation.append(createElement("li", "section-empty", "No conversation turns returned."));
  }
  return turnTargets;
}

function appendIntentField(label, value, evidenceIds, turnTargets) {
  const valueElement = appendDefinition(elements["intent-fields"], label, value);
  const evidence = createElement("div", "evidence-links");
  evidence.setAttribute("aria-label", `Evidence for ${label.toLowerCase()}`);
  evidence.append(createElement("span", "evidence-label", "Evidence"));
  if (evidenceIds.length === 0) evidence.append(createElement("span", "muted", "None cited"));
  evidenceIds.forEach((identifier) => {
    const target = turnTargets.get(identifier);
    const link = createElement(target ? "a" : "span", "evidence-id", identifier);
    if (target) {
      link.href = `#${target}`;
      link.setAttribute("aria-label", `Conversation turn ${identifier}`);
    } else {
      link.classList.add("unresolved-evidence");
      link.title = "This turn ID is not present in the returned conversation.";
      link.append(createElement("span", "sr-only", " (turn not present in conversation)"));
    }
    evidence.append(link);
  });
  valueElement.append(evidence);
}

function renderInterpretation(report, turnTargets) {
  const interpretation = report.interpretation;
  const statusLabels = { valid: "Valid", invalid: "Invalid", ambiguous: "Ambiguous", error: "Error" };
  setBadge(elements["interpretation-status"], {
    label: statusLabels[interpretation.status],
    tone: interpretation.status === "valid" ? "neutral" : "warning",
    icon: interpretation.status === "valid" ? "braces" : "circle-help",
  });
  elements["interpretation-model"].textContent = interpretation.model || "Model not reported";
  elements["intent-fields"].replaceChildren();
  const data = interpretation.data;
  if (data) {
    const timezone = report.initial_booking.timezone;
    const operations = { reschedule: "Reschedule", other: "Other", unknown: "Unknown" };
    const claims = { rescheduled: "Rescheduled", not_rescheduled: "Not rescheduled", unclear: "Unclear" };
    appendIntentField("Requested operation", operations[data.requested_operation], data.evidence.request_turn_ids, turnTargets);
    appendIntentField("Appointment reference", data.appointment_reference ?? "Not identified", data.evidence.appointment_reference_turn_ids, turnTargets);
    appendIntentField("Requested new time", formatTimestamp(data.requested_new_time, timezone), data.evidence.requested_time_turn_ids, turnTargets);
    appendIntentField("Assistant claim", claims[data.assistant_claim], data.evidence.assistant_claim_turn_ids, turnTargets);
    if (data.claimed_booking) {
      appendIntentField("Stated resulting reference", data.claimed_booking.reference ?? "Not identified", data.evidence.assistant_claim_turn_ids, turnTargets);
      appendIntentField("Stated resulting time", formatTimestamp(data.claimed_booking.starts_at, data.claimed_booking.timezone || timezone), data.evidence.assistant_claim_turn_ids, turnTargets);
      appendIntentField("Stated resulting timezone", data.claimed_booking.timezone ?? "Not identified", data.evidence.assistant_claim_turn_ids, turnTargets);
    } else {
      appendIntentField("Stated resulting booking", "No resulting details stated", data.evidence.assistant_claim_turn_ids, turnTargets);
    }
  } else {
    appendDefinition(elements["intent-fields"], "Structured interpretation", "Not returned");
  }
  renderList(elements.ambiguities, data ? data.ambiguities : [], data ? "None reported" : "No interpretation available");
  elements["interpretation-error-section"].hidden = interpretation.errors.length === 0;
  renderList(elements["interpretation-errors"], interpretation.errors, "None reported");
}

function renderTrace(report) {
  elements["action-trace"].replaceChildren();
  report.action_trace.forEach((action) => {
    const item = createElement("li", "trace-item");
    item.append(createElement("span", "trace-sequence", String(action.sequence)));
    const body = createElement("div", "trace-body");
    body.append(createElement("h4", "trace-event", action.event), createElement("p", "trace-detail", action.detail));
    const readings = createElement("dl", "trace-readings");
    appendDefinition(readings, "Booking", action.booking_reference ?? "Not provided", "mono-value");
    appendDefinition(readings, "Target time", formatTimestamp(action.target_time, report.initial_booking.timezone));
    appendDefinition(readings, "Observed time", formatTimestamp(action.observed_time, report.initial_booking.timezone));
    body.append(readings);
    item.append(body);
    elements["action-trace"].append(item);
  });
  if (report.action_trace.length === 0) {
    elements["action-trace"].append(createElement("li", "section-empty", "No actions returned."));
  }
}

function renderChecks(checks) {
  elements["evaluation-checks"].replaceChildren();
  checks.forEach((check) => {
    const item = createElement("li", "check-item");
    const badge = createElement("span");
    setBadge(badge, INTEGRITY_STYLES[check.status]);
    const body = createElement("div", "check-body");
    body.append(createElement("h4", "", check.name), createElement("p", "", check.detail));
    item.append(badge, body);
    elements["evaluation-checks"].append(item);
  });
  if (checks.length === 0) {
    elements["evaluation-checks"].append(createElement("li", "section-empty", "No checks returned."));
  }
}

function renderProvenance(provenance) {
  const container = elements.provenance;
  container.replaceChildren();
  appendDefinition(container, "Database", provenance.database);
  appendDefinition(container, "Interpretation", provenance.interpretation_mode);
  const callStates = {not_called: "Not called", failed_preflight: "Preflight failed; not called", attempted: "Attempted", transport_failed: "Transport failed", http_error: "HTTP error", response_received: "HTTP response received"};
  appendDefinition(container, "API execution", callStates[provenance.api_call.status]);
  appendDefinition(container, "HTTP attempts", String(provenance.api_call.http_attempts));
  appendDefinition(container, "Successful HTTP responses", String(provenance.api_call.successful_http_responses));
  appendDefinition(container, "Reset before run", provenance.reset_before_run ? "Yes" : "No");
  appendDefinition(container, "Independent final read", provenance.independent_final_read ? "Yes" : "No");
  appendDefinition(container, "Mocked components", provenance.mocked_components.length ? provenance.mocked_components.join(", ") : "None declared");
  renderList(elements["controlled-demonstrations"], provenance.controlled_demonstrations, "None declared");
}

function renderReport(report) {
  elements["report-caption"].textContent = report.scenario.description;
  elements["report-run-id"].textContent = report.run_id;
  elements["report-scenario"].textContent = report.scenario.name;
  elements["report-implementation"].textContent = IMPLEMENTATION_LABELS[report.implementation];
  elements["report-controlled"].hidden = !report.controlled_fault;
  elements["report-created"].textContent = formatTimestamp(report.created_at, DEFAULT_TIMEZONE);
  elements["report-duration"].textContent = formatDuration(report.duration_ms);
  elements["report-meta"].hidden = false;
  setBadge(elements["task-verdict"], INTEGRITY_STYLES[report.evaluation.task_verdict], true);
  setBadge(elements["booking-outcome"], OUTCOME_STYLES[report.evaluation.booking_outcome], true);
  setBadge(elements["instruction-adherence"], INTEGRITY_STYLES[report.evaluation.instruction_adherence], true);
  setBadge(elements["confirmation-integrity"], INTEGRITY_STYLES[report.evaluation.confirmation_integrity], true);
  elements["evaluation-explanation"].textContent = report.evaluation.explanation;
  renderBooking(elements["initial-booking"], report.initial_booking);
  renderBooking(elements["final-booking"], report.final_booking, report.final_state);
  const finalStateLabels = { available: "Available", missing: "Missing", unavailable: "Unavailable" };
  setBadge(elements["final-state-status"], {
    label: finalStateLabels[report.final_state.status],
    tone: report.final_state.status === "available" ? "neutral" : "warning",
    icon: report.final_state.status === "available" ? "database" : "database-zap",
  });
  elements["final-state-detail"].textContent = report.final_state.detail;
  const turnTargets = renderConversation(report);
  renderInterpretation(report, turnTargets);
  renderTrace(report);
  renderChecks(report.evaluation.checks);
  renderProvenance(report.provenance);
  elements["report-content"].hidden = false;
  refreshIcons();
}

function selectedScenario() {
  return state.scenarios.find((scenario) => scenario.id === elements["scenario-select"].value);
}

function renderSelectedScenario() {
  const scenario = selectedScenario();
  elements["scenario-description"].textContent = scenario ? scenario.description : "No scenario selected.";
  elements["scenario-request"].textContent = scenario ? scenario.customer_request : "Not available";
  elements["scenario-conditions"].replaceChildren();
  if (scenario) {
    const slot = createElement("span", "condition-label", scenario.slot_available ? "Slot available" : "Slot unavailable");
    const readback = createElement("span", "condition-label", scenario.final_read_available ? "Final read enabled" : "Final read unavailable");
    elements["scenario-conditions"].append(slot, readback);
  }
  syncControls();
}

function renderReportContext() {
  let context = "";
  const report = state.report;
  if (report) {
    if (state.inFlight) {
      context = "Replay in progress. The previous report remains visible below.";
    } else if (state.lastRunFailed) {
      context = "Latest request failed. The previous report remains visible below.";
    } else if (report.implementation !== state.implementation || report.scenario.id !== elements["scenario-select"].value) {
      context = `Selection changed. Still showing ${IMPLEMENTATION_LABELS[report.implementation]} / ${report.scenario.name}.`;
    }
  }
  elements["report-context"].textContent = context;
  elements["report-context"].hidden = context.length === 0;
}

function syncControls() {
  const busy = state.loadingScenarios || state.inFlight !== null || window.agentBusy === true;
  const scenario = selectedScenario();
  elements["scenario-select"].disabled = busy || state.scenarios.length === 0;
  for (const implementation of ["faulty", "corrected"]) {
    const button = elements[`mode-${implementation}`];
    button.disabled = busy;
    button.setAttribute("aria-pressed", String(state.implementation === implementation));
  }
  const caption = elements["implementation-caption"];
  caption.replaceChildren();
  if (state.implementation === "faulty") {
    caption.append(createElement("span", "controlled-label", "Controlled demonstration"));
    caption.append(createElement("span", "", "The reschedule write is deliberately skipped."));
  } else {
    caption.append(createElement("span", "", "The reschedule write is enabled."));
  }
  elements["run-button"].disabled = busy || !scenario || demoMode.enabled || !demoMode.ready;
  elements["run-button"].replaceChildren(
    createIcon(state.inFlight ? "loader-circle" : "play", state.inFlight ? "spin" : ""),
    createElement("span", "", state.inFlight ? "Running replay" : "Run replay"),
  );
  elements["retry-scenarios"].disabled = busy;
  elements["replay-form"].setAttribute("aria-busy", String(busy));
  elements["download-report"].disabled = !state.report;
  elements["empty-state"].hidden = state.report !== null;
  if (!state.report) {
    elements["empty-icon"].replaceChildren(createIcon(state.inFlight ? "loader-circle" : "inbox", state.inFlight ? "spin" : ""));
    elements["empty-title"].textContent = state.inFlight ? "Replay in progress" : "No replay recorded";
    if (state.inFlight) {
      elements["empty-detail"].textContent = `${scenario.name} / ${IMPLEMENTATION_LABELS[state.inFlight.implementation]}`;
    } else if (state.loadingScenarios) {
      elements["empty-detail"].textContent = "Connecting to the replay service.";
    } else if (state.lastRunFailed) {
      elements["empty-detail"].textContent = "The latest request did not return a report.";
    } else {
      elements["empty-detail"].textContent = scenario
        ? `${scenario.name} / ${IMPLEMENTATION_LABELS[state.implementation]} selected`
        : "No scenarios available.";
    }
  }
  renderReportContext();
  refreshIcons();
  if (typeof syncTemporalControls === "function") syncTemporalControls();
}

function setStatus(message) {
  elements["run-status"].textContent = message;
}

function clearNotice() {
  elements.notice.hidden = true;
  elements["notice-message"].textContent = "";
  elements["retry-scenarios"].hidden = true;
}

function showNotice(message, retryScenarios = false) {
  elements["notice-message"].textContent = message;
  elements["retry-scenarios"].hidden = !retryScenarios;
  elements.notice.hidden = false;
}

async function requestJson(url, options = {}) {
  if ((demoMode.enabled || !demoMode.ready) && !["GET", "HEAD"].includes(options.method || "GET")) {
    throw new Error("Recorded demo is read-only. No inference request was sent.");
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);
  try {
    let response;
    try {
      response = await fetch(url, {
        ...options,
        headers: { Accept: "application/json", ...options.headers },
        cache: "no-store",
        signal: controller.signal,
      });
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The replay service did not respond within 3 minutes.");
      throw new Error("Could not reach the replay service.");
    }
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error(`The replay service returned an unreadable response (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      const detail = payload && typeof payload.detail === "string" ? payload.detail : "The replay service could not complete the request.";
      throw new Error(`${detail} (HTTP ${response.status})`);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

async function loadScenarios() {
  if (state.loadingScenarios || state.inFlight) return;
  state.loadingScenarios = true;
  clearNotice();
  setStatus("Loading scenarios.");
  syncControls();
  try {
    const payload = await requestJson("/api/scenarios");
    validateScenarios(payload);
    state.scenarios = payload.scenarios;
    const booking = payload.initial_booking;
    elements["booking-service"].textContent = booking.service;
    elements["booking-reference"].textContent = booking.reference;
    elements["booking-date"].textContent = formatTimestamp(booking.starts_at, booking.timezone, "date");
    elements["booking-time"].textContent = formatTimestamp(booking.starts_at, booking.timezone, "time");
    elements["booking-timezone"].textContent = booking.timezone;
    elements["model-name"].textContent = payload.model;
    elements["scenario-select"].replaceChildren();
    payload.scenarios.forEach((scenario) => {
      const option = createElement("option", "", scenario.name);
      option.value = scenario.id;
      elements["scenario-select"].append(option);
    });
    if (payload.scenarios.length === 0) {
      elements["scenario-select"].append(createElement("option", "", "No scenarios available"));
      showNotice("The replay service returned no scenarios.", true);
      setStatus("No scenarios available.");
    } else {
      elements["scenario-select"].value = payload.scenarios[0].id;
      setStatus("Ready to run.");
    }
  } catch (error) {
    state.scenarios = [];
    elements["scenario-select"].replaceChildren(createElement("option", "", "Scenarios unavailable"));
    elements["booking-service"].textContent = "Booking unavailable";
    for (const identifier of ["booking-reference", "booking-date", "booking-time", "booking-timezone"]) {
      elements[identifier].textContent = "Unavailable";
    }
    elements["model-name"].textContent = "Unavailable";
    showNotice(error.message, true);
    setStatus("Scenarios could not be loaded.");
  } finally {
    state.loadingScenarios = false;
    renderSelectedScenario();
  }
}

async function runReplay(event) {
  event.preventDefault();
  if (state.inFlight || state.loadingScenarios || !selectedScenario()) return;
  const request = Object.freeze({
    scenario_id: elements["scenario-select"].value,
    implementation: state.implementation,
  });
  state.inFlight = request;
  state.lastRunFailed = false;
  clearNotice();
  setStatus(`Running ${IMPLEMENTATION_LABELS[request.implementation]} / ${selectedScenario().name}.`);
  syncControls();
  try {
    const report = await requestJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    validateReport(report, request);
    renderReport(report);
    state.report = report;
    setStatus(`${IMPLEMENTATION_LABELS[report.implementation]} report received for ${report.scenario.name}. Task: ${report.evaluation.task_verdict}. Factual claim accuracy: ${report.evaluation.confirmation_integrity}.`);
  } catch (error) {
    state.lastRunFailed = true;
    showNotice(error.message);
    setStatus("Replay request failed.");
  } finally {
    state.inFlight = null;
    syncControls();
  }
}

function downloadReport() {
  if (!state.report) return;
  const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = createElement("a");
  link.href = url;
  const identifier = state.report.run_id.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 80);
  link.download = `intent-replay-${identifier}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

elements["replay-form"].addEventListener("submit", runReplay);
elements["scenario-select"].addEventListener("change", renderSelectedScenario);
elements["retry-scenarios"].addEventListener("click", loadScenarios);
elements["download-report"].addEventListener("click", downloadReport);
for (const implementation of ["faulty", "corrected"]) {
  elements[`mode-${implementation}`].addEventListener("click", () => {
    if (state.inFlight || state.loadingScenarios) return;
    state.implementation = implementation;
    syncControls();
  });
}

refreshIcons();
demoReady.then(loadScenarios).catch(error => setStatus(error.message));
