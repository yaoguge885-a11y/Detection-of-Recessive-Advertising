"""Citation-safe legal retrieval interfaces and offline implementations."""

from .contracts import LegalDocument, LegalRetriever, LegalSection
from .embeddings import DeterministicHashEmbedding
from .evaluation import (
    LegalRetrievalMetrics,
    LegalRetrievalQuestion,
    evaluate_retriever,
)

__all__ = [
    "DeterministicHashEmbedding",
    "LegalDocument",
    "LegalRetrievalMetrics",
    "LegalRetrievalQuestion",
    "LegalRetriever",
    "LegalSection",
    "evaluate_retriever",
]
