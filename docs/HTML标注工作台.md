# HTML 人工标注工作台

本工作台是本机运行的轻量级人工标注界面，用来替代 `data-tooling/annotation/flet_annotator.py` 的核心流程。它只监听 `127.0.0.1`，不把帖文或评论发送到任何外部服务；模型建议只来自本机 Ollama。

> 数据门禁：当前仓库里没有 `数据集/merged_20260728`，也没有 2,932 条内部批准池的逐条清单。**在没有 approved 固定清单时，本工具只能用于探索性试标，不能把结果称为正式 Gold。** canonical 的 3,312 条并不等于“已批准 3,312 条”。

## 1. 快速启动（Windows PowerShell）

在仓库根目录 `D:\projectsnew\Detection-of-Recessive-Advertising` 下运行。

### 1.1 合成数据演示（推荐先跑）

```powershell
.\scripts\start_html_annotator.ps1 `
  -Dataset data/synthetic/simulated_posts_v1.json `
  -DatasetId synthetic_demo `
  -BatchId smoke `
  -AnnotatorId alice `
  -MediaRoot data/synthetic `
  -NoAutoSuggest
```

脚本会打印类似下面的地址，**必须连同 `?token=...` 一起打开**：

```text
http://127.0.0.1:8765/?token=...
```

如果 PowerShell 执行策略阻止脚本，可改用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_html_annotator.ps1 `
  -Dataset data/synthetic/simulated_posts_v1.json `
  -DatasetId synthetic_demo `
  -BatchId smoke `
  -AnnotatorId alice `
  -MediaRoot data/synthetic `
  -NoAutoSuggest
```

`-NoAutoSuggest` 表示本次启动进入真正的独立盲标：页面不会请求 Ollama，`/api/suggest` 返回 403。

也可以直接调用 Python：

```powershell
python data-tooling/annotation/html_annotator.py `
  --dataset data/synthetic/simulated_posts_v1.json `
  --dataset-id synthetic_demo `
  --batch-id smoke `
  --annotator-id alice `
  --media-root data/synthetic `
  --no-auto-suggest
```

### 1.2 只校验数据和清单，不启动服务

```powershell
python data-tooling/annotation/html_annotator.py `
  --dataset data/synthetic/simulated_posts_v1.json `
  --dataset-id synthetic_demo `
  --batch-id smoke `
  --annotator-id alice `
  --media-root data/synthetic `
  --check-only
```

输出包含 `post_count`、`manifest_role`、`formal_gold_allowed`、清单校验结果和 batch manifest。合成集当前是 **30 条**，不是 50 条。

### 1.3 真实批次（本机文件齐全时）

```powershell
python data-tooling/annotation/html_annotator.py `
  --dataset data/reports/m1/locked_batches/round1.jsonl `
  --dataset-id m1_round1 `
  --batch-id round1 `
  --annotator-id A `
  --media-root 数据集/merged_20260728 `
  --manifest data/reports/m1/locked_batches/round1_manifest.json `
  --manifest-role approved
```

注意：

- 上面的 `locked_batches` 和 `数据集/merged_20260728` 在当前工作区不存在，不能直接照抄运行。
- `--manifest-role approved` 只是**用户声明**，工具不会验证批准来源。没有真实批准清单时请用 `exploratory`（默认值）。
- 不要把项目数据与未来的公开数据集放进同一个 `dataset_id`/`batch_id`；不同数据集应各自建立批次。

## 2. 输出目录与隔离

默认输出根目录：

```text
data/annotations/workbench/<dataset_id>/<batch_id>/<annotator_id>/annotations.jsonl
```

该目录已被 `.gitignore` 忽略。每个批次还有：

```text
data/annotations/workbench/<dataset_id>/<batch_id>/batch_manifest.json
```

隔离规则：

- `dataset_id`、`batch_id`、`annotator_id` 都是目录名的一部分；不同标注人不会写同一个文件。
- 每个标注人目录有 `.lock`。同一标注人重复启动会被拒绝，避免两个窗口互相覆盖。
- `batch_manifest.json` 记录数据集 SHA-256、清单 SHA-256、清单角色、顺序化 post_id 清单 SHA-256、指南版本/哈希和 `formal_gold_allowed`。再次启动同一批次时逐项比对；不匹配会拒绝启动，防止混批。
- 每次保存追加一行 JSON，执行 `flush()` 和 `os.fsync()`。重启时按 `post_id` 重放最后一条 revision。
- 末尾半行损坏会忽略并警告；中间损坏行也会警告。`dataset_id`/`batch_id`/`annotator_id` 或批次清单哈希不匹配的行会被忽略。

