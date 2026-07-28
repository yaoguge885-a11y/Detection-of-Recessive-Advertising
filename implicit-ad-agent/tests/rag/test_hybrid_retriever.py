from datetime import date

import pytest

from impad.contracts import LawEvidence
from impad.rag.contracts import LegalDocument, LegalSection
from impad.rag.hybrid_retriever import HybridLegalRetriever


def _documents() -> list[LegalDocument]:
    return [
        LegalDocument(
            source_id="fixture_disclosure",
            document_title="合成披露规则",
            source_path_or_url="fixture://disclosure",
            document_version="fixture-v1",
            effective_date=date(2026, 1, 1),
            authority_level="synthetic_fixture",
            fixture_only=True,
            sections=[
                LegalSection(
                    article_id="D1",
                    title="商业标识",
                    text="商业推广内容应当在正文显著位置标明广告合作。",
                ),
            ],
        ),
        LegalDocument(
            source_id="fixture_platform",
            document_title="合成平台规则",
            source_path_or_url="fixture://platform",
            document_version="fixture-v1",
            authority_level="synthetic_fixture",
            fixture_only=True,
            sections=[
                LegalSection(
                    article_id="P1",
                    title="链接",
                    text="帖子含购买链接时仍应保留商业推广标识。",
                ),
            ],
        ),
    ]


def _vector_evidence() -> LawEvidence:
    document = _documents()[1]
    section = document.sections[0]
    return LawEvidence(
        source_id=document.source_id,
        document_title=document.document_title,
        source_path_or_url=document.source_path_or_url,
        article_id=section.article_id,
        document_version=document.document_version,
        quote=section.text,
        retrieval_score=0.8,
        limitations=["Synthetic fixture; not legal advice."],
    )


class FixedVectorRetriever:
    def __init__(self, evidence: list[LawEvidence]):
        self.evidence = evidence

    def retrieve(self, query: str, top_k: int = 5) -> list[LawEvidence]:
        return self.evidence[:top_k]


class FailingVectorRetriever:
    def retrieve(self, query: str, top_k: int = 5) -> list[LawEvidence]:
        raise ConnectionError("vector store offline")


def test_hybrid_retriever_unions_paths_and_sets_stable_rerank_scores():
    retriever = HybridLegalRetriever(
        documents=_documents(),
        vector_retriever=FixedVectorRetriever([_vector_evidence()]),
    )

    first = retriever.retrieve("正文显著位置广告合作", top_k=2)
    repeated = retriever.retrieve("正文显著位置广告合作", top_k=2)

    assert [(item.source_id, item.article_id) for item in first] == [
        ("fixture_disclosure", "D1"),
        ("fixture_platform", "P1"),
    ]
    assert first[0].rerank_score == 1.0
    assert all(
        item.rerank_score is not None
        and 0 <= item.rerank_score <= 1
        for item in first
    )
    assert [
        (item.source_id, item.article_id, item.rerank_score)
        for item in repeated
    ] == [
        (item.source_id, item.article_id, item.rerank_score)
        for item in first
    ]


def test_vector_failure_uses_lexical_evidence_without_inventing_quote():
    documents = _documents()
    retriever = HybridLegalRetriever(
        documents=documents,
        vector_retriever=FailingVectorRetriever(),
    )

    result = retriever.retrieve("商业推广正文广告合作", top_k=1)

    assert result[0].quote == documents[0].sections[0].text
    assert "Vector retrieval unavailable; lexical fallback used." in (
        result[0].limitations
    )


def test_empty_and_unrelated_queries_abstain():
    retriever = HybridLegalRetriever(
        documents=_documents(),
        vector_retriever=FixedVectorRetriever([]),
    )

    assert retriever.retrieve("", top_k=5) == []
    assert retriever.retrieve("天气预报篮球比赛", top_k=5) == []


def test_top_k_must_be_positive():
    retriever = HybridLegalRetriever(
        documents=_documents(),
        vector_retriever=FixedVectorRetriever([]),
    )

    with pytest.raises(ValueError, match="top_k must be at least 1"):
        retriever.retrieve("广告", top_k=0)
