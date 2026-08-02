# P2.5 to P3 Readiness Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the documented P1/P2.5 prerequisites so the repository can begin P3 with a validated `PostRecord → CapabilityPlan → ToolResult[] → EvidenceBundle → Evidence Adequacy Gate → VerdictReport` boundary.

**Architecture:** Keep the current seven P2 tools and their scoring logic unchanged. Add a thin P1/manual input boundary, deterministic tool-argument and evidence adapters, a conservative adequacy/judgment baseline, then reconnect the existing Supervisor/NLP/Vision/Behavior/Judge graph through those shared modules. P3 remains responsible for MCPToolGateway, real legal-corpus integration, the unified analysis service/API split, and the larger graph/service refactor; empirical Judge calibration remains P4.

**Tech Stack:** Python 3.10, Pydantic 2, JSON Schema Draft 2020-12 via `jsonschema`, LangGraph, LangChain tools, pytest.

## Global Constraints

- `data/schema/data_schema_v1.json` remains the only authoritative P1 dataset schema.
- Do not modify the score logic in the seven files under `impad/tools/`.
- Missing, skipped, unavailable, or errored modalities must not become zero-score negative evidence.
- `暗广` requires present commercial intent, no found disclosure, and capture sufficient to assess disclosure.
- Unknown disclosure or critical missing evidence produces `需复核`.
- Creator history used by runtime tools must be same-creator and strictly earlier than the target post when timestamps are available.
- Default verification is zero-Key and zero-network; real vision stays explicitly opt-in.
- Preserve existing user changes in the dirty working tree and do not create an isolated worktree that omits them.
- This execution does not commit, stage, push, or open a PR unless the user separately requests it.

---

### Task 1: Runtime PostRecord and CaptureStatus contracts

**Files:**
- Create: `implicit-ad-agent/impad/contracts/post.py`
- Modify: `implicit-ad-agent/impad/contracts/__init__.py`
- Create: `implicit-ad-agent/tests/contracts/test_post_record.py`

**Interfaces:**
- Produces: `CaptureModality`, `CaptureStatus`, `MediaRecord`, `CommentRecord`, `HistoryPost`, `PostRecord`.
- Consumes: P1 field meanings from `data/schema/data_schema_v1.json`; no direct P1 JSON validation occurs in this task.

- [x] **Step 1: Write failing contract tests**

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.post import (
    CaptureModality,
    CaptureStatus,
    HistoryPost,
    PostRecord,
)


def test_post_record_rejects_future_or_cross_creator_resolved_history():
    target_time = datetime(2026, 7, 20, tzinfo=timezone.utc)
    capture = CaptureStatus(
        source="manual",
        modalities={"text": CaptureModality(status="complete")},
    )
    with pytest.raises(ValidationError, match="same creator"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=target_time,
            text="正文",
            capture_status=capture,
            history=[HistoryPost(
                post_id="post_other",
                creator_id="blogger_b",
                text="历史",
                published_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )],
        )


def test_post_record_serializes_capture_and_preserves_missing_as_state():
    post = PostRecord(
        schema_version="runtime-1",
        post_id="post_1",
        platform="other",
        source_type="manual",
        creator_id="blogger_1",
        text="正文",
        capture_status=CaptureStatus(
            source="manual",
            modalities={
                "text": CaptureModality(status="complete"),
                "image": CaptureModality(
                    status="missing",
                    missing_fields=["media.ref"],
                ),
            },
            can_assess_disclosure=False,
        ),
    )
    dumped = post.model_dump(mode="json")
    assert dumped["capture_status"]["modalities"]["image"]["status"] == "missing"
    assert dumped["capture_status"]["can_assess_disclosure"] is False
```

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_post_record.py -q
```

Expected: collection fails because `impad.contracts.post` does not exist.

- [x] **Step 3: Implement the contracts**

Implement strict Pydantic models with these fields:

```python
CaptureState = Literal["complete", "partial", "missing", "not_applicable"]
CaptureModalityName = Literal["text", "image", "comment", "history", "metadata"]

class CaptureModality(BaseModel):
    status: CaptureState
    captured_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

class CaptureStatus(BaseModel):
    source: str
    modalities: dict[CaptureModalityName, CaptureModality]
    can_assess_disclosure: bool = False
    adapter_version: str = "1.0"
    captured_at: datetime | None = None
    user_corrections: list[str] = Field(default_factory=list)
```

