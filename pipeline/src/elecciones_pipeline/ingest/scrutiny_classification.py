"""Classify already-crawled scrutiny JSON without creating election facts.

The Registraduría scrutiny crawl is an immutable, content-addressed input.  This
module reads that input only, records a schema-bound checkpoint in a separate
state directory, and deliberately limits output to operational metadata and a
small allowlisted document index.  It never follows a payload URL and it never
derives vote totals from progress or aggregate material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

CLASSIFIER_VERSION = "scrutiny-classification@2"
_CATEGORY_ALLOWLIST = frozenset(
    {
        "actas-documentos",
        "actas-publicadas",
        "avance-actas",
        "comision",
        "comisiones",
        "divipole",
        "documentos-publicados",
        "estadisticas",
    }
)
_COVERAGE_FIELDS = (
    "expected",
    "retrieved",
    "classified",
    "unclassified",
    "ambiguous",
    "excluded",
    "quarantined",
)
ClassificationKind = Literal["document_index", "metadata", "raw_unclassified"]


class ScrutinyClassificationError(RuntimeError):
    """The raw crawl cannot safely be classified or checkpointed."""


@dataclass(frozen=True)
class PayloadClassification:
    """A schema-only assessment; no election result facts are represented."""

    kind: ClassificationKind
    reason: str
    schema_fingerprint: str
    unknown_keys: tuple[str, ...]


@dataclass(frozen=True)
class ScrutinyClassificationReport:
    snapshot_id: str
    input_plan_id: str
    input_hash: str
    classifier_version: str
    result_facts: int
    document_index_entries: int
    categories: dict[str, dict[str, object]]
    overall: dict[str, int]


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _schema_digest(value: object) -> str:
    """Hash recursive key/type shape only; values, including PII, never enter it."""
    kind = _json_type(value)
    digest = hashlib.sha256()
    digest.update(kind.encode("ascii"))
    digest.update(b"\0")
    if isinstance(value, Mapping):
        for key in sorted(value):
            if not isinstance(key, str):
                raise ScrutinyClassificationError("JSON object key is not a string")
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
            digest.update(_schema_digest(value[key]).encode("ascii"))
            digest.update(b"\0")
    elif isinstance(value, list):
        for child in sorted({_schema_digest(item) for item in value}):
            digest.update(child.encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()


def schema_fingerprint(value: object) -> str:
    """Return a deterministic recursive schema fingerprint with no data values."""
    return f"sha256:{_schema_digest(value)}"


def _is_exact_record(value: object, fields: Mapping[str, type[object]]) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        return False
    return all(type(value[key]) is expected for key, expected in fields.items())


_ACTAS_FIELDS: Mapping[str, type[object]] = {
    "digitalizado": int,
    "escrutado": bool,
    "id_informacion_mesa_corporacion": str,
    "nombre_archivo": str,
    "numero": int,
}
_ACTAS_PUBLICADAS_FIELDS: Mapping[str, type[object]] = {
    "corId": str,
    "mesasEscrutadas": int,
    "mesasFaltantes": int,
    "mesasInstaladas": int,
    "nombreCor": str,
    "porcentajeEscrutadas": float,
    "porcentajeFaltantes": float,
}
_AVANCE_FIELDS: Mapping[str, type[object]] = {
    "codigo": str,
    "digitalizado": int,
    "escrutado": int,
    "etiqueta": str,
    "presenta_sub_comisiones": bool,
    "total": int,
}
_COMISIONES_FIELDS: Mapping[str, type[object]] = {
    "comsom_id": int,
    "nombre": str,
    "presenta_sub_comisiones": int,
    "ticom_id": str,
    "total": int,
    "total_en_proceso": int,
    "total_en_receso": int,
    "total_finalizada": int,
}
_DOCUMENTOS_MINIMAL_FIELDS: Mapping[str, type[object]] = {
    "codigo": int,
    "idComision": int,
    "nivel": str,
    "publicado": int,
    "tipoDocumento": str,
    "urlArchivo": str,
}
_DOCUMENTOS_FULL_FIELDS: Mapping[str, type[object]] = {
    **_DOCUMENTOS_MINIMAL_FIELDS,
    "eleccion": str,
    "nombreDocumento": str,
}
_DOCUMENTOS_FULL_WITH_CORPORATION_FIELDS: Mapping[str, type[object]] = {
    **_DOCUMENTOS_FULL_FIELDS,
    "tipoCorporacion": str,
}
_ESTADISTICAS_FIELDS: Mapping[str, type[object]] = {
    "comisiones": int,
    "finalizadas": int,
    "instaladas": int,
    "procesadas": int,
}


def _row_unknown_keys(value: object, allowed: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    return tuple(sorted(str(key) for key in set(value) - set(allowed)))


def _records_classification(
    payload: object,
    fields: Mapping[str, type[object]] | tuple[Mapping[str, type[object]], ...],
    reason: str,
    *,
    document_index: bool = False,
) -> PayloadClassification:
    fingerprint = schema_fingerprint(payload)
    variants = fields if isinstance(fields, tuple) else (fields,)
    if not isinstance(payload, list):
        return PayloadClassification("raw_unclassified", "ROOT_NOT_ARRAY", fingerprint, ())
    if not payload:
        return PayloadClassification("metadata", "EMPTY_PUBLISHED_COLLECTION", fingerprint, ())
    if all(any(_is_exact_record(row, variant) for variant in variants) for row in payload):
        return PayloadClassification(
            "document_index" if document_index else "metadata", reason, fingerprint, ()
        )
    unknown = sorted(
        {key for row in payload for variant in variants for key in _row_unknown_keys(row, variant)}
    )
    return PayloadClassification(
        "raw_unclassified", "SCHEMA_NOT_RECOGNIZED", fingerprint, tuple(unknown)
    )


def _is_mapping_of_mappings(payload: object) -> bool:
    return isinstance(payload, Mapping) and all(
        isinstance(value, Mapping) for value in payload.values()
    )


def classify_scrutiny_payload(category: str, payload: object) -> PayloadClassification:
    """Classify one payload with category-specific, non-result allowlists.

    No branch returns a vote/result classification.  In particular, counts in
    the public progress endpoints are operational coverage, not election facts.
    """
    fingerprint = schema_fingerprint(payload)
    if category not in _CATEGORY_ALLOWLIST:
        return PayloadClassification(
            "raw_unclassified", "CATEGORY_NOT_ALLOWLISTED", fingerprint, ()
        )
    if category == "actas-documentos":
        return _records_classification(
            payload,
            _ACTAS_FIELDS,
            "ACTAS_DOCUMENT_METADATA_EXACT_ALLOWLIST",
            document_index=True,
        )
    if category == "actas-publicadas":
        return _records_classification(
            payload, _ACTAS_PUBLICADAS_FIELDS, "OPERATIONAL_PROGRESS_METADATA"
        )
    if category == "avance-actas":
        return _records_classification(payload, _AVANCE_FIELDS, "OPERATIONAL_PROGRESS_METADATA")
    if category == "comisiones":
        return _records_classification(payload, _COMISIONES_FIELDS, "OPERATIONAL_PROGRESS_METADATA")
    if category == "documentos-publicados":
        return _records_classification(
            payload,
            (
                _DOCUMENTOS_MINIMAL_FIELDS,
                _DOCUMENTOS_FULL_FIELDS,
                _DOCUMENTOS_FULL_WITH_CORPORATION_FIELDS,
            ),
            "PUBLISHED_DOCUMENT_METADATA",
        )
    if category == "estadisticas":
        if _is_exact_record(payload, _ESTADISTICAS_FIELDS):
            return PayloadClassification(
                "metadata", "OPERATIONAL_PROGRESS_METADATA", fingerprint, ()
            )
        return PayloadClassification("raw_unclassified", "SCHEMA_NOT_RECOGNIZED", fingerprint, ())
    if category == "comision":
        if _is_mapping_of_mappings(payload):
            return PayloadClassification(
                "metadata", "COMMISSION_DIRECTORY_METADATA", fingerprint, ()
            )
        return PayloadClassification("raw_unclassified", "SCHEMA_NOT_RECOGNIZED", fingerprint, ())
    # divipole has codes as dynamic object keys, so only fixed root labels are allowlisted.
    if isinstance(payload, Mapping) and set(payload) == {"corporaciones", "departamentos"}:
        return PayloadClassification("metadata", "GEOGRAPHIC_DIRECTORY_METADATA", fingerprint, ())
    unknown = _row_unknown_keys(payload, {"corporaciones", "departamentos"})
    return PayloadClassification("raw_unclassified", "SCHEMA_NOT_RECOGNIZED", fingerprint, unknown)


def _document_rows(
    payload: object, *, source_url: str, source_path: str, source_hash: str
) -> Iterator[dict[str, object]]:
    """Yield only explicit, allowlisted E-14 document metadata; never dereference it."""
    if not isinstance(payload, list):
        return
    for row in payload:
        if not _is_exact_record(row, _ACTAS_FIELDS):
            raise ScrutinyClassificationError("actas document index requires exact allowlist")
        record = cast(Mapping[str, object], row)
        reference = cast(str, record["nombre_archivo"])
        if not reference:
            continue
        # Keep the published reference verbatim.  Do not make an absolute URL,
        # infer an endpoint, or perform a request.
        yield {
            "source_url": source_url,
            "source_path": source_path,
            "source_content_hash": source_hash,
            "mesa_id": record["id_informacion_mesa_corporacion"],
            "document_reference": reference,
            "document_number": record["numero"],
            "digitalized": record["digitalizado"],
            "scrutinized": record["escrutado"],
        }


@contextmanager
def _read_raw_ledger(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_file():
        raise ScrutinyClassificationError(f"raw scrutiny ledger does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.absolute()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ScrutinyClassificationError(f"immutable classification artifact differs: {path}")
        return
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ScrutinyClassificationError(
                f"immutable classification artifact differs: {path}"
            ) from None
        return
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


class _ClassificationLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    input_hash TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    classifier_version TEXT NOT NULL
                );"""
            )

    def checkpoint(self, snapshot_id: str, input_hash: str, report_hash: str) -> None:
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                "SELECT input_hash,report_hash,classifier_version "
                "FROM snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            expected = (input_hash, report_hash, CLASSIFIER_VERSION)
            if existing is not None and tuple(existing) != expected:
                raise ScrutinyClassificationError("classification snapshot is not immutable")
            if existing is None:
                connection.execute(
                    "INSERT INTO snapshots VALUES (?,?,?,?)",
                    (snapshot_id, input_hash, report_hash, CLASSIFIER_VERSION),
                )


