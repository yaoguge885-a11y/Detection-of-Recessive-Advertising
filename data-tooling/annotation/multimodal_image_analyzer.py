#!/usr/bin/env python3
"""
多模态图像分析器 —— 用视觉 LLM 替代 YOLO+OCR 做深度图像理解。

支持的模型与接入方式：

  ┌──────────────────────┬──────────────────────┬─────────────────────────┐
  │ 模型                  │ API 格式               │ 接入方式                  │
  ├──────────────────────┼──────────────────────┼─────────────────────────┤
  │ GPT-4V / GPT-4o      │ OpenAI Chat Completions│ 同现有 impad.llm 端点    │
  │ Qwen-VL-Max          │ OpenAI 兼容 (DashScope) │ base_url 指向 DashScope  │
  │ GLM-4V / GLM-5V      │ OpenAI 兼容 (Zhipu)    │ base_url 指向 Zhipu API  │
  │ DeepSeek-VL2         │ OpenAI 兼容              │ 同现有 DeepSeek 端点     │
  │ Ollama (llava, etc)  │ Ollama API              │ http://localhost:11434   │
  └──────────────────────┴──────────────────────┴─────────────────────────┘

输出格式：与 YOLO+OCR 路径完全兼容的 image_analysis 条目，
         但 description 和 relevance_to_annotation 质量显著更高。

用法：
  # 单张图片测试
  python scripts/data/annotation/multimodal_image_analyzer.py \
      --image data/media/xxx/01.jpg \
      --model gpt-4o

  # 批量分析（通过 auto_image_annotate.py 的 --use-multimodal 调用）
  python scripts/data/annotation/auto_image_annotate.py \
      --input data/interim/candidates_v1_dedup.jsonl \
      --use-multimodal \
      --multimodal-model gpt-4o-mini
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

CST = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════════════════════════
# Prompt 设计
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个社交媒体内容审核专家，专门分析图片中是否存在商业推广证据。

你的任务是检查图片，判断它是否包含以下 7 类视觉商业证据。对每一项给出 true/false 判定，并提供简要理由。

## 7 类视觉商业证据

1. has_logo: 是否包含品牌 Logo 或商标（文字或图形）
2. has_qr_code: 是否包含二维码或小程序码
3. has_price_info: 是否包含价格数字、折扣、优惠金额
4. has_product_image: 是否包含产品特写（白底、棚拍质感、突出单品）
5. has_chart_or_table: 是否包含销量图表、对比表格、排行榜
6. has_promotional_text: 图片内是否包含促销文案（限时/秒杀/买赠/包邮等）
7. has_contact_info: 是否包含微信号、手机号、店铺地址等联系方式

## 附加任务

- 用 1-3 句中文描述图片内容
- 判断图片最支持哪个证据代码：V（视觉商业证据）/ A（转化动作）/ D（明示商业关系）/ 无
- 评估图片对广告判定的重要性：critical / supportive / neutral

## 输出格式（严格 JSON，不要 markdown 包裹）

{
  "description": "图片内容的1-3句中文描述",
  "detected_elements": {
    "has_logo": false,
    "has_qr_code": false,
    "has_price_info": false,
    "has_product_image": false,
    "has_chart_or_table": false,
    "has_promotional_text": false,
    "has_contact_info": false
  },
  "visual_evidence_codes": [],
  "relevance": "neutral",
  "relevance_reason": "判定依据的简要说明",
  "image_quality": "清晰 / 模糊 / 有水印遮挡 / 文字不可读",
  "commercial_intent_score": 0.0
}

commercial_intent_score 范围 0~1，表示图片整体商业意图强度：
  0.0-0.2: 纯个人分享/风景/表情包
  0.3-0.5: 可能含产品但非推广（如产品测评配图）
  0.6-0.8: 明显的商业推广配图
  0.9-1.0: 明确的广告素材（含价格+购买引导）"""


def build_prompt(image_count: int = 1) -> str:
    """构建用户 prompt。"""
    if image_count == 1:
        return "请分析这张图片。"
    return f"请逐一分析以下 {image_count} 张图片，输出一个 JSON 数组。"


# ═══════════════════════════════════════════════════════════════
# 模型适配器
# ═══════════════════════════════════════════════════════════════

def _encode_image(image_path: Path) -> str:
    """将图片编码为 base64 data URL。"""
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    ext = image_path.suffix.lower()
    mime_map = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png",
                ".gif": "gif", ".webp": "webp", ".bmp": "bmp"}
    mime = mime_map.get(ext, "jpeg")
    return f"data:image/{mime};base64,{data}"


