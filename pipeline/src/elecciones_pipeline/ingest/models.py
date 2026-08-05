"""Typed, serialisable ingestion boundary models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class CollectionConfig(BaseModel):
    """Network limits deliberately conservative for official infrastructure."""

    model_config = ConfigDict(frozen=True)

    requests_per_second: float = Field(default=2.0, ge=1.0, le=5.0)
    per_host_concurrency: int = Field(default=2, ge=1, le=2)
    max_attempts: int = Field(default=4, ge=1, le=8)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retry_base_seconds: float = Field(default=0.5, gt=0)
    retry_max_seconds: float = Field(default=30.0, gt=0)


class OfficialEntryPoints(BaseModel):
    """The three reviewed roots from which all discovery begins."""

    model_config = ConfigDict(frozen=True)

    election_configuration: HttpUrl
    nomenclator: HttpUrl
    scrutiny_index: HttpUrl

    @field_validator("nomenclator")
    @classmethod
    def nomenclator_name_is_explicit(cls, value: HttpUrl) -> HttpUrl:
        if not (value.path or "").endswith("nomenclator.json"):
            raise ValueError("nomenclator must point to nomenclator.json")
        return value

    @field_validator("scrutiny_index")
    @classmethod
    def scrutiny_index_is_explicit(cls, value: HttpUrl) -> HttpUrl:
        if not (value.path or "").endswith("data/index.json"):
            raise ValueError("scrutiny_index must point to data/index.json")
        return value

    def urls(self) -> tuple[str, str, str]:
        return (
            str(self.election_configuration),
            str(self.nomenclator),
            str(self.scrutiny_index),
        )


class Snapshot(BaseModel):
    """An immutable stored response, recorded before any parser observes it."""

    model_config = ConfigDict(frozen=True)

    url: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_key: str
    media_type: str
    byte_size: int = Field(ge=0)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    etag: str | None = None
    last_modified: str | None = None
    snapshot_number: int = Field(default=1, ge=1)


class FetchResult(BaseModel):
    """Outcome of a conditional fetch."""

    model_config = ConfigDict(frozen=True)

    status: Literal["fetched", "not_modified"]
    url: str
    snapshot: Snapshot | None = None


class QuarantineRecord(BaseModel):
    url: str
    reason: str
    status_code: int | None = None
    attempts: int = Field(ge=1)
    quarantined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Coverage(BaseModel):
    """Counts use the release-manifest coverage vocabulary."""

    expected: int = Field(default=0, ge=0)
    retrieved: int = Field(default=0, ge=0)
    parsed: int = Field(default=0, ge=0)
    missing: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)
    excluded: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def has_disjoint_terminal_outcomes(self) -> Coverage:
        """A mesa occupies exactly one terminal coverage bucket."""
        if not self.parsed <= self.retrieved <= self.expected:
            raise ValueError("coverage must satisfy parsed <= retrieved <= expected")
        terminal_total = self.parsed + self.missing + self.ambiguous + self.excluded
        if terminal_total != self.expected:
            raise ValueError("parsed + missing + ambiguous + excluded must equal expected")
        return self

    @classmethod
    def from_outcomes(
        cls,
        expected: int,
        retrieved: int,
        parsed: int,
        *,
        ambiguous: int = 0,
        excluded: int = 0,
    ) -> Coverage:
        missing = expected - parsed - ambiguous - excluded
        return cls(
            expected=expected,
            retrieved=retrieved,
            parsed=parsed,
            missing=missing,
            ambiguous=ambiguous,
            excluded=excluded,
        )
