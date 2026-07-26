# Evidence Verdict and Run Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the evidence, verdict, and run contracts that are independent of P1 post-field mapping, while preserving skipped/error states as unknown rather than negative evidence.

**Architecture:** Keep raw execution outcomes as `ToolResult` and normalize only real supporting observations into `EvidenceItem`. `EvidenceBundle` stores both evidence items and original tool outcomes so the later adequacy gate can distinguish evidence from missing/error states. `VerdictReport` enforces the accepted commercial-intent/disclosure label semantics. `RunMetadata` records versions, trace IDs, errors, and degradation without embedding report prose.

**Tech Stack:** Python 3.10+, Pydantic 2, pytest.

## Global Constraints

- Do not import P1 Schema, `PostRecord`, or `CaptureStatus`.
- A skipped/error `ToolResult` is retained as an outcome and must not create an `EvidenceItem(score=0)`.
- Evidence identifiers must be unique inside a bundle.
- `明广` requires present commercial intent plus disclosed status.
- `暗广` requires present commercial intent plus not-disclosed status.
- Unknown disclosure cannot produce `暗广`; it must remain `需复核`.
- `VerdictReport` contains structured fields only, not a preformatted long report.

---

### Task 1: Evidence contracts

**Files:**
- Create: `implicit-ad-agent/impad/contracts/__init__.py`
- Create: `implicit-ad-agent/impad/contracts/evidence.py`
- Create: `implicit-ad-agent/tests/contracts/__init__.py`
- Create: `implicit-ad-agent/tests/contracts/test_evidence.py`

- [x] **Step 1: Write failing evidence tests**

```python
import json

import pytest
from pydantic import ValidationError

from impad.contracts.evidence import EvidenceBundle, EvidenceItem
from impad.tools.contracts import ToolResult


def _item(evidence_id="ev_1"):
    return EvidenceItem(
        evidence_id=evidence_id,
        kind="soft_ad_signal",
        source="post.text",
        tool_name="analyze_text_intent",
        tool_version="1.0",
        call_id="call_1",
        quote="限时抢购",
        score=0.8,
        span=(0, 4),
    )


def test_bundle_keeps_skipped_outcome_separate_from_real_evidence():
    bundle = EvidenceBundle(
        post_id="post_1",
        items=[_item()],
        tool_results=[
            ToolResult(
                tool_name="analyze_text_intent",
                status="degraded",
            ),
            ToolResult(
                tool_name="topic_drift",
                status="skipped",
                warnings=["History unavailable."],
            ),
        ],
    )
    assert len(bundle.items) == 1
    assert bundle.tool_results[1].status == "skipped"
    assert all(item.tool_name != "topic_drift" for item in bundle.items)
    json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)


def test_bundle_rejects_duplicate_evidence_ids():
    with pytest.raises(ValidationError):
        EvidenceBundle(
            post_id="post_1",
            items=[_item(), _item()],
        )
```

