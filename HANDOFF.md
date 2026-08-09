# HANDOFF：隐性广告识别项目

> 面向下一位接手开发者的事实交接。最后更新：2026-08-09（P5.7安全工程验收与事实门同步后）。
> 先读本文件，再读 `docs/隐性广告识别项目_说明书.md`、`docs/隐性广告识别项目_分阶段计划表.md` 和 `docs/superpowers/` 下已确认的设计/实施记录。

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

- 当前本地整合分支：`codex/p1-m1-into-p3`，工作树位于 `.worktrees/codex-p1-m1-into-p3`。
- 整合基线：`origin/P3` 的 `ba0ab5802b75ddb58967bbf66b83eb360c395e77`。
- P1来源：`origin/P1-·-数据地基与标注规范` 的 `43c59ac11770ea29b87c0612da31ab02d579e165`。
- 本地合并提交：`ca8fc2d`；Schema v1.2运行时兼容提交：`1db5160`。已用 `git merge-base --is-ancestor` 验证P3与P1来源均为当前分支祖先。
- 该分支和提交均仅在本地，尚未推送，也尚未合并回`P3`。原始`P3`工作区保持在`ba0ab58`。

不要覆盖式复制P1或P3目录。后续从当前整合分支继续验证，确认后再决定是否合并回P3；保留无关修改并按职责拆成可Review提交。

## 4. 当前代码状态

主程序目录：`implicit-ad-agent/`。

### 4.1 已完成

| 模块 | 事实状态 |
| --- | --- |
| LangGraph证据主链 | `Supervisor归一化/规划 → NLP/视觉/行为工具组 → CreatorShift → EvidenceBundle → Judge` 可运行 |
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
| MCP运行模式 | `MCPToolGateway`保持ToolResult契约；stdio请求默认30秒超时，失败/超时均本地回落并记录`mcp_transport_fallback`与fallback_count |
| 法规RAG基础 | 小规模官方法规语料、Chroma/hash向量召回、确定性词法召回、RRF重排分数、引用守卫和版本绑定离线报告 |
| 知识与报告 | Knowledge MCP、Judge后LawEvidence、Markdown报告和JSON run持久化已接入 |
| CreatorShift工程准入 | 同creator且严格早于目标时间的HistoryView；mean/max/EMA；复用6维关键词特征的独立图节点；充分历史生成中性证据，不足/缺时间保留非数值状态 |
| 独立合并历史论文基线 | `baseline/`已实现单帖与单帖+mean/max/EMA历史池化的固定Logistic Regression、M1/split fail-closed门、共同cohort、版本/哈希和隐私安全聚合报告；合成fixture专项`54 passed` |
| 统一分析服务 | `AnalysisService`统一主图、Judge后法规检索、报告和run持久化；API与CLI共用；批量逐条复用同一`analyze()`并隔离失败 |
| API与run查询 | `/api/v1/analyze`、`/api/v1/analyze/batch`、URL预览/确认、`/api/v1/runs/{run_id}`、`/api/v1/capabilities`及兼容`/analyze`共用服务 |
| URL服务边界 | HTTPS/authority/port/本地地址校验、显式PlatformAdapter注册、无网络预览、可审计修正和一次性确认已实现；默认注册表为空，不声称支持真实平台 |
| P5.2开发者研究工作台 | 同源、无构建的`/workbench`已接入既有API：单条、混合有效/无效批量、能力门控URL预览/确认、完整run九区渲染、复制/UTF-8下载；默认URL适配器为空且fail closed |
| P5.7安全工程门 | 重定向逐跳复核、DNS私网/变化阻断与IP固定、URL/输出脱敏、提示注入隔离、媒体路径边界、MCP/假A2A权限与超时、生成物扫描均已通过离线验收；未请求真实平台 |
| 评估基础 | 三分类Macro-F1、暗广P/R/F1、AUPRC、ECE/Brier、混淆/错误桶；P4新增固定种子bootstrap区间、显式拒答前预测和risk-coverage工程报告 |
| 默认回归 | 2026-08-09 P5.7收口全量`495 passed, 2 skipped, 1 warning`；P5.7聚焦`144 passed`；warning仍为既有Starlette/httpx弃用提示 |
| 真实视觉测试 | 显式 `vision_integration`，GPU路径此前实测 `2 passed` |

