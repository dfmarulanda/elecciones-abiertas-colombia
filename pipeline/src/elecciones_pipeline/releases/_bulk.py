"""Loader-agnostic bulk primitives shared by every immutable release loader.

Nothing here knows about a particular election year, id scheme, or artifact
layout.  These are the pieces that must behave identically no matter which
release is being loaded: bounded Parquet reading, manifest artifact
verification, scalar coercion that refuses to guess, and COPY into the staging
tables.  Year-specific validation deliberately stays in the loader that owns it
so that generalising one loader can never quietly relax another's assertions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from sqlalchemy import Connection


class ReleaseLoadError(ValueError):
    pass


# A source's legal weight is a property of what kind of document it is, never a
# free choice of the loader.
_PAIR = {
    "contextual_baseline": "context_only",
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "pre_count": "preliminary",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
}
_LEVEL_RANK = {
    "national": 0,
    "department": 1,
    "municipality": 2,
    "zone": 3,
    "polling_place": 4,
    "mesa": 5,
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _parquet(path: Path, required: set[str]) -> pq.ParquetFile:
    """Open and schema-check an artifact without decoding its rows."""
    try:
        artifact = pq.ParquetFile(path)
    except (OSError, ValueError, pq.ArrowException) as exc:
        raise ReleaseLoadError(f"cannot read {path.name} as Parquet") from exc
    if not required.issubset(set(artifact.schema_arrow.names)):
        raise ReleaseLoadError(f"{path.name} lacks required columns")
    if artifact.metadata is None or artifact.metadata.num_rows < 0:
        raise ReleaseLoadError(f"{path.name} has no valid Parquet row metadata")
    return artifact


def _batches(path: Path, required: set[str], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    artifact = _parquet(path, required)
    for batch in artifact.iter_batches(batch_size=batch_size):
        # Bounded conversion: never read a complete artifact into Python.
        yield batch.to_pylist()


def _artifact(manifest: dict[str, Any], release_directory: Path, needle: str) -> tuple[Path, int]:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        raise ReleaseLoadError("manifest datasets must be a list")
    matches = [
        item for item in datasets if isinstance(item, dict) and needle in str(item.get("id"))
    ]
    if len(matches) != 1:
        raise ReleaseLoadError(f"manifest must contain exactly one {needle} artifact")
    entry = matches[0]
    expected_rows = entry.get("record_count")
    expected_size = entry.get("byte_size")
    expected_hash = entry.get("content_hash")
    if (
        not isinstance(expected_rows, int)
        or expected_rows < 0
        or not isinstance(expected_size, int)
        or expected_size < 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        raise ReleaseLoadError(f"invalid {needle} artifact metadata")
    paths = list(release_directory.glob(f"*{needle.replace('-parquet', '')}*.parquet"))
    if len(paths) != 1:
        raise ReleaseLoadError(f"expected exactly one local {needle} artifact")
    digest = hashlib.sha256()
    size = 0
    with paths[0].open("rb") as artifact:
        while chunk := artifact.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ReleaseLoadError(f"artifact hash/size mismatch: {paths[0].name}")
    return paths[0], expected_rows


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseLoadError(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    # bool is an int subclass and must not silently become a vote/round.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReleaseLoadError(f"{label} must be an integer")
    return value


def _timestamp(value: object, label: str) -> datetime:
    raw = _require_string(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseLoadError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ReleaseLoadError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _copy_rows(connection: Connection, copy_sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    """COPY a bounded row iterable through SQLAlchemy's active psycopg transaction."""
    driver_connection: Any = connection.connection.driver_connection
    try:
        cursor: Any = driver_connection.cursor()
        with cursor.copy(copy_sql) as copy:
            for row in rows:
                copy.write_row(row)
        cursor.close()
    except AttributeError as exc:
        raise ReleaseLoadError(
            "historical PostgreSQL loader requires a psycopg COPY connection"
        ) from exc


def _copy_geography(
    connection: Connection,
    release_id: str,
    rows: list[tuple[Any, ...]],
    mesas: list[tuple[Any, ...]],
    *,
    geography_table: str,
    mesa_table: str,
) -> None:
    if rows:
        _copy_rows(
            connection,
            f"COPY {geography_table} "
            "(release_id,election_slug,id,level,code,name,parent_id,canonical_path) FROM STDIN",
            ((release_id, *row) for row in rows),
        )
    if mesas:
        _copy_rows(
            connection,
            f"COPY {mesa_table} "
            "(release_id,election_slug,id,display_number,polling_place_id,municipality_id,"
            "department_id) FROM STDIN",
            ((release_id, *row) for row in mesas),
        )


def _copy_result_batch(
    connection: Connection,
    release_id: str,
    facts: list[tuple[Any, ...]],
    categories: list[tuple[Any, ...]],
    *,
    fact_table: str,
    category_table: str,
) -> None:
    if not facts:
        return
    _copy_rows(
        connection,
        f"COPY {fact_table} "
        "(release_id,election_slug,id,geography_id,geography_level,mesa_id,source_id,metrics) "
        "FROM STDIN",
        ((release_id, *row) for row in facts),
    )
    if categories:
        _copy_rows(
            connection,
            f"COPY {category_table} "
            "(release_id,election_slug,result_fact_id,category_key,category_code,category_name,"
            "category_kind,votes,status) "
            "FROM STDIN",
            ((release_id, *row) for row in categories),
        )
