from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from elecciones_pipeline.ingest.scrutiny import ScrutinyPlanEntry
from elecciones_pipeline.ingest.scrutiny_classification import (
    classify_scrutiny_crawl,
    classify_scrutiny_payload,
    schema_fingerprint,
)
from elecciones_pipeline.ingest.scrutiny_crawl import _Ledger, _plan_id

ACTA = {
    "digitalizado": 1,
    "escrutado": True,
    "id_informacion_mesa_corporacion": "010100101011    ",
    "nombre_archivo": "/docs/E14/example.pdf",
    "numero": 1,
}


@pytest.mark.parametrize(
    ("category", "payload", "kind"),
    [
        ("actas-documentos", [ACTA], "document_index"),
        ("actas-documentos", [], "metadata"),
        (
            "actas-publicadas",
            [
                {
                    "corId": "001",
                    "mesasEscrutadas": 1,
                    "mesasFaltantes": 0,
                    "mesasInstaladas": 1,
                    "nombreCor": "PRESIDENTE",
                    "porcentajeEscrutadas": 100.0,
                    "porcentajeFaltantes": 0.0,
                }
            ],
            "metadata",
        ),
        (
            "avance-actas",
            [
                {
                    "codigo": "1000",
                    "digitalizado": 1,
                    "escrutado": 1,
                    "etiqueta": "ANTIOQUIA",
                    "presenta_sub_comisiones": True,
                    "total": 1,
                }
            ],
            "metadata",
        ),
        ("avance-actas", [], "metadata"),
        (
            "comision",
            {"1000": {"codigo": "1000", "etiqueta": "ANTIOQUIA", "municipales": {}}},
            "metadata",
        ),
        (
            "comisiones",
            [
                {
                    "comsom_id": 1000,
                    "nombre": "ANTIOQUIA",
                    "presenta_sub_comisiones": 1,
                    "ticom_id": "2",
                    "total": 1,
                    "total_en_proceso": 0,
                    "total_en_receso": 0,
                    "total_finalizada": 1,
                }
            ],
            "metadata",
        ),
        ("comisiones", [], "metadata"),
        (
            "divipole",
            {
                "corporaciones": [{"codigo": "001", "etiqueta": "PRESIDENTE"}],
                "departamentos": {},
            },
            "metadata",
        ),
        (
            "documentos-publicados",
            [
                {
                    "codigo": 1,
                    "idComision": 1,
                    "nivel": "NACIONAL",
                    "publicado": 0,
                    "tipoDocumento": "MMS",
                    "urlArchivo": "",
                }
            ],
            "metadata",
        ),
        (
            "documentos-publicados",
            [
                {
                    "codigo": 1,
                    "eleccion": "PRESIDENTE",
                    "idComision": 1,
                    "nivel": "MUNICIPAL",
                    "nombreDocumento": "ACTA",
                    "publicado": 1,
                    "tipoDocumento": "MMS",
                    "urlArchivo": "/docs/mms.pdf",
                },
                {
                    "codigo": 1,
                    "eleccion": "PRESIDENTE",
                    "idComision": 1,
                    "nivel": "MUNICIPAL",
                    "nombreDocumento": "ACTA",
                    "publicado": 1,
                    "tipoCorporacion": "001",
                    "tipoDocumento": "MMS",
                    "urlArchivo": "/docs/mms.pdf",
                },
            ],
            "metadata",
        ),
        ("documentos-publicados", [], "metadata"),
        (
            "estadisticas",
            {"comisiones": 1, "finalizadas": 1, "instaladas": 1, "procesadas": 0},
            "metadata",
        ),
    ],
    ids=[
        "actas-records",
        "actas-empty",
        "actas-publicadas",
        "avance-records",
        "avance-empty",
        "comision-directory",
        "comisiones-records",
        "comisiones-empty",
        "divipole-directory",
        "documentos-minimal",
        "documentos-full-mixed",
        "documentos-empty",
        "estadisticas",
    ],
)
def test_frozen_observed_schema_variants_are_non_result_classifications(
    category: str, payload: object, kind: str
) -> None:
    result = classify_scrutiny_payload(category, payload)
    assert result.kind == kind
    assert result.unknown_keys == ()
    assert result.schema_fingerprint == schema_fingerprint(payload)


def _raw_crawl(tmp_path: Path, payload: object) -> tuple[Path, ScrutinyPlanEntry]:
    raw = tmp_path / "raw"
    entry = ScrutinyPlanEntry(
        source_url="https://official.gov.co/data/esc/v1/actas-documentos/001/actas.json",
        source_path="data/esc/v1/actas-documentos/001/actas.json",
        category="actas-documentos",
    )
    plan_id = _plan_id("a" * 64, (entry,))
    ledger = _Ledger(raw / "scrutiny.sqlite3")
    ledger.prepare(plan_id, "a" * 64, (entry,))
    content = json.dumps(payload, separators=(",", ":")).encode()
    content_hash = hashlib.sha256(content).hexdigest()
    object_path = raw / "objects" / "sha256" / content_hash
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(content)
    ledger.record(plan_id, entry, "unclassified", "valid_json", content_hash)
    return raw, entry


def test_checkpointed_classification_is_idempotent_and_indexes_only_allowlisted_metadata(
    tmp_path: Path,
) -> None:
    raw, _ = _raw_crawl(tmp_path, [ACTA])
    classified = tmp_path / "classified"
    first = classify_scrutiny_crawl(raw, classified)
    second = classify_scrutiny_crawl(raw, classified)

    assert first == second
    assert first.result_facts == 0
    assert first.overall == {
        "expected": 1,
        "retrieved": 1,
        "classified": 1,
        "unclassified": 0,
        "ambiguous": 0,
        "excluded": 0,
        "quarantined": 0,
    }
    index = (classified / "document-index" / f"{first.snapshot_id}.jsonl").read_text(
        encoding="utf-8"
    )
    assert json.loads(index) == {
        "digitalized": 1,
        "document_number": 1,
        "document_reference": "/docs/E14/example.pdf",
        "mesa_id": "010100101011    ",
        "scrutinized": True,
        "source_content_hash": hashlib.sha256(
            json.dumps([ACTA], separators=(",", ":")).encode()
        ).hexdigest(),
        "source_path": "data/esc/v1/actas-documentos/001/actas.json",
        "source_url": "https://official.gov.co/data/esc/v1/actas-documentos/001/actas.json",
    }


def test_schema_drift_stays_raw_and_reports_only_the_unknown_key_name(tmp_path: Path) -> None:
    payload = [{**ACTA, "signatory_name": "Ana Pérez"}]
    raw, _ = _raw_crawl(tmp_path, payload)
    report = classify_scrutiny_crawl(raw, tmp_path / "classified")

    assert report.overall["classified"] == 0
    assert report.overall["unclassified"] == 1
    artifact = (tmp_path / "classified" / "snapshots" / f"{report.snapshot_id}.json").read_text()
    assert "Ana Pérez" not in artifact
    assert "signatory_name" in artifact
    assert (
        not list((tmp_path / "classified" / "document-index").glob("*.jsonl"))
        or not (
            tmp_path / "classified" / "document-index" / f"{report.snapshot_id}.jsonl"
        ).read_text()
    )


def test_empty_known_payload_is_classified_metadata_with_zero_document_rows(tmp_path: Path) -> None:
    raw, _ = _raw_crawl(tmp_path, [])
    report = classify_scrutiny_crawl(raw, tmp_path / "classified")

    assert report.document_index_entries == 0
    assert report.overall["classified"] == 1
    assert report.overall["unclassified"] == 0
