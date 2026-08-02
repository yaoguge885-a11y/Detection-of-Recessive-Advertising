# Post-P1 Existing Function Test Library Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `docs/已有功能测试指令库.md` so every operational and teaching section matches the latest P1→P2 merged code, data assets, test commands, verified outputs, and unfinished boundaries.

**Architecture:** Keep the existing `0～14` chapter structure as the reader's navigation contract. Update the file in four reviewable slices—baseline, module/API tests, optional/troubleshooting, and theory—then run a repository-backed final audit. No production code, tests, Schema, or data assets are changed.

**Tech Stack:** Markdown, Windows PowerShell, Git, Python 3.10+, pytest, FastAPI/Uvicorn, Pydantic, MCP Python SDK, Chroma.

## Global Constraints

- Preserve the existing `0～14` chapter responsibilities; new P1-related subheadings are allowed.
- Default mandatory commands must be zero-Key, zero-network, and must not load real visual models.
- Mark dependency installation, real vision, real LLM, LangSmith, `/analyze`, and platform collection with explicit network/cost warnings.
- Current branch is `P2_Tool-Compartment-Model-Tooling`; latest merged P1 is `6679671`; merge commit is `98cb599`; HANDOFF commit is `ca6c351`.
- Current verified full suite is `171 passed, 2 skipped`; the focused P1-data/contracts/orchestration/MCP/RAG/CreatorShift suite is `109 passed`.
- Both `scripts/data/validate_submission_assets.py` and `data-tooling/validate_submission_assets.py` must report `VALIDATION PASSED`, 30 content records, and 30 annotation supplements.
- The latest P1 tree does not track the historical 598 candidate records or 6697 media files; never describe them as current assets.
- A2A, formal P1→PostRecord adaptation, main-graph Evidence/Function Calling integration, real legal corpus, research web workbench, URL adapters, and browser extension remain unfinished.
- Preserve unrelated dirty-worktree changes and commit only the plan or target documentation named by each task.

---

### Task 1: Update Environment, P1 Merge, and Mandatory Baseline Sections

**Files:**
- Modify: `docs/已有功能测试指令库.md:1-205`
- Reference: `HANDOFF.md`
- Reference: `scripts/data/validate_submission_assets.py`
- Reference: `data-tooling/validate_submission_assets.py`

**Interfaces:**
- Consumes: current Git commits, P1 validators, venv layout, and verified pytest counts.
- Produces: chapters `0～3` with the canonical manual acceptance sequence used by all later sections.

- [ ] **Step 1: Record the stale baseline before editing**

Run:

```powershell
rg -n "2026-07-24|142 passed|不能证明 P1 与当前 P2 已经完成集成" docs\已有功能测试指令库.md
```

Expected: matches in the header and chapter 3, proving the current document is stale.

- [ ] **Step 2: Update chapter 0 feature boundaries**

Set the snapshot date to `2026-07-26`, state that P1 `6679671` is contained through merge `98cb599`, and add:

- P1 v1.0 Schema and 30-record synthetic fixture as verified assets;
- `data-tooling/` and `tests/data` as implemented local data tooling/tests;
- `171 passed, 2 skipped` as the full baseline;
- `109 passed` as the focused integration baseline;
- explicit unfinished boundaries copied from Global Constraints.

Do not describe the historical candidate/media counts as present.

- [ ] **Step 3: Update chapter 1 activation commands**

Start from the repository root and use:

```powershell
Set-Location -LiteralPath 'D:\AAA Jobs\Detection-of-Recessive-Advertising'
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& '.\implicit-ad-agent\.venv\Scripts\Activate.ps1'
$env:PYTHONUTF8 = '1'
python -c "import sys; print(sys.version); print(sys.executable); assert sys.prefix != sys.base_prefix"
```

Explain that `Set-ExecutionPolicy` and `PYTHONUTF8` affect only the current PowerShell process.

- [ ] **Step 4: Keep dependency installation separate from mandatory offline tests**

Retain:

```powershell
Set-Location '.\implicit-ad-agent'
python -m pip install -r requirements.txt
python -m pip install -e ".[mcp,rag]"
python -m pip check
python -c "import pytest, mcp, chromadb; print('required test dependencies: OK')"
```

Mark both `pip install` commands as potentially networked. State that `pip check` is local but does not prove business behavior.

- [ ] **Step 5: Add P1 merge and asset gates to chapter 3**

From the repository root, document:

