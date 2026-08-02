# 已有功能测试指令库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `docs/已有功能测试指令库.md`，让项目开发者能从激活虚拟环境开始，安全地跑通所有当前已完成的本地功能，并通过理论、源码、测试和实验四层教学理解系统。

**Architecture:** 文档先提供零 Key、零联网的线性必跑路径，再按功能模块给出专项命令和手工检查，最后隔离真实视觉、LLM 与外部追踪等可选路径。每个功能条目统一连接验证目标、命令、通过标准、代码入口、理论解释、测试能证明和不能证明的性质。

**Tech Stack:** Markdown、Windows PowerShell、Python 3.10+、pytest、FastAPI/Uvicorn、MCP Python SDK、Chroma、YOLO/EasyOCR（可选）、OpenAI 兼容 LLM（可选）

## Global Constraints

- 目标文件固定为 `docs/已有功能测试指令库.md`。
- 所有主命令从 `D:\AAA Jobs\Detection-of-Recessive-Advertising` 开始。
- 完成依赖安装后，必跑测试必须零 Key、零联网，不读取或上传真实项目数据。
- 首次安装依赖可能访问 Python 包索引，文档必须单独说明。
- 真实视觉、真实 LLM、LangSmith、模型下载和可能计费路径必须使用醒目警告，并排除在默认一键验收之外。
- P1 Schema、真实法规语料、MCP Gateway、A2A、网页工作台和当前主图的完整新架构尚未验收，不得写成已完成功能。
- 当前默认全量回归基线为 `142 passed, 2 skipped`；文档必须标注这是 2026-07-24 当前分支实测快照，不是永久常量。
- PowerShell 命令优先使用激活后的 `python -m ...`，排障命令同时给出显式 `.\.venv\Scripts\python.exe` 形式。
- 不修改业务代码、测试代码或依赖版本；只创建测试指令库并验证已有事实。

---

### Task 1: 建立手册骨架与环境必跑路径

**Files:**
- Create: `docs/已有功能测试指令库.md`
- Reference: `docs/superpowers/specs/2026-07-24-existing-function-test-library-design.md`
- Reference: `implicit-ad-agent/pyproject.toml`
- Reference: `implicit-ad-agent/requirements.txt`
- Reference: `implicit-ad-agent/tests/conftest.py`

**Interfaces:**
- Consumes: 当前 `.venv`、`pyproject.toml` 的 `mcp`/`rag` extras、pytest 的 `vision_integration` opt-in 策略。
- Produces: 后续模块章节共同引用的工作目录、环境变量、安全等级、通过标志和命令约定。

- [ ] **Step 1: 写出标题、阅读方式和三种安全等级**

在目标文档中明确：

```markdown
- ✅ 必跑：安装完成后零 Key、零联网。
- 🧪 专项：仍为本地测试，用于定位具体模块。
- ⚠️ 可选：可能加载真实模型、联网、上传轨迹或产生费用。
```

- [ ] **Step 2: 写出从仓库根目录激活虚拟环境的完整命令**

使用：

```powershell
Set-Location 'D:\AAA Jobs\Detection-of-Recessive-Advertising'
Set-Location '.\implicit-ad-agent'
.\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable); assert sys.prefix != sys.base_prefix"
```

