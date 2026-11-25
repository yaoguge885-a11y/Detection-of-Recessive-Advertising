"""Context-aware disclosure evidence for text and OCR strings.

Commercial-intent keywords are deliberately broad. Disclosure evidence needs
to be narrower because words such as 合作 and 广告 also occur in ordinary
discussion. This module returns spans that can be cited by the evidence
bundle. Ambiguous spans are neutral candidates until a verifier checks their
surrounding sentence.
"""
from __future__ import annotations

import re

from .contracts import ToolEvidence


_SENTENCE_BOUNDARY = re.compile(r"[。！？!?；;\n]")

# These forms explicitly describe the post itself as sponsored or paid. Bare
# commercial words are not matched inside ordinary prose; a complete short
# label list is handled separately below.
_STANDALONE_LABEL = re.compile(
    r"(?:^|(?<=[。！？!?\n]))[ \t]*"
    r"(?:品牌合作|付费合作|商务合作|广告合作|广告|赞助内容)"
    r"(?=[,，、|｜。.!！\n]|$)"
)

_EXPLICIT_PATTERNS = (
    re.compile(r"#(?:ad|sponsored|广告|品牌合作|商务合作|广告合作)(?![A-Za-z0-9_])", re.IGNORECASE),
    _STANDALONE_LABEL,
    re.compile(
        r"(?:本帖|本篇|本文|此帖|这篇|这期|本期|本视频|本内容|这条笔记|该内容)"
        r"\s*(?:为|是|系|属于|由)\s*"
        r"(?:品牌(?:方)?|商家|官方|合作方)?"
        r"\s*(?:付费合作|商业合作|商务合作|品牌合作|广告合作|合作推广|赞助(?:内容)?)"
    ),
    re.compile(
        r"(?:本帖|本篇|本文|此帖|这篇|这期|本期|本视频|本内容|这条笔记|该内容)"
        r"[^。！？!?；;\n]{0,18}(?:由|获)"
        r"[^。！？!?；;\n]{1,16}(?:付费合作|商业合作|商务合作|品牌合作|广告合作|合作推广|赞助(?:内容)?)"
    ),
    re.compile(
        r"(?:品牌方|商家|官方|合作方)\s*"
        r"(?:提供的)?\s*(?:付费合作|商业合作|商务合作|品牌合作|广告合作|合作推广|赞助(?:内容)?)"
    ),
)

_CANDIDATE_PATTERNS = (
    re.compile(r"合作方"),
    re.compile(r"合作"),
    re.compile(r"推广"),
    re.compile(r"赞助"),
    re.compile(r"商务"),
)

# These spans describe a denial, a third party, a question, or an ordinary
# conversation. They cannot establish that the current post is disclosed.
_BLOCKED_CONTEXT = (
    re.compile(
        r"(?:没有|没|无|并无|并没有|不是|并非|不属于|不含|未有|未进行|非)"
        r"[\u4e00-\u9fffA-Za-z0-9#]{0,10}"
        r"(?:品牌(?:方)?合作|合作方?|广告(?:合作)?|推广|赞助|商务)"
    ),
    re.compile(r"(?:如何|怎么|怎样|为何|为什么|哪里|寻找|获得|接到|谈到|想要).{0,12}(?:合作|赞助|推广|商务)"),
    re.compile(r"(?:聊聊|讨论|科普|识别|判断|区分|了解|什么是).{0,8}广告"),
    re.compile(r"广告片"),
    re.compile(
        r"(?:第三方|他人|别人|朋友|品牌方的|客户的|"
        r"(?:他|她|其)(?:这期|本期|这篇|本篇|该内容))"
        r".{0,12}(?:付费|赞助|广告|合作|推广)"
    ),
)

_PEER_COLLABORATION = re.compile(
    r"(?:和|跟|与|同学|朋友|同事|家人|伙伴|同伴|项目组|团队)"
    r"[\u4e00-\u9fff]{0,6}(?:一起)?合作"
)


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start
               for other_start, other_end in ranges)


