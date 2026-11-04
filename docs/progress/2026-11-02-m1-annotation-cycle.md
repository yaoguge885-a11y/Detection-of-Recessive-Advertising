# M1 标注循环执行记录（2026-11-02）

本文件记录本轮把「盲标 → 本地 AI 辅助人工标注」切换后实际完成的工作、可核验的产物和未完成项。

## 1. 决策变化

| 项目 | 原设计 | 本次实际 |
| --- | --- | --- |
| 21 条 Qwen 盲测 | A 已完成，等待 B | **放弃**，不进入 κ 与 Gold；材料留存于 `data/reports/m1/private/` |
| 正式 κ | 双人独立盲标 150 条 | **未执行**（无第二标注人） |
| Gold 规模 | 1,500 条双人 | 单人 120 条，实际有效 116 条 |
| AI 参与 | control 无 AI、assisted 有 AI | 本轮全部无 AI（`/api/suggest` 返回 403） |

## 2. 数据与批次

- 正式候选池落地：`data/reports/m1/privacy/formal_3312_v2/`（2,932 条批准，380 条排除），候选池 SHA-256 `53d7e707…`，与正式化报告一致。
- 隐私审批范围：`approved_for_internal_m1_formal_experiments_external_release_blocked`。
- 正式锁批：`data/reports/m1/locked_batches/`，状态 `locked`，2,050 唯一 post_id，批间交集 0。

| 批次 | batch_id | 条数 | 媒体可用/缺失 |
| --- | --- | ---: | --- |
| round1 | m1_round1_100 | 100 | 55 / 45 |
| round2 | m1_round2_formal_150 | 150 | 73 / 77 |
| gold_control | m1_gold_control_180 | 180 | 78 / 102 |
| gold_assisted | m1_gold_assisted_1620 | 1620 | 474 / 1146 |

波次清单（`locked_batches/waves/`）：

| 波次 | 条数 | SHA-256 前缀 | 状态 |
| --- | ---: | --- | --- |
| kappa_150 | 150 | `5ee7aa9b` | 未标注 |
| gold_control_180 | 180 | `14e38d21` | 未标注 |
| gold_assisted_w1_320 | 320 | `05772d4a` | 未标注 |
| gold_human_120 | 120 | `42caf8ba` | **已标注（本轮）** |

## 3. 工具

- 新增 `scripts/start_m1_gold.ps1`：按波次启动标注工作台，`kappa`/`control`/`human120` 强制 `--no-auto-suggest`。
- 该脚本需保存为 UTF-8 with BOM，否则 Windows PowerShell 5.1 读取中文串会解析失败。
- 校验结果：`manifest_role=approved`、`formal_gold_allowed=true`、`missing_count=0`。
- 交付包 `data/reports/m1/private/M1_标注交付_20261102.zip`（私有，不入库）。

## 4. 本轮标注结果（A，m1_gold_human_120）

- 计划 120 条，导出 119 条，**1 条未标注**：`私有案例-12`。
- 全部 119 条 `annotation_method=human`、`saw_model_advice=false`。
- 质检（`qc_report_20261102_213011.json`）：

| 项目 | 结果 |
| --- | --- |
| 采集失败剔除 | 3 条（`post_07f7f77…`、`私有案例-13…`、`私有案例-14…`），标记 `invalid_capture_failed` |
| 补记证据码 A | 2 条收藏集内容（`私有案例-15…`、`私有案例-16…`） |
| 有效样本 | **116 条** |

有效样本标签分布：非广 82、明广 13、out_of_scope 12、暗广 5、uncertain 4。

QC 产物位于 `data/annotations/workbench/m1_formal_3312_v2/m1_gold_human_120/A/`（Git 忽略目录），原始导出未修改。

## 5. 关键发现

1. `auto_judge.py` 已固定 `temperature: 0.0`，AI 建议本身是确定性的；此前怀疑的「AI 上下文漂移」不来自温度。
2. 单人标注下无法计算 κ；如需信度指标，需第二人独立标注 40–50 条重叠样本。
3. 媒体缺失比例高（control 180 条中 102 条无本地媒体），标注时按"未采集"处理，不能推断为"未发现"。
4. 指南 v1.0 的 SHA-256 已写入每条标注记录，本批次期间不得修改该文件；新规则以补充文件形式记录。

## 6. 未完成项

- 补标 1 条（`私有案例-12`）。
- 若需要 κ：第二标注人重叠标注。
- 若需要更大 Gold：`gold_control` 剩余 60 条、`gold_assisted_w1_320` 均可继续。
- 规则补充（S-1/S-2/S-3）待形成 v1.1 并指定生效批次。
- M1 总门禁仍为 `passed=false`：Gold 数量、切分、Dataset Card 均未满足。

## 7. 外部 API 辅助通道（2026-11-02 晚间）

### 7.1 授权与范围披露

