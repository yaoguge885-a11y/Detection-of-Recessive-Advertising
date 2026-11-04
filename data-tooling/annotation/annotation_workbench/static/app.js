"use strict";

/*
 * The browser never builds HTML from post text.  Every value from the server is
 * assigned with textContent (or attribute values that we control), so posts and
 * comments cannot inject markup.
 */

const state = {
  token: "",
  posts: [],
  total: 0,
  index: 0,
  current: null,
  selectedLabel: null,
  filterUnfinished: false,
  autoSuggest: true,
  meta: null,
  busy: false,
  adviceRequestId: 0,
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value == null ? "" : String(value);
}

function show(node, visible = true) {
  if (node) node.hidden = !visible;
}

function tokenFromUrl() {
  try {
    return new URLSearchParams(window.location.search).get("token") || "";
  } catch (_) {
    return "";
  }
}

function storageKey() {
  const d = state.meta ? state.meta.dataset_id : "unknown";
  const b = state.meta ? state.meta.batch_id : "unknown";
  const a = state.meta ? state.meta.annotator_id : "unknown";
  return `recessive-workbench:${d}:${b}:${a}`;
}

function readLocal(key, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return value == null ? fallback : value;
  } catch (_) {
    return fallback;
  }
}

function writeLocal(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch (_) {
    /* localStorage may be disabled; position persistence is best effort. */
  }
}

class ApiFailure extends Error {
  constructor(status, data) {
    super((data && data.error) || `HTTP ${status}`);
    this.status = status;
    this.data = data || {};
  }
}

async function api(path, options = {}) {
  const headers = Object.assign({"X-Workbench-Token": state.token}, options.headers || {});
  const init = {method: options.method || "GET", headers, cache: "no-store"};
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  let data = {};
  try {
    data = await response.json();
  } catch (_) {
    data = {};
  }
  if (!response.ok) throw new ApiFailure(response.status, data);
  return data;
}

function addBanner(kind, text, prefix) {
  const area = $("banner-area");
  if (!area) return;
  const box = document.createElement("div");
  box.className = `banner ${kind}`;
  if (prefix) {
    const strong = document.createElement("strong");
    strong.textContent = prefix;
    box.appendChild(strong);
  }
  box.appendChild(document.createTextNode(text));
  area.appendChild(box);
}

function clearBanners() {
  const area = $("banner-area");
  if (area) area.textContent = "";
}

function renderMeta() {
  const meta = state.meta;
  if (!meta) return;
  setText("meta-dataset", `数据集：${meta.dataset_id}`);
  setText("meta-batch", `批次：${meta.batch_id}`);
  setText("meta-annotator", `标注人：${meta.annotator_id}`);
  setText("meta-mode", meta.blind_mode ? "模式：盲标（无建议）" : "模式：模型辅助可用");
  const toggle = $("btn-toggle-suggest");
  if (toggle) {
    if (meta.suggest_available === false) {
      toggle.disabled = true;
      toggle.textContent = "盲标（本次启动已禁用建议）";
      toggle.title = "启动时使用了 --no-auto-suggest；如需模型辅助请重启并去掉该参数。";
    } else {
      toggle.disabled = false;
      toggle.textContent = state.autoSuggest ? "关闭自动建议" : "开启自动建议";
      toggle.title = "";
    }
  }
}

function renderWarnings() {
  clearBanners();
  const meta = state.meta;
  if (!meta) return;
  if (meta.blind_mode) {
    addBanner("info", "盲标模式：本页不会请求模型建议，保存记录为 human（独立人工）。", "盲标：");
  }
  if (!meta.formal_gold_allowed) {
    addBanner(
      "warn",
      "当前批次没有 approved 固定清单；只能作为探索性试标，不能宣称正式 Gold。",
      "数据门禁："
    );
  } else {
    addBanner(
      "info",
      "清单用途声明为 approved；工具只记录声明，不替代人工批准审计。",
      "清单声明："
    );
  }
  const seen = new Set();
  for (const warning of meta.warnings || []) {
    if (seen.has(warning)) continue;
    seen.add(warning);
    addBanner("warn", warning, "注意：");
  }
  if (meta.manifest && meta.manifest.duplicate_count) {
    addBanner("warn", `清单重复 ${meta.manifest.duplicate_count} 个 post_id。`, "清单：");
  }
  if (meta.manifest && meta.manifest.missing_count) {
    addBanner("warn", `清单有 ${meta.manifest.missing_count} 个 post_id 不在数据集中。`, "清单：");
  }
}

