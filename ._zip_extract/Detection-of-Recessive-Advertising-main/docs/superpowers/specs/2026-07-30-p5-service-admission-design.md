# P5.1 Batch and URL Service Admission Design

**Date:** 2026-07-30
**Status:** Implemented and verified on 2026-07-30
**Scope:** P5.1 batch analysis and URL preview/confirm service boundary

## 1. Goal

Complete the first P5 engineering slice without depending on new P1 data,
live platform access, a Web UI, or A2A:

1. add bounded batch analysis that reuses `AnalysisService.analyze()`;
2. add a safe URL preview/confirm workflow around an injectable
   `PlatformAdapter`;
3. preserve explicit capture gaps and user corrections;
4. keep default tests zero-key and zero-network;
5. synchronize `HANDOFF.md` and
   `docs/已有功能测试指令库.md`.

This slice is P5.1 engineering admission only. It does not complete the P5
milestone or claim that Xiaohongshu/Bilibili live adapters, the research
workbench, or A2A are available.

## 2. Current Facts

- `POST /api/v1/analyze` already delegates to one `AnalysisService`.
- `AnalysisService.analyze()` owns graph execution, legal retrieval, readable
  reporting, and run persistence.
- `PostRecord` and `CaptureStatus` are the normalized runtime boundary.
- Before this slice, the API had no batch endpoint, platform adapter contract,
  URL preview, or URL confirmation workflow.
- P5.3 and P5.4 separately own live Xiaohongshu and Bilibili adapters.
- The verified pre-P5.1 default baseline is
  `326 passed, 2 skipped, 1 warning`.
- Formal M1 and M4 remain incomplete.

## 3. Considered Approaches

### A. Batch endpoint only

This is the smallest change, but it leaves half of the explicit P5.1
deliverable (`URL preview/confirm API`) unimplemented. Rejected.

### B. Implement live Xiaohongshu and Bilibili fetching now

This would collapse P5.1, P5.3, and P5.4 into one change and introduce
network, access-control, terms, login, anti-bot, and fixture-provenance
questions before the service contract is stable. Rejected.

### C. Batch plus adapter-driven URL preview/confirm

Add the complete service boundary now, but keep live adapters out of scope.
Tests inject a static adapter; the default application advertises no supported
platform hosts and rejects unsupported URLs. This is the selected approach.

## 4. Batch Analysis

Add:

- `AnalysisService.analyze_batch(items)`;
- `POST /api/v1/analyze/batch`;
- a request limit of 1 to 50 items;
- per-item success/error results and aggregate counts.

Each item retains its own `runtime_mode`. The batch method calls
`AnalysisService.analyze()` once per item rather than duplicating graph,
retrieval, report, or persistence logic.

Errors are isolated per item:

- validation and normalization errors become `invalid_input`;
- unexpected execution failures become `analysis_failed`;
- error messages are safe summaries and do not expose input text, paths,
  credentials, or exception details;
- one failed item does not prevent later valid items from running.

Batch is intentionally sequential in this slice. Concurrency, scheduling,
streaming, cancellation, and high-throughput operation are non-goals.

## 5. Platform Adapter Boundary

Add `impad.adapters.platforms` with:

- `PlatformAdapter` protocol;
- `PlatformAdapterRegistry`;
- `URLImportService`;
- structured URL preview and correction contracts;
- explicit `URLImportError` codes.

A `PlatformAdapter`:

- declares a stable name, version, platform, and supported hosts;
- receives one validated HTTPS URL;
- returns a fully validated `PostRecord`;
- records only a hash of the source reference in provenance;
- must preserve missing capture state instead of inventing fields.

The default registry is empty until P5.3/P5.4 add approved live adapters.
Unsupported hosts fail closed. Tests use an injected static adapter and never
access the network.

## 6. URL Safety

The shared URL validator:

- accepts HTTPS only;
- rejects usernames/passwords in authority;
- rejects fragments from the fetch target;
- permits only the default HTTPS port;
- rejects `localhost`, `.localhost`, `.local`, `.internal`, and IP literals
  that are loopback, private, link-local, multicast, reserved, or unspecified;
- requires a registry match before any adapter is called.

The preview response exposes a display URL containing scheme, normalized host,
and path only. Query and fragment values are not returned, logged, committed,
or persisted in a run. A SHA-256 `source_ref_hash` provides traceability
without exposing the original reference.

DNS resolution and redirect validation belong to each future live adapter and
must repeat the public-destination check after every resolution/redirect. This
slice makes no network request and does not claim DNS-rebinding protection is
fully implemented.

## 7. Preview and Confirm Flow

### Preview

`POST /api/v1/import/url/preview`:

1. validates the URL;
2. selects one registered adapter;
3. obtains a normalized `PostRecord`;
4. returns an opaque `preview_id`, adapter/platform/version, display URL,
   source hash, the normalized post, and capture audit;
5. does not run classification or persist an analysis run.

