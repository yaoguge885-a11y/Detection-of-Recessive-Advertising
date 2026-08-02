"""Text and comment expert group backed by the shared tool runtime."""
from __future__ import annotations

from ..state import AdCheckState
from .runtime import execute_agent_group


_TOOLS = {
    "analyze_text_intent",
    "sentiment_curve",
    "comment_anomaly",
}


def nlp_agent(state: AdCheckState) -> AdCheckState:
    return execute_agent_group(
        state,
        agent_name="nlp",
        tool_names=_TOOLS,
    )
