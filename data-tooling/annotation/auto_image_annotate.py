#!/usr/bin/env python3
"""图像自动标注 —— YOLO11n + OCR / 多模态视觉模型 → image_analyses 字段。

功能：
  1. 加载帖子 JSONL，逐条遍历帖子的 media[] 图片
  2. 【预过滤】基于 <图片N> 标记 + 文件元数据 + OpenCV 跳过非内容图
  3. YOLO11n 目标检测：识别产品、Logo、二维码、人物、手机/屏幕等
  4. OCR 文字提取（EasyOCR / pytesseract 自动选择）
  5. 【多模态】可选：使用 GPT-4V / GLM-4V / Qwen-VL 替代 YOLO+OCR
  6. 根据检测结果自动推断 detected_elements 标志位与 visual_evidence_codes
  7. 产出符合 05-标注补充-图像与备注结构.md 的 image_analyses[] 记录

用法：
  # 默认：YOLO + OCR（自动跳过非内容图片）
  python scripts/data/annotation/auto_image_annotate.py \\
    --input data/interim/candidates_v1_dedup.jsonl \\
    --limit 10

  # 多模态模式（更准确的商业意图判断）
  python scripts/data/annotation/auto_image_annotate.py \\
    --input data/interim/candidates_v1_dedup.jsonl \\
    --use-multimodal --multimodal-model gpt-4o-mini \\
    --limit 10

  # 禁用预过滤（分析所有图片，包括装饰图）
  python scripts/data/annotation/auto_image_annotate.py \\
    --input data/interim/candidates_v1_dedup.jsonl \\
    --no-prefilter

  # 补充模式：为已有标注文件补充 image_analyses
  python scripts/data/annotation/auto_image_annotate.py \\
    --supplement data/annotations/D_20260721_143000.json \\
    --output data/annotations/D_supplemented.json

依赖：pip install ultralytics easyocr (或 pytesseract + Pillow)
模型：项目根目录 yolo11n.pt
多模态：需 OPENAI_API_KEY 或兼容端点（GLM-4V / Qwen-VL）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 项目根目录加入 sys.path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CST = timezone(timedelta(hours=8))

# ── YOLO 模型路径 ──
DEFAULT_MODEL = PROJECT_ROOT / "yolo11n.pt"

# ── COCO 类别 → 业务含义映射 ──
# YOLO11n 使用 COCO 80 类，我们关注与广告识别相关的类别
COCO_AD_MAP = {
    # COCO ID → (detected_elements 中的 key, 说明)
    0: ("has_person", "人物"),                    # person
    39: ("has_product_image", "瓶装商品"),         # bottle
    44: ("has_product_image", "瓶装商品"),         # bottle → 同上
    46: ("has_product_image", "水果/食品"),        # banana → 食品类
    47: ("has_product_image", "水果/食品"),        # apple
    48: ("has_product_image", "水果/食品"),        # sandwich
    49: ("has_product_image", "水果/食品"),        # orange
    50: ("has_product_image", "食品"),             # broccoli
    51: ("has_product_image", "食品"),             # carrot
    52: ("has_product_image", "食品"),             # hot dog
    53: ("has_product_image", "食品"),             # pizza
    54: ("has_product_image", "食品"),             # donut
    55: ("has_product_image", "食品"),             # cake
    62: ("has_product_image", "电子设备"),          # tv / monitor
    63: ("has_product_image", "电子设备"),          # laptop
    64: ("has_product_image", "电子设备"),          # mouse
    65: ("has_product_image", "电子设备"),          # remote
    66: ("has_product_image", "电子设备"),          # keyboard
    67: ("has_product_image", "电子设备"),          # cell phone
    72: ("has_product_image", "电子设备"),          # tv
    73: ("has_product_image", "电子设备"),          # laptop
    76: ("has_product_image", "电子设备"),          # keyboard
    77: ("has_product_image", "电子设备"),          # cell phone
    84: ("has_product_image", "书籍/出版物"),       # book
    # 以下 COCO 无直接对应，用于辅助判断
    1: ("has_person", "人物"),                     # bicycle → 可能有骑行装备广告
    2: ("has_product_image", "车辆"),               # car
    3: ("has_product_image", "车辆"),               # motorcycle
    5: ("has_product_image", "车辆"),               # bus
    7: ("has_product_image", "车辆"),               # truck
}

# 这些 COCO 类别强烈暗示商业/产品内容
PRODUCT_CLASSES = {39, 44, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
                   62, 63, 64, 65, 66, 67, 72, 73, 76, 77, 84, 2, 3, 5, 7}
PERSON_CLASSES = {0, 1}
SCREEN_CLASSES = {62, 63, 67, 72, 73, 77}  # 屏幕/手机 → 可能是二维码/价格截图


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL/JSON 文件，兼容缩进多行格式。"""
    raw_text = path.read_text(encoding="utf-8-sig")
    records: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    content_len = len(raw_text)
    while idx < content_len:
        while idx < content_len and raw_text[idx] in " \t\n\r":
            idx += 1
        if idx >= content_len:
            break
        try:
            obj, end = decoder.raw_decode(raw_text, idx)
            records.append(obj)
            idx = end
        except json.JSONDecodeError:
            next_brace = raw_text.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace
    return records


