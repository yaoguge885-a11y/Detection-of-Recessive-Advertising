#!/usr/bin/env python3
"""
Flet GUI ——

   - /
   - <图片N>
   - YOLO+OCR / LLM (GPT-4V/Qwen-VL/GLM-4V)
   - LLM  — AI
   -  +  + Markdown
   -  +

:

  python scripts/data/annotation/flet_annotator.py \
    --input data/interim/candidates_v1_dedup.jsonl \
    --output-dir data/annotations \
    --media-base data

: pip install flet ultralytics easyocr openai
"""
from __future__ import annotations

import json, os, re, sys, threading, time, base64, webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CST = timezone(timedelta(hours=8))
import flet as ft

# ── LLM / 多模态模型配置 ──
_LLM_CONFIG = {
    "enabled": True,
    "image_model": "gpt-4o-mini",          # 多模态图片分析模型
    "image_backend": "openai",             # "openai" 或 "ollama"
    "image_base_url": os.getenv("OPENAI_BASE_URL", None),
    "image_api_key": os.getenv("OPENAI_API_KEY", None),
    "text_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),  # 纯文本 LLM（协驾标注建议）
    "text_base_url": os.getenv("OPENAI_BASE_URL", None),
    "text_api_key": os.getenv("OPENAI_API_KEY", None),
}

# ── 分置信度自动判断（co-pilot-auto-judge-design v1.0）──
try:
    from auto_judge import (  # type: ignore
        run_ollama_judge as _aj_run_ollama_judge,
        compute_keyword_weights_for_post,
        classify_confidence,
        build_auto_record,
        DEFAULT_AUTO_THRESHOLD,
        SUGGESTION_LOWER_BOUND,
        OLLAMA_DEFAULT_MODEL,
        OLLAMA_DEFAULT_URL,
        OLLAMA_TIMEOUT,
        LABEL_TO_CODE,
    )
    _HAS_AUTO_JUDGE = True
except Exception:  # pragma: no cover - auto_judge 不可用时降级为旧行为
    _HAS_AUTO_JUDGE = False
    DEFAULT_AUTO_THRESHOLD = 0.85
    SUGGESTION_LOWER_BOUND = 0.55
    OLLAMA_DEFAULT_MODEL = "qwen3.5:9b"
    OLLAMA_DEFAULT_URL = "http://localhost:11434"
    OLLAMA_TIMEOUT = 120
    LABEL_TO_CODE = {"明广": "mingguang", "暗广": "anguang",
                     "非广": "feiguang", "out_of_scope": "out_of_scope"}

    def _aj_run_ollama_judge(*a, **k):  # type: ignore
        raise RuntimeError("auto_judge 模块不可用")

    def compute_keyword_weights_for_post(text):  # type: ignore
        return {}

    def classify_confidence(conf, auto_threshold=DEFAULT_AUTO_THRESHOLD):  # type: ignore
        return "manual"

    def build_auto_record(*a, **k):  # type: ignore
        return {}

def _border_all(width=1, color=None):
    """Flet 0.86.x compatible border helper (ft.border.all removed)."""
    if color is None: color = ft.Colors.GREY_300
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, bottom=side, left=side, right=side)

VALID_LABELS = ["mingguang", "anguang", "feiguang", "out_of_scope"]
LABEL_NAMES = {"mingguang": "明广", "anguang": "暗广", "feiguang": "非广", "out_of_scope": "范围外"}
EVIDENCE_CODES = {
    "D": "明示商业关系（广告/赞助/合作标识）",
    "C": "明确商业对象（单一品牌/商品/店铺/服务）",
    "P": "劝服/促销话术（夸赞、限时、价格刺激）",
    "A": "转化动作（下单、扫码、优惠码、链接）",
    "V": "视觉商业证据（产品特写、Logo、价格表）",
    "B": "行为偏移（与博主既往人设/主题不符）",
    "M": "评论异常（置顶导流、格式化赞美）",
}

def load_posts(input_path: Path) -> List[Dict]:
    """加载 JSONL/JSON 文件，兼容缩进多行 JSON 和爬虫产出的结构异常。

    处理已知的爬虫 bug：
    1. text 字段后孤立的 "],\n  \"comments\"" → 移除 stray ],
    2. media 片段缺失闭合 ]} 导致与下一个帖子粘连
    3. orphan media 自动合并回所属帖子
    """
    raw = input_path.read_text(encoding="utf-8-sig")

    # ── Fix 1: 移除 text 字段后的 stray ], ──
    # "...\",\n\n  ],\n  \"comments\""  →  "...\",\n  \"comments\""
    raw = re.sub(r',\s*\n\s*\],\s*\n(\s*)"comments"', r',\n\1"comments"', raw)

    # ── Fix 2: orphan media 片段缺少闭合 ]} → 插入缺失的 ]} ──
    # {  "media": [ { ... } \n  "schema_version"  →  {  "media": [ { ... } ] }\n{  "schema_version"
    raw = re.sub(
        r'(\{\s*"media":\s*\[.*?\})\s*\n(\s*"schema_version")',
        r'\1\n  ]\n}\n\n\2',
        raw, flags=re.DOTALL
    )

    # ── Parse all top-level JSON objects ──
    records = []
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    while idx < n:
        while idx < n and raw[idx] in " \t\n\r":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            if isinstance(obj, dict):
                records.append(obj)
            idx = end
        except json.JSONDecodeError:
            next_brace = raw.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace

    # ── 分离有效帖子和 orphan media 片段 ──
    posts = []
    orphan_media: Dict[str, List[Dict]] = {}
    for obj in records:
        pid = obj.get("post_id", "")
        if pid:
            posts.append(obj)
        elif "media" in obj and set(obj.keys()) <= {"media"}:
            for m in obj.get("media", []):
                if not isinstance(m, dict):
                    continue
                mid = m.get("media_id", "")
                match = re.match(r"media_(post_[a-f0-9]+)_\d+", mid)
                if match:
                    orphan_media.setdefault(match.group(1), []).append(m)

    # ── 合并 orphan media ──
    if orphan_media:
        for post in posts:
            pid = post.get("post_id", "")
            if pid in orphan_media:
                existing = post.get("media", [])
                post["media"] = existing + orphan_media[pid]

    return posts

