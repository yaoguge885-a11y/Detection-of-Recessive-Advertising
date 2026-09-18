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
| post_05ae08121794bdd1cd669e4f6e1f5399 | bilibili | 非广 | absent | 0.0 | unknown |
| post_195a03c4f90c0c9f622d196432946e2c | bilibili | 非广 | absent | 0.06 | unknown |
| post_1a9a9b87dcd51b45041095c55d807926 | bilibili | 非广 | absent | 0.08 | unknown |
| post_1ef042cf6c74c1165b48891f65470558 | bilibili | 非广 | absent | 0.0 | unknown |
| post_35009204fb2ca453978f7f8b743a9231 | bilibili | 需复核 | absent | 0.17 | unknown |
| post_3b26c4afacaefada95a7ec75fc0c1f6d | wechat_official_account | 明广 | present | 0.75 | disclosed |
| post_4976c1906d5f3a1bbaffbe85ff456048 | bilibili | 需复核 | absent | 0.0 | unknown |
| post_4ae53c9b8c1121ab4cc886accc3e48fa | wechat_official_account | 需复核 | absent | 0.33 | unknown |
| post_6359044c941c302d243bcc9d08d32b85 | bilibili | 非广 | absent | 0.0 | unknown |
| post_8d906895fb07ee1a549adbb507d10e9a | bilibili | 需复核 | absent | 0.06 | unknown |
| post_9b50147811564580bf67424ebfa032fa | wechat_official_account | 需复核 | absent | 0.06 | unknown |
| post_a4739762d272497d63110b5139c5d74d | wechat_official_account | 需复核 | absent | 0.31 | unknown |
| post_af7e39bb0e54bf462113b52b344e7691 | bilibili | 非广 | absent | 0.0 | unknown |
| post_c05468eb3c162f7ec213ebca858d5c5a | wechat_official_account | 需复核 | absent | 0.17 | unknown |
| post_c3d233ed2bcc8a712aea7a9a9fe1f910 | bilibili | 需复核 | absent | 0.0 | unknown |
| post_dfd50b13367a926f3b1af89c9a694208 | bilibili | 非广 | absent | 0.0 | unknown |
| post_e81e997c02e88e4c55fc8b2fde052e6f | wechat_official_account | 需复核 | present | 0.53 | unknown |
| post_ef75aaf8a7c2227767714e7928dcdde1 | wechat_official_account | 需复核 | absent | 0.17 | unknown |
| post_f238e64ecdf83a21194134f348d3a166 | bilibili | 非广 | absent | 0.08 | unknown |
| post_f5cef696ef1822726a436bcc82a2de77 | wechat_official_account | 需复核 | absent | 0.31 | unknown |

## 5. 结论

- 确定性基线对 **暗广（隐性广告）完全无效**：0/20 召回，这是本项目的核心目标类别。
- 基线高度保守：42 条被判 需复核，而预标注只有 3 条 manual（不确定）+ 4 条 out_of_scope。
- 基线把大量 非广 判成 需复核/明广，且把 5 条 明广 部分判成 非广/需复核，仅凭关键词规则的意图分不足以支撑隐性广告判定。
- 结论：现有 `deterministic_baseline_v1` 不能作为 M1 判断基线；要把 LLM 接进 judge 才可能复现/超越预标注质量。
