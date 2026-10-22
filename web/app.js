"use strict";
const byId = (id) => document.getElementById(id);
let state = { runs: [], samples: [] };
let selectedId = null;
let filter = "all";
const titles = {
  return_instructions_draft: "Return instructions prepared",
  tracking_update_draft: "Tracking update prepared",
  order_reference_request_draft: "Ask for the order reference",
  human_review: "A person needs to review this"
};
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The request could not be processed.");
  return result;
}
function feedback(text, error = false) {
  byId("feedback").textContent = text;
  byId("feedback").className = error ? "error" : "";
}
function key(run) { return run.mode + ":" + run.ticket_id; }
function selectSample(index) {
  const sample = state.samples[index];
  byId("ticket-id").value = sample ? sample.ticket_id : "CUSTOM-" + Date.now();
  byId("email").value = sample ? sample.sender_email : "alex@example.com";
  byId("order-id").value = sample && sample.order_id ? sample.order_id : "";
  byId("message").value = sample ? sample.message : "";
}
function render() {
  const runs = state.runs;
  byId("total-count").textContent = runs.length;
  byId("draft-count").textContent = runs.filter(r => r.route !== "human_review").length;
  byId("review-count").textContent = runs.filter(r => r.route === "human_review").length;
  byId("live-count").textContent = runs.filter(r => r.mode === "live" && r.extraction).length;
  byId("run-list").replaceChildren();
  const visible = runs.filter(r => filter === "all" || (filter === "review" ? r.route === "human_review" : r.route !== "human_review"));
  for (const run of visible) {
    const row = node("button", undefined, "run-row" + (key(run) === selectedId ? " selected" : ""));
    row.type = "button";
    const label = node("div");
    label.append(node("strong", run.ticket_id), node("small", run.ticket.message));
    row.append(label, node("span", run.route === "human_review" ? "Review" : "Draft ready", "route-pill" + (run.route === "human_review" ? " review" : "")));
    row.addEventListener("click", () => { selectedId = key(run); render(); });
    byId("run-list").append(row);
  }
  if (runs.length && !visible.length) byId("run-list").append(node("p", "No requests in this view.", "hint"));
  const run = runs.find(r => key(r) === selectedId);
  byId("empty").hidden = Boolean(run);
  byId("detail").hidden = !run;
  if (!run) return;
  byId("detail-id").textContent = run.ticket_id;
  byId("detail-route").textContent = titles[run.route] || run.route;
  byId("detail-mode").textContent = run.mode === "demo" ? "OFFLINE RULES" : "LIVE AI";
  byId("reason").textContent = run.reason;
  byId("original-message").textContent = run.ticket.message;
  byId("intent").textContent = run.extraction ? "Intent: " + run.extraction.category.replaceAll("_", " ") + " · Evidence: “" + run.extraction.evidence + "” · Confidence score: " + run.extraction.confidence : "No model extraction used for this outcome.";
  byId("checks").replaceChildren();
  byId("checks-section").hidden = !run.checks.length;
  for (const check of run.checks) {
    const row = node("div", undefined, "check" + (check.passed ? "" : " failed"));
    const text = node("div", check.label);
    text.append(node("small", check.detail));
    row.append(node("span", check.passed ? "✓" : "!", "check-icon"), text);
    byId("checks").append(row);
  }
  byId("draft-section").hidden = !run.draft;
  byId("draft").textContent = run.draft || "";
  byId("trace").replaceChildren();
  for (const step of run.trace) {
    const item = node("li");
    item.append(node("strong", step.step), node("small", step.detail));
    byId("trace").append(item);
  }
  byId("run-meta").textContent = "Saved " + new Date(run.created_at).toLocaleString() + " · " + run.duration_ms + " ms · " + run.classifier + ".";
}
async function refresh() {
  state = await api("/api/state");
  byId("live-option").disabled = !state.live_available;
  byId("integration-status").textContent = state.order_source || "LOCAL FIXTURES";
  render();
}
byId("ticket-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  byId("process").disabled = true;
  feedback(byId("mode").value === "live" ? "Calling the model and checking the result…" : "Checking the request…");
  const ticket = { ticket_id: byId("ticket-id").value, sender_email: byId("email").value, message: byId("message").value };
  if (byId("order-id").value.trim()) ticket.order_id = byId("order-id").value.trim();
  try {
    const run = await api("/api/process", { mode: byId("mode").value, ticket });
    selectedId = key(run);
    await refresh();
    feedback(run.replayed ? "Existing result returned. The duplicate was not processed again." : "Saved. Inspect the checks and draft on the right.");
  } catch (error) { feedback(error.message, true); }
  finally { byId("process").disabled = false; }
});
byId("run-demo").addEventListener("click", async () => {
  byId("run-demo").disabled = true;
  try {
    const batch = await api("/api/demo", { mode: "demo" });
    selectedId = key(batch.results[0]);
    await refresh();
    feedback("14 synthetic scenarios loaded. This batch used rules, not an AI model.");
  } catch (error) { feedback(error.message, true); }
  finally { byId("run-demo").disabled = false; }
});
byId("sample").addEventListener("change", () => selectSample(byId("sample").value));
byId("mode").addEventListener("change", () => {
  byId("mode-hint").textContent = byId("mode").value === "live" ? "Submits this message to OpenAI using the server's API key. Use synthetic data only. Results still need policy checks." : "Offline mode demonstrates the workflow. Live AI is a separate, optional mode.";
});
for (const button of document.querySelectorAll(".filter")) {
  button.addEventListener("click", () => {
    filter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach(b => b.classList.toggle("active", b === button));
    render();
  });
}
refresh().then(() => {
  state.samples.forEach((sample, index) => {
    const option = node("option", sample.ticket_id + " · " + sample.message.slice(0, 55));
    option.value = index;
    byId("sample").append(option);
  });
  byId("sample").value = "0";
  selectSample(0);
}).catch(error => feedback(error.message, true));
