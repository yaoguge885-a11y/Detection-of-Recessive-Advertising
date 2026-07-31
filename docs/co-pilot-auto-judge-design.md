# 分置信度自动判断系统设计方案

> 版本：v1.1
> 日期：2026-07-31
> 目标：高置信度自动标注，低置信度保留人工判断
> 本地推理：Ollama + Qwen3.5 9B

---

## 1. 设计动机

当前标注流程中，每条帖子都需要标注员手动完成全部步骤（看文本 → 看图片 → 选标签 → 勾证据 → 填描述 → 调置信度）。对于明显的明广（"#广告 感谢品牌方..."）或明显的非广（个人生活分享），这些步骤是机械重复。

本方案引入 **三级自动判断**：系统对高置信度内容直接给出标注并自动保存，对中等置信度内容给出建议等待确认，对低置信度内容完全交给人工。

### 核心原则

1. **自动判断不等于替代人工**：自动保存的记录标记 `annotation_method: "auto_accepted"`，可审计、可排除、可回溯
2. **不污染 κ**：自动标注记录不参与双人标注 κ 计算
3. **阈值可调**：从保守（0.90）开始，随验证结果逐步放宽
4. **模型建议不修改人工判断**（任务书第 3.9 条）

---

## 2. 架构总览

```
帖子加载
  │
  ├─► YOLO+OCR (本地免费, <1s) ──► 图片分析结果
  │     detected_elements + visual_evidence_codes
  │
  ├─► 6维关键词向量 (本地免费, <0.1s) ──► keyword_weights + ad_pressure
  │
  └─► Qwen3.5 9B via Ollama (本地, ~5-15s) ──► 综合判定
         │
         ├── confidence ≥ 0.85  ──► 🟢 自动保存标注，跳至下一条
         ├── 0.55 ≤ confidence < 0.85 ──► 🟡 展示建议面板，等待人工确认
         └── confidence < 0.55  ──► 🔴 不展示建议，纯人工判断
```

### 为什么采用 YOLO+OCR 文本证据，而不是直接看图？

Qwen3.5 9B 是**多模态模型**（同时支持文本与图像输入）。但本系统仍采用 YOLO+OCR（`auto_image_annotate.py`）产出结构化的 `detected_elements` 和 `visual_evidence_codes`，作为文本证据传入 LLM。

**这比直接把图扔给多模态模型更可靠**，因为 YOLO+OCR 的确定性输出（"图片3含品牌Logo + 价格数字"）消除了视觉幻觉风险，且文本证据可审计、可进证据链。多模态直连仅作为后续扩展选项。

---

## 3. 三级阈值定义

### 3.1 阈值表

| 置信度区间 | 行为 | 标注方法标记 | UI 表现 |
|-----------|------|-------------|--------|
| ≥ 0.85 | 🟢 自动保存 | `auto_accepted` | Toast 提示，自动跳下一条 |
| 0.55–0.84 | 🟡 展示建议 | `human`（人工确认后） | 右侧面板显示建议，需手动采纳 |
| < 0.55 | 🔴 无建议 | `human` | 面板显示"⚠️ 此帖需人工判断" |

### 3.2 阈值选择依据

- **0.85**：保守起点。只自动处理"非常明显"的帖子（如明确的 #广告 标记 或 纯个人生活分享）。如果 30 条验证中自动标注与人工复核一致率 < 95%，上调至 0.90
- **0.55**：下限。低于此值的帖子，LLM 的判断与随机无异，展示建议反而产生锚定效应

### 3.3 阈值可配置

```powershell
# GUI 模式
python flet_annotator.py \
  --auto-threshold 0.85 \
  --ollama-model qwen3.5:9b

# CLI 批量模式
python manual_review_annotate.py \
  --auto-threshold 0.85 \
  --ollama-model qwen3.5:9b \
  --input data/interim/candidates_v1.jsonl
```

---

## 4. Qwen3.5 9B 推理设计

### 4.1 调用方式

```
POST http://localhost:11434/api/chat
{
  "model": "qwen3.5:9b",
  "messages": [
    {"role": "system", "content": "<系统提示词>"},
    {"role": "user", "content": "<帖子文本 + 图片分析 + 关键词向量>"}
  ],
  "format": "json",
  "stream": false,
  "think": false,
  "keep_alive": "30m",
  "options": {"temperature": 0.0, "num_predict": 1024}
}
```

Ollama 的 `"format": "json"` 模式强制输出合法 JSON，无需手动正则提取。

**关键参数（实测 v1.1 补充）：**
- `"think": false`（**顶层**参数）：Qwen3.5 默认开启 thinking 会消耗上千 token、每帖 30-50s；顶层禁用后每帖仅 2-4 秒（放进 `options` 里不生效）
- `"keep_alive": "30m"`：模型常驻，避免每条帖子冷启动加载 6.6GB（默认 5 分钟会卸载）
- 服务器管理工具 `data-tooling/annotation/ollama_server.py`：显式启动/状态查询/模型预热（会自动探测桌面应用的 `OLLAMA_MODELS` 目录，本机为 `E:\ollama`）

