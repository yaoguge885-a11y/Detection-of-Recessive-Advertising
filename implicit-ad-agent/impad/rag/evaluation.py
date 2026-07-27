"""Offline retrieval metrics without answer generation."""
from __future__ import annotations

import math
import time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .contracts import LegalRetriever


QuestionCategory = Literal["direct", "cross_document", "abstention"]


class LegalRetrievalQuestion(BaseModel):
    """One expected-citation query in the offline benchmark."""

    question_id: str = Field(min_length=1)
    category: QuestionCategory
    query: str = Field(min_length=1)
    expected_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def expected_keys_match_category(self):
        if self.category == "abstention" and self.expected_keys:
            raise ValueError("abstention questions cannot expect citations")
        if self.category != "abstention" and not self.expected_keys:
            raise ValueError("answerable questions require expected citations")
        if len(self.expected_keys) != len(set(self.expected_keys)):
            raise ValueError("expected_keys must be unique")
        return self


class LegalRetrievalQuestionResult(BaseModel):
    """Observed citations and metrics for one benchmark question."""

    question_id: str
    category: QuestionCategory
    expected_keys: list[str]
    retrieved_keys: list[str]
    recall: float = Field(ge=0, le=1)
    reciprocal_rank: float = Field(ge=0, le=1)
    false_citation: bool
    latency_ms: float = Field(ge=0)


class LegalRetrievalMetrics(BaseModel):
    """Aggregate retrieval and abstention metrics."""

    total_questions: int = Field(ge=0)
    answerable_questions: int = Field(ge=0)
    abstention_questions: int = Field(ge=0)
    recall_at_5: float = Field(ge=0, le=1)
    mrr_at_5: float = Field(ge=0, le=1)
    citation_precision_at_5: float = Field(ge=0, le=1)
    direct_recall_at_5: float = Field(ge=0, le=1)
    cross_document_recall_at_5: float = Field(ge=0, le=1)
    false_citation_rate: float = Field(ge=0, le=1)
    answerable_coverage: float = Field(ge=0, le=1)
    p95_latency_ms: float = Field(ge=0)
    results: list[LegalRetrievalQuestionResult] = Field(default_factory=list)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def evaluate_retriever(
    retriever: LegalRetriever,
    questions: list[LegalRetrievalQuestion],
    *,
    top_k: int = 5,
) -> LegalRetrievalMetrics:
    """Run retrieval only and compute citation recall/abstention metrics."""

    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    results: list[LegalRetrievalQuestionResult] = []
    for question in questions:
        started = time.perf_counter()
        evidence = retriever.retrieve(question.query, top_k=top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved_keys = list(dict.fromkeys(
            f"{item.source_id}#{item.article_id}"
            for item in evidence
            if item.article_id is not None
        ))
        expected = set(question.expected_keys)
        retrieved = set(retrieved_keys)
        recall = (
            len(expected & retrieved) / len(expected)
            if expected
            else 0.0
        )
        false_citation = (
            question.category == "abstention" and bool(retrieved_keys)
        )
        relevant_ranks = [
            index + 1
            for index, key in enumerate(retrieved_keys)
            if key in expected
        ]
        results.append(LegalRetrievalQuestionResult(
            question_id=question.question_id,
            category=question.category,
            expected_keys=question.expected_keys,
            retrieved_keys=retrieved_keys,
            recall=recall,
            reciprocal_rank=(
                1.0 / min(relevant_ranks) if relevant_ranks else 0.0
            ),
            false_citation=false_citation,
            latency_ms=latency_ms,
        ))

    answerable = [
        result for result in results if result.category != "abstention"
    ]
    abstention = [
        result for result in results if result.category == "abstention"
    ]
    direct = [
        result for result in results if result.category == "direct"
    ]
    cross_document = [
        result
        for result in results
        if result.category == "cross_document"
    ]
    return LegalRetrievalMetrics(
        total_questions=len(results),
        answerable_questions=len(answerable),
        abstention_questions=len(abstention),
        recall_at_5=_mean([result.recall for result in answerable]),
        mrr_at_5=_mean([
            result.reciprocal_rank for result in answerable
        ]),
        citation_precision_at_5=_mean([
            (
                len(set(result.expected_keys) & set(result.retrieved_keys))
                / len(result.retrieved_keys)
                if result.retrieved_keys
                else 0.0
            )
            for result in answerable
        ]),
        direct_recall_at_5=_mean([result.recall for result in direct]),
        cross_document_recall_at_5=_mean([
            result.recall for result in cross_document
        ]),
        false_citation_rate=_mean([
            1.0 if result.false_citation else 0.0
            for result in abstention
        ]),
        answerable_coverage=_mean([
            1.0 if result.recall > 0 else 0.0
            for result in answerable
        ]),
        p95_latency_ms=_p95([result.latency_ms for result in results]),
        results=results,
    )
