# P5.2 Research Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a same-origin, no-build developer research workbench for the existing single, batch, URL-preview/confirm, and run-query APIs.

**Architecture:** FastAPI serves package-owned HTML, CSS, and JavaScript at `/workbench` and `/workbench/assets`. The browser uses only existing `/health` and `/api/v1` contracts, fetches persisted `RunRecord` data for complete rendering, and never duplicates analysis logic. Static security invariants are enforced by pytest; complete workflows and responsive behavior are verified in a real browser.

**Tech Stack:** Python 3.10, FastAPI/Starlette `StaticFiles` and `FileResponse`, pytest/TestClient, semantic HTML, modern dependency-free CSS, browser-native ES2020 JavaScript, and the in-app browser for local end-to-end verification.

## Global Constraints

- Add no Node manifest, bundler, remote frontend dependency, or new Python runtime dependency.
- Keep the default path zero-key and zero-network; do not register a live platform adapter.
- Do not change `AnalysisService`, Judge, CreatorShift, RAG, M1, or existing API response contracts.
- Render all untrusted values with `textContent`; never use `innerHTML`, inline event handlers, inline scripts, or inline styles.
- Do not use cookies, local/session storage, IndexedDB, service workers, analytics, remote fonts, or remote images.
- Only server-provided `https:` law references may become clickable external links.
- Preserve explicit missing, degraded, conflicted, and review-required states.
- Keep the existing two intentional vision skips and existing Starlette/httpx warning boundary factual.
- Do not claim live platform capture, four-person UAT, P5/M5, M1, or M4 completion.
- Use `apply_patch` for edits and commit each independently reviewable task.

---

### Task 1: Serve package-owned workbench assets securely

**Files:**
- Create: `implicit-ad-agent/impad/web/__init__.py`
- Create: `implicit-ad-agent/impad/web/index.html`
- Create: `implicit-ad-agent/impad/web/workbench.css`
- Create: `implicit-ad-agent/impad/web/workbench.js`
- Create: `implicit-ad-agent/tests/web/__init__.py`
- Create: `implicit-ad-agent/tests/web/test_workbench.py`
- Modify: `implicit-ad-agent/app.py`
- Modify: `implicit-ad-agent/pyproject.toml`

**Interfaces:**
- Consumes: `create_app(service, url_import_service=...) -> FastAPI`.
- Produces: `asset_directory() -> Path`, `GET /workbench`, and static paths under `/workbench/assets`.

- [ ] **Step 1: Write failing route, asset, header, and package-data tests**

Create `tests/web/test_workbench.py` with:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def _client(tmp_path: Path) -> TestClient:
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    return TestClient(create_app(service))


def test_workbench_document_and_assets_are_served(tmp_path):
    client = _client(tmp_path)

    document = client.get("/workbench")
    stylesheet = client.get("/workbench/assets/workbench.css")
    script = client.get("/workbench/assets/workbench.js")

    assert document.status_code == 200
    assert document.encoding.lower() == "utf-8"
    assert "text/html" in document.headers["content-type"]
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


def test_workbench_document_has_strict_security_headers(tmp_path):
    response = _client(tmp_path).get("/workbench")

    assert response.headers["content-security-policy"] == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_root_links_to_workbench(tmp_path):
    response = _client(tmp_path).get("/")

    assert response.status_code == 200
    assert 'href="/workbench"' in response.text
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
Set-Location implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests\web\test_workbench.py -q
```

Expected: collection fails because `impad.web` does not exist or requests to
`/workbench` and its assets return 404.

- [ ] **Step 3: Add the asset resolver and package-data rule**

Create `impad/web/__init__.py`:

```python
"""Package-owned assets for the local developer workbench."""
from pathlib import Path


def asset_directory() -> Path:
    return Path(__file__).resolve().parent
```

Extend `[tool.setuptools.package-data]` in `pyproject.toml`:

```toml
"impad.web" = ["*.html", "*.css", "*.js"]
```

- [ ] **Step 4: Add minimal external assets**

Create `impad/web/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>隐性广告识别 · 开发者研究工作台</title>
  <link rel="stylesheet" href="/workbench/assets/workbench.css">
  <script src="/workbench/assets/workbench.js" defer></script>
</head>
<body>
  <main>
    <h1>开发者研究工作台</h1>
  </main>
</body>
</html>
```

Create `impad/web/workbench.css`:

```css
:root {
  color-scheme: light;
}

body {
  margin: 0;
  font-family: system-ui, sans-serif;
}
```

Create `impad/web/workbench.js`:

```javascript
"use strict";
```

- [ ] **Step 5: Mount assets and serve the secured document**

In `app.py`, import:

```python
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from impad.web import asset_directory
```

Define the exact header constant:

```python
WORKBENCH_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
```

Inside `create_app()`, before returning the application:

```python
    workbench_assets = asset_directory()
    application.mount(
        "/workbench/assets",
        StaticFiles(directory=workbench_assets),
        name="workbench-assets",
    )

    @application.get("/workbench", response_class=FileResponse)
    def workbench():
        return FileResponse(
            workbench_assets / "index.html",
            media_type="text/html; charset=utf-8",
            headers=WORKBENCH_HEADERS,
        )
