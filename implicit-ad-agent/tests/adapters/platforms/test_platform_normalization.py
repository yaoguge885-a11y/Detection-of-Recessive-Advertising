"""Shared platform payload normalization."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.adapters.platforms.normalization import (
    ParsedPlatformPost,
    build_platform_post,
)
from impad.contracts import CaptureModality, DisclosureRecord, MediaRecord


_CAPTURED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _target_modalities(
    *,
    text: str = "complete",
    image: str = "complete",
    comment: str = "complete",
    disclosure: str = "complete",
):
    return {
        "text": CaptureModality(status=text),
        "image": CaptureModality(status=image),
        "comment": CaptureModality(status=comment),
        "disclosure": CaptureModality(status=disclosure),
    }


def _payload_fields(**overrides):
    fields = {
        "platform": "fixture",
        "content_type": "post",
        "post_id": "post-1",
        "creator_id": "creator-1",
        "published_at": datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        "text": "fixture body",
        "media": [],
        "comments": [],
        "disclosures": [],
        "captured_at": _CAPTURED_AT,
    }
    fields.update(overrides)
    return fields


def _payload(*, media=None, modalities=None, **overrides):
    fields = _payload_fields(**overrides)
    fields["media"] = [] if media is None else media
    fields["modalities"] = (
        _target_modalities() if modalities is None else modalities
    )
    return ParsedPlatformPost(**fields)


def test_build_platform_post_requires_all_target_modalities():
    with pytest.raises(ValidationError, match="missing target modalities"):
        ParsedPlatformPost(
            **_payload_fields(),
            modalities={
                "text": CaptureModality(status="complete"),
            },
        )


def test_remote_image_reference_is_partial_and_blocks_disclosure_absence():
    post = build_platform_post(
        _payload(
            media=[MediaRecord(
                media_id="image-1",
                type="image",
                ref="https://media.example.test/image-1.jpg",
            )],
            modalities=_target_modalities(image="partial"),
        ),
        source_ref_hash="a" * 64,
        adapter_version="fixture-v1",
    )

    assert post.capture_status.modalities["image"].status == "partial"
    assert post.capture_status.can_assess_disclosure is False
    assert post.privacy.anonymized is True


def test_build_platform_post_populates_auditable_runtime_fields():
    post = build_platform_post(
        _payload(
            media=[MediaRecord(media_id="image-1", type="image")],
            disclosures=[DisclosureRecord(
                kind="platform_badge",
                text="品牌合作",
                source="platform_metadata",
            )],
        ),
        source_ref_hash="b" * 64,
        adapter_version="fixture-v2",
    )

    assert post.schema_version == "1.0"
    assert post.source_type == "platform_fixture"
    assert post.provenance.source_ref_hash == "b" * 64
    assert post.provenance.collected_at == _CAPTURED_AT
    assert post.provenance.collector == "synthetic_fixture"
    assert post.capture_status.source == "fixture:fixture"
    assert post.capture_status.adapter_version == "fixture-v2"
    assert post.capture_status.captured_at == _CAPTURED_AT
    assert post.capture_status.can_assess_disclosure is True
    assert post.privacy.anonymized is True
    assert post.privacy.contains_sensitive_data is False


def test_build_platform_post_blocks_disclosure_assessment_for_non_image_media():
    post = build_platform_post(
        _payload(
            media=[MediaRecord(media_id="video-1", type="video")],
        ),
        source_ref_hash="c" * 64,
        adapter_version="fixture-v1",
    )

    assert post.capture_status.can_assess_disclosure is False


def test_parsed_platform_post_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="extra"):
        ParsedPlatformPost(
            **_payload_fields(),
            modalities=_target_modalities(),
            unknown_field="must not be silently dropped",
        )