def load_existing(output_dir: Path, aid: str) -> Tuple[Optional[Path], Set[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        list(output_dir.glob(f"{aid}_*.json")) + list(output_dir.glob(f"{aid}_*.jsonl")),
        key=os.path.getmtime, reverse=True)
    if not candidates: return None, set()
    latest = candidates[0]
    completed = set()
    # Use raw_decode to handle pretty-printed multi-line JSON
    raw = latest.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    while idx < n:
        while idx < n and raw[idx] in " \t\n\r": idx += 1
        if idx >= n: break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            pid = obj.get("post_id", "")
            if pid: completed.add(pid)
            idx = end
        except json.JSONDecodeError:
            next_brace = raw.find("{", idx + 1)
            if next_brace == -1: break
            idx = next_brace
    return latest, completed

def save_annotation(output_dir: Path, aid: str, record: Dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    fpath = output_dir / f"{aid}_{ts}.json"
    with fpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return fpath

def run_image_analysis_bg(post: Dict, media_base: Path, callback):
    try:
        from image_prefilter import extract_content_image_indices
        text = post.get("text", "")
        indices = extract_content_image_indices(text)
        media = post.get("media", [])
        results = {}
        for i in indices:
            if i >= len(media): continue
            ref = media[i].get("ref", "")
            img_path = media_base / ref
            if not img_path.exists():
                results[i] = {"error": "file missing"}
                continue
            try:
                from auto_image_annotate import load_yolo, load_ocr, analyze_image
                yolo = load_yolo()
                ocr = load_ocr()
                analysis = analyze_image(yolo, ocr, img_path, i + 1, ref, "")
                results[i] = {
                    "detected_elements": analysis.get("detected_elements", {}),
                    "visual_evidence_codes": analysis.get("visual_evidence_codes", []),
                    "description": analysis.get("description", ""),
                    "ocr_text": analysis.get("ocr_text"),
                    "analysis_method": "yolo_ocr_auto",
                }
            except Exception as e:
                results[i] = {"error": str(e)[:100]}
        if callback: callback(results)
    except Exception as e:
        if callback: callback({"__error__": str(e)[:200]})


def run_llm_image_analysis_bg(post: Dict, media_base: Path, callback, model=None, backend=None, base_url=None, api_key=None):
    """使用多模态 LLM（GPT-4V / Qwen-VL / GLM-4V / Ollama）分析图片。

    与 run_image_analysis_bg 接口一致，输出兼容的 results dict。
    """
    try:
        from image_prefilter import extract_content_image_indices
        from multimodal_image_analyzer import analyze_images_multimodal

        text = post.get("text", "")
        indices = extract_content_image_indices(text)
        media = post.get("media", [])
        results = {}

        # 收集所有有效图片路径
        valid_items = []
        for i in indices:
            if i >= len(media): continue
            ref = media[i].get("ref", "")
            img_path = media_base / ref
            if img_path.exists():
                valid_items.append((i, img_path, ref))
            else:
                results[i] = {"error": "file missing"}

        if valid_items:
            img_paths = [p for _, p, _ in valid_items]
            # 调用多模态分析（逐张分析，保证 robust）
            for idx, img_path, ref in valid_items:
                try:
                    entries = analyze_images_multimodal(
                        [img_path],
                        model=model or _LLM_CONFIG["image_model"],
                        backend=backend or _LLM_CONFIG["image_backend"],
                        base_url=base_url or _LLM_CONFIG["image_base_url"],
                        api_key=api_key or _LLM_CONFIG["image_api_key"],
                    )
                    if entries:
                        entry = entries[0]
                        results[idx] = {
                            "detected_elements": entry.get("detected_elements", {}),
                            "visual_evidence_codes": entry.get("visual_evidence_codes", []),
                            "description": entry.get("description", ""),
                            "ocr_text": None,  # 多模态模型不分离 OCR
                            "analysis_method": f"multimodal_{model or _LLM_CONFIG['image_model']}",
                            "relevance_to_annotation": entry.get("relevance_to_annotation", ""),
                            "image_quality_notes": entry.get("image_quality_notes", ""),
                            "commercial_intent_score": entry.get("commercial_intent_score", 0.0),
                        }
                    else:
                        results[idx] = {"error": "no result from model"}
                except Exception as e:
                    results[idx] = {"error": str(e)[:100]}

        if callback: callback(results)
    except Exception as e:
        if callback: callback({"__error__": str(e)[:200]})


def run_llm_copilot_suggestion_bg(post: Dict, image_analyses: Dict, callback, model=None, base_url=None, api_key=None, backend="openai", ollama_url=None, ollama_timeout=120):
    """LLM ：根据帖子文本 + 图片分析结果，生成标注建议。

    backend 支持：
      - "openai"（默认）：OpenAI 兼容云端 LLM
      - "ollama"：本地 Ollama（Qwen3.5 9B，分置信度自动判断系统）

    输出格式（通过 callback 传递）:
    {
        "suggested_label": "mingguang" | "anguang" | "feiguang" | "out_of_scope",
        "suggested_evidence_codes": ["V", "D", ...],
        "suggested_evidence": ["证据描述1", "证据描述2", ...],
        "suggested_confidence": 0.0 ~ 1.0,
        "reasoning": "建议理由（1-3句）",
    }
    """
    try:
        # ── 本地 Ollama 后端：走分置信度自动判断系统 ──
        if backend == "ollama":
            suggestion = _aj_run_ollama_judge(
                post,
                image_analyses=image_analyses,
                keyword_weights=None,
                model=model or OLLAMA_DEFAULT_MODEL,
                url=ollama_url or OLLAMA_DEFAULT_URL,
                timeout=ollama_timeout,
            )
            # auto_judge 已归一化出 suggested_* 字段，直接回调
            if callback:
                callback(suggestion)
            return

        from openai import OpenAI

        client = OpenAI(
            api_key=api_key or _LLM_CONFIG["text_api_key"],
            base_url=base_url or _LLM_CONFIG["text_base_url"] or "https://api.openai.com/v1",
        )

        # 构建 prompt
        title = post.get("title", "")
        text = post.get("text", "")
        blogger = post.get("blogger_id", "")
        platform = post.get("platform", "")

        # 截断过长文本
        if len(text) > 3000:
            text = text[:3000] + "\n...(truncated)"

        # 汇总图片分析
        img_summary_parts = []
        for idx, a in sorted(image_analyses.items()):
            if "error" in a:
                img_summary_parts.append(f"  Pic{idx+1}: 分析失败 ({a['error'][:60]})")
            else:
                detected = a.get("detected_elements", {})
                codes = a.get("visual_evidence_codes", [])
                desc = a.get("description", "")[:120]
                active = [k.replace("has_", "") for k, v in detected.items() if v]
                img_summary_parts.append(
                    f"  Pic{idx+1}: 证据代码={codes} | 检测={active or '无'} | 描述={desc}"
                )
        img_summary = "\n".join(img_summary_parts) if img_summary_parts else "无图片分析"

        system_prompt = """你是一个社交媒体内容审核专家，专门识别隐性广告（软广/暗广）。

你的任务是根据帖子的文本内容和图片分析结果，给出标注建议。

## 标签定义
- mingguang（明广）：帖子明确标识了商业关系（如"广告""合作""赞助"标签），或内容明显是商业推广
- anguang（暗广）：帖子存在商业推广意图但未明确标识，例如：
  - 看似个人分享但实际推荐特定品牌/产品
  - 文案中包含促销话术、购买引导
  - 图片中有产品特写、Logo、价格等商业元素
  - 与博主既往人设/主题不符的商业内容
- feiguang（非广）：正常的个人分享、知识科普、新闻资讯等，无商业推广意图
- out_of_scope（范围外）：无法判断、非中文内容、纯转发无观点等

## 证据代码
- D: 明示商业关系（广告/赞助/合作标识）
- C: 明确商业对象（单一品牌/商品/店铺/服务）
- P: 劝服/促销话术（夸赞、限时、价格刺激）
- A: 转化动作（下单、扫码、优惠码、链接）
- V: 视觉商业证据（产品特写、Logo、价格表）
- B: 行为偏移（与博主既往人设/主题不符）
- M: 评论异常（置顶导流、格式化赞美）

## 输出格式（严格 JSON，不要 markdown 包裹）
{
  "suggested_label": "anguang",
  "suggested_evidence_codes": ["V", "P"],
  "suggested_evidence": [
    "图片1中出现了品牌Logo特写",
    "文案中包含'限时优惠'等促销话术"
  ],
  "suggested_confidence": 0.75,
  "reasoning": "虽然帖子以个人分享口吻撰写，但图片中的产品特写和文案中的价格暗示表明存在商业推广意图，建议标注为暗广。"
}"""

        user_prompt = f"""请分析以下帖子并给出标注建议。

## 帖子信息
- 标题: {title}
- 博主: {blogger}
- 平台: {platform}

## 帖子文本
{text}

## 图片分析结果
{img_summary}

请输出 JSON 格式的标注建议。"""

        response = client.chat.completions.create(
            model=model or _LLM_CONFIG["text_model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
            temperature=0.0,
            timeout=60,
        )

        raw = response.choices[0].message.content or ""
        # 解析 JSON
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines)

        # 查找 JSON 对象
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            suggestion = json.loads(match.group())
        else:
            suggestion = json.loads(raw)

        if callback:
            callback(suggestion)

    except Exception as e:
        if callback:
            callback({"__error__": str(e)[:200]})

class AnnotatorApp:
    def __init__(self, posts, output_dir, media_base, aid="D", completed=None,
                 llm_image_model=None, llm_image_backend=None, llm_text_model=None,
                 api_base_url=None, api_key=None,
                 auto_threshold=DEFAULT_AUTO_THRESHOLD,
                 ollama_model=OLLAMA_DEFAULT_MODEL,
                 ollama_url=OLLAMA_DEFAULT_URL,
                 ollama_backend=False,
                 ollama_timeout=OLLAMA_TIMEOUT):
        self.posts = posts
        self.output_dir = output_dir
        self.media_base = media_base
        self.aid = aid
        self.completed = completed or set()
        self.idx = 0
        self.image_analyses = {}
        self.analyzing = False
        self.suggesting = False  # LLM 协驾建议进行中
        self.page = None

        # ── 分置信度自动判断状态（co-pilot-auto-judge-design）──
        # 模式: "auto"=自动保存 | "suggest"=仅建议 | "manual"=纯人工
        self.auto_mode = "auto"
        self.auto_threshold = float(auto_threshold or DEFAULT_AUTO_THRESHOLD)
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.ollama_backend = bool(ollama_backend)
        self.ollama_timeout = ollama_timeout
        self.auto_count = 0      # 自动保存计数
        self.manual_count = 0    # 人工标注计数（本次会话）

        # ── LLM 配置 ──
        if llm_image_model: _LLM_CONFIG["image_model"] = llm_image_model
        if llm_image_backend: _LLM_CONFIG["image_backend"] = llm_image_backend
        if llm_text_model: _LLM_CONFIG["text_model"] = llm_text_model
        if api_base_url: _LLM_CONFIG["image_base_url"] = _LLM_CONFIG["text_base_url"] = api_base_url
        if api_key: _LLM_CONFIG["image_api_key"] = _LLM_CONFIG["text_api_key"] = api_key

        # ── 分析模式: "yolo" | "llm" ──
        self.analysis_mode = "yolo"
        # ── LLM 协驾建议缓存 ──
        self.copilot_suggestion = None

        for i, p in enumerate(posts):
            if p.get("post_id") not in self.completed:
                self.idx = i; break

    @property
    def post(self): return self.posts[self.idx] if self.posts else {}
    @property
    def pid(self): return self.post.get("post_id", "?")

    # ---- UI Build ----
    def build(self, page: ft.Page):
        self.page = page
        page.title = "隐性广告标注工作台"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window_width = 1400
        page.window_height = 900
        page.padding = 10

        # Top bar
        self.progress_text = ft.Text("", size=14)

        # 分析模式切换
        self.analysis_mode_dd = ft.Dropdown(
            value="yolo",
            options=[
                ft.dropdown.Option("yolo", "YOLO+OCR"),
                ft.dropdown.Option("llm", f"LLM ({_LLM_CONFIG['image_model']})"),
            ],
            width=180, dense=True,
        )
        self.analysis_mode_dd.on_change = self._on_analysis_mode_change
        self.analyze_btn = ft.Button("分析图片", icon=ft.Icons.IMAGE_SEARCH, on_click=self.run_analysis)
        self.copilot_btn = ft.Button("AI 建议标注", icon=ft.Icons.AUTO_AWESOME, on_click=self.run_copilot_suggestion)
        self.save_btn = ft.Button("保存标注", icon=ft.Icons.SAVE, on_click=self.save_current)

        # ── 分置信度自动判断 UI（设计文档 §3/§6.1）──
        self.auto_mode_dd = ft.Dropdown(
            value=self.auto_mode,
            options=[
                ft.dropdown.Option("auto", "🟢 自动"),
                ft.dropdown.Option("suggest", "🟡 建议"),
                ft.dropdown.Option("manual", "🔴 纯人工"),
            ],
            width=120, dense=True,
            tooltip="自动模式：高置信度自动保存 / 建议模式：仅展示建议 / 纯人工：不展示建议",
        )
        self.auto_mode_dd.on_change = self._on_auto_mode_change
        self.threshold_slider = ft.Slider(
            min=0.70, max=0.95, value=self.auto_threshold,
            divisions=25, label="{value}", width=180,
        )
        self.threshold_slider.on_change = self._on_threshold_change
        self.threshold_text = ft.Text(f"{self.auto_threshold:.2f}", size=12, color=ft.Colors.GREY_700)

        top_bar = ft.Row([
            ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Previous (Ctrl+Left)", on_click=lambda e: self.go(-1)),
            ft.IconButton(ft.Icons.ARROW_FORWARD, tooltip="Next (Ctrl+Right)", on_click=lambda e: self.go(1)),
            self.progress_text,
            ft.Container(expand=True),
            self.auto_mode_dd, ft.Text("阈值:", size=12), self.threshold_slider, self.threshold_text,
            ft.VerticalDivider(width=12),
            ft.Text("分析引擎:", size=12), self.analysis_mode_dd,
            self.analyze_btn, self.copilot_btn, self.save_btn,
        ], spacing=6)

        # Left: text + comments
        self.title_text = ft.Text("", size=20, weight=ft.FontWeight.BOLD)
        self.meta_text = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.post_type_badge = ft.Text("", size=12, weight=ft.FontWeight.BOLD)
        self.body_md = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.NONE)
        # ── 评论区（可折叠）──
        self.comments_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self.comments_list = ft.Column([], scroll=ft.ScrollMode.AUTO)
        self.comments_container = ft.Column([
            ft.Divider(),
            self.comments_header,
            self.comments_list,
        ], visible=False)
        left_col = ft.Column([
            self.title_text, self.meta_text, self.post_type_badge, ft.Divider(),
            self.body_md,
            self.comments_container,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        # Right: images
        self.gallery = ft.GridView(expand=True, max_extent=250, child_aspect_ratio=1.0, spacing=8, run_spacing=8)
        self.img_info = ft.Text("", size=12, color=ft.Colors.GREY_600)
        self.analysis_text = ft.Text("", size=12)
        # LLM 协驾建议展示
        self.suggestion_title = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self.suggestion_text = ft.Text("", size=12)
        self.accept_suggestion_btn = ft.Button(
            "✅ 采纳建议", icon=ft.Icons.CHECK_CIRCLE,
            on_click=self.accept_suggestion, visible=False)
        right_col = ft.Column([
            ft.Text("媒体 (图片/视频)", size=16, weight=ft.FontWeight.BOLD),
            self.img_info, self.gallery,
            ft.Divider(),
            ft.Text("图像分析结果", size=14, weight=ft.FontWeight.BOLD),
            self.analysis_text,
            ft.Divider(),
            ft.Row([ft.Text("🤖 AI 协驾建议", size=14, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True), self.accept_suggestion_btn]),
            self.suggestion_title,
            self.suggestion_text,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        # Bottom: annotation panel
        self.label_btns = ft.Row([
            ft.Button(n, on_click=lambda e, l=k: self.select_label(l))
            for k, n in LABEL_NAMES.items()
        ], spacing=8)
        self.selected_label = ft.Text("未选择", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE)

        self.evidence_cbs = {}
        ev_row = ft.Row([ft.Text("证据:", size=14)], spacing=4)
        for code, desc in EVIDENCE_CODES.items():
            cb = ft.Checkbox(label=code, tooltip=desc, value=False)
            self.evidence_cbs[code] = cb
            ev_row.controls.append(cb)

        self.conf_slider = ft.Slider(min=0, max=1, value=0.8, divisions=10, label="{value}", width=200)
        self.conf_text = ft.Text("0.8", size=14)
        self.evidence_input = ft.TextField(label="证据描述（一行一条）", multiline=True, min_lines=2, max_lines=4, expand=True)
        self.notes_input = ft.TextField(label="备注 (Markdown)", multiline=True, min_lines=2, max_lines=6, expand=True)

        annotation_panel = ft.Column([
            ft.Divider(),
            ft.Row([ft.Text("标签:", size=14), self.selected_label, ft.Container(expand=True)]),
            self.label_btns, ev_row,
            ft.Row([ft.Text("确信度:", size=14), self.conf_slider, self.conf_text, ft.Container(expand=True)]),
            self.evidence_input, self.notes_input,
        ])

        main_row = ft.Row([
            ft.Container(left_col, expand=2, padding=10),
            ft.VerticalDivider(),
            ft.Container(right_col, expand=3, padding=10),
        ], expand=True)

        # ── 底部状态栏（设计文档 §5.3）──
        self.status_bar = ft.Text("", size=12, color=ft.Colors.GREY_700)

        page.add(top_bar, ft.Divider(), main_row, annotation_panel, ft.Divider(), self.status_bar)
        page.on_keyboard_event = self._on_keyboard
        self._refresh()

    # ---- Refresh ----
    def _refresh(self):
        if not self.posts: return
        p = self.post
        pid = p.get("post_id", "?")
        self.progress_text.value = f"  [{self.idx + 1}/{len(self.posts)}]  {pid[:20]}..."
        if pid in self.completed: self.progress_text.value += "  DONE"
        self.title_text.value = p.get("title") or "(no title)"
        plat = p.get("platform", "?")
        blogger = (p.get("blogger_id") or "?")[:20]
        pub = p.get("published_at") or "unknown"
        mn = len(p.get("media", []))
        # 媒体类型统计
        media_types = set(m.get("type", "image") for m in p.get("media", []))
        type_labels = []
        if "video" in media_types: type_labels.append("🎬视频")
        if "image" in media_types: type_labels.append("🖼图片")
        self.meta_text.value = f"Platform: {plat} | Blogger: {blogger}... | Published: {pub} | Media: {mn}{' (' + ','.join(type_labels) + ')' if type_labels else ''}"
        self.post_type_badge.value = f"类型: {' | '.join(type_labels)}" if type_labels else ""

        # ── 文本清洗与渲染 ──
        text = p.get("text", "")
        is_garbage = self._is_garbage_text(text)
        if is_garbage:
            self.post_type_badge.value = (self.post_type_badge.value + " | ⚠️抓取失败(页面源码)").strip(" |")
            text = f"> ⚠️ **该帖子抓取失败**：爬虫未获取到正文内容，捕获了页面源码。\n> 请点击右侧视频卡片在浏览器中查看原文。\n> 来源: {p.get('_collected',{}).get('source_url','')}\n\n---\n\n<details><summary>原始抓取内容 (点击展开)</summary>\n\n```\n{text[:2000]}\n```\n\n</details>"
        elif plat == "bilibili":
            text, meta_info = self._clean_bilibili_text(text)
            if meta_info:
                text = meta_info + "\n\n---\n\n" + text
        if len(text) > 8000:
            text = text[:8000] + "\n\n*...(truncated)*"
        text = re.sub(r'<图片(\d+)>', r' [Pic\1](marker:\1) ', text)
        self.body_md.value = text

        self._refresh_images()
        self._refresh_comments()
        self.selected_label.value = "未选择"
        self.selected_label.color = ft.Colors.ORANGE
        for cb in self.evidence_cbs.values(): cb.value = False
        self.conf_slider.value = 0.8; self.conf_text.value = "0.8"
        self.evidence_input.value = ""; self.notes_input.value = ""
        self.image_analyses = {}
        self.copilot_suggestion = None
        mode_label = "LLM" if self.analysis_mode == "llm" else "YOLO+OCR"
        self.analysis_text.value = f"点击 '分析图片' ({mode_label}) 开始"
        self.suggestion_title.value = ""
        self.suggestion_text.value = ""
        self.accept_suggestion_btn.visible = False
        self.page.update()

    @staticmethod
    def _is_garbage_text(text: str) -> bool:
        """检测文本是否为抓取失败的页面源码/登录墙/乱码。"""
        if not text or len(text.strip()) < 10:
            return True  # 空或极短文本视为无效

        # ── 编码乱码特征（常见 mojibake）──
        mojibake = ["锟斤拷", "烫烫烫", "屯屯屯", "\ufffd", "�"]
        if any(m in text for m in mojibake):
            return True

        # ── 页面源码 / JS 特征 ──
        js_html_markers = [
            "window.__MIRROR_CONFIG__", "window.reportConfig",
            "window.reportMsgObj", "vue-ssr-outlet",
            "<!DOCTYPE html", "<html", "</script>", "</div>",
            "function(", "=> {", "const ", "export default",
        ]
        js_hits = sum(1 for m in js_html_markers if m in text)

        # ── 登录墙 / 验证页特征 ──
        login_markers = [
            "扫描二维码登录", "请使用\n哔哩哔哩客户端",
            "立即登录", "忘记密码", "首次使用",
            "点我注册", "短信登录", "密码登录",
            "扫码登录", "验证码", "滑块验证",
        ]
        login_hits = sum(1 for m in login_markers if m in text)

        # 判定：JS+登录标记 ≥2 或 单类 ≥3
        if js_hits + login_hits >= 2:
            return True
        if js_hits >= 3 or login_hits >= 3:
            return True

        # ── 全是非正文内容（只有 URL 和数字）──
        stripped = re.sub(r'https?://\S+', '', text)
        stripped = re.sub(r'[\d,.\s]+', '', stripped)
        if len(stripped) < 20 and len(text) > 200:
            return True

        return False

    @staticmethod
    def _clean_bilibili_text(text: str) -> Tuple[str, str]:
        """清洗B站文本：分离视频描述与统计元数据。

        Returns: (description, metadata_summary)
        """
        if not text:
            return text, ""
        # B站文本格式: "描述..., 视频播放量 N、弹幕量 N、..., 视频作者 XXX, 作者简介 ..., 相关视频：..."
        # 匹配"视频播放量"作为元数据起始标记
        meta_start = re.search(r',\s*视频播放量\s+\d+', text)
        if not meta_start:
            return text, ""

        desc = text[:meta_start.start()].strip().rstrip(",")
        meta = text[meta_start.start():].lstrip(",").strip()

        # 整理元数据摘要
        parts = []
        stats_match = re.search(
            r'视频播放量\s+(\d+)、弹幕量\s+(\d+)、点赞数\s+(\d+)、投硬币枚数\s+(\d+)、收藏人数\s+(\d+)、转发人数\s+(\d+)',
            meta)
        if stats_match:
            parts.append(f"📊 播放:{stats_match.group(1)} | 弹幕:{stats_match.group(2)} | 点赞:{stats_match.group(3)} | 收藏:{stats_match.group(5)}")

        author_match = re.search(r'视频作者\s+(\S+)', meta)
        if author_match:
            parts.append(f"👤 作者: {author_match.group(1)}")

        # 相关视频最多显示 5 个
        related_match = re.search(r'相关视频：(.+)', meta)
        if related_match:
            related = [r.strip().rstrip("，。") for r in related_match.group(1).split("，") if r.strip()]
            if related:
                parts.append(f"📺 相关视频 ({len(related)}): " + " | ".join(related[:5]))
                if len(related) > 5:
                    parts[-1] += f" ...等{len(related)}个"

        return desc, "\n".join(parts) if parts else meta[:300]

    def _refresh_comments(self):
        """刷新评论列表。"""
        self.comments_list.controls.clear()
        comments = self.post.get("comments", [])
        if not comments:
            self.comments_container.visible = False
            return

        self.comments_container.visible = True
        self.comments_header.value = f"💬 评论 ({len(comments)})"

        for c in comments[:30]:  # 最多展示 30 条
            author = (c.get("author_id") or "匿名")[:14]
            text = c.get("text", "")
            likes = c.get("like_count", 0)
            pinned = "📌 " if c.get("is_pinned") else ""
            # 截断过长评论
            if len(text) > 200:
                text = text[:200] + "..."

            # 评论气泡样式
            comment_card = ft.Container(
                ft.Column([
                    ft.Row([
                        ft.Text(f"{pinned}{author}", size=11, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_700),
                        ft.Container(expand=True),
                        ft.Text(f"👍 {likes}", size=10, color=ft.Colors.GREY_500),
                    ], spacing=4),
                    ft.Text(text, size=12),
                ], spacing=2),
                padding=8,
                border=_border_all(1, ft.Colors.GREY_200),
                border_radius=6,
                margin=4,
            )
            self.comments_list.controls.append(comment_card)

    def _refresh_images(self):
        self.gallery.controls.clear()
        text = self.post.get("text", "")
        platform = self.post.get("platform", "")
        ci = set()
        if text:
            for m in re.finditer(r'<图片(\d+)>', text): ci.add(int(m.group(1)) - 1)
        media = self.post.get("media", [])
        shown = 0
        videos = 0
        errors = []
        for i, m in enumerate(media):
            if ci and i not in ci: continue
            ref = m.get("ref") or ""
            media_type = m.get("type", "image")
            source_url = m.get("source_url", "")
            num = i + 1

            # ── 视频媒体：显示播放卡片 ──
            if media_type == "video" and source_url:
                card = self._build_video_card(num, source_url, platform, i)
                self.gallery.controls.append(card)
                shown += 1; videos += 1
                continue

            # ── 图片媒体（原有逻辑）──
            ip = self.media_base / ref if ref else None
            if ip and ip.exists():
                try:
                    ext = ip.suffix.lower().lstrip(".")
                    mime_map = {"jpg":"jpeg","jpeg":"jpeg","png":"png","gif":"gif","webp":"webp","bmp":"bmp"}
                    mime = mime_map.get(ext, "jpeg")
                    b64 = base64.b64encode(ip.read_bytes()).decode()
                    img = ft.Image(src=f"data:image/{mime};base64,{b64}", tooltip=f"Pic{num}")
                    img.fit = ft.BoxFit.CONTAIN
                    img.border_radius = 8
                except Exception as exc:
                    errors.append(f"Pic{num}: {exc}")
                    img = ft.Container(
                        ft.Text(f"Pic{num}\n读取失败\n{str(exc)[:50]}", size=11, text_align=ft.TextAlign.CENTER),
                        width=200, height=200,
                        border=_border_all(1, ft.Colors.RED_300), border_radius=8,
                        alignment=ft.alignment.Alignment(0, 0))
            else:
                # 无本地文件：可能是图片 ref 为空或文件缺失
                if ref:
                    errors.append(f"Pic{num}: 文件缺失 ({ref[:40]})")
                msg = "文件缺失" if ref else "无媒体文件"
                img = ft.Container(
                    ft.Text(f"Pic{num}\n{msg}", size=12, text_align=ft.TextAlign.CENTER),
                    width=200, height=200,
                    border=_border_all(1, ft.Colors.GREY_300), border_radius=8,
                    alignment=ft.alignment.Alignment(0, 0))
            analysis = self.image_analyses.get(i, {})
            badge_parts = []
            if analysis.get("visual_evidence_codes"):
                badge_parts.append(",".join(analysis["visual_evidence_codes"]))
            if analysis.get("analysis_method", "").startswith("multimodal"):
                badge_parts.append("🤖")
            badge = f" [{','.join(badge_parts)}]" if badge_parts else ""
            cap = ft.Text(f"Pic{num}{badge}", size=11)
            self.gallery.controls.append(ft.Container(ft.Column([img, cap], spacing=4, alignment=ft.MainAxisAlignment.CENTER)))
            shown += 1

        status = f"Showing {shown}/{len(media)} media"
        if videos > 0:
            status += f"  |  🎬 {videos} videos"
        if errors:
            status += f"  |  Errors: {'; '.join(errors[:3])}"
        self.img_info.value = status

    # ---- 视频卡片构建 ----
    def _build_video_card(self, num: int, source_url: str, platform: str, media_index: int):
        """为视频媒体构建占位卡片 + 浏览器播放按钮。"""
        # 平台图标/颜色
        platform_colors = {
            "bilibili": (ft.Colors.PINK_300, "B站"),
            "xiaohongshu": (ft.Colors.RED_300, "小红书"),
            "wechat": (ft.Colors.GREEN_300, "微信"),
            "douyin": (ft.Colors.BLACK, "抖音"),
        }
        plat_color, plat_label = platform_colors.get(platform, (ft.Colors.BLUE_300, platform or "视频"))

        # 缩短 URL 显示
        short_url = source_url
        if len(short_url) > 45:
            short_url = short_url[:42] + "..."

        analysis = self.image_analyses.get(media_index, {})
        badge_parts = []
        if analysis.get("visual_evidence_codes"):
            badge_parts.append(",".join(analysis["visual_evidence_codes"]))
        badge = f" [{','.join(badge_parts)}]" if badge_parts else ""

        card_content = ft.Column([
            ft.Container(
                ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, size=48, color=plat_color),
                alignment=ft.alignment.Alignment(0, 0),
                width=200, height=120,
                border=_border_all(2, plat_color), border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.05, plat_color),
            ),
            ft.Text(f"🎬 {plat_label}视频{num}{badge}", size=12, weight=ft.FontWeight.BOLD),
            ft.Text(short_url, size=10, color=ft.Colors.GREY_500),
            ft.Button(
                "在浏览器中播放",
                icon=ft.Icons.OPEN_IN_BROWSER,
                on_click=lambda e, url=source_url: self._open_video(url),
                height=32,
            ),
        ], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Container(card_content, width=220)

    def _open_video(self, url: str):
        """在系统默认浏览器中打开视频 URL。"""
        try:
            webbrowser.open(url)
            self._snack(f"已在浏览器中打开: {url[:60]}...", ft.Colors.BLUE)
        except Exception as e:
            self._snack(f"打开浏览器失败: {e}", ft.Colors.RED)

    # ---- Actions ----
    def _on_analysis_mode_change(self, e=None):
        self.analysis_mode = self.analysis_mode_dd.value or "yolo"

    def _on_auto_mode_change(self, e=None):
        """自动模式切换：🟢自动 / 🟡建议 / 🔴纯人工。"""
        self.auto_mode = self.auto_mode_dd.value or "auto"
        self._update_status_bar()
        self.page.update()

    def _on_threshold_change(self, e=None):
        """置信度阈值滑块变化。"""
        try:
            self.auto_threshold = float(self.threshold_slider.value)
        except (TypeError, ValueError):
            self.auto_threshold = DEFAULT_AUTO_THRESHOLD
        self.threshold_text.value = f"{self.auto_threshold:.2f}"
        self._update_status_bar()
        self.page.update()

    def _update_status_bar(self):
        """刷新底部状态栏：自动标注 / 人工标注 / 待标注 计数。"""
        mode_label = {"auto": "🟢 自动", "suggest": "🟡 建议", "manual": "🔴 纯人工"}.get(self.auto_mode, "?")
        pending = len(self.posts) - len(self.completed) - self.auto_count
        if pending < 0:
            pending = 0
        if self.status_bar:
            self.status_bar.value = (
                f"模式: {mode_label} | 阈值: {self.auto_threshold:.2f} | "
                f"自动标注: {self.auto_count} | 人工标注: {self.manual_count} | "
                f"待标注: {pending}"
            )

    def auto_save_if_confident(self, suggestion: Dict, auto: bool = True) -> bool:
        """检查置信度，达到阈值时自动保存标注并跳转（设计文档 §5.3）。

        Args:
            suggestion: LLM 判定结果（含 label/confidence/evidence_codes 等）
            auto: 是否属于自动采纳（区别于手动点击采纳）

        Returns:
            True=已自动保存并跳转；False=未触发自动保存
        """
        if self.auto_mode != "auto":
            return False
        conf = suggestion.get("suggested_confidence", suggestion.get("confidence", 0))
        if conf < self.auto_threshold:
            return False

        # 构造自动保存记录（annotation_method="auto_accepted"，不参与 κ）
        record = build_auto_record(
            self.post,
            suggestion,
            model=self.ollama_model,
            auto_accepted=auto,
        )
        record["annotator_id"] = "system" if auto else self.aid
        record["markdown_notes"] = f"[自动标注] {suggestion.get('reasoning', '')}"
        save_annotation(self.output_dir, record["annotator_id"], record)
        self.completed.add(self.pid)
        self.auto_count += 1
        self._update_status_bar()

        label_cn = suggestion.get("label", suggestion.get("suggested_label", "?"))
        self._snack(f"✅ 已自动标注为「{label_cn}」(置信度 {conf:.0%})", ft.Colors.GREEN)
        self.page.update()
        self.go(1)
        return True

    def run_analysis(self, e=None):
        if self.analyzing: return

        # 检查是否有可分析的媒体
        media = self.post.get("media", [])
        has_images = any(m.get("type", "image") == "image" and m.get("ref") for m in media)
        has_videos = any(m.get("type") == "video" for m in media)
        if not has_images:
            if has_videos:
                self.analysis_text.value = "⚠️ 该帖子仅有视频媒体，请点击视频卡片在浏览器中查看"
            else:
                self.analysis_text.value = "⚠️ 无可分析的图片媒体"
            self.page.update()
            return

        self.analyzing = True; self.analyze_btn.disabled = True
        mode_label = "LLM" if self.analysis_mode == "llm" else "YOLO+OCR"
        self.analysis_text.value = f"分析中... ({mode_label})"; self.page.update()

        if self.analysis_mode == "llm":
            self._run_llm_analysis()
        else:
            self._run_yolo_analysis()

    def _run_yolo_analysis(self):
        def cb(results):
            self.analyzing = False; self.analyze_btn.disabled = False
            if "__error__" in results:
                self.analysis_text.value = f"Error: {results['__error__']}"
            else:
                self.image_analyses = results
                self._display_analysis_results(results)
            self._refresh_images(); self.page.update()
        threading.Thread(target=run_image_analysis_bg, args=(self.post, self.media_base, cb), daemon=True).start()

    def _run_llm_analysis(self):
        def cb(results):
            self.analyzing = False; self.analyze_btn.disabled = False
            if "__error__" in results:
                self.analysis_text.value = f"Error: {results['__error__']}"
            else:
                self.image_analyses = results
                self._display_analysis_results(results)
            self._refresh_images(); self.page.update()
        threading.Thread(target=run_llm_image_analysis_bg,
                         args=(self.post, self.media_base, cb), daemon=True).start()

    def _display_analysis_results(self, results: Dict):
        """统一显示图片分析结果（YOLO/LLM 通用）。"""
        lines = []
        for idx, a in sorted(results.items()):
            if "error" in a:
                lines.append(f"Pic{idx+1}: err {a['error']}")
            else:
                el = a.get("detected_elements", {})
                codes = a.get("visual_evidence_codes", [])
                desc = a.get("description", "")
                active = [k.replace("has_", "") for k, v in el.items() if v]
                method = a.get("analysis_method", "yolo")
                tag = "🤖" if method.startswith("multimodal") else "🔍"
                lines.append(f"{tag} Pic{idx+1}: {codes if codes else '-'} {', '.join(active) if active else '无商业特征'}")
                if desc and method.startswith("multimodal"):
                    lines.append(f"    {desc[:120]}")
                if a.get("ocr_text"):
                    lines.append(f"    OCR: {a['ocr_text'][:80]}")
                if a.get("commercial_intent_score") is not None:
                    lines.append(f"    商业意图: {a['commercial_intent_score']:.0%}")
        self.analysis_text.value = "\n".join(lines) if lines else "无内容图片"

    # ---- LLM 协驾建议 ----
    def run_copilot_suggestion(self, e=None):
        """触发 LLM 协驾建议生成（支持 Ollama 后端 + 分置信度自动判断）。"""
        if self.suggesting: return
        self.suggesting = True; self.copilot_btn.disabled = True
        self.suggestion_title.value = "🤔 正在分析..."
        self.suggestion_text.value = "LLM 正在阅读帖子和图片分析结果，生成标注建议..."
        self.accept_suggestion_btn.visible = False
        self.page.update()

        backend = "ollama" if self.ollama_backend else "openai"

        def cb(result):
            self.suggesting = False; self.copilot_btn.disabled = False
            if "__error__" in result:
                self.suggestion_title.value = "❌ 建议生成失败"
                self.suggestion_text.value = f"错误: {result['__error__']}"
                self.copilot_suggestion = None
                self.accept_suggestion_btn.visible = False
            else:
                self.copilot_suggestion = result
                conf = result.get("suggested_confidence", result.get("confidence", 0))
                tier = classify_confidence(conf, self.auto_threshold)

                # 🟢 高置信度 → 自动保存并跳转（auto_save_if_confident 内部处理）
                if self.auto_save_if_confident(result):
                    self.suggestion_title.value = ""
                    self.suggestion_text.value = ""
                    self.accept_suggestion_btn.visible = False
                    self.page.update()
                    return

                label_cn = LABEL_NAMES.get(result.get("suggested_label", ""),
                                           result.get("suggested_label", "?"))
                self.suggestion_title.value = f"📋 建议标签: {label_cn}  (确信度: {conf:.0%})"

                if tier == "manual":
                    # 🔴 低置信度：不展示建议细节（防锚定效应）
                    self.suggestion_text.value = (
                        "⚠️ 此帖置信度低于人工判断下限，建议完全由人工独立判断，不展示模型建议。"
                    )
                    self.accept_suggestion_btn.visible = False
                else:
                    # 🟡 中置信度：展示建议，等待人工确认
                    lines = [f"**理由**: {result.get('reasoning', '')}"]
                    codes = result.get("suggested_evidence_codes", [])
                    if codes:
                        code_desc = ", ".join(f"{c}({EVIDENCE_CODES.get(c, '?')})" for c in codes)
                        lines.append(f"**建议证据代码**: {code_desc}")
                    evidence = result.get("suggested_evidence", [])
                    if evidence:
                        lines.append(f"**建议证据描述**:")
                        for ev in evidence:
                            lines.append(f"  • {ev}")
                    self.suggestion_text.value = "\n".join(lines)
                    self.accept_suggestion_btn.visible = True
            self.page.update()
        threading.Thread(target=run_llm_copilot_suggestion_bg,
                         args=(self.post, self.image_analyses, cb,
                               _LLM_CONFIG["text_model"], None, None, backend,
                               self.ollama_url, self.ollama_timeout),
                         daemon=True).start()

    def accept_suggestion(self, e=None, auto=False):
        """采纳 LLM 协驾建议，自动填充标注表单。

        Args:
            auto: True=自动采纳（填充后立即保存并跳转，annotation_method=auto_accepted）；
                  False=手动采纳（填充表单等待人工检查后保存）
        """
        if not self.copilot_suggestion:
            self._snack("没有可用的建议", ft.Colors.ORANGE); return
        s = self.copilot_suggestion

        # 设置标签
        label = s.get("suggested_label", "")
        if label in VALID_LABELS:
            self.select_label(label)

        # 设置证据代码
        codes = s.get("suggested_evidence_codes", [])
        for c, cb in self.evidence_cbs.items():
            cb.value = c in codes

        # 设置确信度
        conf = s.get("suggested_confidence", 0.8)
        conf = max(0.0, min(1.0, conf))
        self.conf_slider.value = conf
        self.conf_text.value = f"{conf:.1f}"

        # 设置证据描述
        evidence = s.get("suggested_evidence", [])
        self.evidence_input.value = "\n".join(evidence)

        # 设置备注
        reasoning = s.get("reasoning", "")
        if reasoning:
            self.notes_input.value = f"[AI 建议理由] {reasoning}"

        self.accept_suggestion_btn.visible = False
        if auto:
            # 自动采纳：直接保存并跳转
            self.save_current(auto=True)
        else:
            self._snack("已采纳 AI 建议，请检查后保存", ft.Colors.GREEN)
        self.page.update()

    def select_label(self, label: str):
        self.selected_label.value = LABEL_NAMES.get(label, label)
        color_map = {"mingguang": ft.Colors.RED, "anguang": ft.Colors.ORANGE, "feiguang": ft.Colors.GREEN, "out_of_scope": ft.Colors.GREY}
        self.selected_label.color = color_map.get(label, ft.Colors.ORANGE)
        self.page.update()

    def save_current(self, e=None, auto=False):
        label = self.selected_label.value
        for k, v in LABEL_NAMES.items():
            if label == v: label = k; break
        if label not in VALID_LABELS:
            self._snack("请先选择标签", ft.Colors.RED); return

        # 构建 image_analyses 条目
        image_analysis_entries = []
        for i, a in self.image_analyses.items():
            if "error" in a:
                continue
            media_list = self.post.get("media", [])
            if i < len(media_list):
                ref = media_list[i].get("ref", "")
            else:
                ref = ""
            entry = {
                "media_ref": ref,
                "image_index": i + 1,
                "analysis_method": a.get("analysis_method", "yolo_ocr_auto"),
                "description": a.get("description", ""),
                "ocr_text": a.get("ocr_text"),
                "detected_elements": a.get("detected_elements", {}),
                "visual_evidence_codes": a.get("visual_evidence_codes", []),
            }
            if a.get("analysis_method", "").startswith("multimodal"):
                entry["relevance_to_annotation"] = a.get("relevance_to_annotation", "")
                entry["image_quality_notes"] = a.get("image_quality_notes", "")
                entry["commercial_intent_score"] = a.get("commercial_intent_score", 0.0)
            image_analysis_entries.append(entry)

        record = {
            "post_id": self.pid, "annotator_id": "system" if auto else self.aid, "guide_version": "1.1",
            "label": label, "confidence": round(self.conf_slider.value, 2),
            "evidence_codes": [c for c, cb in self.evidence_cbs.items() if cb.value],
            "evidence": [e.strip() for e in self.evidence_input.value.split("\n") if e.strip()] if self.evidence_input.value else [],
            "uncertain_reason": None,
            "annotated_at": datetime.now(CST).isoformat(),
            # 标注方式标记（"auto_accepted"=自动保存，不参与 κ；"human"=人工标注）
            "annotation_method": "auto_accepted" if auto else "human",
            "markdown_notes": self.notes_input.value,
            "image_analyses": image_analysis_entries,
            # 如果有 AI 协驾建议，也记录下来
            "ai_copilot_suggestion": {
                "suggested_label": self.copilot_suggestion.get("suggested_label", ""),
                "suggested_evidence_codes": self.copilot_suggestion.get("suggested_evidence_codes", []),
                "suggested_confidence": self.copilot_suggestion.get("suggested_confidence", 0),
                "reasoning": self.copilot_suggestion.get("reasoning", ""),
            } if self.copilot_suggestion else None,
        }
        # 自动保存时附加完整 _llm_suggestion（设计文档 §5.1）
        if auto and self.copilot_suggestion:
            record["_llm_suggestion"] = {
                "label": self.copilot_suggestion.get("label",
                        self.copilot_suggestion.get("suggested_label", label)),
                "confidence": self.copilot_suggestion.get("confidence",
                        self.copilot_suggestion.get("suggested_confidence", 0)),
                "evidence_codes": self.copilot_suggestion.get("evidence_codes",
                        self.copilot_suggestion.get("suggested_evidence_codes", [])),
                "evidence": self.copilot_suggestion.get("evidence",
                        self.copilot_suggestion.get("suggested_evidence", [])),
                "reasoning": self.copilot_suggestion.get("reasoning", ""),
                "model": self.ollama_model,
                "auto_accepted": True,
            }
        save_annotation(self.output_dir, record["annotator_id"], record)
        self.completed.add(self.pid)
        if auto:
            self.auto_count += 1
        else:
            self.manual_count += 1
        self._update_status_bar()
        self._snack(f"✅ 已{'自动' if auto else ''}保存: {self.pid[:24]}...", ft.Colors.GREEN)
        self.go(1)

    def _snack(self, msg, color=ft.Colors.GREEN):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg, color=color), duration=2000)
        self.page.snack_bar.open = True; self.page.update()

    # ---- Navigation ----
    def go(self, delta):
        new_idx = self.idx + delta
        if 0 <= new_idx < len(self.posts):
            self.idx = new_idx; self._refresh()
        self._update_status_bar()
        if self.page:
            self.page.update()

    def _on_keyboard(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key == "Arrow Left": self.go(-1)
        elif e.ctrl and e.key == "Arrow Right": self.go(1)
        elif e.ctrl and e.key == "S": self.save_current()
        elif e.ctrl and e.key == "A": self.run_analysis()
        elif e.ctrl and e.key == "G": self.run_copilot_suggestion()  # Ctrl+G = AI 建议
        elif e.ctrl and e.key == "Y": self.accept_suggestion()        # Ctrl+Y = 采纳建议
        elif e.key in ("1","2","3","4"):
            idx = int(e.key) - 1
            if idx < len(VALID_LABELS): self.select_label(VALID_LABELS[idx])

def main():
    import argparse
    p = argparse.ArgumentParser(description="Flet Annotation Workbench")
    p.add_argument("--input", default="data/interim/candidates_v1_dedup.jsonl")
    p.add_argument("--output-dir", default="data/annotations")
    p.add_argument("--media-base", default="data")
    p.add_argument("--annotator-id", default="D")
    # LLM / 多模态配置
    p.add_argument("--llm-image-model", default=None,
                   help="多模态图片分析模型 (e.g. gpt-4o-mini, qwen-vl-max, glm-4v)")
    p.add_argument("--llm-image-backend", default=None, choices=["openai", "ollama"],
                   help="图片分析后端")
    p.add_argument("--llm-text-model", default=None,
                   help="纯文本 LLM 模型 (协驾建议用)")
    p.add_argument("--api-base-url", default=None,
                   help="OpenAI 兼容 API 端点 (同时用于图片和文本)")
    p.add_argument("--api-key", default=None,
                   help="API 密钥")
    p.add_argument("--skip-garbage", action="store_true",
                   help="自动跳过抓取失败的帖子（含页面源码/登录墙/乱码）")
    # ── 分置信度自动判断（co-pilot-auto-judge-design）──
    p.add_argument("--auto-threshold", type=float, default=None,
                   help=f"自动保存置信度阈值（默认 {DEFAULT_AUTO_THRESHOLD}，范围 0.70–0.95）")
    p.add_argument("--ollama-backend", action="store_true",
                   help="使用本地 Ollama 做 AI 协驾建议（代替 OpenAI 云端 LLM）")
    p.add_argument("--ollama-model", default=None,
                   help=f"Ollama 模型名（默认 {OLLAMA_DEFAULT_MODEL}）")
    p.add_argument("--ollama-url", default=None,
                   help=f"Ollama 服务地址（默认 {OLLAMA_DEFAULT_URL}）")
    p.add_argument("--ollama-timeout", type=float, default=OLLAMA_TIMEOUT,
                   help=f"Ollama 单条推理超时秒数（默认 {OLLAMA_TIMEOUT}）")
    args = p.parse_args()

    ip = PROJECT_ROOT / args.input; od = PROJECT_ROOT / args.output_dir; mb = PROJECT_ROOT / args.media_base
    print(f"Loading: {ip}")
    posts = load_posts(ip)
    print(f"  {len(posts)} posts loaded")

    # ── 过滤垃圾帖子 ──
    if args.skip_garbage:
        before = len(posts)
        posts = [p for p in posts if not AnnotatorApp._is_garbage_text(p.get("text", ""))]
        print(f"  跳过 {before - len(posts)} 条抓取失败的帖子，剩余 {len(posts)}")

    _, completed = load_existing(od, args.annotator_id)
    print(f"  {len(completed)} already completed")

    app = AnnotatorApp(posts, od, mb, args.annotator_id, completed,
                       llm_image_model=args.llm_image_model,
                       llm_image_backend=args.llm_image_backend,
                       llm_text_model=args.llm_text_model,
                       api_base_url=args.api_base_url,
                       api_key=args.api_key,
                       auto_threshold=args.auto_threshold,
                       ollama_model=args.ollama_model or OLLAMA_DEFAULT_MODEL,
                       ollama_url=args.ollama_url or OLLAMA_DEFAULT_URL,
                       ollama_backend=args.ollama_backend,
                       ollama_timeout=args.ollama_timeout)
    print(f"\nStarting workbench (desktop)...")
    print(f"  Shortcuts: Ctrl+Arrows=Navigate | Ctrl+S=Save | Ctrl+A=Analyze | Ctrl+G=AI建议 | Ctrl+Y=采纳 | 1-4=Quick label")
    print(f"  Analysis engines: YOLO+OCR / LLM ({_LLM_CONFIG['image_model']})")
    if args.ollama_backend:
        print(f"  AI 协驾: Ollama ({app.ollama_model}) | 自动阈值: {app.auto_threshold:.2f}")
    ft.app(target=app.build)  # legacy entry, ok for 0.86.x desktop

if __name__ == "__main__":
    main()
