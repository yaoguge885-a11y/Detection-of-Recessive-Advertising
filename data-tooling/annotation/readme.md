# 标注工具舱说明（README）

> 更新日期：2026-07-31
> 本目录包含隐性广告识别人工标注 + 分置信度自动判断（AI 协驾）的完整工具链。

---

## 1. 本目录有什么

| 文件 | 类型 | 职责 |
|------|------|------|
| `auto_judge.py` | **核心模块** | 分置信度自动判断系统：三级判断、Ollama 推理、关键词回退、自动保存记录 |
| `ollama_server.py` | **服务器管理** | 显式启动 Ollama、查询状态（版本/已安装/已加载模型）、模型预热与常驻 |
| `batch_pre_annotate.py` | **批量预标注** | 全量跑自动判断管线，输出 auto / suggest / stats 三路结果 |
| `manual_review_annotate.py` | CLI 标注 | 交互式人工标注，支持 Ollama 后端 + 自动阈值自动保存 |
| `flet_annotator.py` | GUI 工作台 | 桌面标注界面，含自动模式开关、阈值滑块、Toast、状态栏 |
| `tests/test_auto_judge.py` | 单元测试 | 21 个用例（mock 掉 Ollama，不依赖模型） |
| `标注计划.md` | 设计来源 | 分置信度自动判断系统原始设计稿 |
| `readme.md` | 本文档 | 使用说明 |

其余为历史标注工具：`auto_image_annotate.py`（YOLO+OCR 图片分析）、`multimodal_image_analyzer.py`（多模态 LLM 图片分析）、`image_prefilter.py`、`validate_schema.py`、`calculate_agreement.py`（κ 计算）、`build_gold_dataset.py`、`privacy_scan.py` 等。

设计文档：`docs/co-pilot-auto-judge-design.md`（完整设计方案）。

---

## 2. 分置信度自动判断系统是什么

为解决"每条帖子都人工全流程标注"的重复劳动，引入 **三级自动判断**：

```
帖子加载
  ├─► YOLO+OCR 图片分析（本地，可选）
  ├─► 6 维关键词向量（本地，<0.1s）
  └─► Qwen3.5 9B via Ollama（本地，2~4s/条）──► 综合判定
         ├── confidence ≥ 0.85  ──► 🟢 自动保存标注，跳下一条
         ├── 0.55 ≤ confidence < 0.85 ──► 🟡 展示建议，等待人工确认
         └── confidence < 0.55  ──► 🔴 不展示建议，纯人工判断
```

### 核心原则
- **自动判断不等于替代人工**：自动保存记录标记 `annotation_method: "auto_accepted"`，可审计、可排除、可回溯
- **不污染 κ**：自动标注记录（`annotator_id="system"`）不参与双人标注 κ 计算
- **阈值可调**：默认 0.85（范围 0.70–0.95），可随验证结果调整
- **失败自动回退**：Ollama 不可用/超时/非 JSON 时，降级为纯关键词规则（明广 0.90 自动保存 / 暗广 0.45 强制人工 / 无信号纯人工）

---

## 3. 环境准备（一次性）

### 3.1 Python
使用项目支持的 **Python 3.10** 环境；在本仓库内优先使用 `implicit-ad-agent/.venv`。依赖包括 `requests`、`flet`（GUI 用）和 `openai`（兼容客户端用）。

### 3.2 Ollama 与模型
```powershell
# 确认 Ollama 服务可访问
ollama list

# 安装模型（已装则跳过）
ollama pull qwen3.5:9b

# 查看服务器状态（版本/已安装/已加载）
python data-tooling/annotation/ollama_server.py status

# 启动服务器 + 预热模型并常驻（推荐）
python data-tooling/annotation/ollama_server.py serve --preload
```

> **运行环境注意事项**：
> 1. Ollama 模型目录可能通过 `OLLAMA_MODELS` 配置为非默认位置；`ollama_server.py status` 会报告实际发现结果。
> 2. **Qwen3.5 默认开启 thinking**。请求必须在顶层设置 `"think": false`（放进 `options` 里不生效），避免长推理截断结构化 JSON。
> 3. **`keep_alive`**：设置 `keep_alive: "30m"`（或 `-1`）可减少重复冷启动；实际延迟和显存占用依目标机器实测。

---

## 4. 使用指南

