# P1 / M1 项目交接（2026-09-09）

本版交付给组长在 **`P1-·-数据地基与标注规范`** 分支检查，再由组长决定是否合并 `main`。包含原 M1 分支、原工作区中已完成的可复用修改、运行示例、测试、依赖约束与进展报告。

先读本文完成运行，再查看 [组长进展与组会汇报](docs/progress/2026-09-09-project-status.md)、[逐文件上传备注](docs/upload_notes_2026-09-09.md)、[Qwen 诊断](docs/m1_qwen_diagnosis_public.md) 和 [数据集卡](docs/dataset_card_current.md)。旧交接在 [历史文档](docs/history/HANDOFF_before_p1_m1_20260909.md)，其中日期、分支位置和测试数量均为历史快照。

## 1. 接手时先对齐的事实

当前做到 **阶段3正式化完成、阶段4模型路线待确认**。代码和预演工具已经具备；正式 M1 验收还没有通过。

| 项目 | 已核验状态 | 对后续工作的含义 |
| --- | --- | --- |
| canonical 候选 | 3,312 条唯一帖子，117 位创作者；Bilibili 2,503 / WeChat 809 | 这是候选规模，不是 Gold 数量 |
| 来源与隐私阶段3 | 2,932 条正式候选，380 条排除；正式化引用 7/7 哈希一致 | 后续正式锁批只能使用已批准候选池 |
| 旧固定20条复核 | A/B 材料通过联合机械校验；真实 Qwen 工程运行20条均 `uncertain`、无错误/回退 | 不能宣布模型准确率或质量已通过 |
| 新21条盲测 | A/B 独立 v2 页面和便携包已准备，67 个本地媒体引用、7 个受限视频入口 | 等待真实独立答案、分歧仲裁和路线签字 |
| 正式下游 | 正式锁批、Round 1、Round 2、Gold、无泄漏切分、最终 Gate 均未完成 | 预演产物不能提升为正式证据 |
| 工程系统 | LangGraph 证据链、工具契约、MCP、Judge 后 RAG、CLI/API、工作台及合成基线可回归 | 属于团队已有工程成果；论文级分类效果仍需正式数据验证 |

研究核心仍为 CreatorShift：检验创作者历史信息对暗广识别是否提供增益。Agent、Function Calling、MCP、RAG 属于工程贡献。正式金标为明广 / 暗广 / 非广；`uncertain` 与“需复核”用于治理和运行，不作为第四个金标类别。

## 2. 先跑通交付工具

需要 Python 3.12。以下命令从**仓库根目录**执行：

```powershell
git clone --branch 'P1-·-数据地基与标注规范' https://github.com/yaoguge885-a11y/Detection-of-Recessive-Advertising.git
cd Detection-of-Recessive-Advertising
python -X utf8 scripts/demo_m1_handoff.py
```

这个命令只用标准库，创建两条合成样本，走完“固定清单 → A/B HTML → 各自便携 ZIP → 角色隔离及文件可用性检查”。终端输出 `status: passed` 和 HTML/ZIP 路径。解压整个角色文件夹后按包内 README 打开页面。输出在 Git 忽略的 `data/run_outputs/handoff_demo_.../`，保留已有结果，不覆盖真实材料。演示不调用模型、不需要 API Key，不产生正式标注或质量结论。

## 3. 安装验证环境并运行系统

本版以 Windows、Python 3.12.5 验证。`requirements-handoff.lock` 固定通过验证的依赖版本；包含 test、MCP、RAG 和传统基线依赖。首次安装需联网。真实视觉栈、Ollama 模型和平台采集环境单独配置。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-handoff.txt
.\.venv\Scripts\python.exe -X utf8 scripts/verify_handoff.py
```

验证脚本检查依赖一致性、标注工具、传统基线、主系统、两套提交资产校验、盲测演示和系统 CLI 演示。有 Node.js 时也运行工作台行为测试；未安装会明确记录跳过。日志与 JSON 报告位于 `data/run_outputs/handoff_checks_.../`，测试使用独立临时目录。

启动网页工作台：

```powershell
cd implicit-ad-agent
..\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/workbench> 或 <http://127.0.0.1:8000/docs>。默认本地确定性分析不需要模型 Key。URL 导入默认适配器为空，先使用手工输入或仓库示例。真实图片推理需额外视觉依赖和权重；本次通用环境不代表真实视觉验收。

本次实际结果见 [验证记录](docs/verification_2026-09-09.md)。历史文档中的 405、576 等数量属于其他日期/分支，不能相加或当成本版结果。

## 4. 合并和修改范围

- P1 基点：`36298fa75df516c095ca43798741529640dfbb78`。
- 原 M1：`f43b6fff8d2e1a74eab62556a5c9c1ff443efbfb`，分支 `feat/m1-b-privacy-workflow`。
- 整合时 main：`a6cce27a0945aa0344593546b984b8a599942b11`；本次不向 main 推送。
- 合并提交：`ac4f8f5`，保留两条分支历史。原 M1 相对 main 的8次独立提交均进入 P1。

冲突处理保留 P1 的采集去重、字段提取、清理和 Ollama 服务能力；预标注合并 P1 的并行/续跑与 M1 的指南、固定清单、严格标签和审计契约。旧 P1 聚合审计冲突文件保存在 `data/reports/m1/history/p1_20260803/`，仅用于历史追溯。

核心增量：

