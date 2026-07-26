import math
from datetime import date

from impad.rag.chroma_retriever import (
    ChromaLegalRetriever,
    CitationGuard,
)
from impad.rag.contracts import LegalDocument, LegalSection
from impad.rag.embeddings import DeterministicHashEmbedding


def _documents():
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
                LegalSection(
                    article_id="D2",
                    title="图片披露",
                    text="披露标识可以位于图片，但必须清晰可辨认。",
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
                )
            ],
        ),
    ]


def test_hash_embedding_is_deterministic_normalized_and_fixed_size():
    embedding = DeterministicHashEmbedding(dimensions=64)
    first = embedding.embed("商业推广应标明广告")
    repeated = embedding.embed("商业推广应标明广告")

    assert first == repeated
    assert len(first) == 64
    assert math.isclose(
        math.sqrt(sum(value * value for value in first)),
        1.0,
        rel_tol=1e-9,
    )


def test_index_is_idempotent_and_uses_explicit_local_embeddings():
    retriever = ChromaLegalRetriever(
        collection_name="test_idempotent",
        dimensions=64,
    )

    assert retriever.index_documents(_documents()) == 3
    assert retriever.index_documents(_documents()) == 3
    assert retriever.count() == 3
    assert retriever.uses_external_embedding is False


def test_exact_clause_query_returns_traceable_indexed_citation():
    documents = _documents()
    retriever = ChromaLegalRetriever(
        collection_name="test_exact_clause",
        dimensions=128,
        minimum_score=0.5,
    )
    retriever.index_documents(documents)

    evidence = retriever.retrieve(
        "商业推广内容应当在正文显著位置标明广告合作。",
        top_k=2,
    )

    assert evidence
    assert evidence[0].source_id == "fixture_disclosure"
    assert evidence[0].article_id == "D1"
    assert evidence[0].quote == documents[0].sections[0].text
    CitationGuard.from_documents(documents).validate(evidence)


def test_high_threshold_abstains_for_unrelated_query():
    retriever = ChromaLegalRetriever(
        collection_name="test_abstain",
        dimensions=128,
        minimum_score=0.99,
    )
    retriever.index_documents(_documents())

    assert retriever.retrieve("天气预报和篮球比赛", top_k=5) == []


def test_new_document_version_replaces_old_chunks_for_same_source():
    original = _documents()[0]
    updated = LegalDocument(
        source_id=original.source_id,
        document_title=original.document_title,
        source_path_or_url=original.source_path_or_url,
        document_version="fixture-v2",
        effective_date=date(2026, 2, 1),
        authority_level="synthetic_fixture",
        fixture_only=True,
        sections=[
            LegalSection(
                article_id="D1",
                title="正文披露",
                text="新版规则要求商业推广在正文开头标明广告合作。",
            ),
            LegalSection(
                article_id="D2",
                title="图片披露",
                text="新版规则要求图片披露标识保持清晰可见。",
            ),
        ],
    )
    retriever = ChromaLegalRetriever(
        collection_name="test_version_replacement",
        dimensions=128,
        minimum_score=0.5,
    )
    retriever.index_documents([original])
    retriever.index_documents([updated])

    assert retriever.count() == 2
    evidence = retriever.retrieve(updated.sections[0].text, top_k=2)
    assert evidence[0].document_version == "fixture-v2"
    assert evidence[0].quote == updated.sections[0].text
