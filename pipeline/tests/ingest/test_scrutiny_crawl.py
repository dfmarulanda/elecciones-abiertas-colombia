import asyncio
from pathlib import Path

import httpx
import pytest
from elecciones_pipeline.catalog import load_source_catalog
from elecciones_pipeline.ingest.models import CollectionConfig
from elecciones_pipeline.ingest.scrutiny import ScrutinyPlanEntry
from elecciones_pipeline.ingest.scrutiny_crawl import (
    ScrutinyCrawlReport,
    _Ledger,
    _plan_id,
    crawl_scrutiny,
)

ROOT = Path(__file__).resolve().parents[3]


def _entries() -> tuple[ScrutinyPlanEntry, ...]:
    return (
        ScrutinyPlanEntry(
            source_url="https://official.gov.co/data/esc/v1/avance/a.json",
            source_path="data/esc/v1/avance/a.json",
            category="avance",
        ),
        ScrutinyPlanEntry(
            source_url="https://official.gov.co/data/esc/v1/documentos/b.json",
            source_path="data/esc/v1/documentos/b.json",
            category="documentos",
        ),
    )


def test_one_request_per_second_is_a_supported_conservative_policy() -> None:
    assert CollectionConfig(requests_per_second=1, per_host_concurrency=1).requests_per_second == 1


def test_plan_id_is_manifest_immutable() -> None:
    entries = _entries()
    assert _plan_id("a" * 64, entries) != _plan_id("b" * 64, entries)
    assert _plan_id("a" * 64, entries) != _plan_id("a" * 64, entries[:1])


def test_ledger_resume_and_category_coverage(tmp_path: Path) -> None:
    entries = _entries()
    plan_id = _plan_id("a" * 64, entries)
    ledger = _Ledger(tmp_path / "scrutiny.sqlite3")
    ledger.prepare(plan_id, "a" * 64, entries)
    ledger.record(plan_id, entries[0], "unclassified", "valid_json", "c" * 64)
    assert [row["source_url"] for row in ledger.pending(plan_id)] == [entries[1].source_url]
    report = ledger.report(plan_id)
    assert report.expected == 2
    assert report.retrieved == 1
    assert report.parsed == 0
    assert report.unclassified == 1
    assert report.missing == 1
    assert report.categories["avance"]["unclassified"] == 1


def test_ledger_rejects_tampered_same_plan(tmp_path: Path) -> None:
    entries = _entries()
    ledger = _Ledger(tmp_path / "scrutiny.sqlite3")
    ledger.prepare("fixed", "a" * 64, entries)
    with pytest.raises(Exception, match="immutable"):
        ledger.prepare("fixed", "a" * 64, entries[:1])


def test_crawl_uses_the_catalog_declared_round1_manifest_only(tmp_path: Path) -> None:
    catalog = load_source_catalog(ROOT / "config/sources/presidencia-2026-primera-vuelta.json")
    requested: list[str] = []
    manifest = {"data/esc/v1/actas-documentos/001/": "actas.json"}

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/data/index.json":
            return httpx.Response(200, json=manifest, headers={"Content-Type": "application/json"})
        if request.url.path == "/data/esc/v1/actas-documentos/001/actas.json":
            return httpx.Response(200, json=[], headers={"Content-Type": "application/json"})
        return httpx.Response(404, headers={"Content-Type": "application/json"})

    async def run() -> tuple[ScrutinyCrawlReport, list[str]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            report = await crawl_scrutiny(catalog, tmp_path, http_client=client)
        return report, requested

    report, requested = asyncio.run(run())
    assert report.expected == report.retrieved == report.unclassified == 1
    assert report.parsed == 0
    assert requested == [
        "https://escrutiniospresidente2026.registraduria.gov.co/data/index.json",
        "https://escrutiniospresidente2026.registraduria.gov.co/"
        "data/esc/v1/actas-documentos/001/actas.json",
    ]
