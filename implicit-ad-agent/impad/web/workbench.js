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

function setupSingleForm() {}
function setupBatchForm() {}
function setupUrlForms() {}
function setupExportActions() {}
