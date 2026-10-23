const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const { JSDOM } = require("jsdom");

const html = readFileSync("web/index.html", "utf8");
const script = readFileSync("web/app.js", "utf8");
const samples = JSON.parse(readFileSync("data/tickets.json", "utf8"));
const policy = JSON.parse(readFileSync("data/policy.json", "utf8"));
const copy = (value) => JSON.parse(JSON.stringify(value));
const flush = async () => {
  await new Promise(setImmediate);
  await new Promise(setImmediate);
};

function run(ticketId, route) {
  const ticket = samples.find((ticket) => ticket.ticket_id === ticketId);
  const draft =
    route === "human_review" ? null : "Please confirm the return item.";
  return {
    ticket_id: ticketId,
    ticket: copy(ticket),
    mode: "demo",
    route,
    attempt: 1,
    can_reprocess: false,
    reason:
      route === "human_review"
        ? "Order value requires review."
        : "Checks passed.",
    draft,
    created_at: "2026-10-23T08:00:00+00:00",
    order: null,
    extraction: null,
    checks: [],
    trace: [],
    activity: [],
    review: {
      state: draft ? "draft_ready" : "needs_review",
      revision: 0,
      draft,
      note: "",
    },
  };
}

async function desk(t, options = {}) {
  const dom = new JSDOM(html, {
    url: "http://127.0.0.1:8765/",
    runScripts: "outside-only",
  });
  t.after(() => dom.window.close());
  const window = dom.window;
  window.HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  window.HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  window.crypto.randomUUID = randomUUID;
  const state = {
    runs: [
      run("DEMO-005", "human_review"),
      run("DEMO-001", "return_instructions_draft"),
    ],
    samples: copy(samples).reverse(),
    policy,
    live_available: false,
    evaluation: null,
    orchestration: null,
  };
  const requests = [];
  const retryResults = new Map();
  if (options.retryFailure) {
    Object.assign(state.runs[0], {
      reason: "Classification unavailable: Provider unavailable",
      processing_error: "extraction",
      can_reprocess: true,
    });
    state.runs[0].attempts = [copy(state.runs[0])];
  }
  window.fetch = async (path, config = {}) => {
    const payload = config.body ? JSON.parse(config.body) : undefined;
    requests.push({ path, payload });
    let result = state;
    let status = 200;
    if (path === "/api/review") {
      const target = state.runs.find(
        (row) => row.ticket_id === payload.ticket_id,
      );
      if (options.conflict) {
        target.review = {
          state: "approved",
          revision: 1,
          draft: "Another operator's draft",
          note: "Newer note",
        };
        result = { error: "Another decision changed this case." };
        status = 409;
      } else {
        target.review = {
          state: "approved",
          revision: 1,
          draft: payload.draft,
          note: payload.note,
        };
        result = { review: target.review };
      }
    } else if (path === "/api/reprocess") {
      const target = state.runs.find(
        (row) => row.ticket_id === payload.ticket_id,
      );
      if (!retryResults.has(payload.event_id)) {
        const previous = copy(target);
        Object.assign(target, {
          attempt: 2,
          can_reprocess: false,
          processing_error: null,
          route: "return_instructions_draft",
          draft: "Recovered draft",
          reason: "Checks passed.",
          review: {
            state: "draft_ready",
            revision: 0,
            draft: "Recovered draft",
            note: "",
          },
          activity: [
            {
              kind: "reprocess",
              attempt: 2,
              detail: payload.note,
              created_at: target.created_at,
            },
          ],
        });
        target.attempts = [previous, copy(target)];
        retryResults.set(payload.event_id, copy(target));
      }
      result = retryResults.get(payload.event_id);
      if (options.loseRetryResponse) {
        options.loseRetryResponse = false;
        throw new Error("Connection interrupted");
      }
    } else if (path === "/api/process") {
      status = options.processStatus || 200;
      result =
        status === 200 ? state.runs[1] : { error: "Invalid order reference." };
    } else if (path === "/api/demo") {
      result = { results: state.runs };
    }
    return { ok: status < 400, status, json: async () => copy(result) };
  };
  window.eval(script);
  await flush();
  const byId = (id) => window.document.getElementById(id);
  const select = (id) =>
    window.document.querySelector(`tr[data-key="demo:${id}"]`).click();
  const input = (id, value) => {
    byId(id).value = value;
    byId(id).dispatchEvent(new window.Event("input", { bubbles: true }));
  };
  return { window, byId, select, input, requests, state, options };
}

