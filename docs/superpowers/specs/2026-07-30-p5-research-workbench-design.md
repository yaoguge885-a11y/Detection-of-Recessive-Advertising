# P5.2 Research Workbench Engineering Admission Design

**Date:** 2026-07-30
**Status:** Approved by the user on 2026-07-30
**Scope:** Same-origin developer research workbench for the existing P5.1 API

## 1. Goal

Complete the P5.2 engineering implementation needed by the four project
developers to exercise the existing evidence pipeline from a browser:

1. accept single-item, batch, and URL-preview input;
2. render verdict, review state, evidence, capture gaps, CreatorShift history,
   legal citations, run metadata, and run events;
3. expose the P5.1 preview/correction/confirm workflow without inventing a
   live platform adapter;
4. provide raw JSON and readable-report inspection/export for reproducibility;
5. keep the default path zero-key, zero-network, and free of a Node build
   dependency;
6. synchronize current-state and testing documentation after verification.

This is P5.2 engineering admission. It does not complete P5 or M5 and does not
claim team user-acceptance testing, live Xiaohongshu/Bilibili capture, A2A, or
research accuracy.

## 2. Current Facts

- The current branch is a normal checkout of
  `P2_Tool-Compartment-Model-Tooling`.
- P5.1 already provides:
  - `POST /api/v1/analyze`;
  - `POST /api/v1/analyze/batch`;
  - `POST /api/v1/import/url/preview`;
  - `POST /api/v1/import/url/confirm`;
  - `GET /api/v1/runs/{run_id}`;
  - `GET /api/v1/capabilities`.
- The default platform adapter registry is empty and makes no network request.
- The repository has no existing frontend package, Node manifest, Vite
  configuration, or established component system.
- The verified pre-P5.2 default baseline is
  `380 passed, 2 skipped, 1 warning`.
- Formal M1 and M4 remain incomplete; P5.3-P5.7 have not been implemented.

## 3. Considered Approaches

### A. Same-origin static HTML, CSS, and JavaScript

FastAPI serves one workbench document and repository-owned assets. The browser
calls the existing `/api/v1` contracts. This adds no build tool, package
manager, frontend runtime, or duplicate backend logic.

This is the selected approach because the first users are four developers,
the current repository is Python-only, and the workbench can satisfy the P5.2
interaction requirements without introducing a second toolchain.

### B. Jinja server-side rendering

Server-rendered forms would be simple for single-item analysis, but batch
selection, URL preview/correction, result switching, evidence filtering, and
raw export would still require substantial browser state. It would also
tempt the server layer to duplicate API presentation logic. Rejected.

### C. Vite/React single-page application

This offers the richest long-term component ecosystem, but it introduces a
Node build chain, frontend dependency updates, generated artifacts, and a
second test stack before the workbench interaction model is proven. Rejected
for P5.2; it can be reconsidered only if later product requirements outgrow
the no-build implementation.

## 4. Round Scope and Boundaries

This round delivers one complete P5.2 engineering slice:

- a loadable `/workbench`;
- three input modes;
- one reusable result workspace;
- deterministic error/empty/loading states;
- browser and automated verification;
- synchronized handoff, phase, specification, and test documentation.

It does not include:

- a live Xiaohongshu, Bilibili, or Douyin adapter;
- DNS or redirect checks for a future network adapter;
- login, cookies, CAPTCHA, scraping evasion, or access-control bypass;
- accounts, RBAC, server-side sessions, a database, or multi-tenancy;
- WebSocket progress, distributed jobs, or high-throughput scheduling;
- A2A services or local/A2A comparisons;
- changes to classification, CreatorShift, Judge, RAG, or M1 logic;
- a claim that four-person user-acceptance testing or M5 has passed.

## 5. Architecture and Files

Add a focused `impad/web` asset package:

- `implicit-ad-agent/impad/web/index.html`
  - semantic workbench structure only;
  - no inline style, script, or untrusted initial data;
- `implicit-ad-agent/impad/web/workbench.css`
  - responsive visual system and component states;
- `implicit-ad-agent/impad/web/workbench.js`
  - capability loading, input normalization, API calls, safe DOM rendering,
    export, and view state;
- `implicit-ad-agent/impad/web/__init__.py`
  - marks assets as package-owned and provides a stable asset-directory
    resolver.

Modify `implicit-ad-agent/app.py` to:

- mount `/workbench/assets` from the package asset directory;
- serve `index.html` at `GET /workbench`;
- add a visible workbench link on `/`;
- attach the document security headers defined below;
- leave every existing API and compatibility route unchanged.