```

Change the root response so it includes:

```html
<p><a href="/workbench">打开开发者研究工作台</a></p>
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py tests\test_app.py -q
```

Expected: all tests pass and existing health/single-analysis routes remain
available.

- [ ] **Step 7: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web `
  implicit-ad-agent/tests/web `
  implicit-ad-agent/app.py `
  implicit-ad-agent/pyproject.toml
git diff --cached --check
git commit -m "feat: serve secure research workbench"
```

---

### Task 2: Build the semantic responsive workbench shell

**Files:**
- Modify: `implicit-ad-agent/impad/web/index.html`
- Modify: `implicit-ad-agent/impad/web/workbench.css`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**
- Consumes: `/workbench` and `/workbench/assets` from Task 1.
- Produces: stable DOM IDs and data attributes used by all JavaScript tasks.

- [ ] **Step 1: Add failing semantic-landmark and static-safety tests**

Append:

```python
import re


def test_workbench_has_all_input_and_result_landmarks(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    for marker in (
        'id="capability-status"',
        'id="runtime-mode"',
        'id="single-panel"',
        'id="batch-panel"',
        'id="url-panel"',
        'id="submission-status"',
        'id="batch-results"',
        'id="verdict-section"',
        'id="coverage-section"',
        'id="evidence-section"',
        'id="creator-shift-section"',
        'id="history-section"',
        'id="law-section"',
        'id="trace-section"',
        'id="report-section"',
        'id="raw-section"',
    ):
        assert marker in html


def test_workbench_markup_has_no_inline_or_remote_execution_path(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    assert "<style" not in html.lower()
    assert re.search(r"<script[^>]+src=", html, re.IGNORECASE)
    assert not re.search(r"<script(?![^>]+src=)", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    assert 'style="' not in html.lower()
    assert "http://" not in html.lower()
    assert "https://" not in html.lower()


def test_workbench_css_has_narrow_layout_and_no_remote_assets(tmp_path):
    css = _client(tmp_path).get(
        "/workbench/assets/workbench.css"
    ).text

    assert "@media (max-width: 860px)" in css
    assert "overflow-wrap: anywhere" in css
    assert "url(http" not in css.lower()
```

- [ ] **Step 2: Run shell tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py -q
```

Expected: required landmark and responsive CSS assertions fail against the
minimal Task 1 document.

- [ ] **Step 3: Implement the complete semantic document**

Replace the minimal body with these top-level regions and exact stable IDs:

```html
<body>
  <header class="masthead">
    <div>
      <p class="eyebrow">P5 · Evidence Workbench</p>
      <h1>隐性广告识别</h1>
      <p class="subtitle">开发者研究工作台</p>
    </div>
    <div class="capability-strip" aria-live="polite">
      <span id="health-status" class="status-chip">API 检查中</span>
      <span id="capability-status" class="status-chip">能力检查中</span>
      <span id="url-capability" class="status-chip">URL 检查中</span>
    </div>
  </header>

  <main class="workbench-layout">
    <aside class="input-rail" aria-label="分析输入">
      <div class="runtime-row">
        <label for="runtime-mode">运行模式</label>
        <select id="runtime-mode">
          <option value="local">local</option>
          <option value="mcp">mcp</option>
        </select>
      </div>

      <div class="tab-list" role="tablist" aria-label="输入方式">
        <button id="single-tab" role="tab" aria-selected="true"
                aria-controls="single-panel">单条</button>
        <button id="batch-tab" role="tab" aria-selected="false"
                aria-controls="batch-panel" tabindex="-1">批量</button>
        <button id="url-tab" role="tab" aria-selected="false"
                aria-controls="url-panel" tabindex="-1">URL预览</button>
      </div>

      <section id="single-panel" role="tabpanel"
               aria-labelledby="single-tab">
        <form id="single-form">
          <label for="single-text">正文</label>
          <textarea id="single-text" required></textarea>
          <div class="field-grid">
            <label>帖子ID<input id="single-post-id"></label>
            <label>平台<input id="single-platform" value="other"></label>
            <label>创作者<input id="single-creator"></label>
            <label>发布时间<input id="single-published-at"
                                   type="datetime-local"></label>
          </div>
          <label for="single-comments">评论 JSON 数组</label>
          <textarea id="single-comments">[]</textarea>
          <label for="single-history">历史 JSON 数组</label>
          <textarea id="single-history">[]</textarea>
          <label class="check-row">
            <input id="single-capture-complete" type="checkbox">
            已完整采集披露面
          </label>
          <div class="button-row">
            <button type="submit">开始分析</button>
            <button id="single-clear" type="button"
                    class="secondary">清空</button>
          </div>
        </form>
      </section>

      <section id="batch-panel" role="tabpanel"
               aria-labelledby="batch-tab" hidden>
        <form id="batch-form">
          <label for="batch-json">批量请求 JSON</label>
          <textarea id="batch-json">{"items":[]}</textarea>
          <label for="batch-file">读取本地 JSON 文件</label>
          <input id="batch-file" type="file"
                 accept="application/json,.json">
          <p id="batch-count">0 / 50</p>
          <div class="button-row">
            <button type="submit">运行批量分析</button>
            <button id="batch-clear" type="button"
                    class="secondary">清空</button>
          </div>
        </form>
      </section>

      <section id="url-panel" role="tabpanel"
               aria-labelledby="url-tab" hidden>
        <form id="url-preview-form">
          <label for="url-input">平台URL</label>
          <input id="url-input" type="url" autocomplete="off">
          <button id="url-preview-submit" type="submit">生成预览</button>
        </form>
        <p id="url-unavailable" class="notice" hidden></p>
        <section id="url-preview-result" hidden>
          <dl id="url-preview-meta"></dl>
          <form id="url-confirm-form">
            <label for="correction-text">正文</label>
            <textarea id="correction-text"></textarea>
            <label for="correction-creator">创作者ID</label>
            <input id="correction-creator">
            <label for="correction-published-at">发布时间</label>
            <input id="correction-published-at">
            <label for="correction-media">媒体 JSON 数组</label>
            <textarea id="correction-media">[]</textarea>
            <label for="correction-comments">评论 JSON 数组</label>
            <textarea id="correction-comments">[]</textarea>
            <label for="correction-history">历史 JSON 数组</label>
            <textarea id="correction-history">[]</textarea>
            <label for="correction-capture">采集状态 JSON 对象</label>
            <textarea id="correction-capture">{}</textarea>
            <div class="button-row">
              <button type="submit">确认并分析</button>
              <button id="url-discard" type="button"
                      class="secondary">丢弃本地预览</button>
            </div>
          </form>
        </section>
      </section>

      <p id="submission-status" class="submission-status"
         aria-live="polite">等待输入</p>
    </aside>

    <section class="result-canvas" aria-label="分析结果">
      <section id="batch-results" class="panel" hidden>
        <div class="section-heading">
          <h2>批量结果</h2>
          <span id="batch-summary"></span>
        </div>
        <div id="batch-items"></div>
      </section>

      <div id="result-empty" class="empty-state">
        <p>提交合成或获准数据后，这里将展示完整证据链。</p>
      </div>

      <div id="result-content" hidden>
        <section id="verdict-section" class="panel"></section>
        <section id="coverage-section" class="panel"></section>
        <section id="evidence-section" class="panel"></section>
        <section id="creator-shift-section" class="panel"></section>
        <section id="history-section" class="panel"></section>
        <section id="law-section" class="panel"></section>
        <section id="trace-section" class="panel"></section>
        <section id="report-section" class="panel"></section>
        <section id="raw-section" class="panel"></section>
      </div>
    </section>
  </main>
</body>
```

- [ ] **Step 4: Implement the visual system**

Replace the minimal CSS with a complete tokenized stylesheet that includes
these required rules:

```css
:root {
  color-scheme: light;
  --paper: #f5f2ea;
  --surface: #fffdf8;
  --ink: #172033;
  --muted: #667085;
  --line: #d8d3c7;
  --accent: #5146e5;
  --accent-soft: #eceaff;
  --success: #176b4d;
  --warning: #9a5b13;
  --danger: #a63a3a;
  --radius: 16px;
  --shadow: 0 14px 42px rgb(23 32 51 / 9%);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system,
               "Segoe UI", sans-serif;
}

button,
input,
select,
textarea {
  font: inherit;
}

button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[role="tab"]:focus-visible {
  outline: 3px solid rgb(81 70 229 / 35%);
  outline-offset: 2px;
}

.masthead {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  padding: 28px clamp(20px, 4vw, 56px);
  border-bottom: 1px solid var(--line);
}

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 24px;
  padding: 24px clamp(20px, 4vw, 56px) 56px;
}

.input-rail {
  position: sticky;
  top: 16px;
  align-self: start;
  max-height: calc(100vh - 32px);
  overflow: auto;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.result-canvas,
.panel,
.evidence-card,
.law-card,
.timeline-item,
.event-row {
  min-width: 0;
  overflow-wrap: anywhere;
}

.panel {
  margin-bottom: 18px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.tab-list,
.button-row,
.capability-strip,
.status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.field-grid,
.summary-grid,
.evidence-grid,
.law-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

textarea {
  width: 100%;
  min-height: 92px;
  resize: vertical;
}

[hidden] {
  display: none !important;
}

@media (max-width: 860px) {
  .masthead {
    align-items: start;
    flex-direction: column;
  }

  .workbench-layout {
    grid-template-columns: 1fr;
    padding-inline: 14px;
  }

  .input-rail {
    position: static;
    max-height: none;
  }

  .field-grid,
  .summary-grid,
  .evidence-grid,
  .law-grid {
    grid-template-columns: 1fr;
  }
}
```

Add the remaining selectors needed by the markup using these invariants:

- labels are block-level and inputs fill the available width;
- primary buttons use `--accent`; secondary buttons remain neutral;
- status chips have neutral/success/warning/danger variants;
- review-required and degraded cards use amber, not success green;
- evidence polarity is communicated by text and border style, not color alone;
- event and timeline lists remain readable at 390px without horizontal
  scrolling.

Use these concrete component rules:

```css
label {
  display: grid;
  gap: 6px;
  margin-block: 12px;
  color: var(--muted);
  font-size: 0.88rem;
  font-weight: 650;
}

input,
select,
textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: white;
  color: var(--ink);
}

button {
  min-height: 40px;
  padding: 9px 14px;
  border: 1px solid var(--accent);
  border-radius: 10px;
  background: var(--accent);
  color: white;
  cursor: pointer;
}

button.secondary,
[role="tab"] {
  border-color: var(--line);
  background: white;
  color: var(--ink);
}

[role="tab"][aria-selected="true"] {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}

button:disabled,
input:disabled {
  cursor: not-allowed;
  border-color: var(--line);
  background: #ece9e1;
  color: #6f6b63;
}

.status-chip,
.verdict-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
}

.submission-status[data-tone="success"],
.status-chip[data-tone="success"] {
  color: var(--success);
}

.submission-status[data-tone="error"],
.status-chip[data-tone="error"] {
  color: var(--danger);
}

.notice,
.conflict-card {
  padding: 12px;
  border-left: 4px solid var(--warning);
  background: #fff5df;
}

.definition-grid {
  display: grid;
  grid-template-columns: minmax(110px, auto) minmax(0, 1fr);
  gap: 6px 14px;
}

.definition-grid dt {
  color: var(--muted);
}

.definition-grid dd {
  margin: 0;
  white-space: pre-wrap;
}

.coverage-card,
.evidence-card,
.law-card,
.timeline-item {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: white;
}

.evidence-card[data-polarity="supports"] {
  border-left: 4px solid var(--success);
}

.evidence-card[data-polarity="contradicts"] {
  border-left: 4px dashed var(--danger);
}

.evidence-card[data-polarity="neutral"] {
  border-left: 4px dotted var(--accent);
}

.timeline,
.event-list {
  display: grid;
  gap: 10px;
  padding: 0;
  list-style: none;
}

.report-text,
.raw-json {
  max-width: 100%;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.muted {
  color: var(--muted);
}

@media (max-width: 520px) {
  .definition-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run shell tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\web -q
```

Expected: every Task 1 and Task 2 test passes.

- [ ] **Step 6: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web/index.html `
  implicit-ad-agent/impad/web/workbench.css `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "feat: add research workbench shell"
```

---

### Task 3: Add safe client state, tabs, capability discovery, and input parsing

**Files:**
- Modify: `implicit-ad-agent/impad/web/workbench.js`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**
- Consumes: DOM IDs from Task 2, `GET /health`, and
  `GET /api/v1/capabilities`.
- Produces: `state`, safe DOM helpers, `fetchJson`, tab control, parsed single
  and batch payloads, and capability-driven URL availability.

- [ ] **Step 1: Add failing JavaScript security and endpoint-contract tests**

Append:

```python
def test_workbench_script_uses_safe_dom_and_only_same_origin_api(tmp_path):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for required in (
        '"/health"',
        '"/api/v1/capabilities"',
        'textContent',
        'DOMContentLoaded',
        'parseJsonArray',
        'parseBatchPayload',
        'setupTabs',
        'loadCapabilities',
    ):
        assert required in script
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "serviceWorker",
        "http://",
        "https://",
    ):
        assert forbidden not in script
```

- [ ] **Step 2: Run the script contract test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py `
  -k "script_uses_safe_dom" -q
```

Expected: required endpoint/helper markers are absent from the minimal script.

- [ ] **Step 3: Implement state and safe DOM helpers**

Use:

```javascript
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
```

- [ ] **Step 4: Implement safe HTTP and JSON parsing**

Use:

```javascript
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
```

- [ ] **Step 5: Implement keyboard tabs and capability loading**

Use:

```javascript
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
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(
        event.key
      )) {
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
```

- [ ] **Step 6: Initialize without hiding startup errors**

Use:

```javascript
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
```

Define temporary no-op setup functions at the end so this task stays runnable:

```javascript
function setupSingleForm() {}
function setupBatchForm() {}
function setupUrlForms() {}
function setupExportActions() {}
```

Subsequent tasks replace each no-op with its complete implementation.

- [ ] **Step 7: Run focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\web -q
```

- [ ] **Step 8: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web/workbench.js `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "feat: add safe workbench client foundation"
```

---

### Task 4: Implement single analysis and complete run rendering

**Files:**
- Modify: `implicit-ad-agent/impad/web/workbench.js`
- Modify: `implicit-ad-agent/impad/web/workbench.css`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**
- Consumes: `POST /api/v1/analyze`, `GET /api/v1/runs/{run_id}`, safe DOM
  helpers from Task 3, and the complete `RunRecord` contract.
- Produces: `renderRun(record, response)`, every required result renderer, and
  a complete single-analysis form flow.

- [ ] **Step 1: Add failing renderer and single-flow contract tests**

Append:

```python
def test_workbench_script_defines_complete_run_renderers(tmp_path):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for required in (
        '"/api/v1/analyze"',
        '"/api/v1/runs/"',
        "renderRun",
        "renderVerdict",
        "renderCoverage",
        "renderEvidence",
        "renderCreatorShift",
        "renderHistory",
        "renderLawEvidence",
        "renderTrace",
        "renderReport",
        "renderRaw",
    ):
        assert required in script
```

- [ ] **Step 2: Run the renderer test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py `
  -k "complete_run_renderers" -q
```

Expected: renderer and endpoint markers are absent.

- [ ] **Step 3: Add reusable rendering primitives**

Implement:

```javascript
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
```

- [ ] **Step 4: Implement verdict, coverage, evidence, and conflict rendering**

Implement `renderVerdict(record)`, `renderCoverage(bundle)`, and
`renderEvidence(bundle)` with these exact field mappings:

```javascript
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
```

- [ ] **Step 5: Implement CreatorShift, history, law, trace, report, and raw renderers**

Implement:

```javascript
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
```

- [ ] **Step 6: Connect the shared renderer and single form**

Use:

```javascript
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
```

Replace the Task 3 `setupSingleForm` no-op; keep the other no-ops.

- [ ] **Step 7: Run focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\test_app.py tests\api -q
```

- [ ] **Step 8: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web/workbench.js `
  implicit-ad-agent/impad/web/workbench.css `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "feat: render complete analysis runs"
```

---

### Task 5: Implement batch loading, isolation display, and run selection

**Files:**
- Modify: `implicit-ad-agent/impad/web/workbench.js`
- Modify: `implicit-ad-agent/impad/web/workbench.css`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**
- Consumes: `POST /api/v1/analyze/batch`, `parseBatchPayload`, and
  `loadAndRenderRun`.
- Produces: file loading, count validation, ordered batch rows, and successful
  run selection.

- [ ] **Step 1: Add failing batch-flow asset test**

Append:

```python
def test_workbench_script_defines_batch_file_and_result_flow(tmp_path):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for required in (
        '"/api/v1/analyze/batch"',
        "FileReader",
        "renderBatchResults",
        "setupBatchForm",
        "batch.items",
    ):
        assert required in script
```

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py -k "batch_file_and_result_flow" -q
```

- [ ] **Step 3: Implement count and ordered result rendering**

Use:

```javascript
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
```

- [ ] **Step 4: Implement batch form and local file reading**

Replace the no-op with:

```javascript
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
```

- [ ] **Step 5: Add batch list styling**

Add:

```css
.batch-item-list {
  display: grid;
  gap: 10px;
}

.batch-item {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: white;
}

.batch-item[data-ok="true"] {
  border-left: 4px solid var(--success);
}

.batch-item[data-ok="false"] {
  border-left: 4px solid var(--danger);
}

.batch-item code {
  min-width: 0;
  overflow-wrap: anywhere;
}

@media (max-width: 520px) {
  .batch-item {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
```

- [ ] **Step 6: Run focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\api\test_routes.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web/workbench.js `
  implicit-ad-agent/impad/web/workbench.css `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "feat: add workbench batch analysis"
```

---

### Task 6: Implement capability-gated URL preview and audited confirmation

**Files:**
- Modify: `implicit-ad-agent/impad/web/workbench.js`
- Modify: `implicit-ad-agent/impad/web/workbench.css`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`

**Interfaces:**
- Consumes: P5.1 preview/confirm endpoints and `URLImportPreview` response.
- Produces: no-adapter state, sanitized preview rendering, allowlisted
  corrections, confirmation, and local preview disposal.

- [ ] **Step 1: Add failing URL-flow and privacy asset test**

Append:

```python
def test_workbench_script_defines_gated_url_preview_and_confirm(tmp_path):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for required in (
        '"/api/v1/import/url/preview"',
        '"/api/v1/import/url/confirm"',
        "activePreview",
        "renderUrlPreview",
        "urlCorrections",
        'byId("url-input").value = ""',
    ):
        assert required in script
```

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py `
  -k "gated_url_preview_and_confirm" -q
```

- [ ] **Step 3: Implement sanitized preview rendering**

Use:

```javascript
function metadataPair(term, value) {
  return [element("dt", term), element("dd", value ?? "未知")];
}

function renderUrlPreview(preview) {
  state.activePreview = preview;
  byId("url-preview-result").hidden = false;
  const metadata = byId("url-preview-meta");
  replaceChildren(
    metadata,
    ...metadataPair("平台", preview.platform),
    ...metadataPair("适配器", preview.adapter_name),
    ...metadataPair("版本", preview.adapter_version),
    ...metadataPair("展示URL", preview.display_url),
    ...metadataPair("来源哈希", preview.source_ref_hash),
  );
  const post = preview.post;
  byId("correction-text").value = post.text;
  byId("correction-creator").value = post.creator_id;
  byId("correction-published-at").value = post.published_at || "";
  byId("correction-media").value = jsonText(post.media);
  byId("correction-comments").value = jsonText(post.comments);
  byId("correction-history").value = jsonText(post.history);
  byId("correction-capture").value = jsonText(post.capture_status);
}
```

- [ ] **Step 4: Implement correction construction and URL form behavior**

Use:

```javascript
function urlCorrections() {
  return {
    text: byId("correction-text").value,
    creator_id: byId("correction-creator").value,
    published_at: byId("correction-published-at").value || null,
    media: parseJsonArray(
      byId("correction-media").value,
      "媒体",
    ),
    comments: parseJsonArray(
      byId("correction-comments").value,
      "评论",
    ),
    history: parseJsonArray(
      byId("correction-history").value,
      "历史",
    ),
    capture_status: parseJsonObject(
      byId("correction-capture").value,
      "采集状态",
    ),
  };
}

function clearLocalPreview() {
  state.activePreview = null;
  byId("url-preview-result").hidden = true;
  replaceChildren(byId("url-preview-meta"));
  byId("url-confirm-form").reset();
}

function setupUrlForms() {
  const previewForm = byId("url-preview-form");
  const confirmForm = byId("url-confirm-form");
  previewForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      setBusy(previewForm, true);
      setSubmissionStatus("正在生成URL预览");
      const preview = await fetchJson("/api/v1/import/url/preview", {
        method: "POST",
        body: JSON.stringify({url: byId("url-input").value}),
      });
      byId("url-input").value = "";
      renderUrlPreview(preview);
      setSubmissionStatus("URL预览已生成，请核对后确认", "success");
    } catch (error) {
      setSubmissionStatus(
        `${error.code || "client_error"}：${error.message}`,
        "error",
      );
    } finally {
      setBusy(previewForm, false);
    }
  });
  confirmForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.activePreview) {
      setSubmissionStatus("没有可确认的URL预览", "error");
      return;
    }
    try {
      setBusy(confirmForm, true);
      setSubmissionStatus("正在确认并分析URL预览");
      const response = await fetchJson("/api/v1/import/url/confirm", {
        method: "POST",
        body: JSON.stringify({
          preview_id: state.activePreview.preview_id,
          corrections: urlCorrections(),
          runtime_mode: byId("runtime-mode").value,
        }),
      });
      await loadAndRenderRun(response);
      clearLocalPreview();
      setSubmissionStatus("URL预览确认并分析完成", "success");
    } catch (error) {
      setSubmissionStatus(
        `${error.code || "client_error"}：${error.message}`,
        "error",
      );
    } finally {
      setBusy(confirmForm, false);
    }
  });
  byId("url-discard").addEventListener("click", () => {
    clearLocalPreview();
    setSubmissionStatus("本地预览视图已丢弃");
  });
}
```

This submits only the seven fields already allowed by
`URLImportCorrections`; it never sends `post_id`, `platform`, `source_type`,
schema version, provenance, privacy, source hash, adapter name, or adapter
version.

- [ ] **Step 5: Add preview styling**

Add:

```css
#url-preview-meta {
  display: grid;
  grid-template-columns: minmax(90px, auto) minmax(0, 1fr);
  gap: 6px 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #faf8f2;
}

