# P1 合并前独立模块设计

## 目标

在不读取或复制 P1 权威 Schema、不修改现有 LangGraph 主链的前提下，完成四组可独立验证、后续可直接复用的基础能力：

1. 证据与运行契约、Function Calling 约束和运行追踪；
2. Detection MCP Server；
3. Chroma 法规 RAG 基础与离线评测；
4. CreatorShift 防泄漏历史视图和简单历史基线。

每个模块必须先写失败测试，再写最小实现；模块测试与默认全量回归均通过后才算完成。

## 范围边界

### 本轮包含

- 扩充 `EvidenceItem` 与 `EvidenceBundle`，同时保持旧构造方式兼容；
- 禁止同工具、同规范化参数的重复 Function Call；
- 将 Capability Plan 的调用预算和单工具超时应用到执行阶段；
- 记录结构化 run event，并能汇总进 `RunMetadata`；
- 使用官方 Python MCP SDK v1.x 建立一个 Detection Tool Server，复用现有 `LocalToolGateway`；
- 使用显式、确定性的本地 embedding 建立 Chroma 离线检索，不下载模型、不调用网络；
- 建立30题离线检索评测fixture，其中直接检索、跨文档检索、无答案拒答各10题；
- 建立 CreatorHistoryView 的同creator、严格早于目标时间和最低样本约束；
- 实现 mean、max、EMA 三种历史池化和可解释shift结果。

### 本轮不包含

- P1 `content_record → PostRecord` 映射；
- `CaptureStatus` 与披露充分性；
- 7个正式 EvidenceAdapter；
- `state.py`、`graph.py`、Agent和Judge重构；
- 真实法规语料收集与法律结论；
- CreatorShift训练模型和真实数据指标；
- A2A、平台URL适配、Web工作台。

## 架构

### 证据与运行层

`ToolResult` 仍是工具边界。`EvidenceItem` 增加极性、强度、来源类型、生产者、状态、限制和时间；`EvidenceBundle` 增加模态覆盖、冲突与缺失要求。新增 `RunEvent`/`RunTrace`，Function Calling 在提出、拒绝、完成、失败和停止时记录事件。

Function Calling 继续只执行 Planner 允许的工具。重复检测使用“工具名 + 规范化参数SHA256”，无效或重复调用不会进入ToolGateway。传入 `CapabilityPlan` 时，执行器使用其 `call_budget` 和 `tool_timeouts`。

### MCP层

一个 Detection MCP Server 暴露七个工具，不复制工具核心。MCP名称来自 `ToolSpec.mcp_name`；输入Schema来自工具注册表；输出Schema来自 `ToolResult`。服务端把MCP调用映射到 `LocalToolGateway.call()`，并返回结构化 ToolResult。

默认提供stdio入口，测试通过真实MCP会话完成工具发现和至少一次调用。SDK固定在稳定v1范围 `mcp>=1.27,<2`，避免尚未稳定的v2接口。

### RAG层

`LegalDocument → LegalSection → LegalChunk → ChromaLegalRetriever → LawEvidence`。索引和查询embedding均由确定性哈希向量生成，测试和默认运行不下载外部模型。Chroma使用关闭匿名遥测的EphemeralClient；后续可在同一接口替换为持久化或语义embedding。

`CitationGuard` 只允许返回索引中实际存在的chunk。评测器计算 Recall@5、可回答题覆盖率和无答案误引率。测试语料明确标记为合成fixture，不作为真实法律依据。

### CreatorShift层

`CreatorHistoryView` 接收目标creator、目标时间和历史特征。构造时拒绝跨creator、未来或同时间记录，按时间排序，并返回历史充分性。池化器对同一特征集合执行mean、max或EMA；shift计算目标特征与历史池化向量的绝对差异，输出总体分数及贡献最大的特征。

## 错误与降级

- 缺少可用工具时计划预算为0；
- Function Call参数错误、重复或越权时返回结构化拒绝轨迹；
- MCP未知工具返回协议错误，不泄露内部异常；
- 单工具错误继续以ToolResult error返回；
- RAG无可靠命中返回空列表，不生成引用；
- CreatorShift历史不足返回insufficient/unavailable，不返回伪造的0分。

## 验收

- 每个新增行为都有先红后绿的单元或集成测试；
- MCP测试使用真实官方SDK会话，而不是只测试内部mock；
- Chroma测试零Key、零联网、零模型下载；
- 30题fixture结构完整，并能由评测器运行；
- CreatorShift测试覆盖跨creator、未来泄漏、样本不足和三种池化；
- `implicit-ad-agent/.venv/Scripts/python.exe -m pytest -q` 全量通过；
- `compileall` 与 `git diff --check` 通过；
- 最后更新 `HANDOFF.md` 的当前事实、依赖、测试命令、已完成与P1阻塞边界。
