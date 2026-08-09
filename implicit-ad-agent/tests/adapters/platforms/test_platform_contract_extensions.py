"""Platform capture and disclosure contract extensions."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from impad.contracts import DisclosureRecord
from impad.contracts.post import CaptureModality


def test_disclosure_record_is_strict_and_capture_supports_unsupported():
    marker = DisclosureRecord(
        kind="platform_badge",
        text="品牌合作",
        source="platform_metadata",
    )

    assert marker.text == "品牌合作"
    assert CaptureModality(status="unsupported").status == "unsupported"
    with pytest.raises(ValidationError):
        DisclosureRecord(
            kind="inferred_signal",
            text="可能是广告",
            source="classifier",
        )
