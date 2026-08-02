import json

import pytest
from pydantic import ValidationError

from impad.tools.contracts import ToolLimitation, ToolResult
from impad.tools.registry import TOOLS_V1, TOOL_READINESS


def test_registry_has_unique_structured_tools():
    names = [item.name for item in TOOLS_V1]
    assert len(names) == len(set(names)) == 7
    assert all(item.description for item in TOOLS_V1)
    assert all(item.args_schema is not None for item in TOOLS_V1)
    assert all(TOOL_READINESS[name] for name in names)


def test_common_result_is_json_serializable():
    result = ToolResult(tool_name="sample", status="skipped")
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_common_result_accepts_optional_runtime_metadata():
    result = ToolResult(
        tool_name="sample",
        status="error",
        call_id="call_1",
        run_id="run_1",
        latency_ms=12,
        error_code="tool_timeout",
        retryable=True,
        input_fingerprint="sha256:abc",
        limitations=[ToolLimitation(
            kind="evidence",
            code="tool_timeout",
            message="No evidence was produced before the deadline.",
        )],
    )

    assert result.limitations[0].kind == "evidence"
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_common_result_rejects_negative_latency():
    with pytest.raises(ValidationError):
        ToolResult(tool_name="sample", status="error", latency_ms=-1)