- 数据责任人 A 决定改用 OpenAI 兼容端点（DeepSeek）批量生成建议，用于 384 条待标 Gold。
- **该操作超出 `privacy_approval.json` 中 `approved_for_internal_m1_formal_experiments_external_release_blocked` 的 internal-only 范围**：帖子正文与评论被发送到 `api.deepseek.com`。本次共 500 条，时间 2026-11-02 22:02–22:20（UTC+8）。
- 该决定由 A 以数据责任人身份作出；后续对外发布、数据集再分发仍受限，模型端不保留用于再分发的数据。

### 7.2 实现

| 文件 | 改动 |
| --- | --- |
| `data-tooling/annotation/auto_judge.py` | 新增 `run_openai_compat_judge()`；`run_auto_judge(backend=...)` 分发；HTTP 错误带响应体；`finish_reason=length` 自动翻倍 `max_tokens` 重试；`response_format` 400 时降级重试 |
| `data-tooling/annotation/batch_pre_annotate.py` | 新增 `--backend`、`--api-base-url`、`--api-model`、`--api-key-env`、`--api-timeout`、`--env-file`；API 模式跳过 Ollama 预热；审计记录实际模型名 |
| `data-tooling/annotation/annotation_workbench/file_suggestions.py` | 新增离线建议源，页面读预跑结果，不再实时调用模型 |
| `data-tooling/annotation/html_annotator.py` | 新增 `--suggestion-file` |
| `scripts/start_m1_gold.ps1` | 新增 `human120`、`ai384` 波次；`ai384` 自动选取最新 `audit_*.jsonl` 作为离线建议 |

联调中发现并修复的问题：`Authorization` 头被误写为常量、`--api-model` 未传入判定器、`max_tokens` 过小导致 JSON 截断、`.env` 中 `LLM_MODEL` 不是有效模型名（有效值为 `deepseek-flash` / `deepseek-v4-pro`）。

### 7.3 500 条建议生成

- 输入：`data/annotations/preannotated/input_gold_500.jsonl`（control 180 + assisted 320），SHA-256 `699BD39E…`
- 模型：`deepseek-v4-pro`，温度 0，`max_tokens` 3072，并发 100，`--no-images`
- 结果：500/500 完成，0 错误；`suggest` 380 条，`manual`（弃答或低置信）120 条，弃答率 24%
- 产物：`data/annotations/preannotated/gold_ai_500_v4pro/`（Git 忽略）

### 7.4 116 条对照结果

以纯人工标注的 116 条有效样本为基准（见第 4 节）：

| 指标 | 数值 |
| --- | ---: |
| 配对样本 | 116 |
| 双方均为三分类 | 80 |
| 一致率 | 91.25% |
| Cohen's κ | **0.493** |
| 模型弃答 | 25 条（21.6%） |

混淆矩阵（行=人工，列=模型）：

| 人工 \ 模型 | 非广 | 明广 | 暗广 | uncertain |
| --- | ---: | ---: | ---: | ---: |
| 非广 (82) | 69 | 2 | 0 | 11 |
| 明广 (13) | 3 | 4 | 0 | 6 |
| 暗广 (5) | 2 | 0 | 0 | 3 |
| out_of_scope (12) | 7 | 0 | 0 | 3 |

**关键结论：模型暗广召回为 0/5。** 与 2026-09 的 DeepSeek 评测方向一致（当时 recall 35%），说明暗广仍是当前模型的系统性短板。

另有 4 条高置信度分歧（模型置信度 ≥0.8 但与人不同），其中 `私有案例-17` 模型以 0.85 判非广且**未给出任何证据码**，属无证据下结论。

完整数据见 `gold_ai_500_v4pro/comparison_116.json`（Git 忽略）。

### 7.5 创作者上下文缺失（研究相关）

- 500 条记录中仅 128 条（26%）带 `blogger_history_refs`。
- `auto_judge.py` 的提示词**从未传入创作者历史**，模型对博主身份与既往内容完全不可见。
- 人工判为暗广的 5 条中有 4 条本身无任何历史记录，说明人的优势部分来自数据集之外的经验（对博主的既有印象），而非数据中的历史字段。

由此产生两点后果：

1. 支持 CreatorShift 假设：单帖证据不足时，创作者上下文对暗广判断有实质影响。
2. 影响可复现性：依赖记忆的判定必须在证据字段写明理由，否则他人无法复现。指南 EC-14 亦规定创作者偏离（`B`）不能单独定暗广。

### 7.6 明日待办

1. 按分层口径标注 384 条：明广/非广参考建议，暗广独立判断（模型暗广召回为 0）。
2. 标注时把"熟悉博主"类理由写入证据字段。
3. 可选实验：将创作者历史加入提示词后重跑，量化暗广召回变化。
4. 收尾质检、更新 Dataset Card，并重跑 M1 门禁（当前仍 `passed=false`）。
