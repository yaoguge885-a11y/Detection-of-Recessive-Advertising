"use strict";

const state = {
  capabilities: null,
  activePreview: null,
  activeResponse: null,
  activeRun: null,
  batch: null,
};

const byId = (id) => document.getElementById(id);

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  if (className) {
    node.className = className;
  }
  return node;
}

function replaceChildren(target, ...children) {
  target.replaceChildren(...children.filter(Boolean));
}

function setSubmissionStatus(message, tone = "neutral") {
  const target = byId("submission-status");
  target.textContent = message;
  target.dataset.tone = tone;
}

function setBusy(form, busy) {
  for (const control of form.elements) {
    control.disabled = busy;
  }
  form.dataset.state = busy ? "loading" : "idle";
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      ...(options.headers || {}),
    },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail;
    const message = (
      detail && typeof detail === "object" && detail.message
    ) || (
      typeof detail === "string" && detail
    ) || `请求失败（HTTP ${response.status}）`;
    const error = new Error(message);
    error.code = (
      detail && typeof detail === "object" && detail.code
    ) || `http_${response.status}`;
    throw error;
  }
  return payload;
}

function parseJson(text, label) {
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${label}不是合法JSON`);
  }
}

function parseJsonArray(text, label) {
  const value = parseJson(text, label);
  if (!Array.isArray(value)) {
    throw new Error(`${label}必须是JSON数组`);
  }
  return value;
}

function parseJsonObject(text, label) {
  const value = parseJson(text, label);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label}必须是JSON对象`);
  }
  return value;
}

function parseBatchPayload(text) {
  const value = parseJson(text, "批量请求");
  const items = Array.isArray(value) ? value : value && value.items;
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("批量请求必须包含至少一条items");
  }
  const maximum = state.capabilities?.batch_analysis?.max_items || 50;
  if (items.length > maximum) {
    throw new Error(`批量请求不能超过${maximum}条`);
  }
  return {items};
}

function heading(title, detail) {
  const wrapper = element("div", null, "section-heading");
  wrapper.append(element("h2", title));
  if (detail) {
    wrapper.append(element("span", detail, "section-detail"));
  }
  return wrapper;
}

function definitionList(entries) {
  const list = element("dl", null, "definition-grid");
  for (const [term, value] of entries) {
    list.append(element("dt", term), element("dd", value ?? "未知"));
  }
  return list;
}

function listOrEmpty(values, emptyText) {
  const list = element("ul");
  if (!values || values.length === 0) {
    list.append(element("li", emptyText, "muted"));
    return list;
  }
  for (const value of values) {
    list.append(element("li", value));
  }
  return list;
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(3) : "未知";
}

function formatTime(value) {
  if (!value) {
    return "时间未知";
  }
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? String(value)
    : date.toLocaleString("zh-CN", {hour12: false});
}

function jsonText(value) {
  return JSON.stringify(value, null, 2);
}

function setupTabs() {
  const tabs = [
    ["single-tab", "single-panel"],
    ["batch-tab", "batch-panel"],
    ["url-tab", "url-panel"],
  ].map(([tabId, panelId]) => ({
    tab: byId(tabId),
    panel: byId(panelId),
  }));

  function activate(index, focus = false) {
    tabs.forEach((item, itemIndex) => {
      const selected = itemIndex === index;
      item.tab.setAttribute("aria-selected", String(selected));
      item.tab.tabIndex = selected ? 0 : -1;
      item.panel.hidden = !selected;
    });
    if (focus) {
      tabs[index].tab.focus();
    }
  }

  tabs.forEach((item, index) => {
    item.tab.addEventListener("click", () => activate(index));
    item.tab.addEventListener("keydown", (event) => {
      if (![
        "ArrowLeft", "ArrowRight", "Home", "End",
      ].includes(event.key)) {
        return;
      }
      event.preventDefault();
      const next = event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (
            index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length
          ) % tabs.length;
      activate(next, true);
    });
  });
}

