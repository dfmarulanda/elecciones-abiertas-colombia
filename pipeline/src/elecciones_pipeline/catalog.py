"""Validated access to the reviewed official-source catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class CatalogError(ValueError):
    """The checked-in source catalog is incomplete or internally inconsistent."""


class CollectionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_concurrency_per_host: int = Field(ge=1, le=2)
    requests_per_second_minimum: float = Field(ge=2, le=5)
    requests_per_second_maximum: float = Field(ge=2, le=5)
    require_https: Literal[True]
    follow_retry_after: Literal[True]
    conditional_requests: Literal[True]
    raw_bytes_before_parse: Literal[True]

    @model_validator(mode="after")
    def ordered_rate_bounds(self) -> CollectionPolicy:
        if self.requests_per_second_minimum > self.requests_per_second_maximum:
            raise ValueError("minimum request rate cannot exceed maximum request rate")
        return self


class CatalogSource(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    id: str
    role: str
    legal_status: str
    entrypoints: dict[str, str]
    election_id: str | None = None
    election_sigla: str | None = None


class ContextualSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    role: Literal["context_only"]
    url: HttpUrl


class SourceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_ref: str | None = Field(default=None, alias="$schema")
    catalog_version: str
    election_slug: str
    verified_at: str
    publication_state: Literal[
        "awaiting_verified_final_declaration", "ready_for_candidate_release"
    ]
    official_hub: HttpUrl
    collection_policy: CollectionPolicy
    allowed_hosts: list[str] = Field(min_length=1)
    sources: list[CatalogSource] = Field(min_length=1)
    contextual_sources: list[ContextualSource]

    @model_validator(mode="after")
    def all_entrypoint_hosts_are_reviewed(self) -> SourceCatalog:
        allowed = set(self.allowed_hosts)
        for source in self.sources:
            for raw_url in source.entrypoints.values():
                candidate = raw_url.replace("{mesa-id}", "verified-mesa-id")
                parsed = urlsplit(candidate)
                if parsed.scheme != "https" or parsed.hostname not in allowed:
                    raise ValueError(f"source {source.id} has an unreviewed entrypoint")
        for contextual_source in self.contextual_sources:
            if contextual_source.url.host not in allowed:
                raise ValueError(
                    f"contextual source {contextual_source.id} has an unreviewed host"
                )
        return self

    def source(self, source_id: str) -> CatalogSource:
        try:
            return next(item for item in self.sources if item.id == source_id)
        except StopIteration as exc:
            raise CatalogError(f"source {source_id!r} is absent from the catalog") from exc

    def precount_source(self) -> CatalogSource:
        """Return the one reviewed structured pre-count source.

        The source identity and electoral identifiers are catalog data so a
        reviewed round can never silently inherit another round's host or
        election settings.
        """
        matches = [source for source in self.sources if source.role == "preliminary_precount"]
        if len(matches) != 1:
            raise CatalogError("catalog must declare exactly one preliminary pre-count source")
        source = matches[0]
        required = {
            "configuration": source.entrypoints.get("configuration"),
            "nomenclator": source.entrypoints.get("nomenclator"),
            "national_results": source.entrypoints.get("national_results"),
            "mesa_results_template": source.entrypoints.get("mesa_results_template"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise CatalogError(f"pre-count source {source.id} is missing: {', '.join(missing)}")
        return source

    def scrutiny_source(self) -> CatalogSource | None:
        """Return the declared structured scrutiny source, if the catalog has one."""
        matches = [
            source
            for source in self.sources
            if source.role == "legally_valid_scrutiny_by_published_grain"
        ]
        if len(matches) > 1:
            raise CatalogError("catalog declares more than one structured scrutiny source")
        return matches[0] if matches else None

    def final_declaration_source(self) -> CatalogSource | None:
        """Return the controlling final-declaration reference, if catalogued.

        This is metadata only.  The collector never dereferences the linked
        E-24/E-26/CNE document through this accessor.
        """
        matches = [
            source for source in self.sources if source.role == "controlling_final_declaration"
        ]
        if len(matches) > 1:
            raise CatalogError("catalog declares more than one final declaration source")
        return matches[0] if matches else None

    def precount_entrypoints(self) -> dict[str, str]:
        """Return only the roots required by preliminary pre-count ingestion.

        Scrutiny, documentary, and final sources remain excluded even when
        those roles coexist in the same election catalog.
        """
        source = self.precount_source()
        required = {
            "precount_configuration": source.entrypoints.get("configuration"),
            "precount_nomenclator": source.entrypoints.get("nomenclator"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise CatalogError(f"required pre-count entrypoints are missing: {', '.join(missing)}")
        return {name: value for name, value in required.items() if value}

    def manifest_entrypoints(self) -> dict[str, str]:
        """Return reviewed crawl roots, including scrutiny only when declared.

        A reviewed pre-count-only catalog has configuration and nomenclator
        roots but no structured scrutiny manifest. Once a structured scrutiny
        source is declared, its explicit manifest remains mandatory.
        """
        scrutiny = self.scrutiny_source()
        required = self.precount_entrypoints()
        if scrutiny is not None:
            manifest = scrutiny.entrypoints.get("manifest")
            if not manifest:
                raise CatalogError("required entrypoints are missing: scrutiny_manifest")
            required["scrutiny_manifest"] = manifest
        return required


def load_source_catalog(path: Path) -> SourceCatalog:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot load source catalog {path}: {exc}") from exc
    try:
        return SourceCatalog.model_validate(payload)
    except ValueError as exc:
        raise CatalogError(f"invalid source catalog {path}: {exc}") from exc