同时给出仅在执行策略阻止激活时使用的当前进程临时放行：

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
```

- [ ] **Step 3: 写出依赖安装和身份确认**

使用：

```powershell
python -m pip install -r requirements.txt
python -m pip install -e ".[mcp,rag]"
python -m pip check
python -c "import pytest, mcp, chromadb; print('required test dependencies: OK')"
```

说明前两条安装命令可能联网；后两条只做本地检查。通过标准分别为安装成功、`No broken requirements found.` 和 `required test dependencies: OK`。

- [ ] **Step 4: 写出必跑的一键验收**

使用：

```powershell
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
python -m compileall -q impad tests
python -m pytest -q
```

通过标准：`compileall` 退出码为 0；pytest 当前快照为 `142 passed, 2 skipped`，且不存在 `failed` 或 `error`。解释两个 skip 是显式 opt-in 的真实视觉测试。

- [ ] **Step 5: 检查手册开头命令**

Run:

```powershell
Get-Content -Encoding UTF8 '..\docs\已有功能测试指令库.md' | Select-Object -First 120
```

Expected: 激活、解释器确认、安装、依赖检查、编译和全量回归按依赖顺序出现；可选命令没有混入必跑代码块。

- [ ] **Step 6: 提交手册骨架**

```powershell
git add -- docs/已有功能测试指令库.md
git commit -m "docs: add existing feature test runbook"
```

### Task 2: 增加模块专项测试与手工运行指令

**Files:**
- Modify: `docs/已有功能测试指令库.md`
- Reference: `implicit-ad-agent/tests/`
- Reference: `implicit-ad-agent/run_demo.py`
- Reference: `implicit-ad-agent/run_tools_demo.py`
- Reference: `implicit-ad-agent/app.py`
- Reference: `implicit-ad-agent/impad/protocols/mcp/detection_server.py`

**Interfaces:**
- Consumes: Task 1 中已激活的 PowerShell 环境和安全等级。
- Produces: 每个已完成模块的独立验证入口、通过标准、代码索引和失败首查点。

- [ ] **Step 1: 写出基础 Agent、API 和演示专项**

命令必须包含：

```powershell
python -m pytest tests\test_smoke.py tests\test_agents.py tests\test_keywords.py tests\test_vision.py -q
python -m pytest tests\test_tools_demo.py -q
python run_demo.py
python run_tools_demo.py
```

说明 `run_demo.py` 不带 `--llm` 走零 Key 起步图；`run_tools_demo.py` 使用脱敏固定样例并调用七工具。对终端输出执行结构检查，不把规则占位图描述成最终架构。

- [ ] **Step 2: 写出七工具和 VisionContext 专项**

命令必须包含：

```powershell
python -m pytest tests\test_tool_contracts.py tests\test_tool_registry.py tests\test_tool_text_intent.py tests\test_tool_sentiment.py tests\test_tool_topic_drift.py tests\test_tool_comment_anomaly.py tests\test_tool_ocr_extract.py tests\test_tool_detect_logo_product.py tests\test_tool_image_text_consistency.py tests\test_tool_vision_context.py tests\test_vision_consistency_sanity.py -q
```

通过标准：退出码 0；七个 registry 工具均可序列化调用；缺图、样本不足等情况使用 `skipped`/`score=null`，而不是伪造 0 分。

- [ ] **Step 3: 写出契约与编排专项**

命令必须包含：

```powershell
python -m pytest tests\contracts -q
python -m pytest tests\orchestration -q
```

说明契约测试验证 Evidence/Verdict/Run 的字段约束和不变量；编排测试验证 Capability Plan、白名单、预算、去重、超时、错误归一化和 Trace，而不是判断广告识别准确率。

- [ ] **Step 4: 写出 MCP 专项和服务手工启动**

命令必须包含：

```powershell
python -m pytest tests\protocols\mcp -q
python -m impad.protocols.mcp.detection_server
```

说明 pytest 会通过真实 stdio 子进程完成 list/call/错误映射/Local-MCP 一致性；直接启动 Server 后安静等待 stdin 是正常现象，使用 `Ctrl+C` 停止，不把“无网页输出”判为失败。

- [ ] **Step 5: 写出 RAG 与 CreatorShift 专项**

命令必须包含：

```powershell
python -m pytest tests\rag -q
python -m pytest tests\creator_shift -q
python -m pytest tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q
```

通过标准：各命令退出码 0；组合命令当前快照为 `80 passed`。RAG 当前合成基线为 Recall@5 `0.65`、直接题 `0.90`、跨文档题 `0.40`、无答案误引率 `0`；CreatorShift 必须拒绝同时间、未来时间、跨 creator 和重复帖子历史。

- [ ] **Step 6: 写出 FastAPI 手工验证**

在第一个 PowerShell 窗口：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

在第二个 PowerShell 窗口只验证本地健康接口：

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/health'
```

说明使用 `Ctrl+C` 停止服务；该 API 是现有起步接口，不是目标研究工作台。`POST /analyze` 使用 `graph.py`，移入 Task 3 的联网/费用可选区。

- [ ] **Step 7: 对模块命令做路径和收集检查**

Run:

```powershell
python -m pytest --collect-only -q
```

Expected: 收集成功且无 import error；真实视觉用例仍只在指定 marker 时执行。

- [ ] **Step 8: 提交专项测试章节**

```powershell
git add -- docs/已有功能测试指令库.md
git commit -m "docs: document module test commands"
```

### Task 3: 隔离高风险可选测试并补齐排障

**Files:**
- Modify: `docs/已有功能测试指令库.md`
- Reference: `implicit-ad-agent/requirements-vision.txt`
- Reference: `implicit-ad-agent/tests/test_vision_integration.py`
- Reference: `implicit-ad-agent/README.md`
- Reference: `implicit-ad-agent/impad/config.py`
- Reference: `implicit-ad-agent/impad/llm.py`

**Interfaces:**
- Consumes: Task 1 的安全等级和 Task 2 的本地基线。
- Produces: 与默认回归物理分隔的视觉/LLM/追踪实验，以及可按症状执行的排障树。

- [ ] **Step 1: 写出真实视觉警告和命令**

