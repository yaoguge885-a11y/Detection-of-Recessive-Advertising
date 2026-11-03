# M1 标注阶段交付说明（2026-11-03）

> 分支：`P1-m1-gate-reconcile`
> 状态：**标注工作已完成并合并，M1 门禁仍未通过**

## 一、一句话结论

单标注人路线下完成了 **503 条**标注，合并出 **479 条三元 Gold 候选**（非广 386 / 暗广 52 / 明广 41）。
原计划 1,500 条双人 Gold、正式 κ、切分与 Dataset Card 均未完成，M1 门禁 `passed=false`。

## 二、实际完成的工作

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 正式候选池落地 | 完成 | `data/reports/m1/privacy/formal_3312_v2/`，2,932 批准 / 380 排除，SHA `53d7e707…` |
| 正式锁批 | 完成 | `locked_batches/`，2,050 唯一 post_id，批间交集 0，状态 `locked` |
| 标注批次 1（无 AI 盲标） | 完成 | `m1_gold_human_120`，119 条导出，含 1 轮补正，Gold 候选 108 条 |
| 标注批次 2（AI 辅助人工确认） | 完成 | `m1_gold_ai_384`，384 条全部完成，53 条含修订，Gold 候选 371 条 |
| 批间重叠 | 0 | 两批 post_id 无交集，可直接合并 |
| Gold 合并 | 完成 | 479 条三元标签，见第四节 |
| M1 门禁 | **未通过** | 见第五节 |

## 三、标注工具与产物

新增/修改的代码（均在 `data-tooling/annotation/`）：

| 文件 | 作用 |
| --- | --- |
| `merge_gold_batches.py` | **新增**。合并单标注者分批导出，保留 `gold_tier` 分层（`blind_human` / `human_assisted`），输出可直接接门禁的 `gold_count` |
| `auto_judge.py` | 新增外部 API 后端 `run_openai_compat_judge()`；新增创作者历史注入 |
| `batch_pre_annotate.py` | 新增 `--backend` / `--api-*` / `--creator-history-*` |
| `file_suggestions.py` | **新增**。离线建议源，避免逐条调模型（119 ms 返回） |
| `scripts/start_m1_gold.ps1` | 按波次启动工作台，需保存为 UTF-8 with BOM |

与既有 `build_gold_dataset.py` 的分工：后者要求 `annotation_method == "human"` 的双人盲标，会把 384 批的 `human_assisted` 全部排除为 `non_human_method`，因此另写了合并脚本，**不修改**原脚本行为。

## 四、Gold 合并结果

**文件位置**：

| 文件 | 条数 | 路径 |
| --- | ---: | --- |
| **`gold_tri.jsonl`** | **479** | `data/reports/m1/gold/gold_tri.jsonl` |
| `gold_all.jsonl` | 503 | `data/reports/m1/gold/gold_all.jsonl` |
| `gold_excluded.jsonl` | 24 | `data/reports/m1/gold/gold_excluded.jsonl` |
| `report.json` | — | `data/reports/m1/gold/report.json` |

绝对路径：`D:\projectsnew\Detection-of-Recessive-Advertising\data\reports\m1\gold\`

**479 条金标就是 `gold_tri.jsonl`**，一行一条 JSON，含 `label` / `confidence` / `evidence_codes` / `post_id` / `gold_tier` / `batch_id` 等字段。
该目录已在 `.gitignore`，不入版本库，需在本地或通过打包传递。

输入 503 条唯一记录 → **479 条 Gold 候选** + 24 条排除。

| 标签 | blind_human（116 批） | human_assisted（384 批） | 合计 |
| --- | ---: | ---: | ---: |
| 非广 | 89 | 297 | **386** |
| 暗广 | 6 | 46 | **52** |
| 明广 | 13 | 28 | **41** |
| 小计 | 108 | 371 | **479** |

排除 24 条：采集失败 8、`out_of_scope` 8、`uncertain` 8。
分批次看：批次 1 排除 11 条（采集失败 4 / oos 3 / uncertain 4），批次 2 排除 13 条（采集失败 4 / oos 5 / uncertain 4）。

产物在 `data/reports/m1/gold/`（已 `.gitignore`，含真实 post_id 不入库）：

| 文件 | 条数 | SHA-256 前缀 |
| --- | ---: | --- |
| `gold_all.jsonl` | 503 | `40f5121dc58fc879` |
| `gold_tri.jsonl` | 479 | `b702585eef9f3265` |
| `gold_excluded.jsonl` | 24 | `147d3d592e967818` |
| `report.json` | — | 分布、分层、排除原因、复核队列 |

复现命令：

```powershell
python data-tooling\annotation\merge_gold_batches.py `
  --input "blind_human=data\workbench_m1_formal_3312_v2_m1_gold_human_120_A_20261103_1851.json" `
  --input "human_assisted=data\workbench_m1_formal_3312_v2_m1_gold_ai_384_A_20261103_1851.json" `
  --pool "data\reports\m1\privacy\formal_3312_v2\formal_eligible_candidates.jsonl" `
  --out-dir "data\reports\m1\gold"
