"use strict";

const byId = id => document.getElementById(id);
const caseKey = run => `${run.mode}:${run.ticket_id}`;
const edits = new Map();
let state = { runs: [], samples: [] };
let selectedId = null;
let filter = "all";
let reviewing = false;

const stateLabel = {
  needs_review: "Needs review",
  draft_ready: "Draft ready",
  approved: "Approved",
  reviewed: "Reviewed"
};
const routeLabel = {
  return_instructions_draft: "Return request",
  tracking_update_draft: "Delivery question",
  order_reference_request_draft: "Missing order reference",
  human_review: "Exception review"
};
const sampleLabels = [
  "Standard return", "Delivery status", "Outside return window", "Missing order number",
  "High-value order", "Damaged item", "Customer mismatch", "Not delivered",
  "Spanish return request", "Duplicate charge", "Instruction override", "Unknown order",
  "Unsupported country", "Multiple order references"
];

function element(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  if (className) value.className = className;
  return value;
}
function badge(text, kind = "") { return element("span", text, `pill ${kind}`); }
function statusOf(run) { return run.review?.state || (run.route === "human_review" ? "needs_review" : "draft_ready"); }
function statusTone(status) { return status === "needs_review" ? "amber" : status === "draft_ready" ? "teal" : "green"; }
function selectedCase() { return state.runs.find(run => caseKey(run) === selectedId); }
function savedDraft(run) { return run.review?.draft ?? run.draft ?? ""; }
function savedNote(run) { return run.review?.note || ""; }
function sourceLabel(run) { return run.dispatch ? "n8n" : run.mode === "live" ? "Live AI" : "Baseline"; }
function money(value) { return new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(value); }
function processedAt(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" });
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return result;
}
function feedback(text, error = false) {
  const target = byId("feedback");
  target.hidden = !text;
  target.textContent = text;
  target.className = `notification${error ? " error" : ""}`;
}
function setView(next) {
  for (const id of ["queue", "workflow", "checks"]) byId(`${id}-view`).hidden = id !== next;
  document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.view === next));
  const labels = {
    queue: ["Returns", "Returns inbox", "Every request, its checks, and the next step."],
    workflow: ["Workflow", "The automation workflow", "Follow the hand-off from customer message to operator decision."],
    checks: ["Verification", "Workflow verification", "Inspect the saved results and the rules behind each decision."]
  };
  ["view-label", "page-title", "page-subtitle"].forEach((id, index) => { byId(id).textContent = labels[next][index]; });
}
function setFilter(next) {
  filter = next;
  document.querySelectorAll(".tabs button").forEach(button => button.classList.toggle("active", button.dataset.status === next));
  setView("queue");
  render();
}
function visibleCases() {
  const query = byId("search").value.toLowerCase().trim();
  return state.runs.filter(run => {
    const status = statusOf(run);
    const matchesStatus = filter === "all" || (filter === "done" ? ["approved", "reviewed"].includes(status) : filter === status);
    const text = [run.ticket_id, run.ticket.message, run.ticket.sender_email, run.order?.order_id, run.extraction?.order_id].join(" ").toLowerCase();
    return matchesStatus && (!query || text.includes(query));
  });
}
function selectCase(run) {
  selectedId = caseKey(run);
  renderDetail();
  for (const row of byId("case-rows").children) {
    const selected = row.dataset.key === selectedId;
    row.classList.toggle("selected", selected);
    row.setAttribute("aria-selected", String(selected));
  }
}
function render() {
  const runs = state.runs;
  byId("nav-count").textContent = runs.length;
  byId("review-count").textContent = runs.filter(run => statusOf(run) === "needs_review").length;
  byId("draft-count").textContent = runs.filter(run => statusOf(run) === "draft_ready").length;
  byId("done-count").textContent = runs.filter(run => ["approved", "reviewed"].includes(statusOf(run))).length;
  byId("n8n-count").textContent = runs.filter(run => run.dispatch?.source === "n8n").length;

  const visible = visibleCases();
  if (!visible.some(run => caseKey(run) === selectedId)) selectedId = visible.length ? caseKey(visible[0]) : null;
  byId("queue-size").textContent = `${visible.length} of ${runs.length}`;
  byId("queue-empty").hidden = visible.length > 0;
  byId("case-rows").replaceChildren();

  for (const run of visible) {
    const row = element("tr", undefined, caseKey(run) === selectedId ? "selected" : "");
    row.tabIndex = 0;
    row.dataset.key = caseKey(run);
    row.setAttribute("aria-label", `${run.ticket_id}, ${stateLabel[statusOf(run)]}`);
    row.setAttribute("aria-selected", String(caseKey(run) === selectedId));
    const request = element("td");
    request.append(element("strong", routeLabel[run.route], "request-subject"));
    request.append(element("span", run.ticket.message, "request-preview"));
    const metadata = element("div", undefined, "request-meta");
    const order = run.order?.order_id || run.extraction?.order_id;
    metadata.append(element("span", order || run.ticket_id, "request-ref"));
    metadata.append(element("span", "·", "separator"), element("span", sourceLabel(run)));
    request.append(metadata);
    const status = element("td");
    status.append(badge(stateLabel[statusOf(run)], statusTone(statusOf(run))));
    row.append(request, status);
    row.addEventListener("click", () => selectCase(run));
    row.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectCase(run); }
    });
    byId("case-rows").append(row);
  }
  renderDetail();
  renderEvidence();
}
function nextStep(run) {
  if (statusOf(run) === "approved") return "Response draft approved";
  if (statusOf(run) === "reviewed") return "Operator review recorded";
  if (statusOf(run) === "needs_review" && run.route !== "human_review") return "Further investigation requested";
  if (run.route !== "human_review") return "Ready for a response check";
  const failed = run.checks.find(check => !check.passed);
  const labels = {
    "Within value threshold": "Review the order value",
    "Customer email matches": "Verify the customer's identity",
    "Within return window": "Review return eligibility",
    "Order exists": "Confirm the order reference",
    "Delivered order": "Check delivery before proceeding",
    "Supported country": "Check the available return route",
    "One consistent order reference": "Confirm which order to handle"
  };
  return labels[failed?.label] || "This request needs an operator";
}
function renderDetail() {
  const run = selectedCase();
  byId("no-selection").hidden = Boolean(run);
  byId("case-detail").hidden = !run;
  if (!run) return;
  const changedCase = byId("case-detail").dataset.caseKey !== selectedId;
  byId("case-detail").dataset.caseKey = selectedId;
  const status = statusOf(run);
  byId("case-id").textContent = run.ticket_id;
  byId("case-title").textContent = routeLabel[run.route] || run.route;
  byId("case-state").textContent = stateLabel[status];
  byId("case-state").className = `pill ${statusTone(status)}`;
  byId("case-meta").textContent = `${run.ticket.sender_email} · Processed ${processedAt(run.created_at)} Madrid`;
  byId("next-action").textContent = nextStep(run);
  byId("decision-banner").className = `decision-banner${status === "needs_review" ? "" : " positive"}`;
  byId("decision-symbol").textContent = status === "needs_review" ? "!" : "✓";
  const failed = run.checks.find(check => !check.passed);
  byId("reason").textContent = status === "approved" ? "Saved for the team. No customer message has been sent." : status === "reviewed" ? savedNote(run) : failed?.detail || run.reason;
  byId("original-message").textContent = run.ticket.message;
  byId("intent-evidence").textContent = run.extraction ? `Identified ${run.extraction.category.replaceAll("_", " ")} · Evidence: “${run.extraction.evidence}”` : "No validated extraction. An operator needs to inspect the request.";

  byId("order-facts").replaceChildren();
  byId("order-facts").hidden = !run.order;
  if (run.order) {
    for (const [label, value] of [["Order reference", run.order.order_id], ["Order value", money(run.order.total_eur)], ["Country", run.order.country]]) {
      const fact = element("div");
      fact.append(element("small", label), element("strong", value));
      byId("order-facts").append(fact);
    }
  }
  byId("checks").replaceChildren();
  for (const check of run.checks) {
    const item = element("div", undefined, `check-row${check.passed ? "" : " fail"}`);
    item.title = check.detail;
    item.append(element("span", check.passed ? "✓" : "!", "check-dot"));
    const description = element("div");
    description.append(element("strong", check.label));
    if (!check.passed) description.append(element("small", check.detail));
    item.append(description);
    byId("checks").append(item);
  }
  byId("check-summary").textContent = `${run.checks.filter(check => check.passed).length} / ${run.checks.length} passed`;
  byId("response-section").hidden = !run.draft;
  const pending = edits.get(selectedId);
  byId("draft-text").value = pending?.draft ?? savedDraft(run);
  byId("review-note").value = pending?.note ?? savedNote(run);
  byId("approve-draft").hidden = !run.draft || run.route === "human_review";
  byId("mark-reviewed").hidden = run.route !== "human_review";
  byId("review-state-note").textContent = status === "approved" ? "Approval recorded. Nothing has been sent." : status === "reviewed" ? "Next step recorded. Merchant actions happen outside this prototype." : "Records a decision only. No message or refund is sent.";
  updateEditLabel();

  byId("activity").replaceChildren();
  const steps = [...run.trace, ...(run.activity || []).map(event => ({
    step: event.kind === "dispatch" ? "n8n queue hand-off" : event.action.replaceAll("_", " "),
    detail: `${event.detail} · ${processedAt(event.created_at)}`
  }))];
  for (const step of steps) {
    const item = element("li");
    item.append(element("strong", step.step), element("small", step.detail));
    byId("activity").append(item);
  }
  if (changedCase) byId("case-body").scrollTop = 0;
  byId("model-data").textContent = JSON.stringify({
    model: run.model, extraction: run.extraction, provider_usage: run.provider_usage,
    processing_ms: run.duration_ms, review_revision: run.review?.revision || 0
  }, null, 2);
}
function updateEditLabel() {
  byId("unsaved-label").hidden = !edits.has(selectedId);
  byId("reset-edits").hidden = !edits.has(selectedId);
}
function captureEdits() {
  const run = selectedCase();
  if (!run) return;
  const draft = byId("draft-text").value;
  const note = byId("review-note").value;
  if (draft === savedDraft(run) && note === savedNote(run)) edits.delete(selectedId);
  else edits.set(selectedId, { draft, note, revision: edits.get(selectedId)?.revision ?? run.review?.revision ?? 0 });
  updateEditLabel();
}
function renderEvidence() {
  const evaluation = state.evaluation;
  byId("evaluation-model").textContent = evaluation?.model || "No saved run";
  byId("evaluation-summary").replaceChildren();
  if (evaluation) {
    for (const [number, label] of [[`${evaluation.route_matches} / ${evaluation.case_count}`, "Expected routes matched"], [evaluation.validated_live_extractions, "Validated model extractions"], [evaluation.review_required_but_drafted, "Review cases given a draft"]]) {
      const statistic = element("div");
      statistic.append(element("strong", number), element("small", label));
      byId("evaluation-summary").append(statistic);
    }
  }
  byId("evaluation-rows").replaceChildren();
  for (const item of evaluation?.cases || []) {
    const row = element("tr");
    row.append(element("td", item.id), element("td", item.expected_route.replaceAll("_", " ")), element("td", item.actual_route.replaceAll("_", " ")));
    const result = element("td");
    result.append(badge(item.matched ? "Matched" : "Mismatch", item.matched ? "teal" : "amber"));
    row.append(result);
    byId("evaluation-rows").append(row);
  }
  byId("policy-details").replaceChildren();
  const policy = state.policy || {};
  for (const [label, value] of [["Return window", `${policy.return_window_days} days`], ["Manual review above", money(policy.manual_review_above_eur)], ["Supported countries", (policy.supported_countries || []).join(", ")], ["Reference date", policy.reference_date]]) {
    const fact = element("div");
    fact.append(element("dt", label), element("dd", value));
    byId("policy-details").append(fact);
  }
  byId("orchestration-evidence").replaceChildren();
  if (!state.orchestration) byId("orchestration-evidence").append(element("p", "No verified n8n execution has been saved yet."));
  for (const run of state.orchestration?.runs || []) {
    const record = element("div", undefined, "receipt");
    record.append(element("strong", `${run.ticket_id} → ${run.destination.replaceAll("_", " ")}`), element("small", `${run.status === "replayed" ? "Saved outcome reused" : "Successfully executed"} · n8n ${state.orchestration.n8n_version}`));
    byId("orchestration-evidence").append(record);
  }
}
function modeHint() {
  byId("mode-hint").textContent = byId("mode").value === "live" ? "One small paid model call per new ticket. Only message text goes to OpenAI." : "Keyword baseline. No model runs and no API credit is used.";
}
async function refresh() {
  state = await api("/api/state");
  byId("live-option").disabled = !state.live_available;
  if (!state.live_available) byId("mode").value = "demo";
  modeHint();
  render();
}
function loadSample(index) {
  const sample = state.samples[index];
  byId("ticket-id").value = `CASE-${Date.now()}`;
  byId("email").value = sample?.sender_email || "alex@example.com";
  byId("order-id").value = sample?.order_id || "";
  byId("message").value = sample?.message || "";
}
async function review(action) {
  const run = selectedCase();
  if (!run || reviewing) return;
  const note = byId("review-note").value;
  if (action !== "approve_draft" && !note.trim()) {
    feedback("Add a note describing the next step.", true);
    byId("review-note").focus();
    return;
  }
  const id = selectedId;
  const payload = {
    event_id: crypto.randomUUID(), ticket_id: run.ticket_id, mode: run.mode, action,
    note, draft: byId("draft-text").value || null,
    expected_revision: edits.get(id)?.revision ?? run.review?.revision ?? 0
  };
  reviewing = true;
  for (const control of document.querySelectorAll(".review-actions button, #review-note, #draft-text")) control.disabled = true;
  try {
    await api("/api/review", payload);
    edits.delete(id);
    await refresh();
    feedback(action === "approve_draft" ? "Draft approved and saved. No message sent." : "Operator decision saved.");
  } catch (error) {
    if (error.status === 409) await refresh();
    feedback(error.message + (error.status === 409 ? " Reset edits to load the latest saved version." : ""), true);
  } finally {
    reviewing = false;
    for (const control of document.querySelectorAll(".review-actions button, #review-note, #draft-text")) control.disabled = false;
  }
}