Add `implicit-ad-agent/tests/web/test_workbench.py` for route, document,
asset, and security invariants. Existing API/service tests remain the source
of truth for analysis behavior.

No new runtime dependency or Node package is added.

## 6. Workbench Layout

### 6.1 Header and capability status

The header contains:

- project name and the phrase “开发者研究工作台”;
- local/MCP runtime selector;
- API health/capability status;
- batch limit;
- registered URL platforms;
- a visible statement when no URL adapter is configured.

The capability response drives these values. The UI does not hard-code a
platform as available.

### 6.2 Input workspace

Three tabs share one submission-status region:

1. **单条分析**
   - text;
   - optional post ID, platform, creator, and publication time;
   - comments and history as JSON arrays;
   - capture-complete checkbox;
   - analyze and clear actions.
2. **批量分析**
   - JSON editor accepting the API `items` array or an object containing
     `items`;
   - local `.json` file loading through `FileReader`;
   - item count display and the server maximum;
   - submit and clear actions.
3. **URL预览**
   - URL input and preview action;
   - capability-driven disabled state when no adapter is registered;
   - sanitized display URL, adapter name/version, source hash, normalized
     capture audit, and editable corrections after a successful preview;
   - direct fields for text, creator ID, and publication time;
   - JSON editors for media, comments, history, and capture status;
   - confirm and discard-local-view actions.

After a successful URL preview, the original URL input is cleared. Only the
server-provided display URL is rendered.

### 6.3 Result workspace

One result workspace is reused by single, batch, and confirmed URL analyses.
It contains:

- verdict label, confidence, review-required state, commercial intent,
  disclosure state, reasons, run status, mode, and duration;
- coverage and missing-requirement summaries;
- evidence cards grouped by `source_type`, showing polarity, status, quote,
  score/strength, producer, source reference, related IDs, and limitations;
- explicit conflict cards rather than hiding conflicts in majority summaries;
- a CreatorShift card showing status, history count/requirement, method,
  score when valid, feature deltas, top features, and limitations;
- a chronological history timeline from the persisted `RunRecord.post`,
  followed by the target post; missing timestamps remain visibly unknown;
- legal-evidence cards with title, article, version, quote, score, and
  limitations;
- a run-event table ordered by timestamp, with event type, stage, tool,
  call ID, and safe serialized data;
- run issues, tool/model versions, retry/fallback counts, and trace IDs;
- readable Markdown report as text;
- raw response and complete run JSON viewers;
- copy and UTF-8 JSON/Markdown download actions.

External citation links are clickable only when their parsed protocol is
`https:`. Other source references are rendered as text.

### 6.4 Batch result selection

Batch submission renders every item in original order:

- success rows show index, label, review state, run ID, and a “查看” action;
- failure rows show index and the stable safe error code/message;
- selecting a successful row loads its complete run by `run_id` and renders
  the shared result workspace;
- failures remain visible and do not prevent successful results from being
  inspected.

## 7. Browser Data Flow

On startup:

```text
GET /health + GET /api/v1/capabilities
  -> capability badges
  -> runtime options
  -> batch limit
  -> URL availability
```

Single analysis:

```text
form -> POST /api/v1/analyze
  -> AnalyzeResponse
  -> GET /api/v1/runs/{run_id}
  -> shared result workspace
```

Batch analysis:

```text
JSON/file -> POST /api/v1/analyze/batch
  -> ordered per-item list
  -> select successful run_id
  -> GET /api/v1/runs/{run_id}
  -> shared result workspace
```

URL analysis:

```text
URL -> POST /api/v1/import/url/preview
  -> sanitized preview + capture audit
  -> allowlisted corrections
  -> POST /api/v1/import/url/confirm
  -> AnalyzeResponse
  -> GET /api/v1/runs/{run_id}
  -> shared result workspace
```

The browser never calls LangGraph nodes, tools, RAG, or the run store
directly.

## 8. State and Error Handling

Each action has `idle`, `loading`, `success`, and `error` presentation states.
While a request is loading:

- its submit button is disabled;
- the status region names the active operation;
- duplicate submission is prevented;
- other completed results remain available.

Client-side parsing rejects:

- comments/history values that are not JSON arrays;
- batch values that do not resolve to a non-empty `items` array;
- batches over the capability limit;
- correction editors whose values have the wrong top-level JSON type.

Server responses remain authoritative. HTTP error rendering shows the stable
API code/message when present and a generic status message otherwise. It does
not display stack traces, response headers, request bodies, or caught
exception objects.

The workbench does not add an aggressive client timeout. Users can clear the
local view after a request finishes; backend timeout and fallback behavior
remain owned by the existing service.

