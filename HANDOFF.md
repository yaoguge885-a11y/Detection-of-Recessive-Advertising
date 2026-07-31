# HANDOFF：隐性广告识别项目

> 面向下一位接手开发者的事实交接。最后更新：2026-07-26（M1代码治理收口与真实数据试运行后）。
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
- P1合并和本轮P2.5改造都只存在于本地，没有推送远端P2。
- 合并前的67个未提交/未跟踪P2文件已逐路径恢复；本轮又在同一工作树加入P1输入适配、证据适配、充分性门和主图接入。当前改动均未暂存、未提交，不得覆盖、清理或重置。
- 安全备份仍保留在 `stash@{0}`：`codex-pre-p1-merge-2026-07-26`，对象为 `6c0bfedd4c8d990a5ffccd8a089bb3ee9bafcba3`。确认工作区无误前不要删除。

不要从最新 `main` 重新建空目录复制文件，也不要再次把P1整分支覆盖到P2。后续开发直接从当前P2继续，并将现有未提交模块按职责拆成可Review提交。

## 4. 当前代码状态

主程序目录：`implicit-ad-agent/`。

### 4.1 已完成

| 模块 | 事实状态 |
| --- | --- |
| LangGraph P2.5主链 | `Supervisor归一化/规划 → NLP/视觉/行为工具组 → EvidenceBundle → Judge` 可运行 |
| 运行输入契约 | `PostRecord/CaptureStatus`已实现；解析后的历史强制同creator、不得包含目标帖自身且严格早于目标帖；时间未知的历史不进入行为工具 |
| P1/手工输入适配 | P1记录先经权威JSON Schema校验；手工/旧输入映射到同一PostRecord |
| 文本能力 | 关键词唯一事实来源、6维权重和确定性文本工具；默认主图不读取Key、不联网 |
| 视觉基础 | YOLO11、EasyOCR、焦点分析、惰性依赖、缓存 |
| 工具契约 | `ToolResult` 四态：`ok/degraded/skipped/error` |
| P2工具舱 | 7/7 ready：文本意图、情绪、OCR、图文一致、商品/Logo、主题漂移、评论异常 |
| 视觉复用 | `VisionContext` 按内容哈希缓存，一次推理供多个视觉工具复用 |
| 工具运行边界 | `LocalToolGateway`、带运行元数据的`ToolResult`、超时/错误归一化与输入指纹 |
| Capability Planner | 按模态、最低样本数、调用预算和单工具超时生成确定性计划 |
| Function Calling | 工具白名单、顶层/嵌套未知参数拒绝、畸形调用记录、重复调用拒绝、有限重试、跨专家共享运行级预算和结构化轨迹；已接入现有Agent主图 |
| 证据适配 | 7种ToolResult统一转换为EvidenceItem；skipped/error/absence不生成负向证据 |
| 证据/运行契约 | `EvidenceItem/EvidenceBundle/VerdictReport/RunMetadata`；覆盖、冲突、缺失要求和run event |
| 充分性门与Judge | 已移除`0.6/0.25/0.15`投票；先检查采集/工具/冲突，再分离商业意图与披露；多图片未全覆盖、OCR实际不可用或未知披露均转需复核 |
| Detection MCP | 官方MCP Python SDK v1低层Server；7工具可经stdio发现/调用，并有Local/MCP一致性和错误测试 |
| 法规RAG基础 | Chroma离线检索、确定性本地hash embedding、引用守卫和30题合成评测fixture |
| CreatorShift基础 | 同creator且严格早于目标时间的HistoryView；mean/max/EMA池化和可解释shift结果 |
| API | FastAPI `/health`、`/analyze` 起步接口；当前确定性P2.5主图默认不需Key，尚未拆成统一分析服务与正式路由层 |
| 默认回归 | 当前零Key/零网络全量`227 passed, 2 skipped`；P2.5准入重点`116 passed` |
| 真实视觉测试 | 显式 `vision_integration`，GPU路径此前实测 `2 passed` |

### 4.2 P2.5缺口关闭状态

