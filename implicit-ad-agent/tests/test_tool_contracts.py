import json

from impad.tools.contracts import ToolResult
from impad.tools.registry import TOOLS_V1, TOOL_READINESS


def test_registry_has_unique_structured_tools():
    names = [item.name for item in TOOLS_V1]
    assert len(names) == len(set(names)) == 4
    assert all(item.description for item in TOOLS_V1)
    assert all(item.args_schema is not None for item in TOOLS_V1)
    assert all(TOOL_READINESS[name] for name in names)


def test_common_result_is_json_serializable():
    result = ToolResult(tool_name="sample", status="skipped")
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

