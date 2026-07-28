"""Version-bound, zero-network P3 legal-retrieval reports."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .corpus import LegalCorpus
from .evaluation import (
    LegalRetrievalMetrics,
    LegalRetrievalQuestion,
    evaluate_retriever,
)


class LegalRetrievalBenchmark(BaseModel):
    """A question set explicitly bound to one legal-corpus version."""

    model_config = ConfigDict(extra="forbid")

    benchmark_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    questions: list[LegalRetrievalQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def question_ids_are_unique(self):
        ids = [question.question_id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique")
        return self


class P3RetrievalReport(BaseModel):
    """Auditable indexing and retrieval evidence for one benchmark run."""

    retriever_name: str = Field(min_length=1)
    retriever_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    question_count: int = Field(ge=1)
    indexed_sections: int = Field(ge=1)
    indexing_time_ms: float = Field(ge=0)
    evaluation_time_ms: float = Field(ge=0)
    generated_at: datetime
    deterministic_config: dict[str, str | int | float | bool]
    metrics: LegalRetrievalMetrics


def load_retrieval_benchmark(path: Path) -> LegalRetrievalBenchmark:
    """Load only the explicit version-bound benchmark object schema."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LegalRetrievalBenchmark.model_validate(payload)


def run_p3_retrieval_benchmark(
    corpus: LegalCorpus,
    benchmark: LegalRetrievalBenchmark,
    *,
    top_k: int = 5,
    minimum_score: float = 0.34,
) -> P3RetrievalReport:
    """Build the deterministic hybrid retriever and evaluate one benchmark."""

    if benchmark.corpus_version != corpus.corpus_version:
        raise ValueError(
            f"benchmark expects corpus {benchmark.corpus_version}, "
            f"got {corpus.corpus_version}"
        )

    from .chroma_retriever import ChromaLegalRetriever
    from .hybrid_retriever import HybridLegalRetriever

    collection_suffix = hashlib.sha256(
        corpus.corpus_version.encode("utf-8")
    ).hexdigest()[:16]
    indexing_started = time.perf_counter()
    vector_retriever = ChromaLegalRetriever(
        collection_name=f"p3_benchmark_{collection_suffix}",
        dimensions=256,
        minimum_score=minimum_score,
    )
    vector_retriever.index_documents(corpus.documents)
    retriever = HybridLegalRetriever(corpus.documents, vector_retriever)
    indexing_time_ms = (time.perf_counter() - indexing_started) * 1000

    evaluation_started = time.perf_counter()
    metrics = evaluate_retriever(
        retriever,
        benchmark.questions,
        top_k=top_k,
    )
    evaluation_time_ms = (time.perf_counter() - evaluation_started) * 1000

    return P3RetrievalReport(
        retriever_name="chroma_lexical_rrf",
        retriever_version="hybrid_rrf_v1",
        corpus_version=corpus.corpus_version,
        benchmark_version=benchmark.benchmark_version,
        question_count=len(benchmark.questions),
        indexed_sections=sum(
            len(document.sections) for document in corpus.documents
        ),
        indexing_time_ms=indexing_time_ms,
        evaluation_time_ms=evaluation_time_ms,
        generated_at=datetime.now(timezone.utc),
        deterministic_config={
            "top_k": top_k,
            "minimum_score": minimum_score,
            "rrf_k": 60,
            "vector_candidates": 10,
            "external_embedding": False,
        },
        metrics=metrics,
    )