| 原4.2缺口 | 当前事实 |
| --- | --- |
| Agent未使用全部7工具 | 已关闭：NLP组调用文本意图/情绪/评论，视觉组调用OCR/图文一致/商品Logo，行为组调用主题漂移；统一走Restricted Function Calling |
| State未接P1 | 已关闭：主图State保存PostRecord、CaptureStatus、CapabilityPlan、ToolResult、EvidenceBundle、RunMetadata和VerdictReport |
| Behavior为关键词占位 | P2.5部分关闭：已切到正式topic_drift工具；CreatorShift真实特征、模型和Agent接入按阶段留在P4 |
| Judge固定权重 | P2.5已关闭：固定专家投票已删除，加入充分性门、商业意图/披露分离和保守确定性Judge；经验校准按阶段留在P4 |
| Function Calling/追踪未接主图 | 已关闭：现有专家工具组写入同一run_id、ToolResult和run event |
| MCPToolGateway/主图MCP回落 | 按阶段留在P3，不属于P2.5准入门 |
| 真实法规语料/知识MCP/报告接入 | 按阶段留在P3 |
| A2A和平台URL | 按阶段留在P5 |
| Web研究工作台 | 按阶段留在P5；当前首页仍只是API入口说明 |
| M1审计与事实门 | 代码侧已关闭：新增安全聚合审计、统一M1门禁和结构化报告；不足、缺失或非正式证据均不能误通过 |
| M1数据治理工具 | 代码侧已关闭：保守迁移、完整Schema、隐私人工审批门、结构化κ、Gold规则和创作者/content-group连通切分已具备回归测试 |

### 4.3 尚未完成

- **M1数据关口仍未通过**：本地外部数据已完成只读审计，只有282个唯一候选、15个创作者；无正式Gold、第二轮盲标、无泄漏切分、条款完成证明或隐私人工审批。P2.5及M1工具代码已具备开始P3工程开发的接口，但不能把这写成“P3正式阶段已通过”。
- **P3**：统一`services/analyze.py`和API schema/routes、MCPToolGateway与本地回落、真实法规语料和Knowledge MCP、Judge后RAG/报告接入、持久化run查询与可观测性。
- **P4**：CreatorShift真实历史特征/模型/Agent接入，Judge验证集校准、阈值与risk-coverage实验。
- **P5**：A2A远程专家、小红书/B站URL适配、研究工作台和local/A2A对照。

### 4.4 2026-07-26合并与独立模块验收

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
- 该历史验收时独立P2模块仍未读取P1 Schema；“双基线同时通过”当时只证明合并未破坏两侧行为。正式Schema适配和端到端主链验收已在下方4.5另行完成。

### 4.5 2026-07-26 P2.5代码准入验收

- P1内容记录经`data/schema/data_schema_v1.json` Draft 2020-12校验后映射为PostRecord；P1形态的畸形输入不会降级成宽松手工输入，未知字段和缺少必填字段均有失败测试。
- 手工/旧输入与P1输入共用PostRecord；远程URL不伪装成本地图片能力。
- 七工具参数由PostRecord统一生成并用严格Pydantic schema验证；未知顶层/嵌套字段和畸形调用均拒绝并记录，全模态规划测试覆盖7/7工具，不在默认测试加载视觉模型。
- EvidenceAdapter覆盖7/7 ToolResult；`skipped/error/absence/insufficient`均不生成EvidenceItem。
- Evidence Adequacy Gate覆盖缺文本、提供但不可用的图片、图片工具错误、工具报告的图文冲突、多图片覆盖不足、OCR能力不可用和视频/音频等未支持媒体；缺失的可选历史/评论不记负分。
- Judge严格执行：商业意图不足→非广；意图成立+已披露→明广；意图成立+未披露且披露面已完整采集并成功OCR→暗广；未知披露/冲突/关键缺失→需复核。
- P2.5重点命令：`116 passed`；当前全量：`227 passed, 2 skipped`；`pip check`、`compileall`、FastAPI健康/分析入口和两套P1资产校验均通过。
- 以上测试证明代码接口和离线工程行为，不证明真实数据规模、论文分类精度、经验校准或真实法规质量。

### 4.6 2026-07-26 M1代码治理与真实数据试运行

- 外部输入 `C:\Users\31729\Desktop\dataset_full` 全程只读；它是本地示例路径，不是仓库依赖或可公开数据集。
- 安全审计：304行、282个唯一帖子、22个重复行、15个创作者、单一WeChat平台；6,697个唯一媒体引用均可定位；来源条款完成记录为0。
- 保守迁移：304条输入全部生成v1.0记录，其中135条正常、169条因采集/LLM状态需复核；未虚构条款日期、隐私安全状态或感知哈希。
- 完整Draft 2020-12校验：304/304有效。可空日期与相对报告路径在真实试跑中暴露并修复，均有回归测试。
- 隐私门禁：无人工审批文件时304条全部为`interim`，`public=0`；规则扫描产生8,177个模式命中，这只是待复核的规则结果，不等于8,177项已确认隐私泄漏。安全报告不保存明文匹配、正文、来源URL、创作者或标注者字段。
- pilot一致性：两份文件有36个共同有效标注ID，22对为双方都采用三元标签的κ样本；κ=1.0、95% bootstrap区间[1.0, 1.0]，但样本中暗广为0且`formal_second_round=false`，因此只能作工具试跑，不能作M1正式κ或Gold证据。
- 标注指南新增24个结构化边界案例，达到指南数量项；当前Dataset Card明确记录数据、隐私、条款、切分和规模限制。
- M1门禁退出码为2且`passed=false`：指南通过；候选规模、Gold和Dataset Card失败；正式一致性与合规需复核；切分证据缺失。
- 当前验收：数据测试`62 passed`；默认全量`260 passed, 2 skipped`；`pip check`、`compileall`、两套P1资产校验和6组镜像文件字节一致性均通过。