def call_openai_vision(
    image_paths: List[Path],
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
    timeout: int = 60,
) -> Dict:
    """通过 OpenAI 兼容 API 调用视觉模型。

    支持：GPT-4V, GPT-4o, Qwen-VL (via DashScope), GLM-4V (via Zhipu)
    """
    from openai import OpenAI
    import os

    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
    if base_url is None:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 构建消息
    content: List[Dict] = [{"type": "text", "text": build_prompt(len(image_paths))}]
    for img_path in image_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": _encode_image(img_path), "detail": "low"},
        })

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
        timeout=timeout,
    )

    raw = response.choices[0].message.content or ""
    return _parse_multimodal_response(raw, len(image_paths))


def call_ollama_vision(
    image_paths: List[Path],
    model: str = "llava:13b",
    timeout: int = 120,
) -> Dict:
    """通过 Ollama 调用本地视觉模型。

    支持的 Ollama 视觉模型：llava, llava-llama3, bakllava, minicpm-v
    """
    import requests

    prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(len(image_paths))

    # Ollama 支持直接传 base64 图片
    images = [_encode_image(p) for p in image_paths]

    payload = {
        "model": model,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "options": {"temperature": 0.0},
    }

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    return _parse_multimodal_response(raw, len(image_paths))


def _parse_multimodal_response(raw: str, image_count: int) -> Dict:
    """健壮解析多模态模型响应。返回标准化的单图或多图分析结果。"""
    raw = raw.strip()

    # 去掉 markdown 代码块
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)

    # 尝试直接解析
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # 查找最外层 JSON 对象或数组
        match = re.search(r'(\[.*\]|\{.*\})', raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                parsed = _fallback_parse(raw)
        else:
            parsed = _fallback_parse(raw)

    # 标准化：确保返回 {"single": {...}} 或 {"multiple": [{...}, ...]}
    if isinstance(parsed, list):
        return {"type": "multiple", "analyses": parsed, "raw": raw}
    elif isinstance(parsed, dict) and "description" in parsed:
        return {"type": "single", "analysis": parsed, "raw": raw}
    else:
        return {"type": "single", "analysis": _fallback_parse(raw), "raw": raw}


def _fallback_parse(raw: str) -> Dict:
    """模型输出格式异常时的兜底。"""
    return {
        "description": f"[模型输出解析失败，原始响应]: {raw[:200]}",
        "detected_elements": {
            "has_logo": False, "has_qr_code": False, "has_price_info": False,
            "has_product_image": False, "has_chart_or_table": False,
            "has_promotional_text": False, "has_contact_info": False,
        },
        "visual_evidence_codes": [],
        "relevance": "neutral",
        "relevance_reason": "模型输出解析失败",
        "image_quality": "未知",
        "commercial_intent_score": 0.0,
    }


# ═══════════════════════════════════════════════════════════════
# 统一分析接口
# ═══════════════════════════════════════════════════════════════

def analyze_images_multimodal(
    image_paths: List[Path],
    model: str = "gpt-4o-mini",
    backend: str = "openai",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 2,
) -> List[Dict[str, Any]]:
    """对多张图片运行多模态分析，返回 image_analysis 条目列表。

    Args:
        image_paths: 图片路径列表
        model: 模型名（gpt-4o, gpt-4o-mini, qwen-vl-max, glm-4v 等）
        backend: "openai"（OpenAI 兼容 API）或 "ollama"（本地模型）
        base_url: API 端点 URL（仅 openai 后端）
        api_key: API 密钥（仅 openai 后端）
        max_retries: 失败重试次数

    Returns:
        image_analysis 条目列表，格式兼容 annotation_supplement_schema
    """
    valid_paths = [(i, p) for i, p in enumerate(image_paths) if p.exists()]
    if not valid_paths:
        return []

    # 单张图片分析
    results: List[Dict] = []
    analyzed_at = datetime.now(CST).isoformat()

    for img_idx, img_path in valid_paths:
        for attempt in range(max_retries + 1):
            try:
                if backend == "ollama":
                    resp = call_ollama_vision([img_path], model=model)
                else:
                    resp = call_openai_vision(
                        [img_path], model=model, base_url=base_url, api_key=api_key)

                analysis = resp.get("analysis", {}) if resp.get("type") == "single" else {}
                break
            except Exception as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"    ⚠️ 重试 {attempt+1}/{max_retries} ({wait}s): {e}", file=sys.stderr)
                    time.sleep(wait)
                else:
                    print(f"    ❌ 多模态分析失败 [{img_path.name}]: {e}", file=sys.stderr)
                    analysis = _fallback_parse(str(e))

        # 标准化为 image_analysis 条目
        detected = analysis.get("detected_elements", {})
        evidence_codes = analysis.get("visual_evidence_codes", [])

        entry = {
            "media_ref": str(img_path),
            "source_url": None,
            "image_index": img_idx + 1,
            "analysis_method": f"multimodal_{model}",
            "description": analysis.get("description", ""),
            "ocr_text": None,  # 多模态模型不分离 OCR，描述中已包含文字信息
            "detected_elements": {
                "has_logo": detected.get("has_logo", False),
                "has_qr_code": detected.get("has_qr_code", False),
                "has_price_info": detected.get("has_price_info", False),
                "has_product_image": detected.get("has_product_image", False),
                "has_chart_or_table": detected.get("has_chart_or_table", False),
                "has_promotional_text": detected.get("has_promotional_text", False),
                "has_contact_info": detected.get("has_contact_info", False),
            },
            "visual_evidence_codes": evidence_codes,
            "relevance_to_annotation": analysis.get("relevance_reason", ""),
            "image_quality_notes": analysis.get("image_quality", "清晰"),
            "commercial_intent_score": analysis.get("commercial_intent_score", 0.0),
            "analyzed_at": analyzed_at,
            "_raw_model_response": resp.get("raw", "")[:500] if 'resp' in dir() else "",
        }
        results.append(entry)

    return results