必须在命令前说明可能安装数 GB 依赖、下载模型、占用 GPU/CPU，并建议先保存全量本地回归结果：

```powershell
python -m pip install -r requirements-vision.txt
python -m pytest -m vision_integration -q
python run_tools_demo.py --image samples\images\test_image.jpg
```

当前视觉集成通过快照为 `2 passed`。说明首次模型下载需要网络；PyTorch 弃用或 `pin_memory` warning 不自动等于失败。

- [ ] **Step 2: 写出真实 LLM 和 LangSmith 警告**

只给出人工确认后的可选命令：

```powershell
python run_demo.py --llm
$body = @{ text = '分享一个最近使用的普通水杯。' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/analyze' -ContentType 'application/json' -Body $body
```

要求读者先检查 `.env` 中端点、模型名、Key、LangSmith tracing 状态和供应商计费规则；明确禁止把真实 Key 或用户数据写入文档、终端截图或仓库。说明 `POST /analyze` 与带 `--image` 的 `run_demo.py` 都进入 `graph.py`，可能因 `.env` 中存在 Key 而触发 NLP LLM；`run_tools_demo.py --image` 才是纯本地视觉工具链。

- [ ] **Step 3: 写出症状到检查动作的排障表**

至少覆盖：

```text
No module named pytest/langgraph -> 解释器不在 .venv
Activate.ps1 被禁止 -> Process 级 RemoteSigned
Fatal error in launcher -> 使用 python -m pytest/pip/uvicorn
mcp/chromadb import error -> 安装 .[mcp,rag]
2 skipped -> 默认行为，真实视觉未 opt-in
MCP Server 启动后无输出 -> 正在等待 stdio
测试尝试上传 LangSmith -> 关闭两个 tracing 环境变量
RAG 返回空引用 -> 阈值拒答，不得补写条款
CreatorShift 历史被拒绝 -> 检查 creator、时区和 published_at < target_time
```

- [ ] **Step 4: 写出验收记录模板**

模板固定包含日期、分支、HEAD、Python、依赖检查、全量测试、专项测试、可选测试是否执行、失败摘要和复现命令。不得把未执行的可选测试填写为通过。

- [ ] **Step 5: 检查危险命令隔离**

Run:

```powershell
Select-String -Path '..\docs\已有功能测试指令库.md' -Pattern '--llm|vision_integration|LANGSMITH|可能产生费用|可选'
```

Expected: 每个 `--llm`、真实视觉和 tracing 命令都位于可选章节附近，并有联网/费用或数据边界说明。

- [ ] **Step 6: 提交风险与排障章节**

```powershell
git add -- docs/已有功能测试指令库.md
git commit -m "docs: add optional test safety and troubleshooting"
```

### Task 4: 编写理论—代码—测试—实验教学

**Files:**
- Modify: `docs/已有功能测试指令库.md`
- Reference: `implicit-ad-agent/impad/tools/contracts.py`
- Reference: `implicit-ad-agent/impad/contracts/evidence.py`
- Reference: `implicit-ad-agent/impad/contracts/verdict.py`
- Reference: `implicit-ad-agent/impad/orchestration/`
- Reference: `implicit-ad-agent/impad/protocols/mcp/detection_server.py`
- Reference: `implicit-ad-agent/impad/rag/`
- Reference: `implicit-ad-agent/impad/creator_shift/`
- Reference: `implicit-ad-agent/impad/tools/vision_context.py`

**Interfaces:**
- Consumes: Task 2 已建立的模块索引与测试命令。
- Produces: 按学习深度排序、与当前项目绑定的理论教学和可复现实验。

- [ ] **Step 1: 写出“必须重点掌握”课程**

逐项使用“问题 → 理论假设 → 数据流 → 代码 → 测试 → 反例 → 小实验 → 尚未证明”模板，覆盖：

```text
契约驱动设计
ToolResult 与缺失证据语义
EvidenceBundle 到 VerdictReport 的证据链
测试分层与可复现性
Capability Plan / Function Calling / Tool Gateway
CreatorShift 的纵向建模与未来信息泄漏
```

- [ ] **Step 2: 写出“部分深入学习”课程**

覆盖：

```text
MCP 的业务/协议/部署三层解耦
向量检索、余弦相似度、Top-K、Recall@K 与阈值拒答
引用完整性与 RAG 不污染分类结论
VisionContext 内容哈希缓存、版本与幂等性
多模态缺失、相关性与不能补零
Run State / Trace / Log / Metric 的区别
置信度校准、复核与拒绝预测
```

Recall@K 使用公式：

```text
Recall@K = 前 K 个检索结果中命中的相关条款数 / 该查询全部相关条款数
```

并使用当前项目 Recall@5 `0.65` 解释其含义和局限。