### 4.2 P2.5缺口关闭状态

| 原4.2缺口 | 当前事实 |
| --- | --- |
| Agent未使用全部7工具 | 已关闭：NLP组调用文本意图/情绪/评论，视觉组调用OCR/图文一致/商品Logo，行为组调用主题漂移；统一走Restricted Function Calling |
| State未接P1 | 已关闭：主图State保存PostRecord、CaptureStatus、CapabilityPlan、ToolResult、EvidenceBundle、RunMetadata和VerdictReport |
| Behavior为关键词占位 | 工程侧已关闭：topic_drift继续走七工具舱，独立CreatorShift节点已接入主图；当前仅为确定性关键词历史基线，学习模型与真实特征仍待P1/M4 |
| Judge固定权重 | P2.5已关闭：固定专家投票已删除，加入充分性门、商业意图/披露分离和保守确定性Judge；经验校准按阶段留在P4 |
| Function Calling/追踪未接主图 | 已关闭：现有专家工具组写入同一run_id、ToolResult和run event |
| MCPToolGateway/主图MCP回落 | 已关闭：主图支持local/mcp，失败回落本地并记录hybrid与fallback_count |
| 官方法规基线/知识MCP/报告接入 | 工程MVP已关闭：小规模官方条款、Knowledge MCP、Judge后检索、引用报告和run查询可运行；不代表完整法律覆盖 |
| A2A和平台URL | P5.1已关闭批量与URL服务契约；真实小红书/B站适配和A2A仍留在P5后续 |
| Web研究工作台 | P5.2工程实现并已验证：`/workbench`同源静态资源、无Node构建、单条/批量/URL能力门、完整run视图、复制/下载、键盘与响应式布局；团队UAT仍未完成 |
| M1审计与事实门 | 代码侧已关闭：新增安全聚合审计、统一M1门禁和结构化报告；不足、缺失或非正式证据均不能误通过 |
| M1数据治理工具 | 代码侧已关闭：保守迁移、完整Schema、隐私人工审批门、结构化κ、Gold规则和创作者/content-group连通切分已具备回归测试 |

### 4.3 尚未完成

- **M1数据关口仍未通过**：用户提供ZIP已完成本地审计，权威JSONL有2,901个唯一候选、108个创作者，距3,000还差99；无正式Gold、第二轮盲标、无泄漏切分、条款完成证明、隐私人工审批或Dataset Card审批。M1工具与P3接口可运行，但不能把这写成“M1已验收”或“P3研究实验已就绪”。
- **P3非数据依赖工程范围已完成，但正式M3仍受M1事实证据约束**：统一服务、API/CLI、MCP超时回落、Knowledge MCP、混合检索、版本绑定报告、run查询、追踪和分类错误分析已通过离线测试；远程MCP可达性、法规覆盖质量和真实数据效果尚未证明。
- **P4研究门仍未通过**：独立`baseline/`历史融合分类工程包已完成并以合成fixture专项`54 passed`验证；真实纵向特征/学习模型、Judge验证集校准、阈值选择、消融、置信区间和增益结论仍等待M1 Gold与无泄漏split。正式Gold=0且M1未通过，暂无真实训练/test指标、CreatorShift增益或M4验收。P4正式实验协议已冻结在`docs/superpowers/specs/2026-08-08-p4-experiment-protocol-design.md`：五方法共同cohort、dev调参/test一次性评估、固定种子与输入哈希、10,000次creator-cluster bootstrap、text→vision→history→full消融，以及无增益止损规则均已预先指定；协议冻结不等于区间估计已经实现或M4通过。
- **P5.2仅完成工程门，不是P5/M5完成**：批量分析、URL安全边界、显式适配器注册、预览/确认和修正审计，以及同源无构建研究工作台均已实现；四人团队UAT、真实小红书/B站适配、A2A远程专家、local/A2A对照、P5.3～P5.7和完整P5安全验收均未完成，M5未通过。

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
- P2.5重点命令：`116 passed`；该日当时全量：`227 passed, 2 skipped`；`pip check`、`compileall`、FastAPI健康/分析入口和两套P1资产校验均通过。当前代码基线见4.7。
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
- 该日验收：数据测试`62 passed`；当时默认全量`260 passed, 2 skipped`；`pip check`、`compileall`、两套P1资产校验和6组镜像文件字节一致性均通过。当前代码基线见4.7。