#url-preview-meta dt {
  color: var(--muted);
  font-weight: 650;
}

#url-preview-meta dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

#url-unavailable {
  color: var(--warning);
}

#url-confirm-form textarea {
  min-height: 120px;
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: 0.82rem;
}

@media (max-width: 520px) {
  #url-preview-meta {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run focused tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\api tests\adapters\platforms -q
```

- [ ] **Step 7: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web/workbench.js `
  implicit-ad-agent/impad/web/workbench.css `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "feat: add workbench URL review flow"
```

---

### Task 7: Add explicit export controls and complete browser verification

**Files:**
- Modify: `implicit-ad-agent/impad/web/index.html`
- Modify: `implicit-ad-agent/impad/web/workbench.js`
- Modify: `implicit-ad-agent/impad/web/workbench.css`
- Modify: `implicit-ad-agent/tests/web/test_workbench.py`
- Local-only artifact directory: `$env:TEMP\impad-p5-workbench`

**Interfaces:**
- Consumes: all Task 1-6 browser behavior.
- Produces: copy/download helpers, browser-verified desktop/narrow workbench,
  and a final list of UI issues fixed under TDD.

- [ ] **Step 1: Add failing export and accessibility contract tests**

Append:

```python
def test_workbench_script_defines_explicit_copy_and_download_actions(
    tmp_path,
):
    script = _client(tmp_path).get(
        "/workbench/assets/workbench.js"
    ).text

    for required in (
        "navigator.clipboard.writeText",
        "downloadText",
        "URL.createObjectURL",
        "URL.revokeObjectURL",
        "setupExportActions",
    ):
        assert required in script


def test_workbench_has_accessible_status_and_tabs(tmp_path):
    html = _client(tmp_path).get("/workbench").text

    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 3
    assert 'aria-live="polite"' in html
    assert 'aria-label="分析输入"' in html
    assert 'aria-label="分析结果"' in html
```

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web\test_workbench.py `
  -k "copy_and_download or accessible_status" -q
```

Expected: export helper markers are absent; accessibility assertions already
pass and protect Task 2 markup.

- [ ] **Step 3: Implement copy and UTF-8 download helpers**

Use:

```javascript
function actionButton(label, handler) {
  const button = element("button", label, "secondary");
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    setSubmissionStatus(successMessage, "success");
  } catch {
    setSubmissionStatus(
      "浏览器拒绝复制，请从文本区域手动复制",
      "error",
    );
  }
}

function downloadText(filename, text, mediaType) {
  const blob = new Blob([text], {type: mediaType});
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
  setSubmissionStatus(`${filename}已下载`, "success");
}

function setupExportActions() {
  // Export buttons are created only by renderReport/renderRaw after a run.
}
```

The empty setup function is intentional: it documents that export controls
are run-scoped and created by the renderers, while retaining a single
initialization contract.

- [ ] **Step 4: Run focused P5.2 automated gate**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\test_app.py tests\api -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Start a hidden local server for browser monitoring**

In PowerShell:

```powershell
Set-Location implicit-ad-agent
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
$env:PYTHONUTF8 = '1'
$artifactDir = Join-Path $env:TEMP 'impad-p5-workbench'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$server = Start-Process `
  -FilePath '.\.venv\Scripts\python.exe' `
  -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','8765' `
  -WorkingDirectory (Get-Location) `
  -WindowStyle Hidden `
  -PassThru
```

Verify readiness without a long blocking sleep:

```powershell
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  try {
    $health = Invoke-RestMethod `
      -Uri 'http://127.0.0.1:8765/health' `
      -TimeoutSec 2
    if ($health.status -eq 'ok') { break }
  } catch {}
  Start-Sleep -Milliseconds 250
}
if ($health.status -ne 'ok') { throw 'workbench server did not start' }
```

- [ ] **Step 6: Run real-browser functional checks**

Use the `browser:control-in-app-browser` skill and navigate to:

```text
http://127.0.0.1:8765/workbench
```

Verify in order:

1. capability badges report API normal, seven tools, batch maximum 50, and
   URL not configured;
2. URL input/submit are disabled and the explanation is visible;
3. submit a synthetic single record with text
   `品牌合作，广告，限时购买` and `capture_complete=true`;
4. assert a verdict, coverage, evidence, CreatorShift, history, law, trace,
   report, and raw sections render;
5. submit a batch with one valid item, one structurally invalid item missing
   `text`, and a second valid item;
6. assert all three rows remain visible, only the invalid row fails, and each
   successful row can load its own run;
7. click copy and download controls and verify the status message changes;
8. use ArrowLeft/ArrowRight/Home/End on tabs and verify focus/selection;
9. inspect the browser console and confirm zero application errors.

If any behavior fails, write one failing pytest/static contract or a
repeatable browser assertion that reproduces it, then apply the smallest fix
and rerun Steps 4 and 6.

- [ ] **Step 7: Verify desktop and narrow layout**

At 1440px and 390px viewport widths:

- ensure the input rail and result canvas have no overlap;
- ensure no document-level horizontal scrollbar exists;
- ensure all buttons and JSON editors remain reachable;
- ensure long run IDs, hashes, source references, and JSON wrap;
- save screenshots to:
  - `$artifactDir\workbench-desktop.png`;
  - `$artifactDir\workbench-narrow.png`.

Do not add these screenshots to Git.

- [ ] **Step 8: Stop only the server started by this task**

```powershell
if ($server -and -not $server.HasExited) {
  Stop-Process -Id $server.Id
}
```

Confirm port 8765 is no longer owned by that process. Do not terminate other
Python, browser, or Codex processes.

- [ ] **Step 9: Commit**

```powershell
git add -- `
  implicit-ad-agent/impad/web `
  implicit-ad-agent/tests/web/test_workbench.py
