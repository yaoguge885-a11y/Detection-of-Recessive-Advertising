"use strict";

// Execute the page's real handlers against synthetic DOM/storage doubles.
// This does not open a browser or read any human draft or annotation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");

const sourcePath = process.env.M1_BLIND_HTML_TEST_SOURCE ||
  path.join(__dirname, "..", "generate_m1_qwen_blind_html.py");
const source = fs.readFileSync(sourcePath, "utf8");
const helperNames = source.includes('function draftMatchesContext(') ? ['draftMatchesContext'] : [];
const functions = ["emptyRecord", "ensureRecords", "save", ...helperNames, "load", "recordFor", "fixedMediaMissing",
  "remoteMediaGap", "allMediaViewed", "allRemoteMediaResolved", "allMediaReviewed", "isDone",
  "bindItem", "updateCard", "validateItem", "buildDraftSnapshot"].map(name => {
  const match = source.match(new RegExp("^  function " + name + "\\(.*$", "m"));
  assert.ok(match, "missing page function " + name);
  return match[0];
}).join("\n");

class Field {
  constructor() { this.listeners = {}; this.value = ""; this.textContent = ""; this.checked = false; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  input(value) {
    this.value = value;
    assert.equal(typeof this.listeners.input, "function");
    this.listeners.input({target: this});
  }
}

function harness({evidence = "Synthetic observed evidence", reason = "", storage = new Map(), load = false} = {}) {
  const item = {post_id: "synthetic_4", ordinal: 4, media: []};
  const other = {post_id: "synthetic_6", ordinal: 6, media: []};
  const record = {label: "uncertain", confidence: "0.7", evidence, uncertain_reason: reason,
    evidence_codes: [], reviewed: true, reviewed_at: "2026-10-29T00:00:00Z", media_review_confirmed: true,
    viewed_media_refs: [], remote_media_statuses: {}, remote_open_attempts: {}};
  const fields = Object.fromEntries([".confidence", ".evidence", ".uncertain-reason", ".reviewed",
    ".media-confirm", ".item-head .badge", "[data-errors]"].map(k => [k, new Field()]));
  const card = {querySelector: key => fields[key], querySelectorAll: () => []};
  const context = vm.createContext({state: {attestation: {media_gaps_ack: false}, records: {
    [item.post_id]: record, [other.post_id]: {...record, label: "非广", evidence: "Other synthetic record"}}},
    ITEMS: [item, other], itemKey: x => x.post_id, item, card, META: {manifest_sha256: "synthetic-manifest",
      source_sha256: "synthetic-source", guide_sha256: "synthetic-guide", evidence_code_scheme: "annotation_guide_table_v1",
      evidence_code_dictionary_sha256: "synthetic-dictionary"},
    ROLE: "B", REVIEW_SCHEMA_VERSION: helperNames.length ? "m1_blind_human_review_v3" : "m1_blind_human_review_v2", STORAGE_KEY: "synthetic-draft-B",
    localStorage: {setItem: (key, value) => storage.set(key, value), getItem: key => storage.get(key)},
    setMessage: () => {}, renderNav: () => {}, CSS: {escape: x => x},
    document: {querySelector: () => card}, Date, console});
  vm.runInContext(functions, context);
  if (load) vm.runInContext("load()", context);
  vm.runInContext("bindItem(item); updateCard(item,card)", context);
  return {context, fields, storage, record: context.state.records[item.post_id]};
}

test("entering uncertainty reason immediately clears old error and updates completion", () => {
  const h = harness();
  assert.match(h.fields["[data-errors]"].textContent, /uncertain 必须填写原因/);
  h.fields[".uncertain-reason"].input("Synthetic missing video evidence");
  assert.equal(h.record.uncertain_reason, "Synthetic missing video evidence");
  assert.equal(h.fields["[data-errors]"].textContent, "");
  assert.equal(h.fields[".item-head .badge"].textContent, "已完成");
});

test("deleting a reason restores the error rather than leaving a false completed badge", () => {
  const h = harness({reason: "Synthetic reason"});
  assert.equal(h.fields[".item-head .badge"].textContent, "已完成");
  h.fields[".uncertain-reason"].input("   ");
  assert.match(h.fields["[data-errors]"].textContent, /uncertain 必须填写原因/);
  assert.equal(h.fields[".item-head .badge"].textContent, "待完成");
});

test("evidence edits update validation without replacing or losing the reason", () => {
  const h = harness({evidence: "", reason: "Synthetic reason"});
  h.fields[".evidence"].input("Synthetic evidence supplied");
  assert.equal(h.fields["[data-errors]"].textContent, "");
  assert.equal(h.fields[".item-head .badge"].textContent, "已完成");
  assert.equal(h.record.uncertain_reason, "Synthetic reason");
  h.fields[".evidence"].input("");
  assert.match(h.fields["[data-errors]"].textContent, /请填写证据说明/);
  assert.equal(h.fields[".item-head .badge"].textContent, "待完成");
});

test("typing a reason does not bypass the separate evidence requirement", () => {
  const h = harness({evidence: ""});
  h.fields[".uncertain-reason"].input("Synthetic reason");
  assert.doesNotMatch(h.fields["[data-errors]"].textContent, /uncertain 必须填写原因/);
  assert.match(h.fields["[data-errors]"].textContent, /请填写证据说明/);
  assert.equal(h.fields[".item-head .badge"].textContent, "待完成");
});

test("input is persisted with the existing storage key and other records survive reload", () => {
  const h = harness();
  h.fields[".uncertain-reason"].input("Saved synthetic reason");
  h.fields[".evidence"].input("Saved synthetic evidence");
  assert.ok(h.storage.has("synthetic-draft-B"));
  const restored = harness({storage: h.storage, load: true});
  assert.equal(restored.record.uncertain_reason, "Saved synthetic reason");
  assert.equal(restored.record.evidence, "Saved synthetic evidence");
  assert.equal(restored.context.state.records.synthetic_6.evidence, "Other synthetic record");
});

test("unfinished draft snapshot preserves existing entries without certifying completion", () => {
  const h = harness({evidence: "", reason: "User's unfinished reason"});
  h.record.reviewed = false;
  h.record.media_review_confirmed = false;
  const before = JSON.stringify(h.context.state);
  const snapshot = vm.runInContext("buildDraftSnapshot()", h.context);
  assert.equal(snapshot.schema_version, helperNames.length ? "m1_blind_draft_snapshot_v2" : "m1_blind_draft_snapshot_v1");
  assert.equal(snapshot.formal_evidence, false);
  assert.equal(snapshot.status, "draft_incomplete_or_unverified");
  assert.equal(JSON.stringify(snapshot.state), before);
  assert.equal(JSON.stringify(h.context.state), before);
  assert.equal(snapshot.state.records.synthetic_4.reviewed, false);
  assert.equal(snapshot.state.records.synthetic_4.media_review_confirmed, false);
  assert.equal(snapshot.state.records.synthetic_4.evidence, "");
  snapshot.state.records.synthetic_4.evidence = "Changed copy";
  assert.equal(h.record.evidence, "");
  assert.equal(snapshot.sample_count, 2);
  assert.equal(snapshot.ordered_post_ids.join(","), "synthetic_4,synthetic_6");
});
