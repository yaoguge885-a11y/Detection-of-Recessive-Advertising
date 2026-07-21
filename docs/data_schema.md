# P1 数据 Schema v1.0（本次交付说明）

本次提交包含两个 JSON 文件：

- `data/schema/data_schema_v1.json`：标准帖子输入 `content_record` 与独立 `annotation_record` 的 JSON Schema、字段说明和样例；
- `data/synthetic/simulated_posts_v1.json`：30 条完全合成的模拟帖子，以及逐条对应的参考标注和覆盖矩阵。

## 设计原则

1. **内容与标注分离**：`content_records` 不保存最终标签；`reference_annotations` 仅用于本次模拟集的规则测试。
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

该脚本仅使用 Python 标准库，会检查字段、类型、ID 关联、标签分布、证据码和模拟数据隐私标记。
