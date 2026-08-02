"""MCP-facing mapping that reuses the local tool registry and gateway."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from typing import Any
from uuid import uuid4

import mcp.server.stdio
import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel

from ...orchestration.tool_gateway import LocalToolGateway, RunContext
from ...tools.contracts import ToolResult
from ...tools.registry import TOOL_SPECS_V1, ToolSpec


class MCPToolNotFoundError(LookupError):
    """Public error for names outside the MCP detection catalog."""


class DetectionMCPTool(BaseModel):
    """Protocol-neutral description used to build MCP Tool messages."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class DetectionMCPService:
    """Map MCP names to LocalToolGateway without copying tool logic."""

    def __init__(
        self,
        gateway: LocalToolGateway | None = None,
        specs: list[ToolSpec] | None = None,
    ):
        selected = list(TOOL_SPECS_V1 if specs is None else specs)
        self._gateway = gateway or LocalToolGateway(selected)
        self._by_mcp_name = {spec.mcp_name: spec for spec in selected}

    def list_tools(self) -> list[DetectionMCPTool]:
        output_schema = ToolResult.model_json_schema()
        return [
            DetectionMCPTool(
                name=spec.mcp_name,
                description=spec.description,
                input_schema=deepcopy(spec.input_schema),
                output_schema=deepcopy(output_schema),
            )
            for spec in self._by_mcp_name.values()
            if spec.ready
        ]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        run_id: str | None = None,
        call_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        spec = self._by_mcp_name.get(name)
        if spec is None or not spec.ready:
            raise MCPToolNotFoundError("MCP tool is not available")
        context = RunContext(
            run_id=run_id or f"mcp_run_{uuid4().hex}",
            call_id=call_id,
            timeout_seconds=timeout_seconds,
        )
        result = self._gateway.call(spec.name, arguments, context)
        return result.model_dump(mode="json")


def create_detection_server(
    service: DetectionMCPService | None = None,
) -> Server:
    """Create a low-level MCP server from registry-owned JSON Schemas."""

    active_service = service or DetectionMCPService()
    server = Server("implicit-ad-detection-tools")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
                outputSchema=tool.output_schema,
            )
            for tool in active_service.list_tools()
        ]

    @server.call_tool()
    async def call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> mcp_types.CallToolResult:
        try:
            result = active_service.call_tool(name, arguments)
        except MCPToolNotFoundError:
            return mcp_types.CallToolResult(
                isError=True,
                content=[
                    mcp_types.TextContent(
                        type="text",
                        text="MCP tool is not available.",
                    )
                ],
            )
        return mcp_types.CallToolResult(
            content=[
                mcp_types.TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False),
                )
            ],
            structuredContent=result,
            isError=False,
        )

    return server


async def run_stdio() -> None:
    """Run the Detection Tool Server over standard input/output."""

    server = create_detection_server()
    async with mcp.server.stdio.stdio_server() as (
        read_stream,
        write_stream,
    ):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="implicit-ad-detection-tools",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
