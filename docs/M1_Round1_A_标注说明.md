# M1 Round 1：A 标注说明

## 固定文件

- 只读输入：`data/reports/m1/locked_batches/round1.jsonl`
- 批次清单：`data/reports/m1/locked_batches/round1_manifest.json`
- A 输出目录：`data/run_outputs/m1_annotations/round1/A`
- 标注指南：`docs/annotation_guide_v1.md`
- 媒体根目录：`数据集/merged_20260728`

不要直接修改 `round1.jsonl`。启动标注程序后，结果会逐条写入 A 输出目录中的 `A_YYYYMMDD_HHMMSS.json`。该文件是连续追加的 JSON 对象流，由项目工具读取；不要用普通 JSON 编辑器重排或另存。

## 启动

在仓库根目录的 PowerShell 执行：

```powershell
.\scripts\start_round1_A.ps1
```

如果 PowerShell 阻止脚本，可在当前窗口执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_round1_A.ps1
```

## 每条记录怎么操作

主操作提示出现后：

- `v`：列出媒体，输入 `1`、`1,3,5`、`1-4` 或 `a` 打开图片；查看后回到终端。
- `n`：进入纯人工标注。
- `s`：暂时跳过；下次运行仍会出现。
- `q`：保存并退出；下次运行同一脚本选择继续即可断点续标。

Round 1 关闭了 LLM，因此不要用 `y`；按 `n` 进入人工填写。

### 标签编号

| 编号 | 标签 | 使用条件 |
|---:|---|---|
| 0 | 明广 | 存在明确广告、赞助、合作或商业关系披露，并且内容具有推广性质 |
| 1 | 暗广 | 存在商业推广意图，但没有明确披露商业关系 |
| 2 | 非广 | 正常分享、科普、测评或讨论，证据不足以支持商业推广判断 |
| 3 | uncertain | 信息缺失、媒体无法判断或证据冲突，不能可靠落入前三类 |
| 4 | out_of_scope | 招聘、个人二手、公益募集等不属于研究范围 |

### 证据代码

- `D`：明确广告/赞助/合作披露。
- `C`：明确商业对象，内容围绕特定品牌、商品、店铺或服务。
- `P`：劝服、促销、稀缺或价格刺激话术。
- `A`：下单、扫码、优惠码、购买链接、私信获取等转化动作。
- `V`：Logo、产品特写、价格表、优惠券或其他视觉商业证据。
- `B`：与创作者以往主题或表达方式明显偏离；只能作为辅助证据。
- `M`：置顶导流、模板化赞美等评论异常。

多个代码用英文逗号输入，例如 `C,P,A`。没有可靠证据代码可以直接回车。

### 置信度和文字证据

- 置信度输入 `0.0` 到 `1.0`；直接回车默认为 `0.8`。
- 文字证据应填写具体原文或媒体观察，例如：`正文出现“点击链接领取专属优惠券”`。
- 每行填写一条证据，空行结束。
- 选择 `uncertain` 时必须填写不确定原因。

## 自动保存格式

每条结果至少包含：

```json
{
  "post_id": "post_...",
  "annotator_id": "A",
  "guide_version": "1.0",
  "label": "暗广",
  "confidence": 0.85,
  "evidence_codes": ["C", "P", "A"],
  "evidence": ["正文出现专属优惠码", "引导点击链接购买"],
  "uncertain_reason": null,
  "annotation_method": "human",
  "annotated_at": "ISO-8601 时间"
}
```

程序还会在 `post` 字段中保存只读的原帖副本，方便后续审计。Round 1 的 A 文件不得给 B 查看，A 也不得打开 B 的标注目录。
