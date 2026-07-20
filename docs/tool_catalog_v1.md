# P2 工具目录 v1

> 更新：2026-07-20。本文记录稳定接口和真实完成度，不以“能 import”代替 ready。

## 公共契约

所有工具采用两层结构：`_xxx_core(Pydantic Input) -> Pydantic Result`，以及 LangChain `@tool` 薄适配层。公共输出位于 `impad/tools/contracts.py`，包含 `tool_name`、`tool_version`、`status`、`score`、`evidence`、`warnings`、`payload` 和 `model_info`。

状态语义：`ok` 为主实现成功；`degraded` 为可参与判断的弱模型/规则结果；`skipped` 为输入不足且不得以 0 分冒充正常；`error` 为有输入但执行失败且无安全替代。

## 当前清单

| 工具 | Owner | Ready | 分数方向 | 当前实现与限制 |
| --- | --- | --- | --- | --- |
| `analyze_text_intent` | L | 是 | 越高越有商业导购意图 | 复用 6 维关键词和导购压力；当前规则版标记 `degraded`，返回原文 span |
| `sentiment_curve` | L | 是 | 越高越有焦虑/紧迫劝服情绪 | 正负情感与焦虑/紧迫分离；历史少于 3 条时不生成突变点 |
| `topic_drift` | L | 是 | 越高越偏离历史主题 | 当前用字符 bigram 余弦降级；仅使用当前发布时间前、最多 20 条历史 |
| `comment_anomaly` | L | 是 | 越高评论行为越异常 | 规则检测重复、模板赞美、短时突发；少于 5 条返回 `skipped` |
| `ocr_extract` | V | 是 | OCR 文本块平均置信度 | 复用 `VisionContext`；返回全文、bbox 文本块、二维码与价格/折扣/销量信号 |
| `image_text_consistency` | V | 是 | 越高图文语义越一致 | 当前为 OCR bigram + YOLO 对象映射降级版；只输出一致性，不输出广告结论 |
| `detect_logo_product` | V | 是 | 越高商品/品牌越显著 | 复用 YOLO COCO 与 OCR；明确区分通用商品、OCR 品牌候选和真正 Logo |

因此当前为 **7/7 ready**。三个视觉工具均使用独立 Pydantic Input，只接收本地 `image_path`，并可注入同一个 `VisionContext` 以避免重复运行 YOLO/OCR。M2 仍需完成更完整的真实视觉样例复核和 L/V 交叉评审后才能最终验收。

图文一致性已完成 30 对合成 sanity set：匹配组平均分 0.659、错配组 0.000，均值差 0.659。该结果记录于 `docs/vision_consistency_sanity_v1.md`；它验证降级算法的分数方向，不替代真实图片 integration。

## 调用示例

纯 core 适合单测、API 和 Agent 内部复用：

```python
from impad.tools.text_intent import TextIntentInput, _analyze_text_intent_core

result = _analyze_text_intent_core(TextIntentInput(text="限时优惠，扫码下单"))
print(result.model_dump(mode="json"))
```

LangChain 工具可独立 invoke：

```python
from impad.tools.text_intent import analyze_text_intent

result = analyze_text_intent.invoke({"text": "限时优惠，扫码下单"})
```

三个视觉工具先从本地图片生成一次上下文，再复用结构化发现：

```python
from impad.tools.vision_context import build_vision_context
from impad.tools.ocr_extract import ocr_extract
from impad.tools.detect_logo_product import detect_logo_product
from impad.tools.image_text_consistency import image_text_consistency

image_path = "samples/images/test_image.jpg"
context = build_vision_context(image_path).model_dump(mode="json")
ocr = ocr_extract.invoke({"image_path": image_path, "vision_context": context})
products = detect_logo_product.invoke({"image_path": image_path, "vision_context": context})
relation = image_text_consistency.invoke({
    "text": "帖子正文", "image_path": image_path, "vision_context": context
})
```

固定零 Key 演示：

```powershell
cd implicit-ad-agent
..\.venv\Scripts\python.exe run_tools_demo.py
```

默认回归测试零 Key、零联网且不要求视觉重依赖：

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

## 后续替换点

- `analyze_text_intent` 可在 core 内接入 ADR-010 的 `json_mode` LLM 主实现，失败后保留当前规则降级。
- `sentiment_curve` 可替换为中文情感模型，但焦虑/紧迫字段与普通正负情感必须继续分离。
- `topic_drift` 计划替换为 `bge-small-zh-v1.5` embedding；接口、时间过滤和 `skipped` 语义保持不变。
- `VisionContext` 已实现按图片内容哈希和视觉流水线版本缓存；三个工具接受同一上下文，不重复运行 YOLO/OCR。
- `image_text_consistency` 当前明确标记 `degraded`；后续可在稳定契约内替换为 VLM/CLIP 主实现。
- `detect_logo_product` 当前没有专用 Logo 模型，`logo_candidates` 保持为空且 `capabilities.logo_detection="none"`。

