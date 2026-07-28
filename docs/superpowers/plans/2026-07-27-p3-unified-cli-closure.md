# P3 Unified CLI Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `run_demo.py` use the merged P3 `AnalysisService`, then synchronize the project handoff and test documentation with the verified P3 engineering baseline.

**Architecture:** Keep `AnalysisService` as the only analysis entry point used by both FastAPI and the demo CLI. The CLI remains a thin sample loader and presenter; it does not read LangGraph state or rebuild verdict/report logic. Documentation distinguishes the completed P3 engineering MVP from the still-failing M1 research-data gate.

**Tech Stack:** Python 3.10, Pydantic v2, LangGraph, FastAPI, pytest, PowerShell, Markdown.

## Global Constraints

- Default CLI and tests must remain zero-Key and zero-network.
- `--image` remains an explicit real-vision opt-in; default tests must not load YOLO or EasyOCR.
- `--llm` remains accepted only as a deprecated compatibility flag and must not read a Key or call an LLM.
- Missing, skipped, error, or insufficient evidence must not become negative evidence.
- Do not modify the seven P2 tools, the LangGraph evidence graph, M1 thresholds, CreatorShift, A2A, URL adapters, Web UI, or LightRAG.
- The small official legal corpus is an engineering baseline, not proof of complete legal coverage or legal advice.
- Passing code tests does not mark M1 or formal research evaluation complete.
- `HANDOFF.md` and `docs/已有功能测试指令库.md` are required synchronization targets.
- Preserve unrelated user changes; stage and commit only files named by each task.

---

### Task 1: Route the demo CLI through `AnalysisService`

**Files:**
- Create: `implicit-ad-agent/tests/test_demo.py`
- Modify: `implicit-ad-agent/run_demo.py`

**Interfaces:**
- Consumes: `AnalysisService.analyze(post: dict | PostRecord, *, runtime_mode: Literal["local", "mcp"]) -> AnalysisResult`
- Produces: `run_demo(samples_path=DEFAULT_SAMPLES, *, image_path=None, service=None) -> list[AnalysisResult]`
- Produces: `main(argv=None, *, samples_path=DEFAULT_SAMPLES, service=None) -> int`

- [ ] **Step 1: Write the three failing CLI tests**

Create `implicit-ad-agent/tests/test_demo.py`:

```python
import json
from types import SimpleNamespace

from run_demo import main, run_demo


class FakeAnalysisService:
    def __init__(self):
        self.calls = []

    def analyze(self, post, *, runtime_mode):
        self.calls.append((post, runtime_mode))
        index = len(self.calls)
        return SimpleNamespace(
            readable_report=f"report-{index}",
            run_metadata=SimpleNamespace(run_id=f"run_{index}"),
        )


def _samples(tmp_path):
    path = tmp_path / "samples.json"
    path.write_text(
        json.dumps(
            [
                {"text": "样本一", "blogger": "A"},
                {"text": "样本二", "blogger": "B"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_run_demo_uses_unified_local_service_for_default_samples(tmp_path):
    service = FakeAnalysisService()

    results = run_demo(_samples(tmp_path), service=service)

    assert [item.readable_report for item in results] == [
        "report-1",
        "report-2",
    ]
    assert service.calls == [
        ({"text": "样本一", "blogger": "A"}, "local"),
        ({"text": "样本二", "blogger": "B"}, "local"),
    ]


def test_run_demo_image_path_still_uses_unified_local_service(tmp_path):
    service = FakeAnalysisService()

    results = run_demo(
        _samples(tmp_path),
        image_path="sample.jpg",
        service=service,
    )

    assert len(results) == 1
    assert service.calls == [(
        {
            "text": "分享一下最近入手的好物～",
            "blogger": "demo",
            "image_path": "sample.jpg",
        },
        "local",
    )]


def test_main_accepts_deprecated_llm_flag_and_prints_report_and_run_id(
    tmp_path,
    capsys,
):
    service = FakeAnalysisService()

    exit_code = main(
        ["--llm"],
        samples_path=_samples(tmp_path),
        service=service,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--llm 已弃用" in output
    assert "report-1" in output
    assert "run_id：run_1" in output
    assert all(mode == "local" for _, mode in service.calls)
```

- [ ] **Step 2: Run the new test file and verify RED**

Run:

```powershell
Set-Location -LiteralPath 'D:\AAA Jobs\Detection-of-Recessive-Advertising\implicit-ad-agent'
.\.venv\Scripts\python.exe -m pytest tests\test_demo.py -q
```

Expected: collection fails because the current module does not export `run_demo`, proving that the old CLI cannot be exercised through the unified service interface.

