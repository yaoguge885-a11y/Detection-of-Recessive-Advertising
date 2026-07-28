# P3 统一 CLI 入口与合并收口设计

## 目标

在不扩大 P3 功能范围的前提下，让开发者演示入口 `run_demo.py` 与
FastAPI 共用已经合并的 `AnalysisService`，并把项目文档同步到当前可验证
事实。完成后，默认 CLI 能以零 Key、零网络方式执行完整的
`PostRecord → 工具 → EvidenceBundle → Judge → 法规检索 → 报告 → run 持久化`
链路，不再把 `hello_graph.py` 占位图描述为项目主演示。

本任务只关闭 P3 合并后的入口与事实漂移，不把代码测试通过解释为 M1 数据
关口、真实分类精度或论文结论已经通过。

## 当前事实

- 当前分支已经合并 P3 MVP 提交 `c3ed82d`。
- `AnalysisService` 已统一调用主图、Judge 后法规检索、可读报告和 JSON run
  持久化。
- `/api/v1/analyze`、`/api/v1/runs/{run_id}` 和能力接口已使用统一服务。
- Detection MCP、本地回落、Knowledge MCP、版本化官方法规语料基线和分类
  评估指标已有自动测试。
- 现场验证通过 `pip check`、`compileall`、P3 聚焦测试 `13 passed` 和默认
  全量回归 `273 passed, 2 skipped`。
- `run_demo.py` 的默认路径仍调用 `hello_graph.py`；`--llm` 和 `--image`
  路径直接调用 `impad.graph`，均绕过 `AnalysisService`。
- README、HANDOFF、说明书、阶段表和已有功能测试指令库仍保留 P3 合并前
  状态、旧测试数量或对已删除文档的引用。
- 正式 M1 仍受真实候选数量、Gold、第二轮盲标、泄漏检查、条款与隐私审批
  限制，不能因 P3 工程代码可运行而标记为通过。

## 范围

### 本轮包含

1. 将 `run_demo.py` 的默认、`--llm` 兼容参数和 `--image` 路径统一到
   `AnalysisService`。
2. 保持默认演示零 Key、零网络，不加载真实视觉模型。
3. 保持 `--image <path>` 为显式真实视觉路径；缺少可选视觉依赖时沿用工具
   和主图的保守降级语义。
4. 输出统一服务生成的 `readable_report`，并显示可用于查询持久化结果的
   `run_id`。
5. 为 CLI 入口补充自动测试，证明它调用统一服务而不是
   `hello_graph.py`/裸 `graph.invoke`。
6. 更新 README、HANDOFF、项目说明书、分阶段计划表和已有功能测试指令库中
   与本任务直接相关的 P3 状态、演示命令、测试基线和未完成边界。
7. 删除文档中对已经不存在的 `docs/现有代码修改大纲.md` 的入口引用。
8. 运行聚焦测试、默认全量回归、依赖/编译检查和 P1 资产校验，记录本次
   验收结果。

### 本轮不包含

- 批量分析 API、URL 导入、平台适配或 Web 研究工作台；
- A2A 远程专家或独立远程部署；
- LightRAG 对照实验；
- CreatorShift 真实特征、模型训练或 Judge 经验校准；
- 扩充法规语料、修改检索算法或宣称法律知识质量；
- 修改 M1 数量、Gold、一致性、泄漏或合规门槛；
- 重构七个 P2 工具、LangGraph 主图或现有契约；
- 删除 `hello_graph.py`，因为它仍可作为独立教学占位模块保留，只是不再作为
  默认项目演示入口。

## CLI 设计

`run_demo.py` 继续读取 `samples/sample_posts.json`，逐条调用同一个
`AnalysisService` 实例。单次进程复用服务、检索器和 run store，避免为每条
样本重复创建基础设施。

默认命令：

```powershell
.\.venv\Scripts\python.exe run_demo.py
```

行为：

1. 读取脱敏样本；
2. 使用 `runtime_mode="local"`；
3. 不读取 API Key，不联网，不加载真实视觉模型；
4. 对每条样本输出 `readable_report`；
5. 输出 `run_id`，对应记录保存在 `.impad_runtime/runs/`。

`--image <path>` 将显式图片路径注入演示帖后仍调用同一服务。该参数继续代表
用户主动选择真实视觉依赖，不改变默认离线验收边界。

`--llm` 继续被命令行接受，避免破坏已有脚本，但只作为兼容参数：输出一条
弃用说明后仍调用确定性 `AnalysisService`。本任务不重新引入 LLM 选择或
Key 读取。

## 接口与依赖边界

CLI 只依赖 `impad.services.AnalysisService` 的公开接口：

```python
result = service.analyze(post, runtime_mode="local")
```

CLI 读取：

- `result.readable_report`
- `result.run_metadata.run_id`

