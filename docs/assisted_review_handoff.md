# B 草稿接续与 AI 辅助复核工具

本工具把用户已经导出的部分草稿与已有 AI 建议合并为一个本地复核页面。它只补空白字段，保留原有标签、置信度、说明和媒体查看记录；原稿另作逐字节备份。它不调用模型，也不把 AI 建议写成人工已确认结果。

先用合成材料验证运行：

```powershell
python -X utf8 scripts/demo_assisted_review.py
```

命令只用 Python 标准库，创建三条合成记录和一个像素图片，模拟一条已填、一条部分填写、一条未填写的状态。输出在新的 `data/run_outputs/assisted_demo_时间戳/`，终端给出 HTML 路径。打开后检查新增项、有异议则修改，勾选人工确认，再导出。演示没有真实帖子、真实人员、网络请求或模型调用。

使用真实的受控材料时，显式指定五个路径：

```powershell
python -X utf8 data-tooling/annotation/build_assisted_review.py --draft data/reports/m1/private/draft.json --page data/reports/m1/private/frozen_B_page.html --suggestions data/reports/m1/private/suggestions.json --media-base data/run_outputs/merged_20260728 --output-dir data/run_outputs/assisted_review_new
```

`--draft` 是原页面“导出未完成草稿”生成的 B 快照，支持 `m1_blind_draft_snapshot_v1/v2`；`--page` 是对应固定版本页面，提供原始样本和指南。工具核对角色、顺序、源数据、清单和指南指纹，有字典指纹时也核对字典。输出目录必须不存在，避免覆盖原进度。

`--suggestions` 只提供候选标签与说明，格式示例由演示生成。其 `items` 按 ordinal 指定，`fields` 只允许 label、confidence、evidence_codes、evidence、uncertain_reason。已有非空值不会被建议覆盖，查看、签字和完成声明也不能由建议写入。建议的实际作者、媒体检查范围和限制应如实写入 suggestion_author、media_inspection、review_note。

输出包括：

- `B_AI辅助复核_接续草稿.html` 和 `review_core.js`：须放在同一目录；页面使用独立浏览器存储键，不覆盖旧盲测草稿。
- `original_user_draft.json`：原稿字节备份。
- `seed.json`：原记录、补齐记录、字段来源和媒体相对路径。
- `preservation_report.json`：输入哈希、保留核验及补齐范围。

部分编辑可以导出为 `m1_ai_assisted_review_draft_v1`；新增项经真实用户确认后导出为 `m1_ai_assisted_human_review_v1`。两者均明确 `annotation_method=ai_assisted_human_review`、`independent_blind_review=false`、`formal_evidence=false`，不计入正式 κ 或 Gold。确认 AI 文本不等于观看了视频，原媒体记录保持原样。

**旧 v2 回件核验**

`data-tooling/annotation/check_blind_returns_v2.py` 只用于原冻结 v2 批次的独立人工回件结构核验。需要取得私有候选、固定页面、指南和清单，按交接相对路径放入仓库。AI 辅助结果会被拒绝，不能通过改名或改 schema 冒充独立回件。

```powershell
python -X utf8 data-tooling/annotation/check_blind_returns_v2.py --b data/reports/m1/private/original_B.json --seal
```

两份有效原件都独立完成后，协调人可传入 `--a`、`--b`、`--seal --compare`。只有两份有效且标注人不同、原件封存后，才生成对照与待人工裁决清单。缺件时退出码为 2，读取错误为 1，两份均有效为 0。单独检查 B 时因 A 未提供而返回 2 是预期状态。结构核验不证明真实独立性或标签正确率。

公开仓库仅含可复用代码和合成示例。实际 21 条的原稿、逐条建议、媒体与接续页由交接人通过私有包另行提供。当前真实接续停在“新增或补齐 14 条待用户确认”，没有声称独立盲测、裁决或 M1 完成。
