import json

from run_tools_demo import run_tools_demo


def test_fixed_demo_reads_deidentified_post_and_invokes_seven_tools():
    result = run_tools_demo()
    assert result["post_id"] == "demo-post-001"
    assert result["visual_source"] == "synthetic_fixture"
    assert len(result["tools"]) == 7
    assert all(output["evidence"] for output in result["tools"].values())
    json.dumps(result, ensure_ascii=False)
