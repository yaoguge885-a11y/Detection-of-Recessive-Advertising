"""Vision expert group backed by the shared tool runtime."""
from __future__ import annotations

from ..state import AdCheckState
from .runtime import execute_agent_group


_TOOLS = {
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
}


def vision_agent(state: AdCheckState) -> AdCheckState:
    return execute_agent_group(
        state,
        agent_name="vision",
        tool_names=_TOOLS,
    )
