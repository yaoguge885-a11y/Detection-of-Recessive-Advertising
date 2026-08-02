import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.evidence import (
    EvidenceBundle,
    EvidenceConflict,
    EvidenceItem,
    EvidenceModalityCoverage,
)
from impad.tools.contracts import ToolResult


def _item(evidence_id="ev_1"):
    return EvidenceItem(
        evidence_id=evidence_id,
        kind="soft_ad_signal",
        source="post.text",
        tool_name="analyze_text_intent",
        tool_version="1.0",
        call_id="call_1",
        quote="限时抢购",
        score=0.8,
        span=(0, 4),
    )


def test_bundle_keeps_skipped_outcome_separate_from_real_evidence():
    bundle = EvidenceBundle(
        post_id="post_1",
        items=[_item()],
        tool_results=[
            ToolResult(
                tool_name="analyze_text_intent",
                status="degraded",
            ),
            ToolResult(
                tool_name="topic_drift",
                status="skipped",
                warnings=["History unavailable."],
            ),
        ],
    )

    assert len(bundle.items) == 1
    assert bundle.tool_results[1].status == "skipped"
    assert all(item.tool_name != "topic_drift" for item in bundle.items)
    json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)


def test_bundle_rejects_duplicate_evidence_ids():
    with pytest.raises(ValidationError):
        EvidenceBundle(
            post_id="post_1",
            items=[_item(), _item()],
        )


def test_legacy_post_text_source_is_inferred_as_text_modality():
    item = _item()

    assert item.source_type == "text"
    assert item.source_ref == "post.text"


def test_rich_evidence_item_keeps_provenance_and_limitations():
    item = EvidenceItem(
        evidence_id="ev_rich",
        kind="commercial_intent",
        source="post.text",
        tool_name="analyze_text_intent",
        tool_version="1.0",
        polarity="supports",
        strength=0.8,
        source_type="text",
        source_ref="post.text",
        producer="tool:analyze_text_intent",
        producer_version="1.0",
        status="degraded",
        limitations=["Rule fallback was used."],
        observed_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    assert item.polarity == "supports"
    assert item.strength == 0.8
    assert item.status == "degraded"
    assert item.limitations == ["Rule fallback was used."]
    json.dumps(item.model_dump(mode="json"), ensure_ascii=False)


def test_bundle_tracks_coverage_conflicts_and_missing_requirements():
    bundle = EvidenceBundle(
        post_id="post_1",
        items=[_item("ev_1"), _item("ev_2")],
        coverage=[
            EvidenceModalityCoverage(
                modality="text",
                status="covered",
                evidence_ids=["ev_1", "ev_2"],
            ),
            EvidenceModalityCoverage(
                modality="history",
                status="missing",
            ),
        ],
        conflicts=[
            EvidenceConflict(
                conflict_id="conflict_1",
                evidence_ids=["ev_1", "ev_2"],
                reason="The two tools disagree on commercial strength.",
            )
        ],
        missing_requirements=["creator_history"],
    )

    assert bundle.coverage[1].status == "missing"
    assert bundle.conflicts[0].evidence_ids == ["ev_1", "ev_2"]
    assert bundle.missing_requirements == ["creator_history"]
    json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)


def test_bundle_rejects_unknown_coverage_evidence_reference():
    with pytest.raises(ValidationError, match="unknown evidence_id"):
        EvidenceBundle(
            post_id="post_1",
            items=[_item()],
            coverage=[
                EvidenceModalityCoverage(
                    modality="text",
                    status="covered",
                    evidence_ids=["ev_missing"],
                )
            ],
        )


def test_bundle_rejects_conflict_with_duplicate_or_unknown_references():
    with pytest.raises(ValidationError):
        EvidenceConflict(
            conflict_id="conflict_1",
            evidence_ids=["ev_1", "ev_1"],
            reason="Duplicate references are not a conflict.",
        )

    with pytest.raises(ValidationError, match="unknown evidence_id"):
        EvidenceBundle(
            post_id="post_1",
            items=[_item("ev_1"), _item("ev_2")],
            conflicts=[
                EvidenceConflict(
                    conflict_id="conflict_1",
                    evidence_ids=["ev_1", "ev_missing"],
                    reason="One reference is not present.",
                )
            ],
        )
