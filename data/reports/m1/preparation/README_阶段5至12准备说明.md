# M1 阶段 5–12 准备说明

状态：`preparation_only_not_formal`
准备日期：2026-08-17
执行人：B（工程准备）

## 已经可以完成且已完成的准备

- 阶段 5：四批固定规格、seed、互斥锁定、精确导出、候选 SHA 绑定和非正式预演保护由 `data-tooling/m1_lock_batches.py` 实现。
- 阶段 6：Round 1 B 侧正式入口预检由 `data-tooling/m1_round1_preflight.py` 实现。
- 阶段 6–9：任一 A/B 标注流可用 `data-tooling/m1_annotation_output.py` 核验固定 ID、顺序、数量、annotator、人工方法和标签；支持每 300 条阶段性验收。
- 阶段 10：裁决格式、C 抽查回执和 Gold 构建所需文件位置已模板化。
- 阶段 11：Gold 与 canonical 的 `blogger_id/content_group_id` 严格回连由 `data-tooling/m1_gold_metadata.py` 实现；缺失 blogger_id 会直接失败。
- 阶段 12：`data-tooling/m1_downstream_readiness.py` 只读检查阶段 5–12 固定证据路径，不能把模板或预演误判为正式完成。

## 当前不能提前做的内容

- 不能在阶段 3/4 总门前生成 `status=locked` 的正式四批。
- 不能提前查看或人工标注 Round 1/Round 2/Gold 的真实 ID。
- Round 1 未结束并冻结指南前，不能开始正式 Round 2。
- 正式 κ 未达到 0.60 前，不能开始 Gold control/assisted。
- A/B 双人结果未齐全前，不能生成裁决清单或 Gold。
- Gold 不足 1,500 前，不能生成正式 split。
- D 未核验证据前，不能把 Dataset Card 状态改为 `true`。

## 后续唯一执行顺序

1. A 返回阶段 3 回执和固定 20 条校准 JSON；A/B 共同签模型路线。
2. 正式化 `formal_eligible_candidates.jsonl`，数量不少于 2,050，并生成匹配 SHA 的 `formalization_report.json`。
3. 正式锁定四批；C 填批次封存回执。
4. A/B 各自完成 Round 1；解盲修订指南；C 填指南冻结回执。
5. A/B 各自完成 Round 2；核验输出；计算正式 κ。
6. κ 合格后，A/B 各自完成 gold_control 和 gold_assisted；每 300 条保存暂停检查记录。
7. 解盲后只对真实分歧共同裁决；C 抽查 30–50 条。
8. 构建 Gold；回连 creator/content group；执行隔离切分。
9. A/B 提供证据，D 终审 Dataset Card 和最终 Gate。

## 固定模板

- `templates/stage4_model_route_decision_TEMPLATE.json`
- `templates/stage5_C_batch_seal_TEMPLATE.json`
- `templates/stage6_annotation_guide_freeze_TEMPLATE.json`
- `templates/stage9_300_checkpoint_TEMPLATE.json`
- `templates/stage10_adjudication_TEMPLATE.jsonl`
- `templates/stage10_C_adjudication_spotcheck_TEMPLATE.json`
- `templates/stage11_near_duplicate_detection_TEMPLATE.json`
- `templates/stage12_D_final_review_TEMPLATE.md`

模板必须复制到正式路径后由真实责任人填写；不得直接把模板状态改名当成完成证据。