### 4.2 System Prompt（证判分离设计）

```
你是社交媒体内容审核专家，专门识别隐性广告（暗广/软广）。
你的职责是**整理证据并作出判断**，而非替代人工最终决定。

## 标签定义
- 明广：明确标识商业关系（含"广告""赞助""合作""#ad""恰饭"等标识）
- 暗广：存在商业推广意图但未明确标识
  （品牌/产品是核心内容，有劝服话术，无广告标识）
- 非广：正常的个人分享、生活记录（无单一商业对象，无劝服话术）
- out_of_scope：招聘、个人二手交易、公益募集等不属于商业内容营销

## 证据代码
- D：明示商业关系（广告/赞助/合作标识）
- C：明确商业对象（单一品牌/商品/店铺/服务）
- P：劝服/促销话术（夸赞、限时、价格刺激）
- A：转化动作（下单、扫码、优惠码、链接）
- V：视觉商业证据（产品特写、Logo、价格表）
- B：行为偏移（与博主既往人设/主题不符）——只能辅助
- M：评论异常（置顶导流、格式化赞美）

## 判断流程
1. 先列出所有可能的证据（逐条，含原文引用和来源）
2. 再列出指向相反结论的证据
3. 指出信息缺口
4. 最后给出综合判断

## 重要规则
- 采集不完整不能推导"未披露"
- CreatorShift (B) 不能单独决定暗广
- 只有明确标识才算 D 类证据
- 多个弱证据叠加 ≠ 一个强证据

## 输出格式（严格 JSON）
{
  "label": "明广" | "暗广" | "非广" | "out_of_scope",
  "confidence": 0.0-1.0,
  "evidence_codes": ["D", "V"],
  "evidence": ["原文引用1", "原文引用2"],
  "reasoning": "综合推理过程（50-150字）",
  "uncertain_reason": null,
  "information_gaps": ["如果能看到评论区置顶..."]
}
```

### 4.3 User Prompt 模板

```
## 帖子信息
- 标题：{title}
- 博主：{blogger_id}
- 平台：{platform}

## 帖子正文
{text}

## 图片分析结果
{image_analysis_summary}

## 关键词特征向量
- 促销种草：{promotion_words_score}
- 价格提及：{price_mentions_score}
- 紧迫感：{urgency_expressions_score}
- 品牌商务：{brand_mentions_score}
- 行动召唤：{action_words_score}
- 自然表达：{natural_expression_score}

请按系统提示词的要求，输出 JSON 格式的综合判断。
```

### 4.4 失败回退

当 Ollama 不可用、超时（>120s）或返回非 JSON 时：

1. 回退到纯关键词规则（`impad/tools/keywords.py` 的 `ad_pressure()`）
2. `ad_pressure ≥ 0.5` + 无 explicit_ad_marker → `label="暗广"`, `confidence=0.45`（低于 0.55，强制人工）
3. 有 explicit_ad_marker → `label="明广"`, `confidence=0.90`（高于 0.85，自动保存）
4. 其他 → 不做建议，纯人工

---

## 5. 自动保存机制

