"""Load the versioned official legal corpus used by the P3 baseline."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .contracts import LegalDocument


DEFAULT_CORPUS_PATH = Path(__file__).with_name("data") / "legal_corpus_v1.json"


class LegalCorpus(BaseModel):
    corpus_version: str = Field(min_length=1)
    documents: list[LegalDocument] = Field(min_length=1)


def load_legal_corpus(path: Path | None = None) -> LegalCorpus:
    selected = path or DEFAULT_CORPUS_PATH
    payload = json.loads(selected.read_text(encoding="utf-8"))
    return LegalCorpus.model_validate(payload)


def build_default_legal_retriever(
    *,
    minimum_score: float = 0.34,
):
    from .chroma_retriever import ChromaLegalRetriever

    corpus = load_legal_corpus()
    retriever = ChromaLegalRetriever(
        collection_name="implicit_ad_official_legal_v1",
        dimensions=256,
        minimum_score=minimum_score,
    )
    retriever.index_documents(corpus.documents)
    return retriever
