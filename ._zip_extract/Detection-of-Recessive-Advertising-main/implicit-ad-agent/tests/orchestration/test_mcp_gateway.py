import asyncio

import pytest

from impad.orchestration import (
    CapabilityContext,
    MCPToolGateway,
    RunContext,
    StdioDetectionMCPClient,
)
from impad.orchestration.tool_gateway import LocalToolGateway


class FakeMCPClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def list_tools(self):
        return {
            "detection.analyze_text_intent",
            "detection.sentiment_curve",
        }

    def call_tool(self, name, arguments):
        if self.fail:
            raise ConnectionError("offline")
        result = LocalToolGateway().call(
            name.removeprefix("detection."),
            arguments,
            RunContext(run_id="remote"),
        )
        return result.model_dump(mode="json")


class SlowStdioClient(StdioDetectionMCPClient):
    async def _request(self, **kwargs):
        await asyncio.sleep(0.05)


def test_mcp_gateway_lists_and_returns_shared_tool_result_contract():
    gateway = MCPToolGateway(client=FakeMCPClient())
    listed = gateway.list_tools(CapabilityContext(
        modalities=frozenset({"text"}),
        sample_counts={"text": 1},
    ))

    assert {item.name for item in listed} == {
        "analyze_text_intent",
        "sentiment_curve",
    }
    result = gateway.call(
        "analyze_text_intent",
        {"text": "品牌合作，限时购买"},
        RunContext(run_id="run_mcp", call_id="call_mcp"),
    )
    assert result.run_id == "run_mcp"
    assert result.call_id == "call_mcp"
    assert result.tool_name == "analyze_text_intent"
    assert gateway.fallback_count == 0


def test_mcp_gateway_falls_back_locally_and_records_degradation():
    gateway = MCPToolGateway(client=FakeMCPClient(fail=True))
    result = gateway.call(
        "analyze_text_intent",
        {"text": "品牌合作，限时购买"},
        RunContext(run_id="run_fallback"),
    )

    assert result.status in {"ok", "degraded"}
    assert gateway.fallback_count == 1
    assert any(
        item.code == "mcp_transport_fallback"
        for item in result.limitations
    )


def test_stdio_timeout_uses_local_fallback_and_records_degradation():
    gateway = MCPToolGateway(
        client=SlowStdioClient(timeout_seconds=0.001),
    )

    result = gateway.call(
        "analyze_text_intent",
        {"text": "品牌合作，限时购买"},
        RunContext(run_id="run_timeout"),
    )

    assert result.status in {"ok", "degraded"}
    assert gateway.fallback_count == 1
    assert any(
        item.code == "mcp_transport_fallback"
        for item in result.limitations
    )


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_stdio_timeout_must_be_positive(timeout_seconds):
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than 0",
    ):
        StdioDetectionMCPClient(timeout_seconds=timeout_seconds)
