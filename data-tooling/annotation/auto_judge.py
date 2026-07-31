#!/usr/bin/env python3
"""分置信度自动判断系统核心模块（co-pilot-auto-judge-design v1.0 的实现）。

三级自动判断：
  - confidence >= auto_threshold (默认 0.85)  → 🟢 auto_accepted  自动保存标注
  - 0.55 <= confidence < auto_threshold       → 🟡 suggestion     展示建议，等待人工确认
  - confidence <  0.55                        → 🔴 manual         不展示建议，纯人工判断

本地推理：Ollama + Qwen3.5 9B
  - 图片分析由 YOLO+OCR / 多模态 LLM 产出结构化的 detected_elements +
    visual_evidence_codes，作为文本证据传入 LLM（确定性输出，消除视觉幻觉风险）
  - 关键词特征由 impad/tools/keywords.py 的 6 维向量提供（本地免费，<0.1s）

核心原则：
  - 自动判断不等于替代人工：自动保存记录标记 annotation_method="auto_accepted"
  - 不污染 κ：自动标注记录不参与双人标注 κ 计算
  - 模型建议不修改人工判断
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ── Windows GBK 控制台兼容：强制 UTF-8 输出 ──
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 项目根目录与 impad 导入 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_IMPAD_ROOT = PROJECT_ROOT / "implicit-ad-agent"
if str(_IMPAD_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPAD_ROOT))

CST = timezone(timedelta(hours=8))

# ════════════════════════════════════════════════════════════════════
# 常量与默认值
# ════════════════════════════════════════════════════════════════════
OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "qwen3.5:9b"
OLLAMA_TIMEOUT = 120          # 单条推理超时（秒）
OLLAMA_HEALTH_TIMEOUT = 5     # 健康检查超时（秒）

DEFAULT_AUTO_THRESHOLD = 0.85  # 自动保存阈值（默认，可调 0.70–0.95）
SUGGESTION_LOWER_BOUND = 0.55  # 建议展示下限：低于此值不展示建议（防锚定）

# 标签（与设计文档一致，中文标签；flet 端用代码可经 LABEL_TO_CODE 转换）
VALID_LABELS = ("明广", "暗广", "非广", "out_of_scope")
LABEL_TO_CODE = {
    "明广": "mingguang",
    "暗广": "anguang",
    "非广": "feiguang",
    "out_of_scope": "out_of_scope",
}
CODE_TO_LABEL = {v: k for k, v in LABEL_TO_CODE.items()}

EVIDENCE_CODES = {
    "D": "明示商业关系（广告/赞助/合作标识）",
    "C": "明确商业对象（单一品牌/商品/店铺/服务）",
    "P": "劝服/促销话术（夸赞、限时、价格刺激）",
    "A": "转化动作（下单、扫码、优惠码、链接）",
    "V": "视觉商业证据（产品特写、Logo、价格表）",
    "B": "行为偏移（与博主既往人设/主题不符）——只能辅助",
    "M": "评论异常（置顶导流、格式化赞美）",
}

GUIDE_VERSION = "1.0"

# ════════════════════════════════════════════════════════════════════
# 6 维关键词向量（优先复用 impad/tools/keywords.py，不可用则本地兜底）
# ════════════════════════════════════════════════════════════════════
try:
    from impad.tools.keywords import (  # type: ignore
        EXPLICIT_AD_MARKERS,
        compute_keyword_weights as _impad_keyword_weights,
        ad_pressure as _impad_ad_pressure,
    )
    _HAS_IMPAD_KEYWORDS = True
    ad_pressure = _impad_ad_pressure
except Exception:  # pragma: no cover - 本地兜底
    _HAS_IMPAD_KEYWORDS = False
    EXPLICIT_AD_MARKERS = ("广告", "赞助", "推广", "合作", "#ad", "恰饭", "商务", "品牌方")

    _PROMOTION_WORDS = ("种草", "安利", "必买", "回购", "强烈推荐", "推荐", "爆款", "热卖",
                        "超赞", "真香", "宝藏", "好用到哭", "值得入", "闭眼入", "无限回购")
    _PRICE_WORDS = ("价格", "多少钱", "性价比", "划算", "超值", "便宜", "实惠", "优惠",
                    "折扣", "特价", "促销", "满减", "到手价", "直降", "原价", "秒杀", "领券")
    _URGENCY_WORDS = ("限时", "抢购", "赶紧", "快来", "马上", "立刻", "立即", "不要错过",
                      "仅剩", "名额有限", "最后一天", "手慢无", "库存告急", "冲鸭")
    _BRAND_WORDS = ("品牌", "官方", "正品", "旗舰店", "专营", "授权", "代理", "招商",
                    "加盟", "货源", "批发", "一件代发", "赞助", "恰饭")
    _ACTION_WORDS = ("点击", "扫码", "链接", "私信", "购买", "下单", "加购", "购物车",
                     "小黄车", "点上方", "戳这里", "领取", "蹲一个", "冲同款")
    _NATURAL_WORDS = ("我觉得", "我认为", "感受", "体验", "心情", "日记", "分享", "记录",
                      "吐槽", "生活", "学习", "朋友", "家人", "今天", "昨天", "周末",
                      "假期", "随手记", "碎碎念")

    _FALLBACK_CATEGORIES = {
        "promotion_words": _PROMOTION_WORDS,
        "price_mentions": _PRICE_WORDS,
        "urgency_expressions": _URGENCY_WORDS,
        "brand_mentions": _BRAND_WORDS,
        "action_words": _ACTION_WORDS,
        "natural_expression": _NATURAL_WORDS,
    }
    _FALLBACK_SATURATION = {
        "promotion_words": 4, "price_mentions": 4, "urgency_expressions": 3,
        "brand_mentions": 3, "action_words": 3, "natural_expression": 5,
    }

    def compute_keyword_weights(text: str) -> Dict[str, float]:
        return {
            dim: round(min(len([w for w in words if w in text]) / _FALLBACK_SATURATION[dim], 1.0), 2)
            for dim, words in _FALLBACK_CATEGORIES.items()
        }

    def ad_pressure(weights: Dict[str, float]) -> float:
        keys = ("promotion_words", "price_mentions", "urgency_expressions", "action_words")
        return round(sum(weights.get(k, 0.0) for k in keys) / len(keys), 2)

WEIGHT_LABELS_ZH = {
    "promotion_words": "促销种草",
    "price_mentions": "价格提及",
    "urgency_expressions": "紧迫感",
    "brand_mentions": "品牌商务",
    "action_words": "行动召唤",
    "natural_expression": "自然表达",
}
WEIGHT_ORDER = ("promotion_words", "price_mentions", "urgency_expressions",
                "brand_mentions", "action_words", "natural_expression")


# ════════════════════════════════════════════════════════════════════
# System Prompt（证判分离设计，见设计文档 4.2）
# ════════════════════════════════════════════════════════════════════
OLLAMA_SYSTEM_PROMPT = """你是社交媒体内容审核专家，专门识别隐性广告（暗广/软广）。
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
}"""


# ════════════════════════════════════════════════════════════════════
# 关键词特征（设计文档 4.3 / 6.1 的 compute_keyword_weights_for_post）
# ════════════════════════════════════════════════════════════════════
def compute_keyword_weights_for_post(text: str) -> Dict[str, float]:
    """封装 keywords.py 的 6 维关键词向量计算。

    Returns: {"promotion_words": 0.5, "price_mentions": 0.25, ...}
    """
    text = text or ""
    if _HAS_IMPAD_KEYWORDS:
        return _impad_keyword_weights(text)
    return compute_keyword_weights(text)


def summarize_keyword_weights(weights: Dict[str, float]) -> str:
    """把 6 维权重向量拼成 LLM 可读的中文摘要。"""
    lines = []
    for dim in WEIGHT_ORDER:
        label = WEIGHT_LABELS_ZH.get(dim, dim)
        lines.append(f"- {label}：{weights.get(dim, 0.0):.2f}")
    return "\n".join(lines)


def has_explicit_ad_marker(text: str) -> bool:
    """是否有明广标识（D 类证据）。"""
    text = text or ""
    return any(marker in text for marker in EXPLICIT_AD_MARKERS)


# ════════════════════════════════════════════════════════════════════
# 图片分析摘要（设计文档 4.3）
# ════════════════════════════════════════════════════════════════════
def summarize_image_analyses(image_analyses: Optional[Dict[int, Dict]]) -> str:
    """把 YOLO+OCR / 多模态 LLM 的图片分析结果汇总成文本。"""
    if not image_analyses:
        return "无图片分析结果"
    parts = []
    for idx in sorted(image_analyses, key=int):
        a = image_analyses[idx] or {}
        if "error" in a:
            parts.append(f"  图片{int(idx) + 1}: 分析失败 ({str(a['error'])[:60]})")
            continue
        detected = a.get("detected_elements", {}) or {}
        codes = a.get("visual_evidence_codes", []) or []
        desc = (a.get("description") or "").strip()[:150]
        active = [k.replace("has_", "") for k, v in detected.items() if v]
        ocr = (a.get("ocr_text") or "").strip()
        method = a.get("analysis_method", "yolo_ocr_auto")
        seg = f"  图片{int(idx) + 1}: 证据代码={codes or '无'} | 检测元素={active or '无'}"
        if desc:
            seg += f" | 描述={desc}"
        if ocr:
            seg += f" | OCR={ocr[:80]}"
        seg += f" | 方法={method}"
        parts.append(seg)
    return "\n".join(parts) if parts else "无图片分析结果"


# ════════════════════════════════════════════════════════════════════
# User Prompt 模板（设计文档 4.3）
# ════════════════════════════════════════════════════════════════════
def build_user_prompt(
    post: Dict[str, Any],
    image_analysis_summary: str,
    keyword_weights: Optional[Dict[str, float]] = None,
) -> str:
    title = (post.get("title") or "").strip() or "(无标题)"
    blogger = (post.get("blogger_id") or "?").strip()
    platform = (post.get("platform") or "?").strip()
    text = post.get("text") or ""
    if len(text) > 5000:
        text = text[:5000] + "\n\n[... 正文过长已截断 ...]"

    weights = keyword_weights or compute_keyword_weights_for_post(text)
    kw_summary = summarize_keyword_weights(weights)

    return f"""## 帖子信息
