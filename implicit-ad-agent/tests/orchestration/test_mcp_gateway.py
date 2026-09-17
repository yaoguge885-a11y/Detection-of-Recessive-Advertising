import asyncio

import pytest

from impad.orchestration import (
    CapabilityContext,
    MCPToolGateway,
    RemoteAuthorizationError,
    RemoteProtocolViolationError,
    RunContext,
    StdioDetectionMCPClient,
)
from impad.orchestration.remote_policy import MAX_REMOTE_RESULT_BYTES
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


class CountingFallback(LocalToolGateway):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def call(self, name, arguments, run):
        self.calls += 1
        return super().call(name, arguments, run)


class RecordingMCPClient(FakeMCPClient):
    def __init__(self):
        super().__init__()
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return super().call_tool(name, arguments)


class ForgedResultMCPClient(FakeMCPClient):
    def call_tool(self, name, arguments):
        result = super().call_tool(name, arguments)
        result["tool_name"] = "system.exec"
        return result


class MalformedResultMCPClient(FakeMCPClient):
    def call_tool(self, name, arguments):
        return {"tool_name": name}


class OversizedResultMCPClient(FakeMCPClient):
    def call_tool(self, name, arguments):
        result = super().call_tool(name, arguments)
        result["payload"] = {"data": "x" * MAX_REMOTE_RESULT_BYTES}
        return result


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


def test_mcp_gateway_rejects_ungranted_call_before_remote_or_fallback():
    client = RecordingMCPClient()
    fallback = CountingFallback()
    gateway = MCPToolGateway(client=client, fallback=fallback)

    with pytest.raises(RemoteAuthorizationError) as caught:
        gateway.call(
            "analyze_text_intent",
            {"unexpected_secret_field": "must-not-be-validated-first"},
            RunContext(
                run_id="run_denied",
                allowed_tools=frozenset({"sentiment_curve"}),
            ),
        )

    assert caught.value.code == "capability_not_allowed"
    assert client.calls == []
    assert fallback.calls == 0
    assert gateway.fallback_count == 0


@pytest.mark.parametrize(
    "client",
    [ForgedResultMCPClient(), MalformedResultMCPClient()],
)
def test_mcp_gateway_fails_closed_on_forged_or_malformed_result(client):
    fallback = CountingFallback()
    gateway = MCPToolGateway(client=client, fallback=fallback)

    with pytest.raises(RemoteProtocolViolationError) as caught:
        gateway.call(
            "analyze_text_intent",
            {"text": "品牌合作，限时购买"},
            RunContext(
                run_id="run_protocol_violation",
                allowed_tools=frozenset({"analyze_text_intent"}),
            ),
        )

    assert caught.value.code == "remote_protocol_violation"
    assert fallback.calls == 0
    assert gateway.fallback_count == 0


def test_mcp_gateway_fails_closed_on_oversized_result():
    fallback = CountingFallback()
    gateway = MCPToolGateway(
        client=OversizedResultMCPClient(),
        fallback=fallback,
    )

    with pytest.raises(RemoteProtocolViolationError):
        gateway.call(
            "analyze_text_intent",
            {"text": "品牌合作，限时购买"},
            RunContext(
                run_id="run_oversized",
                allowed_tools=frozenset({"analyze_text_intent"}),
            ),
        )

    assert fallback.calls == 0
    assert gateway.fallback_count == 0


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
