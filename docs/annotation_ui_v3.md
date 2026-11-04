# 标注页面 v3 与证据字典

2026 年 10 月 29 日工程更新。新生成页面直接读取固定标注指南中的 D C P A V M B 字典，避免页面与指南对同一代码作不同解释。本次不修改标签规则，不重写已发出的 v2 页面、答案或便携包。

原页面将 C 解释为行动号召、A 解释为品牌指向、B 解释为账号背景，与指南的 C 商业对象核心、A 商业转化动作、B 可验证历史变化不一致。新生成器从传入指南的 Markdown 表格提取七个代码，缺少或重复代码时停止。界面说明、导出字典和版本指纹使用同一份定义。

新交付格式为 `m1_blind_html_delivery_v3`，正式人工导出格式为 `m1_blind_human_review_v3`，未完成草稿快照格式为 `m1_blind_draft_snapshot_v2`。这些名称描述文件格式，不表示人工审核或 M1 验收通过。

导出同时包含 `evidence_code_scheme`、完整 `evidence_code_dictionary` 和 `evidence_code_dictionary_sha256`。浏览器草稿绑定清单、指南、字典和角色；导入时还核对源数据指纹。v1/v2 人工结果、不同字典及声明为 AI 辅助的结果不能导入新页面。旧记录仍按原冻结版本解读，不自动重映射字母。

生成新批次必须显式指定清单、输入和输出目录，例如：

```powershell
.\.venv-handoff\Scripts\python.exe -X utf8 data-tooling/annotation/generate_m1_qwen_blind_html.py --manifest data/private/new_batch/manifest.json --input data/private/new_batch/candidates.jsonl --guide docs/annotation_guide_v1.md --media-base data/private/new_batch --output-root data/run_outputs/new_batch_delivery_v3
```

上述为路径示例，实际执行须使用获准的固定输入。工具不再默认选取旧 21 条清单，也不再默认写入旧交付目录。即使指定 `--force`，也拒绝用 v3 覆盖有旧 schema 清单的交付目录。新格式不能使已接触 AI 建议的样本重新成为独立盲测。

输入事件会立即更新“待完成”状态和校验提示，并保存文本草稿。“导出未完成草稿”允许保留未完成记录，独立于完整结果导出；它不会补勾查看状态、签字或完成声明。

当前 21 条的 v2 回件检查工具继续服务该旧批次。v3 是供后续新批次评审使用的契约，不能把新文件直接当作旧 v2 回件，也没有在本次工程更新中发布新的真实标注批次。

验证入口：

```powershell
.\.venv-handoff\Scripts\python.exe -X utf8 scripts/verify_handoff.py
```

该入口已纳入输入刷新、草稿保留、旧版本拒绝、字典不一致拒绝和 AI 辅助结果隔离的 Node 检查。Node 未安装时报告明确记录跳过，不会伪称完成。Windows 子进程以隐藏窗口启动，测试缓存写入本次输出目录。