### 4.7 2026-07-27 P3合并与统一CLI收口验收

- P3实现提交`c3ed82d`经合并提交`1aad3f2`进入当前P2分支。
- `AnalysisService`统一本地/MCP主图、Judge后法规检索、Markdown报告和JSON run持久化。
- FastAPI版本化分析、能力和run查询接口与`run_demo.py`共用同一服务；`--llm`仅保留为零Key兼容参数。
- P3聚焦测试`16 passed`；默认全量`276 passed, 2 skipped`；`pip check`、`compileall`和两个P1资产校验器通过。
- 上述结果证明P3工程MVP和离线契约行为，不证明M1数据门、远程MCP部署、法规覆盖质量、论文分类精度或CreatorShift增益。

### 4.8 2026-07-27 P3非数据依赖工程收尾验收

- 默认`LegalRetriever`改为Chroma向量召回与确定性词法召回的RRF融合；`rerank_score`可追踪，最终引用继续通过`CitationGuard`逐字核验。
- 评测问题集显式绑定`corpus_version`；旧顶层数组schema和语料版本错配会失败，不再允许把合成30题误跑到官方小语料。
- `scripts/evaluate_p3.py`提供`retrieval`和`classification`两个零Key/零网络子命令，直接按脚本路径运行已有subprocess回归。
- `StdioDetectionMCPClient`默认超时30秒；超时与传输失败都通过现有Gateway本地降级并记录`mcp_transport_fallback`。
- 确定性本地/MCP工具运行仍保持`token_usage={}`、`cost_usd=null`，不伪造成本采集。
- 证据快照：
  - `data/reports/p3/retrieval_synthetic_30.json`：30题，Recall@1 `0.75`、Recall@3/5 `1.0`、跨文档Recall@5 `1.0`、误引率`0`。
  - `data/reports/p3/retrieval_official_15.json`：2份官方文档、7个sections、15题，Recall@1 `0.85`、Recall@3/5与MRR@5 `1.0`、误引率`0`。
  - `data/reports/p3/classification_fixture.json`：6行合成夹具，错误ID `4/5/6`、复核ID `4`。
- P3聚焦`45 passed`；该次全量`299 passed, 2 skipped, 1 warning`。warning为既有Starlette/httpx弃用提示，无新增skip；最新全量见4.9。
- 这些指标仅证明小型语料和合成夹具的工程行为；正式M3仍等待M1 Gold、双标/仲裁、无泄漏切分、条款和隐私证据。

### 4.9 2026-07-30 P4工程准入验收

- 新增独立`creator_shift`图节点，始终记录历史充分性；目标时间或目标文本缺失、无历史和短历史分别保留`unavailable/insufficient`，缺失文本历史会被排除，不生成0分。
- 运行时复用`compute_keyword_weights()`的6维确定性特征，默认EMA（`alpha=0.5`）；mean/max/EMA仍通过统一内核评测，不新增关键词事实源。
- 充分历史只生成一条`polarity=neutral`的CreatorShift证据；配对图测试验证加入历史前后Judge的标签、置信度、商业意图和披露状态不变。
- `data/reports/p4/creator_shift_fixture.json`绑定`synthetic-creator-shift-v1`和SHA-256夹具哈希：4个合成案例、mean/max/EMA共12条结果，6条sufficient、3条insufficient、3条unavailable。
- `data/reports/p4/calibration_fixture.json`绑定`synthetic-calibration-v1`：6条显式拒答前预测、500次固定种子bootstrap和完整risk-coverage曲线。
- P4工程准入聚焦`61 passed`；当前全量`326 passed, 2 skipped, 1 warning`；`pip check`与`compileall`通过。warning仍为既有Starlette/httpx弃用提示。
- 以上只证明运行时接线、确定性夹具、指标计算和报告可复现；不证明真实CreatorShift增益、Judge校准、最终阈值、论文统计结论或M4通过。

