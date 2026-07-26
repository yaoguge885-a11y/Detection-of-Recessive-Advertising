"""PostRecord capability and tool-argument adaptation."""
from __future__ import annotations

from impad.adapters.manual import post_record_from_manual
from impad.orchestration.capability_planner import CapabilityPlanner
from impad.orchestration.post_tools import (
    capability_context_from_post,
    function_calls_from_post,
)
from impad.tools.registry import TOOL_SPEC_BY_NAME


ALL_TOOL_NAMES = {
    "analyze_text_intent",
    "sentiment_curve",
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
    "topic_drift",
    "comment_anomaly",
}


def _post(**updates):
    raw = {
        "text": "限时推荐，欢迎了解",
        "published_at": "2026-07-20T00:00:00Z",
        "comments": [
            {"comment_id": f"comment_{index}", "text": f"评论{index}"}
            for index in range(5)
        ],
        "history": [
            {
                "post_id": f"post_history_{index}",
                "text": f"历史{index}",
                "published_at": f"2026-07-{17 + index}T00:00:00Z",
            }
            for index in range(3)
        ],
    }
    raw.update(updates)
    return post_record_from_manual(raw)


def test_post_with_all_modalities_generates_all_seven_tool_calls(tmp_path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fixture")
    post = _post(image_path=str(image))
    context = capability_context_from_post(post)
    plan = CapabilityPlanner().plan(context)

    calls = function_calls_from_post(post, plan)

    assert {call["name"] for call in calls} == ALL_TOOL_NAMES
    for call in calls:
        spec = TOOL_SPEC_BY_NAME[call["name"]]
        spec.tool.args_schema.model_validate(call["args"])


def test_text_only_post_exposes_only_text_tools():
    post = post_record_from_manual({"text": "普通文本"})
    context = capability_context_from_post(post)
    plan = CapabilityPlanner().plan(context)

    calls = function_calls_from_post(post, plan)

    assert [call["name"] for call in calls] == [
        "analyze_text_intent",
        "sentiment_curve",
    ]


def test_remote_image_url_does_not_create_local_image_capability():
    post = post_record_from_manual({
        "text": "带远程图片",
        "image_url": "https://example.com/image.jpg",
    })

    context = capability_context_from_post(post)

    assert "image" not in context.modalities
    assert context.sample_counts.get("image", 0) == 0


def test_insufficient_comments_and_history_do_not_generate_calls():
    post = post_record_from_manual({
        "text": "样本不足",
        "comments": [{"comment_id": "comment_1", "text": "一条"}],
        "history": [
            {"post_id": "post_history_1", "text": "历史一"},
            {"post_id": "post_history_2", "text": "历史二"},
        ],
    })
    context = capability_context_from_post(post)
    plan = CapabilityPlanner().plan(context)

    calls = function_calls_from_post(post, plan)
    names = {call["name"] for call in calls}

    assert "comment_anomaly" not in names
    assert "topic_drift" not in names


def test_optional_tool_filter_preserves_registry_order():
    post = _post()
    context = capability_context_from_post(post)
    plan = CapabilityPlanner().plan(context)

    calls = function_calls_from_post(
        post,
        plan,
        tool_names={"comment_anomaly", "analyze_text_intent"},
    )

    assert [call["name"] for call in calls] == [
        "analyze_text_intent",
        "comment_anomaly",
    ]


def test_unknown_timestamp_history_is_not_executable_or_sent_to_sentiment():
    post = post_record_from_manual({
        "text": "目标帖",
        "published_at": "2026-07-20T00:00:00Z",
        "history": [
            {"post_id": f"post_history_{index}", "text": f"历史{index}"}
            for index in range(3)
        ],
    })

    context = capability_context_from_post(post)
    plan = CapabilityPlanner().plan(context)
    calls = function_calls_from_post(post, plan)

    assert "history" not in context.modalities
    assert "topic_drift" not in {call["name"] for call in calls}
    sentiment = next(
        call for call in calls if call["name"] == "sentiment_curve"
    )
    assert sentiment["args"]["history"] == []
