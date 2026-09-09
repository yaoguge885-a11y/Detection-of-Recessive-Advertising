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
import hashlib
import math
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
# 模型常驻时间：默认 5 分钟后 Ollama 会卸载模型，冷启动加载 6.6GB 很慢。
# 设为较长时间（或 -1 永久常驻），避免每条帖子都重新加载模型。
OLLAMA_KEEP_ALIVE = "30m"
# 预热模型超时（秒）：首次加载 6.6GB 模型可能需要较长时间，单独放宽
OLLAMA_WARMUP_TIMEOUT = 300
# 完整指南 + 最长正文 + 评论摘要会超过 Ollama 默认 4,096 token。
# 显式申请 32K，仍远低于 qwen3.5:4b 本地模型声明的 262K 上限。
OLLAMA_NUM_CTX = 32768
# Qwen3.5 默认开启 thinking 会消耗大量 token 并拖慢推理；
# 自动判断只关心最终 JSON 判定，关闭 thinking 模式可显著加速。
OLLAMA_DISABLE_THINKING = True

DEFAULT_AUTO_THRESHOLD = 0.85  # 自动保存阈值（默认，可调 0.70–0.95）
SUGGESTION_LOWER_BOUND = 0.55  # 建议展示下限：低于此值不展示建议（防锚定）

# 标签（与设计文档一致，中文标签；flet 端用代码可经 LABEL_TO_CODE 转换）
VALID_LABELS = ("明广", "暗广", "非广", "uncertain", "out_of_scope")
LABEL_TO_CODE = {
    "明广": "mingguang",
    "暗广": "anguang",
    "非广": "feiguang",
    "uncertain": "uncertain",
    "out_of_scope": "out_of_scope",
}
CODE_TO_LABEL = {v: k for k, v in LABEL_TO_CODE.items()}
LABEL_ALIASES = {
    "不确定": "uncertain",
    "无法判断": "uncertain",
    "需复核": "uncertain",
}

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
- uncertain：证据缺失、冲突、未采集或不可读，当前不能可靠归入三元标签
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
  "label": "明广" | "暗广" | "非广" | "uncertain" | "out_of_scope",
  "confidence": 0.0-1.0,
  "evidence_codes": ["D", "V"],
  "evidence": ["原文引用1", "原文引用2"],
  "reasoning": "综合推理过程（50-150字）",
  "uncertain_reason": null,
  "information_gaps": ["如果能看到评论区置顶..."]
}