### 4.10 2026-07-30 P5.1服务工程准入验收

- `AnalysisService.analyze_batch()`支持1～50条顺序批处理；每条成功都复用权威单条`analyze()`路径，输入归一化错误与执行错误分别安全映射为`invalid_input`和`analysis_failed`，单条失败不阻断后续记录。
- FastAPI新增`POST /api/v1/analyze/batch`；即使某一条缺少必填API字段，也返回该条失败和其余条目的结果，不把整批误退成422。空批次和超过50条仍在请求边界拒绝。
- 新增`impad.adapters.platforms`：只接受HTTPS、拒绝凭据/非默认端口/本地与非公网IP，按显式host注册解析PlatformAdapter；默认注册表为空，不调用网络、不声明任何真实平台可用。
- URL流程新增`POST /api/v1/import/url/preview`和`POST /api/v1/import/url/confirm`。预览不运行分类；query/fragment不进入展示URL，敏感值通过结构化字段扫描防止进入PostRecord；确认只允许白名单字段、保留适配器审计元数据并记录实际发生的更正。
- 进程内预览存储采用原子`claim/release/consume`：同一preview并发只能有一次分析；校验或分析失败会释放供重试，成功后一次性消费。它仍不是持久队列或分布式任务系统。
- 两轮独立代码审查均无Critical；审查指出的并发重复确认、敏感值转义/短值误判、内部ValueError分类和API单条结构隔离均已补回归并修复。
- P5.1聚焦回归`58 passed, 1 warning`；当前默认全量`380 passed, 2 skipped, 1 warning`；`pip check`、`compileall`和两套P1资产校验通过。warning仍为既有Starlette/httpx弃用提示。
- 本验收不包含真实小红书/B站请求、DNS/重定向安全、Web工作台、A2A、local/A2A对照、账号/RBAC/高并发或完整P5安全测试；不代表P5/M5、M1或M4通过。

### 4.11 2026-07-31 P5.2研究工作台工程门复核

- `GET /workbench`由既有FastAPI同源提供，只有仓库资产；无Node构建、远程资产、浏览器存储或后台网络采集。CSP限制为同源，`Cache-Control: no-store`、`nosniff`和`no-referrer`保持生效。
- 页面覆盖单条分析、批量JSON/UTF-8文件、能力门控URL预览/确认；默认平台注册表为空时URL输入与提交按钮禁用，且在能力未就绪/失败时也fail closed。单条、批量和确认后的URL分析都读取持久化`run_id`并渲染结论、覆盖/缺失、证据、CreatorShift、历史、法规、轨迹、报告和raw JSON九区。
- 2026-07-31新鲜工程门：`pip check`输出`No broken requirements found.`；`compileall -q impad tests scripts app.py run_demo.py run_tools_demo.py`退出0；P5.2聚焦`28 passed, 1 warning in 3.18s`；全量`390 passed, 2 skipped, 1 warning in 12.13s`。唯一warning是既有Starlette/httpx TestClient弃用提示；两个skip仍为显式视觉路径。
- 两个P1校验器均输出`VALIDATION PASSED`（各30条content、30条supplement）。这是提交资产一致性验证，**不**代表M1通过。
- 运行资产扫描未发现`innerHTML`等禁止sink或远程workbench资产；可复制的fail-closed密钥扫描精确允许旧P5.1计划文件内两处指定历史fixture，并断言为**2 expected historical fixture matches, 0 unexpected matches**。少于/多于两处或任何其他匹配都会失败。`git diff --check`通过。
- Task 7真实浏览器证据（实施提交`fde1e4a`）：单条run为`run_bf717e85fd934afc81d227edf3720ab6`；混合批量为2成功/1失败/3总计；默认URL禁用；键盘ArrowLeft/Right/Home/End可用；剪贴板复制成功，实际UTF-8 `.md`和`.json`下载已核对；1440px和390px均无横向溢出；GREEN新增console errors为0。截图临时路径为`C:\Users\31729\AppData\Local\Temp\impad-p5-workbench\workbench-desktop.png`和`...\workbench-narrow.png`，不提交。
- 此节只关闭P5.2工程门：不声称四人团队UAT、真实平台采集、A2A、P5.3～P5.7、M1/M4/M5或分类/法规研究结论已完成。M1仍被候选池、Gold、合规、正式协议、无泄漏切分和Dataset Card证据缺口阻塞。