async function loadCapabilities() {
  const [health, capabilities] = await Promise.all([
    fetchJson("/health"),
    fetchJson("/api/v1/capabilities"),
  ]);
  state.capabilities = capabilities;
  updateBatchCount();
  byId("health-status").textContent = health.status === "ok"
    ? "API 正常"
    : "API 状态未知";
  byId("capability-status").textContent = (
    `${capabilities.detection_tools}个工具 · `
    + `批量上限${capabilities.batch_analysis.max_items}`
  );
  const platforms = capabilities.url_import.platforms || [];
  const available = platforms.length > 0;
  byId("url-preview-submit").disabled = !available;
  byId("url-input").disabled = !available;
  byId("url-unavailable").hidden = available;
  byId("url-unavailable").textContent = available
    ? ""
    : "当前未配置平台URL适配器；请使用单条或批量输入。";
  byId("url-capability").textContent = available
    ? `URL：${platforms.map((item) => item.platform).join("、")}`
    : "URL：未配置";
  return capabilities;
}

function renderVerdict(record) {
  const report = record.verdict_report;
  const metadata = record.run_metadata;
  const target = byId("verdict-section");
  const badge = element("span", report.label, "verdict-badge");
  badge.dataset.label = report.label;
  replaceChildren(
    target,
    heading("判定摘要", metadata.run_id),
    badge,
    definitionList([
      ["置信度", formatScore(report.confidence)],
      ["需要复核", report.review_required ? "是" : "否"],
      ["商业意图", report.commercial_intent.status],
      ["披露状态", report.disclosure.status],
      ["运行状态", metadata.status],
      ["运行模式", metadata.runtime_mode],
      ["耗时", metadata.duration_ms == null
        ? "未知"
        : `${metadata.duration_ms} ms`],
      ["判断方法", report.judgment_method],
    ]),
    element("h3", "判定理由"),
    listOrEmpty(report.reasons, "没有附加理由"),
  );
}

function renderCoverage(bundle) {
  const target = byId("coverage-section");
  const grid = element("div", null, "coverage-grid");
  for (const coverage of bundle.coverage || []) {
    const card = element("article", null, "coverage-card");
    card.dataset.status = coverage.status;
    card.append(
      element("h3", coverage.modality),
      element("p", coverage.status, "status-text"),
      element("p", `证据：${coverage.evidence_ids.length}`),
    );
    grid.append(card);
  }
  const conflicts = element("div", null, "conflict-list");
  for (const conflict of bundle.conflicts || []) {
    conflicts.append(
      element(
        "article",
        `${conflict.reason} · ${conflict.evidence_ids.join("、")}`,
        "conflict-card",
      ),
    );
  }
  replaceChildren(
    target,
    heading("覆盖、缺失与冲突"),
    grid,
    element("h3", "缺失要求"),
    listOrEmpty(bundle.missing_requirements, "没有记录缺失要求"),
    element("h3", "证据冲突"),
    conflicts.childElementCount
      ? conflicts
      : element("p", "没有记录证据冲突", "muted"),
  );
}

function renderEvidence(bundle) {
  const target = byId("evidence-section");
  const groups = new Map();
  for (const item of bundle.items || []) {
    const key = item.source_type || "metadata";
    groups.set(key, [...(groups.get(key) || []), item]);
  }
  const content = element("div");
  for (const [sourceType, items] of groups) {
    content.append(element("h3", sourceType));
    const grid = element("div", null, "evidence-grid");
    for (const item of items) {
      const card = element("article", null, "evidence-card");
      card.dataset.polarity = item.polarity;
      card.dataset.status = item.status;
      card.append(
        element("h4", item.kind),
        definitionList([
          ["状态", item.status],
          ["极性", item.polarity],
          ["强度", formatScore(item.strength)],
          ["生产者", item.producer],
          ["来源", item.source_ref],
          ["关联帖子", item.related_post_id],
        ]),
        element("p", item.quote || "没有可显示引用", "evidence-quote"),
        listOrEmpty(item.limitations, "没有记录局限"),
      );
      grid.append(card);
    }
    content.append(grid);
  }
  replaceChildren(
    target,
    heading("证据画布", `${bundle.items.length}条`),
    content.childElementCount
      ? content
      : element("p", "当前没有正向证据项", "muted"),
  );
}