- [ ] **Step 3: 写出“当前只需了解”地图**

明确 LangGraph 起步图、FastAPI 起步接口、真实 LLM/LangSmith、A2A、网页工作台和 P1 主链适配的当前状态，避免读者把未来设计当作已完成代码。

- [ ] **Step 4: 为重点概念加入可执行小实验**

实验仅使用现有测试或 `pytest -k`，至少包含：

```powershell
python -m pytest tests\contracts\test_evidence.py -k skipped -vv
python -m pytest tests\orchestration\test_function_calling.py -k "duplicate or budget or timeout" -vv
python -m pytest tests\protocols\mcp -k consistency -vv
python -m pytest tests\rag -k "abstain or benchmark" -vv
python -m pytest tests\creator_shift -k "equal_or_future or cross_creator" -vv
```

每个实验说明观察点，不要求修改业务代码。

- [ ] **Step 5: 检查理论内容与代码索引是否闭环**

Run:

```powershell
$doc = Get-Content -Raw -Encoding UTF8 '..\docs\已有功能测试指令库.md'
@('契约驱动','证据','Function Calling','MCP','Recall@K','CreatorShift','未来信息泄漏','当前测试不能证明') |
  ForEach-Object { if (-not $doc.Contains($_)) { throw "缺少教学主题：$_" } }
```

Expected: 命令退出码 0，不抛出“缺少教学主题”。

- [ ] **Step 6: 提交教学章节**

```powershell
git add -- docs/已有功能测试指令库.md
git commit -m "docs: teach theory behind existing tests"
```

### Task 5: 实跑验收并完成文档质量检查

**Files:**
- Modify: `docs/已有功能测试指令库.md`（仅修正实跑发现的错误）
- Test: `implicit-ad-agent/tests/`

**Interfaces:**
- Consumes: Tasks 1-4 的完整手册。
- Produces: 与当前工作区事实一致、可复制执行、无占位符的最终交付。

- [ ] **Step 1: 运行本地必跑检查**

在 `implicit-ad-agent` 目录运行：

```powershell
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
python -m pip check
python -m compileall -q impad tests
python -m pytest -q
```

Expected: `pip check` 输出 `No broken requirements found.`；`compileall` 退出码 0；pytest 为 `142 passed, 2 skipped` 或仅因后续合法测试新增而增加，不允许失败。

- [ ] **Step 2: 运行模块专项组合**

```powershell
python -m pytest tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q
```

Expected: 当前快照 `80 passed`，无失败和错误。

- [ ] **Step 3: 运行教学小实验**

逐条执行 Task 4 Step 4 的五条 `pytest -k` 命令。

Expected: 每条至少选中一个测试、退出码 0；若表达式没有选中目标测试，修正文档中的 `-k` 表达式。

- [ ] **Step 4: 运行默认演示**

```powershell
python run_demo.py
python run_tools_demo.py
```

Expected: 两条命令退出码 0；不要求 Key；工具演示调用七个工具并输出可序列化结果。

- [ ] **Step 5: 检查文档中的本地路径**

```powershell
$paths = @(
  'implicit-ad-agent\pyproject.toml',
  'implicit-ad-agent\app.py',
  'implicit-ad-agent\run_demo.py',
  'implicit-ad-agent\run_tools_demo.py',
  'implicit-ad-agent\impad\contracts\evidence.py',
  'implicit-ad-agent\impad\orchestration\function_calling.py',
  'implicit-ad-agent\impad\protocols\mcp\detection_server.py',
  'implicit-ad-agent\impad\rag\chroma_retriever.py',
  'implicit-ad-agent\impad\creator_shift\contracts.py'
)
$paths | ForEach-Object { if (-not (Test-Path $_)) { throw "路径不存在：$_" } }
```

Expected: 退出码 0。

- [ ] **Step 6: 做占位符、空白和范围审计**

在仓库根目录运行：

```powershell
rg -n "TBD|TODO|待补充|以后填写|xxx" "docs\已有功能测试指令库.md"
git diff --check -- "docs\已有功能测试指令库.md"
rg -n "A2A|网页工作台|真实法规|P1" "docs\已有功能测试指令库.md"
```

Expected: 第一条无匹配；第二条退出码 0；第三条只命中“尚未完成/当前不可验收”的边界说明。

- [ ] **Step 7: 核对 Git 作用域**

```powershell
git status --short
git diff -- "docs/已有功能测试指令库.md"
```

Expected: 本任务只新增或修改目标手册；工作区中既有的其他修改保持原样。

- [ ] **Step 8: 提交实跑修正**

仅当实跑产生修正时：

```powershell
git add -- docs/已有功能测试指令库.md
git commit -m "docs: verify existing feature test runbook"
```
