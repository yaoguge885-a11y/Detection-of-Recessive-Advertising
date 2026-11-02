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

- 计划 120 条，导出 119 条，**1 条未标注**：`post_90171b8ca5db2c58077d675a6a78a6f8`。
- 全部 119 条 `annotation_method=human`、`saw_model_advice=false`。
- 质检（`qc_report_20261102_213011.json`）：

| 项目 | 结果 |
| --- | --- |
| 采集失败剔除 | 3 条（`post_07f7f77…`、`post_0cab0716…`、`post_91829edb…`），标记 `invalid_capture_failed` |
| 补记证据码 A | 2 条收藏集内容（`post_0a18a3ec…`、`post_21167eb5…`） |
| 有效样本 | **116 条** |

有效样本标签分布：非广 82、明广 13、out_of_scope 12、暗广 5、uncertain 4。

QC 产物位于 `data/annotations/workbench/m1_formal_3312_v2/m1_gold_human_120/A/`（Git 忽略目录），原始导出未修改。

## 5. 关键发现

1. `auto_judge.py` 已固定 `temperature: 0.0`，AI 建议本身是确定性的；此前怀疑的「AI 上下文漂移」不来自温度。
2. 单人标注下无法计算 κ；如需信度指标，需第二人独立标注 40–50 条重叠样本。
3. 媒体缺失比例高（control 180 条中 102 条无本地媒体），标注时按"未采集"处理，不能推断为"未发现"。
4. 指南 v1.0 的 SHA-256 已写入每条标注记录，本批次期间不得修改该文件；新规则以补充文件形式记录。

## 6. 未完成项

- 补标 1 条（`post_90171b8ca5db2c58077d675a6a78a6f8`）。
- 若需要 κ：第二标注人重叠标注。
- 若需要更大 Gold：`gold_control` 剩余 60 条、`gold_assisted_w1_320` 均可继续。
- 规则补充（S-1/S-2/S-3）待形成 v1.1 并指定生效批次。
- M1 总门禁仍为 `passed=false`：Gold 数量、切分、Dataset Card 均未满足。
