"""History expert group backed by the shared topic-drift tool."""
from __future__ import annotations

from ..state import AdCheckState
from .runtime import execute_agent_group


def behavior_agent(state: AdCheckState) -> AdCheckState:
    return execute_agent_group(
        state,
        agent_name="behavior",
        tool_names={"topic_drift"},
    )
