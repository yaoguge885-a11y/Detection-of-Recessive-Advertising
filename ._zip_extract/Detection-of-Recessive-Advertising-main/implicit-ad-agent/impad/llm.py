"""厂商无关的 LLM 客户端：走 OpenAI 兼容端点。

改 .env 里的 OPENAI_BASE_URL / LLM_MODEL 就能在 DeepSeek / 通义千问 / OpenAI 间切换，
代码不用动。

Ollama 本地推理（co-pilot-auto-judge 分置信度自动判断系统）：
  get_ollama_llm() 返回指向本地 Ollama 的 OpenAI 兼容客户端，
  也可用 impad/tools 之外的 data-tooling/annotation/auto_judge.py 直接走
  Ollama 原生 /api/chat（JSON 模式更可靠）。
"""
from __future__ import annotations
from langchain_openai import ChatOpenAI
from .config import settings


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=temperature,
    )


def get_ollama_llm(model: str = "qwen3.5:9b",
                   url: str = "http://localhost:11434",
                   temperature: float = 0.0) -> ChatOpenAI:
    """Ollama 本地推理客户端工厂（OpenAI 兼容端点 /v1）。

    Args:
        model: Ollama 模型名（默认 qwen3.5:9b，多模态模型，自动判断用文本通道）
        url: Ollama 服务地址（默认本地 11434 端口）
        temperature: 采样温度，自动判断用 0.0 保持确定性

    Returns:
        ChatOpenAI 实例，指向本地 Ollama。
    """
    return ChatOpenAI(
        model=model,
        api_key="ollama",  # Ollama 本地端点不需要真实密钥
        base_url=f"{url.rstrip('/')}/v1",
        temperature=temperature,
    )
