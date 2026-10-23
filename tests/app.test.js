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
  assert.equal(payload.action, "approve_draft");
  assert.equal(app.byId("case-state").textContent, "Approved");
  assert.equal(app.byId("unsaved-label").hidden, true);
  assert.equal(app.byId("approve-draft").disabled, false);
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