- [ ] **Step 3: Replace the legacy graph selection with the minimal unified CLI**

Replace `implicit-ad-agent/run_demo.py` with:

```python
"""Run de-identified samples through the unified P3 analysis service.

Usage:
    python run_demo.py
    python run_demo.py --llm
    python run_demo.py --image path/to.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from impad.services import (
    AnalysisResult,
    AnalysisService,
    get_default_analysis_service,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SAMPLES = PROJECT_ROOT / "samples" / "sample_posts.json"


def run_demo(
    samples_path: str | Path = DEFAULT_SAMPLES,
    *,
    image_path: str | None = None,
    service: AnalysisService | None = None,
) -> list[AnalysisResult]:
    """Analyze fixed samples locally through the shared service boundary."""

    if image_path:
        posts = [{
            "text": "分享一下最近入手的好物～",
            "blogger": "demo",
            "image_path": image_path,
        }]
    else:
        posts = json.loads(
            Path(samples_path).read_text(encoding="utf-8")
        )
    active_service = service or get_default_analysis_service()
    return [
        active_service.analyze(post, runtime_mode="local")
        for post in posts
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    samples_path: str | Path = DEFAULT_SAMPLES,
    service: AnalysisService | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="deprecated compatibility flag; analysis remains deterministic",
    )
    parser.add_argument(
        "--image",
        help="optional local image path for the real vision pipeline",
    )
    args = parser.parse_args(argv)

    if args.llm:
        print(">> --llm 已弃用；继续使用零 Key 的确定性 AnalysisService。\n")

    results = run_demo(
        samples_path,
        image_path=args.image,
        service=service,
    )
    for index, result in enumerate(results, start=1):
        print(f"===== 分析结果 {index} =====")
        print(result.readable_report)
        print(f"run_id：{result.run_metadata.run_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the CLI tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_demo.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Verify the legacy graphs are no longer CLI dependencies**

Run:

```powershell
rg -n "hello_graph|from impad\.graph|graph\.invoke" run_demo.py
```

Expected: no matches and exit code `1`.

- [ ] **Step 6: Run the real default CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe run_demo.py
```

Expected:

- three reports;
- each report contains a `run_id`;
- each run is persisted under `.impad_runtime\runs`;
- no API Key, LLM call, network request, YOLO, or EasyOCR is required.

- [ ] **Step 7: Commit the CLI implementation**

```powershell
git add -- implicit-ad-agent/run_demo.py implicit-ad-agent/tests/test_demo.py
git commit -m "feat: route demo through unified analysis service"
```

---

### Task 2: Synchronize README and HANDOFF facts

**Files:**
- Modify: `README.md`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: verified behavior from Task 1 and P3 merge commit `c3ed82d`
- Produces: current public entry summary and current developer handoff

- [ ] **Step 1: Update the README current snapshot**

Apply these factual changes:

```markdown
## 当前事实快照（2026-07-27）

| LangGraph/P3主链 | `PostRecord → Capability Plan → 七工具组 → EvidenceBundle → 充分性门 → Judge → 法规检索 → 报告/run持久化`可运行 | P4再接真实CreatorShift特征与校准 |
| P2工具舱 | 7/7工具ready；Local/MCP共用ToolResult契约，MCP失败可回落本地 | 保持真实视觉和远程部署显式opt-in |
| RAG/MCP/A2A | Detection MCP、MCPToolGateway回落、Knowledge MCP和小规模官方法规语料基线已实现；A2A未实现 | 扩语料与LightRAG仅做受控后续实验，P5建设A2A |
| Web/API/CLI | 统一AnalysisService、版本化单条分析/run查询API和CLI演示已接入 | P5再接批量、URL与研究工作台 |
```

Set the verified default baseline to:

```markdown
本地零Key全量回归当前为 `276 passed, 2 skipped`，其中P3统一服务、API、MCP回落、Knowledge MCP、官方法规基线、评估指标和CLI闭环均有聚焦测试。真实视觉、远程MCP、LLM和联网采集仍是显式可选路径。
```

Delete the table row for the removed `docs/现有代码修改大纲.md`. Replace the final route sentence with:

```markdown
更完整的设计与执行顺序见 `docs/` 下的说明书、阶段计划、superpowers设计与实施记录。
```

- [ ] **Step 2: Update HANDOFF completed, remaining, and execution sections**

Add or update rows in section 4.1:

```markdown
| 统一分析服务 | `AnalysisService`统一主图、Judge后法规检索、报告和run持久化；API与CLI共用 |
| MCP运行模式 | `MCPToolGateway`保持ToolResult契约，stdio失败时本地回落并记录hybrid/fallback_count |
| 知识与报告 | Knowledge MCP、小规模官方法规语料、引用守卫、Judge后LawEvidence和Markdown报告已接入 |
| API与run查询 | `/api/v1/analyze`、`/api/v1/runs/{run_id}`、`/api/v1/capabilities`及兼容`/analyze`共用服务 |
| 评估基础 | 三分类Macro-F1、暗广P/R/F1、AUPRC、ECE/Brier、coverage/review_rate已有离线实现 |
| 默认回归 | 当前零Key/零网络全量`276 passed, 2 skipped`；P3聚焦`16 passed` |
```

Close the two P3 rows in section 4.2:

```markdown
| MCPToolGateway/主图MCP回落 | 已关闭：主图支持local/mcp，失败回落本地并记录hybrid与fallback_count |
| 官方法规基线/知识MCP/报告接入 | 工程MVP已关闭：小规模官方条款、Knowledge MCP、Judge后检索、引用报告和run查询可运行；不代表完整法律覆盖 |
```

Replace the P3 item in section 4.3 with:

```markdown
- **P3工程MVP已完成，但正式阶段门仍受M1事实证据约束**：统一服务、API/CLI、MCP回落、Knowledge MCP、官方法规工程基线、报告、run查询、追踪和分类指标已通过离线测试；远程MCP可达性、法规覆盖质量和真实数据效果尚未证明。
```

Update section 8 so the next engineering sequence is:

```markdown
1. 保持P3工程MVP回归稳定，不重写七工具、证据主链或统一服务。
2. 并行完成M1外部事实工作：≥3000唯一合规候选、来源条款与人工隐私审批、第二轮盲标、仲裁、≥1500 Gold和零泄漏切分。
3. M1通过后进入P4真实CreatorShift特征/模型、Judge校准和risk-coverage实验。
4. P5再实现A2A、URL适配、批量API和Web工作台；LightRAG保持非阻塞A/B候选。
```

Remove both references to `docs/现有代码修改大纲.md`. Change the RAG warning to state that the repository contains a small official corpus plus synthetic evaluation fixtures, neither of which proves complete legal coverage. Replace the dirty-worktree assertion with a general rule to preserve unrelated changes.

- [ ] **Step 3: Add a dated P3 merge-closure acceptance section to HANDOFF**

Add section `4.7 2026-07-27 P3合并与统一CLI收口验收` containing:

```markdown
- P3实现提交`c3ed82d`经合并提交`1aad3f2`进入当前P2分支。
- `AnalysisService`统一本地/MCP主图、Judge后法规检索、Markdown报告和JSON run持久化。
- FastAPI版本化分析、能力和run查询接口与`run_demo.py`共用同一服务；`--llm`仅保留为零Key兼容参数。
- P3聚焦测试`16 passed`；默认全量`276 passed, 2 skipped`；`pip check`、`compileall`和两个P1资产校验器通过。
- 上述结果证明P3工程MVP和离线契约行为，不证明M1数据门、远程MCP部署、法规覆盖质量、论文分类精度或CreatorShift增益。
```

- [ ] **Step 4: Check the two source-of-truth documents**

Run:

```powershell
rg -n "227 passed|260 passed|P3拆统一|P3实现MCPToolGateway|MCPToolGateway/主图MCP回落.*留在P3|docs/现有代码修改大纲.md|当前工作区有未提交修改" README.md HANDOFF.md
git diff --check -- README.md HANDOFF.md
```

Expected: no obsolete matches; `git diff --check` exits `0`.

- [ ] **Step 5: Commit README and HANDOFF**

```powershell
git add -- README.md HANDOFF.md
git commit -m "docs: sync P3 merge handoff facts"
```

---

### Task 3: Synchronize the specification, phase plan, and test runbook

**Files:**
- Modify: `docs/隐性广告识别项目_说明书.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/已有功能测试指令库.md`

**Interfaces:**
- Consumes: Task 1 CLI behavior and Task 2 factual status wording
- Produces: consistent architecture, roadmap, and reproducible test instructions

- [ ] **Step 1: Update the project specification implementation map**

Change the current-state table so it states:

```markdown
| 服务入口 | `implicit-ad-agent/app.py` | 已有 | FastAPI挂载统一服务，提供`/health`、兼容`/analyze`及`/api/v1`分析、能力和run查询。 |
| 演示入口 | `implicit-ad-agent/run_demo.py`、`run_tools_demo.py` | 已有 | 前者调用统一AnalysisService并输出报告/run_id；后者保留七工具独立离线演示。 |
| 主图与状态 | `implicit-ad-agent/impad/graph.py`、`state.py` | 已有 | P1/手工输入归一化、规划、并行工具组、EvidenceBundle、充分性门和保守Judge已接通。 |
| Agent | `implicit-ad-agent/impad/agents/` | 已有 | Supervisor、三类工具组和Judge共用ToolGateway、运行预算、证据与追踪契约。 |
| Detection MCP | `implicit-ad-agent/impad/protocols/mcp/detection_server.py`、`orchestration/mcp_gateway.py` | 已有 | stdio暴露七工具；主图支持MCP调用、契约保持和本地回落。 |
| 法规RAG与Knowledge MCP | `implicit-ad-agent/impad/rag/`、`protocols/mcp/knowledge_server.py` | 已有 | 小规模官方法规语料、Chroma/hash基线、引用守卫、离线评测和Knowledge MCP已实现；不代表完整法律覆盖。 |
| 统一分析与报告 | `implicit-ad-agent/impad/services/`、`api/` | 已有 | API/CLI共用分析、Judge后RAG、可读报告、JSON run持久化和按run_id查询。 |
```

Mark already-created PostRecord, adapters, gateway, EvidenceAdapter, service, Knowledge MCP, report, and evaluation rows as implemented. Keep platform URL adapters, CreatorShift real model, A2A, batch/Web, and research-data assets pending.

- [ ] **Step 2: Update the phase plan without claiming the M1 fact gate passed**

Set the overview rows to:

```markdown
| P2.5 Schema与证据整合 | 07-22～08-17 | 代码层完成 | schema适配、EvidenceBundle、ToolGateway、Function Calling | M2.5 |
| P3 证据型Agent MVP | 08-18～09-21 | 工程MVP完成，正式门受M1约束 | 本地主链、官方法规Chroma基线、MCP、统一服务与报告 | M3 |
```

Add a P3 status note after task 3.7:

```markdown
截至2026-07-27，3.1～3.7的工程MVP均已有实现和离线测试；其中法规部分是小规模官方条款工程基线，远程部署、真实数据效果和完整法规覆盖尚未验收。M1事实门未通过前，不把M3写成论文数据或正式研究评估通过。
```

Change task 5.1 so it only contains remaining P5 scope:

```markdown
| 5.1 | 批量/URL服务扩展 | L | 批量、URL预览/确认API | 复用现有统一AnalysisService，不复制单条分析逻辑 |
```

- [ ] **Step 3: Rewrite obsolete current-boundary claims in the test runbook**

Update the header date to `2026-07-27`. In the current-function table, state:

```markdown
| LangGraph证据主链 | P1/手工输入、七工具、EvidenceBundle、充分性门和保守Judge已接通 | Agent、图证据流与统一服务测试 |
| Detection MCP与Gateway | 七工具stdio协议、主图MCP模式和失败本地回落已实现 | `tests\protocols\mcp`；`tests\orchestration\test_mcp_gateway.py` |
| 法规RAG与Knowledge MCP | 小规模官方语料、Chroma/hash检索、引用守卫、Knowledge MCP和Judge后报告已实现 | `tests\rag`；Knowledge MCP测试；service测试 |
| FastAPI与统一服务 | `/api/v1/analyze`、能力、run查询和兼容`/analyze`共用AnalysisService | `tests\api`；`tests\services` |
| CLI演示 | `run_demo.py`调用统一服务并持久化run；`run_tools_demo.py`独立演示七工具 | `tests\test_demo.py`；`tests\test_tools_demo.py` |
```

Remove P1 Adapter, evidence-chain integration, MCP gateway, Knowledge MCP, official legal baseline, and Judge-after-RAG from the “cannot prove implemented” list. Keep real M1 completion, remote deployment, complete legal coverage, A2A, Web/URL, P4 model, and research accuracy.

- [ ] **Step 4: Update the runbook commands and risk boundaries**

Make these exact operational changes:

1. Section 3.4 baseline becomes `276 passed, 2 skipped`.
2. Section 5.1 becomes “统一P3分析演示”; expected output is three readable reports and three `run_id` values.
3. State that `.impad_runtime\runs\<run_id>.json` is local ignored runtime output.
4. Section 6 states `/health`, `/api/v1/capabilities`, `/api/v1/analyze`, and `/api/v1/runs/{run_id}` are zero-Key local engineering paths.
5. Replace the old optional `run_demo.py --llm` section with a warning that it is deprecated and remains deterministic/zero-Key.
6. Keep `run_demo.py --image` in the real-vision opt-in section, but remove the obsolete claim that it may call an LLM.
7. Move `POST /analyze` out of the paid/LLM warning; document `/api/v1/analyze` as the authoritative route and `/analyze` as compatibility.
8. Troubleshooting for `/analyze` should point to local dependency/runtime errors rather than LLM endpoint latency.
9. Replace “hello_graph.py and graph.py are starter implementations” with: `hello_graph.py` is a teaching-only placeholder; `graph.py` is the evidence graph reached through `AnalysisService`.
10. Clarify the old 30-question synthetic RAG benchmark and the new 15-question official-corpus smoke benchmark are separate and neither proves full legal coverage.