## 输出要求
- **直接输出最终 JSON 结果**，不要输出思考过程、不要使用 <think> 等推理标签
- 只输出一个 JSON 对象，不要 markdown 代码块包裹
- 证据缺失、采集状态未知或披露区域不完整时输出 uncertain；不得把“未提供”当成“未发现”
- 如果确实需要简短思考，请确保最终以完整 JSON 对象结尾"""


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


def sha256_text(text: str) -> str:
    """返回 UTF-8 文本的 SHA-256；空文本返回空字符串。"""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_collection_complete(value: Any) -> str:
    """把不同来源的采集完整性字段归一为 complete/incomplete/unknown。"""
    if value is True:
        return "complete"
    if value is False:
        return "incomplete"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"complete", "completed", "true", "yes"}:
            return "complete"
        if normalized in {"incomplete", "partial", "false", "no"}:
            return "incomplete"
        return "unknown"
    if isinstance(value, dict):
        for key in ("status", "collection_status"):
            if key in value:
                state = normalize_collection_complete(value.get(key))
                if state != "unknown":
                    return state
        if "complete" in value:
            return normalize_collection_complete(value.get("complete"))
        relevant = [
            value[key]
            for key in (
                "page_complete",
                "disclosure_area_complete",
                "comments_complete",
                "media_complete",
            )
            if key in value
        ]
        if relevant:
            if any(item is False for item in relevant):
                return "incomplete"
            if all(item is True for item in relevant):
                return "complete"
    return "unknown"


def determine_media_evidence_status(
    post: Dict[str, Any],
    image_analyses: Optional[Dict[int, Dict]],
    media_analysis_requested: Optional[bool] = None,
) -> str:
    """区分无媒体、未请求、未提供、分析失败和已提供，避免证据语义混淆。"""
    media = [m for m in (post.get("media") or []) if isinstance(m, dict)]
    if not media:
        return "no_media"
    if media_analysis_requested is False:
        return "not_requested"
    if image_analyses is None:
        return "not_provided"
    if not image_analyses:
        return "attempted_no_result" if media_analysis_requested else "not_provided"
    successful = sum(
        1 for analysis in image_analyses.values()
        if isinstance(analysis, dict) and "error" not in analysis
    )
    if successful == 0:
        return "analysis_failed"
    if (successful < len(image_analyses)
            or set(image_analyses) != set(range(len(media)))):
        return "partial"
    return "provided"


def summarize_comments(comments: Any, max_chars: int = 4000) -> str:
    """把已采集评论整理为可追踪的 Prompt 片段，并限制总长度。"""
    if not isinstance(comments, list) or not comments:
        return "无已提供评论（不代表评论区已完整采集）"
    lines: List[str] = []
    used = 0
    for index, comment in enumerate(comments[:30], 1):
        if isinstance(comment, dict):
            text = str(comment.get("text") or "").strip()
        else:
            text = str(comment).strip()
        if not text:
            continue
        line = f"- 评论{index}：{text}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(line) > remaining:
            lines.append(line[:remaining] + "[…已截断…]")
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines) if lines else "无可读评论（不代表评论区已完整采集）"


# ════════════════════════════════════════════════════════════════════
# User Prompt 模板（设计文档 4.3）
# ════════════════════════════════════════════════════════════════════
def build_user_prompt(
    post: Dict[str, Any],
    image_analysis_summary: str,
    keyword_weights: Optional[Dict[str, float]] = None,
    *,
    guide_text: str = "",
    guide_version: str = GUIDE_VERSION,
    guide_sha256: str = "",
    media_evidence_status: str = "unknown",
    collection_complete: Any = None,
) -> str:
    title = (post.get("title") or "").strip() or "(无标题)"
    blogger = (post.get("blogger_id") or "?").strip()
    platform = (post.get("platform") or "?").strip()
    text = post.get("text") or ""
    if len(text) > 5000:
        text = text[:5000] + "\n\n[... 正文过长已截断 ...]"

    weights = keyword_weights or compute_keyword_weights_for_post(text)
    kw_summary = summarize_keyword_weights(weights)
    comments_summary = summarize_comments(post.get("comments"))
    guide_hash = guide_sha256 or sha256_text(guide_text)
    collection_state = normalize_collection_complete(collection_complete)
    media_count = len(post.get("media") or [])
    authoritative_guide = guide_text.strip() or "（未提供外部指南；只能使用系统内置规则）"

    return f"""## 权威标注指南（必须遵循）
- 版本：{guide_version or "unknown"}
- SHA-256：{guide_hash or "unknown"}

{authoritative_guide}

## 本次证据可用性
- collection_complete：{collection_state}
- media_evidence_status：{media_evidence_status}
- 帖子媒体引用数：{media_count}
- 重要：not_requested / not_provided / unknown 表示证据未知，不表示证据不存在。

## 帖子信息
- 标题：{title}
- 博主：{blogger}
- 平台：{platform}

## 帖子正文
{text}

## 图片分析结果
{image_analysis_summary}