### 4.12 2026-07-31 分置信度自动判断标注系统（co-pilot-auto-judge）

- 设计文档：`docs/co-pilot-auto-judge-design.md`（v1.1，本地推理 Ollama + `qwen3.5:9b`）。
- 核心模块：`data-tooling/annotation/auto_judge.py` —— 三级自动判断（≥0.85 自动保存 / 0.55–0.84 建议 / <0.55 纯人工）、Ollama `/api/chat` JSON 推理、关键词失败回退、自动保存记录构建。
- 服务器管理：`data-tooling/annotation/ollama_server.py` —— 显式启动 `ollama serve`、查询状态（版本/已安装/已加载）、模型预热与常驻（`status` / `serve` / `preload` 子命令）。
- 配套工具：`batch_pre_annotate.py`（批量预标注，输出 auto/suggest/stats 三文件）、`manual_review_annotate.py`（新增 `--auto-threshold`/`--ollama-backend`/`--ollama-model` 等）、`flet_annotator.py`（新增自动模式开关、阈值滑块、Toast、底部状态栏）。
- `impad/llm.py` 新增 `get_ollama_llm()` 工厂（OpenAI 兼容端点指向本地 Ollama）。
- 自动保存审计约定：`annotator_id="system"`、`annotation_method="auto_accepted"`、`_llm_suggestion` 记录模型与是否自动采纳；**自动标注记录不参与双人 κ 计算**。
- **运行环境约束**：
  - Ollama 模型目录可能由 `OLLAMA_MODELS` 改到非默认位置；`ollama_server.py` 会尝试从桌面应用日志探测，部署时仍应以 `status` 子命令实测。
  - **Qwen3.5 默认开启 thinking**；本工具在请求顶层设置 `"think": false`，避免长推理挤占结构化 JSON 输出。实际延迟和显存占用必须在目标机器重新测量。
  - 预热：`python data-tooling/annotation/ollama_server.py serve --preload`；批量脚本默认预热并使用 `keep_alive=30m`，减少重复冷启动。
- 单元测试：`data-tooling/annotation/tests/test_auto_judge.py`（21 passed，mock 掉 Ollama，不依赖模型）。
- 三条样例仅完成 Ollama/CLI/GUI 工程冒烟；它们不证明自动标注准确率、正式双标一致性或 Gold 质量。
- Windows GBK 控制台兼容：CLI 脚本均强制 `sys.stdout.reconfigure(encoding="utf-8")`。
- 修复 `flet_annotator.py` 原有 4 处无法解析的延迟导入（`scripts.data.annotation.*`/`data_tooling.annotation.*` → 同目录直接导入）。

### 4.13 2026-07-31 P1→P3本地整合与M1数据复核

