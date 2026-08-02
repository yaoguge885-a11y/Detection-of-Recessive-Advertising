"""Versioned legal-document contracts independent of the analysis graph."""
from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from ..contracts.verdict import LawEvidence


class LegalSection(BaseModel):
    """One explicitly citable section of a legal or rules document."""

    article_id: str = Field(min_length=1)
    title: str | None = None
    text: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)


class LegalDocument(BaseModel):
    """A source-versioned document ready for deterministic chunking."""

    source_id: str = Field(min_length=1)
    document_title: str = Field(min_length=1)
    source_path_or_url: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    effective_date: date | None = None
    jurisdiction: str | None = None
    authority_level: Literal[
        "law",
        "regulation",
        "platform_rule",
        "case",
        "synthetic_fixture",
    ]
    fixture_only: bool = False
    sections: list[LegalSection] = Field(min_length=1)

    @model_validator(mode="after")
    def article_ids_are_unique(self):
        ids = [section.article_id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("article_id values must be unique within a document")
        if self.authority_level == "synthetic_fixture" and not self.fixture_only:
            raise ValueError("synthetic_fixture documents must set fixture_only")
        return self


class LegalRetriever(Protocol):
    """Stable retrieval boundary shared by Chroma and later backends."""

    def retrieve(self, query: str, top_k: int = 5) -> list[LawEvidence]:
        """Return only citations that exist in the indexed corpus."""
