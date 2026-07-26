#!/usr/bin/env python3
"""
Ollama 本地模型适配器 —— 用本地模型替代云端 API 做 HTML 结构化提取。

支持的模型与最低硬件要求：

  ┌─────────────────────┬──────────┬─────────────┬──────────────┐
  │ 模型                 │ 参数量    │ 4-bit 显存   │ 适用场景       │
  ├─────────────────────┼──────────┼─────────────┼──────────────┤
  │ Qwen2.5-7B-Instruct │ 7B       │ ~5 GB       │ ✅ 推荐（最小）│
  │ Qwen2.5-14B         │ 14B      │ ~9 GB       │ ✅ 更准确       │
  │ DeepSeek-R1-8B      │ 8B       │ ~5 GB       │ ✅ 推理强       │
  │ Gemma-2-9B          │ 9B       │ ~6 GB       │ ✅ 轻量         │
  │ Llama-3.1-8B        │ 8B       │ ~5 GB       │ ⚠️ 中文较弱     │
  │ Qwen2.5-1.5B        │ 1.5B     │ ~2 GB       │ ❌ 不够          │
  │ Qwen2.5-3B          │ 3B       │ ~3 GB       │ ⚠️ 勉强         │
  └─────────────────────┴──────────┴─────────────┴──────────────┘

  推荐最低配置：Qwen2.5-7B-Instruct (4-bit 量化) ≈ 5GB 显存
  7B 以下模型对中文 HTML 结构理解不稳定，容易产生 JSON 格式错误。

安装与使用：

  # 1. 安装 Ollama（https://ollama.com）
  # 2. 拉取模型
  ollama pull qwen2.5:7b

  # 3. 在 crawl_public_posts.py 中使用
  python scripts/data/crawler/crawl_public_posts.py \\
      --input data/raw/urls.txt \\
      --use-ollama \\
      --ollama-model qwen2.5:7b

  # 4. 独立测试
  python scripts/data/crawler/ollama_extractor.py --test
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# ═══════════════════════════════════════════════════════════════
# Prompt 模板（为 7B 模型优化：指令更明确、输出约束更强）
# ═══════════════════════════════════════════════════════════════

PROMPT_OLLAMA = """你是一个精确的 HTML 解析器。从下方微信文章 HTML 中提取三项信息，只输出一个 JSON 对象。

## HTML 内容
{html_content}

## 要求

1. 提取标题：<title> 标签中的文字，去掉 "公众号名称" 后缀
2. 提取正文：只保留文章自然段落，删除所有微信 UI（赞赏/留言/关注/导航/阅读数）
3. 处理图片：正文有 {image_count} 张图片。在对应位置插入标记 <图片1> <图片2>...，编号从 1 开始连续递增。尺寸过小的图标/二维码不标记。

## 输出格式（只输出 JSON，不要任何其他文字）
```json
{{
  "title": "文章标题",
  "clean_text": "段落1\\n\\n<图片1>\\n\\n段落2",
  "image_captions": [
    {{"index": 1, "is_content": true, "caption": "图片说明或 null"}}
  ],
  "notes": ""
}}
```"""


PROMPT_OLLAMA_SIMPLE = """解析微信文章 HTML，输出 JSON。

要求：
1. title: 提取文章标题（去公众号后缀）
2. clean_text: 纯净正文，图片位置插入<图片1> <图片2>标记
3. image_captions: 每张内容图片的标注，无标注填 null

HTML:
{html_content}