`PostRecord` must use `creator_id` as the runtime field, keep P1 `source_type`, media/comments/history/history_refs/provenance/privacy, reject extra fields, and validate that every resolved history item has the same creator and is strictly earlier when both timestamps exist.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_post_record.py -q
.\.venv\Scripts\python.exe -m pytest tests/contracts -q
```

Expected: all contract tests pass.

---

### Task 2: P1 and manual input adapters

**Files:**
- Modify: `implicit-ad-agent/pyproject.toml`
- Create: `implicit-ad-agent/impad/adapters/__init__.py`
- Create: `implicit-ad-agent/impad/adapters/p1_schema.py`
- Create: `implicit-ad-agent/impad/adapters/manual.py`
- Create: `implicit-ad-agent/tests/adapters/__init__.py`
- Create: `implicit-ad-agent/tests/adapters/test_p1_schema_adapter.py`
- Create: `implicit-ad-agent/tests/adapters/test_manual_adapter.py`

**Interfaces:**
- Consumes: `PostRecord`, `CaptureStatus`, and repository-root `data/schema/data_schema_v1.json`.
- Produces: `post_record_from_content_record(record: dict) -> PostRecord` and `post_record_from_manual(record: dict) -> PostRecord`.

- [x] **Step 1: Write failing P1 adapter tests**

Use the first content record from `data/synthetic/simulated_posts_v1.json` as the real fixture. Assert literal mapped values:

```python
post = post_record_from_content_record(record)
assert post.post_id == "post_explicit_sponsor"
assert post.creator_id == "blogger_style_001"
assert post.media[0].ref == "media/post_explicit_sponsor/01.jpg"
assert post.capture_status.source == "p1_schema_v1"
assert post.capture_status.can_assess_disclosure is True
```

Copy the record, add an unknown field, and assert the JSON Schema error contains that field name. Copy the record, remove `privacy`, and assert the error points to `privacy`. This proves the adapter validates against the authoritative schema before mapping and never silently drops unknown data.

- [x] **Step 2: Verify P1 RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/adapters/test_p1_schema_adapter.py -q
```

Expected: collection fails because the adapter does not exist.

- [x] **Step 3: Implement authoritative P1 validation and mapping**

Add the direct runtime dependency:

```toml
"jsonschema>=4.22,<5",
```

Resolve the schema with `Path(__file__).resolve().parents[3] / "data/schema/data_schema_v1.json"`, use `Draft202012Validator`, sort validation errors by their absolute path, and raise a `ValueError` containing the JSON path plus validator message. Map `blogger_id → creator_id`; do not mutate the input record.

For capture status:

- text is `complete` when non-empty, otherwise `not_applicable`;
- image is `complete` only when every image has a non-empty ref, `partial` when some image refs are absent, and `not_applicable` when no image exists;
- comment is `complete` when the source field is present, otherwise `missing`;
- history is `partial` when unresolved refs exist, otherwise `not_applicable`;
- `can_assess_disclosure=True` only for a fully synthetic record whose text/image capture is complete or not applicable.

- [x] **Step 4: Write and verify failing manual-adapter tests**

Tests must assert:

- legacy `blogger`, string comments, string history, and `image_path` normalize into runtime records;
- history receives the current creator and remains ordered;
- manual input defaults to `can_assess_disclosure=False`;
- an explicit manual `capture_complete=True` makes disclosure assessable only when supplied local modalities are complete.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/adapters/test_manual_adapter.py -q
```

Expected: collection fails because the manual adapter does not exist.

- [x] **Step 5: Implement the minimal manual adapter**

Generate stable `post_manual_<sha256-prefix>` and `blogger_manual_<sha256-prefix>` identifiers from normalized input when IDs are absent. Map legacy strings into `CommentRecord` and `HistoryPost` without fabricating timestamps. Reject remote `http/https` image URLs as local-image capability; retain them only as unavailable metadata until P5 platform adapters exist.

- [x] **Step 6: Verify adapters GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/adapters -q
.\.venv\Scripts\python.exe -m pip check
```

Expected: all adapter tests and dependency checks pass.

---

### Task 3: Post-to-tool capability and argument adapter

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/post_tools.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_post_tools.py`

**Interfaces:**
- Consumes: `PostRecord`, `CapabilityPlanner`, and the seven registered tool schemas.
- Produces: `capability_context_from_post(post)`, `function_calls_from_post(post, plan, tool_names=None)`, and `execute_post_tools(...)`.

- [x] **Step 1: Write failing behavior tests**

Create a post with non-empty text, five comments, three earlier history posts, and one real temporary local image file. Assert the generated names are exactly:

```python
{
    "analyze_text_intent",
    "sentiment_curve",
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
    "topic_drift",
    "comment_anomaly",
}
```

Also assert a text-only post exposes only text tools, a remote image URL does not create image capability, comments below five omit `comment_anomaly`, history below three omits `topic_drift`, and every generated arguments dict validates against its real registered tool schema.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_post_tools.py -q
```

