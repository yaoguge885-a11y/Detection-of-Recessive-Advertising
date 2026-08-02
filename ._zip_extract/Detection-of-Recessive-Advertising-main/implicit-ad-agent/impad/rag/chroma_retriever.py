"""Citation-safe Chroma retrieval with explicit offline embeddings."""
from __future__ import annotations

import hashlib
from typing import Iterable

import chromadb
from chromadb.config import Settings

from ..contracts.verdict import LawEvidence
from .contracts import LegalDocument
from .embeddings import DeterministicHashEmbedding


class CitationGuard:
    """Reject citations that do not exactly match an indexed section."""

    def __init__(self, allowed_quotes: dict[tuple[str, str, str], str]):
        self._allowed_quotes = dict(allowed_quotes)

    @classmethod
    def from_documents(cls, documents: Iterable[LegalDocument]):
        return cls({
            (
                document.source_id,
                document.document_version,
                section.article_id,
            ): section.text
            for document in documents
            for section in document.sections
        })

    def validate(self, evidence: list[LawEvidence]) -> None:
        for item in evidence:
            key = (
                item.source_id,
                item.document_version or "",
                item.article_id or "",
            )
            if self._allowed_quotes.get(key) != item.quote:
                raise ValueError("citation does not match an indexed section")


class ChromaLegalRetriever:
    """Offline Chroma baseline that never invokes a hosted embedding model."""

    def __init__(
        self,
        *,
        collection_name: str = "implicit_ad_legal_rules",
        dimensions: int = 256,
        minimum_score: float = 0.25,
    ):
        if not 0 <= minimum_score <= 1:
            raise ValueError("minimum_score must be between 0 and 1")
        self.minimum_score = minimum_score
        self.embedding = DeterministicHashEmbedding(dimensions)
        self._client = chromadb.EphemeralClient(settings=Settings(
            anonymized_telemetry=False,
        ))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )
        self._guard = CitationGuard({})
        self._documents: dict[str, LegalDocument] = {}
        self._chunk_ids_by_source: dict[str, set[str]] = {}

    @property
    def uses_external_embedding(self) -> bool:
        return False

    def count(self) -> int:
        return self._collection.count()

    @staticmethod
    def _chunk_id(
        source_id: str,
        document_version: str,
        article_id: str,
    ) -> str:
        raw = f"{source_id}:{document_version}:{article_id}".encode("utf-8")
        return f"legal_{hashlib.sha256(raw).hexdigest()}"

    def index_documents(self, documents: list[LegalDocument]) -> int:
        source_ids = [document.source_id for document in documents]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id values must be unique in one batch")
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str | bool]] = []
        for document in documents:
            document_chunk_ids = {
                self._chunk_id(
                    document.source_id,
                    document.document_version,
                    section.article_id,
                )
                for section in document.sections
            }
            obsolete_ids = (
                self._chunk_ids_by_source.get(document.source_id, set())
                - document_chunk_ids
            )
            if obsolete_ids:
                self._collection.delete(ids=sorted(obsolete_ids))
            self._chunk_ids_by_source[document.source_id] = (
                document_chunk_ids
            )
            self._documents[document.source_id] = document
            for section in document.sections:
                ids.append(self._chunk_id(
                    document.source_id,
                    document.document_version,
                    section.article_id,
                ))
                texts.append(section.text)
                metadata: dict[str, str | bool] = {
                    "source_id": document.source_id,
                    "document_title": document.document_title,
                    "source_path_or_url": document.source_path_or_url,
                    "document_version": document.document_version,
                    "article_id": section.article_id,
                    "authority_level": document.authority_level,
                    "fixture_only": document.fixture_only,
                }
                if document.effective_date is not None:
                    metadata["effective_date"] = (
                        document.effective_date.isoformat()
                    )
                if document.jurisdiction is not None:
                    metadata["jurisdiction"] = document.jurisdiction
                metadatas.append(metadata)
        if ids:
            self._collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
                embeddings=self.embedding.embed_many(texts),
            )
        self._guard = CitationGuard.from_documents(self._documents.values())
        return len(ids)

    def retrieve(self, query: str, top_k: int = 5) -> list[LawEvidence]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not query.strip() or self.count() == 0:
            return []
        response = self._collection.query(
            query_embeddings=[self.embedding.embed(query)],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        evidence: list[LawEvidence] = []
        for quote, metadata, distance in zip(
            documents,
            metadatas,
            distances,
        ):
            if quote is None or metadata is None:
                continue
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            if score < self.minimum_score:
                continue
            evidence.append(LawEvidence(
                source_id=str(metadata["source_id"]),
                document_title=str(metadata["document_title"]),
                source_path_or_url=str(metadata["source_path_or_url"]),
                article_id=str(metadata["article_id"]),
                document_version=str(metadata["document_version"]),
                jurisdiction=(
                    str(metadata["jurisdiction"])
                    if "jurisdiction" in metadata
                    else None
                ),
                effective_date=metadata.get("effective_date"),
                quote=quote,
                retrieval_score=score,
                limitations=(
                    ["Synthetic fixture; not legal advice."]
                    if bool(metadata.get("fixture_only"))
                    else []
                ),
            ))
        self._guard.validate(evidence)
        return evidence