git diff --cached --check
git commit -m "test: verify research workbench UX"
```

If browser verification requires no tracked fix after Task 6, do not create
an empty commit; record the verification evidence in Task 8 documentation.

---

### Task 8: Synchronize factual documentation and close the engineering gate

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/已有功能测试指令库.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/隐性广告识别项目_说明书.md`
- Modify: `docs/superpowers/specs/2026-07-30-p5-research-workbench-design.md`
- Modify: `docs/superpowers/plans/2026-07-30-p5-research-workbench.md`

**Interfaces:**
- Consumes: fresh automated/browser verification output and final committed
  implementation.
- Produces: reproducible handoff, copyable test/run commands, and explicit
  incomplete team-UAT/P5.3-P5.7/M1/M4/M5 boundaries.

- [ ] **Step 1: Run dependency and compilation checks**

```powershell
Set-Location implicit-ad-agent
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q `
  impad tests scripts app.py run_demo.py run_tools_demo.py
```

Both commands must exit zero; `pip check` must report
`No broken requirements found.`.

- [ ] **Step 2: Run focused and full pytest gates**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\test_app.py tests\api -q
.\.venv\Scripts\python.exe -m pytest -q
```

Record the exact fresh pass/skip/warning counts emitted by these commands.
Do not copy pre-P5.2 counts into the current-status sections.

