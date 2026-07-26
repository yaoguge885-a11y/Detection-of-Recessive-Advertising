"""Deterministic capability planning over the registered P2 tools."""
from __future__ import annotations

from copy import deepcopy
from typing import Sequence

from pydantic import BaseModel, Field

from ..tools.registry import TOOL_SPECS_V1, ToolSpec
from .tool_gateway import CapabilityContext, tool_eligibility_issues


class CapabilityPlanningPolicy(BaseModel):
    """Run-level caps applied to the deterministic tool plan."""

    max_calls: int = Field(default=8, ge=1, le=64)
    max_tool_timeout_seconds: float | None = Field(default=None, gt=0)


class SkippedTool(BaseModel):
    """A tool omitted from the plan with machine-readable reasons."""

    tool_name: str
    reasons: list[str]


class CapabilityPlan(BaseModel):
    """Auditable output consumed by Function Calling and execution nodes."""

    available_tools: list[str]
    skipped_tools: list[SkippedTool]
    function_definitions: list[dict]
    call_budget: int = Field(ge=0)
    tool_timeouts: dict[str, float]
    parallel_tools: list[str]
    serial_tools: list[str]


class CapabilityPlanner:
    """Build stable plans without an LLM or a platform-specific post model."""

    def __init__(self, specs: Sequence[ToolSpec] | None = None):
        self._specs = list(TOOL_SPECS_V1 if specs is None else specs)

    def plan(
        self,
        context: CapabilityContext,
        policy: CapabilityPlanningPolicy | None = None,
    ) -> CapabilityPlan:
        active_policy = policy or CapabilityPlanningPolicy()
        available: list[ToolSpec] = []
        skipped: list[SkippedTool] = []

        for spec in self._specs:
            issues = tool_eligibility_issues(spec, context)
            if issues:
                skipped.append(SkippedTool(
                    tool_name=spec.name,
                    reasons=issues,
                ))
            else:
                available.append(spec)

        timeouts = {}
        for spec in available:
            timeout = spec.default_timeout_seconds
            if active_policy.max_tool_timeout_seconds is not None:
                timeout = min(
                    timeout,
                    active_policy.max_tool_timeout_seconds,
                )
            timeouts[spec.name] = timeout

        return CapabilityPlan(
            available_tools=[spec.name for spec in available],
            skipped_tools=skipped,
            function_definitions=[
                deepcopy(spec.function_calling)
                for spec in available
            ],
            call_budget=active_policy.max_calls if available else 0,
            tool_timeouts=timeouts,
            parallel_tools=[
                spec.name for spec in available if spec.allow_parallel
            ],
            serial_tools=[
                spec.name for spec in available if not spec.allow_parallel
            ],
        )
