import json

import pytest

from impad.security.redaction import (
    REDACTED,
    redact_sensitive_text,
    redact_structure,
)


SECRETS = (
    "cookie-secret-123",
    "set-cookie-secret-234",
    "bearer-secret-456",
    "basic-secret-567",
    "api-secret-789",
    "query-secret-abc",
    "fragment-secret-def",
    "url-password-ghi",
)


def test_redacts_headers_tokens_and_sensitive_url_components():
    raw = (
        "Cookie: sid=cookie-secret-123\n"
        "Set-Cookie: sid=set-cookie-secret-234; HttpOnly\n"
        "Authorization: Bearer bearer-secret-456\n"
        "Basic basic-secret-567\n"
        "api_key=api-secret-789\n"
        "https://user:url-password-ghi@example.test:8443/post"
        "?token=query-secret-abc#fragment-secret-def"
    )

    result = redact_sensitive_text(raw)

    assert all(secret not in result for secret in SECRETS)
    assert "user:" not in result
    assert ":8443" not in result
    assert "?" not in result
    assert "#" not in result
    assert "https://example.test/post" in result


def test_recursive_redaction_is_key_aware_without_destroying_token_usage():
    raw = {
        "cookies": {"sid": "cookie-secret-123"},
        "authorization": "Bearer bearer-secret-456",
        "nested": [
            {"access_token": "query-secret-abc"},
            {"token": "fragment-secret-def"},
        ],
        "token_usage": {"input": 12, "output": 4},
    }

    result = redact_structure(raw)

    assert result["cookies"] == REDACTED
    assert result["authorization"] == REDACTED
    assert result["nested"][0]["access_token"] == REDACTED
    assert result["nested"][1]["token"] == REDACTED
    assert result["token_usage"] == {"input": 12, "output": 4}
    assert all(secret not in json.dumps(result) for secret in SECRETS)


def test_redacts_one_layer_url_encoded_sensitive_url_without_decoding_secrets():
    raw = (
        "https%3A%2F%2Fuser%3Aurl-password-ghi%40example.test%3A8443"
        "%2Fpost%3Ftoken%3Dquery-secret-abc%23fragment-secret-def"
    )

    result = redact_sensitive_text(raw)

    assert result == "https://example.test/post"
    assert all(secret not in result for secret in SECRETS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("comment", "Cookie: sid=cookie-secret-123"),
        ("caption", "Authorization: Basic basic-secret-567"),
        ("quote", "access_token=query-secret-abc"),
        ("data", {"refresh_token": "fragment-secret-def"}),
    ],
)
def test_recursive_redaction_covers_untrusted_nested_artifact_fields(
    field,
    value,
):
    result = redact_structure({field: value})
    serialized = json.dumps(result, ensure_ascii=False)

    assert all(secret not in serialized for secret in SECRETS)


def test_redaction_preserves_scalar_and_tuple_types_and_is_idempotent():
    raw = {
        "count": 3,
        "score": 0.5,
        "ready": True,
        "missing": None,
        "tuple": ("api_key=api-secret-789", 4),
    }

    once = redact_structure(raw)
    twice = redact_structure(once)

    assert twice == once
    assert once["tuple"] == ("api_key=[REDACTED]", 4)
    assert isinstance(once["tuple"], tuple)
    assert once["count"] == 3
    assert once["score"] == 0.5
    assert once["ready"] is True
    assert once["missing"] is None