- [ ] **Step 3: Run both P1 asset validators**

From the repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe `
  scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe `
  data-tooling\validate_submission_assets.py
```

Both must output `VALIDATION PASSED`.

- [ ] **Step 4: Run security and remote-asset scans**

```powershell
$script = Get-Content -Raw -Encoding UTF8 `
  implicit-ad-agent\impad\web\workbench.js
$html = Get-Content -Raw -Encoding UTF8 `
  implicit-ad-agent\impad\web\index.html
$css = Get-Content -Raw -Encoding UTF8 `
  implicit-ad-agent\impad\web\workbench.css

$forbidden = @(
  'innerHTML',
  'outerHTML',
  'insertAdjacentHTML',
  'localStorage',
  'sessionStorage',
  'indexedDB',
  'document.cookie',
  'serviceWorker'
)
foreach ($pattern in $forbidden) {
  if ($script.Contains($pattern)) {
    throw "forbidden workbench API: $pattern"
  }
}
if ($html -match 'https?://' -or $css -match 'url\\(https?://') {
  throw 'remote workbench asset reference found'
}

$secretMatches = rg -n `
  'api[_-]?key\\s*[=:]|access[_-]?token\\s*[=:]|bearer\\s+[A-Za-z0-9]' `
  implicit-ad-agent\impad\web HANDOFF.md docs
if ($LASTEXITCODE -gt 1) { throw 'secret scan failed to run' }
if ($LASTEXITCODE -eq 0) {
  $secretMatches
  throw 'possible secret assignment found'
}

git diff --check
```