### 5.1 保存的标注记录结构

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
  "annotated_at": "2026-07-31T10:30:00Z",
  "annotation_method": "auto_accepted",
  "_llm_suggestion": {
    "label": "暗广",
    "confidence": 0.92,
    "evidence_codes": ["V", "P"],
    "evidence": ["图片2中品牌Logo特写", "文案含'无限回购'等回购话术"],
    "reasoning": "帖子以个人分享口吻介绍某品牌产品，图片中出现品牌Logo特写，文案含回购话术，但无广告标识，判定为暗广",
    "model": "qwen3.5:9b",
    "auto_accepted": true
  }
}
```

### 5.2 关键标记

| 字段 | 值 | 用途 |
|------|-----|------|
| `annotator_id` | `"system"` | 区分自动标注与人工标注 |
| `annotation_method` | `"auto_accepted"` | 标注方式标记 |
| `_llm_suggestion.model` | `"qwen3.5:9b"` | 使用的模型 |
| `_llm_suggestion.auto_accepted` | `true` | 是否被自动采纳 |

### 5.3 自动保存触发流程

```
1. LLM 返回 {label, confidence: 0.92, ...}
2. confidence >= AUTO_THRESHOLD (0.85) → 触发自动保存
3. accept_suggestion() 填充表单控件
4. save_current() 写入标注记录
5. 导航至下一条帖子
6. Toast 通知："✅ 已自动标注为「暗广」(置信度 0.92)"
7. 底部状态栏更新："自动标注: 15 | 人工标注: 3 | 待标注: 282"
```

---

## 6. 文件修改清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `data-tooling/annotation/flet_annotator.py` | 修改 + 新增 | 核心：Ollama 推理接入、自动保存、UI 控件 |
| `data-tooling/annotation/manual_review_annotate.py` | 修改 | CLI 增加 Ollama 后端和自动阈值 |
| `data-tooling/annotation/batch_pre_annotate.py` | **新建** | 批量预标注脚本 |
| `implicit-ad-agent/impad/llm.py` | 修改 | 新增 `get_ollama_llm()` 工厂函数 |
| `docs/co-pilot-auto-judge-design.md` | **新建** | 本文档 |

### 6.1 `flet_annotator.py` 改动详情

#### 新增函数

| 函数 | 行数（估） | 职责 |
|------|----------|------|
| `run_ollama_judge(post, image_analyses, keyword_weights)` | ~80 | 调用 Ollama `/api/chat`，返回结构化判定 |
| `auto_save_if_confident(suggestion, post_index)` | ~30 | 检查置信度，自动保存并跳转 |
| `compute_keyword_weights_for_post(text)` | ~15 | 封装 `keywords.py` 的调用 |

#### 修改函数

| 函数 | 改动 |
|------|------|
| `run_llm_copilot_suggestion_bg()` | 增加 `backend` 参数，`"ollama"` 时调用 `run_ollama_judge()` |
| `run_copilot_suggestion()` | 调用后自动判断是否触发 `auto_save_if_confident()` |
| `accept_suggestion()` | 增加 `auto` 参数，区分自动采纳与手动采纳 |

#### 新增 UI 元素

| 控件 | 位置 | 功能 |
|------|------|------|
| 自动模式开关 | 顶部工具栏 | 🟢自动 / 🟡建议 / 🔴纯人工 |
| 置信度阈值滑块 | 顶部工具栏（开关展开） | 0.70–0.95，默认 0.85 |
| Toast 通知 | 右下角 | 自动保存成功提示 |
| 底部状态栏 | 窗口底部 | 实时显示自动/人工/待标注计数 |

---

## 7. 验证计划

### 7.1 环境准备

```powershell
# 1. 安装 Qwen3.5 9B
ollama pull qwen3.5:9b

# 2. 验证模型可用
ollama run qwen3.5:9b "你好，请用JSON格式输出：{\"status\": \"ok\"}"
```

### 7.2 功能验证

```powershell
# 启动标注器（自动模式）
python flet_annotator.py \
  --input anonymized_posts.jsonl \
  --auto-threshold 0.85 \
  --ollama-model qwen3.5:9b
```

### 7.3 质量验证

| 验证项 | 方法 | 通过标准 |
|--------|------|---------|
| 自动标注准确率 | 抽样 30 条自动标注，人工复核 | ≥ 95% 与人工判断一致 |
| 阈值合理性 | 统计各区间分布 | 自动区间占比 30-50% |
| 回退机制 | 关闭 Ollama 后启动 | 自动降级为纯人工 |
| 字段完整性 | 检查自动保存的标注记录 | 所有必填字段齐全 |

### 7.4 回归验证

```powershell
# 确保现有功能不受影响
python data-tooling/annotation/validate_schema.py \
  data/run_outputs/merged_20260728/anonymized_posts.jsonl \
  --target-schema 1.2

python data-tooling/m1_readiness.py audit \
  --dataset-root data/run_outputs/merged_20260728 \
  --output data/reports/m1/dataset_full_audit.json
```

---

## 8. 风险与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| Qwen3.5 9B 判断质量不足 | 中 | 从 0.85 保守阈值起步；人工复核 30 条验证 |
| Ollama 响应慢（>15s/条） | 中 | 超时 120s；加载时后台运行不阻塞 UI |
| 自动标注污染 κ | 低 | `annotation_method: "auto_accepted"` 标记，κ 计算排除 |
| 阈值过低导致错误自动保存 | 低 | 初始 0.85，可按需上调；保存前展示 toast 可撤销 |
| Ollama 服务不可用 | 低 | 自动回退到纯人工模式，不影响基本标注功能 |

---

## 9. 后续扩展

1. **多模型投票**：同时跑 Qwen3.5 9B + DeepSeek，一致时置信度 +0.1
2. **主动学习**：自动标注中低置信度的帖子优先推给人工
3. **阈值自适应**：根据历史自动标注的准确率动态调整阈值
4. **批量预标注**：正式双标前先跑一轮全量预标注，减少人工工作量

---

## 10. 相关文件索引

| 文件 | 角色 |
|------|------|
| `docs/co-pilot-auto-judge-design.md` | 本文档 |
| flet_annotator.py | GUI 标注工作台（主要修改目标） |
| manual_review_annotate.py | CLI 标注工具 |
| auto_image_annotate.py | YOLO+OCR 图片分析 |
| multimodal_image_analyzer.py | 多模态 LLM 图片分析 |
| llm.py | LLM 客户端工厂 |
| keywords.py | 6 维关键词特征向量 |
| judgment.py | 确定性规则判定 |
| verdict.py | 判定合约 |
| annotation_guide_v1.md | 标注规范 |
| P1_M1_双人任务书.md | 任务书（合规约束） |
