"""Deterministic lexical and vector fusion for legal citations."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts.verdict import LawEvidence
from .contracts import LegalDocument, LegalRetriever


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")
_VECTOR_FALLBACK_LIMITATION = (
    "Vector retrieval unavailable; lexical fallback used."
)
_LEXICAL_FALLBACK_LIMITATION = (
    "Lexical retrieval unavailable; vector fallback used."
)


def tokenize_legal_text(text: str) -> list[str]:
    """Return stable ASCII words plus Chinese unigrams and bigrams."""

    tokens: list[str] = []
    for match in _TOKEN_PATTERN.findall(text.lower()):
        if match.isascii():
            tokens.append(match)
            continue
        characters = list(match)
        tokens.extend(characters)
        tokens.extend(
            "".join(characters[index:index + 2])
            for index in range(len(characters) - 1)
        )
    return tokens


@dataclass(frozen=True)
class _SectionEntry:
    document: LegalDocument
    section_index: int
    tokens: frozenset[str]

    @property
    def key(self) -> tuple[str, str, str]:
        section = self.document.sections[self.section_index]
        return (
            self.document.source_id,
            self.document.document_version,
            section.article_id,
        )

    def to_evidence(self, retrieval_score: float) -> LawEvidence:
        section = self.document.sections[self.section_index]
        return LawEvidence(
            source_id=self.document.source_id,
            document_title=self.document.document_title,
            source_path_or_url=self.document.source_path_or_url,
            article_id=section.article_id,
            document_version=self.document.document_version,
            jurisdiction=self.document.jurisdiction,
            effective_date=self.document.effective_date,
            quote=section.text,
            retrieval_score=retrieval_score,
            limitations=(
                ["Synthetic fixture; not legal advice."]
                if self.document.fixture_only
                else []
            ),
        )


class HybridLegalRetriever:
    """Fuse deterministic lexical and vector ranks without changing contracts."""

    def __init__(
        self,
        documents: list[LegalDocument],
        vector_retriever: LegalRetriever,
        *,
        rrf_k: int = 60,
        vector_candidates: int = 10,
        minimum_lexical_score: float = 0.1,
    ):
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        if vector_candidates < 1:
            raise ValueError("vector_candidates must be at least 1")
        if not 0 <= minimum_lexical_score <= 1:
            raise ValueError(
                "minimum_lexical_score must be between 0 and 1"
            )
        self.vector_retriever = vector_retriever
        self.rrf_k = rrf_k
        self.vector_candidates = vector_candidates
        self.minimum_lexical_score = minimum_lexical_score
        self._entries = [
            _SectionEntry(
                document=document,
                section_index=index,
                tokens=frozenset(tokenize_legal_text(section.text)),
            )
            for document in documents
            for index, section in enumerate(document.sections)
        ]
        self._entries_by_key = {entry.key: entry for entry in self._entries}
        from .chroma_retriever import CitationGuard

        self._guard = CitationGuard.from_documents(documents)

    @staticmethod
    def _evidence_key(item: LawEvidence) -> tuple[str, str, str] | None:
        if item.document_version is None or item.article_id is None:
            return None
        return (
            item.source_id,
            item.document_version,
            item.article_id,
        )

    def _lexical_candidates(
        self,
        query_tokens: frozenset[str],
    ) -> list[tuple[tuple[str, str, str], float]]:
        candidates = []
        for entry in self._entries:
            overlap = query_tokens & entry.tokens
            if not any(len(token) > 1 for token in overlap):
                continue
            score = len(overlap) / len(query_tokens)
            if score >= self.minimum_lexical_score:
                candidates.append((entry.key, score))
        return sorted(
            candidates,
            key=lambda item: (-item[1], item[0]),
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[LawEvidence]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query_tokens = frozenset(tokenize_legal_text(query))
        if not query_tokens:
            return []

        lexical_failed = False
        try:
            lexical = self._lexical_candidates(query_tokens)
        except Exception:
            lexical_failed = True
            lexical = []
        vector_failed = False
        try:
            vector = self.vector_retriever.retrieve(
                query,
                top_k=max(top_k, self.vector_candidates),
            )
        except Exception:
            vector_failed = True
            vector = []

        vector_by_key: dict[tuple[str, str, str], LawEvidence] = {}
        vector_ranks: dict[tuple[str, str, str], int] = {}
        for rank, item in enumerate(vector, start=1):
            key = self._evidence_key(item)
            if key is not None and key not in vector_ranks:
                vector_by_key[key] = item
                vector_ranks[key] = rank
        lexical_scores = dict(lexical)
        lexical_ranks = {
            key: rank
            for rank, (key, _) in enumerate(lexical, start=1)
        }
        candidate_keys = set(vector_ranks) | set(lexical_ranks)
        if not candidate_keys:
            return []

        fused = {
            key: (
                (
                    1 / (self.rrf_k + vector_ranks[key])
                    if key in vector_ranks
                    else 0
                )
                + (
                    1 / (self.rrf_k + lexical_ranks[key])
                    if key in lexical_ranks
                    else 0
                )
            )
            for key in candidate_keys
        }
        best_rank = {
            key: min(
                vector_ranks.get(key, self.vector_candidates + len(lexical)),
                lexical_ranks.get(key, self.vector_candidates + len(lexical)),
            )
            for key in candidate_keys
        }
        ordered_keys = sorted(
            candidate_keys,
            key=lambda key: (-fused[key], best_rank[key], key),
        )
        maximum_score = max(fused.values())
        evidence: list[LawEvidence] = []
        for key in ordered_keys[:top_k]:
            item = vector_by_key.get(key)
            if item is None:
                entry = self._entries_by_key.get(key)
                if entry is None:
                    continue
                item = entry.to_evidence(lexical_scores[key])
            limitations = list(item.limitations)
            if vector_failed and _VECTOR_FALLBACK_LIMITATION not in limitations:
                limitations.append(_VECTOR_FALLBACK_LIMITATION)
            if (
                lexical_failed
                and _LEXICAL_FALLBACK_LIMITATION not in limitations
            ):
                limitations.append(_LEXICAL_FALLBACK_LIMITATION)
            evidence.append(item.model_copy(update={
                "rerank_score": fused[key] / maximum_score,
                "limitations": limitations,
            }))

        self._guard.validate(evidence)
        return evidence