CLI 不读取 LangGraph State 内部字段，不直接调用 `graph.invoke`，也不自行
拼装 verdict、证据或法规引用。API 和 CLI 因而共享同一权威分析行为。

为便于测试，CLI 内部提供一个小型可调用函数，接收样本路径、可选图片路径和
可注入的 `AnalysisService`。不增加新的抽象层、配置系统或通用 CLI 框架。

## 数据流

```text
run_demo.py
  → sample JSON / explicit image path
  → AnalysisService.analyze(runtime_mode="local")
  → PostRecord normalization
  → capability plan and seven-tool evidence flow
  → Evidence Adequacy Gate
  → VerdictReport
  → post-Judge legal retrieval
  → readable_report
  → JsonRunStore
  → terminal report + run_id
```

## 错误与降级

- 样本文件不存在、JSON 无效或帖子输入不符合契约时，CLI 返回非零退出并保留
  可定位错误；不把错误转换成成功报告。
- 默认样本没有真实本地图片时，保持缺失/跳过语义，不将其计为负向证据。
- 显式 `--image` 路径不存在或视觉依赖不可用时，沿用现有适配器、工具和充分
  性门的错误/降级行为，不在 CLI 中复制判断逻辑。
- 法规检索失败时，由 `AnalysisService` 记录 degradation 和空引用；CLI
  只展示权威报告。
- run 持久化失败时不声称分析已被保存；异常继续向命令行传播。
- `--llm` 不读取 Key、不触发网络，只提示兼容参数已弃用。

## 测试策略

实施采用测试驱动，先写能证明旧入口问题的失败测试，再做最小修改。

至少覆盖：

1. 默认 CLI 对全部样本调用注入的 `AnalysisService`；
2. 默认调用固定使用 `runtime_mode="local"`；
3. CLI 输出服务返回的报告和 `run_id`；
4. `--image` 只覆盖演示帖的 `image_path`，仍使用统一服务；
5. `--llm` 被接受并提示弃用，但不切换到旧图或 LLM；
6. 生产代码不再导入 `impad.hello_graph` 或直接调用
   `impad.graph.graph.invoke`；
7. 现有 API、P2.5、MCP、RAG、CreatorShift 和数据治理测试保持通过。

测试使用注入的轻量假服务验证 CLI 编排，不在默认测试中加载 Chroma、YOLO、
EasyOCR、网络或真实 API Key。完整 `AnalysisService` 行为继续由现有 service
和 API 测试覆盖。

## 文档同步规则

文档只写现场验证和代码可证明的状态：

- 把统一分析服务、正式 API、MCPToolGateway 回落、Knowledge MCP、Judge 后
  RAG、报告、run 查询和评估指标标记为“工程 MVP 已实现”；
- 把全量测试基线更新为本次最终实测值，而不是预先写死 `273`；
- 明确法规语料是小规模官方条款工程基线，不是完备法律知识库；
- 明确测试证明契约和离线工程行为，不证明真实分类准确率或法律判断质量；
- M1 继续标记为事实侧未通过；
- P4 CreatorShift、P5 A2A/URL/Web、LightRAG 对照继续保留在后续阶段；
- 阶段表可将 P3 标记为“工程 MVP 已完成/阶段验收受 M1 事实门约束”，避免
  同时出现“未开始”和“代码已完成”的矛盾。

## 验收标准

本任务完成必须同时满足：

1. `run_demo.py` 三条入口路径均不再直接使用旧图；
2. 默认演示在零 Key、零网络条件下完成并输出报告和 `run_id`；
3. 新增 CLI 测试先失败后通过；
4. P3 聚焦测试通过；
5. 默认全量回归通过，且没有新增非预期 skip；
6. `pip check` 和 `compileall` 通过；
7. 两个 P1 资产校验入口均输出 `VALIDATION PASSED`；
8. `git diff --check` 通过；
9. 五份目标文档之间的 P3 状态、测试基线和未完成边界一致；
10. 不改动 M1 门槛，不引入本轮范围外功能。

建议验收命令：

```powershell
cd implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests\test_demo.py -q
.\.venv\Scripts\python.exe run_demo.py
.\.venv\Scripts\python.exe -m pytest tests\services tests\api `
  tests\orchestration\test_mcp_gateway.py `
  tests\protocols\mcp\test_knowledge_protocol.py `
  tests\protocols\mcp\test_knowledge_service.py `
  tests\rag\test_official_corpus.py `
  tests\rag\test_official_evaluation.py `
  tests\evaluation\test_classification.py -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests
.\.venv\Scripts\python.exe -m pytest -q

cd ..
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
git diff --check
```

最终验收报告分别陈述代码结果、文档结果和仍未完成的研究/数据边界，不使用
“全部 P3 正式通过”这种超出证据的表述。
