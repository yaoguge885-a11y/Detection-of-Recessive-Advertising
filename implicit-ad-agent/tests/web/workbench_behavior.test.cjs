"use strict";

const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tag = "div", value = "") {
    this.tagName = tag.toUpperCase();
    this.value = value;
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
    this.elements = [];
    this.style = {};
  }

  get childElementCount() {
    return this.children.length;
  }

  append(...children) {
    this.children.push(...children.filter(Boolean));
  }

  replaceChildren(...children) {
    this.children = children.filter(Boolean);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  emit(type, event = {}) {
    return this.listeners.get(type)(event);
  }

  setAttribute(name, value) {
    this[name] = String(value);
  }

  focus() {}

  reset() {
    this.resetCalled = true;
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

function response(payload, ok = true, status = 200) {
  return {ok, status, json: async () => payload};
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function waitFor(predicate, message) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await flush();
  }
  assert.fail(message);
}

function textOf(node) {
  return [node.textContent, ...node.children.map(textOf)].join(" ");
}

function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children) {
    const found = find(child, predicate);
    if (found) return found;
  }
  return null;
}

function runResponse(runId, label = "暗广") {
  return {
    verdict_report: {label, review_required: false},
    run_metadata: {run_id: runId},
  };
}

function runRecord(runId, label = "暗广") {
  return {
    verdict_report: {
      label,
      confidence: 0.9,
      review_required: false,
      commercial_intent: {status: "present"},
      disclosure: {status: "missing"},
      judgment_method: "fixture",
      reasons: ["fixture reason"],
      creator_shift: null,
      law_evidence: [],
    },
    run_metadata: {
      run_id: runId,
      status: "completed",
      runtime_mode: "local",
      duration_ms: 12,
      issues: [],
      tool_versions: {},
      model_versions: {},
      retry_count: 0,
      fallback_count: 0,
      trace_ids: [],
    },
    evidence_bundle: {
      items: [], coverage: [], conflicts: [], missing_requirements: [],
    },
    post: {post_id: "post-target", published_at: null, text: "fixture", history: []},
    law_evidence: [],
    run_events: [],
    readable_report: `report ${runId}`,
  };
}

function batchResponse(runId, label = "暗广") {
  return {
    succeeded: 1,
    failed: 0,
    total: 1,
    items: [{index: 0, ok: true, result: runResponse(runId, label)}],
  };
}

function setup(fetchImpl = () => Promise.reject(new Error("unexpected fetch"))) {
  const ids = [
    "submission-status", "runtime-mode", "single-form", "single-text", "single-platform",
    "single-comments", "single-history", "single-capture-complete",
    "single-post-id", "single-creator", "single-published-at", "single-clear",
    "batch-form", "batch-json", "batch-file", "batch-count", "batch-clear",
    "batch-results", "batch-summary", "batch-items", "url-preview-form",
    "url-preview-submit", "url-input", "url-unavailable", "url-capability",
    "url-confirm-form", "url-discard", "url-preview-result", "url-preview-meta",
    "correction-text", "correction-creator", "correction-published-at",
    "correction-media", "correction-comments", "correction-history",
    "correction-capture", "single-recovery", "result-empty", "result-content",
    "verdict-section", "coverage-section", "evidence-section", "creator-shift-section",
    "history-section", "law-section", "trace-section", "report-section", "raw-section",
  ];
  const elements = new Map(ids.map((id) => [id, new FakeElement("div")]));
  elements.get("single-text").value = "fixture input";
  elements.get("single-platform").value = "other";
  elements.get("runtime-mode").value = "local";
  elements.get("single-comments").value = "[]";
  elements.get("single-history").value = "[]";
  elements.get("batch-json").value = '{"items":[{"text":"fixture"}]}';
  elements.get("correction-text").value = "fixture input";
  elements.get("correction-creator").value = "creator";
  elements.get("correction-media").value = "[]";
  elements.get("correction-comments").value = "[]";
  elements.get("correction-history").value = "[]";
  elements.get("correction-capture").value = "{}";
  for (const formId of ["single-form", "batch-form", "url-preview-form", "url-confirm-form"]) {
    const form = elements.get(formId);
    form.elements = [new FakeElement("input")];
  }
  const sandbox = {
    URL,
    document: {
      body: new FakeElement("body"),
      addEventListener() {},
      createElement(tag) { return new FakeElement(tag); },
      getElementById(id) { return elements.get(id); },
    },
    fetch: fetchImpl,
    navigator: {clipboard: {writeText: async () => {}}},
    Blob,
    window: {setTimeout() {}},
  };
  const scriptPath = path.resolve(__dirname, "..", "..", "impad", "web", "workbench.js");
  const script = process.env.WORKBENCH_SCRIPT_REVISION
    ? childProcess.execFileSync(
      "git",
      ["show", `${process.env.WORKBENCH_SCRIPT_REVISION}:implicit-ad-agent/impad/web/workbench.js`],
      {encoding: "utf8", cwd: path.resolve(__dirname, "..", "..", "..")},
    )
    : fs.readFileSync(scriptPath, "utf8");
  vm.runInNewContext(script, sandbox);
  return {elements, sandbox};
}

