"""MCP server for citation-safe retrieval from the official legal corpus."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.server.stdio
import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

from ...contracts import LawEvidence
from ...rag import LegalRetriever, build_default_legal_retriever


class LegalSearchInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class LegalSearchOutput(BaseModel):
    query: str
    abstained: bool
    citations: list[LawEvidence] = Field(default_factory=list)


class KnowledgeMCPService:
    """Protocol-neutral knowledge service used by MCP and local tests."""

    tool_name = "knowledge.search_legal_rules"

    def __init__(self, retriever: LegalRetriever | None = None):
        self._retriever = retriever or build_default_legal_retriever()

    def list_tools(self) -> list[dict[str, Any]]:
        input_schema = LegalSearchInput.model_json_schema()
        input_schema["additionalProperties"] = False
        return [{
            "name": self.tool_name,
            "description": (
                "Retrieve exact, source-versioned advertising-law clauses. "
                "Returns no citations when the retriever abstains."
            ),
            "input_schema": input_schema,
            "output_schema": LegalSearchOutput.model_json_schema(),
        }]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != self.tool_name:
            raise LookupError("Knowledge MCP tool is not available")
        request = LegalSearchInput.model_validate(arguments)
        citations = self._retriever.retrieve(
            request.query,
            top_k=request.top_k,
        )
        return LegalSearchOutput(
            query=request.query,
            abstained=not citations,
            citations=citations,
        ).model_dump(mode="json")


def create_knowledge_server(
    service: KnowledgeMCPService | None = None,
) -> Server:
    active_service = service or KnowledgeMCPService()
    server = Server("implicit-ad-legal-knowledge")

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=item["name"],
                description=item["description"],
                inputSchema=item["input_schema"],
                outputSchema=item["output_schema"],
            )
            for item in active_service.list_tools()
        ]

    @server.call_tool()
    async def call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> mcp_types.CallToolResult:
        try:
            result = active_service.call_tool(name, arguments)
        except (LookupError, ValueError):
            return mcp_types.CallToolResult(
                isError=True,
                content=[mcp_types.TextContent(
                    type="text",
                    text="Knowledge MCP request is invalid or unavailable.",
                )],
            )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False),
            )],
            structuredContent=result,
            isError=False,
        )

    return server


async def run_stdio() -> None:
    server = create_knowledge_server()
    async with mcp.server.stdio.stdio_server() as (
        read_stream,
        write_stream,
    ):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="implicit-ad-legal-knowledge",
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