## 已提供评论
{comments_summary}

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
    """从 Ollama 返回的文本中提取并解析 JSON 对象。

    容忍：
      - markdown 代码块包裹（```json ... ```）
      - Qwen3.5 的 thinking 前缀（模型可能先输出思考过程再输出 JSON）
      - JSON 前后混有其他文本

    使用括号配平定位 JSON 对象，避免贪婪正则把 thinking 内容也算进去。
    """
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    # 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 括号配平定位最外层 JSON 对象
    start = raw.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[start:i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
        start = raw.find("{", start + 1)
    return None


def run_ollama_judge(
    post: Dict[str, Any],
    image_analyses: Optional[Dict[int, Dict]] = None,
    keyword_weights: Optional[Dict[str, float]] = None,
    model: str = OLLAMA_DEFAULT_MODEL,
    url: str = OLLAMA_DEFAULT_URL,
    timeout: float = OLLAMA_TIMEOUT,
    keep_alive: Optional[str] = None,
    guide_text: str = "",
    guide_version: str = GUIDE_VERSION,
    guide_sha256: str = "",
    media_analysis_requested: Optional[bool] = None,
    collection_complete: Any = None,
    num_ctx: int = OLLAMA_NUM_CTX,
) -> Dict[str, Any]:
    """调用 Ollama /api/chat 对单条帖子做综合判定。

    Args:
        post: 帖子记录（title/text/blogger_id/platform）
        image_analyses: {图片序号: 分析结果}，来自 YOLO+OCR / 多模态 LLM
        keyword_weights: 6 维关键词向量；None 时自动计算
        model: Ollama 模型名（默认 qwen3.5:9b）
        url: Ollama 服务地址
        timeout: 请求超时（秒）
        keep_alive: 模型常驻时长（如 "30m"、"-1"）；None 用全局默认。
                   设长可避免每条帖子重新加载模型（冷启动加载 6.6GB 很慢）。

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
    media_status = determine_media_evidence_status(
        post, image_analyses, media_analysis_requested
    )
    collection_value = (
        post.get("collection_complete")
        if collection_complete is None and "collection_complete" in post
        else collection_complete
    )
    collection_state = normalize_collection_complete(collection_value)
    resolved_guide_hash = guide_sha256 or sha256_text(guide_text)
    img_summary = (
        f"证据状态={media_status}\n{summarize_image_analyses(image_analyses)}"
    )
    weights = keyword_weights or compute_keyword_weights_for_post(text)
    user_prompt = build_user_prompt(
        post,
        img_summary,
        weights,
        guide_text=guide_text,
        guide_version=guide_version,
        guide_sha256=resolved_guide_hash,
        media_evidence_status=media_status,
        collection_complete=collection_value,
    )

    # Qwen3.5 默认开启 thinking 会消耗上千 token、每帖 30-50s。
    # 顶层 "think": false 是 Qwen3 在 Ollama 0.32.5 下验证有效的禁用方式
    # （放进 options 里不生效）。禁用后每帖约 2-5 秒。
    options: Dict[str, Any] = {
        "temperature": 0.0,
        "num_predict": 1024,
        "num_ctx": int(num_ctx),
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
        "keep_alive": keep_alive or OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    if OLLAMA_DISABLE_THINKING:
        # 顶层参数：禁用思考（Qwen3 在 Ollama 0.32.5 下验证有效，
        # 每帖从 ~30-50s 降到 ~2-5s；放进 options 里不生效）
        payload["think"] = False

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

    raw_label = parsed.get("label", parsed.get("suggested_label"))
    parsed["label_raw"] = raw_label
    parsed["_model"] = model
    parsed["_backend"] = "ollama"
    parsed["_guide_version"] = guide_version or "unknown"
    parsed["_guide_sha256"] = resolved_guide_hash or "unknown"
    parsed["_media_evidence_status"] = media_status
    parsed["_collection_complete"] = collection_state
    parsed["_num_ctx"] = int(num_ctx)
    normalized = normalize_suggestion(parsed)
    return enforce_evidence_contract(
        normalized,
        post=post,
        media_evidence_status=media_status,
        collection_complete=collection_state,
    )


def warm_up_model(model: str = OLLAMA_DEFAULT_MODEL,
                  url: str = OLLAMA_DEFAULT_URL,
                  timeout: float = OLLAMA_WARMUP_TIMEOUT,
                  keep_alive: Optional[str] = None,
                  num_ctx: int = OLLAMA_NUM_CTX) -> bool:
    """预加载模型：批处理前用最小请求把模型加载进内存并驻留。

    6.6GB 模型首次冷启动加载需要 60~120s+，容易超过单条推理超时。
    先预热一次，后续每条帖子的推理即可命中已加载模型，显著提速。

    Returns:
        True=模型已就绪（加载成功或已加载）；False=预热失败（继续走回退）。
    """
    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "keep_alive": keep_alive or OLLAMA_KEEP_ALIVE,
            "options": {
                "num_predict": 1,
                "temperature": 0.0,
                "num_ctx": int(num_ctx),
            },
        }
        if OLLAMA_DISABLE_THINKING:
            payload["think"] = False
        resp = requests.post(f"{url.rstrip('/')}/api/chat", json=payload, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


class SuggestionContractError(ValueError):
    """模型输出不满足标签契约；调用方必须失败关闭并转人工。"""


def normalize_suggestion(suggestion: Dict[str, Any]) -> Dict[str, Any]:
    """标准化 LLM 返回的判定结果（标签/置信度/证据字段校验）。"""
    result = dict(suggestion or {})

    # 标签：兼容中文与代码两种写法
    label = result.get("label") or result.get("suggested_label") or ""
    result.setdefault("label_raw", label)
    result["label"] = normalize_label(label)

    # 置信度
    try:
        conf = float(result.get("confidence", result.get("suggested_confidence", 0.0)))
    except (TypeError, ValueError):
        conf = 0.0
    if not math.isfinite(conf):
        conf = 0.0
    result.setdefault("confidence_raw", conf)
    result["confidence"] = round(max(0.0, min(1.0, conf)), 4)
    if result["label"] == "uncertain":
        # uncertain 永远进入纯人工层；保留 confidence_raw 供审计。
        result["confidence"] = 0.0

    # 证据代码
    codes = result.get("evidence_codes") or result.get("suggested_evidence_codes") or []
    if isinstance(codes, str):
        codes = [codes]
    result["evidence_codes"] = [c for c in codes if c in EVIDENCE_CODES]

    # 证据描述
    evidence = result.get("evidence") or result.get("suggested_evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence] if evidence.strip() else []
    result["evidence"] = [str(e).strip() for e in evidence if str(e).strip()]

    result.setdefault("reasoning", "")
    result.setdefault("uncertain_reason", None)
    result.setdefault("information_gaps", [])
    if isinstance(result["information_gaps"], str):
        gap = result["information_gaps"].strip()
        result["information_gaps"] = [gap] if gap else []
    if result["label"] == "uncertain" and not result["uncertain_reason"]:
        result["uncertain_reason"] = "模型判断为 uncertain，需人工复核"

    # 与 flet 端 copilot_suggestion 字段兼容
    result.setdefault("suggested_label", LABEL_TO_CODE.get(result["label"], result["label"]))
    result.setdefault("suggested_confidence", result["confidence"])
    result.setdefault("suggested_evidence_codes", result["evidence_codes"])
    result.setdefault("suggested_evidence", result["evidence"])
    return result


def normalize_label(label: Any) -> str:
    """把已知写法归一为规范标签；非法或空标签显式失败。"""
    label = str(label or "").strip()
    if label in LABEL_ALIASES:
        return LABEL_ALIASES[label]
    if label in VALID_LABELS:
        return label
    if label in LABEL_TO_CODE:
        return label
    if label in CODE_TO_LABEL:
        return CODE_TO_LABEL[label]
    error = SuggestionContractError(f"非法标签: {label!r}")
    error.label_raw = label
    raise error


def enforce_evidence_contract(
    suggestion: Dict[str, Any],
    *,
    post: Dict[str, Any],
    media_evidence_status: str,
    collection_complete: Any,
) -> Dict[str, Any]:
    """暗广必须有完整披露链；缺失/未知证据时程序化转入 uncertain。"""
    result = dict(suggestion)
    if result.get("label") != "暗广":
        return result

    gaps: List[str] = []
    collection_state = normalize_collection_complete(collection_complete)
    if collection_state != "complete":
        gaps.append(f"披露区域/评论采集完整性为 {collection_state}")

    has_media = bool(post.get("media"))
    if has_media and media_evidence_status not in {"provided", "no_media"}:
        gaps.append(f"媒体证据状态为 {media_evidence_status}")

    if not gaps:
        return result

    prior_reason = str(result.get("uncertain_reason") or "").strip()
    reason = "；".join(gaps) + "，不能据此强判暗广，需人工复核"
    if prior_reason:
        reason = f"{reason}；模型原说明：{prior_reason}"
    information_gaps = list(result.get("information_gaps") or [])
    for gap in gaps:
        if gap not in information_gaps:
            information_gaps.append(gap)

    result["label"] = "uncertain"
    result["confidence"] = 0.0
    result["uncertain_reason"] = reason
    result["information_gaps"] = information_gaps
    result["suggested_label"] = "uncertain"
    result["suggested_confidence"] = 0.0
    result["_evidence_contract_override"] = True
    return result


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
    # 研究治理约定：0 明确表示关闭自动接受，而不是“所有结果都自动接受”。
    if auto_threshold > 0 and confidence >= auto_threshold:
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
        "guide_version": suggestion.get("_guide_version", GUIDE_VERSION),
        "guide_sha256": suggestion.get("_guide_sha256", "unknown"),
        "label_raw": suggestion.get("label_raw"),
        "label": suggestion.get("label", "uncertain"),
        "confidence": suggestion.get("confidence", 0.0),
        "evidence_codes": suggestion.get("evidence_codes", []),
        "evidence": suggestion.get("evidence", []),
        "uncertain_reason": suggestion.get("uncertain_reason"),
        "annotated_at": datetime.now(CST).isoformat(),
        "annotation_method": "auto_accepted" if auto_accepted else "human",
        "backend": suggestion.get("_backend", "unknown"),
        "fallback": bool(suggestion.get("_fallback", False)),
        "error": suggestion.get("_error"),
        "media_evidence_status": suggestion.get("_media_evidence_status", "unknown"),
        "collection_complete": suggestion.get("_collection_complete", "unknown"),
        "num_ctx": suggestion.get("_num_ctx", OLLAMA_NUM_CTX),
        "_llm_suggestion": {
            "label_raw": suggestion.get("label_raw"),
            "label": suggestion.get("label", "uncertain"),
            "confidence": suggestion.get("confidence", 0.0),
            "confidence_raw": suggestion.get("confidence_raw"),
            "evidence_codes": suggestion.get("evidence_codes", []),
            "evidence": suggestion.get("evidence", []),
            "reasoning": suggestion.get("reasoning", ""),
            "model": suggestion.get("_model", model),
            "backend": suggestion.get("_backend", "unknown"),
            "fallback": bool(suggestion.get("_fallback", False)),
            "error": suggestion.get("_error"),
            "guide_sha256": suggestion.get("_guide_sha256", "unknown"),
            "media_evidence_status": suggestion.get("_media_evidence_status", "unknown"),
            "collection_complete": suggestion.get("_collection_complete", "unknown"),
            "num_ctx": suggestion.get("_num_ctx", OLLAMA_NUM_CTX),
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
    keep_alive: Optional[str] = None,
    guide_text: str = "",
    guide_version: str = GUIDE_VERSION,
    guide_sha256: str = "",
    media_analysis_requested: Optional[bool] = None,
    collection_complete: Any = None,
    num_ctx: int = OLLAMA_NUM_CTX,
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
    media_status = determine_media_evidence_status(
        post, image_analyses, media_analysis_requested
    )
    collection_value = (
        post.get("collection_complete")
        if collection_complete is None and "collection_complete" in post
        else collection_complete
    )
    collection_state = normalize_collection_complete(collection_value)
    resolved_guide_hash = guide_sha256 or sha256_text(guide_text) or "unknown"

    try:
        suggestion = run_ollama_judge(
            post, image_analyses, keyword_weights,
            model=model, url=url, timeout=timeout, keep_alive=keep_alive,
            guide_text=guide_text,
            guide_version=guide_version,
            guide_sha256=resolved_guide_hash,
            media_analysis_requested=media_analysis_requested,
            collection_complete=collection_value,
            num_ctx=num_ctx,
        )
    except SuggestionContractError as exc:
        error = str(exc)[:300]
        suggestion = normalize_suggestion({
            "label": "uncertain",
            "label_raw": getattr(exc, "label_raw", None),
            "confidence": 0.0,
            "evidence_codes": [],
            "evidence": [],
            "reasoning": f"模型标签契约错误: {error}",
            "uncertain_reason": "模型输出标签不合法，已失败关闭并转纯人工",
            "information_gaps": ["需要人工复核模型原始输出"],
            "_model": model,
            "_backend": "ollama-contract-error",
        })
    except Exception as exc:  # noqa: BLE001 - Ollama 不可用/超时/非 JSON 一律回退
        error = str(exc)[:300]
        fallback = True
        suggestion = keyword_fallback(post, keyword_weights)

    if suggestion is not None:
        suggestion.setdefault("_model", model)
        suggestion.setdefault("_backend", "unknown")
        suggestion.setdefault("_guide_version", guide_version or "unknown")
        suggestion.setdefault("_guide_sha256", resolved_guide_hash)
        suggestion.setdefault("_media_evidence_status", media_status)
        suggestion.setdefault("_collection_complete", collection_state)
        suggestion.setdefault("_num_ctx", int(num_ctx))
        suggestion["_fallback"] = fallback
        suggestion["_error"] = error

    tier = "manual"
    record: Optional[Dict[str, Any]] = None
    if suggestion is not None:
        if suggestion.get("label") in {"uncertain", "out_of_scope"}:
            tier = "manual"
        else:
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
        "backend": suggestion.get("_backend", "none") if suggestion else "none",
        "label_raw": suggestion.get("label_raw") if suggestion else None,
        "guide_version": guide_version or "unknown",
        "guide_sha256": resolved_guide_hash,
        "media_evidence_status": media_status,
        "collection_complete": collection_state,
        "num_ctx": int(num_ctx),
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
