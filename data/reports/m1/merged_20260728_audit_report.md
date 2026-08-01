# merged_20260728 本地数据审计报告

> 输入：用户提供的外部 `merged_20260728.zip`
> 解压目录：`data/run_outputs/merged_20260728`（已被 Git 忽略）
> 审计日期：2026-07-31（报告时间戳使用 UTC，显示为 2026-08-01）
> 结论：数据结构与媒体完整性检查通过；M1 未通过

## 1. 执行摘要

本报告仅记录从用户提供 ZIP 中可复现的聚合事实。ZIP 原件未修改，正文、来源 URL、创作者 ID、标注者 ID 和媒体文件均未提交 Git。

权威候选文件 `anonymized_posts.jsonl` 共 2,901 条，全部通过 Schema v1.2 校验；帖子无重复，14,174 个唯一媒体引用均可定位。候选池距离 M1 要求的 3,000 条还差 99 条，且正式 Gold、第二轮盲标一致性、来源条款完成证明、隐私人工审批、无泄漏切分和 Dataset Card 审批仍缺失，因此 `m1_gate_report.json` 保持 `passed=false`。

## 2. ZIP 与输入边界

| 项目 | 结果 |
|---|---:|
| ZIP 文件数 | 16,577 |
| ZIP 未压缩总大小 | 3,720,266,111 bytes |
| JSONL 文件 | 2（不把 `.bak` 或 `_fixed` 重复计入候选池） |
| 图片条目 | 15,066 |
| 路径穿越条目 | 0 |
| 权威候选文件 | `anonymized_posts.jsonl` |

## 3. 候选与媒体聚合事实

| 指标 | 结果 |
|---|---:|
| 总记录 / 唯一帖子 | 2,901 / 2,901 |
| 重复帖子行 | 0 |
| 唯一创作者 | 108 |
| Bilibili | 2,182 |
| WeChat | 719 |
| 媒体引用 / 唯一引用 | 14,174 / 14,174 |
| 可用 / 缺失唯一引用 | 14,174 / 0 |
| 磁盘媒体文件 | 15,066 |
| 数据集指纹 | `adb39f1840df62cbeef52faabde85177536478c1c06d37bbb747a9a2bb59a3a5` |

## 4. Schema v1.2 校验

执行：

```powershell
python data-tooling\annotation\validate_schema.py `
  data\run_outputs\merged_20260728\anonymized_posts.jsonl `
  --target-schema 1.2 `
  --schema data-tooling\schema\data_schema_v1_2.json `
  --report data\reports\m1\merged_20260728_schema_validate.json
```

结果：2,901 条有效，0 条无效。此次命令未启用隐私扫描，因此报告中的 `privacy_findings` 为 `disabled`，不能据此声称隐私已通过。

## 5. M1 统一门禁

| 检查项 | 当前值 | 要求 | 状态 |
|---|---:|---:|---|
| 标注指南边界案例 | 24 | ≥20 | passed |
| 唯一候选 | 2,901 | ≥3,000 | failed |
| 正式 Gold | 0 | ≥1,500 | failed |
| 第二轮正式 κ | pilot 1.0 | 正式 κ ≥0.6 | review_required |
| 条款 / 隐私审批 | false / false | 均为 true | review_required |
| 创作者 / 近重复泄漏 | 未生成 | 均为 0 | missing |
| Dataset Card 审批 | false | true | failed |

最终门禁：`passed=false`，命令退出码 2（符合预期）。

## 6. 合规边界

- 2,901 条记录均自述 `anonymized=true`、`contains_sensitive_data=false`，但这只是数据字段声明，不是隐私人工审批证据。
- 当前候选中 `terms_checked_at` 可计数记录为 0；来源台账仍为 `review_required`。
- 本次没有执行或宣称 PII 人工复核、原地掩码、公开发布审批。
- 自动标注和历史 pilot 标注都不计入正式 Gold，也不替代独立双标与仲裁。

## 7. 报告索引

| 文件 | 说明 |
|---|---|
| `data/reports/m1/dataset_full_audit.json` | 当前 ZIP 的安全聚合审计 |
| `data/reports/m1/merged_20260728_schema_validate.json` | Schema v1.2 校验结果 |
| `data/reports/m1/m1_gate_report.json` | M1 统一门禁结果 |
| `docs/dataset_card_current.md` | 当前数据集工作快照 |
| `docs/数据来源合规台账.md` | 来源与合规待办 |
