# P2 工具目录 v1

> 更新：2026-07-19。本文记录稳定接口和真实完成度，不以“能 import”代替 ready。

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
| `ocr_extract` | V | 否 | 不适用/文本提取置信 | 现有 `vision.py` 是底层资产，尚缺 P2 契约薄封装 |
| `image_text_consistency` | V | 否 | 越高图文语义越一致 | 尚未实现；不能把一致性分解释成广告概率 |
| `detect_logo_product` | V | 否 | 越高商品/品牌越显著 | 尚未实现；必须区分 COCO 通用物体、OCR 品牌候选与真正 Logo |

因此当前为 **4/7 ready**，尚未达到 M2 的至少 6 个工具门槛。需要 V 完成三个视觉工具并交叉评审 L 的四个工具后才能验收。

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
- 所有视觉工具必须复用一次 `VisionContext`，不能对同一图片重复运行 YOLO/OCR。

