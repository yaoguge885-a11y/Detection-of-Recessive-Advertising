"""Fail-closed authorization and validation for remote capabilities."""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError


MAX_REMOTE_RESULT_BYTES = 1024 * 1024
_T = TypeVar("_T")


class RemoteSecurityError(RuntimeError):
    """Base class for stable, secret-free remote security failures."""

    code = "remote_security_error"


class RemoteAuthorizationError(RemoteSecurityError):
    """Raised before a capability outside the active allow-list can run."""

    code = "capability_not_allowed"


class RemoteProtocolViolationError(RemoteSecurityError):
    """Raised when a remote response violates the bounded contract."""

    code = "remote_protocol_violation"


class RemoteTransportTimeout(RemoteSecurityError, TimeoutError):
    """Raised when a remote call exceeds its approved deadline."""

    code = "remote_timeout"


class RemoteCapabilityPolicy(BaseModel):
    """Immutable limits shared by MCP and future A2A transports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol: Literal["mcp", "a2a"]
    allowed_names: frozenset[str]
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_result_bytes: int = Field(
        default=MAX_REMOTE_RESULT_BYTES,
        ge=1,
        le=MAX_REMOTE_RESULT_BYTES,
    )


class RemoteResultEnvelope(BaseModel):
    """Protocol-neutral identity plus opaque, size-bounded result data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_name: str = Field(min_length=1)
    payload: dict[str, Any]


def authorize_remote_capability(
    name: str,
    policy: RemoteCapabilityPolicy,
) -> None:
    """Reject a call not granted by the caller's exact active allow-list."""

    if name not in policy.allowed_names:
        raise RemoteAuthorizationError(
            "Remote capability is not authorized for this run."
        )


def invoke_with_deadline(
    operation: Callable[[], _T],
    policy: RemoteCapabilityPolicy,
) -> _T:
    """Wait for a synchronous transport only until the policy deadline."""

    outcome: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcome.put(("result", operation()))
        except Exception as exc:
            outcome.put(("error", exc))

    worker = threading.Thread(
        target=invoke,
        name=f"{policy.protocol}-remote-call",
        daemon=True,
    )
    worker.start()
    worker.join(policy.timeout_seconds)
    if worker.is_alive():
        raise RemoteTransportTimeout(
            "Remote transport exceeded its approved deadline."
        )

    kind, value = outcome.get_nowait()
    if kind == "error":
        raise value
    return value  # type: ignore[return-value]


def _bounded_json_bytes(raw: object, policy: RemoteCapabilityPolicy) -> bytes:
    try:
        encoded = json.dumps(
            raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RemoteProtocolViolationError(
            "Remote result is not valid bounded JSON."
        ) from exc
    if len(encoded) > policy.max_result_bytes:
        raise RemoteProtocolViolationError(
            "Remote result exceeds the approved size limit."
        )
    return encoded


def validate_remote_result(
    expected_name: str,
    raw: object,
    policy: RemoteCapabilityPolicy,
) -> RemoteResultEnvelope:
    """Validate authorization, byte size, schema, and exact remote identity."""

    authorize_remote_capability(expected_name, policy)
    _bounded_json_bytes(raw, policy)
    try:
        envelope = RemoteResultEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise RemoteProtocolViolationError(
            "Remote result does not match the approved contract."
        ) from exc
    if envelope.capability_name != expected_name:
        raise RemoteProtocolViolationError(
            "Remote result identity does not match the approved capability."
        )
    return envelope
