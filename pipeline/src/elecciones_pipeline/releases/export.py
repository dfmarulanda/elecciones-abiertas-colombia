"""Byte-accounted, deterministic exports for normalized release datasets."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetArtifact:
    name: str
    format: str
    key: str
    sha256: str
    row_count: int
    byte_size: int
    schema: tuple[tuple[str, str], ...]

    def manifest_item(self) -> dict[str, Any]:
        return asdict(self) | {"schema": [list(item) for item in self.schema]}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalise_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not all(isinstance(row, Mapping) for row in rows):
        raise ExportError("dataset rows must be mappings")
    columns = sorted({str(key) for row in rows for key in row})
    normalised = [{key: row.get(key) for key in columns} for row in rows]
    return sorted(normalised, key=_canonical)


def _schema(table: pa.Table) -> tuple[tuple[str, str], ...]:
    return tuple((field.name, str(field.type)) for field in table.schema)


def _write(path: Path, table: pa.Table, format_name: str) -> None:
    if format_name == "json":
        rows = table.to_pylist()
        path.write_text(
            "\n".join(_canonical(row) for row in rows) + ("\n" if rows else ""), "utf-8"
        )
    elif format_name == "csv":
        import polars as pl

        frame = cast(pl.DataFrame, pl.from_arrow(table))
        frame.write_csv(path, include_header=True, float_scientific=None)
    elif format_name == "parquet":
        # No created-by timestamps or arbitrary pandas metadata are added.
        pq.write_table(table, path, compression="zstd", compression_level=3, version="2.6")
    else:
        raise ExportError(f"unsupported export format {format_name!r}")


def export_dataset(
    rows: Sequence[Mapping[str, Any]], *, name: str, directory: Path, format: str
) -> DatasetArtifact:
    """Export sorted rows under a SHA-256 key; an existing matching object is reused."""
    if not name or "/" in name or ".." in name:
        raise ExportError("dataset name must be a simple identifier")
    if format not in {"json", "csv", "parquet"}:
        raise ExportError("format must be json, csv, or parquet")
    normalised = _normalise_rows(rows)
    table = pa.Table.from_pylist(normalised)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{name}.{format}.tmp"
    _write(temporary, table, format)
    raw = temporary.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    target = directory / "datasets" / name / f"{digest}.{format}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != raw:
        raise ExportError(f"content-addressed object collision at {target}")
    if not target.exists():
        temporary.replace(target)
    else:
        temporary.unlink()
    return DatasetArtifact(
        name=name,
        format=format,
        key=str(target.relative_to(directory)),
        sha256=digest,
        row_count=table.num_rows,
        byte_size=len(raw),
        schema=_schema(table),
    )
