"""Deterministic extraction of JSON objects embedded in platform HTML."""
from __future__ import annotations

import json


def extract_assigned_json(html: str, marker: str) -> dict:
    """Extract the balanced JSON object assigned after ``marker``.

    The scanner tracks JSON string state so braces inside strings do not alter
    the object depth.  Source text is passed to ``json.loads`` unchanged.
    """
    marker_end = html.find(marker)
    if marker_end < 0:
        raise ValueError("embedded JSON marker not found")
    marker_end += len(marker)

    start = html.find("{", marker_end)
    if start < 0:
        raise ValueError("embedded JSON object not found")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                object_text = html[start : index + 1]
                try:
                    value = json.loads(object_text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "embedded JSON object is invalid"
                    ) from exc
                if not isinstance(value, dict):
                    raise ValueError("embedded JSON object is invalid")
                return value

    raise ValueError("embedded JSON object is incomplete")