function renderProgress(progress) {
  const done = progress.done || 0;
  const total = progress.total || state.total || 0;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const fill = $("progress-fill");
  if (fill) fill.style.width = `${pct}%`;
  const track = document.querySelector(".progress-track");
  if (track) track.setAttribute("aria-valuenow", String(pct));
  const counts = progress.counts || {};
  const parts = [`${done} / ${total}（${pct}%）`];
  const labels = ["明广", "暗广", "非广", "uncertain", "out_of_scope"];
  for (const label of labels) {
    if (counts[label]) parts.push(`${label} ${counts[label]}`);
  }
  if (progress.assisted) parts.push(`辅助 ${progress.assisted}`);
  setText("progress-text", parts.join(" · "));
}

function updateExportLinks() {
  const token = encodeURIComponent(state.token);
  const json = $("export-json");
  const jsonl = $("export-jsonl");
  if (json) json.href = `/api/export?format=json&token=${token}`;
  if (jsonl) jsonl.href = `/api/export?format=jsonl&token=${token}`;
}

function setBadge(node, text, kind) {
  if (!node) return;
  node.textContent = text;
  node.className = `badge${kind ? ` ${kind}` : ""}`;
}

function renderPost(payload) {
  state.current = payload;
  const post = payload.post;
  const annotation = payload.annotation;
  setText("post-position", `第 ${post.index + 1} / ${payload.total} 条 · ${post.post_id}`);
  setText("post-title", post.title_missing ? "（标题缺失）" : post.title);
  setText("post-platform", post.platform);
  setText("post-source", post.source_type);
  setText("post-blogger", post.blogger_id);
  setText("post-published", post.published_at || "未记录");

  const collection = $("badge-collection");
  setBadge(collection, post.collection_label, post.collection_complete === "complete" ? "ok" : "warn");

  const savedBadge = $("badge-saved");
  show(savedBadge, Boolean(payload.saved));
  if (payload.saved) setBadge(savedBadge, "已保存", "ok");

  const disclosure = post.disclosure;
  const disclosureCard = $("disclosure-card");
  if (disclosureCard) disclosureCard.dataset.status = disclosure.status;
  setText("disclosure-label", disclosure.label);
  const detail = $("disclosure-detail");
  if (disclosure.detail) {
    detail.textContent = `采集到的披露字段：${disclosure.detail}`;
    show(detail, true);
  } else {
    show(detail, false);
  }

  const textNode = $("post-text");
  textNode.textContent = post.text_missing ? "" : post.text;
  show(textNode, !post.text_missing);
  show($("text-missing"), post.text_missing);

  setText("comments-meta", `· ${post.comments.label}`);
  const commentList = $("comments-list");
  commentList.textContent = "";
  if (!post.comments.items.length) {
    const note = document.createElement("p");
    note.className = "empty-note";
    note.textContent = post.comments.label;
    commentList.appendChild(note);
  } else {
    for (const comment of post.comments.items) {
      const box = document.createElement("div");
      box.className = "comment";
      if (comment.author) {
        const author = document.createElement("div");
        author.className = "comment-author";
        author.textContent = comment.author;
        box.appendChild(author);
      }
      const text = document.createElement("div");
      text.textContent = comment.text || "（空评论）";
      box.appendChild(text);
      commentList.appendChild(box);
    }
    if (post.comments.truncated) {
      const note = document.createElement("p");
      note.className = "empty-note";
      note.textContent = `评论较多，仅显示前 ${post.comments.items.length} 条；未显示不等于不存在。`;
      commentList.appendChild(note);
    }
  }

  setText("media-meta", `· ${post.media_summary.label}`);
  renderMedia(post.media);

  fillForm(annotation);
  renderAdviceState(payload.advice_state, post, annotation);
  updateNavButtons();
}

