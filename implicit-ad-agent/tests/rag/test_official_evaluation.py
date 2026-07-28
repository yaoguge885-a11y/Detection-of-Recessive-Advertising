from pathlib import Path

from impad.rag import evaluate_retriever, load_retrieval_benchmark
from impad.rag.corpus import build_default_legal_retriever


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "legal_rag_official_eval_15.json"
)


def test_official_corpus_retrieval_has_recall_mrr_precision_and_abstention():
    questions = load_retrieval_benchmark(FIXTURE).questions
    metrics = evaluate_retriever(
        build_default_legal_retriever(),
        questions,
        top_k=5,
    )

    assert metrics.total_questions == 15
    assert 0 <= metrics.recall_at_5 <= 1
    assert 0 <= metrics.mrr_at_5 <= 1
    assert 0 <= metrics.citation_precision_at_5 <= 1
    assert 0 <= metrics.false_citation_rate <= 1
    assert metrics.recall_at_5 >= 0.6
    assert metrics.mrr_at_5 >= 0.6
    assert metrics.false_citation_rate == 0
