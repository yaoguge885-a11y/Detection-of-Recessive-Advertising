import json

import pytest
from pydantic import ValidationError

from impad.contracts.verdict import (
    CommercialIntent,
    DisclosureEvidence,
    VerdictReport,
)


def _intent(status="present"):
    return CommercialIntent(
        status=status,
        score=0.9 if status == "present" else None,
        evidence_ids=["ev_1"] if status == "present" else [],
    )


def test_dark_ad_requires_present_intent_and_no_disclosure():
    report = VerdictReport(
        post_id="post_1",
        label="暗广",
        confidence=0.85,
        review_required=False,
        commercial_intent=_intent(),
        disclosure=DisclosureEvidence(
            status="not_disclosed",
            confidence=0.8,
            evidence_ids=["ev_2"],
        ),
        evidence_ids=["ev_1", "ev_2"],
        reasons=["商业意图强且完整披露区域未发现披露"],
    )

    assert report.label == "暗广"
    json.dumps(report.model_dump(mode="json"), ensure_ascii=False)


def test_unknown_disclosure_cannot_be_dark_ad():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="暗广",
            confidence=0.5,
            review_required=False,
            commercial_intent=_intent(),
            disclosure=DisclosureEvidence(status="unknown"),
        )


def test_bright_ad_requires_disclosed_status():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="明广",
            confidence=0.7,
            review_required=False,
            commercial_intent=_intent(),
            disclosure=DisclosureEvidence(status="not_disclosed"),
        )


def test_non_ad_requires_absent_commercial_intent():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="非广",
            confidence=0.7,
            review_required=False,
            commercial_intent=_intent(),
            disclosure=DisclosureEvidence(status="unknown"),
        )


def test_review_label_and_flag_must_agree():
    with pytest.raises(ValidationError):
        VerdictReport(
            post_id="post_1",
            label="需复核",
            confidence=0.4,
            review_required=False,
            commercial_intent=CommercialIntent(status="uncertain"),
            disclosure=DisclosureEvidence(status="unknown"),
        )


def test_review_report_accepts_unknown_evidence_state():
    report = VerdictReport(
        post_id="post_1",
        label="需复核",
        confidence=0.4,
        review_required=True,
        commercial_intent=CommercialIntent(status="uncertain"),
        disclosure=DisclosureEvidence(
            status="unknown",
            limitations=["Disclosure area was not captured."],
        ),
        reasons=["采集不完整"],
    )

    assert report.review_required is True
