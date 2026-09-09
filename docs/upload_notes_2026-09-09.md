# P1 / M1 上传文件与提交备注（2026-09-09）

目标分支：`P1-·-数据地基与标注规范`。组长检查后决定是否合并 main。按用途拆分提交，便于逐项检查和回退；本表对应“不同文件分别说明上传了什么、为什么上传”的要求。

## 1. 原 M1 分支合并

提交备注：**`merge: 将 M1 隐私与标注流程整合到 P1，保留 P1 采集和并行能力`**。

P1 基点 `36298fa` 与 M1 基点 `f43b6ff` 通过 merge 保留历史，不以目录覆盖代替合并。原 M1 相对 main 的8个独立提交如下：

| 提交 | 内容与保留理由 |
| --- | --- |
| `07d429d` | 网络误报与敏感内容遮蔽，保留 B 侧隐私处理流程 |
| `9c63a7b` | 补充复核流程，保证新增证据能继续人工核验 |
| `7d0d985` | B 侧状态记录，保留阶段工作可追溯性 |
| `c8b9521` | 私有材料忽略规则，防止后续误上传 |
| `a91930d` | cohort与校准校验，约束来源集合和复核材料 |
| `bddc312` | 阶段5–12准备/校验工具，方便路线确认后接续 |
| `50db14f` | 阶段3完成、阶段4待确认的事实同步 |
| `f43b6ff` | 正式锁批目录忽略规则，保持真实标注证据受控 |

冲突文件处理：`HANDOFF.md`、批量预标注、Bilibili采集、两份历史聚合审计、功能测试指令库、分阶段计划表、数据治理测试。保留 P1 增量能力和 M1 新事实；旧 P1 审计另存 `data/reports/m1/history/p1_20260803/`，不混用不同候选基线。

## 2. 预标注与可靠续跑

提交备注：**`fix(annotation): 合并完整指南与证据审计，支持版本绑定的并行续跑`**。

| 文件 | 文件备注 |
| --- | --- |
| `data-tooling/annotation/auto_judge.py` | 修复 uncertain/非法标签处理；接入完整指南、上下文和媒体覆盖；记录回退与原始输出；处理非有限置信度 |
| `data-tooling/annotation/batch_pre_annotate.py` | 保留 P1 并行参数，加入清单/指南/版本哈希、顺序审计、统计和严格续跑；阈值0禁用自动接收 |
| `data-tooling/annotation/batch_annotation_runtime.py` | 新增逐条原子检查点、输出锁、有界并行与无重复输出重建 |
| `data-tooling/annotation/manual_review_annotate.py` | 人工复核传递统一指南和模型上下文；保留人工确认职责 |
| `data-tooling/annotation/tests/test_auto_judge.py` | 回归标签、指南、模型参数、媒体证据和审计契约 |
| `data-tooling/annotation/tests/test_batch_handoff_runtime.py` | 验证真实线程并行、固定顺序、断点恢复、拒绝版本混用、媒体覆盖和非有限值 |

## 3. 盲测交付工具

提交备注：**`feat(annotation): 交付角色隔离盲测工具与无私有数据的可运行示例`**。

| 文件 | 文件备注 |
| --- | --- |
| `data-tooling/annotation/build_m1_qwen_blind_remote_v2_manifest.py` | 从冻结父清单构建v2媒体入口，要求明确盲性声明，记录实际统计与来源哈希 |
| `data-tooling/annotation/generate_m1_qwen_blind_html.py` | 生成独立 A/B HTML、指南和协调清单；提供本地媒体检查、受限视频入口和证据缺口导出 |
| `data-tooling/annotation/package_m1_qwen_blind_role.py` | 每角色独立ZIP，只带必要页面/指南/媒体；校验交付源哈希、相对路径及包内SHA清单，拒绝覆盖 |
| `data-tooling/annotation/tests/test_qwen_blind_review_html.py` | 验证角色隔离、无模型建议、缺失媒体和远程入口限制 |
| `data-tooling/annotation/tests/test_blind_handoff_packaging.py` | 验证完整合成链路、ZIP哈希/入口、禁止覆盖、来源被修改时拒绝打包 |
| `scripts/demo_m1_handoff.py` | 两条合成样本一键生成可打开页面和便携包，证明新克隆可运行工具，不伪造真实标注 |

## 4. 环境、进展与交接

提交备注：**`docs(handoff): 发布 P1 可复现环境、验证记录与组长接续说明`**。

| 文件 | 文件备注 |
| --- | --- |
| `requirements-handoff.txt` | 明确系统、测试、MCP、RAG、基线与打包检查依赖 |
| `requirements-handoff.lock` | 固定本次独立 Python 3.12 环境的实际依赖版本，无本机绝对路径或私有下载地址 |
| `scripts/verify_handoff.py` | 一键执行全部公共工程检查，输出本地日志及JSON；兼容中文路径与独立临时目录 |
| `HANDOFF.md` | 当前阶段、分支范围、运行方法、依赖、私有材料清单、接手角色及验收依据 |
| `README.md` | 首屏提供当前交接、进展与验证入口 |
| `data-tooling/annotation/readme.md` | 说明新增工具与新续跑语义，将旧说明标为历史 |
| `docs/progress/2026-09-09-project-status.md` | 完整进展、个人 B 侧贡献、技术深度、组会口述和下一步；增加本次 P1交付说明 |
| `docs/m1_qwen_diagnosis_public.md` | 六类缺陷、修复、真实20条聚合结果和待验证边界；不含逐条私有内容 |
| `docs/dataset_card_current.md` | 同步阶段3正式化及21条盲测状态，保留 Gold/κ/切分尚未完成的事实 |
| `docs/verification_2026-09-09.md` | 记录本版实际测试、演示、环境与明确跳过项 |
| `docs/upload_notes_2026-09-09.md` | 本表，供组长按文件审查 |
| `docs/history/HANDOFF_before_p1_m1_20260909.md` | 归档旧交接，保留已有工程决策和历史细节 |
| `data/reports/m1/preparation/B_pre_gate_downstream_regression_20260822.md` | 补交 B 侧下游准备回归报告，明确其历史日期和非正式产物性质 |
| `.gitignore` | 排除真实盲测目录、逐条诊断/清单和打包临时目录 |

本次从最新文件树移出 `data/reports/m1/privacy_scan_report.json` 与 `data/reports/m1/qwen_calibration_20_review_manifest.json`：二者包含逐条标识信息，保留私有副本，公开只交付聚合结论。历史提交不改写。真实盲测目录、ZIP、人工答案、仲裁与原始诊断均不上传。

另外仅规范以下既有聚合报告的行尾空白，不改变数据：`data/reports/audit_repaired.md`、`data/reports/m1/m1_data_audit.json`、`data/reports/m1/qwen_calibration_50_report.md`、`data/reports/m1/schema_validation.json`。

## 5. 合并后的分支处理

只有在确认远程 P1 指向本版提交、原 P1 和 M1 两个基点均为其祖先后，才删除旧 `feat/m1-b-privacy-workflow` 分支指针。M1 内容和提交历史仍保存在 P1。main 由组长另行审核合并；先前的进展文档分支不在本次删除范围。