### 4.1 批量预标注（自动判断主入口）
```powershell
python data-tooling/annotation/batch_pre_annotate.py \
  --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
  --output-dir data/annotations/preannotated \
  --auto-threshold 0.85 \
  --ollama-model qwen3.5:9b \
  --num-parallel 2 \
  --limit 100 \
  --no-images          # 跳过图片分析（默认会尝试 YOLO+OCR）
```

> **v2（2026-08-02）速度优化**：采用**异步流水线**（asyncio 并发窗口 + 图片预取），
> 配合 Ollama 服务端 **序列批处理**（`OLLAMA_NUM_PARALLEL=2`）让 GPU 同时解码多个请求。
> 启动服务器时需带 `--num-parallel 2`：
> ```powershell
> python data-tooling/annotation/ollama_server.py --num-parallel 2 serve --preload
> ```
> 并发窗口 `--num-parallel` 需与服务器的 `OLLAMA_NUM_PARALLEL` 匹配（8GB 显存 + 9B 建议 2-3）。

> **断点续传**：每条帖子完成后写入 `progress_<时间戳>.jsonl` 检查点，中断/崩溃后可恢复：
> ```powershell
> # 恢复最近一个批次（自动检测）
> python data-tooling/annotation/batch_pre_annotate.py -i <posts.jsonl> --resume-latest
> # 恢复指定批次
> python data-tooling/annotation/batch_pre_annotate.py -i <posts.jsonl> --resume 20260802_201911
> ```
> 恢复时跳过已完成帖子、重建统计、继续追加到原输出文件（含 manual 无建议帖也能恢复）。

输出三路文件：
- `auto_<时间戳>.jsonl` —— 🟢 高置信度自动保存的标注记录（`annotation_method: "auto_accepted"`）
- `suggest_<时间戳>.jsonl` —— 🟡 中置信度建议，供人工确认
- `stats_<时间戳>.json` —— 📊 统计报告（各区间分布/回退数/耗时/吞吐）
- `progress_<时间戳>.jsonl` —— 📌 进度检查点（断点续传依据）

常用参数：
| 参数 | 默认 | 说明 |
|------|------|------|
| `--auto-threshold` | 0.85 | 自动保存阈值（0.70–0.95） |
| `--ollama-model` | qwen3.5:9b | Ollama 模型名 |
| `--ollama-url` | http://localhost:11434 | 服务器地址 |
| `--keep-alive` | 30m | 模型常驻时长（-1 永久） |
| `--no-warmup` | 关 | 跳过预热（默认自动预热） |
| `--num-parallel` | 2 | 客户端并发窗口（1-4，需与服务器 NUM_PARALLEL 匹配） |
| `--image-workers` | 2 | 图片分析线程池大小 |
| `--no-images` | 关 | 跳过图片分析 |
| `--timeout` | 120 | 单条推理超时（秒） |
| `--resume <时间戳>` | 无 | 恢复指定批次（跳过已完成帖子） |
| `--resume-latest` | 关 | 自动恢复最近一个批次 |

### 4.2 服务器管理工具
```powershell
# 查看状态（版本 / 已安装模型 / 当前已加载模型）
python data-tooling/annotation/ollama_server.py status

# 确保服务器运行（未运行则拉起 ollama serve），并预热模型
#   --num-parallel N：启用序列批处理（GPU 同时解码 N 个请求，配合批量脚本并发窗口）
python data-tooling/annotation/ollama_server.py --num-parallel 2 serve --preload

# 仅预热模型（已加载则跳过）
python data-tooling/annotation/ollama_server.py preload
```

### 4.3 CLI 人工标注（支持自动保存）
```powershell
python data-tooling/annotation/manual_review_annotate.py \
  --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
  --output-dir data/annotations \
  --annotator-id D \
  --auto-threshold 0.85 \      # 高置信度自动保存，跳过人工确认
  --ollama-backend \            # 用本地 Ollama 预分析（代替云端 LLM）
  --ollama-model qwen3.5:9b \
  --no-supplement               # 跳过图像/备注等补充字段
```

### 4.4 GUI 工作台
```powershell
python data-tooling/annotation/flet_annotator.py \
  --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
  --output-dir data/annotations \
  --auto-threshold 0.85 \
  --ollama-backend \
  --ollama-model qwen3.5:9b \
  --skip-garbage
```