- 从`origin/P3@ba0ab58`建立隔离工作树与`codex/p1-m1-into-p3`分支；合并`origin/P1-·-数据地基与标注规范@43c59ac`，合并提交为`ca8fc2d`，两边历史均保留。
- 删除P1分支中的一次性URL/作者列表、临时诊断脚本、运行日志和本机输出；保留可参数化的增量合并工具，并用窄范围`.gitignore`防止同类产物再次进入Git。
- P3运行时适配器按`schema_version`加载v1.0或v1.2权威Schema；v1.1按v1.2兼容验证，未知版本和未知字段继续fail closed。v1.2来源扩展字段经Schema验证后只映射运行时所需字段。
- 用户ZIP只读检查无路径穿越，解压到`data/run_outputs/merged_20260728`（Git忽略）；原始ZIP未修改，真实正文、媒体、URL和ID映射均未提交。
- 当前权威JSONL审计：2,901行/2,901唯一帖子、108个创作者、Bilibili 2,182 + WeChat 719、14,174个唯一媒体引用全部可定位、15,066个磁盘媒体文件、0重复帖子。
- Schema v1.2校验为2,901有效/0无效；这次未启用隐私扫描，不能沿用其他数据批次的PII处置结论。
- 独立代码审查发现并关闭治理旁路：一致性与Gold工具现在只接受`annotation_method="human"`且标注者ID经首尾空白归一化后非空、不同、非`system`的标注对；`auto_accepted`、缺失方法/ID和同一标注者均聚合排除，正式轮次标记会fail closed。两份运行镜像字节一致并有回归保护。
- `scripts/merge_incremental.py`只升级v1.1或接收v1.2；不再写入`is_content=null`或未定义的LLM字段，每条记录在目标备份、追加或媒体复制前先通过权威v1.2 Schema校验。
- M1门禁仍为`passed=false`、退出码2：候选差99、Gold为0、正式第二轮κ待复核、条款与隐私审批未完成、无泄漏切分缺失、Dataset Card未审批。
- 数据集指纹：`adb39f1840df62cbeef52faabde85177536478c1c06d37bbb747a9a2bb59a3a5`。该指纹是后续增量补齐、标注与审批的版本锚点。
- 审查修复后新鲜验证：治理/增量聚焦`30 passed`，自动判断`21 passed`，全量`405 passed, 2 skipped, 1 warning`；`pip check`、`compileall`和两套P1资产校验通过。

### 4.14 2026-08-08 P5.7安全工程验收

- 工程门：PASS。完整证据矩阵见`docs/security/2026-08-08-p5-7-security-acceptance.md`。
- 新鲜聚焦回归：`144 passed in 5.31s`；最终新鲜全量：`495 passed, 2 skipped, 1 warning in 12.71s`。`compileall`、`pip check`和`git diff --check`退出码均为0。
- 已验证八项控制：重定向逐跳重新校验；DNS变化/私网答案阻断并固定已校验IP；URL凭据、非默认端口、query/fragment脱敏；网页提示注入保持用户数据角色；平台正文不能扩大工具白名单；路径穿越/异常媒体引用失败关闭；MCP与假A2A超时、伪造身份、越权调用边界；API、报告、run和扫描器输出不泄漏Cookie、Token或敏感URL。
- 生产扫描器仅输出路径、规则、行号、匹配字节长度和SHA-256；对干净验收run退出0，对不安全合成fixture退出1且不回显秘密。
- 本验收完全离线，没有请求真实平台URL。假A2A只证明供未来P5.5复用的共享策略；P5.3/P5.4真实适配器、P5.5真实A2A、P5.6对照、四人UAT、M1、M4和M5仍未完成。

## 5. P1数据资产事实

远端最新P1成果已经合并到本地P3整合分支，但“资产合并”不等于M1验收完成。

### 5.1 已有资产

- `data/schema/data_schema_v1.json`：JSON Schema Draft 2020-12，v1.0权威字段标准。
- `data/schema/data_schema_v1_2.json`与`data-tooling/schema/data_schema_v1_2.json`：v1.2权威Schema镜像，哈希一致；P3运行时已支持。
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
- 当前ZIP已验证为2,901个唯一候选，距M1候选池≥3,000还差99；当前没有可计为正式Gold的记录，低于≥1,500。
- 外部数据Schema v1.2和媒体引用完整性已通过；条款核验为0，隐私人工审批未完成，因此所有记录最多停留在`interim`。
- Schema v1.0继续服务历史提交资产；v1.1按v1.2兼容验证，v1.2是当前扩展Schema。运行时按记录版本选择Schema，不静默升级或宽松接收未知版本。
- `data-tooling/`与`implicit-ad-agent/scripts/data/`仍有脚本副本；当前6组M1文件字节一致并有镜像测试，但长期仍应决定唯一维护来源。
- 标注指南已有24个边界案例；这只关闭指南数量项，不替代真实双标和Gold。
- 尚无可确认的第二轮独立盲标、仲裁包、Gold v1和零泄漏正式切分报告；pilot κ不得冒充正式证据。
- 任何恢复或新采集的真实内容在进入Git公开范围前，都必须重新完成条款核验、脱敏、直接身份/联系方式/URL参数和疑似秘密扫描。

