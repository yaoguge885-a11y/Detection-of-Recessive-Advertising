# HANDOFF：隐性广告识别项目

> 面向下一位接手开发者的事实交接。最后更新：2026-07-26（远端最新P1合入本地P2后）。
> 先读本文件，再读 `docs/隐性广告识别项目_说明书.md`、`docs/隐性广告识别项目_分阶段计划表.md` 和 `docs/现有代码修改大纲.md`。

## 1. 一句话目标

构建一个证据驱动的多智能体系统：输入社交媒体文本、图片、评论和创作者历史，输出 **明广 / 暗广 / 非广** 三元判定、置信度、可追溯证据和法规/平台规则引用；证据不足或采集不完整时转为 `需复核`。

首批用户是4名项目开发者。最终形态是可在GitHub直接下载运行的开源网页工程，浏览器插件为冲刺目标。

## 2. 已冻结的关键决策

### 2.1 研究与工程边界

- 论文核心创新：**CreatorShift纵向多模态偏好变化建模**。
- Agent、Function Calling、MCP、A2A、RAG是正式工程贡献，不冒充算法创新。
- 传统XGBoost、文本单模态、单帖多模态和简单历史池化均作为基线。
- CreatorShift的最低成功标准是优于“单帖多模态”和“简单历史池化”，不能只要求优于XGBoost。

### 2.2 标签边界

- 正式金标：`明广 / 暗广 / 非广`。
- 商业意图成立后，有明确披露证据为明广；无披露且采集充分为暗广。
- `需复核` 是运行状态；P1 schema中的 `uncertain/out_of_scope` 是数据治理状态，不是第四个金标。
- 不单独训练“披露状态分类器”；保留轻量 `disclosure_evidence`，记录披露文本、平台标记及来源位置。

### 2.3 系统边界

- `Function Calling`：L0默认主链。
- `RAG`：L0知识与引用层，分类后运行，不污染分类证据。
- `MCP`：L1正式工具接口；本地和MCP复用同一工具实现。
- `A2A`：L1正式分布式运行模式；保留本地模式作为参考实现和降级路径。
- 网页端是最低产品目标；小红书优先、B站其次，抖音后置；浏览器插件在网页/API稳定后开发。

## 3. 当前Git与工作区事实

- 当前工作分支：`P2_Tool-Compartment-Model-Tooling`。
- P1远程分支：`origin/P1-·-数据地基与标注规范`，本次拉取到的最新提交为 `6679671d35abf6d4bd9f17ec92f5585397244202`。
- 本地P1→P2合并提交：`98cb599e280d97dddf779cfaa1b0a90d4f2b7608`；两个父提交分别是原P2 `76fb13f` 与最新P1 `6679671`。
- 已用 `git merge-base --is-ancestor` 验证 `6679671` 是当前P2的祖先；两边历史均被保留。
- 本次只完成本地合并，没有推送远端P2。
- 合并前的67个未提交/未跟踪P2文件已逐路径恢复；除本文件外，其余修改继续保持未提交状态，不得覆盖、清理或重置。
- 安全备份仍保留在 `stash@{0}`：`codex-pre-p1-merge-2026-07-26`，对象为 `6c0bfedd4c8d990a5ffccd8a089bb3ee9bafcba3`。确认工作区无误前不要删除。

不要从最新 `main` 重新建空目录复制文件，也不要再次把P1整分支覆盖到P2。后续开发直接从当前P2继续，并将现有未提交模块按职责拆成可Review提交。

## 4. 当前代码状态

主程序目录：`implicit-ad-agent/`。

### 4.1 已完成

