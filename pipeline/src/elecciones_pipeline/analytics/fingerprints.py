"""Deterministic, source-bound fingerprints for statistical analyzers.

The manifest intentionally records inputs *to* a build fingerprint, never the
fingerprint itself.  That makes the digest stable on repeated imports while
still binding the exact executable sources, schema, interpreter and locked
dependency graph used to produce an artifact.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _relative_source_name(source: Path, root: Path) -> str:
    try:
        return source.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # Temporary source fixtures used to independently reproduce a manifest
        # need an unambiguous name too; callers cannot silently collide paths.
        return source.resolve().as_posix()


def analyzer_build_manifest(
    *,
    analyzer: str,
    artifact_schema_version: str,
    source_files: Iterable[str | Path],
    components: Mapping[str, str],
    lock_file: str | Path | None = None,
    runtime: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Build the canonical non-self-referential analyzer provenance manifest."""
    if not isinstance(analyzer, str) or not analyzer:
        raise ValueError("analyzer must be a non-empty string")
    if not isinstance(artifact_schema_version, str) or not artifact_schema_version:
        raise ValueError("artifact_schema_version must be a non-empty string")
    if not components or any(
        not isinstance(key, str) or not key or not isinstance(value, str) or not value
        for key, value in components.items()
    ):
        raise ValueError("components must be a non-empty mapping of non-empty strings")
    root = _repository_root()
    resolved_lock = Path(lock_file) if lock_file is not None else root / "uv.lock"
    if not resolved_lock.is_file():
        raise ValueError("analyzer fingerprint requires the repository uv.lock")
    resolved_sources = tuple(sorted({Path(item).resolve() for item in source_files}))
    if not resolved_sources or any(not source.is_file() for source in resolved_sources):
        raise ValueError("analyzer fingerprint requires existing source files")
    source_hashes = {
        _relative_source_name(source, root): hashlib.sha256(source.read_bytes()).hexdigest()
        for source in resolved_sources
    }
    if len(source_hashes) != len(resolved_sources):
        raise ValueError("analyzer fingerprint source paths must be unique")
    resolved_runtime = (
        dict(runtime)
        if runtime is not None
        else {
            "implementation": sys.implementation.name,
            "python": ".".join(str(part) for part in sys.version_info[:3]),
        }
    )
    if not resolved_runtime or any(
        not isinstance(key, str) or not key or not isinstance(value, str) or not value
        for key, value in resolved_runtime.items()
    ):
        raise ValueError("runtime must be a non-empty mapping of non-empty strings")
    return {
        "analyzer": analyzer,
        "artifact_schema_version": artifact_schema_version,
        "components": dict(sorted(components.items())),
        "dependency_lock_sha256": hashlib.sha256(resolved_lock.read_bytes()).hexdigest(),
        "runtime": dict(sorted(resolved_runtime.items())),
        "source_sha256": dict(sorted(source_hashes.items())),
    }


def derive_analyzer_fingerprint(
    *,
    analyzer: str,
    artifact_schema_version: str,
    source_files: Iterable[str | Path],
    components: Mapping[str, str],
    lock_file: str | Path | None = None,
    runtime: Mapping[str, str] | None = None,
) -> str:
    """Return the SHA-256 digest of :func:`analyzer_build_manifest`."""
    manifest = analyzer_build_manifest(
        analyzer=analyzer,
        artifact_schema_version=artifact_schema_version,
        source_files=source_files,
        components=components,
        lock_file=lock_file,
        runtime=runtime,
    )
    return hashlib.sha256(_canonical_json(manifest)).hexdigest()
