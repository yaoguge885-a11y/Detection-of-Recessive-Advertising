import json

from impad.tools.contracts import ToolResult
from impad.tools.registry import TOOLS_V1, TOOL_READINESS
from impad.tools.vision_context import VisionContext


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


def test_registry_tools_invoke_with_minimal_serializable_examples():
    context = VisionContext.model_validate({
        "image_id": "sha256:registry", "image_name": "registry.jpg",
        "objects": [{"class_name": "bottle", "confidence": 0.9,
                     "bbox": [1, 2, 20, 40], "center": [10, 20]}],
        "texts": [{"text": "面霜限时优惠", "confidence": 0.9,
                   "bbox": [4, 5, 80, 20]}],
        "model_version": "registry-fixture-v1",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    }).model_dump(mode="json")
    history = [
        {"post_id": str(index), "text": "面霜护肤使用记录",
         "published_at": f"2026-07-0{index}"}
        for index in range(1, 4)
    ]
    comments = [
        {"comment_id": str(index), "text": "太好用了，已下单",
         "created_at": f"2026-07-04T10:0{index}:00"}
        for index in range(5)
    ]
    examples = {
        "analyze_text_intent": {"text": "面霜限时优惠"},
        "sentiment_curve": {"text": "面霜限时优惠", "history": history},
        "ocr_extract": {"image_path": "registry.jpg", "vision_context": context,
                        "detect_qr": False},
        "image_text_consistency": {"text": "面霜限时优惠",
                                   "image_path": "registry.jpg",
                                   "vision_context": context},
        "detect_logo_product": {"image_path": "registry.jpg",
                                "vision_context": context},
        "topic_drift": {"post_id": "current", "text": "面霜限时优惠",
                        "published_at": "2026-07-04", "history": history},
        "comment_anomaly": {"comments": comments},
    }

    for registered_tool in TOOLS_V1:
        result = registered_tool.invoke(examples[registered_tool.name])
        envelope = ToolResult.model_validate(result)
        assert envelope.tool_name == registered_tool.name
        assert envelope.status in {"ok", "degraded"}
        assert envelope.evidence
        assert envelope.model_info
        assert envelope.score is None or 0 <= envelope.score <= 1
        json.dumps(result, ensure_ascii=False)
