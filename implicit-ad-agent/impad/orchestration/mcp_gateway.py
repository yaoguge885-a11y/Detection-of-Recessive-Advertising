"""Detection-tool MCP client gateway with a contract-preserving local fallback."""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

from ..tools.contracts import ToolLimitation, ToolResult
from ..tools.registry import TOOL_SPECS_V1, ToolSpec
from .tool_gateway import (
    CapabilityContext,
    LocalToolGateway,
    RunContext,
    ToolGateway,
    UnknownToolError,
    input_fingerprint,
    tool_eligibility_issues,
    validate_tool_arguments,
)


class DetectionMCPClient(Protocol):
    """Small synchronous boundary used by MCPToolGateway."""

    def list_tools(self) -> set[str]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...


class StdioDetectionMCPClient:
    """Start the repository Detection MCP server for each protocol request."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        project_root: Path | None = None,
        timeout_seconds: float = 30.0,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        self.python_executable = python_executable or sys.executable
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.timeout_seconds = timeout_seconds

    async def _request(
        self,
        *,
        list_only: bool,
        name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        parameters = StdioServerParameters(
            command=self.python_executable,
            args=["-m", "impad.protocols.mcp.detection_server"],
            cwd=self.project_root,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                if list_only:
                    return await session.list_tools()
                return await session.call_tool(
                    name or "",
                    arguments=arguments or {},
                )

    def _run_request(self, **kwargs):
        return asyncio.run(asyncio.wait_for(
            self._request(**kwargs),
            timeout=self.timeout_seconds,
        ))

    def list_tools(self) -> set[str]:
        response = self._run_request(list_only=True)
        return {tool.name for tool in response.tools}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._run_request(
            list_only=False,
            name=name,
            arguments=arguments,
        )
        if response.isError or response.structuredContent is None:
            raise RuntimeError("Detection MCP call failed")
        return dict(response.structuredContent)


class MCPToolGateway:
    """Invoke registered tools through MCP and fall back locally on failure."""

    def __init__(
        self,
        client: DetectionMCPClient | None = None,
        *,
        fallback: ToolGateway | None = None,
        specs: list[ToolSpec] | None = None,
    ):
        selected = list(TOOL_SPECS_V1 if specs is None else specs)
        self._specs = {spec.name: spec for spec in selected}
        self._client = client or StdioDetectionMCPClient()
        self._fallback = fallback or LocalToolGateway(selected)
        self._fallback_count = 0
        self._remote_names: set[str] | None = None
        self._lock = threading.Lock()

    @property
    def fallback_count(self) -> int:
        with self._lock:
            return self._fallback_count

    def list_tools(self, context: CapabilityContext) -> list[ToolSpec]:
        with self._lock:
            if self._remote_names is None:
                try:
                    self._remote_names = self._client.list_tools()
                except Exception:
                    self._remote_names = {
                        spec.mcp_name
                        for spec in self._specs.values()
                        if spec.ready
                    }
            remote_names = set(self._remote_names)
        return [
            spec
            for spec in self._specs.values()
            if spec.mcp_name in remote_names
            and not tool_eligibility_issues(spec, context)
        ]

    def call(
        self,
        name: str,
        arguments: dict,
        run: RunContext,
    ) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownToolError(f"Tool is not registered: {name}")
        validated = validate_tool_arguments(spec.tool.args_schema, arguments)
        normalized = validated.model_dump(mode="json")
        try:
            raw = self._client.call_tool(spec.mcp_name, normalized)
            result = ToolResult.model_validate(raw)
            return result.model_copy(update={
                "run_id": run.run_id,
                "call_id": run.call_id or result.call_id,
                "input_fingerprint": input_fingerprint(normalized),
            })
        except Exception:
            with self._lock:
                self._fallback_count += 1
            result = self._fallback.call(name, normalized, run)
            limitation = ToolLimitation(
                kind="evidence",
                code="mcp_transport_fallback",
                message="MCP unavailable; the same registered tool ran locally.",
                source=name,
            )
            return result.model_copy(update={
                "warnings": [
                    *result.warnings,
                    "MCP unavailable; local fallback used.",
                ],
                "limitations": [*result.limitations, limitation],
            })