## 3. 界面功能

- 单条展示：标题、正文、评论、平台、来源、博主、发布时间、采集状态、披露区域和本地媒体。
- 标签：`明广`、`暗广`、`非广`、`uncertain`、`out_of_scope`。
- 人工填写：置信度、证据码、证据说明（一行一条）、不确定原因、备注。
- 导航：上一条、下一条、按序号跳转、只看未完成、进度统计。
- 每条单独保存；重启后从 `annotations.jsonl` 恢复；支持 JSON 和 JSONL 导出。
- 所有帖子文本、评论和媒体说明都用 `textContent` 写入 DOM，不拼接 `innerHTML`。
- `Ctrl+Enter` 保存当前条。

### 标签与证据码约束

| 标签 | 含义 | 工具校验 |
| --- | --- | --- |
| `明广` | 有商业推广意图且有明确广告/赞助/合作/赠送/平台商业标识 | 必须含 `D`，且至少一条证据说明 |
| `暗广` | 有商业推广意图，且披露区域完整采集后仍未发现明确披露 | 不得含 `D`，且至少一条证据说明 |
| `非广` | 没有足够证据支持商业推广意图 | 可无证据码 |
| `uncertain` | 证据缺失、冲突或质量不足 | 必须填写不确定原因 |
| `out_of_scope` | 不属于本研究范围 | 可无证据码 |

证据码：`D` 明确披露/平台标识、`C` 商业合作/赞助、`P` 推广话术/购买引导、`A` 账号商业属性、`V` 视觉/视频证据、`M` 媒体/文本缺失、`B` 行为线索。`B` 只能辅助，不能单独使用。完整定义以 `docs/annotation_guide_v1.md` 为准。

## 4. Ollama 建议

默认配置：

- 模型：`qwen3.5:9b`
- 地址：`http://127.0.0.1:11434`（只接受回环地址）
- 不思考：`think=false`
- 每次请求只发送 **system + 当前帖子**，不发送上一条对话，不保留聊天历史
- 请求包含：完整 `docs/annotation_guide_v1.md`、当前帖子的标题/博主/平台/正文/评论（默认前 30 条，`--comment-limit`）/媒体证据状态；若记录自带 `image_analyses` 也会带上，但工作台不会自行生成图像分析
- 请求失败会显示红色错误和耗时；**不会**回退到关键词判断，**不会**自动保存
- 模型返回只显示在“模型建议”卡片；点“采用建议”也只填表，仍需人工核对并点击保存

相关参数：

```powershell
--model qwen3.5:9b
--ollama-url http://127.0.0.1:11434
--timeout 120
--num-predict 1536
--comment-limit 30
```

关闭建议：

```powershell
--no-auto-suggest
```

这是真正的盲标启动：页面不显示模型标签，`/api/suggest` 返回 403，且本次会话不能重新开启建议。

### human 与 human_assisted

- 没有看过模型建议（或请求失败且没有看到模型标签）→ `annotation_method = "human"`。
- 页面显示了模型建议，保存时必须勾选“我看过模型建议”→ `annotation_method = "human_assisted"`，并记录 `saw_model_advice=true`。
- 如果页面已显示建议但未勾选，服务端返回 409，拒绝把辅助判断伪装成独立人工。
- 一条记录一旦是 `human_assisted`，后续修改仍保持 `human_assisted`，不会降级为 `human`。

**下游兼容性：** `data-tooling/annotation/build_gold_dataset.py` 和 `calculate_agreement.py` 只接受 `annotation_method="human"`；`human_assisted` 会被当作 `non_human_method` 排除。工作台不会为了兼容而错误标成 `human`。混合来源数据不能直接进入正式 Gold/κ 计算。

## 5. 固定 post_id 清单

支持：

- `.txt`：一行一个 post_id，`#` 开头为注释
- `.json`：数组，或含 `post_ids`/`items`/`records`/`posts` 的对象
- `.jsonl`：一行一个
- `.csv`：首列；识别 `post_id`/`postid`/`id`/`帖子id` 表头

