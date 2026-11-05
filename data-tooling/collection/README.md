# 标注前置采集方案（v1.3）

> 状态：`proposed`（方案已定，尚未接入正式批次）
> 建立日期：2026-11-05
> 解决的问题：采集链路倒置

## 1. 问题定义

原流程是**先爬取、再离线判断**。这导致判定所需的前提信息在采集阶段就已丢失，事后无法补救。

以下数字来自 `formal_3312_v2` 全池 2,932 条实测：

| 症状 | 数量 | 占比 |
| --- | ---: | ---: |
| `collection_complete` 字段为 `None` | 2,932 | **100%** |
| 标题为字面字符串 `"None"` | 852 | 29.1% |
| 仅有视频 `source_url`，无本地文件、无 `caption`、无 `ocr_text` | 1,071 | 36.5% |
| 评论为空 | 700 | 23.9% |
| 采集失败（验证码壳页 / 正文 <40 字） | 107 | 3.6% |

### 1.1 最关键的断裂

v1.0 判定暗广的前提是「**相关披露区域已完整采集**，仍未发现明确披露」。

但 `collection_complete` 全池为 `None`，而工作台把它当作采集状态的唯一来源：

```
collection_complete = None
  → disclosure_view 判定为 unknown
    → 按 v1.0，unknown 不得推导暗广
```

实际标注中仍产出了 52 条暗广，而标注记录里**没有任何**字段承载这个前提：

| 字段 | Gold 记录中是否存在 |
| --- | --- |
| `disclosure_status` | 无 |
| `collection_complete` | 无 |
| `viewed_media` | 无 |

结论：52 条暗广的判定前提**一条记录都没有留下**，事后不可审计。这是流程倒置的直接后果，而不是标注质量问题。

## 2. 方案：人的观察是权威，爬虫只做回填

核心转变：**判断不再依赖爬虫是否成功**。

### 2.1 字段权威归属

| 人工填写（权威，不被覆盖） | 爬虫回填（派生，可重复执行） |
| --- | --- |
| `intake.source_url` 原始链接 | `post_id`（由 URL 派生，无需爬虫） |
| `intake.viewed_media` 是否真看完媒体 | `title` / `text` |
| `intake.disclosure_status` 亲眼确认的披露状态 | `media[]` |
| `intake.disclosure_note` 在哪看的、看到什么 | `comments[]` |
| `intake.draft_label` / `draft_evidence` 初判与理由 | `blogger_id` / `published_at` |
| `intake.annotator_id` / `intake_at` | `backfill.status` / `backfill.attempted_at` |

### 2.2 完整性改为推导值

`collection_complete` 不再由谁单方面声明，而是两个事实共同决定：

```python
def derive_collection_complete(viewed_media, backfill_status):
    if viewed_media == "full" and backfill_status == "ok":
        return "complete"
    if viewed_media in ("full", "partial"):
        return "incomplete"
    return "unknown"
```

要点：**爬虫失败不会让这条样本作废**。人已经在平台上看到内容并记录，记录依然有效，只是完整性降为 `incomplete`，披露判定仍可依据 `intake.disclosure_status`。

### 2.3 post_id 无需爬虫即可确定

`post_id = "post_" + sha256(salt + url)[:32]`，只依赖 URL。

已实测：从既有候选池取 8 条 bilibili 记录，用 `intake_cli.derive_post_id` 重新计算，**8/8 完全一致**。因此录入时就能生成稳定 ID，回填时精确对齐，不依赖执行顺序。

## 3. 使用方式

### 3.1 录入（人工）

```powershell
.venv\Scripts\python.exe data-tooling\collection\intake_cli.py `
  --out data/collection/intake.jsonl --annotator A