def _sentence_span(text: str, start: int, end: int) -> tuple[str, tuple[int, int]]:
    """Return the complete source sentence containing a match."""

    left_boundary = max(
        (match.end() for match in _SENTENCE_BOUNDARY.finditer(text, 0, start)),
        default=0,
    )
    right_match = _SENTENCE_BOUNDARY.search(text, end)
    right_boundary = right_match.end() if right_match else len(text)
    left = left_boundary
    right = right_boundary
    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    return text[left:right], (left, right)


def _blocked_ranges(text: str) -> list[tuple[int, int]]:
    ranges = [match.span() for pattern in _BLOCKED_CONTEXT for match in pattern.finditer(text)]
    ranges.extend(match.span() for match in _PEER_COLLABORATION.finditer(text))
    return ranges


def _matches(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    blocked: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            if not _overlaps(*match.span(), blocked):
                found.append(match.span())
    selected: list[tuple[int, int]] = []
    for start, end in sorted(found, key=lambda span: (-(span[1] - span[0]), span[0])):
        if not _overlaps(start, end, selected):
            selected.append((start, end))
    return sorted(selected)


def _candidate_is_relevant(text: str, start: int, end: int) -> bool:
    if _overlaps(start, end, _blocked_ranges(text)):
        return False
    sentence, _ = _sentence_span(text, start, end)
    if _PEER_COLLABORATION.search(sentence):
        return False
    # Generic 合作 is a candidate only when its sentence has a post or brand
    # cue. This keeps ordinary project collaboration out of the verifier.
    if text[start:end] == "合作":
        return bool(re.search(r"(?:本帖|本篇|本文|这篇|这次|此次|本次|内容|帖子|视频|品牌|商家|合作方|商务|付费)", sentence))
    return True


def _is_contextual_explicit(text: str, start: int, end: int) -> bool:
    """Keep questions, quotations, and teaching examples out of confirmation."""

    sentence, sentence_span = _sentence_span(text, start, end)
    local_start = start - sentence_span[0]
    local_end = end - sentence_span[0]
    before = sentence[:local_start]
    after = sentence[local_end:]
    if re.search(r"[?？]", after):
        return True
    if re.search(r"(?:引用|引述|提到|说到|举例|原文|原话)", before):
        return True
    if re.search(r"(?:这句话|这句|这段话|的话)", after):
        return True
    if text[start:end].startswith("#") and re.search(
        r"(?:教你|教学|教程|识别|判断|解释|说明|讲解).{0,12}$",
        before,
    ):
        return True
    return False


def disclosure_evidence(
    text: str,
    *,
    source: str = "post.text",
) -> list[ToolEvidence]:
    """Extract confirmed markers and sentence-level unresolved candidates."""

    blocked = _blocked_ranges(text)
    explicit_spans = [
        span for span in _matches(text, _EXPLICIT_PATTERNS, blocked)
        if not _is_contextual_explicit(text, *span)
    ]
    evidence: list[ToolEvidence] = []
    occupied: list[tuple[int, int]] = []
    for start, end in explicit_spans:
        quote, sentence_span = _sentence_span(text, start, end)
        if sentence_span in occupied:
            continue
        occupied.append(sentence_span)
        evidence.append(ToolEvidence(
            kind="explicit_ad_marker",
            source=source,
            quote=quote,
            span=sentence_span,
        ))

    candidate_spans = _matches(text, _CANDIDATE_PATTERNS, [*blocked, *explicit_spans])
    for start, end in candidate_spans:
        if not _candidate_is_relevant(text, start, end):
            continue
        quote, sentence_span = _sentence_span(text, start, end)
        if sentence_span in occupied:
            continue
        occupied.append(sentence_span)
        evidence.append(ToolEvidence(
            kind="disclosure_candidate",
            source=source,
            quote=quote,
            span=sentence_span,
        ))
    return evidence


__all__ = ["disclosure_evidence"]
