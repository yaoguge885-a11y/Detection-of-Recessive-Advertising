"""Runtime orchestration boundaries shared by local and remote execution."""

from .adequacy import EvidenceAdequacyResult, assess_evidence_adequacy
from .capability_planner import (
    CapabilityPlan,
    CapabilityPlanner,
    CapabilityPlanningPolicy,
    SkippedTool,
)
from .evidence_adapters import (
    build_evidence_bundle,
    evidence_items_from_tool_result,
)
from .function_calling import (
    FunctionCallingPolicy,
    FunctionCallingResult,
    FunctionCallRequest,
    FunctionCallTrace,
    RestrictedFunctionCaller,
)
from .judgment import (
    assess_commercial_intent,
    assess_disclosure,
    build_verdict_report,
)
from .post_tools import (
    capability_context_from_post,
    execute_post_tools,
    execute_post_tools_parallel,
    function_calls_from_post,
)
from .tool_gateway import (
    CapabilityContext,
    LocalToolGateway,
    RunContext,
    ToolGateway,
    UnavailableToolError,
    UnknownToolError,
)
from .mcp_gateway import MCPToolGateway, StdioDetectionMCPClient
from .remote_policy import (
    RemoteAuthorizationError,
    RemoteCapabilityPolicy,
    RemoteProtocolViolationError,
    RemoteResultEnvelope,
    RemoteSecurityError,
    RemoteTransportTimeout,
    authorize_remote_capability,
    invoke_with_deadline,
    validate_remote_result,
)
from .tracing import InMemoryTraceRecorder, RunEvent, RunTrace, attach_trace

__all__ = [
    "CapabilityContext",
    "CapabilityPlan",
    "CapabilityPlanner",
    "CapabilityPlanningPolicy",
    "capability_context_from_post",
    "EvidenceAdequacyResult",
    "assess_evidence_adequacy",
    "assess_commercial_intent",
    "assess_disclosure",
    "build_verdict_report",
    "build_evidence_bundle",
    "evidence_items_from_tool_result",
    "execute_post_tools",
    "execute_post_tools_parallel",
    "FunctionCallingPolicy",
    "FunctionCallingResult",
    "FunctionCallRequest",
    "FunctionCallTrace",
    "function_calls_from_post",
    "InMemoryTraceRecorder",
    "LocalToolGateway",
    "MCPToolGateway",
    "RemoteAuthorizationError",
    "RemoteCapabilityPolicy",
    "RemoteProtocolViolationError",
    "RemoteResultEnvelope",
    "RemoteSecurityError",
    "RemoteTransportTimeout",
    "RestrictedFunctionCaller",
    "RunEvent",
    "RunContext",
    "RunTrace",
    "SkippedTool",
    "StdioDetectionMCPClient",
    "ToolGateway",
    "UnavailableToolError",
    "UnknownToolError",
    "authorize_remote_capability",
    "attach_trace",
    "invoke_with_deadline",
    "validate_remote_result",
]
