"""Stable gateway for listing and invoking registered analysis tools."""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from typing import Protocol, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from ..tools.contracts import ToolLimitation, ToolResult
from ..tools.registry import (
    TOOL_SPECS_V1,
    ToolModality,
    ToolSpec,
)


class CapabilityContext(BaseModel):
    """Modalities and sample counts available to one analysis run."""

    modalities: frozenset[ToolModality] = Field(default_factory=frozenset)
    sample_counts: dict[str, int] = Field(default_factory=dict)


class RunContext(BaseModel):
    """Identifiers and per-call runtime overrides."""

    run_id: str = Field(min_length=1)
    call_id: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class UnknownToolError(LookupError):
    """Raised when a caller asks for a tool outside the registry."""


class UnavailableToolError(RuntimeError):
    """Raised when a registered tool is not ready for execution."""


class UnexpectedToolArgumentsError(ValueError):
    """Raised when a tool call contains fields outside its input contract."""


def validate_tool_arguments(args_schema, arguments: dict) -> BaseModel:
    unknown = sorted(set(arguments) - set(args_schema.model_fields))
    if unknown:
        raise UnexpectedToolArgumentsError(
            "Unexpected tool arguments: " + ", ".join(unknown)
        )
    return args_schema.model_validate(arguments)


class ToolGateway(Protocol):
    """Execution boundary shared by local and future MCP gateways."""

    def list_tools(self, context: CapabilityContext) -> list[ToolSpec]:
        """List ready tools supported by the available input capabilities."""

    def call(
        self,
        name: str,
        arguments: dict,
        run: RunContext,
    ) -> ToolResult:
        """Validate and invoke one tool, returning the shared result envelope."""


class _ToolTimeoutError(TimeoutError):
    pass


def tool_eligibility_issues(
    spec: ToolSpec,
    context: CapabilityContext,
) -> list[str]:
    """Explain why a tool cannot run with the available input capabilities."""

    issues = []
    if not spec.ready:
        issues.append("tool_not_ready")
    missing = sorted(spec.required_modalities - context.modalities)
    issues.extend(f"missing_modality:{item}" for item in missing)
    for kind, minimum in spec.minimum_samples.items():
        if kind not in context.modalities:
            continue
        observed = context.sample_counts.get(kind, 0)
        if observed < minimum:
            issues.append(
                f"insufficient_samples:{kind}:{observed}<{minimum}"
            )
    return issues


def input_fingerprint(arguments: dict) -> str:
    canonical = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _invoke_with_timeout(spec: ToolSpec, arguments: dict, timeout_seconds: float):
    outcome: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcome.put(("result", spec.tool.invoke(arguments)))
        except Exception as exc:
            outcome.put(("error", exc))

    worker = threading.Thread(
        target=invoke,
        name=f"tool-{spec.name}",
        daemon=True,
    )
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise _ToolTimeoutError

    kind, value = outcome.get_nowait()
    if kind == "error":
        raise value
    return value


class LocalToolGateway:
    """Invoke registered LangChain tools in the current Python process."""

    def __init__(self, specs: Sequence[ToolSpec] | None = None):
        selected = list(TOOL_SPECS_V1 if specs is None else specs)
        self._specs = {spec.name: spec for spec in selected}

    def list_tools(self, context: CapabilityContext) -> list[ToolSpec]:
        return [
            spec
            for spec in self._specs.values()
            if not tool_eligibility_issues(spec, context)
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
        if not spec.ready:
            raise UnavailableToolError(f"Tool is not ready: {name}")

        validated = validate_tool_arguments(
            spec.tool.args_schema,
            arguments,
        )
        validated_arguments = validated.model_dump(mode="json")
        fingerprint = input_fingerprint(validated_arguments)
        call_id = run.call_id or f"call_{uuid4().hex}"
        timeout_seconds = run.timeout_seconds or spec.default_timeout_seconds
        started = time.perf_counter()

        try:
            raw_result = _invoke_with_timeout(
                spec,
                validated_arguments,
                timeout_seconds,
            )
            result = ToolResult.model_validate(raw_result)
        except _ToolTimeoutError:
            return self._error_result(
                spec=spec,
                run=run,
                call_id=call_id,
                fingerprint=fingerprint,
                started=started,
                error_code="tool_timeout",
                retryable=True,
                warning="Local tool execution exceeded its configured timeout.",
                limitation="No evidence was produced before the deadline.",
            )
        except Exception as exc:
            return self._error_result(
                spec=spec,
                run=run,
                call_id=call_id,
                fingerprint=fingerprint,
                started=started,
                error_code="tool_execution_error",
                retryable=False,
                warning=f"Local tool execution failed ({type(exc).__name__}).",
                limitation="The tool failed before producing validated evidence.",
            )

        return result.model_copy(update={
            "tool_version": spec.version,
            "call_id": call_id,
            "run_id": run.run_id,
            "latency_ms": self._latency_ms(started),
            "input_fingerprint": fingerprint,
        })

    @staticmethod
    def _latency_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

    def _error_result(
        self,
        *,
        spec: ToolSpec,
        run: RunContext,
        call_id: str,
        fingerprint: str,
        started: float,
        error_code: str,
        retryable: bool,
        warning: str,
        limitation: str,
    ) -> ToolResult:
        return ToolResult(
            tool_name=spec.name,
            tool_version=spec.version,
            status="error",
            call_id=call_id,
            run_id=run.run_id,
            latency_ms=self._latency_ms(started),
            error_code=error_code,
            retryable=retryable,
            input_fingerprint=fingerprint,
            warnings=[warning],
            limitations=[ToolLimitation(
                kind="evidence",
                code=error_code,
                message=limitation,
                source=spec.name,
            )],
        )