Pending previews are process-local, bounded, and one-time. They are not a
durable job queue. Confirmation atomically claims a preview; concurrent
confirmations fail closed, validation/analysis failure releases the claim, and
successful analysis consumes it.

### Confirm

`POST /api/v1/import/url/confirm`:

1. loads the pending preview;
2. applies only allowlisted corrections;
3. revalidates the entire `PostRecord`;
4. appends changed field names to
   `CaptureStatus.user_corrections`;
5. calls the same `AnalysisService.analyze()`;
6. consumes the preview only after successful analysis.

Allowlisted corrections are:

- `text`;
- `creator_id`;
- `published_at`;
- `media`;
- `comments`;
- `history`;
- `capture_status`.

`post_id`, `platform`, `source_type`, schema version, provenance, privacy, and
source hash cannot be replaced through confirmation.

## 8. API Contracts

Add:

- `BatchAnalyzeRequest`, `BatchAnalyzeResponse`,
  `BatchAnalyzeItemResponse`;
- `URLPreviewRequest`, `URLPreviewResponse`;
- `URLImportCorrections`, `URLConfirmRequest`.

New endpoints:

- `POST /api/v1/analyze/batch`;
- `POST /api/v1/import/url/preview`;
- `POST /api/v1/import/url/confirm`.

`GET /api/v1/capabilities` reports:

- batch availability and maximum item count;
- URL preview/confirm availability;
- currently registered platform names and hosts.

The compatibility `/analyze` route remains unchanged.

## 9. Error Mapping

| Condition | HTTP/result behavior |
| --- | --- |
| empty or oversized batch | request validation `422` |
| invalid batch item during analysis | item `invalid_input`; other items continue |
| unexpected batch execution failure | item `analysis_failed`; other items continue |
| unsafe or malformed URL | `422` with stable URL error code |
| unsupported host | `422` with `unsupported_url_host` |
| adapter normalization failure | `422` with safe `adapter_failed` |
| missing/consumed preview | `404` with `preview_not_found` |
| invalid corrections | `422`; preview remains available |
| analysis failure after confirmation | existing safe API failure; preview remains available |

## 10. Testing

Default tests cover:

- batch size bounds;
- two successful items create two independent runs;
- one invalid item does not block a later valid item;
- service batch calls the existing single-item method;
- HTTPS/public-host validation and unsafe URL rejection;
- unsupported hosts fail before adapter execution;
- preview returns normalized capture audit without creating a run;
- display/persisted data omit URL query and fragment;
- confirmation records allowlisted corrections and persists one run;
- consumed or unknown preview IDs fail closed;
- invalid corrections do not consume a preview;
- capabilities report only registered adapters;
- all existing single-item routes remain unchanged.

No test makes a real network request.

Review-driven regressions also cover:

- concurrent confirmation of one preview;
- mutation of a returned preview object;
- attempted capture-audit metadata forgery;
- short query values that legitimately occur in post text;
- decoded query values containing JSON-escaped characters;
- internal execution `ValueError` classification;
- structurally invalid API items that must not abort a batch.

## 11. Acceptance Criteria

1. Batch requests accept 1-50 items and report per-item success/error.
2. Batch processing reuses `AnalysisService.analyze()` and isolates failures.
3. URL preview requires an explicitly registered adapter and makes no default
   network request.
4. Unsafe schemes, authorities, ports, local/private destinations, and
   unsupported hosts are rejected before adapter execution.
5. Preview does not create an analysis run.
6. Confirmation applies only allowlisted corrections, records the correction
   fields, revalidates `PostRecord`, and then creates exactly one run.
7. Query/fragment secrets do not appear in preview responses, run records,
   generated fixtures, or documentation.
8. Focused and full tests, `pip check`, compilation, both P1 validators,
   security scans, and `git diff --check` pass.
9. `HANDOFF.md`, the existing-function test library, phase plan, and
   specification state both the implemented P5.1 facts and the incomplete
   P5.2-P5.7/M1/M4 boundaries.

## 12. Non-goals

- live Xiaohongshu, Bilibili, or Douyin fetching;
- login, cookies, access-control bypass, scraping evasion, or browser
  automation;
- Web UI;
- A2A services or local/A2A comparison;
- durable preview storage or distributed batch jobs;
- high concurrency, accounts, RBAC, or multi-tenant operation;
- changing classification, CreatorShift, Judge, RAG, or M1 logic;
- claiming P5 or M5 completion.

## 13. Verification Evidence

- focused P5.1 gate: `58 passed, 1 warning`;
- default full gate: `380 passed, 2 skipped, 1 warning`;
- `pip check`: `No broken requirements found.`;
- compilation: passed for `impad`, tests, scripts, and application/demo
  entrypoints;
- both P1 asset validators: `VALIDATION PASSED`;
- two independent code reviews: no Critical findings; all Important findings
  were either already fixed or closed with regression tests;
- the warning is the pre-existing Starlette/httpx deprecation warning.

These results admit only the P5.1 engineering boundary. They do not admit
P5/M5, M1, or M4.