for (const button of document.querySelectorAll("[data-view]")) button.addEventListener("click", () => setView(button.dataset.view));
for (const button of document.querySelectorAll("[data-status]")) button.addEventListener("click", () => setFilter(button.dataset.status));
byId("search").addEventListener("input", render);
byId("draft-text").addEventListener("input", captureEdits);
byId("review-note").addEventListener("input", captureEdits);
byId("reset-edits").addEventListener("click", () => { edits.delete(selectedId); renderDetail(); });
byId("refresh").addEventListener("click", () => refresh().then(() => feedback("Queue refreshed. Any unsaved edits are kept in this session.")).catch(error => feedback(error.message, true)));
byId("approve-draft").addEventListener("click", () => review("approve_draft"));
byId("mark-reviewed").addEventListener("click", () => review("mark_reviewed"));
byId("hold-case").addEventListener("click", () => review("hold"));
byId("new-request").addEventListener("click", () => {
  loadSample(byId("sample").value);
  byId("request-feedback").textContent = "";
  byId("request-dialog").showModal();
});
for (const id of ["close-dialog", "cancel-request"]) byId(id).addEventListener("click", () => byId("request-dialog").close());
byId("sample").addEventListener("change", () => loadSample(byId("sample").value));
byId("mode").addEventListener("change", modeHint);
byId("ticket-form").addEventListener("submit", async event => {
  event.preventDefault();
  byId("process").disabled = true;
  byId("request-feedback").textContent = "Processing request…";
  const ticket = { ticket_id: byId("ticket-id").value, sender_email: byId("email").value, message: byId("message").value };
  if (byId("order-id").value.trim()) ticket.order_id = byId("order-id").value.trim();
  try {
    const run = await api("/api/process", { mode: byId("mode").value, ticket });
    selectedId = caseKey(run);
    byId("search").value = "";
    await refresh();
    selectedId = caseKey(run);
    setFilter("all");
    byId("request-dialog").close();
    feedback(run.replayed ? "Saved result returned. No repeat model call." : "Request processed. Check the decision and next step.");
  } catch (error) {
    byId("request-feedback").textContent = error.message;
  } finally {
    byId("process").disabled = false;
  }
});
byId("load-scenarios").addEventListener("click", async () => {
  byId("load-scenarios").disabled = true;
  try {
    await api("/api/demo", { mode: "demo" });
    await refresh();
    feedback("14 baseline requests loaded. No AI calls were made.");
  } catch (error) { feedback(error.message, true); }
  finally { byId("load-scenarios").disabled = false; }
});
refresh().then(() => {
  state.samples.forEach((sample, index) => {
    const option = element("option", `${sampleLabels[index] || "Sample request"} · ${sample.ticket_id}`);
    option.value = index;
    byId("sample").append(option);
  });
  byId("sample").value = "0";
}).catch(error => feedback(error.message, true));
