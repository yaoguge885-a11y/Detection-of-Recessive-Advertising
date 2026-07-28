from collections import Counter
from pathlib import Path

from impad.contracts import LawEvidence
from impad.rag.chroma_retriever import ChromaLegalRetriever
from impad.rag.benchmark import load_retrieval_benchmark
from impad.rag.corpus import load_legal_corpus
from impad.rag.evaluation import (
    LegalRetrievalQuestion,
    evaluate_retriever,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load_documents():
    return load_legal_corpus(
        FIXTURES / "legal_rag_documents.json"
    ).documents


def _load_questions():
    return load_retrieval_benchmark(
        FIXTURES / "legal_rag_eval_30.json"
    ).questions


class FixedRetriever:
    def retrieve(self, query, top_k=5):
        return [
            LawEvidence(
                source_id="s",
                document_title="fixture",
                source_path_or_url="fixture://metrics",
                article_id=article_id,
                document_version="v1",
                quote=f"quote-{article_id}",
                retrieval_score=score,
            )
            for article_id, score in (
                ("A", 0.9),
                ("X", 0.8),
                ("B", 0.7),
            )
        ][:top_k]


def test_benchmark_contains_exactly_ten_questions_per_category():
    questions = _load_questions()
    counts = Counter(question.category for question in questions)

    assert len(questions) == 30
    assert counts == {
        "direct": 10,
        "cross_document": 10,
        "abstention": 10,
    }
    assert len({question.question_id for question in questions}) == 30


def test_all_expected_citations_exist_in_fixture_documents():
    known = {
        f"{document.source_id}#{section.article_id}"
        for document in _load_documents()
        for section in document.sections
    }

    for question in _load_questions():
        assert set(question.expected_keys) <= known
        if question.category == "abstention":
            assert question.expected_keys == []
        else:
            assert question.expected_keys


def test_chroma_benchmark_runs_and_reports_recall_and_abstention():
    retriever = ChromaLegalRetriever(
        collection_name="test_30_question_benchmark",
        dimensions=256,
        minimum_score=0.35,
    )
    retriever.index_documents(_load_documents())

    metrics = evaluate_retriever(
        retriever,
        _load_questions(),
        top_k=5,
    )

    assert metrics.total_questions == 30
    assert metrics.answerable_questions == 20
    assert metrics.abstention_questions == 10
    assert 0 <= metrics.recall_at_5 <= 1
    assert 0 <= metrics.direct_recall_at_5 <= 1
    assert 0 <= metrics.cross_document_recall_at_5 <= 1
    assert 0 <= metrics.false_citation_rate <= 1
    assert len(metrics.results) == 30
    assert metrics.recall_at_5 >= 0.6
    assert metrics.direct_recall_at_5 >= 0.8
    assert metrics.cross_document_recall_at_5 >= 0.3
    assert metrics.false_citation_rate == 0


def test_recall_cutoffs_use_the_observed_candidate_order():
    metrics = evaluate_retriever(
        FixedRetriever(),
        [LegalRetrievalQuestion(
            question_id="cutoffs",
            category="direct",
            query="fixture query",
            expected_keys=["s#A", "s#B"],
        )],
        top_k=5,
    )

    assert metrics.recall_at_1 == 0.5
    assert metrics.recall_at_3 == 1.0
    assert metrics.recall_at_5 == 1.0
