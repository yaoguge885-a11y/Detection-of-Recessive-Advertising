# 正向构建采集方案（v1.4）

> 状态：`proposed`
> 建立日期：2026-11-06
> 决策：**AI 只做预标注，人做最终标注**（产出可称 Gold）；**评论双排序各取 10 条**

本方案与 [README.md](./README.md)（v1.3 标注前置采集）的关系：v1.3 解决「人的观察是权威、爬虫只回填」，v1.4 在此之上补齐**采集阶段必须固定住的判定用途字段**，并把 AI 预标注纳入流程。两者可叠加使用。

## 1. 为什么要重做采集

在既有全池 2,932 条上实测出三个缺口，其中第一个是硬缺陷。

### 1.1 评论实际只采到 3 条

| 评论数 | 帖子数 | 占比 |
| ---: | ---: | ---: |
| 0 | 700 | 23.9% |
| 1 | 12 | 0.4% |
| 2 | 26 | 0.9% |
| **3** | **2,194** | **74.8%** |
| > 3 | **0** | 0% |

在原始采集输出 `data/run_outputs/bilibili_20260728_130630/anonymized_posts.jsonl`（1,517 条）中同样是：984 条恰好 3 条、522 条 0 条、最大 3。**不是下游截断，是采集时就只有 3 条。**

**根因**（已定位到代码）：

```python
# bilibili_crawler.py:1367
session = requests.Session()   # 空 session，无任何 Cookie

# bilibili_crawler.py:877
params={"type": comment_type, "oid": oid, "pn": page, "ps": 20, "sort": 1}
```

Playwright 预热得到的 `storage_state`（含 SESSDATA）只用于抓 HTML，**从未注入 requests.Session**。B站评论接口在匿名状态下只返回 3 条热评，`max_comments=50` 实际无效。

**后果**：S-6「反讽排除」规则要求以评论区佐证（「演」「梗」「太像了」），52 条暗广的判定里评论证据几乎为空。这是一条写在规则里、但没有数据支撑的判据。

### 1.2 tags 从未采集

| 检查项 | 结果 |
| --- | --- |
| schema 有 `tags` 字段 | 无 |
| 爬虫调用 tag 接口 | 无 |
| AI 提示词使用 tag | 无 |
| 现有数据中 `#xxx#` 文本 | 53 条（1.8%），是正文井号，非平台 tag |
| 其中含披露词（广告/赞助/合作） | 0 |

### 1.3 简介与正文混淆

B站视频的 `desc`（简介）被直接塞进 `text`，并混入「视频播放量 151538、弹幕量 819、点赞数 5915……」等页面样板文字。

## 2. 五阶段流程

```
S1 采集（机器）  URL / creator 名单 → 结构化全字段
S2 核验（人）    打开平台亲眼确认 → intake
S3 预标注（AI）  S1 + S2 → pre_annotation（仅供参考）
S4 标注（人）    → label / confidence / evidence_codes（最终标签）
S5 质检仲裁      一致性、低置信、采集异常
```

**顺序不可调换的两处**：

- S2 必须在 S3 之前。`disclosure_status`（披露区域是否完整、是否发现披露）只有人能看平台确认，AI 无从得知。把它放在 AI 之后等于让 AI 猜前提。
- S3 的产出只能进 `pre_annotation`，**不得写入 `label`**。最终标签由 S4 人工给出。

## 3. S1 采集：字段清单

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `post_id` | `sha256(salt+url)[:32]` | 只依赖 URL，无需爬虫即可确定 |
| `platform` | URL 匹配 | |
| `blogger_id` | 平台作者 ID + salt | 即 creator_id |
| `published_at` | 平台 | |
| `title` | 平台 | 不得为字面字符串 `"None"`；取不到就置 `null` |
| `desc` | 平台简介 | **与 `text` 分离** |
| `text` | 平台正文 | 必须剥离页面样板 |
| `tags` | tag 接口 | 列表，保持原值 |
| `stats` | 平台 | 播放/点赞/收藏/投币/分享/弹幕/评论数，附 `collected_at` |
| `media[]` | 平台 | 视频至少记录 `source_url`；能落本地则记 `ref` |
| `comments[]` | 见 §4 | 双排序采集 |
| `comments_meta` | 见 §4 | 采集覆盖范围与时点 |

