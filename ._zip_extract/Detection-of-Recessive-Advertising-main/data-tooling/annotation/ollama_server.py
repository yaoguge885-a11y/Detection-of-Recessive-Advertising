#!/usr/bin/env python3
"""Ollama 服务器管理工具 —— 显式启动/查询/预热模型。

设计动机（co-pilot-auto-judge-design）：
  - 依赖 Ollama 隐式启动时，模型冷启动加载 6.6GB 常导致首次推理超时回退；
  - 本工具显式管理服务器生命周期，并通过 /api/ps 查询模型是否已驻留，
    已加载则跳过预热，未加载则预加载并设置 keep_alive 常驻。

用法：
  # 查看服务器状态（版本 / 已安装模型 / 当前已加载模型）
  python ollama_server.py status [--url http://localhost:11434]

  # 预加载模型并常驻（已加载则跳过）
  python ollama_server.py preload [--model qwen3.5:9b] [--keep-alive 30m]

  # 确保服务器运行（未运行则尝试拉起 ollama serve），随后可预热
  python ollama_server.py serve [--model qwen3.5:9b] [--preload]

模块函数（供 auto_judge / batch_pre_annotate 复用）：
  server_status(url)                 -> dict  版本/已安装/已加载模型
  ensure_ollama_running(url)         -> bool  未运行则拉起 ollama serve
  ensure_model_loaded(model,url,ka)  -> bool  已加载跳过，否则预热并常驻
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
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

OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "qwen3.5:9b"
OLLAMA_KEEP_ALIVE = "30m"       # 模型常驻时长；-1=永久
OLLAMA_WARMUP_TIMEOUT = 300     # 首次加载 6.6GB 模型放宽到 5 分钟
OLLAMA_READY_TIMEOUT = 40       # 拉起 serve 后等待就绪的时间（含 GPU 发现，约 25s）
SERVE_LOG = "data/run_outputs/ollama_serve.log"


def detect_models_dir() -> Optional[str]:
    """从 Ollama 桌面应用日志探测其 OLLAMA_MODELS 模型目录。

    桌面应用可能把模型存到非默认路径（如 E:\\ollama），
    直接用默认 C:\\Users\\<user>\\.ollama\\models 会找不到已下载的模型。
    Returns: 探测到的目录；探测失败返回 None（用默认路径）。
    """
    import os
    log_dir = os.environ.get("LOCALAPPDATA", "")
    if not log_dir:
        return None
    for name in ("server.log", "app.log"):
        p = Path(log_dir) / "Ollama" / name
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.search(r"OLLAMA_MODELS:\s*([^\s\"]+)", line)
                if m:
                    return m.group(1).strip()
        except Exception:
            continue
    return None


# ════════════════════════════════════════════════════════════════════
# 状态查询
# ════════════════════════════════════════════════════════════════════
def ollama_running(url: str = OLLAMA_DEFAULT_URL, timeout: float = 5) -> bool:
    """服务器是否可访问（GET /api/tags）。"""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def server_status(url: str = OLLAMA_DEFAULT_URL, timeout: float = 5) -> Dict[str, Any]:
    """综合服务器状态：可用性 / 版本 / 已安装模型 / 已加载模型。

    Returns:
        {
          "available": bool,
          "url": str,
          "version": str|None,
          "models": [已安装模型名...],
          "loaded": [当前驻留内存的模型...],
          "error": str|None,
        }
    """
    base = url.rstrip("/")
    result: Dict[str, Any] = {
        "available": False, "url": url, "version": None,
        "models": [], "loaded": [], "error": None,
    }
    try:
        r = requests.get(f"{base}/api/version", timeout=timeout)
        if r.status_code == 200:
            result["version"] = (r.json() or {}).get("version")
    except Exception as exc:
        result["error"] = f"version: {str(exc)[:120]}"
        return result

    try:
        tags = requests.get(f"{base}/api/tags", timeout=timeout)
        if tags.status_code == 200:
            result["models"] = [m.get("name", "") for m in (tags.json() or {}).get("models", [])]
    except Exception as exc:
        result["error"] = f"tags: {str(exc)[:120]}"

    try:
        ps = requests.get(f"{base}/api/ps", timeout=timeout)
        if ps.status_code == 200:
            loaded = []
            for m in (ps.json() or {}).get("models", []):
                name = m.get("name", "") or ""
                if "@" in name:  # name 可能带 @host 后缀
                    name = name.split("@")[0]
                loaded.append(name)
            result["loaded"] = loaded
    except Exception as exc:
        result["error"] = (result["error"] or "") + f" | ps: {str(exc)[:120]}"

    result["available"] = True
    return result


def model_loaded(model: str = OLLAMA_DEFAULT_MODEL,
                 url: str = OLLAMA_DEFAULT_URL,
                 timeout: float = 5) -> bool:
    """模型当前是否已驻留内存（/api/ps）。"""
    try:
        base = url.rstrip("/")
        ps = requests.get(f"{base}/api/ps", timeout=timeout)
        if ps.status_code != 200:
            return False
        target = model.split(":")[0]  # 兼容 name 前缀匹配
        for m in (ps.json() or {}).get("models", []):
            name = (m.get("name", "") or "").split("@")[0]
            if name == model or name.startswith(target + ":"):
                return True
        return False
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# 服务器生命周期
# ════════════════════════════════════════════════════════════════════
def ensure_ollama_running(url: str = OLLAMA_DEFAULT_URL,
                          start_if_down: bool = True,
                          wait: float = OLLAMA_READY_TIMEOUT,
                          models_dir: Optional[str] = None) -> bool:
    """确保 Ollama 服务器可访问；未运行且允许时尝试拉起 `ollama serve`。

    Args:
        url: 服务器地址
        start_if_down: 未运行时是否尝试拉起
        wait: 等待就绪的秒数
        models_dir: 模型目录；None 时从桌面应用日志探测（保证与已下载模型一致）

    Returns:
        True=服务器就绪；False=不可用。
    """
    if ollama_running(url):
        return True
    if not start_if_down:
        return False

    # 尝试拉起 ollama serve（分离进程，日志写入文件）
    from pathlib import Path
    log_path = Path(SERVE_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 探测正确的模型目录：桌面应用日志优先，其次显式传入，最后默认
    models = models_dir or detect_models_dir()
    env = None
    if models:
        env = dict(os.environ)
        env["OLLAMA_MODELS"] = models
    try:
        with log_path.open("w", encoding="utf-8") as f:
            if sys.platform == "win32":
                creationflags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=f, stderr=f, env=env,
                    creationflags=creationflags,
                    close_fds=True,
                )
            else:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=f, stderr=f, env=env,
                    start_new_session=True,
                    close_fds=True,
                )
    except Exception as exc:
        print(f"  ⚠️ 启动 ollama serve 失败: {exc}", file=sys.stderr)
        return False

    # 轮询等待就绪
    deadline = time.time() + wait
    while time.time() < deadline:
        if ollama_running(url):
            return True
        time.sleep(0.5)
    return False


# ════════════════════════════════════════════════════════════════════
# 模型预热（先查驻留，已加载则跳过）
# ════════════════════════════════════════════════════════════════════
def ensure_model_loaded(model: str = OLLAMA_DEFAULT_MODEL,
                        url: str = OLLAMA_DEFAULT_URL,
                        keep_alive: str = OLLAMA_KEEP_ALIVE,
                        timeout: float = OLLAMA_WARMUP_TIMEOUT) -> bool:
    """确保模型已加载并常驻。

    1. 若 /api/ps 显示模型已驻留 → 直接返回 True（不重复加载）；
    2. 否则发一个最小请求把模型加载进内存，并带 keep_alive 常驻。
    """
    if model_loaded(model, url):
        return True
    try:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"num_predict": 1, "temperature": 0.0},
        }
        resp = requests.post(
            f"{url.rstrip('/')}/api/chat", json=payload, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════
def cmd_status(args) -> int:
    st = server_status(args.url)
    print(f"Ollama 服务器: {args.url}")
    print(f"  可用: {'✅' if st['available'] else '❌'}  版本: {st['version'] or '未知'}")
    if st["error"]:
        print(f"  诊断: {st['error']}")
    print(f"  已安装模型 ({len(st['models'])}): {', '.join(st['models']) or '(无)'}")
    print(f"  当前已加载 ({len(st['loaded'])}): {', '.join(st['loaded']) or '(无)'}")
    if not st["models"] and st["available"]:
        print(f"\n  提示: 未安装任何模型，请运行 `ollama pull {OLLAMA_DEFAULT_MODEL}`")
    if not st["loaded"] and st["models"]:
        print(f"\n  提示: 模型未驻留，可运行 `python ollama_server.py preload --model {OLLAMA_DEFAULT_MODEL}`")
    return 0 if st["available"] else 1


def cmd_preload(args) -> int:
    if not ensure_ollama_running(args.url, start_if_down=True, models_dir=args.models_dir):
        print(f"❌ 服务器不可用且无法拉起: {args.url}")
        return 1
    print(f"⏳ 确保模型已加载: {args.model}（keep_alive={args.keep_alive}）...")
    if ensure_model_loaded(args.model, args.url, args.keep_alive):
        print(f"  ✅ 模型已就绪并常驻")
        return 0
    print(f"  ⚠️ 加载失败（或超时 {OLLAMA_WARMUP_TIMEOUT}s），请检查模型是否存在")
    return 1


def cmd_serve(args) -> int:
    if ollama_running(args.url):
        print(f"✅ Ollama 已在运行: {args.url}")
    else:
        models_hint = args.models_dir or detect_models_dir()
        print(f"⏳ 尝试启动 ollama serve ..." + (f"（模型目录: {models_hint}）" if models_hint else ""))
        if not ensure_ollama_running(args.url, start_if_down=True, models_dir=args.models_dir):
            print(f"❌ 启动失败，请手动运行 `ollama serve` 后重试")
            return 1
        print(f"✅ Ollama 已启动: {args.url}")
    if args.preload:
        return cmd_preload(args)
    st = server_status(args.url)
    print(f"  版本: {st['version'] or '未知'} | 已安装: {', '.join(st['models']) or '(无)'} | 已加载: {', '.join(st['loaded']) or '(无)'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ollama 服务器管理工具（状态/启动/模型预热）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法：", 1)[1].split("模块函数", 1)[0].strip(),
    )
    parser.add_argument("--url", default=OLLAMA_DEFAULT_URL, help=f"Ollama 地址（默认 {OLLAMA_DEFAULT_URL}）")
    parser.add_argument("--model", default=OLLAMA_DEFAULT_MODEL, help=f"模型名（默认 {OLLAMA_DEFAULT_MODEL}）")
    parser.add_argument("--keep-alive", default=OLLAMA_KEEP_ALIVE, help=f"常驻时长（默认 {OLLAMA_KEEP_ALIVE}，-1=永久）")
    parser.add_argument("--models-dir", default=None,
                        help="模型目录（默认自动探测桌面应用配置，如 E:\\ollama）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="查看服务器状态")
    p_status.set_defaults(func=cmd_status)

    p_preload = sub.add_parser("preload", help="预加载模型并常驻")
    p_preload.set_defaults(func=cmd_preload)

    p_serve = sub.add_parser("serve", help="确保服务器运行（必要时拉起）并可选预热")
    p_serve.add_argument("--preload", action="store_true", help="运行后同时预热模型")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
