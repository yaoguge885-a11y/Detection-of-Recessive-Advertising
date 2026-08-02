"""Citation-safe legal retrieval interfaces and offline implementations."""

from .benchmark import (
    LegalRetrievalBenchmark,
    P3RetrievalReport,
    load_retrieval_benchmark,
    run_p3_retrieval_benchmark,
)
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
from .hybrid_retriever import HybridLegalRetriever, tokenize_legal_text

__all__ = [
    "DeterministicHashEmbedding",
    "LegalDocument",
    "LegalCorpus",
    "LegalRetrievalBenchmark",
    "HybridLegalRetriever",
    "LegalRetrievalMetrics",
    "LegalRetrievalQuestion",
    "LegalRetriever",
    "LegalSection",
    "P3RetrievalReport",
    "build_default_legal_retriever",
    "evaluate_retriever",
    "load_legal_corpus",
    "load_retrieval_benchmark",
    "run_p3_retrieval_benchmark",
    "tokenize_legal_text",
]
