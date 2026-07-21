# P1 数据 Schema v1.0（本次交付说明）

本次提交包含两个 JSON 文件：

- `data/schema/data_schema_v1.json`：标准帖子输入 `content_record`、独立 `annotation_record` 与 `annotation_supplement_record` 的 JSON Schema、字段说明和样例；
- `data/synthetic/simulated_posts_v1.json`：30 条完全合成的模拟帖子、逐条对应的参考标注、标注补充记录和覆盖矩阵；
- `docs/annotation_supplement_schema.md`：图像分析、Markdown 备注与边界案例补充记录的字段规范。

## 设计原则

1. **内容、主标注与补充标注分离**：`content_records` 不保存最终标签；`reference_annotations` 保存主标注；`reference_annotation_supplements` 通过 `post_id + annotator_id` 关联图像分析、Markdown 备注和边界讨论。
2. **隐私最小化**：仅保留 `blogger_id`，不把 `blogger_name` 设为必填字段；所有模拟账号、评论者和来源均为虚构。
3. **可审计性**：每条内容记录均有 `provenance` 和 `privacy`；真实数据采集时必须替换为实际来源台账信息。
4. **合成数据边界**：本模拟集用于 Schema 校验、规则试跑和管线冒烟测试，不能替代真实公开数据的双人标注金标集。

## 标签

正式金标的核心标签为：`明广`、`暗广`、`非广`。本 Schema 额外保留：

- `out_of_scope`：招聘、个人二手交易、公益募集等不属于本项目定义的商业内容营销；
- `uncertain`：证据不足或信息不清，应进入复核池而非强行进入金标。

## 验证命令

```powershell
python scripts/data/validate_submission_assets.py
```

该脚本仅使用 Python 标准库，会检查字段、类型、ID 关联、标签分布、证据码、媒体 `ref` 与图像补充记录的一一对应关系，以及模拟数据隐私标记。