| 模块 | 事实状态 |
| --- | --- |
| LangGraph骨架 | `Supervisor → NLP/视觉/行为 → Judge` 可运行 |
| 文本能力 | 关键词唯一事实来源、6维权重、LLM/规则降级 |
| 视觉基础 | YOLO11、EasyOCR、焦点分析、惰性依赖、缓存 |
| 工具契约 | `ToolResult` 四态：`ok/degraded/skipped/error` |
| P2工具舱 | 7/7 ready：文本意图、情绪、OCR、图文一致、商品/Logo、主题漂移、评论异常 |
| 视觉复用 | `VisionContext` 按内容哈希缓存，一次推理供多个视觉工具复用 |
| 工具运行边界 | `LocalToolGateway`、带运行元数据的`ToolResult`、超时/错误归一化与输入指纹 |
| Capability Planner | 按模态、最低样本数、调用预算和单工具超时生成确定性计划 |
| Function Calling | 工具白名单、参数校验、重复调用拒绝、有限重试、计划预算/单工具与总时间预算、独立计数和结构化轨迹 |
| 证据/运行契约 | `EvidenceItem/EvidenceBundle/VerdictReport/RunMetadata`；覆盖、冲突、缺失要求和run event |
| Detection MCP | 官方MCP Python SDK v1低层Server；7工具可经stdio发现/调用，并有Local/MCP一致性和错误测试 |
| 法规RAG基础 | Chroma离线检索、确定性本地hash embedding、引用守卫和30题合成评测fixture |
| CreatorShift基础 | 同creator且严格早于目标时间的HistoryView；mean/max/EMA池化和可解释shift结果 |
| API | FastAPI `/health`、`/analyze` 起步接口 |
| 默认回归 | 合并前P2工作区`142 passed, 2 skipped`；合并并恢复全部P2工作后`171 passed, 2 skipped` |
| 真实视觉测试 | 显式 `vision_integration`，GPU路径此前实测 `2 passed` |

### 4.2 尚未完成

- 当前Agent没有真正使用全部7个P2工具：NLP和视觉Agent仍包含重复/旧逻辑。
- `AdCheckState` 仍以松散 `dict` 为主，没有接P1权威schema。
- Behavior Agent仍是关键词占位；CreatorShift研究内核已存在，但尚未接入PostRecord、真实历史特征或Agent。
- Judge仍使用固定 `0.6/0.25/0.15` 权重，没有证据充分性门、披露证据和校准。
- Function Calling、运行追踪和Capability Plan已经独立可测，但尚未接入LangGraph主链。
- Detection MCP Server已经可运行，但`MCPToolGateway`、主图MCP模式和本地回落尚未实现。
- 法规RAG当前只有合成fixture和离线检索基础；尚无真实权威法规语料、知识MCP Server或Judge后报告接入。
- A2A和平台URL适配尚未进入当前主代码。
- Web首页只是API入口说明，不是研究工作台。

### 4.3 2026-07-26合并与独立模块验收

- 合并前P2工作区基线：`142 passed, 2 skipped`。
- 仅含已提交P2与最新P1的合并态：`87 passed, 2 skipped`。
- 恢复全部合并前P2工作后的默认全量：`171 passed, 2 skipped`。
- P1数据、契约、编排、MCP、RAG与CreatorShift重点测试：`109 passed`。
- `pip check`：`No broken requirements found.`。
- 两个P1资产校验入口均为 `VALIDATION PASSED`：30条内容、30条补充标注，标签分布为明广5、暗广12、非广8、`out_of_scope` 3、`uncertain` 2。
- `compileall`、FastAPI健康入口导入调用、冲突标记扫描和工作区差异检查均通过。
- 合并前stash与恢复后工作区均为67个路径，逐路径集合完全一致。
- Detection MCP真实stdio测试覆盖：7工具发现、实际工具调用、未知/非法调用错误映射、Local/MCP关键字段一致。
- RAG 30题合成基线：Recall@5 `0.65`；直接题 `0.90`；跨文档题 `0.40`；无答案误引率 `0`。这些数字只验证检索工程，不是法律知识质量结论。
- CreatorShift测试覆盖跨creator、未来/同时间泄漏、重复帖子、历史不足、三种池化和可解释差异。
- 独立P2模块仍未读取P1 Schema；本次“双基线同时通过”只证明合并未破坏两侧现有行为，不能替代正式Schema适配和端到端主链验收。

## 5. P1数据资产事实

远端最新P1成果已经合并到本地P2，但“资产合并”不等于M1验收完成。

### 5.1 已有资产