test("queue search includes the sender and clears details for an empty result", async (t) => {
  const app = await desk(t);
  app.input("search", "alex@example.com");
  assert.equal(app.byId("case-rows").children.length, 1);
  assert.equal(app.byId("case-id").textContent, "DEMO-001");
  app.input("search", "no such customer");
  assert.equal(app.byId("case-rows").children.length, 0);
  assert.equal(app.byId("case-detail").hidden, true);
  assert.equal(app.byId("no-selection").hidden, false);
});

test("draft and note edits survive case switches and reset restores saved values", async (t) => {
  const app = await desk(t);
  app.select("DEMO-001");
  app.input("draft-text", "My edited draft");
  app.input("review-note", "Check the item first");
  app.select("DEMO-005");
  app.select("DEMO-001");
  assert.equal(app.byId("draft-text").value, "My edited draft");
  assert.equal(app.byId("review-note").value, "Check the item first");
  assert.equal(app.byId("unsaved-label").hidden, false);
  app.byId("reset-edits").click();
  assert.equal(app.byId("draft-text").value, "Please confirm the return item.");
  assert.equal(app.byId("review-note").value, "");
  assert.equal(app.byId("unsaved-label").hidden, true);
});

test("approval submits the edited draft and revision then displays the saved state", async (t) => {
  const app = await desk(t);
  app.select("DEMO-001");
  app.input("draft-text", "Edited response");
  app.input("review-note", "Order checked");
  app.byId("approve-draft").click();
  await flush();
  const payload = app.requests.find(
    (request) => request.path === "/api/review",
  ).payload;
  assert.equal(payload.draft, "Edited response");
  assert.equal(payload.note, "Order checked");
  assert.equal(payload.expected_revision, 0);
  assert.equal(payload.expected_attempt, 1);
  assert.equal(payload.action, "approve_draft");
  assert.equal(app.byId("case-state").textContent, "Approved");
  assert.equal(app.byId("unsaved-label").hidden, true);
  assert.equal(app.byId("approve-draft").disabled, false);
});

test("retry needs a note and keeps the original failure visible after recovery", async (t) => {
  const app = await desk(t, { retryFailure: true });
  assert.equal(app.byId("retry-processing").hidden, false);
  app.byId("retry-processing").click();
  await flush();
  assert.equal(
    app.requests.filter((r) => r.path === "/api/reprocess").length,
    0,
  );
  app.input("review-note", "Provider recovered.");
  app.byId("retry-processing").click();
  await flush();
  const payload = app.requests.find((r) => r.path === "/api/reprocess").payload;
  assert.equal(payload.expected_attempt, 1);
  assert.equal(payload.expected_revision, 0);
  assert.equal(payload.note, "Provider recovered.");
  assert.equal("draft" in payload, false);
  assert.equal(app.byId("retry-processing").hidden, true);
  assert.match(app.byId("case-meta").textContent, /Attempt 2/);
  assert.equal(app.byId("attempt-history").hidden, false);
  assert.match(app.byId("attempt-history").textContent, /Provider unavailable/);
  assert.match(app.byId("activity").textContent, /Processing retried/);
});

test("a lost retry response reuses its event ID instead of starting another attempt", async (t) => {
  const app = await desk(t, { retryFailure: true, loseRetryResponse: true });
  app.input("review-note", "Service restored.");
  app.byId("retry-processing").click();
  await flush();
  assert.match(app.byId("feedback").textContent, /Connection interrupted/);
  assert.equal(app.byId("retry-processing").disabled, false);
  app.byId("retry-processing").click();
  await flush();
  const retries = app.requests.filter((r) => r.path === "/api/reprocess");
  assert.equal(retries.length, 2);
  assert.equal(retries[0].payload.event_id, retries[1].payload.event_id);
  assert.equal(app.state.runs[0].attempt, 2);
});

