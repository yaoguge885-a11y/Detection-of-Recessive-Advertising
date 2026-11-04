# implicit-ad-agent 确定性基线 vs 预标注（100 条样本）

- 输入：`agent_baseline_result_20260916.json`（100 条，成功 100，失败 0）
- 预标注来源：`agent_sample100_manifest_20260916_231450.json`（同 100 条样本，seed=20260916）
- 判定方法：`deterministic_baseline_v1`（规则表，无 LLM）

## 1. 标签分布

| 标签 | 预标注 | 确定性基线 |
|------|-------:|-----------:|
| 明广 | 5 | 10 |
| 暗广 | 20 | 0 |
| 非广 | 68 | 48 |
| 需复核 | 3 | 42 |
| out_of_scope | 4 | 0 |
| 需复核 | 0 | 0 |

## 2. 混淆矩阵（排除 out_of_scope 后，行=预标注，列=基线）

| 预标注 \ 基线 | 明广 | 暗广 | 非广 | 需复核 | 合计 |
|------------|-----:|-----:|-----:|-------:|-----:|
| 明广 | 3 | 0 | 0 | 2 | 5 |
| 暗广 | 1 | 0 | 8 | 11 | 20 |
| 非广 | 4 | 0 | 38 | 26 | 68 |
| 需复核 | 0 | 0 | 1 | 2 | 3 |

## 3. 一致性与召回

- 4 类整体一致率（含 需复核，n=96）：**43/96 = 44.8%**，Cohen's κ = 0.131
- 3 类一致率（明广/暗广/非广，n=93）：**41/93 = 44.1%**，Cohen's κ = 0.118

| 类别 | 召回（基线命中 / 预标注总数） |
|------|-------------------------------|
| 明广 | 3/5 = 60.0% |
| 暗广 | 0/20 = 0.0% |
| 非广 | 38/68 = 55.9% |

## 4. 暗广漏判明细（核心任务）

预标注 暗广 20 条，基线命中 0 条。全部 20 条漏判如下：

| post_id | 平台 | 基线标签 | 意图状态 | 意图分 | 披露状态 |
|---------|------|---------|---------|-------:|---------|
| 私有样本-01 | bilibili | 非广 | absent | 0.0 | unknown |
| 私有样本-02 | bilibili | 非广 | absent | 0.06 | unknown |
| 私有样本-03 | bilibili | 非广 | absent | 0.08 | unknown |
| 私有样本-04 | bilibili | 非广 | absent | 0.0 | unknown |
| 私有样本-05 | bilibili | 需复核 | absent | 0.17 | unknown |
| 私有样本-06 | wechat_official_account | 明广 | present | 0.75 | disclosed |
| 私有样本-07 | bilibili | 需复核 | absent | 0.0 | unknown |
| 私有样本-08 | wechat_official_account | 需复核 | absent | 0.33 | unknown |
| 私有样本-09 | bilibili | 非广 | absent | 0.0 | unknown |
| 私有样本-10 | bilibili | 需复核 | absent | 0.06 | unknown |
| 私有样本-11 | wechat_official_account | 需复核 | absent | 0.06 | unknown |
| 私有样本-12 | wechat_official_account | 需复核 | absent | 0.31 | unknown |
| 私有样本-13 | bilibili | 非广 | absent | 0.0 | unknown |
| 私有样本-14 | wechat_official_account | 需复核 | absent | 0.17 | unknown |
| 私有样本-15 | bilibili | 需复核 | absent | 0.0 | unknown |
| 私有样本-16 | bilibili | 非广 | absent | 0.0 | unknown |
| 私有样本-17 | wechat_official_account | 需复核 | present | 0.53 | unknown |
| 私有样本-18 | wechat_official_account | 需复核 | absent | 0.17 | unknown |
| 私有样本-19 | bilibili | 非广 | absent | 0.08 | unknown |
| 私有样本-20 | wechat_official_account | 需复核 | absent | 0.31 | unknown |

## 5. 结论

- 确定性基线对 **暗广（隐性广告）完全无效**：0/20 召回，这是本项目的核心目标类别。
- 基线高度保守：42 条被判 需复核，而预标注只有 3 条 manual（不确定）+ 4 条 out_of_scope。
- 基线把大量 非广 判成 需复核/明广，且把 5 条 明广 部分判成 非广/需复核，仅凭关键词规则的意图分不足以支撑隐性广告判定。
- 结论：现有 `deterministic_baseline_v1` 不能作为 M1 判断基线；要把 LLM 接进 judge 才可能复现/超越预标注质量。