**硬性要求**：`title` 为 `null` 与 `title` 为 `"None"` 必须区分。前者表示确实没有标题，后者是抓取缺陷。既有 852 条（29.1%）犯了这个错。

## 4. S1 评论采集：最新 + 最热各 N

采用 N=10。

### 4.1 策略

```
第一步：取 total（首个响应中的 page.count）
若 total <= N：取一次即可，exhausted=true
否则：
  sort=latest 取 N 条
  sort=hot    取 N 条
  按 comment_id 合并去重
  每条记 sort_source: ["latest"] / ["hot"] / 两者都有
```

### 4.2 前提条件

**必须注入登录态**，否则永远只有 3 条：

```python
cookies = session_from_storage_state(storage_state)
session.cookies.update(cookies)
ok, missing = required_cookies_present(cookies)   # 检查 SESSDATA
```

### 4.3 接口选择

| 接口 | 参数 | 备注 |
| --- | --- | --- |
| `/x/v2/reply` | `sort=0` 最新 / `sort=1` 最热 | 老接口，匿名降级严重 |
| `/x/v2/reply/wbi/main` | `mode=2` 最新 / `mode=3` 最热 | 网页现用，需 wbi 签名；代码已有 `bilibili_wbi_sign()` 可复用 |

建议用后者，前者作为回退。

### 4.4 元数据

`comments_meta` 必须记录：`target_n`、`sorts_used`、`total_available`、`exhausted`、`returned`、`requests_made`、`degraded`、`degraded_reason`、`collected_at`。

`degraded=true` 表示平台报告的数量远大于实际返回（典型：报 500 条只给 3 条）。**这种情况不能静默接受**，必须让下游知道评论证据不完整，否则又会重演「规则要求看评论、实际没有评论」的问题。

### 4.5 为什么必须记 `collected_at`

评论是活数据，会持续增长。同一帖子在不同时点采集，评论集合不同。不记时点，后续无法复现，也无法判断"当时评论区是否已有反讽识别"。

## 5. S3 AI 预标注：定位与边界

### 5.1 决策

**AI 只做预标注，最终标签由人工给出。** 输出进 `pre_annotation`，`annotation_method` 记 `human_assisted`。

不得出现 `auto_accepted` 进入 Gold —— 既有 `build_gold_dataset.py` 已明确排除该值。

### 5.2 给 AI 的输入

`title` + `desc` + `tags` + `comments`（含 `sort_source`），以及 S2 的 `intake.viewed_media` 与 `intake.disclosure_status`。

**不给**：人工的 `draft_label`。否则 AI 只是在复述人的初判，预标注失去独立价值。

### 5.3 输出设计

| 字段 | 说明 |
| --- | --- |
| `label` | 允许 `null` 表示弃答 |
| `confidence` | 0–1 |
| `evidence_text` | **自由文本**，刻意不给结构化证据码 |
| `concerns` | 模型自述的不确定点、需人核实的项 |
| `abstain_reason` | 弃答原因 |
| `input_fields` | 实际喂入的字段名，用于复现 |

**为什么不给 `evidence_codes`**：结构化码一旦由 AI 给出，人工极易照抄，`evidence_codes` 会退化成 AI 的复述，失去人工证据的独立信息量。

### 5.4 必须承认的风险：锚定效应

AI 预标注可见，人的判断会向它靠拢。既有数据无法分离这个效应：

