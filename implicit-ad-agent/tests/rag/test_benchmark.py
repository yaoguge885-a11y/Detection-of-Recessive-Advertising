from pathlib import Path

import pytest
from pydantic import ValidationError

from impad.rag.benchmark import (
    LegalRetrievalBenchmark,
    load_retrieval_benchmark,
    run_p3_retrieval_benchmark,
)
from impad.rag.corpus import load_legal_corpus


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_versioned_benchmark_builds_a_timed_hybrid_report():
    corpus = load_legal_corpus(FIXTURES / "legal_rag_documents.json")
    benchmark = load_retrieval_benchmark(
        FIXTURES / "legal_rag_eval_30.json"
    )

    report = run_p3_retrieval_benchmark(corpus, benchmark)

    assert report.corpus_version == "synthetic-legal-v1"
    assert report.benchmark_version == "synthetic-30-v1"
    assert report.retriever_name == "chroma_lexical_rrf"
    assert report.retriever_version == "hybrid_rrf_v1"
    assert report.question_count == 30
    assert report.indexed_sections == 10
    assert report.indexing_time_ms >= 0
    assert report.evaluation_time_ms >= 0
    assert report.metrics.total_questions == 30
    assert len(report.metrics.results) == 30
    assert report.deterministic_config["external_embedding"] is False


def test_benchmark_rejects_a_corpus_version_mismatch_before_indexing():
    corpus = load_legal_corpus(FIXTURES / "legal_rag_documents.json")
    benchmark = load_retrieval_benchmark(
        FIXTURES / "legal_rag_eval_30.json"
    ).model_copy(update={"corpus_version": "synthetic-legal-v2"})

    with pytest.raises(
        ValueError,
        match=(
            "benchmark expects corpus synthetic-legal-v2, "
            "got synthetic-legal-v1"
        ),
    ):
        run_p3_retrieval_benchmark(corpus, benchmark)


def test_benchmark_loader_rejects_the_old_top_level_array_schema(tmp_path):
    path = tmp_path / "old-schema.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_retrieval_benchmark(path)


def test_benchmark_requires_unique_question_ids():
    benchmark = load_retrieval_benchmark(
        FIXTURES / "legal_rag_eval_30.json"
    )
    duplicate = benchmark.questions[1].model_copy(update={
        "question_id": benchmark.questions[0].question_id,
    })

    with pytest.raises(
        ValidationError,
        match="question_id values must be unique",
    ):
        LegalRetrievalBenchmark(
            benchmark_version=benchmark.benchmark_version,
            corpus_version=benchmark.corpus_version,
            questions=[benchmark.questions[0], duplicate],
        )
