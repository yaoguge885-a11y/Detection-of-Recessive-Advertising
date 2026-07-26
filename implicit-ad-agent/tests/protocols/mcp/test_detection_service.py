import json

import pytest

from impad.protocols.mcp.detection_server import (
    DetectionMCPService,
    MCPToolNotFoundError,
)
from impad.tools.contracts import ToolResult
from impad.tools.registry import TOOL_SPEC_BY_NAME


def test_service_lists_all_seven_registry_tools_with_contract_schemas():
    tools = DetectionMCPService().list_tools()

    assert len(tools) == 7
    assert len({tool.name for tool in tools}) == 7
    by_name = {tool.name: tool for tool in tools}
    intent = by_name["detection.analyze_text_intent"]
    spec = TOOL_SPEC_BY_NAME["analyze_text_intent"]
    assert intent.input_schema == spec.input_schema
    assert intent.output_schema == ToolResult.model_json_schema()
    json.dumps([tool.model_dump(mode="json") for tool in tools])


def test_service_calls_real_local_gateway_and_returns_tool_result():
    result = DetectionMCPService().call_tool(
        "detection.analyze_text_intent",
        {"text": "品牌合作，限时抢购"},
        run_id="run_mcp_service",
        call_id="call_mcp_service",
    )
    envelope = ToolResult.model_validate(result)

    assert envelope.tool_name == "analyze_text_intent"
    assert envelope.run_id == "run_mcp_service"
    assert envelope.call_id == "call_mcp_service"
    assert envelope.status in {"ok", "degraded"}


def test_service_rejects_unknown_mcp_name_without_registry_details():
    with pytest.raises(MCPToolNotFoundError, match="MCP tool is not available"):
        DetectionMCPService().call_tool(
            "detection.not_registered",
            {},
            run_id="run_unknown",
        )