| 分组 | 标注日 | AI 建议 | 暗广率 |
| --- | --- | --- | --- |
| `control[0:120]` | 11-02 | 无 | 5.6%（6/108） |
| `control[120:180]` | 11-03 | 有 | 17.2%（10/58） |
| `assisted[0:324]` | 11-03 | 有 | 11.5%（36/313） |

同池对比差异显著（z=2.43），但**归因不可识别**：既可能是 AI 锚定，也可能是跨日校准漂移；且同为 11-03 的两组不显著（z=−1.22），说明 17.2% 这个点估计受 n=58 影响很大。

**建议的低成本保护**（可选，非必需）：从主池随机抽 10% 做 `annotation_method=human` 的盲标，用来量化预标注的影响。不加这个子集，事后就只能承认"不知道 AI 帮了多少、带偏了多少"，与既有 479 条的困境相同。

## 6. schema v1.4 变更

相对 v1.3 新增/修改：

| 字段 | 变化 |
| --- | --- |
| `desc` | 新增，简介与正文分离 |
| `tags` | 新增，平台标签列表 |
| `stats` | 新增，互动数据快照 |
| `comments_meta` | 新增，评论采集覆盖范围 |
| `pre_annotation` | 新增，AI 预标注结果 |
| `annotation_method` | 新增，`human` / `human_assisted` / `auto_accepted` |
| `comment_item.created_at` | 新增，爬虫已抓但此前未入库 |
| `comment_item.sort_source` | 新增，来自哪些排序 |
| `comment_item.is_deleted` | 新增，已删除/折叠 |
| `text` | 描述收紧：必须剥离页面样板 |

**兼容性**：全部新增字段可选。已实测既有 v1.2 记录用 v1.4 schema 校验直接通过，零迁移。

## 7. 与既有 479 条 Gold 的关系

**不回溯重建。** 那 479 条的 `disclosure_status`、`viewed_media`、`tags`、评论（仅 3 条）都无法补录 —— 评论会随时间增长，事后补采的评论集与当年不同，补录等于制造虚假可复现性。

处理方式：

- 479 条保留为「v1.0 指南下的历史 Gold」，Dataset Card 标注其局限：评论覆盖不足、披露前提未记录、无 tags
- 新方案产出的数据集单独命名（如 `formal_v2_forward`），不与 479 条混合统计
- 论文中如需合并报告，必须按采集方案分层披露，不能当作同质样本

## 8. 落地清单

| 项 | 状态 |
| --- | --- |
| schema v1.4 | 已完成（`schema_v1_4.json`） |
| 评论双排序采集策略 | 已完成（`comment_collector.py`），15 项离线测试 |
| 登录态注入辅助 | 已完成（`session_from_storage_state` / `required_cookies_present`） |
| tags 采集 | **待实现**，需接 tag 接口 |
| desc 与 text 分离 | **待实现**，需改 bilibili_html_extractor 与清洗逻辑 |
| 真实 HTTP 适配器 | **待实现**，接入 `comment_collector` 的 `fetch_page` |
| AI 预标注接入 | **待实现**，扩 `auto_judge.build_user_prompt` 支持 tags |
| 试点批次 | 建议 100 条，先验证 tags 与评论改善幅度 |

## 9. 预期收益与已知限制

**收益**

- 评论从 3 条提升到 20 条（双排序去重后），S-6 反讽排除规则首次有数据支撑
- tags 可提供商单标识（如 `#商单#`、品牌名），需试点实测比例
- 简介与正文分离，AI 输入更准确
- 采集失败不再使样本作废（v1.3 intake 机制）

**限制**

- `viewed_media=full` 是自述，无法机器验证
- 登录态存在账号风控与合规风险，需在数据来源合规台账登记
- 评论采集成本上升：每帖约 3–4 次请求（原 1–3 次）
- AI 预标注的锚定效应无法在单批内分离，除非另设盲标子集
- 已失效的视频（S-9 link rot）在新流程下仍不可恢复，只能靠 `source_url` 及时落本地快照缓解
