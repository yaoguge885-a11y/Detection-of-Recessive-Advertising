# CreatorShift Leakage-Safe Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a P1-independent, leakage-safe CreatorShift history view with mean, max, and EMA baselines.

**Architecture:** Accept already-extracted numeric features rather than PostRecord. Validate creator and time boundaries before pooling. Return explicit history sufficiency and an interpretable shift result instead of classifying advertisements.

**Tech Stack:** Python 3.10+, Pydantic 2, standard library, pytest.

## Global Constraints

- Every history item must have the target creator and `published_at < target_time`.
- History insufficiency is not a zero score.
- No P1 Schema, model training, Chroma memory, or label prediction.
- Outputs are evidence features only.

---

### Task 1: Leakage-safe history contracts

**Files:**
- Create: `implicit-ad-agent/impad/creator_shift/__init__.py`
- Create: `implicit-ad-agent/impad/creator_shift/contracts.py`
- Create: `implicit-ad-agent/tests/creator_shift/__init__.py`
- Create: `implicit-ad-agent/tests/creator_shift/test_history_view.py`

**Interfaces:**
- Produces: `HistoryFeature`, `CreatorHistoryView`, `HistorySufficiency`.

- [x] **Step 1: Write failing tests**

Verify:

- valid history is sorted ascending by time;
- a different creator is rejected;
- future and equal timestamps are rejected;
- duplicate post IDs are rejected;
- empty history is `unavailable`;
- fewer than the configured minimum is `insufficient`;
- enough history is `sufficient`.

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/creator_shift/test_history_view.py -q
```

- [x] **Step 3: Implement contracts**

Use timezone-aware datetimes. `CreatorHistoryView` validates all invariants in an after-validator and exposes a `sufficiency` property with observed and required counts.

- [x] **Step 4: Verify GREEN**

Run history-view tests.

---

### Task 2: Mean, max, and EMA baselines

**Files:**
- Create: `implicit-ad-agent/impad/creator_shift/baselines.py`
- Create: `implicit-ad-agent/tests/creator_shift/test_baselines.py`

**Interfaces:**
- Produces: `pool_history(view, method, alpha)` and `PooledHistory`.

- [x] **Step 1: Write failing exact-value tests**

For a three-item fixture, assert exact vectors for:

- arithmetic mean;
- per-feature max;
- chronological EMA with fixed alpha;
- deterministic feature ordering.

Also assert pooling unavailable history raises a domain error and feature-key mismatches are rejected.

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/creator_shift/test_baselines.py -q
```

- [x] **Step 3: Implement minimal pooling**

Implement three methods over complete, matching feature maps. Preserve window start/end and post IDs in PooledHistory.

- [x] **Step 4: Verify GREEN**

Run baseline tests.

---

### Task 3: Interpretable shift calculation

**Files:**
- Create: `implicit-ad-agent/impad/creator_shift/shift.py`
- Create: `implicit-ad-agent/tests/creator_shift/test_shift.py`

**Interfaces:**
- Produces: `CreatorShiftResult`, `calculate_shift(target_features, pooled)`.

- [x] **Step 1: Write failing tests**

Verify:

- overall shift is mean absolute feature difference;
- per-feature deltas are preserved;
- top features are sorted by absolute contribution then name;
- mismatched feature keys are rejected;
- result contains method, window, history count and limitations.

- [x] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/creator_shift/test_shift.py -q
```

- [x] **Step 3: Implement shift result**

Do not map shift to 明广/暗广/非广. Return numeric evidence and history metadata only.

- [x] **Step 4: Verify GREEN**

Run all CreatorShift tests.

---

### Task 4: CreatorShift module gate

- [x] **Step 1: Run module tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/creator_shift -q
```

- [x] **Step 2: Run full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Compile**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad/creator_shift tests/creator_shift
```

