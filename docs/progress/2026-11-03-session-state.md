# M1 标注会话状态快照（2026-11-03 18:55）

> 用途：压缩上下文，供后续会话快速恢复。细节以仓库文件和本文引用为准。
> **标注已收尾，交付说明见 [2026-11-03-m1-annotation-delivery.md](./2026-11-03-m1-annotation-delivery.md)。**

## 一、当前进度

| 项目 | 状态 |
| --- | --- |
| 分支 | `P1-m1-gate-reconcile` |
| 384 批标注 | **384 / 384 完成**（53 条含修订） |
| 116 批（人工基线） | 完成并已补正，OOS 由 15 降至 8 |
| Gold 合并 | **479 条三元**（非广 386 / 暗广 52 / 明广 41） |
| M1 门禁 | 仍 `passed=false`（Gold 479/1500、Dataset Card、切分泄漏、κ） |
| 标注服务 | **已关闭**（8766 / 8767 无监听） |

当前 479 条标签分布：非广 386、暗广 52、明广 41。排除 24 条（采集失败 8、oos 8、uncertain 8）。

## 二、本轮完成的事

1. **正式候选池落地**：`data/reports/m1/privacy/formal_3312_v2/`（2,932 批准 / 380 排除，SHA `53d7e707…`）。
2. **正式锁批**：四批 2,050 唯一 ID、批间交集 0、状态 `locked`。
3. **标注工具改造**（已提交 `b679d16`、`f8646e4`）：
   - `scripts/start_m1_gold.ps1` 按波次启动，需 UTF-8 BOM
   - `auto_judge.run_openai_compat_judge()` 外部 API 后端
   - `batch_pre_annotate --backend/--api-*`、`--creator-history-pool`
   - `annotation_workbench/file_suggestions.py` 离线建议源（119 ms 返回）
4. **AI 预跑**：500 条 DeepSeek v4-pro、100 并发、0 错误、18 分钟、弃答率 24%。
5. **116 条对照**：一致率 91.25%、κ=0.493、暗广召回 0/5。
6. **根因定位**：暗广为 0 是 `collection_complete=unknown` 触发强制 uncertain，非能力缺陷。设为 true 后 40 条抽样出现 2 条暗广（5%），与人工 4.3% 接近。
7. **规则文档**：`docs/annotation_rules_supplement_20261102.md`（S-1～S-9）、`docs/annotation_changelog.md`。
8. **执行记录**：`docs/progress/2026-11-02-m1-annotation-cycle.md`。
9. **384 批完成 + Gold 合并**：新增 `merge_gold_batches.py`，输出 `data/reports/m1/gold/`（479 条三元）。
10. **116 批补正**：12 条 `out_of_scope` 中 9 条改判，oos 15 → 8，暗广 5 → 6。

## 三、已确立的标注规则

| 编号 | 规则 |
| --- | --- |
| S-1 | 采集失败（正文 <15 字/仅样板文字）→ uncertain + 置信度 0 + 备注「采集失败」，剔除不计入 Gold |
| S-2 | 收藏集/数字周边类有购买链接时必须记 `A` 码 |
| S-3 | 游戏实况：长期系列倾向非广；单集作品实况倾向暗广 |
| S-4 | 官方/自营账号**销售导向**内容 → 明广（账号身份记 D）；运营/信息性内容不判广 |
| S-5 | 自我宣传：自述归属 → 明广（D）；隐瞒归属 → 暗广 |
| S-6 | B站无外链 ≠ 无商业意图，`A` 码非必要条件；单一产品+只夸不提缺点+首发/送测 = 合作信号；**必须排除反讽/玩梗**（评论显示「演」「梗」则为非广） |
| S-7 | **游戏引流本身就是商业关系，不限购买**：商业对象可为下载/预约/注册/开服/区服/礼包码/充值；`C` 码适用于「单一游戏即内容核心」，`A` 码含下载预约类动作；S-3 的单集/系列降级为代理信号 |
| S-8 | **比赛/赛事推广按「是否对被推广者形成商业对价」分流**（沿用 EC-21）：被推广者是观众/买家（带动商品销售）→ 在范围内；被推广者是参赛者且零对价（高校创新赛/生态赛/公益赛）→ oos；平台自办社区运营 → 非广 |
| S-9 | **视频源失效（link rot）单独处理**：设计上需手动访问 B站链接看视频；链接失效即证据通道永久关闭 → uncertain + 置信度 ≤0.5 + 不进 Gold；单独计数 `source_gone_video`，与 S-1 采集失败分开；不得由删帖推断标签 |