function renderMedia(items) {
  const grid = $("media-grid");
  grid.textContent = "";
  if (!items.length) {
    const note = document.createElement("p");
    note.className = "empty-note";
    note.textContent = "无媒体记录（不代表没有媒体；记录可能未采集媒体）。";
    grid.appendChild(note);
    return;
  }
  for (const item of items) {
    const card = document.createElement("div");
    card.className = `media-item ${item.status}`;
    const label = document.createElement("div");
    label.className = "media-badge";
    label.textContent = item.label;
    card.appendChild(label);

    if (item.status === "ok" && item.url) {
      let media;
      if (item.type === "image") {
        media = document.createElement("img");
        media.alt = item.caption || `媒体 ${item.index + 1}`;
        media.loading = "lazy";
      } else if (item.type === "video") {
        media = document.createElement("video");
        media.controls = true;
        media.preload = "metadata";
      } else {
        media = null;
      }
      if (media) {
        media.src = item.url;
        media.addEventListener("error", () => {
          card.className = "media-item missing";
          label.textContent = "媒体加载失败（按缺失处理）";
          if (media.parentNode) media.parentNode.removeChild(media);
        });
        card.appendChild(media);
      }
    }
    if (item.ref) {
      const ref = document.createElement("div");
      ref.className = "media-caption";
      ref.textContent = `ref: ${item.ref}`;
      card.appendChild(ref);
    }
    if (item.caption) {
      const caption = document.createElement("div");
      caption.className = "media-caption";
      caption.textContent = `说明：${item.caption}`;
      card.appendChild(caption);
    }
    if (item.reason) {
      const reason = document.createElement("div");
      reason.className = "media-reason";
      reason.textContent = item.reason;
      card.appendChild(reason);
    }
    grid.appendChild(card);
  }
}

function setSelectedLabel(label) {
  state.selectedLabel = label || null;
  document.querySelectorAll(".label-button").forEach((button) => {
    const selected = button.dataset.label === state.selectedLabel;
    button.setAttribute("aria-checked", selected ? "true" : "false");
    button.classList.toggle("selected", selected);
  });
  updateMethodPreview();
}

function checkedCodes() {
  return Array.from(document.querySelectorAll(".code-grid input[type=checkbox]:checked"))
    .map((input) => input.value);
}

function fillForm(annotation) {
  const record = annotation || {};
  setSelectedLabel(record.label || null);
  $("confidence").value = record.confidence == null ? "" : String(record.confidence);
  const codes = new Set(record.evidence_codes || []);
  document.querySelectorAll(".code-grid input[type=checkbox]").forEach((input) => {
    input.checked = codes.has(input.value);
  });
  $("evidence").value = (record.evidence || []).join("\n");
  $("uncertain-reason").value = record.uncertain_reason || "";
  $("notes").value = record.notes || "";
  $("saw-advice").checked = Boolean(record.saw_model_advice);
  setSaveStatus("", "");
  updateMethodPreview();
}

function collectForm() {
  return {
    post_id: state.current ? state.current.post.post_id : "",
    payload: {
      label: state.selectedLabel,
      confidence: $("confidence").value,
      evidence_codes: checkedCodes(),
      evidence: $("evidence").value.split(/\n+/).map((item) => item.trim()).filter(Boolean),
      uncertain_reason: $("uncertain-reason").value,
      notes: $("notes").value,
    },
    saw_model_advice: $("saw-advice").checked,
  };
}

function updateMethodPreview() {
  const saw = $("saw-advice").checked;
  const text = saw
    ? "当前将保存为：human_assisted（看过模型建议；现有 Gold/κ 工具会拒绝该记录）"
    : "当前将保存为：human（独立人工；若本页已显示建议，服务端会拒绝）";
  setText("method-preview", text);
}

