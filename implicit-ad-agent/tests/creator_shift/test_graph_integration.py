from __future__ import annotations

from impad.graph import graph
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def _payload(*, with_history: bool = True) -> dict:
    history = [
        {
            "post_id": f"history_{index}",
            "text": text,
            "published_at": f"2026-07-{26 + index}T00:00:00Z",
        }
        for index, text in enumerate(
            ("今天生活记录", "昨天学习记录", "周末朋友分享"),
            start=1,
        )
    ]
    return {
        "post_id": "target",
        "creator_id": "creator_1",
        "published_at": "2026-07-30T00:00:00Z",
        "text": "限时抢购，强烈推荐，优惠折扣，点击链接购买下单",
        "capture_complete": True,
        "history": history if with_history else [],
    }


def test_graph_persists_creator_shift_as_neutral_history_evidence():
    out = graph.invoke({"post": _payload()})

    summary = out["creator_shift_summary"]
    items = [
        item
        for item in out["evidence_bundle"].items
        if item.kind == "creator_shift"
    ]

    assert summary.status == "sufficient"
    assert len(items) == 1
    assert items[0].polarity == "neutral"
    assert items[0].source_type == "history"
    assert out["verdict_report"].creator_shift == summary
    assert out["verdict_report"].creator_shift_evidence_ids == [
        items[0].evidence_id
    ]
    assert out["run_metadata"].model_versions["creator_shift"] == (
        "creator_shift_runtime_v1"
    )


def test_creator_shift_evidence_does_not_change_baseline_judgment():
    with_history = graph.invoke({"post": _payload()})
    without_history = graph.invoke({
        "post": _payload(with_history=False),
    })

    assert without_history["creator_shift_summary"].status == "unavailable"
    assert not [
        item
        for item in without_history["evidence_bundle"].items
        if item.kind == "creator_shift"
    ]
    for field in (
        "label",
        "confidence",
        "commercial_intent",
        "disclosure",
    ):
        assert getattr(with_history["verdict_report"], field) == getattr(
            without_history["verdict_report"],
            field,
        )


def test_readable_report_exposes_creator_shift_status(tmp_path):
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    result = service.analyze(_payload())

    assert "## CreatorShift" in result.readable_report
    assert "- 状态：sufficient" in result.readable_report
    assert "- 历史数量：3/3" in result.readable_report