```powershell
$p1Commit = git rev-parse 'origin/P1-·-数据地基与标注规范'
git merge-base --is-ancestor $p1Commit HEAD
if ($LASTEXITCODE -ne 0) { throw '最新P1没有进入当前P2' }

python scripts\data\validate_submission_assets.py
if ($LASTEXITCODE -ne 0) { throw 'P1根目录资产校验失败' }

python data-tooling\validate_submission_assets.py
if ($LASTEXITCODE -ne 0) { throw 'data-tooling资产校验失败' }
```

Expected P1 commit: `6679671d35abf6d4bd9f17ec92f5585397244202`.

Expected validator facts: `VALIDATION PASSED`, 30 content records, 30 annotation supplements, label distribution 明广5/暗广12/非广8/out_of_scope3/uncertain2.

- [ ] **Step 6: Update compile and full pytest commands**

From `implicit-ad-agent/`, use:

```powershell
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
python -m compileall -q impad tests app.py scripts\data ..\data-tooling
python -m pytest -q
```

Expected: `171 passed, 2 skipped`. Explain that the two skips are explicit real-vision tests.

- [ ] **Step 7: Update the shortest acceptance block and proof boundaries**

The shortest block must include, in order:

1. activate venv;
2. disable tracing;
3. verify P1 ancestry;
4. run both P1 validators;
5. enter `implicit-ad-agent`;
6. run `pip check`, `compileall`, and full pytest.

Update “can prove” to include P1 assets plus P2 regression coexisting. Update “cannot prove” to include real candidate data, M1 completion, model accuracy, legal correctness, and the unfinished features in Global Constraints.

- [ ] **Step 8: Verify Task 1 content**

Run:

```powershell
rg -n "6679671|98cb599|171 passed, 2 skipped|VALIDATION PASSED|30 content|30条" docs\已有功能测试指令库.md
rg -n "2026-07-24|不能证明 P1 与当前 P2 已经完成集成" docs\已有功能测试指令库.md
git diff --check -- docs\已有功能测试指令库.md
```

Expected: current facts found; stale phrases absent; diff check exits 0.

- [ ] **Step 9: Commit Task 1**

```powershell
git add -- docs/已有功能测试指令库.md
git diff --cached --name-only
git commit -m "docs: update post-P1 mandatory test baseline"
```

Expected staged file list: only `docs/已有功能测试指令库.md`.

---

### Task 2: Update P1 Data, Module, Demo, and FastAPI Sections

**Files:**
- Modify: `docs/已有功能测试指令库.md` chapters `4～6`
- Reference: `implicit-ad-agent/tests/data/`
- Reference: `implicit-ad-agent/tests/contracts/`
- Reference: `implicit-ad-agent/tests/orchestration/`
- Reference: `implicit-ad-agent/tests/protocols/mcp/`
- Reference: `implicit-ad-agent/tests/rag/`
- Reference: `implicit-ad-agent/tests/creator_shift/`
- Reference: `implicit-ad-agent/app.py`

**Interfaces:**
- Consumes: Task 1 baseline and current test directory names.
- Produces: module-by-module manual commands, expected counts, source-learning pointers, demos, and API health acceptance.

- [ ] **Step 1: Add a P1 data-tooling subsection at the start of chapter 4**

Document:

```powershell
python -m pytest tests\data -q
```

Expected: `29 passed`.

Explain coverage:

- the relocated `data-tooling` validator finds repository assets;
- image-placement disposition remains traceable;
- candidate migration fixtures test Schema, ID, provenance, privacy, and media-reference behavior without loading real candidate data.

Code/test pointers:

- `tests/data/test_data_tooling_validator.py`
- `tests/data/test_image_placement_disposition.py`
- `tests/data/test_migrate_p1_candidates.py`
- `data-tooling/annotation/migrate_p1_candidates_to_v1.py`
- `data-tooling/annotation/apply_image_placement_disposition.py`

- [ ] **Step 2: Preserve existing module subsections and update their snapshot context**

Keep commands and verified counts:

- Agent/keywords/vision degradation: `21 passed`;
- seven tools: `40 passed`;
- tools demo: `1 passed`;
- contracts: `17 passed`;
- orchestration: `30 passed`;
- MCP: `6 passed`;
- RAG: `12 passed`;
- CreatorShift: `15 passed`.

State that these counts were revalidated in the `171/2` merged workspace and are snapshots, not permanent contracts.

- [ ] **Step 3: Replace the old independent-module aggregate**

Use:

```powershell
python -m pytest tests\data tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q
```

Expected: `109 passed`.

Explain that this includes P1 data tests and still does not prove main-graph integration.

- [ ] **Step 4: Update collection and demo guidance**

Keep:

```powershell
python -m pytest --collect-only -q
python run_demo.py
python run_tools_demo.py
```

Explain:

- collect-only must show no import errors;
- `run_demo.py` without flags is zero-Key;
- `run_tools_demo.py` uses a synthetic visual fixture;
- neither demo proves real-data model quality.

- [ ] **Step 5: Expand FastAPI endpoint teaching**

Document service start:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Explain:

- `/` is the current simple landing page;
- `/docs` is Swagger UI and can execute endpoints;
- `/redoc` is read-oriented API documentation;
- `/health` is the mandatory local endpoint;
- stop Uvicorn in the server terminal with `Ctrl+C`;
- `/analyze` remains in the optional LLM/cost section.

- [ ] **Step 6: Verify Task 2 commands and paths**

Run:

```powershell
Test-Path implicit-ad-agent\tests\data\test_data_tooling_validator.py
Test-Path implicit-ad-agent\tests\data\test_image_placement_disposition.py
Test-Path implicit-ad-agent\tests\data\test_migrate_p1_candidates.py
rg -n "29 passed|109 passed|Ctrl\\+C|Swagger|ReDoc|/health" docs\已有功能测试指令库.md
git diff --check -- docs\已有功能测试指令库.md
```

Expected: all paths `True`, all terms found, diff check exits 0.

- [ ] **Step 7: Run focused tests**

From `implicit-ad-agent/`:

```powershell
python -m pytest tests\data -q
python -m pytest tests\data tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q
```

Expected: `29 passed`, then `109 passed`.

- [ ] **Step 8: Commit Task 2**

```powershell
git add -- docs/已有功能测试指令库.md
git diff --cached --name-only
git commit -m "docs: add P1 data and API acceptance guidance"
```

Expected staged file list: only `docs/已有功能测试指令库.md`.

---

### Task 3: Update Optional Risks, Troubleshooting, and Acceptance Records

**Files:**
- Modify: `docs/已有功能测试指令库.md` chapters `7～9`
- Reference: `implicit-ad-agent/tests/test_vision_integration.py`
- Reference: `implicit-ad-agent/run_demo.py`
- Reference: `implicit-ad-agent/app.py`
- Reference: `data-tooling/README.md`

**Interfaces:**
- Consumes: mandatory/offline boundary from Tasks 1–2.
- Produces: unambiguous warnings, failure diagnosis, and a current acceptance-record template.

- [ ] **Step 1: Add a visible red optional-test warning**

At the beginning of chapter 7 include:

```html
<span style="color:#d32f2f"><strong>🔴 可选：以下命令可能联网、下载模型、上传轨迹或产生费用，不属于必跑验收。</strong></span>
```

Keep real vision, real LLM, `run_demo.py --image`, `/analyze`, and LangSmith separate so their risks are not conflated.

- [ ] **Step 2: Add P1 platform-collection safety boundaries**

Add a subsection explaining:

- `data-tooling/crawler/` exists but platform collection is not a default test;
- public-page access must follow platform terms, rate limits, minimization, and privacy rules;
- do not save Cookies, bypass login/access control, or commit raw identities/media;
- collection output must pass migration, privacy scan, Schema validation, double annotation, and split checks before becoming research evidence;
- current repository has no tracked real candidate pool to accept.

- [ ] **Step 3: Update troubleshooting for the merged layout**

Add symptom/action entries:

- P1 validator cannot find `data/schema/...`: run it from the repository root and verify the post-merge path fix;
- Chinese labels look garbled: set `$env:PYTHONUTF8='1'` in the current terminal and trust exit code plus stable English markers;
- `git status` is not clean: expected because 66 pre-existing P2 paths remain after committing HANDOFF; do not reset;
- duplicated scripts: `data-tooling/` and `implicit-ad-agent/scripts/data/` are both present, so verify which path a command uses;
- historical 598/6697 references: planning history only, not current assets.

- [ ] **Step 4: Replace the acceptance-record template**

The template must record:

```text
branch: P2_Tool-Compartment-Model-Tooling
latest_p1: 6679671
merge_commit: 98cb599
handoff_commit: ca6c351
p1_root_validator: PASS/FAIL
p1_data_tooling_validator: PASS/FAIL
full_pytest: 171 passed, 2 skipped
focused_pytest: 109 passed
pip_check: PASS/FAIL
compileall: PASS/FAIL
health: PASS/FAIL
optional_tests_run: none / exact commands
```