function setSaveStatus(message, kind) {
  const node = $("save-status");
  node.textContent = message || "";
  node.className = `save-status${kind ? ` ${kind}` : ""}`;
}

function setAdviceCard(kind, badgeText, statusText) {
  const card = $("advice-card");
  card.classList.toggle("error", kind === "error");
  setBadge($("advice-badge"), badgeText, kind);
  setText("advice-status", statusText);
}

function clearAdviceBody() {
  show($("advice-body"), false);
  setText("advice-label", "—");
  setText("advice-confidence", "—");
  setText("advice-reasoning", "—");
  setText("advice-codes", "—");
  setText("advice-evidence", "—");
  setText("advice-gaps", "—");
  setText("advice-latency", "");
}

function renderBlindAdvice() {
  clearAdviceBody();
  setAdviceCard("info", "盲标", "自动建议已关闭：本页不会请求模型，也不会显示模型标签。保存记录为 human。");
}

function renderAdvice(advice) {
  setAdviceCard("ok", "已返回", "模型建议仅供参考，不会自动填写或保存；请人工判断。");
  show($("advice-body"), true);
  setText("advice-label", advice.label);
  setText("advice-confidence", advice.confidence);
  setText("advice-reasoning", advice.reasoning || "（模型未给出理由）");
  setText("advice-codes", (advice.evidence_codes || []).join(" / ") || "（无）");
  setText("advice-evidence", (advice.evidence || []).join("\n") || "（无）");
  setText("advice-gaps", (advice.information_gaps || []).join("；") || "（无）");
  const latency = advice.latency_ms != null ? `耗时 ${advice.latency_ms} ms` : "";
  setText("advice-latency", [advice.model || "", latency, advice.guide_version ? `指南 ${advice.guide_version}` : ""]
    .filter(Boolean).join(" · "));
  $("saw-advice").checked = true;
  updateMethodPreview();
}

function renderAdviceError(message, elapsedMs) {
  clearAdviceBody();
  setAdviceCard(
    "error",
    "失败",
    `模型请求失败：${message}。不会回退为关键词判断，也不会自动保存；请人工标注。`
  );
  if (elapsedMs != null) setText("advice-latency", `失败前耗时 ${elapsedMs} ms`);
  const priorAssisted = Boolean(
    state.current && state.current.annotation
    && state.current.annotation.annotation_method === "human_assisted"
  );
  $("saw-advice").checked = priorAssisted;
  updateMethodPreview();
}

function renderAdviceState(adviceState, post, annotation) {
  const status = adviceState && adviceState.status ? adviceState.status : "not_requested";
  if (!state.autoSuggest) {
    renderBlindAdvice();
    return;
  }
  if (status === "ok" && adviceState.advice) {
    renderAdvice(adviceState.advice);
  } else if (status === "error") {
    renderAdviceError(adviceState.error || "未知错误", adviceState.elapsed_ms);
  } else if (status === "loading") {
    clearAdviceBody();
    setAdviceCard("info", "请求中", "正在请求本机 Ollama；每次只发送当前帖子，不发送历史对话。");
  } else if (annotation && annotation.annotation_method === "human_assisted") {
    clearAdviceBody();
    setAdviceCard(
      "info",
      "历史辅助",
      "此条曾保存为 human_assisted；模型建议正文不会持久化。若重新请求，会显示当前建议。"
    );
    requestAdvice(post.post_id);
  } else {
    clearAdviceBody();
    setAdviceCard("info", "请求中", "打开帖子后自动请求一次建议；不会自动保存。");
    requestAdvice(post.post_id);
  }
}