### 4.7 2026-07-31 分置信度自动判断标注系统（co-pilot-auto-judge）

- 设计文档：`docs/co-pilot-auto-judge-design.md`（v1.1，本地推理 Ollama + `qwen3.5:9b`）。
- 核心模块：`data-tooling/annotation/auto_judge.py` —— 三级自动判断（≥0.85 自动保存 / 0.55–0.84 建议 / <0.55 纯人工）、Ollama `/api/chat` JSON 推理、关键词失败回退、自动保存记录构建。
- 配套工具：`batch_pre_annotate.py`（批量预标注，输出 auto/suggest/stats 三文件）、`manual_review_annotate.py`（新增 `--auto-threshold`/`--ollama-backend`/`--ollama-model` 等）、`flet_annotator.py`（新增自动模式开关、阈值滑块、Toast、底部状态栏）。
- `impad/llm.py` 新增 `get_ollama_llm()` 工厂（OpenAI 兼容端点指向本地 Ollama）。
- 自动保存审计约定：`annotator_id="system"`、`annotation_method="auto_accepted"`、`_llm_suggestion` 记录模型与是否自动采纳；**自动标注记录不参与双人 κ 计算**。
- 关键环境事实：Ollama 服务在本机运行（`http://localhost:11434`），需 `ollama pull qwen3.5:9b`（约 6.6GB）后方可走 LLM 判定路径；模型未就绪时自动降级为关键词规则（明广 0.90 自动保存 / 暗广 0.45 强制人工 / 无信号纯人工）。
- 单元测试：`data-tooling/annotation/tests/test_auto_judge.py`（21 passed，mock 掉 Ollama，不依赖模型）。
- 已实测：批量预标注端到端跑通（含 Ollama 失败回退自动保存明广记录）；CLI 自动保存流程验证通过；GUI 模块导入与集成正常。
- Windows GBK 控制台兼容：三个 CLI 脚本均强制 `sys.stdout.reconfigure(encoding="utf-8")`。
- 修复 `flet_annotator.py` 原有 4 处无法解析的延迟导入（`scripts.data.annotation.*`/`data_tooling.annotation.*` → 同目录直接导入）。

## 5. P1数据资产事实

远端最新P1成果已经合并到本地P2，但“资产合并”不等于M1验收完成。

### 5.1 已有资产

- `data/schema/data_schema_v1.json`：JSON Schema Draft 2020-12，当前权威字段标准。
- `docs/data_schema.md`：schema交付说明。
- `data/synthetic/simulated_posts_v1.json`：30条全合成内容、参考标注和补充标注，只用于冒烟与校验。
- `scripts/data/validate_submission_assets.py`：标准库校验器。
- `data-tooling/`：独立数据工具舱，包含Schema v1.0/v1.1、同一份30条合成fixture、采集、清洗/去重、人工标注、隐私扫描、κ计算、金标构建、按博主划分等脚本。
- `data-tooling/m1_readiness.py`及运行镜像：安全聚合审计与M1统一事实门。
- `docs/annotation_guide_v1.md`：24个边界案例及双标/仲裁规则。
- `docs/dataset_card_current.md`和`data/reports/m1/`：当前外部数据的事实卡、聚合审计、Schema、隐私、pilot一致性与门禁报告。
- `data-tooling/validate_submission_assets.py`：合并时修复了迁移后仓库根目录计算错误，并新增真实子进程回归测试。
- `implicit-ad-agent/scripts/data/`：P1同时保留的一份脚本副本；当前与`data-tooling/`存在重复维护风险。
- 标注规范、补充标注schema、合规登记、数据卡和采集说明文档。

### 5.2 未过关项