```

## 五、M1 门禁现状

`data/reports/m1/m1_gate_report.json`，`passed=false`。

| 检查项 | 状态 | 现状 / 要求 |
| --- | --- | --- |
| `annotation_guide` | 通过 | 边界案例数量达标 |
| `candidate_pool` | 通过 | 2,932 条唯一候选 |
| `gold` | **失败** | 479 / 1,500 |
| `dataset_card` | **失败** | 未完成 |
| `split_leakage` | **缺失** | 未切分，泄漏计数为 `null` |
| `agreement` | 需复核 | 无第二轮正式 κ（`formal_second_round=false`） |
| `compliance` | 需复核 | 隐私/条款状态待确认 |

说明：门禁报告中 `gold.observed = 0` 是因为此前未传 `--gold-report`。现在可用：

```powershell
python data-tooling\m1_readiness.py gate --gold-report data\reports\m1\gold\report.json ...
```

重跑后 `gold` 会显示 479 / 1,500，仍为 `failed`。

## 六、标注规则的变更（重要，需 B 书面确认）

v1.0 冻结指南在标注过程中暴露了空白。实际执行中提出 9 条补充规则，记录于
[docs/annotation_rules_supplement_20261102.md](../annotation_rules_supplement_20261102.md)。

| 编号 | 规则 | 影响 |
| --- | --- | --- |
| S-1 | 采集失败（正文空壳 / 验证码页）→ 剔除，不计入 Gold | 排除 8 条 |
| S-2 | 收藏集/数字周边有购买链接必须记 `A` | 证据码完整性 |
| S-3 | 游戏实况按更新形态区分 | **已被 S-7 降级为代理信号** |
| S-4 | 官方/自营账号**销售导向**内容 → 明广；运营性内容不判广 | 影响明广判定 |
| S-5 | 自我宣传：自述归属 → 明广；隐瞒归属 → 暗广 | 影响明广/暗广边界 |
| S-6 | B站无外链 ≠ 无商业意图，`A` 码非必要条件；须排除反讽 | 影响暗广召回 |
| S-7 | 游戏引流本身就是商业关系（下载/预约/开服/礼包码均算） | 影响暗广边界 |
| S-8 | 比赛/赛事按「是否对被推广者形成商业对价」分流 | 影响范围声明 |
| S-9 | 视频源失效（link rot）→ uncertain + 不计入 Gold | 见第七节 |

**这些规则尚未形成 v1.1，`docs/annotation_guide_v1.md` 保持冻结。**
批次 1 的导出保留 `guide_version=1.0` 与 `guide_sha256=1ed142c6…`，不得改写。

## 七、必须在论文中披露的方法学问题

1. **标注标准中途演进导致批次不可比**
   批次 1（108 条 Gold 候选）暗广率 **5.6%**（6/108，Wilson 95% CI 2.6–11.6），
   批次 2（371 条）暗广率 **12.4%**（46/371）。两批使用不同来源清单：
   批次 1 全部来自 `gold_control[0:120]`，批次 2 = `gold_control[120:180]`（60 条）+ `gold_assisted[0:324]`（324 条）。

   **同池自然实验**（同一 `gold_control` 清单、同一次随机抽样，仅标注时点不同）：

   | 分组 | 标注时点 | 暗广 | 率 | Wilson 95% CI |
   | --- | --- | ---: | ---: | --- |
   | `control[0:120]` | 11-02 | 6/108 | 5.6% | 2.6–11.6 |
   | `control[120:180]` | 11-03 | 10/58 | 17.2% | 9.6–28.9 |
   | `assisted[0:324]` | 11-03 | 36/313 | 11.5% | 8.4–15.5 |

   按平台分层后差异仍在（B站 6.1% → 16.3%，公众号 4.8% → 20.0%），不是平台构成造成。

   **可以确定的**：11-02 与 11-03 之间存在标注校准漂移，且同池对比达到统计显著（两比例 z=2.43，p<0.05）。
   **不能确定的**：
   - 该差异**不能归因于 S-4～S-9 的规则累积**。规则文档提交时间为 11-03 15:46（S-4/S-5/S-6）、15:58（S-7），
     而 384 批自 11-03 10:07 开始标注，且暗广率在**前**四分之一最高：Q1 15.6% → Q2 11.5% → Q3 11.5% → Q4 9.4%。
     规则成文后暗广率是下降的，与「规则放宽导致更多暗广」的假设相反。
   - 两批之间的抽样误差真实存在且不可忽略。`control[120:180]` 仅 58 条，17.2% 的置信区间横跨 9.6–28.9；
     同为 11-03 标注的 `control[120:180]`（17.2%）与 `assisted[0:324]`（11.5%）差异**不显著**（z=−1.22）。
     即 17.2% 这个点估计本身不可靠。
   - 现有 479 条无法把「抽样误差」「跨日校准漂移」「批次疲劳」三者分解开。

   **结论**：两批标签分布**不得直接比较，也不能合并后当作单一同质样本报告**。
   论文中应如实说明该差异存在但归因不可识别，并优先用同一标注时窗内的数据做任何涉及类别的分析。
   若要给出可解释的暗广率，需追加同一时窗内、同一规则下的重新标注（见第八节待决事项 3）。

2. **Gold 不是双人盲标产物**
   `blind_human` 108 条，`human_assisted` 371 条。后者标注者看过模型建议，
   不能用于计算一致性 κ，也不能声称独立盲标。合并文件用 `gold_tier` 分层保留该区别。

3. **视频源失效（link rot）**
   视频类帖设计上要求标注者手动访问 B站链接观看后判断，数据层因硬盘限制只保留 `source_url`。
   384 批 144 条视频记录中 `caption` / `ocr_text` / `ref` 命中率均为 **0**。
   部分链接现已失效且无法补采 → 按 S-9 判 `uncertain` 不进 Gold。
   建议单独披露 link-rot 率，与采集失败率分开。

4. **采集链路倒置**
   合理流程应在平台上直接判断并填写，而非先爬取再离线判断。
   全池 12.2% 采集失败、29% 标题缺失（`title="None"` 字面字符串）、B站视频口播不可得，
   都是倒置流程的后果。

5. **AI 建议全程 `--no-images`**
   模型从未看过任何图片或视频画面。`post_20f8699268` 这类需要画面证据的样本，
   AI 建议只有文本依据。

6. **创作者历史字段失效**
   `blogger_history_refs` 的 836 个 24 位 ID 全部无法解析（爬虫库不存在），
   已改用同博主帖子重建（100% 可用，平均 51.6 帖/博主）。

## 八、已知缺口与待决事项

### 需要 B / 组长决定的

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | S-1～S-9 是否形成 v1.1 | 需 A、B 书面共识并指定生效批次；当前生效状态待定 |
| 2 | Gold 规模是否仍坚持 1,500 | 现有 479。按当前效率，补到 1,500 需再利用剩余 1,547 条候选池，工作量约 3 倍于已完成部分 |
| 3 | 是否执行第二轮 κ | 门禁 `agreement` 需 `formal_second_round=true`，必须双人盲标。也是消除本批次校准漂移的唯一办法 |
| 4 | 数据切分与泄漏检查 | 门禁 `split_leakage` 缺失，需生成并按连通分量检查 creator / near_duplicate 泄漏 |
| 5 | Dataset Card 补齐 | 门禁 `dataset_card` 失败 |

### 需要 A 处理的（本次未做）

| # | 事项 | 数量 |
| --- | --- | --- |
| 1 | 低置信度（<0.6）复核 | 14 条，`report.json` 的 `review_queue.low_confidence_post_ids` |
| 2 | 正文过短且无媒体样本裁定 | 7 条，`review_queue.thin_content_post_ids`。这些是 B站「分享图片」类动态，正文 <40 字、无本地媒体、无标题，但标了非广。脚本未自动排除，需人工决定是否按 S-1 剔除 |
| 3 | `post_60be5c4859b86cd` 口径 | 受邀 Chanel，当前 `非广`，待统一定义 |
| 4 | `post_1c6ffcf384` 的 S-5 例外理由 | 维持暗广，但「独立品牌 vs 自述归属」的区分待 A 书面确认 |

## 九、相关文档索引

| 路径 | 内容 |
| --- | --- |
| [annotation_rules_supplement_20261102.md](../annotation_rules_supplement_20261102.md) | S-1～S-9 规则全文，含反例与实测数据 |
| [annotation_changelog.md](../annotation_changelog.md) | 规则变更记录 |
| [2026-11-02-m1-annotation-cycle.md](./2026-11-02-m1-annotation-cycle.md) | 上一轮执行记录（含外部 API 授权披露） |
| [2026-11-03-session-state.md](./2026-11-03-session-state.md) | 会话状态快照 |
| [annotation_guide_v1.md](../annotation_guide_v1.md) | 冻结的 v1.0 指南 |
| [P1_M1_双人任务书.md](../P1_M1_双人任务书.md) | A/B 分工权威定义（A-1～A-6、B-1～B-7） |

## 十、环境与复现注意事项

- 标注工作台端口 **8766/8767**（8765 被 VS Code 占用），已关闭。
- `scripts/start_m1_gold.ps1` 必须存为 **UTF-8 with BOM**，否则 Windows PowerShell 5.1 解析中文串失败。
- 标注日志 `annotations.jsonl` 为 append-only，每条即时落盘，无需手动保存。
- 工作台前端**不渲染 `source_url`**，视频类样本需依赖单独生成的链接清单访问。
- `data/annotations/`、`data/reports/m1/gold/`、`data/reports/m1/locked_batches/` 均不入库（含真实内容）。
