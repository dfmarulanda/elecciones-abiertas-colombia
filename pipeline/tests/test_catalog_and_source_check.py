from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from elecciones_pipeline.catalog import CatalogError, SourceCatalog, load_source_catalog
from elecciones_pipeline.cli import app
from elecciones_pipeline.ingest import AsyncOfficialClient
from elecciones_pipeline.source_check import check_official_manifests
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_catalog_has_three_reviewed_crawl_roots() -> None:
    catalog = load_source_catalog(
        ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"
    )
    entrypoints = catalog.manifest_entrypoints()
    assert set(entrypoints) == {
        "precount_configuration",
        "precount_nomenclator",
        "scrutiny_manifest",
    }
    assert catalog.publication_state == "ready_for_candidate_release"
    final_declaration = catalog.source("cne-final-declaration-2026-round2")
    assert final_declaration.entrypoints["declaration"].startswith("https://")
    assert all(url.startswith("https://") for url in entrypoints.values())


def test_round1_catalog_has_catalog_driven_identifiers_and_a_reviewed_scrutiny_manifest() -> None:
    catalog = load_source_catalog(
        ROOT / "config/sources/presidencia-2026-primera-vuelta.json"
    )
    source = catalog.precount_source()
    assert source.id == "registraduria-precount-2026-round1"
    assert source.election_id == "1"
    assert source.election_sigla == "PR"
    assert set(catalog.precount_entrypoints()) == {
        "precount_configuration",
        "precount_nomenclator",
    }
    assert set(catalog.manifest_entrypoints()) == {
        "precount_configuration",
        "precount_nomenclator",
        "scrutiny_manifest",
    }
    scrutiny = catalog.scrutiny_source()
    assert scrutiny is not None
    assert scrutiny.id == "registraduria-scrutiny-2026-round1"
    assert scrutiny.entrypoints["manifest"] == (
        "https://escrutiniospresidente2026.registraduria.gov.co/data/index.json"
    )
    assert catalog.publication_state == "ready_for_candidate_release"


def test_declared_structured_scrutiny_without_manifest_fails_closed() -> None:
    payload = json.loads(
        (ROOT / "config/sources/presidencia-2026-primera-vuelta.json").read_text()
    )
    payload["sources"][1]["entrypoints"] = {
        "index": "https://escrutiniospresidente2026.registraduria.gov.co/index.json"
    }
    catalog = SourceCatalog.model_validate(payload)
    with pytest.raises(CatalogError, match="scrutiny_manifest"):
        catalog.manifest_entrypoints()


def test_catalog_rejects_an_unreviewed_entrypoint_host() -> None:
    payload = json.loads(
        (ROOT / "config/sources/presidencia-2026-segunda-vuelta.json").read_text()
    )
    payload["sources"][0]["entrypoints"]["configuration"] = "https://127.0.0.1/a.json"
    with pytest.raises(ValueError, match="unreviewed entrypoint"):
        SourceCatalog.model_validate(payload)


def test_missing_catalog_is_reported_as_a_catalog_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogError):
        load_source_catalog(tmp_path / "missing.json")


def test_source_check_is_non_publishing_and_change_aware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_source_catalog(
        ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"
    )
    generation = {"value": 1}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"generation": generation["value"], "url": str(request.url)},
            headers={"Content-Type": "application/json", "ETag": str(generation["value"])},
        )

    original_init = AsyncOfficialClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        kwargs["sleep"] = _no_sleep
        original_init(self, *args, **kwargs)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(AsyncOfficialClient, "__init__", patched_init)
    first = asyncio.run(check_official_manifests(catalog, tmp_path))
    assert first.publication_performed is False
    assert first.changed is False
    generation["value"] = 2
    second = asyncio.run(check_official_manifests(catalog, tmp_path))
    assert second.changed is True
    assert all(item.snapshot_number == 2 for item in second.items)


def test_source_check_reports_absent_structured_scrutiny_without_claiming_a_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_source_catalog(
        ROOT / "config/sources/presidencia-2026-primera-vuelta.json"
    )
    payload = catalog.model_dump(mode="json", by_alias=True)
    payload["sources"] = [payload["sources"][0]]
    catalog = SourceCatalog.model_validate(payload)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"verified": True})

    original_init = AsyncOfficialClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        kwargs["sleep"] = _no_sleep
        original_init(self, *args, **kwargs)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(AsyncOfficialClient, "__init__", patched_init)
    report = asyncio.run(check_official_manifests(catalog, tmp_path))
    scrutiny = next(item for item in report.items if item.id == "scrutiny_manifest")
    assert scrutiny.status == "not_declared"
    assert scrutiny.url == scrutiny.content_hash == ""
    assert scrutiny.snapshot_number == scrutiny.byte_size == 0


def test_scheduled_source_check_command_is_addressable_and_rejects_full_crawl() -> None:
    result = CliRunner().invoke(
        app, ["source-check", "--no-publish", "--full-crawl"]
    )
    assert result.exit_code == 2
    assert "full crawls require an explicit" in result.output