def _coverage_template() -> dict[str, int]:
    return {field: 0 for field in _COVERAGE_FIELDS}


def classify_scrutiny_crawl(
    raw_state_directory: Path, classification_state_directory: Path
) -> ScrutinyClassificationReport:
    """Run an offline, immutable R1 classification against a completed raw crawl."""
    with _read_raw_ledger(raw_state_directory / "scrutiny.sqlite3") as raw:
        plans = raw.execute("SELECT id,index_hash,entries_json FROM plans ORDER BY id").fetchall()
        if len(plans) != 1:
            raise ScrutinyClassificationError("classification requires exactly one raw crawl plan")
        plan = plans[0]
        rows = raw.execute(
            "SELECT source_url,source_path,category,state,snapshot_hash FROM items "
            "WHERE plan_id=? ORDER BY source_path,source_url",
            (plan["id"],),
        ).fetchall()

    input_material = [
        [row["source_url"], row["source_path"], row["category"], row["state"], row["snapshot_hash"]]
        for row in rows
    ]
    input_hash = hashlib.sha256(
        _canonical_json(
            {
                "classifier_version": CLASSIFIER_VERSION,
                "plan_id": plan["id"],
                "index_hash": plan["index_hash"],
                "entries": input_material,
            }
        )
    ).hexdigest()
    categories: dict[str, dict[str, object]] = {}
    document_lines: list[bytes] = []
    schema_counts: dict[str, Counter[str]] = defaultdict(Counter)
    schema_unknown: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    classifications: list[list[object]] = []

    for row in rows:
        category = cast(str, row["category"])
        detail = categories.setdefault(category, {"coverage": _coverage_template()})
        coverage = cast(dict[str, int], detail["coverage"])
        coverage["expected"] += 1
        state = cast(str, row["state"])
        snapshot_hash = row["snapshot_hash"]
        if state in {"retrieved", "unclassified"} and isinstance(snapshot_hash, str):
            coverage["retrieved"] += 1
            object_path = raw_state_directory / "objects" / "sha256" / snapshot_hash
            try:
                raw_bytes = object_path.read_bytes()
            except OSError as exc:
                raise ScrutinyClassificationError(
                    f"missing raw object for {row['source_path']}"
                ) from exc
            if hashlib.sha256(raw_bytes).hexdigest() != snapshot_hash:
                raise ScrutinyClassificationError(
                    f"raw object hash mismatch for {row['source_path']}"
                )
            try:
                payload = json.loads(raw_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ScrutinyClassificationError(
                    f"raw ledger marked JSON but object is invalid: {row['source_path']}"
                ) from exc
            assessment = classify_scrutiny_payload(category, payload)
            schema_counts[category][assessment.schema_fingerprint] += 1
            schema_unknown[category][assessment.schema_fingerprint].update(assessment.unknown_keys)
            if assessment.kind == "raw_unclassified":
                coverage["unclassified"] += 1
            else:
                coverage["classified"] += 1
            if assessment.kind == "document_index":
                for document in _document_rows(
                    payload,
                    source_url=cast(str, row["source_url"]),
                    source_path=cast(str, row["source_path"]),
                    source_hash=snapshot_hash,
                ):
                    document_lines.append(_canonical_json(document))
            classifications.append(
                [
                    row["source_path"],
                    assessment.kind,
                    assessment.reason,
                    assessment.schema_fingerprint,
                ]
            )
        elif state == "quarantined":
            coverage["quarantined"] += 1
        elif state == "ambiguous":
            coverage["ambiguous"] += 1
            classifications.append([row["source_path"], "raw_unclassified", "RAW_AMBIGUOUS", None])
        elif state == "excluded":
            coverage["excluded"] += 1
            classifications.append([row["source_path"], "raw_unclassified", "RAW_EXCLUDED", None])
        else:
            coverage["unclassified"] += 1
            classifications.append(
                [row["source_path"], "raw_unclassified", "RAW_NOT_RETRIEVED", None]
            )

    for category, detail in categories.items():
        detail["schema_fingerprints"] = [
            {
                "fingerprint": fingerprint,
                "count": count,
                "unknown_keys": sorted(schema_unknown[category][fingerprint]),
            }
            for fingerprint, count in sorted(schema_counts[category].items())
        ]
    overall = {
        field: sum(
            cast(dict[str, int], detail["coverage"])[field] for detail in categories.values()
        )
        for field in _COVERAGE_FIELDS
    }
    snapshot_material = {
        "input_hash": input_hash,
        "classifications": classifications,
        "schemas": {
            category: [
                [fingerprint, count, sorted(schema_unknown[category][fingerprint])]
                for fingerprint, count in sorted(schema_counts[category].items())
            ]
            for category in sorted(categories)
        },
    }
    snapshot_id = (
        "scrutiny-classified-" + hashlib.sha256(_canonical_json(snapshot_material)).hexdigest()[:16]
    )
    report = ScrutinyClassificationReport(
        snapshot_id=snapshot_id,
        input_plan_id=cast(str, plan["id"]),
        input_hash=input_hash,
        classifier_version=CLASSIFIER_VERSION,
        result_facts=0,
        document_index_entries=len(document_lines),
        categories={category: categories[category] for category in sorted(categories)},
        overall=overall,
    )
    report_bytes = _canonical_json(asdict(report))
    _write_immutable(
        classification_state_directory / "snapshots" / f"{snapshot_id}.json", report_bytes
    )
    _write_immutable(
        classification_state_directory / "document-index" / f"{snapshot_id}.jsonl",
        b"".join(document_lines),
    )
    _ClassificationLedger(classification_state_directory / "classification.sqlite3").checkpoint(
        snapshot_id, input_hash, hashlib.sha256(report_bytes).hexdigest()
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline raw-only scrutiny schema classification")
    parser.add_argument("--raw-state-dir", type=Path, required=True)
    parser.add_argument("--classification-state-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asdict(classify_scrutiny_crawl(args.raw_state_dir, args.classification_state_dir)),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
