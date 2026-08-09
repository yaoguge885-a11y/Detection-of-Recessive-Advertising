"""String-aware extraction of JSON assigned in platform fixture HTML."""
from __future__ import annotations

import pytest

from impad.adapters.platforms.embedded_json import extract_assigned_json


def test_extract_assigned_json_handles_nested_braces_inside_strings():
    html = (
        '<script>window.__INITIAL_STATE__ = '
        '{"note":{"text":"brace } and escaped \\\" quote",'
        '"nested":{"items":[1,{"ok":true}]}}};</script>'
    )

    assert extract_assigned_json(html, "window.__INITIAL_STATE__") == {
        "note": {
            "text": 'brace } and escaped " quote',
            "nested": {"items": [1, {"ok": True}]},
        }
    }


def test_extract_assigned_json_fails_when_assignment_is_absent():
    with pytest.raises(ValueError, match="embedded JSON marker not found"):
        extract_assigned_json("<html></html>", "window.__INITIAL_STATE__")


def test_extract_assigned_json_fails_when_object_is_absent():
    with pytest.raises(ValueError, match="embedded JSON object not found"):
        extract_assigned_json(
            "<script>window.__INITIAL_STATE__ = undefined;</script>",
            "window.__INITIAL_STATE__",
        )


def test_extract_assigned_json_fails_when_object_is_incomplete():
    with pytest.raises(ValueError, match="embedded JSON object is incomplete"):
        extract_assigned_json(
            '<script>window.__INITIAL_STATE__ = {"items": [1, 2];</script>',
            "window.__INITIAL_STATE__",
        )


def test_extract_assigned_json_fails_when_object_is_invalid():
    with pytest.raises(ValueError, match="embedded JSON object is invalid"):
        extract_assigned_json(
            '<script>window.__INITIAL_STATE__ = {"items": [1,]};</script>',
            "window.__INITIAL_STATE__",
        )