async function requestAdvice(postId) {
  if (!state.autoSuggest || !postId) return;
  const requestId = ++state.adviceRequestId;
  const card = $("advice-card");
  card.classList.remove("error");
  try {
    const data = await api("/api/suggest", {method: "POST", body: {post_id: postId}});
    if (requestId !== state.adviceRequestId) return;
    if (!state.current || state.current.post.post_id !== postId) return;
    renderAdvice(data.advice);
  } catch (error) {
    if (requestId !== state.adviceRequestId) return;
    if (!state.current || state.current.post.post_id !== postId) return;
    if (error instanceof ApiFailure && error.status === 403 && error.data.code === "blind_mode") {
      state.autoSuggest = false;
      renderMeta();
      renderWarnings();
      renderBlindAdvice();
      return;
    }
    renderAdviceError(error.message || String(error), error.data && error.data.elapsed_ms);
  }
}

async function saveCurrent() {
  if (state.busy || !state.current) return;
  const body = collectForm();
  if (!body.post_id) return;
  if (!body.payload.label) {
    setSaveStatus("请先选择人工标签。", "error");
    return;
  }
  state.busy = true;
  const button = $("btn-save");
  button.disabled = true;
  setSaveStatus("保存中…", "");
  try {
    const data = await api("/api/annotation", {method: "POST", body});
    const record = data.annotation;
    state.current.annotation = record;
    state.current.saved = true;
    const row = state.posts.find((item) => item.post_id === record.post_id);
    if (row) {
      row.done = true;
      row.label = record.label;
      row.annotation_method = record.annotation_method;
    }
    $("saw-advice").checked = Boolean(record.saw_model_advice);
    setBadge($("badge-saved"), "已保存", "ok");
    show($("badge-saved"), true);
    setSaveStatus(
      `已保存（第 ${record.revision} 版，${record.annotation_method}）。`,
      "ok"
    );
    if (data.progress) renderProgress(data.progress);
    updateMethodPreview();
  } catch (error) {
    let message = error.message || String(error);
    if (error instanceof ApiFailure && error.status === 409) {
      message = `${message}（未保存；请确认是否看过建议，或关闭自动建议后重开此帖做盲标。）`;
    }
    setSaveStatus(`保存失败：${message}`, "error");
  } finally {
    state.busy = false;
    button.disabled = false;
  }
}

function updateNavButtons() {
  const prev = $("btn-prev");
  const next = $("btn-next");
  if (prev) prev.disabled = findIndex(-1) == null;
  if (next) next.disabled = findIndex(1) == null;
  const jump = $("jump-input");
  if (jump) {
    jump.max = String(state.total);
    jump.placeholder = `1-${state.total}`;
  }
}

function findIndex(step) {
  let i = state.index;
  for (;;) {
    i += step;
    if (i < 0 || i >= state.total) return null;
    if (!state.filterUnfinished || !state.posts[i] || !state.posts[i].done) return i;
  }
}

async function loadPost(index) {
  if (index < 0 || index >= state.total) return;
  $("loading").hidden = false;
  try {
    const payload = await api(`/api/post?index=${encodeURIComponent(index)}`);
    state.index = index;
    renderPost(payload);
    writeLocal(`${storageKey()}:index`, index);
  } catch (error) {
    addBanner("error", `加载第 ${index + 1} 条失败：${error.message || error}`, "错误：");
  } finally {
    $("loading").hidden = true;
  }
}

function navigate(step) {
  const target = findIndex(step);
  if (target != null) loadPost(target);
}

async function toggleAutoSuggest() {
  const button = $("btn-toggle-suggest");
  button.disabled = true;
  try {
    const data = await api("/api/settings", {method: "POST", body: {auto_suggest: !state.autoSuggest}});
    state.autoSuggest = Boolean(data.auto_suggest);
    state.meta.auto_suggest = state.autoSuggest;
    state.meta.blind_mode = !state.autoSuggest;
    renderMeta();
    renderWarnings();
    if (!state.autoSuggest) {
      $("saw-advice").checked = false;
      updateMethodPreview();
      renderBlindAdvice();
    } else if (state.current) {
      requestAdvice(state.current.post.post_id);
    }
  } catch (error) {
    addBanner("error", `切换自动建议失败：${error.message || error}`, "错误：");
  } finally {
    button.disabled = false;
  }
}

