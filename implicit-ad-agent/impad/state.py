"""Structured LangGraph state for the P2.5 evidence flow."""
from __future__ import annotations

from typing import Any, TypedDict

from .contracts import (
    CaptureStatus,
    EvidenceBundle,
    PostRecord,
    RunMetadata,
    VerdictReport,
)
from .orchestration import (
    CapabilityPlan,
    FunctionCallTrace,
    RunEvent,
)
from .tools.contracts import ToolResult


class AdCheckState(TypedDict, total=False):
    """Shared state; structured contracts are authoritative."""

    post: dict | PostRecord
    post_record: PostRecord
    capture_status: CaptureStatus
    capability_plan: CapabilityPlan
    plan: list[str]
    tool_results: list[ToolResult]
    function_traces: list[FunctionCallTrace]
    run_events: list[RunEvent]
    run_metadata: RunMetadata
    evidence_bundle: EvidenceBundle
    verdict_report: VerdictReport
    agent_outputs: dict[str, dict[str, Any]]
    tool_gateway: Any
    runtime_mode: str

    # Compatibility presentation fields. They are derived, not authoritative.
    agent_votes: dict[str, dict[str, Any]]
    keyword_weights: dict[str, float]
    evidence: list[str]
    verdict: str
    confidence: float
    report: str