- 仓库仍只跟踪30条合成fixture；真实数据只存在于外部本地目录，不得提交正文、媒体、ID映射或私有审查材料。
- 外部数据已验证为282个唯一候选，仍远低于M1候选池≥3000；当前没有可计为正式Gold的记录，低于≥1500。
- 外部数据格式和媒体引用已完成试跑；条款核验为0，隐私人工审批未完成，因此所有记录最多停留在`interim`。
- Schema v1.0与`data-tooling/schema/data_schema_v1_1.json`并存，尚未完成兼容评审与唯一运行版本冻结。
- `data-tooling/`与`implicit-ad-agent/scripts/data/`仍有脚本副本；当前6组M1文件字节一致并有镜像测试，但长期仍应决定唯一维护来源。
- 标注指南已有24个边界案例；这只关闭指南数量项，不替代真实双标和Gold。
- 尚无可确认的第二轮独立盲标、仲裁包、Gold v1和零泄漏正式切分报告；pilot κ不得冒充正式证据。
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

1. 先审阅合并提交`98cb599`、P2.5计划`docs/superpowers/plans/2026-07-26-p2-5-p3-readiness-gate.md`和当前工作区；确认无误后再删除`codex-pre-p1-merge-2026-07-26` stash。
2. 将现有未提交工作按P2工具元数据、独立契约/编排模块、P2.5输入与证据链、MCP、RAG、CreatorShift和文档拆成可Review提交；不要混入二进制文档或根目录临时Schema。
3. 决定`data-tooling/`与`implicit-ad-agent/scripts/data/`的唯一维护来源；在决定前每次修改都必须同步镜像并运行字节一致性测试。
4. P2.5和M1工具代码准入已经完成，不要重写7工具或放宽事实门；P3工程开发从统一分析服务、MCPToolGateway、Knowledge MCP/真实RAG接入和正式报告链开始。
5. 同步推进M1外部工作：补足到≥3000个唯一合规候选，完成来源条款和人工隐私审批、第二轮盲标、仲裁、≥1500 Gold及创作者/content-group零泄漏切分。
6. 只有M1事实门通过后，才能把项目阶段正式标记为P3通过；当前“可开始P3开发”仅指代码接口已就绪。
7. CreatorShift真实模型与Judge经验校准留在P4；A2A、URL适配和Web工作台留在P5，不提前混进P3首个提交。

文件级细节和短期验收见 `docs/现有代码修改大纲.md`。

## 9. 常用验证命令

```powershell
cd implicit-ad-agent

# 安装基础依赖与本轮可选模块
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,rag]"

# 默认零网络回归
.\.venv\Scripts\python.exe -m pytest -q

# P2.5代码准入重点
.\.venv\Scripts\python.exe -m pytest tests\contracts tests\adapters tests\orchestration tests\test_agents.py tests\test_graph_evidence_flow.py -q

# P1数据、协议、RAG与CreatorShift独立模块
.\.venv\Scripts\python.exe -m pytest tests\data tests\protocols\mcp tests\rag tests\creator_shift -q

# M1数据治理聚焦回归
.\.venv\Scripts\python.exe -m pytest tests\data -q

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

当前预期：全量`260 passed, 2 skipped`，M1数据治理`62 passed`，P2.5代码准入重点历史验收为`116 passed`，两个P1校验器均输出`VALIDATION PASSED`。每次跨阶段集成都要同时跑P1资产校验、M1数据测试与默认全量回归。

M1真实数据审计、迁移、Schema、隐私、pilot一致性和门禁的PowerShell命令见`data-tooling/README.md`。当前门禁预期退出码为2；在外部证据补齐前，不要把它改成成功预期。

## 10. 不要重踩的坑

- Windows中文路径下优先使用 `python -m ...` 或显式 `.venv\Scripts\python.exe`，不要依赖损坏的launcher exe。
- 中文文件用UTF-8读取和写入。
- 默认测试不得读取真实API Key、联网或加载真实视觉模型。
- 当前P2.5主图默认使用确定性工具选择，不读取`.env`中的Key；后续若在P3重新启用LLM选择，`json_mode + 英文字段名 + Pydantic校验`仍是国产OpenAI兼容端点的输出兼容策略。
- 工具跳过、图片缺失、历史不足不是负向证据。
- RAG无可靠检索结果时返回空引用，不得补写条款号。
- 当前RAG语料是明确标记的合成测试fixture，不得在报告或论文中当作真实法规评测。
- `mcp`与`chromadb`是可选依赖；契约层不得因未安装可选依赖而无法导入。
- CreatorShift当前输出是简单历史基线证据，不是校准概率，也不能直接决定暗广。
- A2A必须是独立Agent服务间的真实任务交换；同一进程内函数互调不能算A2A验收。
- 不要把外部本地目录中的282个唯一候选和6,697个媒体引用说成仓库已跟踪资产或可公开数据。
- 不要把pilot的κ=1.0说成正式第二轮结果：它只有22对有效三元样本、没有暗广样本，且明确标记为非正式。
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