1. `auto_judge.py`：保留 `uncertain`、拒绝非法标签，传入完整指南与上下文参数，记录媒体覆盖、原始输出和回退来源；处理非有限置信度。
2. `batch_pre_annotate.py` / `batch_annotation_runtime.py`：受限并行、固定顺序、逐条原子检查点、版本绑定续跑和完整审计。
3. `manual_review_annotate.py`：人工复核显式使用指南与上下文参数，保留真实人工判断职责。
4. 三个盲测工具：清单构建、独立角色 HTML、角色专属便携包；验证输入哈希、媒体路径和在线证据状态。
5. 合成演示、验证脚本、专项回归、依赖约束、公开诊断、进展与交接文档。

## 5. 模型预标注与续跑

下面仅是参数示例。先取得获准使用的私有输入和固定清单，确认模型路线及运行条件；示例不产生正式 Gold。

```powershell
.\.venv\Scripts\python.exe data-tooling/annotation/batch_pre_annotate.py --input data/private/candidates.jsonl --post-id-manifest data/private/fixed_manifest.json --guide docs/annotation_guide_v1.md --output-dir data/annotations/preannotated/calibration --ollama-model qwen3.5:9b --num-ctx 32768 --auto-threshold 0 --num-parallel 1 --no-images
```

`--auto-threshold 0` 禁用自动接收；`--no-images` 是文本模式，审计保留媒体证据不足状态。需要视觉时配置依赖及正确 `--media-base`，移除 `--no-images`。模型时延、显存及覆盖情况以实际审计为准。

中断后以**相同命令和参数**追加 `--resume`（最近一批）或 `--resume <batch_id>`。输入、指南、清单、代码、媒体内容或参数变化时拒绝续跑，须新建输出目录重跑。旧版仅有 `progress_*.jsonl` 的结果不能直接迁入新模式。异常断电残留 `.batch.lock` 时，先确认进程已结束，再移除该锁；不要让两个进程写同一输出目录。

输出包括 `auto/suggest/audit/progress_<batch_id>.jsonl`、`stats_*.json`、`run_config_*.json` 和 `checkpoints_*/`，均为本地工程记录。自动结果不计入双人 κ。

## 6. 后续任务与接手建议

| 顺序 | 接手角色 | 动作 | 验收依据 |
| --- | --- | --- | --- |
| 1 | 组长 / 工程接手人 | 检查 P1 diff，按第2、3节运行 | 验证报告与演示；再决定合并 main |
| 2 | 协调人 | 核对阶段3候选及已发21条 v2材料，分别交付 A/B | 正确角色、固定清单/指南/哈希、私有输入可访问 |
| 3 | A / B | 独立完成21条；真实检查媒体和受限视频，导出本角色答案 | 独立声明、逐条证据、完整集合、缺口说明 |
| 4 | 协调人 / 仲裁人 | 收齐答案，处理分歧，按冻结版本比较模型 | 真实仲裁、指标/拒答率/覆盖率/错误/时延报告和路线签字 |
| 5 | 数据负责人 | 通过准备度检查后从2,932条正式候选锁定四批 | `preflight_not_formal` 不得复用为正式批次；固定清单和输入哈希 |
| 6 | A / B / 仲裁人 | 正式第一轮、独立第二轮、κ、仲裁与 Gold | 来源真实；自动接收不计入双人 κ |
| 7 | 数据与实验负责人 | 创作者/近重复组连通切分、Dataset Card审批、最终 Gate | Gold规模、κ门槛、零泄漏、全部门禁通过 |
| 8 | 模型 / 系统负责人 | 比较单帖、多模态及 mean/max/EMA历史基线，推进 CreatorShift及产品验收 | 固定split、共同cohort、版本/种子/消融和错误分析 |

阶段5–12准备与校验工具已入仓库，各脚本的 `--help` 和 [分阶段计划表](docs/隐性广告识别项目_分阶段计划表.md) 提供参数与顺序。执行前仍需真实材料和签字。不要把“工具已实现”写成“正式数据已产出”。

**已经发出的21条 v2包保持冻结。** 本次代码更新不替换既有包；确需重建时由协调人建立新版本清单、记录变更及哈希，并组织重新独立复核，不能静默混用答案。

## 7. 私有材料如何交接

公开仓库只交付代码、合成样例、规则文档和聚合报告。真实正文、URL、post/creator ID映射、媒体、人工审批、独立答案、仲裁和逐条模型审计不公开上传。

接手人向协调人取得 canonical包及指纹、阶段3候选/排除/审批/复扫、旧20条校准和回执、已发21条 v2角色包及协调清单。私有文件保持相对路径和哈希；仅克隆仓库不会获得它们。未经许可不得为了补齐运行依赖上传这些材料。

本次将历史已跟踪的两份逐条清单从最新文件树移出并加忽略规则；Git历史不改写。公开诊断使用聚合版。原工作区的未公开材料继续保留用于受控交接。

## 8. 组会表达重点

个人 B 侧工作围绕“数据质量为什么可信、模型输出为什么可审计、其他组员为什么能接着做”展开：541条隐私任务（其中427条需媒体证据）、后续308条补充核查、固定20条模型复核属于不同流程，不能相加当作唯一样本数；再说明六类预标注缺陷、21条独立盲测设计与本次工程整合。

完整讲述与导师可能追问的问题见进展报告。目前已将采集、隐私、证据、预标注、独立复核和正式门禁连接成可追踪流程；尚未取得的分类效果、κ和Gold结果如实列入下一阶段。