function submitEvent() {
  return {preventDefault() {}};
}

function callsFor(calls, endpoint) {
  return calls.filter((call) => call.path === endpoint);
}

async function testEvidenceCardsKeepEveryTraceableFieldVisible() {
  const fixture = setup();
  const bundle = {
    items: [{
      evidence_id: "ev-rich-7",
      kind: "explicit_ad_marker",
      source_type: "text",
      status: "observed",
      polarity: "supports",
      strength: 0.91,
      producer: "tool:analyze_text_intent",
      source_ref: "post.text",
      quote: "品牌合作",
      limitations: [],
      tool_name: "analyze_text_intent",
      tool_version: "2.4.1",
      call_id: "call-rich-9",
      span: [0, 4],
      bbox: [1, 2, 30, 40],
      related_post_id: "post-history-3",
      comment_ids: ["comment-2", "comment-8"],
    }],
    coverage: [],
    conflicts: [{
      conflict_id: "conflict-1",
      reason: "fixture conflict",
      evidence_ids: ["ev-rich-7", "ev-other-8"],
    }],
    missing_requirements: [],
  };

  fixture.sandbox.renderEvidence(bundle);
  fixture.sandbox.renderCoverage(bundle);
  const card = find(
    fixture.elements.get("evidence-section"),
    (node) => node.dataset.evidenceId === "ev-rich-7",
  );
  assert.ok(card, "the visible evidence card must identify its evidence_id");
  for (const value of [
    "ev-rich-7", "analyze_text_intent", "2.4.1", "call-rich-9",
    "[0,4]", "[1,2,30,40]", "post-history-3", "comment-2", "comment-8",
  ]) {
    assert.match(textOf(card), new RegExp(value.replace(/[.[\]{}()*+?^$\\|]/g, "\\$&")));
  }
  assert.match(textOf(fixture.elements.get("coverage-section")), /ev-rich-7/);
  assert.match(textOf(fixture.elements.get("coverage-section")), /ev-other-8/);
}