- [ ] **Step 5: Update `HANDOFF.md`**

Add a dated P5.2 engineering-admission section that records:

- same-origin no-build `/workbench`;
- single, batch, and capability-gated URL input;
- complete evidence/run rendering;
- security/no-storage constraints;
- browser desktop/narrow checks;
- exact focused/full counts;
- no team UAT, live adapters, A2A, or M5 claim.

Update the current module table, default regression row, next-step order, and
copyable P5.2 focused command.

- [ ] **Step 6: Update the existing-function test library**

Add a P5.2 section containing:

- the focused pytest command;
- zero-key server start command;
- `/workbench` URL;
- one copyable synthetic single request workflow;
- one copyable mixed-validity batch workflow;
- the expected default URL-unavailable behavior;
- browser verification checklist;
- exact current test snapshot;
- explicit statements about what the checks cannot prove.

Update stale “current” counts and the FastAPI feature table without rewriting
historical snapshots.

- [ ] **Step 7: Update phase plan and system specification**

In the phase plan:

- mark 5.2 engineering implementation complete but team UAT pending;
- keep P5.3-P5.7 and M5 incomplete.

In the project specification:

- change the research-workbench module from planned to implemented;
- document `/workbench`, its existing API dependencies, safe rendering, and
  no-build/no-storage boundaries;