### 5.3 Schema使用原则

历史v1.0提交资产继续由`data/schema/data_schema_v1.json`校验；当前Bilibili/扩展字段由内容相同的两份`data_schema_v1_2.json`校验。P3适配器必须先做对应版本的JSON Schema验证，再显式映射到窄运行时契约。

v1.1记录按v1.2兼容Schema验证；未知版本、未知字段或缺少必填字段必须拒绝。后续修改字段时应新增版本、changelog和适配测试，不得原地改变v1.0/v1.2含义。

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

1. 保持P3工程MVP回归稳定，不重写七工具、证据主链或统一服务。
2. 并行完成M1外部事实工作：≥3000唯一合规候选、来源条款与人工隐私审批、第二轮盲标、仲裁、≥1500 Gold和零泄漏切分。
3. 决定`data-tooling/`与`implicit-ad-agent/scripts/data/`的唯一维护来源；在决定前每次修改都必须同步镜像并运行字节一致性测试。
4. 保持已完成的P4工程准入回归；M1通过后替换为真实纵向特征/学习模型，并在验证集完成Judge校准、阈值、消融和risk-coverage实验。
5. 保持P5.1/P5.2/P5.7回归；先完成四人团队UAT，再依次做P5.3小红书缓存fixture/适配器、P5.4 B站适配器、P5.5真实A2A和P5.6运行模式对照。LightRAG保持非阻塞A/B候选。

## 9. 常用验证命令