test("edits from an earlier attempt keep their attempt number after refresh", async (t) => {
  const app = await desk(t, { conflict: true });
  app.select("DEMO-001");
  app.input("draft-text", "Old attempt's edited draft");
  app.state.runs.find((row) => row.ticket_id === "DEMO-001").attempt = 2;
  app.byId("refresh").click();
  await flush();
  app.byId("approve-draft").click();
  await flush();
  const payload = app.requests.find((r) => r.path === "/api/review").payload;
  assert.equal(payload.expected_attempt, 1);
  assert.match(app.byId("feedback").textContent, /Reset edits/);
});

test("a stale revision preserves unsaved text until the operator resets it", async (t) => {
  const app = await desk(t, { conflict: true });
  app.select("DEMO-001");
  app.input("draft-text", "Unsaved draft");
  app.byId("approve-draft").click();
  await flush();
  assert.equal(app.byId("draft-text").value, "Unsaved draft");
  assert.equal(app.byId("unsaved-label").hidden, false);
  assert.match(app.byId("feedback").textContent, /Reset edits/);
  assert.equal(app.byId("approve-draft").disabled, false);
  app.byId("reset-edits").click();
  assert.equal(app.byId("draft-text").value, "Another operator's draft");
  assert.equal(app.byId("review-note").value, "Newer note");
});

test("an exception requires a note before sending a review action", async (t) => {
  const app = await desk(t);
  app.byId("mark-reviewed").click();
  await flush();
  assert.equal(
    app.requests.filter((request) => request.path === "/api/review").length,
    0,
  );
  assert.match(app.byId("feedback").textContent, /Add a note/);
});

test("sample labels and content follow IDs even when fixtures are reordered", async (t) => {
  const app = await desk(t);
  const option = [...app.byId("sample").options].find(
    (item) => item.value === "DEMO-005",
  );
  assert.equal(option.textContent, "High-value order · DEMO-005");
  app.byId("sample").value = "DEMO-005";
  app.byId("new-request").click();
  assert.match(app.byId("message").value, /ORD-1004/);
  assert.equal(app.byId("email").value, "leo@example.com");
});

test("failed submissions show the error and leave the form usable", async (t) => {
  const app = await desk(t, { processStatus: 400 });
  app.byId("new-request").click();
  app
    .byId("ticket-form")
    .dispatchEvent(
      new app.window.Event("submit", { bubbles: true, cancelable: true }),
    );
  await flush();
  assert.equal(app.byId("request-dialog").open, true);
  assert.equal(app.byId("process").disabled, false);
  assert.equal(
    app.byId("request-feedback").textContent,
    "Invalid order reference.",
  );
});

test("customer markup is displayed as text, and absent reports have an empty state", async (t) => {
  const app = await desk(t);
  const message = '<img src=x onerror="alert(1)"> return ORD-1001';
  app.state.runs[1].ticket.message = message;
  app.byId("refresh").click();
  await flush();
  app.select("DEMO-001");
  assert.equal(app.byId("original-message").textContent, message);
  assert.equal(app.byId("original-message").querySelector("img"), null);
  assert.equal(app.byId("evaluation-empty").hidden, false);
});

test("a matching review route still shows a mismatched intent in evaluation", async (t) => {
  const app = await desk(t);
  app.state.evaluation = {
    model: "test-provider",
    case_count: 1,
    route_matches: 1,
    category_case_count: 1,
    category_matches: 0,
    validated_live_extractions: 1,
    review_required_but_drafted: 0,
    unnecessary_escalations: 0,
    cases: [
      {
        id: "METRIC-001",
        expected_category: "payment_problem",
        actual_category: "damaged_item",
        category_matched: false,
        expected_route: "human_review",
        actual_route: "human_review",
        matched: true,
      },
    ],
  };
  app.byId("refresh").click();
  await flush();
  assert.match(
    app.byId("evaluation-summary").textContent,
    /Labelled intents matched/,
  );
  const row = app.byId("evaluation-rows").textContent;
  assert.match(row, /payment problem/);
  assert.match(row, /damaged item/);
  assert.match(row, /Mismatch/);
});