```

逐条询问：链接 → 标题 → 正文摘要 → 是否看完媒体 → 披露状态 → 披露判断依据 → 初判 → 置信度 → 理由。

内置两条自检：

- 声明 `absent_complete`（披露区完整且无披露）但 `viewed_media != full` → 警告「暗广判定依据不足」
- 初判暗广但 `disclosure_status != absent_complete` → 提示「记录后需复核」

同一链接重复录入会被识别并跳过。

### 3.2 回填（爬虫）

```powershell
.venv\Scripts\python.exe data-tooling\collection\backfill.py `
  --intake data/collection/intake.jsonl --out data/collection/intake_backfilled.jsonl
```

只写入爬虫负责的字段，重算 `collection_complete`，不改动 `intake.*`。当前为待接入状态，尚未绑定具体平台爬虫实现。

## 4. 字段定义（schema v1.3）

新增 `intake` 与 `backfill` 两个对象定义，`content_record` 增加 4 个顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `collection_complete` | enum \| null | 由 `intake.viewed_media` + `backfill.status` 推导 |
| `disclosure_status` | enum \| null | 顶层冗余，供工作台直接读取 |
| `intake` | object | 人工观察记录，权威 |
| `backfill` | object | 爬虫回填结果，派生 |

`intake.viewed_media`：`full` / `partial` / `none`
`intake.disclosure_status`：`present` / `absent_complete` / `missing`
`backfill.status`：`ok` / `partial` / `failed` / `pending`

### 4.1 兼容性

- 全部新增字段**可选**，v1.2 旧记录无需迁移。
- 已实测：用 v1.3 schema 校验既有 `formal_eligibility_candidates.jsonl` 记录，**直接通过**。
- `blogger_id` 在 v1.3 放宽为允许 `null`：录入时不知博主，需回填，不得猜测填充。

## 5. 对既有 Gold 的处理边界

**不回溯修复 479 条既有 Gold。**

理由：那 479 条的 `disclosure_status` 与 `collection_complete` 从未记录，无法补录——补录等于凭记忆重建，与「亲眼看过后填写」的性质不同，反而制造虚假可审计性。

处理方式：

- 479 条在 Dataset Card 中标注「披露完整性前提未记录，暗广判定依据不可逐条追溯」
- 52 条暗广单独披露该限制
- 新方案自下一批次起生效

## 6. 已知限制

1. **人工观察无法机器验证**：`viewed_media=full` 是自述，没有机制证明真看过。这是换取「不依赖爬虫」的代价。
2. **录入成本上升**：每条需人多填 5 个字段，估计每条 +20–30 秒。
3. **回填仍可能失败**：只是失败不再致命，会体现为 `incomplete`。
4. **`collection_complete=complete` 的语义更强**：现在是「人看全 + 爬虫补全」双条件，比原来「爬虫说成功」更严格，可能使可达 `complete` 的比例下降。
5. **未解决视频口播的结构化抽取**：`viewed_media=full` 只记录「看过」，口播里的披露话术仍需人工转写进 `disclosure_note`。

## 7. 后续接入步骤

1. **选定试点批次**：建议从剩余候选池抽 50–100 条，不改动已锁批次。
2. **绑定回填实现**：复用 `data-tooling/crawler/bilibili_crawler.py` 与 `sogou_wechat_crawler.py` 的单个帖子抓取函数，失败置 `backfill.status=failed`。
3. **接入工作台**：`display_post` 已能读顶层 `disclosure_status` 与 `collection_complete`，需补 `intake.viewed_media` 与 `intake.disclosure_note` 的展示。
4. **加校验门禁**：批量导入前用 `schema_v1_3.json` 校验；`draft_label=暗广` 但 `disclosure_status != absent_complete` 的记录进入复核队列。
5. **对比实验**：同批样本用新旧流程各跑一遍，比较采集失败率、可审计比例、单条耗时。

## 8. 文件

| 文件 | 说明 |
| --- | --- |
| `schema_v1_3.json` | JSON Schema，v1.2 基础上新增 intake / backfill |
| `intake_cli.py` | 终端交互式录入工具 |
| `backfill.py` | 回填工具（从 intake 生成回填后记录） |
| `test_collection.py` | 单元测试 |