async function testLaterSingleSubmissionWinsWhenEarlierRunLoadsLast() {
  const calls = [];
  const fixture = setup((path, options) => {
    const call = {path, options, gate: deferred()};
    calls.push(call);
    return call.gate.promise;
  });
  fixture.sandbox.setupSingleForm();
  const form = fixture.elements.get("single-form");
  const first = form.emit("submit", submitEvent());
  await flush();
  const second = form.emit("submit", submitEvent());
  await flush();
  const posts = callsFor(calls, "/api/v1/analyze");
  assert.equal(posts.length, 2, "each explicit submit must start its own request");
  posts[1].gate.resolve(response(runResponse("run-B", "B")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-B").length === 1, "B run request was not started");
  callsFor(calls, "/api/v1/runs/run-B")[0].gate.resolve(response(runRecord("run-B", "B")));
  await second;
  posts[0].gate.resolve(response(runResponse("run-A", "A")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-A").length === 1, "A run request was not started");
  callsFor(calls, "/api/v1/runs/run-A")[0].gate.resolve(response(runRecord("run-A", "A")));
  await first;

  assert.match(textOf(fixture.elements.get("verdict-section")), /run-B/);
  assert.match(textOf(fixture.elements.get("verdict-section")), /B/);
  assert.equal(fixture.elements.get("submission-status").textContent, "单条分析完成");
}

async function testLaterBatchSubmissionWinsWhenEarlierBatchLoadsLast() {
  const calls = [];
  const fixture = setup((path, options) => {
    const call = {path, options, gate: deferred()};
    calls.push(call);
    return call.gate.promise;
  });
  fixture.sandbox.setupBatchForm();
  const form = fixture.elements.get("batch-form");
  const first = form.emit("submit", submitEvent());
  await flush();
  const second = form.emit("submit", submitEvent());
  await flush();
  const posts = callsFor(calls, "/api/v1/analyze/batch");
  posts[1].gate.resolve(response(batchResponse("run-B", "B")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-B").length === 1, "B batch run request was not started");
  callsFor(calls, "/api/v1/runs/run-B")[0].gate.resolve(response(runRecord("run-B", "B")));
  await second;
  posts[0].gate.resolve(response(batchResponse("run-A", "A")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-A").length === 1, "A batch run request was not started");
  callsFor(calls, "/api/v1/runs/run-A")[0].gate.resolve(response(runRecord("run-A", "A")));
  await first;

  assert.match(textOf(fixture.elements.get("batch-items")), /run-B/);
  assert.doesNotMatch(textOf(fixture.elements.get("batch-items")), /run-A/);
  assert.match(textOf(fixture.elements.get("verdict-section")), /run-B/);
}

async function testBatchViewCannotReplaceNewerSingleIntent() {
  const calls = [];
  const fixture = setup((path, options) => {
    const call = {path, options, gate: deferred()};
    calls.push(call);
    return call.gate.promise;
  });
  fixture.sandbox.setupSingleForm();
  fixture.sandbox.renderBatchResults(batchResponse("run-A", "A"));
  const view = find(fixture.elements.get("batch-items"), (node) => node.textContent === "查看");
  const viewPromise = view.emit("click");
  await flush();
  const singlePromise = fixture.elements.get("single-form").emit("submit", submitEvent());
  await flush();
  callsFor(calls, "/api/v1/analyze")[0].gate.resolve(response(runResponse("run-B", "B")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-B").length === 1, "B single run request was not started");
  callsFor(calls, "/api/v1/runs/run-B")[0].gate.resolve(response(runRecord("run-B", "B")));
  await singlePromise;
  callsFor(calls, "/api/v1/runs/run-A")[0].gate.resolve(response(runRecord("run-A", "A")));
  await viewPromise;

  assert.match(textOf(fixture.elements.get("verdict-section")), /run-B/);
}

async function testUrlConfirmationCannotReplaceNewerSingleIntent() {
  const calls = [];
  const fixture = setup((path, options) => {
    const call = {path, options, gate: deferred()};
    calls.push(call);
    return call.gate.promise;
  });
  fixture.sandbox.setupUrlForms();
  fixture.sandbox.setupSingleForm();
  fixture.sandbox.renderUrlPreview({preview_id: "preview-A", post: {
    text: "fixture", creator_id: "creator", published_at: null,
    media: [], comments: [], history: [], capture_status: {},
  }});
  const confirmPromise = fixture.elements.get("url-confirm-form").emit("submit", submitEvent());
  await flush();
  const singlePromise = fixture.elements.get("single-form").emit("submit", submitEvent());
  await flush();
  callsFor(calls, "/api/v1/analyze")[0].gate.resolve(response(runResponse("run-B", "B")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-B").length === 1, "B URL race run request was not started");
  callsFor(calls, "/api/v1/runs/run-B")[0].gate.resolve(response(runRecord("run-B", "B")));
  await singlePromise;
  callsFor(calls, "/api/v1/import/url/confirm")[0].gate.resolve(response(runResponse("run-A", "A")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-A").length === 1, "A URL run request was not started");
  callsFor(calls, "/api/v1/runs/run-A")[0].gate.resolve(response(runRecord("run-A", "A")));
  await confirmPromise;

  assert.match(textOf(fixture.elements.get("verdict-section")), /run-B/);
}

async function testPersistedSingleRunOffersOnePostRecoveryAndThenRenders() {
  const calls = [];
  const fixture = setup((path, options) => {
    const call = {path, options, gate: deferred()};
    calls.push(call);
    return call.gate.promise;
  });
  fixture.sandbox.setupSingleForm();
  const singlePromise = fixture.elements.get("single-form").emit("submit", submitEvent());
  await flush();
  callsFor(calls, "/api/v1/analyze")[0].gate.resolve(response(runResponse("run-recover", "Recovered")));
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-recover").length === 1, "recovery run request was not started");
  callsFor(calls, "/api/v1/runs/run-recover")[0].gate.reject(new Error("run read unavailable"));
  await singlePromise;

  const recovery = fixture.elements.get("single-recovery");
  assert.equal(callsFor(calls, "/api/v1/analyze").length, 1);
  assert.equal(recovery.hidden, false);
  assert.match(textOf(recovery), /run已持久化/);
  assert.match(textOf(recovery), /run-recover/);
  const retry = find(recovery, (node) => node.textContent === "重试加载");
  assert.ok(retry, "a persisted run must expose a retry action");
  const retryPromise = retry.emit("click");
  await waitFor(() => callsFor(calls, "/api/v1/runs/run-recover").length === 2, "retry did not load the persisted run");
  assert.equal(callsFor(calls, "/api/v1/analyze").length, 1);
  callsFor(calls, "/api/v1/runs/run-recover")[1].gate.resolve(
    response(runRecord("run-recover", "Recovered")),
  );
  await retryPromise;

  assert.equal(recovery.hidden, true);
  assert.match(textOf(fixture.elements.get("verdict-section")), /run-recover/);
  assert.match(textOf(fixture.elements.get("verdict-section")), /Recovered/);
}

async function main() {
  const tests = [
    testEvidenceCardsKeepEveryTraceableFieldVisible,
    testLaterSingleSubmissionWinsWhenEarlierRunLoadsLast,
    testLaterBatchSubmissionWinsWhenEarlierBatchLoadsLast,
    testBatchViewCannotReplaceNewerSingleIntent,
    testUrlConfirmationCannotReplaceNewerSingleIntent,
    testPersistedSingleRunOffersOnePostRecoveryAndThenRenders,
  ];
  const selected = process.env.WORKBENCH_TEST;
  for (const test of tests) {
    if (!selected || test.name === selected) {
      await test();
    }
  }
}

main().catch((error) => {
  process.exitCode = 1;
  throw error;
});
