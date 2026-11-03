# M1 标注会话状态快照（2026-11-03 15:47）

> 用途：压缩上下文，供后续会话快速恢复。细节以仓库文件和本文引用为准。

## 一、当前进度

| 项目 | 状态 |
| --- | --- |
| 分支 | `P1-m1-gate-reconcile`，最新提交 `f8646e4`（已推送） |
| 工作区 | `data-tooling/annotation/auto_judge.py` 等有未提交改动（创作者历史 + API 后端） |
| 384 批标注 | **227 / 384**，服务运行在 `http://127.0.0.1:8766/` |
| 116 批（人工基线） | 已完成，待按新规则复核（2 份复核包已生成） |
| M1 门禁 | 仍 `passed=false`（Gold 数量、切分、Dataset Card 未达标） |

当前 227 条标签分布：非广 169、暗广 29、明广 21、out_of_scope 6、uncertain 2。

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
7. **规则文档**：`docs/annotation_rules_supplement_20261102.md`（S-1～S-7）、`docs/annotation_changelog.md`。
8. **执行记录**：`docs/progress/2026-11-02-m1-annotation-cycle.md`。

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

1. **标完剩余 157 条**（384 批）。
2. **116 条补正**：
   - `review_oos_12.md`：12 条 out_of_scope 中仅 3 条成立，9 条需改
   - `review_anguang_candidates.md`：9 条候选，预计 3–4 条可改判暗广
3. **导出 + 质检**：384 批导出 JSON，跑与分析 116 批一致的 QC。
4. **提交代码**：`auto_judge.py`、`batch_pre_annotate.py`、规则文档的未提交改动。
5. **重跑 M1 门禁**并更新 Dataset Card。
6. **未完成的方法学说明**：标注协议演进对标签分布的影响（同源对照：116 批暗广 4.3% vs control 尾批 16.7%）。

## 六、已知方法学问题

1. **采集链路倒置**（A 提出）：合理流程应在平台上直接判断并填写，而非先爬取再离线判断。当前 12.2% 采集失败、29% 标题缺失、B站视频口播不可得，都是倒置流程的后果。
2. **AI 模态缺失**：模型无图片、无视频口播，图文类内容人工占优。
3. **标注标准演进**：S-4～S-7 在中途引入，导致前后批次分布不一致，需在论文中披露。
4. **创作者历史字段失效**：`blogger_history_refs` 死链，改用同博主帖子重建。

## 七、关键文件

| 路径 | 说明 |
| --- | --- |
| `docs/annotation_rules_supplement_20261102.md` | S-1～S-7 规则 |
| `docs/progress/2026-11-02-m1-annotation-cycle.md` | 执行记录与 API 授权披露 |
| `scripts/start_m1_gold.ps1` | 波次启动（`human120` / `ai384`） |
| `data/reports/m1/locked_batches/` | 四批清单 + 波次清单 |
| `data/annotations/preannotated/gold_ai_round2_346/` | 346 条建议（图文 217 声明采集完整 + 视频 129 保持 unknown） |
| `data/annotations/workbench/m1_formal_3312_v2/m1_gold_ai_384/A/annotations.jsonl` | 当前标注日志（append-only） |
| `data/workbench_..._gold_human_120_...json` | 116 条人工基线导出 |