function bindEvents() {
  $("btn-prev").addEventListener("click", () => navigate(-1));
  $("btn-next").addEventListener("click", () => navigate(1));
  $("btn-jump").addEventListener("click", () => {
    const value = Number.parseInt($("jump-input").value, 10);
    if (!Number.isFinite(value) || value < 1 || value > state.total) {
      addBanner("warn", `跳转序号必须在 1-${state.total} 之间。`, "跳转：");
      return;
    }
    loadPost(value - 1);
  });
  $("jump-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      $("btn-jump").click();
    }
  });
  $("filter-unfinished").addEventListener("change", (event) => {
    state.filterUnfinished = event.target.checked;
    writeLocal(`${storageKey()}:filter`, state.filterUnfinished ? "1" : "0");
    updateNavButtons();
    if (state.filterUnfinished && state.posts[state.index] && state.posts[state.index].done) {
      const target = findIndex(1);
      if (target != null) loadPost(target);
    }
  });
  $("btn-toggle-suggest").addEventListener("click", toggleAutoSuggest);
  document.querySelectorAll(".label-button").forEach((button) => {
    button.addEventListener("click", () => setSelectedLabel(button.dataset.label));
  });
  $("saw-advice").addEventListener("change", updateMethodPreview);
  $("annotation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveCurrent();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      saveCurrent();
    }
  });
  $("btn-use-advice").addEventListener("click", () => {
    const payload = state.current && state.current.advice_state;
    const advice = payload && payload.advice;
    if (!advice) return;
    setSelectedLabel(advice.label);
    $("confidence").value = advice.confidence == null ? "" : String(advice.confidence);
    const wanted = new Set(advice.evidence_codes || []);
    document.querySelectorAll(".code-grid input[type=checkbox]").forEach((input) => {
      if (wanted.has(input.value)) input.checked = true;
    });
    if ((advice.evidence || []).length) $("evidence").value = advice.evidence.join("\n");
    if (advice.label === "uncertain" && !$("uncertain-reason").value && advice.uncertain_reason) {
      $("uncertain-reason").value = advice.uncertain_reason;
    }
    $("saw-advice").checked = true;
    updateMethodPreview();
    setSaveStatus("已把建议填入表单（未保存）；请人工核对后点击保存。", "ok");
  });
}

async function boot() {
  state.token = tokenFromUrl();
  if (!state.token) {
    addBanner("error", "URL 缺少本地访问 token。请关闭窗口，从 PowerShell 输出中的完整 URL 重新打开。", "无法连接：");
    return;
  }
  $("loading").hidden = false;
  try {
    const meta = await api("/api/state");
    state.meta = meta;
    state.autoSuggest = Boolean(meta.auto_suggest);
    const indexData = await api("/api/index");
    state.posts = indexData.posts || [];
    state.total = indexData.total || state.posts.length;
    renderMeta();
    renderWarnings();
    renderProgress(meta.progress || {done: 0, total: state.total});
    updateExportLinks();

    state.filterUnfinished = readLocal(`${storageKey()}:filter`, "0") === "1";
    $("filter-unfinished").checked = state.filterUnfinished;

    let start = Number.parseInt(readLocal(`${storageKey()}:index`, "0"), 10);
    if (!Number.isFinite(start) || start < 0 || start >= state.total) start = 0;
    if (state.posts[start] && state.posts[start].done && state.filterUnfinished) {
      const next = state.posts.findIndex((row) => !row.done);
      if (next >= 0) start = next;
    }
    if (!state.posts[start] || state.posts[start].done) {
      const first = state.posts.findIndex((row) => !row.done);
      if (first >= 0) start = first;
    }
    bindEvents();
    await loadPost(start);
  } catch (error) {
    addBanner("error", `初始化失败：${error.message || error}`, "错误：");
  } finally {
    $("loading").hidden = true;
  }
}

boot();
