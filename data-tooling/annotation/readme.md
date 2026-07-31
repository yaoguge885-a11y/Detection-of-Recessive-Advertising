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
使用系统 **Python 3.10**（`C:\Users\HONOR\AppData\Local\Programs\Python\Python310\python.exe`），无需虚拟环境。依赖：`requests`、`flet`（GUI 用）、`openai`（云端后端用）。

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

> **本机重要环境事实**（踩坑记录）：
> 1. Ollama 桌面应用把模型存在 **`E:\ollama`**（`OLLAMA_MODELS` 非默认路径），默认 `C:\Users\HONOR\.ollama\models` 是空的。`ollama_server.py` 会自动从桌面应用日志探测正确目录。
> 2. 本机有 **NVIDIA RTX 5060 Laptop GPU（8GB VRAM）**，qwen3.5:9b（Q4_K_M，6.3GB）约 5.5GB 进显存、~0.8GB CPU offload，生成约 **43 tok/s**。
> 3. **Qwen3.5 默认开启 thinking**，会消耗上千 token、每帖 30-50s 且 JSON 可能被截断。**顶层 `"think": false` 参数可禁用**（放进 `options` 里不生效），禁用后每帖仅 2-4 秒。
> 4. **`keep_alive`**：Ollama 默认 5 分钟卸载模型，冷启动加载 6.6GB 很慢。设置 `keep_alive: "30m"`（或 `-1` 永久）保持常驻。

---

## 4. 使用指南

### 4.1 批量预标注（自动判断主入口）
```powershell
python data-tooling/annotation/batch_pre_annotate.py \
  --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
  --output-dir data/annotations/preannotated \
  --auto-threshold 0.85 \
  --ollama-model qwen3.5:9b \
  --limit 100 \
  --no-images          # 跳过图片分析（默认会尝试 YOLO+OCR）
```

输出三路文件：
- `auto_<时间戳>.jsonl` —— 🟢 高置信度自动保存的标注记录（`annotation_method: "auto_accepted"`）
- `suggest_<时间戳>.jsonl` —— 🟡 中置信度建议，供人工确认
- `stats_<时间戳>.json` —— 📊 统计报告（各区间分布/回退数/耗时）

常用参数：
| 参数 | 默认 | 说明 |
|------|------|------|
| `--auto-threshold` | 0.85 | 自动保存阈值（0.70–0.95） |
| `--ollama-model` | qwen3.5:9b | Ollama 模型名 |
| `--ollama-url` | http://localhost:11434 | 服务器地址 |
| `--keep-alive` | 30m | 模型常驻时长（-1 永久） |
| `--no-warmup` | 关 | 跳过预热（默认自动预热） |
| `--no-images` | 关 | 跳过图片分析 |
| `--timeout` | 120 | 单条推理超时（秒） |

### 4.2 服务器管理工具
```powershell
# 查看状态（版本 / 已安装模型 / 当前已加载模型）
python data-tooling/annotation/ollama_server.py status

# 确保服务器运行（未运行则拉起 ollama serve），并预热模型
python data-tooling/annotation/ollama_server.py serve --preload

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
先检查：① 模型是否已安装（`ollama list`）；② 模型是否在正确的目录（`ollama_server.py status` 看已安装列表）；③ thinking 是否禁用了（看 `stats` 的耗时，若每帖 30-50s 说明 thinking 未禁用，需确认代码用的是顶层 `think: false`）。

**Q2: 模型冷启动很慢 / 每次都要重新加载？**
用 `ollama_server.py serve --preload` 预热并 `keep_alive: "30m"` 常驻。批量脚本默认会自动预热。

**Q3: 模型在哪个目录？**
本机桌面应用配置为 `OLLAMA_MODELS=E:\ollama`。`ollama_server.py` 会自动探测，无需手动指定。

**Q4: 想要更快？**
9B 已够快（每条 2-4s）。若仍要提速可换 `qwen3.5:4b`（3.4GB 完全进显存，约快 1.5-2 倍，但判断质量下降）。真正的大头是 thinking，已通过顶层 `think: false` 解决。

**Q5: 自动标注会不会污染 κ？**
不会。自动记录 `annotation_method: "auto_accepted"` 且 `annotator_id="system"`，`calculate_agreement.py` 计算 κ 时按此排除。