- keep real platform adapters and A2A planned.

- [ ] **Step 8: Mark design status and record verification**

Change the design status to `Implemented and verified on 2026-07-30` and add
the exact:

- focused/full pytest counts;
- dependency/compilation results;
- validator results;
- browser checks and screenshot locations;
- known existing warning;
- non-claims.

- [ ] **Step 9: Review every acceptance criterion**

For each of the ten acceptance criteria in the design, identify direct
evidence from:

- production files;
- committed pytest tests;
- fresh command output;
- browser state and screenshots;
- synchronized documents.

Fix any criterion whose evidence is missing or indirect. Re-run the affected
focused check after every fix.

- [ ] **Step 10: Commit factual documentation**

```powershell
git add -- `
  HANDOFF.md `
  docs/已有功能测试指令库.md `
  docs/隐性广告识别项目_分阶段计划表.md `
  docs/隐性广告识别项目_说明书.md `
  docs/superpowers/specs/2026-07-30-p5-research-workbench-design.md `
  docs/superpowers/plans/2026-07-30-p5-research-workbench.md
git diff --cached --check
git commit -m "docs: record P5 research workbench admission"
```

- [ ] **Step 11: Final repository audit**

```powershell
git status --short --branch
git log -15 --oneline
git diff --check
rg -n "^- \\[ \\]" `
  docs\superpowers\plans\2026-07-30-p5-research-workbench.md
```

Completion requires a clean worktree, no unchecked implementation-plan step,
fresh evidence for every acceptance criterion, synchronized required
documents, and explicit incomplete team-UAT/P5.3-P5.7/M1/M4/M5 boundaries.