- 标题：{title}
- 博主：{blogger}
- 平台：{platform}

## 帖子正文
{text}

## 图片分析结果
{image_analysis_summary}

## 关键词特征向量
{kw_summary}

请按系统提示词的要求，输出 JSON 格式的综合判断。"""


# ════════════════════════════════════════════════════════════════════
# Ollama 推理（设计文档 4.1 / 4.2）
# ════════════════════════════════════════════════════════════════════
def ollama_available(url: str = OLLAMA_DEFAULT_URL,
                     timeout: float = OLLAMA_HEALTH_TIMEOUT) -> bool:
    """探测 Ollama 服务是否可用（GET /api/tags）。"""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _extract_json_content(raw: str) -> Optional[Dict[str, Any]]:
    """从 Ollama 返回的文本中提取并解析 JSON 对象（容忍 markdown 代码块包裹）。"""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None


def run_ollama_judge(
    post: Dict[str, Any],
    image_analyses: Optional[Dict[int, Dict]] = None,
    keyword_weights: Optional[Dict[str, float]] = None,
    model: str = OLLAMA_DEFAULT_MODEL,
    url: str = OLLAMA_DEFAULT_URL,
    timeout: float = OLLAMA_TIMEOUT,
) -> Dict[str, Any]:
    """调用 Ollama /api/chat 对单条帖子做综合判定。

    Args:
        post: 帖子记录（title/text/blogger_id/platform）
        image_analyses: {图片序号: 分析结果}，来自 YOLO+OCR / 多模态 LLM
        keyword_weights: 6 维关键词向量；None 时自动计算
        model: Ollama 模型名（默认 qwen3.5:9b）
        url: Ollama 服务地址
        timeout: 请求超时（秒）

    Returns:
        标准化判定结果：
        {
          "label": "明广"|"暗广"|"非广"|"out_of_scope",
          "confidence": 0.0-1.0,
          "evidence_codes": [...],
          "evidence": [...],
          "reasoning": str,
          "uncertain_reason": str|None,
          "information_gaps": [...],
          "_model": model,
          "_backend": "ollama",
        }
        任何失败都会抛出异常（由调用方走 keyword_fallback 回退）。
    """
    text = post.get("text") or ""
    img_summary = summarize_image_analyses(image_analyses)
    weights = keyword_weights or compute_keyword_weights_for_post(text)
    user_prompt = build_user_prompt(post, img_summary, weights)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 1024},
    }

    resp = requests.post(
        f"{url.rstrip('/')}/api/chat",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    content = (body.get("message") or {}).get("content") or ""
    parsed = _extract_json_content(content)
    if parsed is None:
        raise ValueError(f"Ollama 返回非 JSON 内容: {content[:200]!r}")

    parsed["_model"] = model
    parsed["_backend"] = "ollama"
    return normalize_suggestion(parsed)


def normalize_suggestion(suggestion: Dict[str, Any]) -> Dict[str, Any]:
    """标准化 LLM 返回的判定结果（标签/置信度/证据字段校验）。"""
    result = dict(suggestion or {})

    # 标签：兼容中文与代码两种写法
    label = result.get("label") or result.get("suggested_label") or ""
    result["label"] = normalize_label(label)

    # 置信度
    try:
        conf = float(result.get("confidence", result.get("suggested_confidence", 0.0)))
    except (TypeError, ValueError):
        conf = 0.0
    result["confidence"] = round(max(0.0, min(1.0, conf)), 4)

    # 证据代码
    codes = result.get("evidence_codes") or result.get("suggested_evidence_codes") or []
    result["evidence_codes"] = [c for c in codes if c in EVIDENCE_CODES]

    # 证据描述
    evidence = result.get("evidence") or result.get("suggested_evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence] if evidence.strip() else []
    result["evidence"] = [str(e).strip() for e in evidence if str(e).strip()]

    result.setdefault("reasoning", "")
    result.setdefault("uncertain_reason", None)
    result.setdefault("information_gaps", [])

    # 与 flet 端 copilot_suggestion 字段兼容
    result.setdefault("suggested_label", LABEL_TO_CODE.get(result["label"], result["label"]))
    result.setdefault("suggested_confidence", result["confidence"])
    result.setdefault("suggested_evidence_codes", result["evidence_codes"])
    result.setdefault("suggested_evidence", result["evidence"])
    return result


def normalize_label(label: str) -> str:
    """把任意写法的标签归一为中文标签；非法标签返回 '非广'。"""
    label = (label or "").strip()
    if label in VALID_LABELS:
        return label
    if label in LABEL_TO_CODE:
        return label
    if label in CODE_TO_LABEL:
        return CODE_TO_LABEL[label]
    return "非广"


# ════════════════════════════════════════════════════════════════════
# 三级置信度分类（设计文档 3）
# ════════════════════════════════════════════════════════════════════
def classify_confidence(confidence: float,
                        auto_threshold: float = DEFAULT_AUTO_THRESHOLD) -> str:
    """按置信度返回三级分类。

    Returns:
        "auto"    → 高置信度，自动保存（confidence >= auto_threshold）
        "suggest" → 中置信度，展示建议（SUGGESTION_LOWER_BOUND <= c < auto_threshold）
        "manual"  → 低置信度，无建议（confidence < SUGGESTION_LOWER_BOUND）
    """
    if confidence >= auto_threshold:
        return "auto"
    if confidence >= SUGGESTION_LOWER_BOUND:
        return "suggest"
    return "manual"


# ════════════════════════════════════════════════════════════════════
# 失败回退（设计文档 4.4）
# ════════════════════════════════════════════════════════════════════
def keyword_fallback(post: Dict[str, Any],
                     keyword_weights: Optional[Dict[str, float]] = None
                     ) -> Optional[Dict[str, Any]]:
    """纯关键词规则回退。返回 None 表示不做任何建议（纯人工）。

    规则：
      1. 有 explicit_ad_marker → label="明广", confidence=0.90（≥0.85，自动保存）
      2. ad_pressure >= 0.5 且无明广标识 → label="暗广", confidence=0.45（<0.55，强制人工）
      3. 其他 → 返回 None（不做建议）
    """
    text = post.get("text") or ""
    weights = keyword_weights or compute_keyword_weights_for_post(text)
    pressure = ad_pressure(weights)

    if has_explicit_ad_marker(text):
        return normalize_suggestion({
            "label": "明广",
            "confidence": 0.90,
            "evidence_codes": ["D"],
            "evidence": [f"正文含明广标识（如{'/'.join(list(EXPLICIT_AD_MARKERS)[:4])}等）"],
            "reasoning": "正文出现明确广告/赞助/合作标识（D 类证据），且无相反证据，判定为明广。",
            "uncertain_reason": None,
            "information_gaps": [],
            "_model": "keyword-fallback",
            "_backend": "keyword",
        })

    if pressure >= 0.5:
        return normalize_suggestion({
            "label": "暗广",
            "confidence": 0.45,   # 低于 0.55 → 强制人工，不自动保存
            "evidence_codes": ["P"],
            "evidence": [f"关键词导购压力分 {pressure:.2f} ≥ 0.5（促销/价格/紧迫/行动维度）"],
            "reasoning": "关键词规则检测到较强促销/转化信号，但置信度低于人工下限，需人工复核。",
            "uncertain_reason": "规则回退：置信度不足以自动判定，需人工独立判断",
            "information_gaps": [],
            "_model": "keyword-fallback",
            "_backend": "keyword",
        })

    return None


# ════════════════════════════════════════════════════════════════════
# 自动保存记录（设计文档 5.1 / 5.2）
# ════════════════════════════════════════════════════════════════════
def build_auto_record(post: Dict[str, Any],
                      suggestion: Dict[str, Any],
                      model: str = OLLAMA_DEFAULT_MODEL,
                      auto_accepted: bool = True) -> Dict[str, Any]:
    """构建自动保存的标注记录。

    Args:
        post: 帖子记录
        suggestion: 标准化后的 LLM 判定结果
        model: 使用的模型名
        auto_accepted: 是否被自动采纳

    Returns:
        符合设计文档 5.1 结构的标注记录（annotation_method="auto_accepted"）。
    """
    record = {
        "post_id": post.get("post_id", ""),
        "annotator_id": "system",
        "guide_version": GUIDE_VERSION,
        "label": suggestion.get("label", "非广"),
        "confidence": suggestion.get("confidence", 0.0),
        "evidence_codes": suggestion.get("evidence_codes", []),
        "evidence": suggestion.get("evidence", []),
        "uncertain_reason": suggestion.get("uncertain_reason"),
        "annotated_at": datetime.now(CST).isoformat(),
        "annotation_method": "auto_accepted" if auto_accepted else "human",
        "_llm_suggestion": {
            "label": suggestion.get("label", "非广"),
            "confidence": suggestion.get("confidence", 0.0),
            "evidence_codes": suggestion.get("evidence_codes", []),
            "evidence": suggestion.get("evidence", []),
            "reasoning": suggestion.get("reasoning", ""),
            "model": suggestion.get("_model", model),
            "auto_accepted": bool(auto_accepted),
        },
    }
    return record


# ════════════════════════════════════════════════════════════════════
# 完整管线
# ════════════════════════════════════════════════════════════════════
def run_auto_judge(
    post: Dict[str, Any],
    image_analyses: Optional[Dict[int, Dict]] = None,
    keyword_weights: Optional[Dict[str, float]] = None,
    model: str = OLLAMA_DEFAULT_MODEL,
    url: str = OLLAMA_DEFAULT_URL,
    timeout: float = OLLAMA_TIMEOUT,
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
) -> Dict[str, Any]:
    """完整自动判断管线：Ollama 判定 → 失败回退 → 三级分类。

    Returns:
        {
          "suggestion": 标准化判定结果 或 None（纯人工）,
          "tier": "auto" | "suggest" | "manual",
          "auto_threshold": auto_threshold,
          "record": 自动保存的标注记录（tier=="auto" 时非 None）,
          "fallback": bool（是否走了关键词回退）,
          "error": str|None（Ollama 失败原因，回退时记录）,
        }
    """
    suggestion: Optional[Dict[str, Any]] = None
    fallback = False
    error: Optional[str] = None

    try:
        suggestion = run_ollama_judge(
            post, image_analyses, keyword_weights,
            model=model, url=url, timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - Ollama 不可用/超时/非 JSON 一律回退
        error = str(exc)[:300]
        fallback = True
        suggestion = keyword_fallback(post, keyword_weights)

    tier = "manual"
    record: Optional[Dict[str, Any]] = None
    if suggestion is not None:
        tier = classify_confidence(suggestion.get("confidence", 0.0), auto_threshold)
        if tier == "auto":
            record = build_auto_record(
                post, suggestion,
                model=suggestion.get("_model", model),
                auto_accepted=True,
            )

    return {
        "suggestion": suggestion,
        "tier": tier,
        "auto_threshold": auto_threshold,
        "record": record,
        "fallback": fallback,
        "error": error,
    }


# ════════════════════════════════════════════════════════════════════
# 便捷的 ad_pressure 导出（供 flet / CLI 直接用）
# ════════════════════════════════════════════════════════════════════
def compute_ad_pressure(text: str) -> float:
    """计算帖子的关键词导购压力分（0~1）。"""
    return ad_pressure(compute_keyword_weights_for_post(text))


if __name__ == "__main__":
    # 自检：不依赖 Ollama 的关键词部分
    print("auto_judge.py 自检")
    print(f"  impad keywords 可用: {_HAS_IMPAD_KEYWORDS}")
    test_post = {"post_id": "post_selftest", "title": "测试", "text": "今天分享一个限时优惠，点击链接立即下单，无限回购！", "platform": "wechat_official_account"}
    w = compute_keyword_weights_for_post(test_post["text"])
    print(f"  关键词向量: {w}")
    print(f"  ad_pressure: {compute_ad_pressure(test_post['text'])}")
    fb = keyword_fallback(test_post)
    print(f"  关键词回退: {fb['label'] if fb else None} (conf={fb['confidence'] if fb else '-'})")
    explicit = {"post_id": "post_selftest2", "title": "测试", "text": "#广告 感谢品牌方赞助，产品真的很好用", "platform": "wechat_official_account"}
    fb2 = keyword_fallback(explicit)
    print(f"  明广回退: {fb2['label'] if fb2 else None} (conf={fb2['confidence'] if fb2 else '-'})")
    print(f"  Ollama 可用: {ollama_available()}")
    print("自检完成")