## 四、关键数据事实（避免重复踩坑）

| 事实 | 数值 |
| --- | --- |
| B站技术类含外链比例 | 16%（88/551） |
| B站整体含外链比例 | 10.4% |
| 人工暗广使用 A 码比例 | 0/5 |
| 模型判非广的 B站帖中无链接比例 | 92% |
| `blogger_history_refs` 可解析率 | **0%**（836 个 24 位 ID 全为死链，爬虫库不存在） |
| 同博主历史可用比例 | 100%（平均 51.6 帖），已用于提示词 |
| 采集失败（全池） | 12.2%（358/2932） |
| 346 批媒体构成 | 含视频 37.3%、纯文本 30.6%、可读图片 24.6%、缩略图仅 5.8% |
| AI 建议模态 | **纯文本，`--no-images`，模型从未看过图片** |

## 五、待办（按优先级）

1. **B / 组长决策**：S-1～S-9 是否形成 v1.1、Gold 是否仍坚持 1,500、是否执行第二轮 κ、切分与 Dataset Card。
2. **低置信度复核**：14 条（<0.6），见 `data/reports/m1/gold/report.json` 的 `review_queue.low_confidence_post_ids`。
3. **正文过短且无媒体样本裁定**：7 条 B站「分享图片」类动态（`review_queue.thin_content_post_ids`）。脚本未自动排除，需人工决定是否按 S-1 剔除；剔除后 Gold 为 472。
4. **重跑 M1 门禁**：`python data-tooling\m1_readiness.py gate --gold-report data\reports\m1\gold\report.json ...`，`gold` 将显示 479/1500 仍 failed。
5. **口径待定**：`私有案例-03`（受邀 Chanel）；`私有案例-04` 的 S-5 例外理由待 A 书面确认。

## 六、已知方法学问题

1. **采集链路倒置**（A 提出）：合理流程应在平台上直接判断并填写，而非先爬取再离线判断。当前 12.2% 采集失败、29% 标题缺失、B站视频口播不可得，都是倒置流程的后果。
2. **AI 模态缺失**：模型无图片、无视频口播，图文类内容人工占优。
3. **视频源失效（link rot）**：设计上需标注者手动访问 B站链接观看视频判断，但数据层只保留 `source_url`（384 批 144 条视频记录，`caption`/`ocr_text`/`ref` 全部为空）。部分链接现已失效且无法补采 → 按 S-9 判 uncertain 不进 Gold，单独计数，与 S-1 采集失败分开披露。
4. **标注标准演进**：S-4～S-9 在中途引入，前后批次分布不一致。**注意归因未定**：同池对比显示 11-02 与 11-03 之间存在显著校准漂移（z=2.43），但规则成文时间晚于漂移发生时间，且规则成文后暗广率下降，因此不能归因于规则本身；抽样误差（n=58 的切片 CI 9.6–28.9）同样不可忽略。详见交付说明第七节。
5. **创作者历史字段失效**：`blogger_history_refs` 死链，改用同博主帖子重建。

## 七、关键文件

| 路径 | 说明 |
| --- | --- |
| `docs/annotation_rules_supplement_20261102.md` | S-1～S-9 规则 |
| `docs/progress/2026-11-03-m1-annotation-delivery.md` | **交付说明（给组长/B）** |
| `docs/progress/2026-11-02-m1-annotation-cycle.md` | 执行记录与 API 授权披露 |
| `scripts/start_m1_gold.ps1` | 波次启动（`human120` / `ai384`） |
| `data-tooling/annotation/merge_gold_batches.py` | Gold 合并脚本（保留 `gold_tier` 分层） |
| `data/reports/m1/gold/` | Gold 产物（`gold_all` / `gold_tri` / `gold_excluded` / `report.json`，不入库） |
| `data/reports/m1/locked_batches/` | 四批清单 + 波次清单 |
| `data/annotations/preannotated/gold_ai_round2_346/` | 346 条建议（图文 217 声明采集完整 + 视频 129 保持 unknown） |
| `data/annotations/workbench/m1_formal_3312_v2/m1_gold_ai_384/A/annotations.jsonl` | 384 批标注日志（append-only） |
| `data/workbench_..._gold_human_120_A_20261103_1851.json` | 116 批补正后导出（合并输入） |
| `data/workbench_..._gold_ai_384_A_20261103_1851.json` | 384 批导出（合并输入） |
