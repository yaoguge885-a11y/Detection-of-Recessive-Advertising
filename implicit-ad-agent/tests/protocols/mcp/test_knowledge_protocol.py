import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def _round_trip():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "impad.protocols.mcp.knowledge_server"],
        cwd=PROJECT_ROOT,
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            called = await session.call_tool(
                "knowledge.search_legal_rules",
                arguments={
                    "query": "体验分享、购物链接和广告可识别性",
                    "top_k": 3,
                },
            )
            return listed, called


def test_stdio_knowledge_server_lists_and_returns_guarded_citations():
    listed, called = asyncio.run(_round_trip())

    assert [item.name for item in listed.tools] == [
        "knowledge.search_legal_rules"
    ]
    assert called.isError is False
    assert called.structuredContent is not None
    assert "abstained" in called.structuredContent
    for citation in called.structuredContent["citations"]:
        assert citation["source_path_or_url"].startswith(
            "https://www.samr.gov.cn/"
        )
