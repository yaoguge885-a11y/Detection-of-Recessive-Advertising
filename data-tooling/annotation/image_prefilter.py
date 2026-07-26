#!/usr/bin/env python3
"""
图片预过滤器 —— 在 YOLO/OCR/多模态 分析之前，快速过滤非内容图片。

三层过滤策略（按优先级）:

  第一层（零成本）: <图片N> 标记匹配
    - 从帖子文本中提取所有 <图片N> 标记编号
    - 只有对应编号的 media 项才进入分析
    - 假设: 无标记 = 非内容图（已在 HTML 清洗时由 LLM/BS4 判定）

  第二层（低成本）: 文件元数据快速检查
    - 文件大小 < 2KB → 太可能是内容图
    - 尺寸极小 (< 100x100 px) → 头像/图标
    - 完美正方形 + 小尺寸 (< 400x400) → 头像

  第三层（中等成本）: OpenCV 像素分析
    - 低颜色方差 → 纯色背景/分隔条
    - 低边缘密度 (Laplacian) → 模糊背景
    - 用于无 <图片N> 标记的兜底判断

用法：
  from scripts.data.annotation.image_prefilter import should_analyze

  for i, media_item in enumerate(post['media']):
      if should_analyze(post['text'], i, image_path):
          # 进入 YOLO/OCR/多模态分析
          analyze(image_path)
      else:
          # 标记为非内容图，跳过
          mark_as_non_content(media_item)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════════════
# 第一层: <图片N> 标记匹配
# ═══════════════════════════════════════════════════════════════

def extract_content_image_indices(text: str) -> Set[int]:
    """从文本中提取所有 <图片N> 标记的编号（1-based → 转为 0-based）。

    Example:
        "段落1<图片1>段落2<图片3>" → {0, 2}
        （图片1 → index 0, 图片3 → index 2）
    """
    if not text:
        return set()
    markers = re.findall(r'<图片(\d+)>', text)
    return {int(m) - 1 for m in markers}  # 转为 0-based


def has_content_marker(text: str, media_index: int) -> Tuple[bool, str]:
    """判断 media[media_index] 是否在正文中有对应的 <图片N> 标记。

    Args:
        text: 帖子正文（含 <图片N> 标记）
        media_index: media[] 中的索引 (0-based)

    Returns:
        (is_content, reason)
    """
    if not text:
        return True, "no_text: 正文为空，无法基于标记判断，默认视为内容图"

    content_indices = extract_content_image_indices(text)
    image_num = media_index + 1  # 转为 1-based

    if media_index in content_indices:
        return True, f"marker_found: <图片{image_num}> 已标记"
    elif not content_indices:
        return True, "no_markers: 正文无 <图片N> 标记，可能未经 LLM/BS4 清洗，默认全部分析"
    else:
        return False, f"no_marker: 正文中无 <图片{image_num}> 标记（仅有 {sorted([i+1 for i in content_indices])}）"


# ═══════════════════════════════════════════════════════════════
# 第二层: 文件元数据快速检查
# ═══════════════════════════════════════════════════════════════

# 文件大小阈值
MIN_CONTENT_FILE_SIZE = 2 * 1024       # 2KB，小于此值极不可能为内容图
SUSPICIOUS_FILE_SIZE = 5 * 1024        # 5KB，需进一步检查

# 尺寸阈值
MIN_CONTENT_WIDTH = 100                # < 100px 宽 → 图标
MIN_CONTENT_HEIGHT = 100               # < 100px 高 → 图标
AVATAR_MAX_SIZE = 400                  # 方图边长 ≤ 400px → 可能是头像
AVATAR_SQUARE_TOLERANCE = 0.05         # 宽高比容差 5%


def check_file_metadata(image_path: Path) -> Tuple[bool, str]:
    """基于文件元数据（大小、尺寸）快速判断是否为内容图。

    不打开图片像素数据，仅读取文件头和基本信息，速度极快。

    Returns:
        (is_likely_content, reason)
    """
    if not image_path.exists():
        return False, "file_missing: 文件不存在"

    # 文件大小
    file_size = image_path.stat().st_size
    if file_size < MIN_CONTENT_FILE_SIZE:
        return False, f"too_small_file: {file_size}B < {MIN_CONTENT_FILE_SIZE}B"

    # 图片尺寸（只读头部，不解码全部像素）
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            w, h = img.size
    except Exception:
        return True, "cannot_read_size: 无法读取尺寸，默认通过"

    if w < MIN_CONTENT_WIDTH or h < MIN_CONTENT_HEIGHT:
        return False, f"too_small_dim: {w}x{h} < {MIN_CONTENT_WIDTH}x{MIN_CONTENT_HEIGHT}"

    # 正方形 + 小尺寸 → 头像
    aspect = w / max(h, 1)
    is_square = abs(aspect - 1.0) < AVATAR_SQUARE_TOLERANCE
    is_small = w <= AVATAR_MAX_SIZE and h <= AVATAR_MAX_SIZE

    if is_square and is_small:
        if file_size < SUSPICIOUS_FILE_SIZE:
            return False, f"likely_avatar: {w}x{w} square, {file_size}B"
        else:
            # 大文件正方形可能是产品图，不过滤
            return True, f"square_but_large: {w}x{w}, {file_size}B"

    return True, f"size_ok: {w}x{h}, {file_size}B"


# ═══════════════════════════════════════════════════════════════
# 第三层: OpenCV 像素分析（兜底）
# ═══════════════════════════════════════════════════════════════

# 颜色方差阈值
LOW_VARIANCE_THRESHOLD = 200.0    # 方差低于此值 → 纯色/渐变背景
BLUR_THRESHOLD = 50.0             # Laplacian 方差低于此值 → 模糊/无纹理

# 单色占比阈值
MONOCHROME_RATIO = 0.85           # 单一主色像素占比 > 85% → 背景图


def check_pixel_content(image_path: Path) -> Tuple[bool, str]:
    """用 OpenCV 分析像素内容，判断是否为背景/纯色/模糊图。

    仅在无 <图片N> 标记且元数据无法确定时调用。
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return True, "opencv_unavailable: 跳过像素分析"

    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return True, "opencv_read_failed: 默认通过"
    except Exception:
        return True, "opencv_error: 默认通过"

    h, w = img.shape[:2]

    # 1. 颜色方差检查（纯色背景）
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variance = np.var(gray)
    if variance < LOW_VARIANCE_THRESHOLD:
        return False, f"solid_color: gray_variance={variance:.1f}"

    # 2. 模糊度检查（Laplacian 边缘检测）
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < BLUR_THRESHOLD:
        return False, f"blurred: laplacian_var={laplacian_var:.1f}"

    # 3. 单色占比检查
    # 将颜色量化到 32 bins，检查最大 bin 的占比
    quantized = (gray // 8).astype(np.uint8)
    unique, counts = np.unique(quantized, return_counts=True)
    max_ratio = counts.max() / counts.sum()
    if max_ratio > MONOCHROME_RATIO:
        return False, f"monochrome: dominant_color={max_ratio:.1%}"

    return True, f"pixel_ok: var={variance:.1f} lap={laplacian_var:.1f}"


# ═══════════════════════════════════════════════════════════════
# 统一预过滤入口
# ═══════════════════════════════════════════════════════════════

class PrefilterResult:
    """预过滤结果。"""
    def __init__(self, should_analyze: bool, reason: str, method: str):
        self.should_analyze = should_analyze
        self.reason = reason
        self.method = method  # "marker" / "metadata" / "pixel" / "default"

    def __repr__(self):
        return f"Prefilter({self.should_analyze}, {self.method}: {self.reason})"


def should_analyze_image(
    text: str,
    media_index: int,
    image_path: Path,
    use_opencv: bool = False,
) -> PrefilterResult:
    """判断是否应对 media[media_index] 进入后续分析。

    分层决策:
      Layer 1: <图片N> 标记 → 最可信
      Layer 2: 文件元数据 → 快速
      Layer 3: OpenCV 像素 → 兜底（可选）

    Args:
        text: 帖子正文
        media_index: media[] 索引
        image_path: 图片文件路径
        use_opencv: 是否启用 OpenCV 像素分析

    Returns:
        PrefilterResult
    """
    # ── Layer 1: <图片N> 标记 ──
    is_content, reason = has_content_marker(text, media_index)
    if not is_content:
        return PrefilterResult(False, reason, "marker")

    # ── Layer 2: 文件元数据 ──
    is_content, reason = check_file_metadata(image_path)
    if not is_content:
        return PrefilterResult(False, reason, "metadata")

    # ── Layer 3: OpenCV 像素（仅在图片疑似非内容时启用）──
    if use_opencv and "square_but_large" not in reason:
        is_content, reason = check_pixel_content(image_path)
        if not is_content:
            return PrefilterResult(False, reason, "pixel")

    return PrefilterResult(True, reason, "marker" if "marker" in reason else "metadata")


def build_non_content_analysis(
    media_ref: str,
    image_index: int,
    prefilter: PrefilterResult,
) -> Dict:
    """为非内容图片生成占位 image_analysis 条目。

    这样 output JSON 中每条 media 都有对应条目，
    标注者可以清楚地看到哪些图片被自动跳过了。
    """
    return {
        "media_ref": media_ref,
        "source_url": None,
        "image_index": image_index,
        "analysis_method": f"prefiltered_{prefilter.method}",
        "description": f"[自动跳过] {prefilter.reason}",
        "ocr_text": None,
        "detected_elements": {
            "has_logo": False, "has_qr_code": False, "has_price_info": False,
            "has_product_image": False, "has_chart_or_table": False,
            "has_promotional_text": False, "has_contact_info": False,
        },
        "visual_evidence_codes": [],
        "relevance_to_annotation": f"非内容图片: {prefilter.reason}",
        "image_quality_notes": "未分析（预过滤跳过）",
        "analyzed_at": None,
    }


# ═══════════════════════════════════════════════════════════════
# 批量预过滤
# ═══════════════════════════════════════════════════════════════

def prefilter_media_list(
    text: str,
    media_list: List[Dict],
    media_base: Path,
    use_opencv: bool = False,
) -> Tuple[List[int], List[int], Dict[int, Dict]]:
    """对帖子的所有 media[] 条目进行预过滤。

    Args:
        text: 帖子正文
        media_list: post['media'] 列表
        media_base: 图片根目录
        use_opencv: 是否启用 OpenCV

    Returns:
        (analyze_indices, skip_indices, skip_analyses)
        - analyze_indices: 需要分析的 media 索引列表
        - skip_indices: 跳过的 media 索引列表
        - skip_analyses: {index: placeholder_analysis} 供直接写入
    """
    analyze = []
    skip = []
    skip_analyses = {}

    # 先提取标记集合（一次，避免重复解析）
    content_markers = extract_content_image_indices(text) if text else set()

    for i, m in enumerate(media_list):
        ref = m.get("ref", "")
        img_path = media_base / ref if ref else None

        # 检查 <图片N> 标记
        if text and content_markers:
            if i not in content_markers:
                image_num = i + 1
                reason = f"no_marker: 正文中无 <图片{image_num}> 标记"
                skip.append(i)
                skip_analyses[i] = build_non_content_analysis(
                    ref, image_num,
                    PrefilterResult(False, reason, "marker"))
                continue

        # 文件元数据检查
        if img_path and img_path.exists():
            is_content, reason = check_file_metadata(img_path)
            if not is_content:
                skip.append(i)
                skip_analyses[i] = build_non_content_analysis(
                    ref, i + 1,
                    PrefilterResult(False, reason, "metadata"))
                continue

            # OpenCV 像素检查（可选）
            if use_opencv:
                is_content, reason = check_pixel_content(img_path)
                if not is_content:
                    skip.append(i)
                    skip_analyses[i] = build_non_content_analysis(
                        ref, i + 1,
                        PrefilterResult(False, reason, "pixel"))
                    continue

        analyze.append(i)

    return analyze, skip, skip_analyses


# ═══════════════════════════════════════════════════════════════
# 命令行测试
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="图片预过滤器（测试）")
    parser.add_argument("--text", default="段落1<图片1>段落2<图片3>",
                        help="测试用的帖子正文")
    parser.add_argument("--image", default=None, help="测试用的图片路径")
    parser.add_argument("--index", type=int, default=0, help="media 索引")
    parser.add_argument("--use-opencv", action="store_true", help="启用 OpenCV")
    args = parser.parse_args()

    print(f"正文: {args.text[:100]}")
    print(f"提取的 <图片N> 编号 (0-based): {sorted(extract_content_image_indices(args.text))}")

    if args.image:
        img_path = Path(args.image)
        result = should_analyze_image(
            args.text, args.index, img_path, use_opencv=args.use_opencv)
        print(f"\nmedia[{args.index}] → {result}")
    else:
        # 模拟
        for i in range(5):
            result = should_analyze_image(
                args.text, i, Path("dummy.jpg"), use_opencv=False)
            print(f"media[{i}] → {result}")