校验行为：

- 保留清单原顺序，不排序
- 重复 post_id → 报错
- 清单中的 post_id 不在数据集 → 报错
- 没有清单 → 使用数据集原顺序，`formal_gold_allowed=false`
- `exploratory` → `formal_gold_allowed=false`
- `approved` 但没有清单 → CLI 直接报错，拒绝启动
- `approved` 有清单 → 只记录用户声明，不代表工具完成了批准审计

因此，**没有真实批准清单时只能探索性试标**。不要用“先导全量、之后再删排除项”来宣称正式 Gold 门禁已满足。

## 6. 缺失媒体与披露

媒体 URL 只由服务端根据 `post_id` 和媒体序号生成，浏览器不能传任意路径。服务端拒绝绝对路径、盘符路径（包括 `C:foo` 这种相对盘符）、UNC、`..`、NUL，并用 `resolve()` 后再次检查是否位于 `--media-root` 内。

状态会明确显示：

- `ok`：本地文件可读取
- `missing`：记录指向的本地文件不存在（红色卡片）
- `outside`：路径越界（红色卡片，403）
- `remote_only`：只有远程 URL，本地未保存；不自动加载远程资源

披露区域区分：

- `present`：有明确披露/平台商业标识
- `absent_complete`：完整采集且未发现披露（可作为暗广前提）
- `missing`：披露区域未采集/采集不完整，**不能视为不存在**
- `unknown`：采集状态未知，**不能视为不存在**

标题/正文缺失、评论未采集或评论为空但采集不完整，也都会显示为缺失/不确定，不会静默省略。

## 7. 导出

页面顶部有“导出 JSON”和“导出 JSONL”：

- JSON：一个对象，包含导出元信息和 `annotations` 数组
- JSONL：一行一条，按批次顺序排列，只含已保存记录
- 文件名包含 dataset、batch、annotator 和时间戳
- 每行带 `export_sequence`，表示该记录在固定清单中的位置

JSON 元信息里有 `annotation_method_notice`，再次说明 `human_assisted` 会被现有 Gold/κ 工具排除。

## 8. 测试

```powershell
python -m pytest data-tooling/annotation/tests/test_html_annotator.py -q
```

当前结果：`28 passed`。测试覆盖：

- 清单保序、重复、缺失、批次元数据不匹配、manifest 自校验
- 逐条保存、重启恢复、损坏末行、标注人隔离、双开锁
- JSON/JSONL 导出顺序与结构
- 标签/置信度/证据码/不确定原因校验
- 缺失媒体、路径越界、盘符相对路径、远程 URL
- 披露区域和评论的缺失语义
- HTTP token、Host 校验、盲标 403、建议后 409、`human_assisted` 粘性
- mock Ollama 连续两次请求只有当前帖子 messages，无历史上下文；失败可见且不落盘

## 9. 已知限制

1. 当前工作区没有真实 canonical/批准池清单，因此没有跑真实 1,000 条，也不能声称完成了正式 Gold。
2. `--manifest-role approved` 只是声明，工具不验证批准链、来源和排除项是否齐全。
3. 工作台不做图像/视频内容理解；除非上游记录已有 `image_analyses`，模型只看到文本和媒体证据状态。缺失媒体会被明确标出，但不会自动补采。
4. 单机单用户 token 保护只防误访问，不是多用户认证；不要把带 token 的 URL 发给别人。服务只监听回环地址。
5. 追加日志用 `fsync` 降低中断丢失风险，但不是数据库事务；极端断电仍可能留下可识别的末行半条记录，重启时会忽略并警告。
6. 一个标注人目录同时只允许一个进程；同一人换机器/换目录不会自动合并，需要各自导出后人工汇总。
7. 指南版本目前默认取 `1.0`；若指南内容改变，应同时更新 `docs/annotation_guide_v1.md` 的版本标识，避免记录里的版本语义漂移。
8. 工作区没有 AdSpectorX 数据文件；其下载许可、可用性、标签到项目三分类的映射都尚未确认。不要把它与项目数据直接混成同一测试集。
9. 浏览器验证使用 Playwright + 本机 Edge；在沙箱环境中 Playwright 需要命名管道，若遇到权限错误需在允许启动浏览器的环境重试。
