"""Test-suite isolation and opt-in integration-test policy."""
from __future__ import annotations

import os

import pytest


# A developer's .env may enable tracing.  The default regression suite must
# remain zero-network and must never upload test inputs.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"


def pytest_collection_modifyitems(config, items) -> None:
    """Skip heavy vision tests unless the marker is explicitly selected."""
    mark_expression = config.getoption("-m") or ""
    if "vision_integration" in mark_expression:
        return
    skip = pytest.mark.skip(
        reason="select with -m vision_integration to run installed vision models"
    )
    for item in items:
        if "vision_integration" in item.keywords:
            item.add_marker(skip)