function renderCreatorShift(report) {
  const target = byId("creator-shift-section");
  const shift = report.creator_shift;
  if (!shift) {
    replaceChildren(
      target,
      heading("CreatorShift"),
      element("p", "本次运行没有CreatorShift摘要", "muted"),
    );
    return;
  }
  const deltas = Object.entries(shift.feature_deltas || {})
    .map(([name, value]) => `${name}: ${Number(value).toFixed(3)}`);
  replaceChildren(
    target,
    heading("CreatorShift", shift.status),
    definitionList([
      ["历史数量", `${shift.history_count}/${shift.required_history}`],
      ["池化方法", shift.pooling_method],
      ["偏移分数", formatScore(shift.shift_score)],
      ["特征版本", shift.feature_version],
      ["运行版本", shift.runtime_version],
      ["窗口开始", formatTime(shift.window_start)],
      ["窗口结束", formatTime(shift.window_end)],
    ]),
    element("h3", "主要特征"),
    listOrEmpty(shift.top_features, "没有主要特征"),
    element("h3", "特征变化"),
    listOrEmpty(deltas, "没有数值变化"),
    element("h3", "局限"),
    listOrEmpty(shift.limitations, "没有附加局限"),
  );
}

function renderHistory(post) {
  const target = byId("history-section");
  const entries = [...(post.history || [])].sort((left, right) => {
    if (!left.published_at && !right.published_at) return 0;
    if (!left.published_at) return 1;
    if (!right.published_at) return -1;
    return new Date(left.published_at) - new Date(right.published_at);
  });
  const timeline = element("ol", null, "timeline");
  for (const entry of entries) {
    const item = element("li", null, "timeline-item");
    item.append(
      element("time", formatTime(entry.published_at)),
      element("strong", entry.post_id),
      element("p", entry.text),
    );
    timeline.append(item);
  }
  const targetItem = element("li", null, "timeline-item target-post");
  targetItem.append(
    element("time", formatTime(post.published_at)),
    element("strong", `${post.post_id}（目标帖）`),
    element("p", post.text),
  );
  timeline.append(targetItem);
  replaceChildren(
    target,
    heading("创作者历史时间线", `${entries.length}条历史`),
    timeline,
  );
}

function safeLawLink(source) {
  try {
    const url = new URL(source);
    if (url.protocol !== "https:") {
      return element("span", source);
    }
    const link = element("a", "打开来源");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  } catch {
    return element("span", source || "来源未知");
  }
}

function renderLawEvidence(report) {
  const target = byId("law-section");
  const grid = element("div", null, "law-grid");
  for (const citation of report.law_evidence || []) {
    const card = element("article", null, "law-card");
    card.append(
      element("h3", citation.document_title),
      definitionList([
        ["条款", citation.article_id],
        ["版本", citation.document_version],
        ["检索分数", formatScore(citation.retrieval_score)],
        ["重排分数", formatScore(citation.rerank_score)],
      ]),
      element("blockquote", citation.quote || "没有可显示引文"),
      safeLawLink(citation.source_path_or_url),
      listOrEmpty(citation.limitations, "没有附加局限"),
    );
    grid.append(card);
  }
  replaceChildren(
    target,
    heading("法规引用"),
    grid.childElementCount
      ? grid
      : element("p", "检索未返回可靠引用", "muted"),
  );
}