Require recording exact failures and forbid writing “全部正常” without command evidence.

- [ ] **Step 5: Verify Task 3 safety language**

Run:

```powershell
rg -n "🔴 可选|平台条款|Cookie|66|data-tooling/|598|6697|focused_pytest" docs\已有功能测试指令库.md
git diff --check -- docs\已有功能测试指令库.md
```

Expected: all current safety/fact terms found; diff check exits 0.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- docs/已有功能测试指令库.md
git diff --cached --name-only
git commit -m "docs: clarify optional tests and post-merge troubleshooting"
```

Expected staged file list: only `docs/已有功能测试指令库.md`.

---

### Task 4: Extend Learning and Theory Chapters for P1 Data Governance

**Files:**
- Modify: `docs/已有功能测试指令库.md` chapters `10～14`
- Reference: `data/schema/data_schema_v1.json`
- Reference: `data-tooling/schema/data_schema_v1_1.json`
- Reference: `docs/data_schema.md`
- Reference: `data-tooling/annotation/migrate_p1_candidates_to_v1.py`
- Reference: `data-tooling/annotation/privacy_scan.py`
- Reference: `data-tooling/annotation/calculate_agreement.py`
- Reference: `data-tooling/annotation/split_by_blogger.py`

**Interfaces:**
- Consumes: current implementation boundaries and P1 data assets.
- Produces: a learning path that distinguishes engineering tests, data quality, research evidence, and unfinished product claims.

- [ ] **Step 1: Update learning priorities in chapter 10**

Add to “必须重点掌握”:

- P1 v1.0 Schema and missing-value semantics;
- content records, annotation records, and annotation supplements;
- `uncertain/out_of_scope` versus formal 明广/暗广/非广 labels;
- provenance, privacy, media references, and temporal/creator split constraints.

Add to “建议部分深入”:

- candidate migration and rejection reports;
- privacy scanning and compliance ledgers;
- Cohen's κ, adjudication, and label-guideline iteration;
- v1.0/v1.1 compatibility governance.

- [ ] **Step 2: Add P1 Schema and version-governance theory**

Teach:

```text
data/schema/data_schema_v1.json
  -> current canonical submission validator input

data-tooling/schema/data_schema_v1_1.json
  -> compatibility candidate, not automatically canonical
```

Explain that a version changes only after field compatibility, changelog, migration, and tests are reviewed. Do not call the two versions interchangeable.

- [ ] **Step 3: Add data-governance state theory**

Define:

- `明广/暗广/非广`: formal research labels;
- `uncertain`: insufficient evidence/annotation certainty requiring review;
- `out_of_scope`: excluded from the research population;
- `review_required`: runtime decision status, not a fourth training label.

Connect this to the existing “missing is not negative evidence” principle.

- [ ] **Step 4: Add evidence-grade and lineage theory**

Teach the hierarchy:

```text
30-record synthetic fixture
  -> validates structure and tooling
candidate pool
  -> supports annotation and coverage work
double-annotated/adjudicated gold set
  -> supports supervised evaluation
creator-disjoint + forward-time test set
  -> supports CreatorShift research claims
```

Explain why passing fixture tests cannot prove model accuracy or M1 completion.

- [ ] **Step 5: Add migration, privacy, and annotation-reliability teaching**

Cover:

- migration must preserve source-to-new ID mapping and never overwrite raw candidates;
- provenance records source, collection time, collector, and terms review;
- privacy scanning precedes public Git inclusion;
- media references and hashes must remain traceable;
- Cohen's κ measures agreement beyond chance and does not replace adjudication;
- guideline changes use dev/annotation evidence, never hidden test labels.

- [ ] **Step 6: Add P1 hands-on exercises to chapter 13**

Add commands:

```powershell
python -m pytest tests\data\test_data_tooling_validator.py -vv
python -m pytest tests\data\test_migrate_p1_candidates.py -vv
python -m pytest tests\data\test_image_placement_disposition.py -vv
```

For each exercise require answers to:

1. which invariant is protected;
2. what input would be rejected;
3. what the test cannot prove without real compliant data;
4. which report or artifact would be needed for M1 acceptance.

- [ ] **Step 7: Update the final core model in chapter 14**

Use:

```text
P1 Schema / RawRequest
  -> PostRecord + CaptureStatus（未接入）
  -> Capability Plan
  -> bounded Function Calling
  -> ToolResult[]
  -> EvidenceBundle
  -> adequacy + intent + disclosure
  -> VerdictReport
  -> post-judge legal RAG
  -> traceable response
