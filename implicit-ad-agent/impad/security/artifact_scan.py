"""Secret-free scanner for generated JSON, Markdown, and log artifacts."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field

from .redaction import REDACTED, redact_sensitive_text


SUPPORTED_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".log"})
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_TEXT_RULES = (
    (
        "set_cookie_value",
        re.compile(
            r"\bset[-_]cookie\b[\"']?\s*[:=]\s*[\"']?"
            r"(?P<value>[^\\\"'\r\n}]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "cookie_value",
        re.compile(
            r"(?<!set-)(?<!set_)\bcookies?\b[\"']?\s*[:=]\s*[\"']?"
            r"(?P<value>[^\\\"'\r\n}]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "authorization_value",
        re.compile(
            r"\bauthorization\b[\"']?\s*[:=]\s*[\"']?"
            r"(?:(?:bearer|basic)\s+)?"
            r"(?P<value>[^\\\"'\s,;}]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "sensitive_assignment",
        re.compile(
            r"\b(?:token|access[_-]?token|refresh[_-]?token|api[_-]?key|"
            r"password|secret|session(?:[_-]?id)?)\b"
            r"[\"']?\s*[:=]\s*[\"']?"
            r"(?P<value>[^\\\"'\s,;}&#]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded_sensitive_assignment",
        re.compile(
            r"\b(?:token|access(?:_|%5f|-)?token|"
            r"refresh(?:_|%5f|-)?token|api(?:_|%5f|-)?key|"
            r"password|secret|session(?:_|%5f|-)?id)"
            r"(?:%3a|%3d)(?P<value>[^\\\s\"']+)",
            re.IGNORECASE,
        ),
    ),
)


class ArtifactFinding(BaseModel):
    """A finding that identifies a rule without retaining matched content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    rule_id: str
    line_number: int = Field(ge=1)
    match_length: int = Field(ge=0)
    match_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _finding(
    path: Path,
    rule_id: str,
    line_number: int,
    matched: str,
) -> ArtifactFinding:
    encoded = matched.encode("utf-8")
    return ArtifactFinding(
        path=str(path),
        rule_id=rule_id,
        line_number=line_number,
        match_length=len(encoded),
        match_hash=hashlib.sha256(encoded).hexdigest(),
    )


def _read_error(path: Path) -> ArtifactFinding:
    return ArtifactFinding(
        path=str(path),
        rule_id="read_error",
        line_number=1,
        match_length=0,
        match_hash=_EMPTY_HASH,
    )


def _supported_files(paths: Iterable[str | Path]) -> Iterator[Path]:
    observed: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        candidates = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            if (
                candidate in observed
                or candidate.suffix.casefold() not in SUPPORTED_SUFFIXES
                or (candidate.exists() and not candidate.is_file())
            ):
                continue
            observed.add(candidate)
            yield candidate


def _is_redacted(value: str) -> bool:
    return value.strip().rstrip(";").strip() == REDACTED


def _scan_line(path: Path, line_number: int, line: str):
    findings = []
    for rule_id, pattern in _TEXT_RULES:
        for match in pattern.finditer(line):
            value = match.group("value")
            if _is_redacted(value):
                continue
            findings.append(_finding(path, rule_id, line_number, value))
    for match in _URL_RE.finditer(line):
        raw_url = match.group(0)
        if redact_sensitive_text(raw_url) != raw_url:
            findings.append(_finding(
                path,
                "sensitive_url",
                line_number,
                raw_url,
            ))
    return findings


def scan_artifacts(paths: Iterable[str | Path]) -> list[ArtifactFinding]:
    """Recursively scan only supported artifact files as strict UTF-8."""

    findings = []
    for path in _supported_files(paths):
        try:
            content = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            findings.append(_read_error(path))
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            findings.extend(_scan_line(path, line_number, line))
    return sorted(
        findings,
        key=lambda item: (
            item.path,
            item.line_number,
            item.rule_id,
            item.match_hash,
        ),
    )