顶部工具栏新增：
- 🟢自动 / 🟡建议 / 🔴纯人工 模式开关
- 置信度阈值滑块（0.70–0.95）
- 底部状态栏实时显示：自动标注 / 人工标注 / 待标注 计数

快捷键：`Ctrl+←/→` 切换、`Ctrl+S` 保存、`Ctrl+A` 分析、`Ctrl+G` AI 建议、`Ctrl+Y` 采纳、`1-4` 快捷标签。

---

## 5. 自动保存记录结构（审计约定）

```json
{
  "post_id": "post_abc123",
  "annotator_id": "system",
  "guide_version": "1.0",
  "label": "暗广",
  "confidence": 0.92,
  "evidence_codes": ["V", "P"],
  "evidence": ["图片2中品牌Logo特写", "文案含'无限回购'等回购话术"],
  "uncertain_reason": null,
  "annotated_at": "2026-07-31T10:30:00+08:00",
  "annotation_method": "auto_accepted",
  "_llm_suggestion": {
    "label": "暗广",
    "confidence": 0.92,
    "evidence_codes": ["V", "P"],
    "evidence": ["图片2中品牌Logo特写", "文案含'无限回购'等回购话术"],
    "reasoning": "……",
    "model": "qwen3.5:9b",
    "auto_accepted": true
  }
}
```

关键标记：
- `annotator_id: "system"` —— 区分自动标注与人工标注
- `annotation_method: "auto_accepted"` —— 标注方式标记（**不参与 κ**）
- `_llm_suggestion.model` —— 使用的模型
- `_llm_suggestion.auto_accepted` —— 是否自动采纳

---

## 6. 测试

```powershell
python -m pytest data-tooling/annotation/tests/test_auto_judge.py -v
```
21 个用例，覆盖：三级置信度分类及边界、标签归一化、6 维关键词向量、关键词回退规则、自动保存记录结构、Ollama 失败时完整管线降级与三级分流。**不依赖 Ollama/模型**（mock 掉推理调用）。

---

## 7. 常见问题（FAQ）

**Q1: 为什么批量预标注全部走了关键词回退？**
先检查：① 模型是否已安装（`ollama list`）；② 模型目录是否被 `ollama_server.py status` 正确发现；③ 请求是否在顶层使用 `think: false`。

**Q2: 模型冷启动很慢 / 每次都要重新加载？**
用 `ollama_server.py serve --preload` 预热并 `keep_alive: "30m"` 常驻。批量脚本默认会自动预热。

**Q3: 模型在哪个目录？**
由 Ollama 默认目录或 `OLLAMA_MODELS` 决定。先运行 `ollama_server.py status`，不要在仓库文档中写死机器路径。

**Q4: 想要更快？**
可在独立验证集上比较 9B 与更小模型的延迟、显存和标注质量；没有目标机器实测与质量报告时，不预设速度或准确率结论。

**Q5: 自动标注会不会污染 κ？**
不会。自动记录 `annotation_method: "auto_accepted"` 且 `annotator_id="system"`，`calculate_agreement.py` 计算 κ 时按此排除。

**Q6: 想更快？多进程有用吗？**
多进程本身不能更快利用 GPU —— 瓶颈在 Ollama 服务端串行处理。正确做法是**序列批处理**：启动服务器时 `--num-parallel 2`（`OLLAMA_NUM_PARALLEL`），批量脚本用 `--num-parallel 2` 并发窗口提交，让 GPU 同时解码多个请求；图片分析用 `--image-workers` 线程池预取流水线，GPU 与 CPU 同时忙碌。8GB 显存 + 9B 模型建议 2-3，再高会因 KV cache 不足而排队。

**Q7: 批量脚本输出吞吐很慢？**
`stats` 的吞吐含模型预热时间。长文帖子（3000+ token 提示词）单条约 8-10s 属正常；短帖 2-4s。并发窗口越大、帖子越短，批处理收益越明显。

**Q8: 中断/崩溃后要重新跑全部吗？**
不用。每条帖子完成后写入 `progress_<时间戳>.jsonl` 检查点，重跑时加 `--resume-latest`（或 `--resume <时间戳>`）即可跳过已完成帖子，从断点继续。`auto_*/suggest_*` 输出会继续追加，统计会重建合并。
