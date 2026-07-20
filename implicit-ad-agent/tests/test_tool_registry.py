from impad.tools.registry import TOOLS_V1, TOOL_READINESS


def test_registry_contains_seven_unique_ready_tools():
    names = [item.name for item in TOOLS_V1]
    assert len(names) == 7
    assert len(set(names)) == 7
    assert set(names) == set(TOOL_READINESS)
    assert all(TOOL_READINESS.values())


def test_registry_tools_have_docs_and_input_schemas():
    for item in TOOLS_V1:
        assert item.description
        assert item.args_schema is not None
