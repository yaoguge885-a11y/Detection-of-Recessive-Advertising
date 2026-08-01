# Data Schema 变更记录

## v1.0 — 2026-07-21（基线）

- **文件**：`data/schema/data_schema_v1.json`
- **平台支持**：wechat_official_account、weibo、xiaohongshu、douyin、synthetic、other
- **关键字段**：post_id、platform、source_type、blogger_id、text、media、provenance、privacy
- **约束**：`additionalProperties: false`
- **合成资产**：`data/synthetic/simulated_posts_v1.json`（30 条）

## v1.1 — 2026-07-27

- **文件**：`data-tooling/schema/data_schema_v1_1.json`
- **新增平台**：`bilibili`
- **新增可选字段**：
  - `title`（string | null）：帖子/文章标题
  - `content_group_id`（string | null）：跨平台转载内容组 ID
- **兼容性**：向后不兼容 v1.0（`schema_version` 从 `"1.0"` 变为 `"1.1"`）
- **迁移方式**：v1.0 记录需通过适配器升级 `schema_version` 并补充 `title`/`content_group_id` 字段

## v1.2 — 2026-07-28（当前权威版本）

- **文件**：`data-tooling/schema/data_schema_v1_2.json`（权威）、`data/schema/data_schema_v1_2.json`（副本）
- **新增字段**：
  - `media_item.source_url`（string | null）：媒体原始 URL
  - `media_item.caption`（string | null）：媒体标题/描述
  - `media_item.is_content`（boolean）：是否为正文内容图（非装饰/广告）
  - `provenance.llm_summary`（string | null）：LLM 摘要
  - `provenance.llm_extracted_at`（string | null）：LLM 提取时间
  - `content_record._collected`（object）：采集审计快照
- **兼容性**：向后兼容 v1.1（`schema_version` 接受 `"1.1"` 和 `"1.2"`）
- **迁移方式**：v1.1 记录无需修改即可通过 v1.2 校验
- **原因**：爬虫在实际运行中需要记录 `source_url`、区分内容图/装饰图，以及保留采集审计快照