function renderTrace(record) {
  const target = byId("trace-section");
  const events = [...(record.run_events || [])].sort(
    (left, right) => new Date(left.timestamp) - new Date(right.timestamp)
  );
  const list = element("div", null, "event-list");
  for (const event of events) {
    list.append(
      definitionList([
        ["时间", formatTime(event.timestamp)],
        ["事件", event.event_type],
        ["阶段", event.stage],
        ["工具", event.tool_name],
        ["调用ID", event.call_id],
        ["数据", jsonText(event.data)],
      ]),
    );
  }
  replaceChildren(
    target,
    heading("运行轨迹", `${events.length}个事件`),
    list,
    element("h3", "运行问题"),
    listOrEmpty(
      (record.run_metadata.issues || []).map(
        (issue) => `${issue.stage}/${issue.code}: ${issue.message}`
      ),
      "没有记录运行问题",
    ),
    element("h3", "版本与计数"),
    definitionList([
      ["工具版本", jsonText(record.run_metadata.tool_versions)],
      ["模型版本", jsonText(record.run_metadata.model_versions)],
      ["重试", record.run_metadata.retry_count],
      ["回落", record.run_metadata.fallback_count],
      ["Trace IDs", record.run_metadata.trace_ids.join("、")],
    ]),
  );
}

function actionButton(label, handler) {
  const button = element("button", label, "secondary");
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

function updateBatchCount() {
  try {
    const parsed = parseJson(byId("batch-json").value, "批量请求");
    const items = Array.isArray(parsed) ? parsed : parsed?.items;
    const count = Array.isArray(items) ? items.length : 0;
    const maximum = state.capabilities?.batch_analysis?.max_items || 50;
    byId("batch-count").textContent = `${count} / ${maximum}`;
  } catch {
    byId("batch-count").textContent = "JSON待修正";
  }
}

function renderBatchResults(batch) {
  state.batch = batch;
  byId("batch-results").hidden = false;
  byId("batch-summary").textContent = (
    `${batch.succeeded}成功 / ${batch.failed}失败 / ${batch.total}总计`
  );
  const rows = element("div", null, "batch-item-list");
  for (const item of batch.items) {
    const row = element("article", null, "batch-item");
    row.dataset.ok = String(item.ok);
    row.append(element("strong", `#${item.index + 1}`));
    if (item.ok) {
      const report = item.result.verdict_report;
      const metadata = item.result.run_metadata;
      row.append(
        element("span", report.label, "batch-label"),
        element(
          "span",
          report.review_required ? "需复核" : "已判定",
        ),
        element("code", metadata.run_id),
        actionButton("查看", async () => {
          try {
            setSubmissionStatus(`正在加载第${item.index + 1}条结果`);
            await loadAndRenderRun(item.result);
            setSubmissionStatus("批量结果已加载", "success");
          } catch (error) {
            setSubmissionStatus(error.message, "error");
          }
        }),
      );
    } else {
      row.append(
        element("span", item.error.code, "error-code"),
        element("span", item.error.message),
      );
    }
    rows.append(row);
  }
  replaceChildren(byId("batch-items"), rows);
}

function renderReport(record) {
  const pre = element("pre", record.readable_report, "report-text");
  replaceChildren(
    byId("report-section"),
    heading("可读报告"),
    pre,
    actionButton("复制Markdown", () => copyText(
      record.readable_report,
      "Markdown报告已复制",
    )),
    actionButton("下载Markdown", () => downloadText(
      `${record.run_metadata.run_id}.md`,
      record.readable_report,
      "text/markdown;charset=utf-8",
    )),
  );
}

function renderRaw(record, response) {
  replaceChildren(
    byId("raw-section"),
    heading("原始JSON"),
    element("h3", "分析响应"),
    element("pre", jsonText(response), "raw-json"),
    element("h3", "完整RunRecord"),
    element("pre", jsonText(record), "raw-json"),
    actionButton("复制Run JSON", () => copyText(
      jsonText(record),
      "Run JSON已复制",
    )),
    actionButton("下载Run JSON", () => downloadText(
      `${record.run_metadata.run_id}.json`,
      jsonText(record),
      "application/json;charset=utf-8",
    )),
  );
}

function renderRun(record, response) {
  state.activeRun = record;
  state.activeResponse = response;
  byId("result-empty").hidden = true;
  byId("result-content").hidden = false;
  renderVerdict(record);
  renderCoverage(record.evidence_bundle);
  renderEvidence(record.evidence_bundle);
  renderCreatorShift(record.verdict_report);
  renderHistory(record.post);
  renderLawEvidence(record.verdict_report);
  renderTrace(record);
  renderReport(record);
  renderRaw(record, response);
}

async function loadAndRenderRun(response) {
  const runId = response.run_metadata.run_id;
  const record = await fetchJson(
    `/api/v1/runs/${encodeURIComponent(runId)}`
  );
  renderRun(record, response);
  return record;
}

function singlePayload() {
  const payload = {
    text: byId("single-text").value,
    platform: byId("single-platform").value || "other",
    comments: parseJsonArray(
      byId("single-comments").value,
      "评论",
    ),
    history: parseJsonArray(
      byId("single-history").value,
      "历史",
    ),
    capture_complete: byId("single-capture-complete").checked,
    runtime_mode: byId("runtime-mode").value,
  };
  const optional = {
    post_id: byId("single-post-id").value.trim(),
    creator_id: byId("single-creator").value.trim(),
  };
  for (const [key, value] of Object.entries(optional)) {
    if (value) payload[key] = value;
  }
  const publishedAt = byId("single-published-at").value;
  if (publishedAt) {
    payload.published_at = new Date(publishedAt).toISOString();
  }
  return payload;
}

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupSingleForm();
  setupBatchForm();
  setupUrlForms();
  setupExportActions();
  try {
    await loadCapabilities();
    setSubmissionStatus("工作台已就绪", "success");
  } catch (error) {
    setSubmissionStatus(
      `初始化失败：${error.message}`,
      "error",
    );
  }
});