```powershell
cd implicit-ad-agent

# 安装基础依赖与本轮可选模块
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,rag]"

# 默认零网络回归
.\.venv\Scripts\python.exe -m pytest -q

# P3非数据依赖工程聚焦回归
.\.venv\Scripts\python.exe -m pytest tests\rag tests\evaluation tests\orchestration\test_mcp_gateway.py tests\services\test_analysis_service.py tests\scripts\test_evaluate_p3.py -q

# P3离线工程报告
.\.venv\Scripts\python.exe scripts\evaluate_p3.py retrieval --corpus tests\fixtures\legal_rag_documents.json --benchmark tests\fixtures\legal_rag_eval_30.json --output ..\data\reports\p3\retrieval_synthetic_30.json
.\.venv\Scripts\python.exe scripts\evaluate_p3.py retrieval --corpus impad\rag\data\legal_corpus_v1.json --benchmark tests\fixtures\legal_rag_official_eval_15.json --output ..\data\reports\p3\retrieval_official_15.json
.\.venv\Scripts\python.exe scripts\evaluate_p3.py classification --predictions tests\fixtures\classification_eval_v1.json --output ..\data\reports\p3\classification_fixture.json

# P4工程准入聚焦回归
.\.venv\Scripts\python.exe -m pytest tests\creator_shift tests\evaluation tests\scripts\test_evaluate_p4.py tests\test_graph_evidence_flow.py tests\services\test_analysis_service.py -q

# P4零Key/零网络工程报告
.\.venv\Scripts\python.exe scripts\evaluate_p4.py creator-shift --fixture tests\fixtures\creator_shift_eval_v1.json --output ..\data\reports\p4\creator_shift_fixture.json
.\.venv\Scripts\python.exe scripts\evaluate_p4.py calibration --predictions tests\fixtures\calibration_eval_v1.json --output ..\data\reports\p4\calibration_fixture.json --bootstrap-resamples 500 --bootstrap-seed 20260730

# P5.1批量与URL服务工程准入
.\.venv\Scripts\python.exe -m pytest tests\api tests\services tests\adapters\platforms tests\test_app.py -q

# P5.2研究工作台工程门
.\.venv\Scripts\python.exe -m pytest tests\web tests\test_app.py tests\api -q

# P5.7安全工程门
.\.venv\Scripts\python.exe -m pytest tests\adapters\platforms\test_url_safety.py tests\adapters\platforms\test_safe_fetch.py tests\adapters\platforms\test_media_safety.py tests\adapters\platforms\test_url_import.py tests\orchestration\test_remote_policy.py tests\orchestration\test_mcp_gateway.py tests\orchestration\test_function_calling.py tests\protocols\mcp tests\security -q
.\.venv\Scripts\python.exe scripts\security\scan_p5_7_artifacts.py --path <generated-artifact-directory>

# 零Key本地工作台（浏览器打开 http://127.0.0.1:8765/workbench）
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765

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

当前新鲜预期：零Key全量`495 passed, 2 skipped, 1 warning`，P5.7聚焦`144 passed`；治理/增量与自动判断的历史聚焦结果仍见对应章节。每次跨阶段集成都要同时跑P1资产校验、M1数据测试与默认全量回归；测试绿不替代M1/M4/M5事实门。

M1真实数据审计、迁移、Schema、隐私、pilot一致性和门禁的PowerShell命令见`data-tooling/README.md`。当前门禁预期退出码为2；在外部证据补齐前，不要把它改成成功预期。

## 10. 不要重踩的坑

- Windows中文路径下优先使用 `python -m ...` 或显式 `.venv\Scripts\python.exe`，不要依赖损坏的launcher exe。
- 中文文件用UTF-8读取和写入。
- 默认测试不得读取真实API Key、联网或加载真实视觉模型。
- 当前P2.5主图默认使用确定性工具选择，不读取`.env`中的Key；后续若在P3重新启用LLM选择，`json_mode + 英文字段名 + Pydantic校验`仍是国产OpenAI兼容端点的输出兼容策略。
- 工具跳过、图片缺失、历史不足不是负向证据。
- RAG无可靠检索结果时返回空引用，不得补写条款号。
- 当前RAG同时包含小规模官方条款语料和合成评测fixture；二者用于工程回归，不得写成完整法规覆盖或法律质量结论。
- `mcp`与`chromadb`是可选依赖；契约层不得因未安装可选依赖而无法导入。
- CreatorShift当前输出是简单历史基线证据，不是校准概率，也不能直接决定暗广。
- A2A必须是独立Agent服务间的真实任务交换；同一进程内函数互调不能算A2A验收。
- 不要把外部本地ZIP中的2,901个唯一候选、14,174个唯一媒体引用和15,066个媒体文件说成仓库已跟踪资产或可公开数据。
- 不要把pilot的κ=1.0说成正式第二轮结果：它只有22对有效三元样本、没有暗广样本，且明确标记为非正式。
- 不要只改`data-tooling/`或`implicit-ad-agent/scripts/data/`其中一份后假设另一份会自动同步。
- 不把真实用户名、头像、手机号、群二维码、精确URL参数、密钥或内部地址提交到公开仓库。
- 不使用测试集调Prompt、关键词、阈值或CreatorShift窗口。
- 工作区如有无关修改，必须保留并分文件暂存；禁止 `git reset --hard`、覆盖式checkout或批量清理。

## 11. 文档职责

- `README.md`：面向新开发者和最终开源用户的入口。
- `HANDOFF.md`：当前事实、分支、风险和下一步。
- `docs/隐性广告识别项目_说明书.md`：架构、模块、数据流、错误处理、评估与边界。
- `docs/隐性广告识别项目_分阶段计划表.md`：日期、Owner、里程碑和降级决策。
- `docs/superpowers/specs/`与`docs/superpowers/plans/`：已确认设计、实施边界和可复现执行步骤。

新事实优先更新HANDOFF；稳定设计更新说明书；日期与Owner变化更新阶段表；公开使用方法更新README。
