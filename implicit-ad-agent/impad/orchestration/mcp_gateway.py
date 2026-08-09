"""Detection-tool MCP client gateway with a contract-preserving local fallback."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

from ..tools.contracts import ToolLimitation, ToolResult
from ..tools.registry import TOOL_SPECS_V1, ToolSpec
from .remote_policy import (
    MAX_REMOTE_RESULT_BYTES,
    RemoteAuthorizationError,
    RemoteCapabilityPolicy,
    RemoteProtocolViolationError,
    RemoteSecurityError,
    RemoteTransportTimeout,
    authorize_remote_capability,
    invoke_with_deadline,
    validate_remote_result,
)
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


REMOTE_TRANSPORT_ERRORS = (
    RemoteTransportTimeout,
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
    EOFError,
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
        try:
            return asyncio.run(asyncio.wait_for(
                self._request(**kwargs),
                timeout=self.timeout_seconds,
            ))
        except asyncio.TimeoutError as exc:
            raise RemoteTransportTimeout(
                "Remote transport exceeded its approved deadline."
            ) from exc

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
            raise RemoteProtocolViolationError(
                "Remote result does not match the approved contract."
            )
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
                    catalog_policy = RemoteCapabilityPolicy(
                        protocol="mcp",
                        allowed_names=frozenset(
                            spec.mcp_name for spec in self._specs.values()
                        ),
                    )
                    remote_names = invoke_with_deadline(
                        self._client.list_tools,
                        catalog_policy,
                    )
                    self._remote_names = self._validate_remote_catalog(
                        remote_names
                    )
                except REMOTE_TRANSPORT_ERRORS:
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
        allowed_tools = run.allowed_tools
        if allowed_tools is None:
            allowed_tools = frozenset(
                item.name for item in self._specs.values() if item.ready
            )
        policy = RemoteCapabilityPolicy(
            protocol="mcp",
            allowed_names=frozenset(
                item.mcp_name
                for item in self._specs.values()
                if item.name in allowed_tools
            ),
            timeout_seconds=(
                run.timeout_seconds or spec.default_timeout_seconds
            ),
        )
        authorize_remote_capability(spec.mcp_name, policy)
        validated = validate_tool_arguments(spec.tool.args_schema, arguments)
        normalized = validated.model_dump(mode="json")
        try:
            raw = invoke_with_deadline(
                lambda: self._client.call_tool(spec.mcp_name, normalized),
                policy,
            )
            envelope = validate_remote_result(
                spec.mcp_name,
                {
                    "capability_name": spec.mcp_name,
                    "payload": raw,
                },
                policy,
            )
            try:
                result = ToolResult.model_validate(envelope.payload)
            except Exception as exc:
                raise RemoteProtocolViolationError(
                    "Remote result does not match the approved contract."
                ) from exc
            if result.tool_name != spec.name:
                raise RemoteProtocolViolationError(
                    "Remote result identity does not match the approved capability."
                )
            return result.model_copy(update={
                "run_id": run.run_id,
                "call_id": run.call_id or result.call_id,
                "input_fingerprint": input_fingerprint(normalized),
            })
        except REMOTE_TRANSPORT_ERRORS:
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
        except (RemoteAuthorizationError, RemoteProtocolViolationError):
            raise
        except RemoteSecurityError:
            raise
        except Exception as exc:
            raise RemoteProtocolViolationError(
                "Remote result does not match the approved contract."
            ) from exc

    @staticmethod
    def _validate_remote_catalog(raw: object) -> set[str]:
        try:
            encoded = json.dumps(
                sorted(raw) if isinstance(raw, set) else raw,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError) as exc:
            raise RemoteProtocolViolationError(
                "Remote tool catalog is not valid bounded JSON."
            ) from exc
        if len(encoded) > MAX_REMOTE_RESULT_BYTES:
            raise RemoteProtocolViolationError(
                "Remote tool catalog exceeds the approved size limit."
            )
        if not isinstance(raw, set) or not all(
            isinstance(name, str) and name for name in raw
        ):
            raise RemoteProtocolViolationError(
                "Remote tool catalog does not match the approved contract."
            )
        return set(raw)