- `data/schema/data_schema_v1.json`：JSON Schema Draft 2020-12，当前权威字段标准。
- `docs/data_schema.md`：schema交付说明。
- `data/synthetic/simulated_posts_v1.json`：30条全合成内容、参考标注和补充标注，只用于冒烟与校验。
- `scripts/data/validate_submission_assets.py`：标准库校验器。
- `data-tooling/`：独立数据工具舱，包含Schema v1.0/v1.1、同一份30条合成fixture、采集、清洗/去重、人工标注、隐私扫描、κ计算、金标构建、按博主划分等脚本。
- `data-tooling/validate_submission_assets.py`：合并时修复了迁移后仓库根目录计算错误，并新增真实子进程回归测试。
- `implicit-ad-agent/scripts/data/`：P1同时保留的一份脚本副本；当前与`data-tooling/`存在重复维护风险。
- 标注规范、补充标注schema、合规登记、数据卡和采集说明文档。

### 5.2 未过关项

- 最新P1最终树**没有跟踪**先前文档提到的598条微信公众号候选记录和6697个媒体文件；`implicit-ad-agent/data/` 当前没有已跟踪文件。旧文档中的这些数字是历史记录，不是当前仓库可验证资产。
- 若这些候选资产仍需使用，必须从合规的外部备份恢复或重新采集，再运行迁移、隐私扫描和Schema校验；不能把Git历史中曾存在过当作当前可用。
- 当前可验证数据只有30条合成fixture，远未达到M1候选池≥3000、金标≥1500的数量门槛。
- 真实候选数据的格式、ID、provenance、privacy、media引用和条款状态当前均无在库证据可验收。
- Schema v1.0与`data-tooling/schema/data_schema_v1_1.json`并存，尚未完成兼容评审与唯一运行版本冻结。
- `data-tooling/`与`implicit-ad-agent/scripts/data/`存在脚本副本，继续并行修改会产生漂移。
- 当前标注规范只有少量边界案例，未达到≥20条。
- 尚无可确认的双人独立标注、最终κ≥0.6、仲裁包、金标v1和零泄漏划分报告。
- 任何恢复或新采集的真实内容在进入Git公开范围前，都必须重新完成条款核验、脱敏、直接身份/联系方式/URL参数和疑似秘密扫描。

### 5.3 Schema使用原则

当前提交资产校验以`data/schema/data_schema_v1.json`为唯一权威来源。代码中的Pydantic模型、采集适配器和测试fixture都应从它映射，不再另造平行字段表。

`data-tooling/schema/data_schema_v1_1.json`只能作为兼容变更候选；如需支持B站或新增字段，必须完成v1.1评审、changelog和适配测试，不得直接修改v1.0后仍声称版本不变。

## 6. 目标数据流

```text
手工/JSON/URL
   → PlatformAdapter
   → PostRecord + CaptureStatus
   → Capability Planner
   → Function Calling
   → LocalToolGateway 或 MCPToolGateway
   → EvidenceBundle
   → Evidence Adequacy Gate
   → Commercial Intent
   → Disclosure Evidence
   → Calibrated Judge
   → 明广/暗广/非广/需复核
   → LegalRetriever（Chroma基线，LightRAG仅A/B候选）
   → VerdictReport
```

CreatorShift只允许读取 `published_at < target_time` 的同一创作者历史。缺历史返回 `unavailable/skipped`，不能按0分参与Judge。

## 7. 四人主责

| 方向 | 主责 |
| --- | --- |
| L：Agent系统与服务 | Supervisor、Function Calling、Judge、A2A、FastAPI、集成 |
| N：文本与知识层 | 文本工具、RAG、法规/平台规则、报告生成 |
| V：多模态与协议工具 | 视觉工具、VisionContext、MCP Server、视觉证据 |
| D：数据与研究评估 | P1收口、平台适配、CreatorShift数据、指标与论文 |

Owner负责交付，Reviewer必须来自另一方向。共享契约由L维护，但字段变更必须经数据Owner和至少一个工具Owner评审。

## 8. 接手后的执行顺序