# ═══════════════════════════════════════════════════════════════
# 与现有 auto_image_annotate 的集成点
# ═══════════════════════════════════════════════════════════════

def analyze_single_image_multimodal(
    image_path: Path,
    image_index: int,
    media_ref: str,
    source_url: str = "",
    model: str = "gpt-4o-mini",
    backend: str = "openai",
    **kwargs,
) -> Dict[str, Any]:
    """单张图片多模态分析（兼容 auto_image_annotate 的接口）。

    与 YOLO+OCR 的 analyze_image() 函数签名兼容，可直接替换调用。
    """
    results = analyze_images_multimodal(
        [image_path], model=model, backend=backend, **kwargs)

    if not results:
        # 兜底：返回空分析
        return {
            "media_ref": media_ref,
            "source_url": source_url or None,
            "image_index": image_index,
            "analysis_method": f"multimodal_{model}_failed",
            "description": "多模态分析失败",
            "ocr_text": None,
            "detected_elements": {k: False for k in [
                "has_logo", "has_qr_code", "has_price_info",
                "has_product_image", "has_chart_or_table",
                "has_promotional_text", "has_contact_info",
            ]},
            "visual_evidence_codes": [],
            "relevance_to_annotation": "分析失败",
            "image_quality_notes": "未知",
            "analyzed_at": datetime.now(CST).isoformat(),
        }

    entry = results[0]
    entry["media_ref"] = media_ref
    entry["source_url"] = source_url or None
    return entry


# ═══════════════════════════════════════════════════════════════
# 命令行测试
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="多模态图像分析器（测试）")
    parser.add_argument("--image", required=True, help="图片路径")
    parser.add_argument("--model", default="gpt-4o-mini", help="模型名")
    parser.add_argument("--backend", default="openai",
                        choices=["openai", "ollama"], help="后端类型")
    parser.add_argument("--base-url", default=None, help="API 端点")
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"❌ 图片不存在: {img_path}")
        sys.exit(1)

    print(f"🔍 分析: {img_path.name}")
    print(f"   模型: {args.model}")
    print(f"   后端: {args.backend}")

    result = analyze_single_image_multimodal(
        img_path, image_index=1, media_ref=str(img_path),
        model=args.model, backend=args.backend,
        base_url=args.base_url,
    )

    print(f"\n{'='*60}")
    print(f"描述: {result['description']}")
    print(f"检测元素:")
    for k, v in result["detected_elements"].items():
        print(f"  {k}: {'✅' if v else '·'}")
    print(f"证据代码: {result['visual_evidence_codes']}")
    print(f"商业意图: {result.get('commercial_intent_score', 'N/A')}")
    print(f"相关性: {result['relevance_to_annotation'][:100]}")
    print(f"图片质量: {result['image_quality_notes']}")