Expected: collection fails because `post_tools` does not exist.

- [x] **Step 3: Implement deterministic argument generation**

Use the first existing local image ref only. Serialize comments with IDs and history with post ID, text, and ISO timestamp. Filter optional `tool_names` against `plan.available_tools`; preserve registry order; generate provider-neutral calls shaped as:

```python
{"id": f"call_{tool_name}", "name": tool_name, "args": arguments}
```

`execute_post_tools` must call `RestrictedFunctionCaller.execute` with the supplied plan, `RunContext`, and optional recorder. It must never invoke tools directly.

- [x] **Step 4: Verify GREEN and orchestration regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_post_tools.py -q
.\.venv\Scripts\python.exe -m pytest tests/orchestration -q
```

Expected: all tests pass without loading real vision models.

---

### Task 4: Seven-tool EvidenceAdapter and bundle construction

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/evidence_adapters.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_evidence_adapters.py`

**Interfaces:**
- Consumes: `PostRecord`, `ToolResult[]`, and `ToolEvidence`.
- Produces: `evidence_items_from_tool_result(result)` and `build_evidence_bundle(post, results)`.

- [x] **Step 1: Write failing evidence-adapter tests**

Add one literal result fixture for each of the seven tool names. Assert:

- each non-empty, usable observation becomes a traceable `EvidenceItem`;
- `source_ref`, span, bbox, related post ID, and comment IDs survive conversion;
- skipped/error results remain only in `bundle.tool_results` and create no item;
- tool evidence with `kind in {"absence", "insufficient"}` creates no negative item;
- evidence IDs are deterministic and unique;
- capture partial/missing states become coverage and `missing_requirements`;
- ToolResult limitations are preserved.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_evidence_adapters.py -q
```

Expected: collection fails because the adapter does not exist.

- [x] **Step 3: Implement the adapter**

Map commercial/disclosure-bearing kinds to `polarity="supports"`:

```python
{
    "explicit_ad_marker",
    "soft_ad_signal",
    "commercial_object",
    "brand_candidate",
    "comment_anomaly",
}
```

Treat `keyword:*` as supporting only for promotion, price, urgency, brand, and action dimensions. Keep sentiment, OCR, relation, and history observations neutral facts. Use the observation score, falling back to the parent result score only when the observation omits one. Never create a zero item for absence.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_evidence_adapters.py tests/contracts/test_evidence.py -q
```

Expected: all evidence tests pass.

---

### Task 5: Evidence adequacy, disclosure, and deterministic Judge baseline

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/adequacy.py`
- Create: `implicit-ad-agent/impad/orchestration/judgment.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_adequacy.py`
- Create: `implicit-ad-agent/tests/orchestration/test_judgment.py`

**Interfaces:**
- Produces: `EvidenceAdequacyResult`, `assess_evidence_adequacy`, `assess_commercial_intent`, `assess_disclosure`, and `build_verdict_report`.
- Consumes: `PostRecord` and `EvidenceBundle`.

- [x] **Step 1: Write and verify failing adequacy tests**

Tests must prove:

- missing/errored text-intent evidence blocks a forced verdict;
- optional image/history marked `not_applicable` does not block a text-only verdict;
- a provided-but-missing image and explicit evidence conflicts require review;
- skipped history never counts as negative evidence.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_adequacy.py -q
```

Expected: collection fails because the adequacy module does not exist.

- [x] **Step 2: Implement adequacy**

`EvidenceAdequacyResult` contains `intent_evaluable`, `review_required`, and literal reason codes. Text intent is critical for this baseline. Image is critical only when the input declared an image but capture/execution failed. Conflicts always require review. Missing optional comments/history remain explicit but non-blocking.

- [x] **Step 3: Write and verify failing judgment tests**

Use hand-built bundles to prove the exact label table:

| Commercial intent | Disclosure | Adequacy | Expected |
| --- | --- | --- | --- |
| absent | unknown | sufficient | 非广 |
| present | disclosed | sufficient | 明广 |
| present | not_disclosed | sufficient | 暗广 |
| present | unknown | any | 需复核 |
| uncertain | any | any | 需复核 |
| any | any | review required | 需复核 |