Add this P3 focused command:

```powershell
python -m pytest tests\test_demo.py tests\services tests\api `
  tests\orchestration\test_mcp_gateway.py `
  tests\protocols\mcp\test_knowledge_protocol.py `
  tests\protocols\mcp\test_knowledge_service.py `
  tests\rag\test_official_corpus.py `
  tests\rag\test_official_evaluation.py `
  tests\evaluation\test_classification.py -q
```

Expected: `16 passed`, plus the existing Starlette/httpx deprecation warning where applicable.

- [ ] **Step 5: Audit all five synchronized documents for stale claims**

Run from the repository root:

```powershell
rg -n "171 passed|227 passed|260 passed|使用零成本占位图|P3拆统一分析|P3实现MCPToolGateway|MCP Gateway 和真实法规库尚未完成|主图已经存在.*MCPToolGateway|app.py.*impad.graph|当前响应来自旧起步图|docs/现有代码修改大纲.md" README.md HANDOFF.md docs
git diff --check -- README.md HANDOFF.md docs/隐性广告识别项目_说明书.md docs/隐性广告识别项目_分阶段计划表.md docs/已有功能测试指令库.md
```

Expected: no stale matches in current-state documentation; historical superpowers plans/specs may retain old recorded baselines and must not be rewritten.

- [ ] **Step 6: Commit the detailed documentation synchronization**

```powershell
git add -- docs/隐性广告识别项目_说明书.md docs/隐性广告识别项目_分阶段计划表.md docs/已有功能测试指令库.md
git commit -m "docs: update P3 architecture and test runbook"
```

---

### Task 4: Run final acceptance and record the verified boundary

**Files:**
- Modify only if observed counts differ: `README.md`, `HANDOFF.md`, `docs/已有功能测试指令库.md`

**Interfaces:**
- Consumes: all implementation and documentation from Tasks 1–3
- Produces: a verified final repository state with no unrecorded test drift

- [ ] **Step 1: Run dependency and compilation checks**

```powershell
Set-Location -LiteralPath 'D:\AAA Jobs\Detection-of-Recessive-Advertising\implicit-ad-agent'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests app.py run_demo.py
```

Expected: `No broken requirements found.` and silent compile success.

- [ ] **Step 2: Run focused P3 acceptance**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_demo.py tests\services tests\api `
  tests\orchestration\test_mcp_gateway.py `
  tests\protocols\mcp\test_knowledge_protocol.py `
  tests\protocols\mcp\test_knowledge_service.py `
  tests\rag\test_official_corpus.py `
  tests\rag\test_official_evaluation.py `
  tests\evaluation\test_classification.py -q
```

Expected: `16 passed`.

- [ ] **Step 3: Run the default CLI and full regression**

```powershell
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: the CLI emits three reports/run IDs; pytest reports `276 passed, 2 skipped` with no failures.

- [ ] **Step 4: Validate both P1 asset entry points**

```powershell
Set-Location -LiteralPath 'D:\AAA Jobs\Detection-of-Recessive-Advertising'
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
```

Expected: both output `VALIDATION PASSED`.

- [ ] **Step 5: Verify final documentation and working tree**

```powershell
rg -n "276 passed, 2 skipped|16 passed|AnalysisService|run_demo.py|M1.*未通过" README.md HANDOFF.md docs/已有功能测试指令库.md
git diff --check
git status --short --branch
```

Expected: required facts are present, whitespace check passes, and only intentional task files are changed.

- [ ] **Step 6: Correct observed numbers if necessary**

If a successful test command reports a count other than the expected count, replace only the three current-baseline statements in README, HANDOFF, and the test runbook with the exact observed result, rerun `git diff --check`, and do not edit historical design/plan snapshots.

- [ ] **Step 7: Commit any final evidence-only corrections**

Run only when Step 6 changed a document:

```powershell
git add -- README.md HANDOFF.md docs/已有功能测试指令库.md
git commit -m "docs: record verified P3 closure baseline"
```

Do not create an empty commit when the expected counts already match.