```

Label formal P1 adaptation and main-graph integration as unfinished. State that data lineage and experimental split are as important as Agent protocol choices.

- [ ] **Step 8: Verify Task 4 theory coverage**

Run:

```powershell
rg -n "data_schema_v1_1|uncertain|out_of_scope|Cohen|provenance|privacy|creator-disjoint|forward-time|test_data_tooling_validator" docs\已有功能测试指令库.md
git diff --check -- docs\已有功能测试指令库.md
```

Expected: all theory topics found; diff check exits 0.

- [ ] **Step 9: Commit Task 4**

```powershell
git add -- docs/已有功能测试指令库.md
git diff --cached --name-only
git commit -m "docs: teach P1 data governance and research evidence"
```

Expected staged file list: only `docs/已有功能测试指令库.md`.

---

### Task 5: Run Final Documentation and Runtime Acceptance

**Files:**
- Verify: `docs/已有功能测试指令库.md`
- Verify: current repository and `implicit-ad-agent/`

**Interfaces:**
- Consumes: completed chapters from Tasks 1–4.
- Produces: evidence that the manual is internally consistent and executable against the current workspace.

- [ ] **Step 1: Scan for stale or contradictory claims**

Run:

```powershell
rg -n "2026-07-24|142 passed|80 passed|P1 与当前 P2 已经完成集成|仓库现有598|仓库现有 598|6697个媒体文件" docs\已有功能测试指令库.md
```

Expected: no stale-current claims. Historical mentions are allowed only when immediately labeled as removed/historical.

- [ ] **Step 2: Verify every explicitly named path**

Run:

```powershell
@(
  'data/schema/data_schema_v1.json',
  'data-tooling/schema/data_schema_v1_1.json',
  'scripts/data/validate_submission_assets.py',
  'data-tooling/validate_submission_assets.py',
  'implicit-ad-agent/tests/data',
  'implicit-ad-agent/tests/contracts',
  'implicit-ad-agent/tests/orchestration',
  'implicit-ad-agent/tests/protocols/mcp',
  'implicit-ad-agent/tests/rag',
  'implicit-ad-agent/tests/creator_shift'
) | ForEach-Object {
  if (-not (Test-Path -LiteralPath $_)) { throw "Missing documented path: $_" }
}
```

Expected: no exception.

- [ ] **Step 3: Run both P1 validators**

From the repository root:

```powershell
& .\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
if ($LASTEXITCODE -ne 0) { throw 'Root P1 validator failed' }

& .\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
if ($LASTEXITCODE -ne 0) { throw 'Data-tooling P1 validator failed' }
```

Expected: both `VALIDATION PASSED`.

- [ ] **Step 4: Run full and focused pytest**

From `implicit-ad-agent/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests\data tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q
```

Expected: `171 passed, 2 skipped`; then `109 passed`.

- [ ] **Step 5: Run compile, health, and dependency checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad tests app.py scripts\data ..\data-tooling
.\.venv\Scripts\python.exe -c "import app; assert app.health() == {'status': 'ok'}"
.\.venv\Scripts\python.exe -m pip check
```

Expected: compile and health exit 0; pip outputs `No broken requirements found.`

- [ ] **Step 6: Verify Markdown structure and diff**

From the repository root:

```powershell
git diff --check -- docs\已有功能测试指令库.md
Select-String -LiteralPath docs\已有功能测试指令库.md -Pattern '^## ([0-9]+)\.' -Encoding UTF8
git status --short -- docs\已有功能测试指令库.md
```

Expected: chapters `0～14` all present once, no diff errors, and only the target document is modified for this implementation.

- [ ] **Step 7: Commit final audit corrections if needed**

If Task 5 required a documentation correction:

```powershell
git add -- docs/已有功能测试指令库.md
git diff --cached --name-only
git commit -m "docs: verify post-P1 test instruction library"
```

If no correction was needed, do not create an empty commit.

- [ ] **Step 8: Report acceptance evidence**

Report:

- target document path;
- commits created by Tasks 1–5;
- P1 validator outputs;
- full/focused pytest totals;
- compile/health/pip results;
- optional tests not run;
- remaining unfinished feature boundaries.
