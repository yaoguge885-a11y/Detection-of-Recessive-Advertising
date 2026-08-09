import time

import pytest
from pydantic import ValidationError

from impad.orchestration.remote_policy import (
    MAX_REMOTE_RESULT_BYTES,
    RemoteAuthorizationError,
    RemoteCapabilityPolicy,
    RemoteProtocolViolationError,
    RemoteResultEnvelope,
    RemoteTransportTimeout,
    authorize_remote_capability,
    invoke_with_deadline,
    validate_remote_result,
)


def _a2a_policy(**updates):
    values = {
        "protocol": "a2a",
        "allowed_names": frozenset({"analyze_text_intent"}),
        "timeout_seconds": 0.1,
    }
    values.update(updates)
    return RemoteCapabilityPolicy(**values)


def test_a2a_policy_rejects_ungranted_capability_without_echoing_name():
    requested = "system.export_secrets"

    with pytest.raises(RemoteAuthorizationError) as caught:
        authorize_remote_capability(requested, _a2a_policy())

    assert caught.value.code == "capability_not_allowed"
    assert requested not in str(caught.value)


def test_a2a_deadline_stops_waiting_and_returns_safe_timeout_error():
    policy = _a2a_policy(timeout_seconds=0.001)

    with pytest.raises(RemoteTransportTimeout) as caught:
        invoke_with_deadline(lambda: time.sleep(0.05), policy)

    assert caught.value.code == "remote_timeout"
    assert "analyze_text_intent" not in str(caught.value)


def test_a2a_result_rejects_forged_capability_identity():
    raw = {
        "capability_name": "system.exec",
        "payload": {"status": "ok"},
    }

    with pytest.raises(RemoteProtocolViolationError) as caught:
        validate_remote_result("analyze_text_intent", raw, _a2a_policy())

    assert caught.value.code == "remote_protocol_violation"
    assert "system.exec" not in str(caught.value)


def test_a2a_result_rejects_malformed_envelope_without_echoing_payload():
    raw = {"unexpected": "raw-secret-payload"}

    with pytest.raises(RemoteProtocolViolationError) as caught:
        validate_remote_result("analyze_text_intent", raw, _a2a_policy())

    assert caught.value.code == "remote_protocol_violation"
    assert "raw-secret-payload" not in str(caught.value)


def test_a2a_result_rejects_oversized_payload_before_acceptance():
    raw = {
        "capability_name": "analyze_text_intent",
        "payload": {"text": "x" * MAX_REMOTE_RESULT_BYTES},
    }

    with pytest.raises(RemoteProtocolViolationError) as caught:
        validate_remote_result("analyze_text_intent", raw, _a2a_policy())

    assert caught.value.code == "remote_protocol_violation"


def test_a2a_result_accepts_exact_identity_and_bounded_payload():
    raw = {
        "capability_name": "analyze_text_intent",
        "payload": {"status": "ok"},
    }

    assert validate_remote_result(
        "analyze_text_intent",
        raw,
        _a2a_policy(),
    ) == RemoteResultEnvelope.model_validate(raw)


@pytest.mark.parametrize("timeout_seconds", [None, 0, -1])
def test_remote_policy_requires_positive_timeout(timeout_seconds):
    with pytest.raises(ValidationError):
        _a2a_policy(timeout_seconds=timeout_seconds)