Also assert every verdict evidence ID exists in the bundle and no law evidence is fabricated.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_judgment.py -q
```

Expected: collection fails because the judgment module does not exist.

- [x] **Step 4: Implement the deterministic baseline**

Use `analyze_text_intent` as the primary score:

- explicit disclosure evidence or score `>=0.50` gives present intent;
- score `<0.35` with usable text coverage gives absent intent;
- otherwise intent is uncertain.

Disclosure is `disclosed` when explicit disclosure evidence exists, `not_disclosed` only when `post.capture_status.can_assess_disclosure` is true, and `unknown` otherwise. Document this as `deterministic_baseline_v1`; do not call it empirically calibrated.

- [x] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_adequacy.py tests/orchestration/test_judgment.py tests/contracts/test_verdict.py -q
```

Expected: all tests pass.

---

### Task 6: Reconnect the existing graph nodes through P2.5 modules

**Files:**
- Modify: `implicit-ad-agent/impad/state.py`
- Modify: `implicit-ad-agent/impad/agents/supervisor.py`
- Modify: `implicit-ad-agent/impad/agents/nlp_agent.py`
- Modify: `implicit-ad-agent/impad/agents/vision_agent.py`
- Modify: `implicit-ad-agent/impad/agents/behavior_agent.py`
- Modify: `implicit-ad-agent/impad/agents/judge.py`
- Modify: `implicit-ad-agent/impad/graph.py`
- Modify: `implicit-ad-agent/tests/test_agents.py`
- Create: `implicit-ad-agent/tests/test_graph_evidence_flow.py`

**Interfaces:**
- Supervisor normalizes input and creates the capability plan/run metadata.
- NLP group executes `analyze_text_intent`, `sentiment_curve`, and `comment_anomaly`.
- Vision group executes `ocr_extract`, `image_text_consistency`, and `detect_logo_product`.
- Behavior group executes `topic_drift`.
- Judge builds the EvidenceBundle, runs the adequacy/judgment modules, and emits `VerdictReport`.

- [x] **Step 1: Write failing agent and graph tests**

Tests must prove:

- a text post with five comments and three historical posts executes the four eligible non-vision tools through Function Calling;
- a text-only post does not execute image/history/comment tools that are ineligible;
- all results contain the same `run_id`, and traces contain proposed/completed events;
- the graph state contains `PostRecord`, `CaptureStatus`, `CapabilityPlan`, `ToolResult[]`, `EvidenceBundle`, `RunMetadata`, and `VerdictReport`;
- a soft-ad post with unknown disclosure returns `需复核`, not `暗广`;
- the explicit synthetic P1 fixture returns a structured `明广` report without a Key;
- legacy manual input remains accepted.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agents.py tests/test_graph_evidence_flow.py -q
```

Expected: failures because the graph still emits legacy votes and strings.

- [x] **Step 3: Implement minimal graph reconnection**

Keep the current graph topology for P2.5, but replace duplicated Agent scoring with calls to `execute_post_tools`. Accumulate structured ToolResults and trace events in state. The compatibility `evidence` and `report` fields may remain as derived presentation fields, but `VerdictReport` is authoritative. Do not add RAG, MCP client, A2A, API restructuring, or web code.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agents.py tests/test_graph_evidence_flow.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_smoke.py tests/test_tools_demo.py -q
```

Expected: all integration and compatibility tests pass.

---

### Task 7: P3-readiness regression gate and HANDOFF update

**Files:**
- Modify: `HANDOFF.md`
- Modify only if commands changed: `README.md`

**Interfaces:**
- Produces: current-state evidence that P1/P2.5 prerequisites are closed and a precise list of P3 work that remains.

- [x] **Step 1: Run focused gates**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts tests/adapters tests/orchestration tests/test_agents.py tests/test_graph_evidence_flow.py -q
```

- [x] **Step 2: Run complete zero-network regression**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Run data-asset validators**

From the repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
```

- [x] **Step 4: Audit P2.5 requirements**

For each Handoff 4.2 item, record one of:

- closed by current code and named tests;
- intentionally deferred to P3/P4/P5 by the phase plan;
- still incomplete, in which case do not claim P3 readiness.

- [x] **Step 5: Update HANDOFF**

Update:

- current implemented modules and exact test counts;
- the new structured runtime flow and conservative disclosure rule;
- P3 start boundary: graph/service refinement, MCPToolGateway, real legal corpus and Knowledge MCP, structured report presentation and observability hardening;
- P4 empirical calibration and CreatorShift real-feature/model evaluation;
- unchanged P5 A2A, platform URL adapters, and research workbench boundaries.

- [x] **Step 6: Final diff checks**

```powershell
git diff --check -- implicit-ad-agent HANDOFF.md
git status --short
```

Confirm no unrelated user changes were reverted, staged, committed, or deleted.