def load_yolo(model_path: Path = DEFAULT_MODEL):
    """加载 YOLO11n 模型（强制 CPU，避免 CUDA 兼容性问题）。"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics 未安装，请运行: pip install ultralytics")
        sys.exit(1)

    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        sys.exit(1)

    # 强制 CPU 模式，避免 CUDA no kernel image 错误
    import torch
    return YOLO(str(model_path)).to("cpu")


def load_ocr():
    """加载 OCR 引擎（优先 EasyOCR，回退 pytesseract）。"""
    # 尝试 EasyOCR
    try:
        import easyocr
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        return ("easyocr", reader)
    except ImportError:
        pass

    # 尝试 pytesseract
    try:
        import pytesseract
        from PIL import Image
        return ("tesseract", None)
    except ImportError:
        pass

    return (None, None)


def run_ocr(ocr_engine, image_path: Path) -> Optional[str]:
    """对单张图片执行 OCR，返回提取的文字。"""
    engine_type, reader = ocr_engine
    if engine_type is None:
        return None

    try:
        if engine_type == "easyocr":
            results = reader.readtext(str(image_path), detail=0)
            return "\n".join(results) if results else None
        elif engine_type == "tesseract":
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            return text.strip() or None
    except Exception:
        return None

    return None


def detect_qr_code(image_path: Path) -> bool:
    """检测图片中是否包含二维码。"""
    try:
        from PIL import Image
        img = Image.open(image_path).convert("L")
        # 简易检测：用 OpenCV 的 QRCodeDetector（如果可用）
        try:
            import cv2
            import numpy as np
            cv_img = cv2.imread(str(image_path))
            if cv_img is not None:
                detector = cv2.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(cv_img)
                return data != ""
        except ImportError:
            pass
        # 回退：检查图像中是否有典型的 QR 码定位图案（三个角上的方块）
        # 这比较难做，简单跳过
    except Exception:
        pass
    return False


def analyze_image(
    yolo_model,
    ocr_engine,
    image_path: Path,
    image_index: int,
    media_ref: str,
    source_url: str = "",
) -> Dict[str, Any]:
    """对单张图片运行 YOLO + OCR，返回 image_analysis 条目。"""
    detected_elements = {
        "has_logo": False,
        "has_qr_code": False,
        "has_price_info": False,
        "has_product_image": False,
        "has_chart_or_table": False,
        "has_promotional_text": False,
        "has_contact_info": False,
    }
    visual_codes: List[str] = []
    detected_objects: List[str] = []

    # ── YOLO 检测 ──
    try:
        results = yolo_model(str(image_path), verbose=False)
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if conf < 0.35:  # 低置信度过滤
                    continue
                coco_name = result.names.get(cls_id, f"cls_{cls_id}")

                if cls_id in PRODUCT_CLASSES:
                    detected_elements["has_product_image"] = True
                if cls_id in SCREEN_CLASSES:
                    detected_elements["has_chart_or_table"] = True  # 屏幕截图可能含图表/价格
                if cls_id in PERSON_CLASSES:
                    pass  # 人物不作为独立商业证据

                detected_objects.append(f"{coco_name}({conf:.0%})")
    except Exception as e:
        print(f"  ⚠️ YOLO 检测失败 [{image_path.name}]: {e}", file=sys.stderr)

    # 去重
    detected_objects = list(dict.fromkeys(detected_objects))

    # ── OCR 文字提取 ──
    ocr_text: Optional[str] = None
    if ocr_engine[0] is not None:
        ocr_text = run_ocr(ocr_engine, image_path)

    # ── 二维码检测 ──
    has_qr = detect_qr_code(image_path)
    detected_elements["has_qr_code"] = has_qr

    # ── OCR 文本分析 → 推断标志位 ──
    if ocr_text:
        ocr_lower = ocr_text.lower()
        # 价格/折扣信息
        price_keywords = ["¥", "￥", "$", "元", "价格", "原价", "现价", "优惠", "折扣",
                          "立减", "满减", "秒杀", "特价", "限时", "包邮", "免费"]
        if any(kw in ocr_lower or kw in ocr_text for kw in price_keywords):
            detected_elements["has_price_info"] = True

        # Logo/品牌关键词
        brand_keywords = ["logo", "品牌", "官方", "旗舰店", "专柜", "正品", "授权"]
        if any(kw in ocr_lower for kw in brand_keywords):
            detected_elements["has_logo"] = True

        # 促销文案
        promo_keywords = ["限时", "抢购", "秒杀", "特价", "优惠", "满减", "包邮",
                          "买一送一", "立省", "大促", "倒计时", "仅剩", "错过"]
        if any(kw in ocr_lower or kw in ocr_text for kw in promo_keywords):
            detected_elements["has_promotional_text"] = True

        # 联系方式
        contact_keywords = ["微信", "手机", "电话", "扫码", "加好友", "咨询",
                            "微信号", "QQ", "二维码", "关注", "添加"]
        if any(kw in ocr_lower or kw in ocr_text for kw in contact_keywords):
            detected_elements["has_contact_info"] = True

    # ── 推断 visual_evidence_codes ──
    if detected_elements["has_logo"] or detected_elements["has_product_image"]:
        visual_codes.append("V")
    if detected_elements["has_qr_code"] or detected_elements["has_contact_info"]:
        visual_codes.append("A")
    # D 需要明确"广告""合作"文字，不做自动推断
    if detected_elements["has_promotional_text"] and ocr_text:
        if any(kw in (ocr_text or "") for kw in ["广告", "合作", "赞助"]):
            visual_codes.append("D")

    # ── 生成描述 ──
    desc_parts = []
    if detected_objects:
        desc_parts.append(f"检测到: {', '.join(detected_objects[:5])}")
    if ocr_text:
        snippet = ocr_text[:100].replace("\n", " ")
        desc_parts.append(f"OCR文字: {snippet}")
    if has_qr:
        desc_parts.append("含二维码")
    description = "; ".join(desc_parts) if desc_parts else "无显著商业视觉特征"

    # ── 相关性说明 ──
    if visual_codes:
        relevance = f"视觉证据代码: {','.join(visual_codes)}; " + \
                    f"检测到{len(detected_objects)}类目标, OCR提取{'成功' if ocr_text else '失败'}"
    else:
        relevance = "未检测到明确商业视觉证据"

    return {
        "media_ref": media_ref,
        "source_url": source_url or None,
        "image_index": image_index,
        "analysis_method": "yolo_ocr_auto",
        "description": description,
        "ocr_text": ocr_text,
        "detected_elements": detected_elements,
        "visual_evidence_codes": visual_codes,
        "relevance_to_annotation": relevance,
        "image_quality_notes": "自动分析",
        "yolo_objects": detected_objects,
        "analyzed_at": datetime.now(CST).isoformat(),
    }


def process_posts(
    posts: List[Dict[str, Any]],
    yolo_model,
    ocr_engine,
    media_base: Path,
    limit: int = 0,
    use_prefilter: bool = True,
    use_opencv: bool = False,
    use_multimodal: bool = False,
    multimodal_model: str = "gpt-4o-mini",
    multimodal_backend: str = "openai",
) -> Dict[str, List[Dict[str, Any]]]:
    """批量处理帖子图片，返回 {post_id: image_analyses[]}。

    Args:
        use_prefilter: 是否启用 <图片N> 标记预过滤
        use_opencv: 是否启用 OpenCV 像素分析（仅预过滤启用时生效）
        use_multimodal: 是否使用多模态模型替代 YOLO+OCR
        multimodal_model: 多模态模型名
        multimodal_backend: "openai" 或 "ollama"
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    total = min(len(posts), limit) if limit > 0 else len(posts)

    # 统计
    stats = {"total_posts": total, "total_images": 0,
             "analyzed": 0, "skipped_by_marker": 0,
             "skipped_by_metadata": 0, "skipped_by_pixel": 0,
             "skipped_file_missing": 0}

    # 多模态模式：延迟导入
    if use_multimodal:
        from scripts.data.annotation.multimodal_image_analyzer import analyze_single_image_multimodal

    for idx, post in enumerate(posts[:total] if limit > 0 else posts, 1):
        pid = post.get("post_id", "?")
        title = post.get("title", "")[:50]
        text = post.get("text", "")
        media = post.get("media", [])
        stats["total_images"] += len(media)

        print(f"\n[{idx}/{total}] {pid}  {title}")

        if not media:
            print("  (无图片)")
            results[pid] = []
            continue

        # ── 预过滤：找出需要分析的图片 ──
        if use_prefilter:
            from scripts.data.annotation.image_prefilter import (
                prefilter_media_list, build_non_content_analysis,
                extract_content_image_indices,
            )
            analyze_indices, skip_indices, skip_analyses = prefilter_media_list(
                text, media, media_base, use_opencv=use_opencv)

            for si in skip_indices:
                reason = skip_analyses[si]["relevance_to_annotation"]
                if "marker" in reason:
                    stats["skipped_by_marker"] += 1
                elif "metadata" in reason:
                    stats["skipped_by_metadata"] += 1
                elif "pixel" in reason:
                    stats["skipped_by_pixel"] += 1
        else:
            analyze_indices = list(range(len(media)))
            skip_indices = []
            skip_analyses = {}

        # ── 分析需要处理的图片 ──
        analyses_dict: Dict[int, Dict] = dict(skip_analyses)  # 先填入跳过的

        for i in analyze_indices:
            m = media[i]
            ref = m.get("ref", "")
            url = m.get("source_url", "")
            img_path = media_base / ref
            img_num = i + 1

            if not img_path.exists():
                print(f"  [{img_num}] ✗ 文件缺失: {ref}")
                stats["skipped_file_missing"] += 1
                analyses_dict[i] = build_non_content_analysis(
                    ref, img_num,
                    type("R", (), {"method": "missing", "reason": "文件缺失"})())
                continue

            print(f"  [{img_num}] 🔍 {ref[-40:]} ...", end=" ", flush=True)

            if use_multimodal:
                # ── 多模态模式 ──
                analysis = analyze_single_image_multimodal(
                    img_path, image_index=img_num, media_ref=ref,
                    source_url=url, model=multimodal_model,
                    backend=multimodal_backend,
                )
            else:
                # ── YOLO + OCR 模式 ──
                analysis = analyze_image(yolo_model, ocr_engine, img_path, img_num, ref, url)

            codes = analysis.get("visual_evidence_codes", [])
            print(f"{'✅' if codes else '·'} {'商业' if codes else '普通'}图像"
                  f"{' [' + ','.join(codes) + ']' if codes else ''}")
            analyses_dict[i] = analysis
            stats["analyzed"] += 1

        # ── 按原始顺序输出 ──
        analyses = [analyses_dict[i] for i in sorted(analyses_dict.keys())]
        results[pid] = analyses

    # 打印统计
    print(f"\n{'='*60}")
    print(f"📊 预过滤统计:")
    print(f"  总图片:      {stats['total_images']}")
    print(f"  已分析:      {stats['analyzed']}")
    print(f"  标记跳过:    {stats['skipped_by_marker']} (正文无 <图片N>)")
    print(f"  元数据跳过:  {stats['skipped_by_metadata']} (太小/头像)")
    print(f"  像素跳过:    {stats['skipped_by_pixel']} (纯色/模糊)")
    print(f"  文件缺失:    {stats['skipped_file_missing']}")
    print(f"  节省分析:    {sum([stats[k] for k in ('skipped_by_marker','skipped_by_metadata','skipped_by_pixel','skipped_file_missing')])}/{stats['total_images']}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="图像自动标注 —— YOLO11n + OCR → image_analyses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              # 独立批量分析
              python scripts/data/auto_image_annotate.py --limit 10

              # 为已有标注补充 image_analyses
              python scripts/data/auto_image_annotate.py \\
                --supplement data/annotations/D_20260721_143000.json \\
                --output data/annotations/D_supplemented.json
        """),
    )
    parser.add_argument(
        "--input", "-i",
        default="data/run_outputs/anonymized_posts.jsonl",
        help="帖子 JSONL 路径",
    )
    parser.add_argument(
        "--media-base",
        default="data",
        help="图片根目录 (默认: data)",
    )
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL),
        help=f"YOLO 模型路径 (默认: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/annotations/auto_image_analyses.json",
        help="输出 JSON 文件路径",
    )
    parser.add_argument(
        "--supplement", "-s",
        default="",
        help="为已有标注 JSON 补充 image_analyses（就地修改输出到 --output）",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=0,
        help="限制处理条数，0=全部",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="跳过 OCR，仅 YOLO 检测",
    )
    parser.add_argument(
        "--no-prefilter",
        action="store_true",
        help="禁用 <图片N> 标记预过滤（默认启用）",
    )
    parser.add_argument(
        "--use-opencv",
        action="store_true",
        help="启用 OpenCV 像素分析作为预过滤兜底",
    )
    parser.add_argument(
        "--use-multimodal",
        action="store_true",
        help="使用多模态视觉模型替代 YOLO+OCR",
    )
    parser.add_argument(
        "--multimodal-model",
        default="gpt-4o-mini",
        help="多模态模型名 (默认: gpt-4o-mini)",
    )
    parser.add_argument(
        "--multimodal-backend",
        default="openai",
        choices=["openai", "ollama"],
        help="多模态后端 (默认: openai)",
    )
    args = parser.parse_args()

    # ── 加载 ──
    print("⏳ 加载 YOLO 模型...")
    yolo_model = load_yolo(Path(args.model))
    print("✅ YOLO 模型就绪")

    ocr_engine = (None, None)
    if not args.no_ocr:
        print("⏳ 加载 OCR 引擎...")
        ocr_engine = load_ocr()
        if ocr_engine[0]:
            print(f"✅ OCR 引擎: {ocr_engine[0]}")
        else:
            print("⚠️ OCR 不可用（pip install easyocr 或 pytesseract）")

    # ── 补充模式 ──
    if args.supplement:
        supp_path = Path(args.supplement)
        if not supp_path.exists():
            print(f"❌ 标注文件不存在: {supp_path}")
            sys.exit(1)

        print(f"\n📂 加载标注文件: {supp_path}")
        annotations = load_jsonl(supp_path)
        # 过滤掉孤立的 image_analysis 对象（无 post_id 的记录）
        annotations = [a for a in annotations if a.get("post_id")]
        print(f"   共 {len(annotations)} 条标注记录（已过滤孤立对象）")

        # 将 post 为空的记录，从 --input 中回填
        input_path = Path(args.input)
        posts_lookup: Dict[str, Dict[str, Any]] = {}
        empty_post_count = sum(1 for a in annotations if not a.get("post") or a.get("post") == {})
        if empty_post_count > 0 and input_path.exists():
            print(f"   检测到 {empty_post_count} 条记录的 post 为空，从 {input_path} 回填")
            all_posts = load_jsonl(input_path)
            posts_lookup = {p.get("post_id", ""): p for p in all_posts}
            for ann in annotations:
                if not ann.get("post") or ann.get("post") == {}:
                    pid = ann.get("post_id", "")
                    if pid in posts_lookup:
                        ann["post"] = posts_lookup[pid]

        # 收集所有唯一的 post，去重
        posts = [a.get("post", {}) for a in annotations if a.get("post") and a["post"] != {}]
        seen = set()
        unique_posts = []
        for p in posts:
            pid = p.get("post_id", "")
            if pid and pid not in seen:
                seen.add(pid)
                unique_posts.append(p)

        if not unique_posts:
            # 回退：从 --input 加载
            input_path = Path(args.input)
            if input_path.exists():
                print(f"   标注中无 post 原文，从 {input_path} 加载")
                unique_posts = load_jsonl(input_path)
                # 只处理已有标注的帖子
                annotated_ids = {a["post_id"] for a in annotations}
                unique_posts = [p for p in unique_posts if p.get("post_id") in annotated_ids]

        print(f"   待分析图片的帖子: {len(unique_posts)}")
        media_base = Path(args.media_base)
        analyses_map = process_posts(unique_posts, yolo_model, ocr_engine,
                                     media_base, args.limit,
                                     use_prefilter=not args.no_prefilter,
                                     use_opencv=args.use_opencv,
                                     use_multimodal=args.use_multimodal,
                                     multimodal_model=args.multimodal_model,
                                     multimodal_backend=args.multimodal_backend)

        # 补充 image_analyses 到标注记录
        supplemented = 0
        for ann in annotations:
            pid = ann.get("post_id", "")
            if pid in analyses_map and analyses_map[pid]:
                ann["image_analyses"] = analyses_map[pid]
                supplemented += 1

        # 输出
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for ann in annotations:
                f.write(json.dumps(ann, ensure_ascii=False, indent=2) + "\n\n")

        print(f"\n✅ 已补充 {supplemented}/{len(annotations)} 条标注的 image_analyses")
        print(f"   输出: {output_path}")
        return

    # ── 独立模式 ──
    input_path = Path(args.input)
    print(f"\n📂 加载帖子: {input_path}")
    posts = load_jsonl(input_path)
    print(f"   共 {len(posts)} 条帖子")

    media_base = Path(args.media_base)
    analyses_map = process_posts(posts, yolo_model, ocr_engine, media_base, args.limit,
                                 use_prefilter=not args.no_prefilter,
                                 use_opencv=args.use_opencv,
                                 use_multimodal=args.use_multimodal,
                                 multimodal_model=args.multimodal_model,
                                 multimodal_backend=args.multimodal_backend)

    # 组装输出
    output_records = []
    for post in posts[:args.limit] if args.limit > 0 else posts:
        pid = post.get("post_id", "")
        output_records.append({
            "post_id": pid,
            "annotator_id": "auto",
            "supplement_version": "1.0",
            "image_analyses": analyses_map.get(pid, []),
            "markdown_notes": "",
            "edge_case_discussion": None,
            "created_at": datetime.now(CST).isoformat(),
            "updated_at": datetime.now(CST).isoformat(),
        })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in output_records:
            f.write(json.dumps(rec, ensure_ascii=False, indent=2) + "\n\n")

    total_imgs = sum(len(r["image_analyses"]) for r in output_records)
    total_with_evidence = sum(
        1 for r in output_records
        for a in r["image_analyses"]
        if a.get("visual_evidence_codes")
    )
    print(f"\n✅ 完成: {len(output_records)} 条帖子, {total_imgs} 张图片")
    print(f"   其中 {total_with_evidence} 张检测到商业视觉证据")
    print(f"   输出: {output_path}")


if __name__ == "__main__":
    main()