1. 先审阅合并提交`98cb599`和当前工作区；确认无误后再删除`codex-pre-p1-merge-2026-07-26` stash。
2. 将现有未提交P2工作按契约、编排/Function Calling、MCP、RAG、CreatorShift和文档拆成独立可Review提交，不要把二进制文档或根目录临时Schema误混进代码提交。
3. 决定`data-tooling/`与`implicit-ad-agent/scripts/data/`的唯一维护来源；在决定前不要同时修改两份脚本。
4. 以P1 v1.0 Schema映射并冻结 `PostRecord / CaptureStatus`，复核现有Evidence/Verdict运行契约。
5. 为现有7工具增加正式EvidenceAdapter，将NLP/视觉Agent切到ToolGateway与现有Function Calling。
6. 接入Evidence Adequacy Gate、DisclosureEvidence和新Judge，再重构LangGraph主链。
7. 将现有Detection MCP、法规RAG和CreatorShift内核分别接到统一分析服务；保持local路径为默认和降级实现。
8. 从合规外部来源恢复或重新建立真实候选池，完成迁移、隐私扫描、平台补采、双标、κ、仲裁、金标与零泄漏划分。
9. M1与M2.5通过后再启动真实法规语料、知识MCP、A2A和网页工作台的端到端验收。

文件级细节和短期验收见 `docs/现有代码修改大纲.md`。

## 9. 常用验证命令

```powershell
cd implicit-ad-agent

# 安装基础依赖与本轮可选模块
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,rag]"

# 默认零网络回归
.\.venv\Scripts\python.exe -m pytest -q

# P1数据与本轮重点模块
.\.venv\Scripts\python.exe -m pytest tests\data tests\contracts tests\orchestration tests\protocols\mcp tests\rag tests\creator_shift -q

# Detection MCP Server（stdio）
.\.venv\Scripts\python.exe -m impad.protocols.mcp.detection_server

# 真实视觉（显式opt-in）
.\.venv\Scripts\python.exe -m pytest -m vision_integration -q

# 固定工具演示
.\.venv\Scripts\python.exe run_tools_demo.py

# 当前API
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

在仓库根目录运行两个P1零Key校验入口：

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
```

当前预期：全量`171 passed, 2 skipped`，重点模块`109 passed`，两个P1校验器均输出`VALIDATION PASSED`。每次跨阶段集成都要同时跑P1资产校验与P2默认回归。

## 10. 不要重踩的坑

- Windows中文路径下优先使用 `python -m ...` 或显式 `.venv\Scripts\python.exe`，不要依赖损坏的launcher exe。
- 中文文件用UTF-8读取和写入。
- 默认测试不得读取真实API Key、联网或加载真实视觉模型。
- `json_mode + 英文字段名 + Pydantic校验` 是国产OpenAI兼容端点的现有稳定路径；Function Calling只用于工具选择，不等于必须改掉最终结构化输出策略。
- 工具跳过、图片缺失、历史不足不是负向证据。
- RAG无可靠检索结果时返回空引用，不得补写条款号。
- 当前RAG语料是明确标记的合成测试fixture，不得在报告或论文中当作真实法规评测。
- `mcp`与`chromadb`是可选依赖；契约层不得因未安装可选依赖而无法导入。
- CreatorShift当前输出是简单历史基线证据，不是校准概率，也不能直接决定暗广。
- A2A必须是独立Agent服务间的真实任务交换；同一进程内函数互调不能算A2A验收。
- 不要继续引用“仓库现有598条候选和6697个媒体”作为当前事实；最新P1树已不包含这些资产。
- 不要只改`data-tooling/`或`implicit-ad-agent/scripts/data/`其中一份后假设另一份会自动同步。
- 不把真实用户名、头像、手机号、群二维码、精确URL参数、密钥或内部地址提交到公开仓库。
- 不使用测试集调Prompt、关键词、阈值或CreatorShift窗口。
- 当前工作区有未提交修改，禁止 `git reset --hard`、覆盖式checkout或批量清理。

## 11. 文档职责

- `README.md`：面向新开发者和最终开源用户的入口。
- `HANDOFF.md`：当前事实、分支、风险和下一步。
- `docs/隐性广告识别项目_说明书.md`：架构、模块、数据流、错误处理、评估与边界。
- `docs/隐性广告识别项目_分阶段计划表.md`：日期、Owner、里程碑和降级决策。
- `docs/现有代码修改大纲.md`：当前文件如何迁移、P1如何衔接及短期代码顺序。

新事实优先更新HANDOFF；稳定设计更新说明书；日期与Owner变化更新阶段表；公开使用方法更新README。
