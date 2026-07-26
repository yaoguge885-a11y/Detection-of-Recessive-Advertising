import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from impad.orchestration.tool_gateway import LocalToolGateway, RunContext
from impad.tools.contracts import ToolResult


PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def _round_trip():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "impad.protocols.mcp.detection_server"],
        cwd=PROJECT_ROOT,
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            called = await session.call_tool(
                "detection.analyze_text_intent",
                arguments={"text": "品牌合作，限时抢购"},
            )
            unknown = await session.call_tool(
                "detection.not_registered",
                arguments={},
            )
            invalid = await session.call_tool(
                "detection.analyze_text_intent",
                arguments={"text": ""},
            )
            return listed, called, unknown, invalid


def test_stdio_protocol_lists_and_calls_real_detection_tools():
    listed, called, _, _ = asyncio.run(_round_trip())

    assert len(listed.tools) == 7
    assert "detection.analyze_text_intent" in {
        tool.name for tool in listed.tools
    }
    assert called.isError is False
    envelope = ToolResult.model_validate(called.structuredContent)
    assert envelope.tool_name == "analyze_text_intent"
    assert envelope.status in {"ok", "degraded"}


def test_stdio_protocol_maps_unknown_and_invalid_calls_to_public_errors():
    _, _, unknown, invalid = asyncio.run(_round_trip())

    assert unknown.isError is True
    assert unknown.content[0].text == "MCP tool is not available."
    assert invalid.isError is True
    assert "ValidationError" not in invalid.content[0].text


def test_mcp_result_matches_local_gateway_contract_for_same_input():
    _, called, _, _ = asyncio.run(_round_trip())
    mcp_result = ToolResult.model_validate(called.structuredContent)
    local_result = LocalToolGateway().call(
        "analyze_text_intent",
        {"text": "品牌合作，限时抢购"},
        RunContext(run_id="run_local_parity"),
    )

    assert mcp_result.tool_name == local_result.tool_name
    assert mcp_result.tool_version == local_result.tool_version
    assert mcp_result.status == local_result.status
    assert mcp_result.score == local_result.score
    assert mcp_result.evidence == local_result.evidence
    assert mcp_result.payload == local_result.payload
    assert mcp_result.model_info == local_result.model_info
