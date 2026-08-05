"""Immutable index records for externally hosted E-14 references.

E-14 handling is deliberately *index only*.  This package records only the
official outbound reference and the immutable index snapshot that published
it.  It contains no document retrieval, binary cache, OCR, redaction,
derivative, or E-14 transcription capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentType = Literal["e14_delegate", "e14_transmission"]
IndexStatus = Literal["indexed", "unavailable", "ambiguous"]


SourceType = Literal[
    "final_declaration",
    "scrutiny",
    "e14_delegate",
    "e14_transmission",
    "pre_count",
    "contextual_baseline",
]
LegalStatus = Literal[
    "controlling_final", "official_scrutiny", "documentary_evidence", "preliminary", "context_only"
]


class DocumentProvenance(BaseModel):
    """Frozen public Provenance shape used by the API contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_version: str = Field(min_length=1)
    source_type: SourceType
    legal_status: LegalStatus
    source_url: str
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str = Field(min_length=1)
    transform_version: str = Field(min_length=1)
    methodology_version: str | None = None

    @field_validator("source_url")
    @classmethod
    def source_url_is_absolute(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value


class EvidenceDocument(BaseModel):
    """Public E-14 index entry; the document remains only at ``official_url``."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    mesa_id: str = Field(min_length=1)
    document_type: DocumentType
    official_url: str = Field(min_length=1)
    source_index_url: str = Field(min_length=1)
    source_index_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    index_status: IndexStatus = "indexed"
    provenance: DocumentProvenance

    @field_validator("official_url", "source_index_url")
    @classmethod
    def url_is_https_when_present(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("public document URLs must use HTTPS")
        return value


class DocumentIndexEntry(BaseModel):
    """A discovered official URL linked to a canonical mesa already known to ingestion."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    mesa_id: str = Field(min_length=1)
    document_type: DocumentType
    official_url: str
    source_index_url: str
    source_index_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
