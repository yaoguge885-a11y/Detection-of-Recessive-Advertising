# P1 数据 Schema（权威运行版本说明）

> **权威运行版本：v1.2**  
> 本文档描述当前仓库中数据 Schema 的版本策略、兼容范围与升级规则。  
> 版本变更历史见 `docs/data_schema_changelog.md`。

## 当前权威 Schema

| 版本 | 文件路径 | 状态 |
|------|---------|------|
| **v1.2（权威运行版本）** | `data-tooling/schema/data_schema_v1_2.json` | ✅ 生产使用 |
| v1.1 | `data-tooling/schema/data_schema_v1_1.json` | 保留（v1.2 向后兼容） |
| v1.0 | `data/schema/data_schema_v1.json` | 保留（合成资产基线） |

> `data/schema/data_schema_v1_2.json` 与 `data-tooling/schema/data_schema_v1_2.json` 内容相同。  
> 权威文件以 `data-tooling/schema/data_schema_v1_2.json` 为准，`data/schema/` 下为副本。

## 版本兼容范围

| 版本 | `schema_version` 值 | 说明 |
|------|---------------------|------|
| v1.0 | `"1.0"` | 初始版本，仅含 wechat_official_account / weibo / xiaohongshu / douyin / synthetic / other |
| v1.1 | `"1.1"` | 新增 bilibili 平台；可选 `title` 字段；可选 `content_group_id` |
| v1.2 | `"1.1"` 或 `"1.2"` | 在 v1.1 基础上新增 media 的 `source_url`/`caption`/`is_content`、provenance 的 `llm_*` 字段、`_collected` 审计快照 |

v1.2 向后兼容 v1.1：`schema_version` 为 `"1.1"` 的记录通过 v1.2 校验。

## 小红书与 B 站适配策略

- **B 站**：v1.1 起纳入 `platform` 枚举（`"bilibili"`），完整支持图文、视频、评论结构。
- **小红书**：预留 `"xiaohongshu"` 枚举值。当前无小红书真实数据批次。首个小批次采集后如需新增字段，通过 v1.3 兼容扩展处理。
- **`title` 字段**：v1.1 起为可选字段（`string | null`），不可获取时填 `null`。

## 升级规则

1. **向后兼容扩展**（新增可选字段、放宽约束）→ 增加次版本号（如 v1.2 → v1.3），旧数据不经修改即可通过新 Schema。
2. **不兼容改动**（修改必填字段、收紧类型、删除字段）→ 增加主版本号（如 v1.2 → v2.0），需要迁移脚本。
3. 不得通过删除 `additionalProperties: false` 让旧数据通过校验。

## 标签

正式金标的核心标签为：`明广`、`暗广`、`非广`。本 Schema 额外保留：

- `out_of_scope`：招聘、个人二手交易、公益募集等不属于本项目定义的商业内容营销；
- `uncertain`：证据不足或信息不清，应进入复核池而非强行进入金标。

## 验证命令

### v1.0 合成资产验证

```powershell
python scripts/data/validate_submission_assets.py
```

### v1.2 正式候选验证

```powershell
python data-tooling/annotation/validate_schema.py ^
  data\run_outputs\merged_20260728\anonymized_posts.jsonl ^
  --target-schema 1.2 ^
  --schema data-tooling\schema\data_schema_v1_2.json ^
  --report data\reports\m1\schema_report.json
```

## 设计原则

1. **内容、主标注与补充标注分离**：`content_records` 不保存最终标签。
2. **隐私最小化**：仅保留 `blogger_id`，不把 `blogger_name` 设为必填字段。
3. **可审计性**：每条内容记录均有 `provenance` 和 `privacy`。
4. **合成数据边界**：合成资产用于 Schema 校验和管线冒烟测试，不能替代真实数据的双人标注金标集。
