# M1 数据与交接索引

更新于 2026-11-03。执行从 [项目交接](../../HANDOFF.md) 开始。本文说明每份材料用在哪里，以及如何在本地恢复工作目录。

## 当前使用的数据

| 材料 | 数量 | 用途 | 本地位置 |
| --- | ---: | --- | --- |
| B 侧私有包中的获批候选和审批链 | 2,932 | 当前的选样池。候选、人工审批、允许清单和复扫文件按正式化报告核对 SHA-256 | `data/reports/m1/privacy/formal_3312_v2/` |
| 本轮保留标签与合并报告 | 479 | 团队补标计划已纳入的 Gold。108 条单人无 AI、371 条 AI 辅助后人工确认，保留 `gold_tier` | `data/reports/m1/gold/gold_tri.jsonl` 和 `report.json` |
| 本轮全量与排除记录 | 503 / 24 | 全量 = 479 条保留 + 24 条排除。复核排除原因、标签分层及合并结果 | `data/reports/m1/gold/gold_all.jsonl` 和 `gold_excluded.jsonl` |
| 规范化原始候选 | 3,312 | 查原文、媒体引用和候选关系。正式锁批取上面的获批子集 | `data/run_outputs/m1_3312_v2/anonymized_posts.jsonl` |
| 第二轮一致性样本 | 150 | 从获批池锁定新样本，A、B 各自标同一批 | `data/reports/m1/locked_batches/round2.jsonl` 和 `round2_manifest.json`，由批次负责人交接 |

桌面 3,312 条快照覆盖全部获批 ID，但文件指纹与正式化报告绑定的 canonical 输入不同。需要复现来源条款和正式化链时，请使用报告所指的原始版本。

本轮 479 个帖子 ID 全部属于 2,932 条获批池。三份合并输出的 SHA-256 与 `report.json` 一致。119 条和 384 条的两份原始工作台导出仍待补档，因此当前可核验合并结果与报告的一致性。按团队补标口径距离 1,500 条还差 **1,021 条净保留标签**。正式 Gate 仍按仓库现行协议读取正式双人一致性、Gold 构建报告、合规与无泄漏切分证据。若正式验收要接纳这 479 条，先记录批准的纳入规则和分层评估办法，再按批准版本验收。

## 历史材料

- `merged_20260728.zip` 含 2,901 条旧候选和媒体，留作查图或复现旧审计。媒体路径需与当前帖子引用核对。[旧数据审计](../../data/reports/m1/merged_20260728_audit_report.md)
- `preannotated_nonvideo_20260916_002512.jsonl` 是 2,137 条系统预标注，放在 `data/run_outputs/m1_3312_v2/preannotations/`，作为历史对照。第二轮独立盲标不加载建议。
- `dataset_full/` 是早期采集和标注材料，归档即可。B 私有包中另有 21 条辅助接续任务，与正式第二轮的 150 条分开。[B 侧接替交接](B_HANDOFF_2026-11-02.md)

## 恢复本地工作目录

1. 从团队私有渠道取得 B 侧交接包，只将包内的 `formal_3312_v2/` 放到上表对应位置。目录应包含 `formal_eligible_candidates.jsonl`、`formalization_report.json`、`privacy_approval.json`、`public_allowlist.json`、隐私复扫、Schema 校验及 cohort 审计。
2. 将三份 Gold JSONL 和 `report.json` 放到 `data/reports/m1/gold/`。原始候选和机器预标注分开存放。保留收到的原件，若同名文件指纹不同，先查版本。
3. 查第一轮综合表是否保留 A/B 的原始答案，生成或找回 `round1_agreement.json`，确认生效规则并保存 `annotation_guide_freeze_receipt.json`。向批次负责人取已有锁批清单和输入指纹，核实后再发第二轮新样本。需要重新锁批时，先补齐双方模型路线确认。操作见 [阶段 5–12 命令](../../data/reports/m1/preparation/阶段5至12_B执行命令.md)。

GitHub 版本包含代码、合成样例、聚合报告和任务说明。上表的真实逐条数据、审批明细、标注回件和媒体在 Git 忽略目录或外部私有目录中保存。