## 9. Security and Privacy

The workbench follows these mandatory rules:

- untrusted strings are inserted with `textContent`, not `innerHTML`;
- static markup contains no inline script, inline event handler, or inline
  style;
- the document response sets:
  - `Content-Security-Policy: default-src 'self'; script-src 'self';
    style-src 'self'; img-src 'self' data:; connect-src 'self';
    object-src 'none'; base-uri 'none'; frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `Cache-Control: no-store`;
- browser storage, cookies, IndexedDB, service workers, analytics, and remote
  assets are not used;
- input values exist only in form state and memory for the current page;
- downloads happen only after an explicit user action;
- raw URL query/fragment values are not copied into result state or export;
- future adapters remain responsible for their own approved network,
  resolution, redirect, and compliance boundaries.

## 10. Visual Direction

The workbench uses a restrained research-console style:

- warm off-white page background;
- dark ink text with blue-violet evidence accents;
- amber for review/degraded states, red only for errors, and green only for
  completed states;
- a two-column desktop layout with a sticky input rail and result canvas;
- one-column layout below 860px;
- cards with clear hierarchy rather than dashboard-chart decoration;
- system fonts and no remote icons or fonts;
- visible focus indicators, keyboard-operable tabs, labels for every control,
  and status regions using appropriate ARIA live behavior;
- no horizontal overflow at 390px viewport width.

## 11. Testing and Monitoring

### 11.1 Automated tests

Tests must verify:

- `/workbench` returns UTF-8 HTML;
- the document references only same-origin repository assets;
- required input/result landmarks exist;
- no inline scripts, inline event handlers, remote assets, browser-storage
  calls, or unsafe `innerHTML` assignments exist;
- all required security headers are present;
- CSS and JavaScript assets return the correct media types;
- `/` links to `/workbench`;
- `/health`, compatibility `/analyze`, and all `/api/v1` routes retain their
  existing behavior.

The focused P5.2 gate is:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\web tests\test_app.py tests\api -q
```

### 11.2 Browser verification

Run the local app with zero tracing and use a real browser to verify:

1. initial health/capability state;
2. one synthetic single-item analysis;
3. one two-item batch and result switching;
4. one structurally invalid batch item;
5. the default no-adapter URL state;
6. evidence, history, legal, report, raw JSON, and trace rendering;
7. copy/download controls;
8. keyboard tab navigation;
9. desktop and 390px responsive layouts;
10. browser console contains no application errors.

Capture desktop and narrow screenshots as local verification artifacts. They
are not committed unless explicitly needed by later project documentation.

### 11.3 Completion gate

Before completion:

- run the focused P5.2 gate;
- run the full default pytest suite;
- run `pip check` and `compileall`;
- run both P1 asset validators;
- scan runtime and documentation paths for fixture secrets and remote asset
  references;
- run `git diff --check`;
- review the cumulative change against every acceptance criterion;
- synchronize `HANDOFF.md`, `docs/已有功能测试指令库.md`,
  `docs/隐性广告识别项目_分阶段计划表.md`, and
  `docs/隐性广告识别项目_说明书.md`.

## 12. Acceptance Criteria

1. `/workbench` loads from the existing FastAPI application without a
   frontend build or network dependency.
2. Single-item and two-item batch synthetic analyses complete through the
   existing APIs and render complete persisted runs.
3. Batch success and failure items remain independently visible and
   selectable.
4. The URL tab reflects registered capabilities; the default empty registry
   is visibly unavailable and makes no network request.
5. The UI implements the P5.1 preview/correction/confirm contract without
   persisting the original URL or expanding correction permissions.
6. Verdict, review state, evidence, coverage, gaps, conflicts, CreatorShift,
   history timeline, law evidence, run metadata, run issues, run events,
   readable report, and raw JSON all have explicit renderers.
7. Untrusted content has no HTML execution path, and the document security
   headers and no-storage boundary are verified.
8. Desktop and 390px browser checks show no broken layout or horizontal
   overflow, and the browser console has no application errors.
9. Focused/full tests, dependency/compilation checks, both P1 validators,
   security scans, and `git diff --check` pass.
10. Required project documents state the implemented P5.2 engineering facts
    and the incomplete team UAT, P5.3-P5.7, M1, M4, and M5 boundaries.

## 13. Explicit Non-claims

A green workbench gate proves that the current browser client can operate the
existing local contracts and render their evidence safely. It does not prove:

- classification accuracy or CreatorShift research gain;
- complete or legally sufficient rule coverage;
- live platform URL availability;
- remote MCP or A2A deployment;
- four-person UAT;
- P5 or M5 completion.