只有 {image_count} 张图。只输出 JSON:"""  # noqa  # 简化版供小模型使用


# ═══════════════════════════════════════════════════════════════
# Ollama 客户端
# ═══════════════════════════════════════════════════════════════

def _check_ollama_available() -> bool:
    """检测 Ollama 服务是否在运行。"""
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _invoke_ollama(
    prompt: str,
    model: str = "qwen2.5:7b",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """调用 Ollama API 获取文本响应。"""
    import requests

    # Ollama 使用 generate 端点（非 chat），对简单 prompt 更稳定
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def _parse_json_response(text: str) -> Dict:
    """从模型输出中健壮提取 JSON。小模型经常在 JSON 外包裹 markdown 或多余文字。"""
    text = text.strip()

    # 去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 正则匹配最外层 {...}
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 尝试修复常见小模型 JSON 错误
    text = re.sub(r",\s*}", "}", text)   # 多余逗号
    text = re.sub(r",\s*]", "]", text)   # 数组尾部逗号
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"无法从模型输出解析 JSON（前500字符）:\n{text[:500]}")


# ═══════════════════════════════════════════════════════════════
# 提取流程
# ═══════════════════════════════════════════════════════════════

def _preprocess_html_for_ollama(html: str, max_chars: int = 8000) -> str:
    """预处理 HTML 以减少 token 消耗，同时保留结构信息。

    与 API 版本的 _preprocess_html 类似，但更激进地裁剪。
    """
    # 删除 script/style/注释
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)

    # 剥离大部分标签属性，只保留 src/data-src
    def _strip_attrs(m: re.Match) -> str:
        tag = m.group(1)
        inner = m.group(2)
        src = ""
        m_src = re.search(r"""(?:data-)?src\s*=\s*["']([^"']+)["']""", inner, re.IGNORECASE)
        if m_src:
            src = f' src="{m_src.group(1)}"'
        return f"<{tag}{src}>"

    html = re.sub(r"<(\w+)(\s[^>]*)>", _strip_attrs, html, flags=re.IGNORECASE)

    # 压缩空白
    html = re.sub(r"\s+", " ", html)
    html = html.strip()

    if len(html) > max_chars:
        # 保留前后各一半
        half = max_chars // 2
        html = html[:half] + "\n...(中间内容已截断)...\n" + html[-half:]

    return html


def extract_with_ollama(
    html: str,
    image_urls: List[str],
    model: str = "qwen2.5:7b",
    use_simple_prompt: bool = False,
    timeout: int = 120,
) -> Dict:
    """用本地 Ollama 模型从 HTML 中提取正文 + 图片位置。

    Args:
        html: 原始 HTML
        image_urls: 图片 URL 列表
        model: Ollama 模型名（如 qwen2.5:7b）
        use_simple_prompt: True=用简化 prompt（适合 7B 以下小模型）
        timeout: 超时秒数

    Returns:
        与 llm_extract_from_html 格式兼容的 Dict
    """
    if not _check_ollama_available():
        return {
            "title": None, "clean_text": "", "media_enrichments": [],
            "confidence": 0.0, "needs_review": True,
            "notes": "Ollama 服务不可用。请运行: ollama serve",
        }

    clean_html = _preprocess_html_for_ollama(html)
    total_images = len(image_urls)

    if use_simple_prompt:
        prompt = PROMPT_OLLAMA_SIMPLE.format(
            html_content=clean_html, image_count=total_images)
    else:
        prompt = PROMPT_OLLAMA.format(
            html_content=clean_html, image_count=total_images)

    print(f"    [Ollama] 调用 {model} ({len(clean_html)} 字符, {total_images} 图)...")

    try:
        raw = _invoke_ollama(prompt, model=model, temperature=0.0, timeout=timeout)
        result = _parse_json_response(raw)
    except Exception as exc:
        print(f"    [Ollama] 失败: {exc}")
        return {
            "title": None, "clean_text": "", "media_enrichments": [
                {"index": i, "is_content": True, "caption": None}
                for i in range(total_images)
            ],
            "confidence": 0.0, "needs_review": True,
            "notes": f"Ollama 提取失败: {exc}",
        }

    # 标准化输出格式
    captions = result.get("image_captions", [])
    media_enrichments = []
    for cap in captions:
        idx = cap.get("index", -1)
        if isinstance(idx, int) and idx >= 1:
            media_enrichments.append({
                "index": idx - 1,
                "is_content": cap.get("is_content", True),
                "caption": cap.get("caption"),
            })

    # 兜底：未被覆盖的图片
    covered = {e["index"] for e in media_enrichments}
    for i in range(total_images):
        if i not in covered:
            media_enrichments.append({
                "index": i, "is_content": True, "caption": None,
            })

    confidence = 0.7  # 本地模型默认置信度
    needs_review = confidence < 0.8

    return {
        "title": result.get("title"),
        "clean_text": result.get("clean_text", ""),
        "media_enrichments": media_enrichments,
        "confidence": confidence,
        "needs_review": needs_review,
        "notes": f"Ollama/{model}: {result.get('notes', '')}",
        "_method": f"ollama:{model}",
    }


# ═══════════════════════════════════════════════════════════════
# 命令行测试
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ollama 本地模型提取器（测试）")
    parser.add_argument("--test", action="store_true", help="运行连通性测试")
    parser.add_argument("--model", default="qwen2.5:7b", help="模型名")
    parser.add_argument("--simple", action="store_true", help="使用简化 prompt")
    args = parser.parse_args()

    if args.test:
        print("检测 Ollama 服务...")
        if _check_ollama_available():
            print("[OK] Ollama 服务运行中")

            # 列出可用模型
            try:
                import requests
                resp = requests.get("http://localhost:11434/api/tags", timeout=5)
                models = [m["name"] for m in resp.json().get("models", [])]
                print(f"可用模型: {', '.join(models[:10])}")
            except Exception:
                pass

            # 简单测试（短文本）
            test_html = "<html><head><title>测试文章_公众号</title></head><body><div id='js_content'><p>这是一段测试正文。</p><img data-src='https://mmbiz.qpic.cn/test.jpg' /><p>第二段文字。</p></div></body></html>"
            print("\n测试提取...")
            result = extract_with_ollama(test_html, ["https://mmbiz.qpic.cn/test.jpg"], model=args.model, use_simple_prompt=args.simple)
            print(f"标题: {result.get('title')}")
            print(f"正文: {result.get('clean_text', '')[:200]}")
            print(f"置信度: {result.get('confidence')}")
            print(f"需复核: {result.get('needs_review')}")
        else:
            print("[FAIL] Ollama 服务未运行")
            print("请执行: ollama serve")
            print("然后: ollama pull qwen2.5:7b")
    else:
        print("请使用 --test 运行连通性测试")
        print(f"推荐模型: qwen2.5:7b (ollama pull qwen2.5:7b)")
