"""Schema-aligned construction and guarded publication of immutable releases."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from elecciones_pipeline.quality import verify_release
from elecciones_pipeline.quality.release import validate_manifest

from .export import DatasetArtifact
from .pointer import CurrentReleasePointer, activate_current_release


class ReleaseError(ValueError):
    """A candidate cannot be built or published without every release invariant."""


def _https_base(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ReleaseError(f"{label} must be an absolute HTTPS URL")
    return value.rstrip("/")


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReleaseError("created_at must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _localized(value: Mapping[str, str], label: str) -> dict[str, str]:
    result = {locale: value.get(locale, "").strip() for locale in ("es", "en")}
    if not all(result.values()):
        raise ReleaseError(f"{label} requires non-empty es and en values")
    return result


def build_candidate_manifest(
    *,
    release_id: str,
    election_slug: str,
    methodology_version: str,
    created_at: datetime,
    git_commit: str,
    sources: Sequence[Mapping[str, Any]],
    datasets: Sequence[DatasetArtifact],
    artifact_base_url: str,
    dataset_schema_url: str,
    dataset_titles: Mapping[str, Mapping[str, str]],
    notes: Mapping[str, str],
    parser_versions: Mapping[str, str] | None = None,
    dataset_filters: Mapping[str, Mapping[str, str]] | None = None,
    dataset_schema_urls: Mapping[str, str] | None = None,
    synthetic: bool = False,
    aggregate_reconciled: bool = False,
    statistical_validation_passed: bool = False,
    wording_validation_passed: bool = False,
    release_class: Literal["standard", "context_only"] = "standard",
) -> dict[str, Any]:
    """Build one manifest matching the shared release-manifest JSON Schema.

    Real data starts as ``candidate`` and can become ``published`` only through
    :func:`publish_release`. Synthetic data remains a non-publishable fixture.
    """
    if not release_id or not election_slug or not methodology_version or not git_commit:
        raise ReleaseError(
            "release_id, election_slug, methodology_version, and git_commit are required"
        )
    if not sources:
        raise ReleaseError("at least one immutable source is required")
    if not datasets:
        raise ReleaseError("at least one immutable dataset is required")
    artifact_base = _https_base(artifact_base_url, "artifact_base_url")
    schema_url = _https_base(dataset_schema_url, "dataset_schema_url")
    source_items = [deepcopy(dict(item)) for item in sources]
    versions = (
        dict(parser_versions)
        if parser_versions is not None
        else {
            str(source.get("id")): str(source.get("parser_version"))
            for source in source_items
            if source.get("id") and source.get("parser_version")
        }
    )
    filters = dataset_filters or {}
    schema_urls = dataset_schema_urls or {}
    dataset_items: list[dict[str, Any]] = []
    for artifact in sorted(datasets, key=lambda item: (item.name, item.format)):
        title = dataset_titles.get(artifact.name)
        if title is None:
            raise ReleaseError(f"dataset {artifact.name!r} lacks a bilingual title")
        item_filters = filters.get(artifact.name, {})
        item_schema_url = _https_base(
            schema_urls.get(artifact.name, schema_url),
            f"dataset {artifact.name!r} schema_url",
        )
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in item_filters.items()
        ):
            raise ReleaseError(f"dataset {artifact.name!r} filters must be string pairs")
        dataset_items.append(
            {
                "id": f"{artifact.name}-{artifact.format}",
                "title": _localized(title, f"dataset {artifact.name!r} title"),
                "format": artifact.format,
                "url": f"{artifact_base}/{artifact.key}",
                "schema_url": item_schema_url,
                "record_count": artifact.row_count,
                "byte_size": artifact.byte_size,
                "content_hash": artifact.sha256,
                "filters": dict(sorted(item_filters.items())),
            }
        )
    manifest: dict[str, Any] = {
        "$schema": "https://eleccionesabiertas.co/schemas/release-manifest.schema.json",
        "schema_version": "1.0.0",
        "release_id": release_id,
        "election_slug": election_slug,
        "data_version": release_id,
        "status": "fixture" if synthetic else "candidate",
        "release_class": release_class,
        "synthetic": synthetic,
        "created_at": _iso_utc(created_at),
        "methodology_version": methodology_version,
        "parser_versions": dict(sorted(versions.items())),
        "git_commit": git_commit,
        "sources": source_items,
        "datasets": dataset_items,
        "aggregate_reconciled": aggregate_reconciled,
        "statistical_validation_passed": statistical_validation_passed,
        "wording_validation_passed": wording_validation_passed,
        "notes": _localized(notes, "release notes"),
    }
    findings = validate_manifest(manifest)
    if findings:
        raise ReleaseError("; ".join(f"{finding.code}: {finding.detail}" for finding in findings))
    return manifest


def _has_final_declaration(manifest: Mapping[str, Any]) -> bool:
    return any(
        isinstance(source, Mapping)
        and source.get("source_type") == "final_declaration"
        and source.get("legal_status") == "controlling_final"
        and isinstance(source.get("content_hash"), str)
        for source in manifest.get("sources", ())
    )


def _is_context_only_release(manifest: Mapping[str, Any]) -> bool:
    """Return true only for the explicit descriptive-baseline publication class."""
    return manifest.get("release_class") == "context_only"


def publish_release(
    manifest: Mapping[str, Any],
    *,
    facts: Sequence[Mapping[str, Any]],
    directory: Path,
    current_pointer: Path,
    statistical_summary: Mapping[str, Any],
    permanent_wording: str,
    allowed_hosts: set[str],
    public_text: Sequence[str] = (),
    activate: bool = True,
) -> CurrentReleasePointer | None:
    """Validate and publish an immutable release.

    ``context_only`` releases are descriptive baselines, not the active election
    release. They must therefore be explicitly published with ``activate=False``.
    The database exposure workflow remains separately reviewed.
    """
    if manifest.get("status") != "candidate":
        raise ReleaseError("only a real candidate release can be published")
    if manifest.get("synthetic") is True:
        raise ReleaseError("synthetic releases are unpublishable")
    context_only = _is_context_only_release(manifest)
    if context_only and activate:
        raise ReleaseError("context_only releases cannot become the active release")
    if not context_only and not _has_final_declaration(manifest):
        raise ReleaseError("published releases require an immutable final-declaration source")
    published = deepcopy(dict(manifest))
    published["status"] = "published"
    verify_release(
        published,
        facts=facts,
        statistical_summary=statistical_summary,
        permanent_wording=permanent_wording,
        allowed_hosts=allowed_hosts,
        public_text=public_text,
    ).require_passed()
    encoded = json.dumps(
        published,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    release_id = str(published["release_id"])
    target = directory / "manifests" / f"{release_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != encoded:
        raise ReleaseError("an immutable release id already refers to different bytes")
    if not target.exists():
        target.write_bytes(encoded)
    if not activate:
        return None
    pointer = CurrentReleasePointer.create(
        release_id=release_id,
        manifest_path=str(target.relative_to(directory)),
        synthetic=False,
    )
    activate_current_release(current_pointer, pointer)
    return pointer
