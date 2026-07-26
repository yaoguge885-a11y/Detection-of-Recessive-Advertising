from impad.orchestration.capability_planner import (
    CapabilityPlanner,
    CapabilityPlanningPolicy,
)
from impad.orchestration.tool_gateway import CapabilityContext, LocalToolGateway


def test_text_only_plan_exposes_only_text_tools_with_explicit_skips():
    context = CapabilityContext(
        modalities=frozenset({"text"}),
        sample_counts={"text": 1},
    )
    plan = CapabilityPlanner().plan(context)

    assert plan.available_tools == [
        "analyze_text_intent",
        "sentiment_curve",
    ]
    skipped = {item.tool_name: item.reasons for item in plan.skipped_tools}
    assert "missing_modality:image" in skipped["ocr_extract"]
    assert "missing_modality:history" in skipped["topic_drift"]
    assert plan.call_budget == 8
    assert len(plan.function_definitions) == 2


def test_present_but_insufficient_comments_are_skipped_not_available():
    context = CapabilityContext(
        modalities=frozenset({"comments"}),
        sample_counts={"comments": 4},
    )
    plan = CapabilityPlanner().plan(context)
    skipped = {item.tool_name: item.reasons for item in plan.skipped_tools}

    assert "comment_anomaly" not in plan.available_tools
    assert "insufficient_samples:comments:4<5" in skipped["comment_anomaly"]


def test_full_context_exposes_all_seven_tools():
    context = CapabilityContext(
        modalities=frozenset({"text", "image", "comments", "history"}),
        sample_counts={"text": 1, "image": 1, "comments": 5, "history": 3},
    )
    plan = CapabilityPlanner().plan(context)

    assert len(plan.available_tools) == 7
    assert plan.skipped_tools == []


def test_empty_context_has_zero_call_budget():
    plan = CapabilityPlanner().plan(CapabilityContext())

    assert plan.available_tools == []
    assert plan.function_definitions == []
    assert plan.call_budget == 0


def test_policy_caps_calls_and_tool_timeouts():
    context = CapabilityContext(
        modalities=frozenset({"text", "image", "comments", "history"}),
        sample_counts={"text": 1, "image": 1, "comments": 5, "history": 3},
    )
    plan = CapabilityPlanner().plan(
        context,
        CapabilityPlanningPolicy(
            max_calls=3,
            max_tool_timeout_seconds=5,
        ),
    )

    assert plan.call_budget == 3
    assert all(value <= 5 for value in plan.tool_timeouts.values())


def test_gateway_and_planner_use_the_same_eligibility_rule():
    context = CapabilityContext(
        modalities=frozenset({"text", "comments"}),
        sample_counts={"text": 1, "comments": 5},
    )
    planned = CapabilityPlanner().plan(context).available_tools
    listed = [spec.name for spec in LocalToolGateway().list_tools(context)]

    assert planned == listed