- [x] **Step 2: Run evidence tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_evidence.py -q
```

Expected: collection fails because `impad.contracts.evidence` does not exist.

- [x] **Step 3: Implement EvidenceItem and EvidenceBundle**

```python
class EvidenceItem(BaseModel):
    evidence_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    source: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    call_id: str | None = None
    quote: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    span: tuple[int, int] | None = None
    bbox: list[int] | None = None
    related_post_id: str | None = None
    comment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    post_id: str = Field(min_length=1)
    items: list[EvidenceItem] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    limitations: list[ToolLimitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_ids_are_unique(self):
        ids = [item.evidence_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique")
        return self
```

- [x] **Step 4: Run evidence tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_evidence.py -q
```

---

### Task 2: Verdict contracts and invariants

**Files:**
- Create: `implicit-ad-agent/impad/contracts/verdict.py`
- Create: `implicit-ad-agent/tests/contracts/test_verdict.py`

- [x] **Step 1: Write failing verdict tests**

```python
import json

import pytest
from pydantic import ValidationError

from impad.contracts.verdict import (
    CommercialIntent,
    DisclosureEvidence,
    VerdictReport,
)


def _intent(status="present"):
    return CommercialIntent(
        status=status,
        score=0.9 if status == "present" else None,
        evidence_ids=["ev_1"] if status == "present" else [],
    )


def test_dark_ad_requires_present_intent_and_no_disclosure():
    report = VerdictReport(
        post_id="post_1",
        label="暗广",
        confidence=0.85,
        review_required=False,
        commercial_intent=_intent(),
        disclosure=DisclosureEvidence(
            status="not_disclosed",
            confidence=0.8,
            evidence_ids=["ev_2"],
        ),
        evidence_ids=["ev_1", "ev_2"],
        reasons=["商业意图强且完整披露区域未发现披露"],
    )
    assert report.label == "暗广"
    json.dumps(report.model_dump(mode="json"), ensure_ascii=False)


def test_unknown_disclosure_cannot_be_dark_ad():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="暗广",
            confidence=0.5,
            review_required=False,
            commercial_intent=_intent(),
            disclosure=DisclosureEvidence(status="unknown"),
        )


def test_review_label_and_flag_must_agree():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="需复核",
            confidence=0.4,
            review_required=False,
            commercial_intent=CommercialIntent(status="uncertain"),
            disclosure=DisclosureEvidence(status="unknown"),
        )
```

- [x] **Step 2: Run verdict tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_verdict.py -q
```

- [x] **Step 3: Implement structured verdict types**

Create:

```python
class CommercialIntent(BaseModel):
    status: Literal["present", "absent", "uncertain"]
    score: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class DisclosureEvidence(BaseModel):
    status: Literal["disclosed", "not_disclosed", "unknown"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LawEvidence(BaseModel):
    reference_id: str
    title: str
    source_url: str
    jurisdiction: str | None = None
    effective_date: date | None = None
    quote: str | None = None
    retrieval_score: float | None = Field(default=None, ge=0, le=1)


class VerdictReport(BaseModel):
    post_id: str
    label: Literal["明广", "暗广", "非广", "需复核"]
    confidence: float = Field(ge=0, le=1)
    review_required: bool
    commercial_intent: CommercialIntent
    disclosure: DisclosureEvidence
    creator_shift_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    law_evidence: list[LawEvidence] = Field(default_factory=list)
```

Add an after-model validator enforcing review-label agreement and the three non-review label semantics listed in Global Constraints.

- [x] **Step 4: Run verdict tests and verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_verdict.py -q
```

---

### Task 3: Run metadata

**Files:**
- Create: `implicit-ad-agent/impad/contracts/run.py`
- Create: `implicit-ad-agent/tests/contracts/test_run.py`
- Modify: `implicit-ad-agent/impad/contracts/__init__.py`

- [x] **Step 1: Write failing run tests**

```python
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.run import RunIssue, RunMetadata


def test_run_metadata_serializes_versions_and_degradation():
    metadata = RunMetadata(
        run_id="run_1",
        status="degraded",
        started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        duration_ms=15,
        tool_versions={"analyze_text_intent": "1.0"},
        model_versions={"intent": "rule_v1"},
        issues=[RunIssue(
            kind="degradation",
            code="history_unavailable",
            message="Creator history was not available.",
            stage="capability_plan",
            retryable=False,
        )],
        trace_ids=["trace_1"],
    )
    assert metadata.issues[0].kind == "degradation"
    json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False)


def test_run_metadata_rejects_negative_duration():
    with pytest.raises(ValidationError):
        RunMetadata(
            run_id="run_1",
            status="failed",
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            duration_ms=-1,
        )
```

- [x] **Step 2: Run run-metadata tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_run.py -q
```

- [x] **Step 3: Implement RunIssue and RunMetadata**

```python
class RunIssue(BaseModel):
    kind: Literal["error", "degradation"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    retryable: bool | None = None


class RunMetadata(BaseModel):
    run_id: str = Field(min_length=1)
    status: Literal["pending", "running", "completed", "degraded", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)
    issues: list[RunIssue] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
```

- [x] **Step 4: Run all contract tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts -q
```

---

### Task 4: Regression gate

- [x] **Step 1: Run the full default suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 2: Run compile and diff checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad
git diff --check
```
