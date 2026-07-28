"""Citation-safe legal retrieval interfaces and offline implementations."""

from .contracts import LegalDocument, LegalRetriever, LegalSection
from .corpus import (
    LegalCorpus,
    build_default_legal_retriever,
    load_legal_corpus,
)
from .embeddings import DeterministicHashEmbedding
from .evaluation import (
    LegalRetrievalMetrics,
    LegalRetrievalQuestion,
    evaluate_retriever,
)

__all__ = [
    "DeterministicHashEmbedding",
    "LegalDocument",
    "LegalCorpus",
    "LegalRetrievalMetrics",
    "LegalRetrievalQuestion",
    "LegalRetriever",
    "LegalSection",
    "build_default_legal_retriever",
    "evaluate_retriever",
    "load_legal_corpus",
]