function setupSingleForm() {
  const form = byId("single-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      setBusy(form, true);
      setSubmissionStatus("正在运行单条分析");
      const response = await fetchJson("/api/v1/analyze", {
        method: "POST",
        body: JSON.stringify(singlePayload()),
      });
      await loadAndRenderRun(response);
      setSubmissionStatus("单条分析完成", "success");
    } catch (error) {
      setSubmissionStatus(
        `${error.code || "client_error"}：${error.message}`,
        "error",
      );
    } finally {
      setBusy(form, false);
    }
  });
  byId("single-clear").addEventListener("click", () => {
    form.reset();
    byId("single-platform").value = "other";
    byId("single-comments").value = "[]";
    byId("single-history").value = "[]";
    setSubmissionStatus("单条输入已清空");
  });
}
function setupBatchForm() {
  const form = byId("batch-form");
  const editor = byId("batch-json");
  editor.addEventListener("input", updateBatchCount);
  byId("batch-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      editor.value = String(reader.result);
      updateBatchCount();
      setSubmissionStatus("本地JSON文件已读取");
    });
    reader.addEventListener("error", () => {
      setSubmissionStatus("本地JSON文件读取失败", "error");
    });
    reader.readAsText(file, "utf-8");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      setBusy(form, true);
      const request = parseBatchPayload(editor.value);
      setSubmissionStatus(`正在分析${request.items.length}条记录`);
      const batch = await fetchJson("/api/v1/analyze/batch", {
        method: "POST",
        body: JSON.stringify(request),
      });
      renderBatchResults(batch);
      const firstSuccess = batch.items.find((item) => item.ok);
      if (firstSuccess) {
        await loadAndRenderRun(firstSuccess.result);
      }
      setSubmissionStatus("批量分析完成", "success");
    } catch (error) {
      setSubmissionStatus(
        `${error.code || "client_error"}：${error.message}`,
        "error",
      );
    } finally {
      setBusy(form, false);
    }
  });
  byId("batch-clear").addEventListener("click", () => {
    editor.value = '{"items":[]}';
    byId("batch-file").value = "";
    byId("batch-results").hidden = true;
    replaceChildren(byId("batch-items"));
    updateBatchCount();
    setSubmissionStatus("批量输入已清空");
  });
  updateBatchCount();
}
function setupUrlForms() {}
function setupExportActions() {}
