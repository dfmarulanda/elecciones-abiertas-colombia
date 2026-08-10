import csv
import hashlib
import io
import json
from pathlib import Path
from typing import cast

import pytest
from elecciones_api.config import Settings
from elecciones_api.cursor import CursorError, decode_keyset_cursor, encode_keyset_cursor
from elecciones_api.db import Base
from elecciones_api.main import (
    _normalized_csv_header,
    _normalized_csv_row,
    _normalized_fact,
    _scrub_sentry_event,
    create_app,
    select_repository,
)
from elecciones_api.repository import (
    FixtureRepository,
    PostgresReadRepository,
    ReleaseNotFoundError,
    RepositoryUnavailableError,
    ResourceNotFoundError,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sentry_sdk.types import Event

ROOT = Path(__file__).resolve().parents[3]
SLUG = "presidencia-2026-segunda-vuelta"
TEST_CURSOR_SECRET = "test-non-default-cursor-secret"  # noqa: S105 - test-only value


def _outcome_artifact() -> dict[str, object]:
    artifact: dict[str, object] = {
        "status": "not_evaluable",
        "evaluable": False,
        "issues": [{"code": "source_fact_coverage_incomplete", "record_ids": []}],
        "scope": None,
        "outcome_source": None,
        "leader_id": None,
        "runner_up_id": None,
        "leader_votes": None,
        "runner_up_votes": None,
        "observed_margin_votes": None,
        "verified_record_ids": None,
        "unresolved_record_ids": None,
        "verified_affected_votes": None,
        "verified_margin_shift_bound": None,
        "unresolved_affected_vote_upper_bound": None,
        "unresolved_margin_shift_upper_bound": None,
        "combined_affected_vote_upper_bound": None,
        "combined_margin_shift_upper_bound": None,
        "verified_margin_headroom": None,
        "combined_margin_headroom": None,
        "tie_possible_from_verified": None,
        "lead_change_possible_from_verified": None,
        "tie_possible_including_unresolved": None,
        "lead_change_possible_including_unresolved": None,
        "source_links": [],
        "evidence_hash": None,
        "methodology_version": "outcome-sensitivity-v3.0.0",
        "calculation": "authenticated documentary bounds only",
        "limitations": ["Statistical screening signals are excluded."],
    }
    artifact["output_hash"] = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return artifact


def _outcome_dataset(
    artifact: dict[str, object], *, release_id: str = "release", election_slug: str = "election"
) -> tuple[bytes, dict[str, object]]:
    raw = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    content_hash = hashlib.sha256(raw).hexdigest()
    return raw, {
        "id": f"outcome-sensitivity-{election_slug}",
        "format": "json",
        "url": f"https://artifacts.example.test/releases/{release_id}/{content_hash}.json",
        "schema_url": "https://artifacts.example.test/schemas/outcome-sensitivity.schema.json",
        "record_count": 1,
        "byte_size": len(raw),
        "content_hash": content_hash,
        "filters": {
            "artifact_kind": "outcome_sensitivity",
            "election_slug": election_slug,
            "data_version": release_id,
            "core_output_hash": artifact["output_hash"],
            "methodology_version": artifact["methodology_version"],
            "evidence_hash": artifact["evidence_hash"] or "none",
        },
    }


def client() -> TestClient:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    return TestClient(create_app(repository=repository))


def test_versioned_analysis_resources_are_typed_and_keep_detection_separate() -> None:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    version = repository.data_version
    base = f"/api/v1/releases/{version}/elections/{SLUG}/analysis"
    with TestClient(create_app(repository=repository)) as api:
        summary = api.get(f"{base}/summary")
        anomalies = api.get(f"{base}/anomalies")
        diagnostics = api.get(f"{base}/model_diagnostics")
    assert summary.status_code == anomalies.status_code == diagnostics.status_code == 200
    item = anomalies.json()["items"][0]
    assert item["is_anomaly"] is True
    assert item["typed_components"]
    assert item["explanation"]["status"] == "non_evaluable"
    assert item["minimum_ballot_edits_status"] == "not_evaluable"
    for anomaly in anomalies.json()["items"]:
        statistical = [
            component
            for component in anomaly["typed_components"]
            if component["evidence_type"] == "research_preview"
        ]
        assert all(component["points"] == 0 for component in statistical)
        legacy_statistical = [
            component
            for component in anomaly["components"]
            if component["component_type"] in {"peer_distribution", "spatial_cluster"}
        ]
        assert all(component["points"] == 0 for component in legacy_statistical)
        if anomaly["evidence_tier"] == "research_preview":
            assert anomaly["audit_priority_score"] == 0
    assert diagnostics.json()["status"] == "research_preview"


def test_analysis_resources_are_pinned_to_one_immutable_analysis_release() -> None:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    version = repository.data_version
    base = f"/api/v1/releases/{version}/elections/{SLUG}/analysis"
    with TestClient(create_app(repository=repository)) as api:
        summary_response = api.get(f"{base}/summary")
        summary = summary_response.json()
        analysis_release_id = summary["analysis_release"]["analysis_release_id"]
        page = api.get(f"{base}/anomalies?limit=1")
        explicit = api.get(f"{base}/summary", params={"analysis_release": analysis_release_id})
        mismatch = api.get(f"{base}/summary", params={"analysis_release": "analysis-wrong"})

    metadata = summary["analysis_release"]
    assert metadata == explicit.json()["analysis_release"]
    assert metadata["source_release_id"] == version
    assert metadata["election_slug"] == SLUG
    assert metadata["exposure_tier"] == "preliminary_research"
    assert metadata["preliminary_caveat"]["es"]
    assert metadata["preliminary_caveat"]["en"]
    assert len(metadata["canonical_input_hash"]) == 64
    assert len(metadata["manifest_hash"]) == 64
    assert len(metadata["provenance_hash"]) == 64
    assert metadata["artifact_status"] == "research_preview"
    assert metadata["evaluable"] is True
    assert summary_response.headers["cache-control"] == "no-store, max-age=0"
    assert summary_response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert page.json()["analysis_release"] == metadata
    assert mismatch.status_code == 404


def test_analysis_cursor_is_pinned_to_the_resolved_analysis_release() -> None:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    version = repository.data_version
    base = f"/api/v1/releases/{version}/elections/{SLUG}/analysis/anomalies"
    with TestClient(create_app(repository=repository)) as api:
        first = api.get(base, params={"limit": 1})
        cursor = first.json()["page"]["next_cursor"]
        pinned_release = first.json()["analysis_release"]["analysis_release_id"]
        if cursor is not None:
            mismatch = api.get(
                base,
                params={
                    "limit": 1,
                    "cursor": cursor,
                    "analysis_release": f"{pinned_release}-different",
                },
            )
            assert mismatch.status_code in {400, 404}


def test_analysis_artifacts_are_typed_immutable_and_download_safe() -> None:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    version = repository.data_version
    base = f"/api/v1/releases/{version}/elections/{SLUG}/analysis/artifacts"
    with TestClient(create_app(repository=repository)) as api:
        listing = api.get(base)
        item = listing.json()["items"][0]
        detail = api.get(f"{base}/{item['artifact_id']}")
        download = api.get(f"{base}/{item['artifact_id']}/download", follow_redirects=False)

    assert listing.status_code == detail.status_code == 200
    assert listing.json()["analysis_release"] == detail.json()["analysis_release"]
    assert item["url"].startswith("https://eleccionesabiertas.co/")
    assert item["byte_hash"] == item["content_hash"]
    assert "reviewer" not in json.dumps(item).lower()
    assert "document_bytes" not in json.dumps(item).lower()
    assert download.status_code == 307
    assert download.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert download.headers["etag"] == f'"{item["byte_hash"]}"'


def test_analysis_anomaly_detail_openapi_response_is_typed() -> None:
    repository = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    version = repository.data_version
    base = f"/api/v1/releases/{version}/elections/{SLUG}/analysis"
    with TestClient(create_app(repository=repository)) as api:
        anomaly_id = api.get(f"{base}/anomalies").json()["items"][0]["id"]
        detail = api.get(f"{base}/anomalies/{anomaly_id}")
        runtime_openapi = cast(FastAPI, api.app).openapi()

    assert detail.status_code == 200
    response_schema = runtime_openapi["paths"][
        "/api/v1/releases/{release_id}/elections/{election_slug}/analysis/anomalies/{anomaly_id}"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/AnalysisAnomaly")


def test_postgres_analysis_guard_is_disjoint_exact_and_never_reads_legacy_signals() -> None:
    repository = object.__new__(PostgresReadRepository)
    calls: list[tuple[str, dict[str, object]]] = []

    def normalized(statement: str, values: dict[str, object]) -> list[dict[str, object]]:
        calls.append((statement, values))
        if "FROM analysis_releases" in statement:
            return [
                {
                    "analysis_release_id": "analysis-1",
                    "source_release_id": "release-1",
                    "source_election_slug": "election-1",
                    "methodology_version": "analysis-v1",
                    "canonical_input_hash": "a" * 64,
                    "producer_runtime_fingerprint": "b" * 64,
                    "generated_at": "2026-08-10T10:00:00Z",
                    "manifest_hash": "c" * 64,
                    "exposure_tier": "preliminary_research",
                    "approved_at": "2026-08-10T11:00:00Z",
                    "caveat_es": "Investigación preliminar",
                    "caveat_en": "Preliminary research",
                }
            ]
        if "SELECT artifact_status" in statement:
            return [{"artifact_status": "available"}]
        raise AssertionError(statement)

    repository._active_release_id = "release-1"
    repository._normalized = normalized  # type: ignore[method-assign,assignment]
    metadata = repository.analysis_release_metadata("election-1", "release-1", "analysis-1")

    guard_sql, guard_values = calls[0]
    assert metadata.analysis_release_id == "analysis-1"
    assert guard_values == {"r": "release-1", "e": "election-1", "a": "analysis-1"}
    assert "ax.revoked_at IS NULL" in guard_sql
    assert "sx.access_scope='preliminary'" in guard_sql
    assert "sx.access_scope='public'" in guard_sql
    assert "review_signals" not in guard_sql


def test_postgres_analysis_artifacts_keep_stored_reason_and_reject_unsafe_url() -> None:
    repository = object.__new__(PostgresReadRepository)
    repository._active_release_id = "release-1"
    repository._allowed_artifact_hosts = {"official.example"}
    artifact_url = f"https://official.example/analysis/{'d' * 64}.json"

    def normalized(statement: str, values: dict[str, object]) -> list[dict[str, object]]:
        if "FROM analysis_releases" in statement:
            return [
                {
                    "analysis_release_id": "analysis-1",
                    "source_release_id": "release-1",
                    "source_election_slug": "election-1",
                    "methodology_version": "analysis-v1",
                    "canonical_input_hash": "a" * 64,
                    "producer_runtime_fingerprint": "b" * 64,
                    "generated_at": "2026-08-10T10:00:00Z",
                    "manifest_hash": "c" * 64,
                    "exposure_tier": "preliminary_research",
                    "approved_at": "2026-08-10T11:00:00Z",
                    "caveat_es": "Investigación preliminar",
                    "caveat_en": "Preliminary research",
                }
            ]
        if "SELECT artifact_status" in statement:
            return [{"artifact_status": "not_evaluable"}]
        if "SELECT artifact_id,kind" in statement:
            return [
                {
                    "artifact_id": "spatial-status",
                    "kind": "spatial_status",
                    "schema_version": "1.0.0",
                    "media_type": "application/json",
                    "record_count": 0,
                    "byte_size": 0,
                    "byte_hash": "d" * 64,
                    "content_hash": "e" * 64,
                    "immutable_url": None,
                    "artifact_status": "not_evaluable",
                    "status_reason": "authenticated_coordinates_missing",
                }
            ]
        raise AssertionError((statement, values))

    repository._normalized = normalized  # type: ignore[method-assign,assignment]
    artifacts = repository.analysis_artifacts("election-1", "release-1", "analysis-1")
    assert artifacts[0].status_reasons == ["authenticated_coordinates_missing"]

    with pytest.raises(RepositoryUnavailableError, match="invalid immutable URL"):
        repository._validated_analysis_artifact_url(  # noqa: SLF001
            artifact_url.replace("official.example", "official.example@evil.example"),
            "d" * 64,
        )


def test_normalized_outcome_reads_strict_content_addressed_analysis_artifact() -> None:
    fixture = FixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    metadata = fixture.analysis_release_metadata(SLUG, fixture.data_version, None)
    repository = object.__new__(PostgresReadRepository)
    repository._sessions = object()
    repository._allowed_artifact_hosts = {"github.com"}
    repository.analysis_release_metadata = lambda *_args: metadata  # type: ignore[method-assign]
    artifact = _outcome_artifact()
    raw = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    byte_hash = hashlib.sha256(raw).hexdigest()

    def normalized(_statement: str, _values: dict[str, object]) -> list[dict[str, object]]:
        return [
            {
                "artifact_id": f"{metadata.analysis_release_id}:outcome_sensitivity",
                "media_type": "application/json",
                "record_count": 1,
                "byte_size": len(raw),
                "byte_hash": byte_hash,
                "content_hash": byte_hash,
                "immutable_url": (
                    "https://github.com/example/releases/download/analysis/"
                    f"{byte_hash}-outcome_sensitivity.json"
                ),
                "artifact_status": "available",
            }
        ]

    repository._normalized = normalized  # type: ignore[method-assign,assignment]
    repository._outcome_artifact_fetcher = lambda _url: raw

    result = repository.normalized_outcome_sensitivity(
        metadata.source_release_id,
        metadata.election_slug,
        metadata.analysis_release_id,
    )

    assert result.status == "not_evaluable"
    assert result.analysis_release == metadata
    assert result.output_hash == artifact["output_hash"]


def test_outcome_artifact_redirects_are_limited_to_the_github_release_host() -> None:
    repository = object.__new__(PostgresReadRepository)

    accepted = repository._validated_outcome_redirect_url(  # noqa: SLF001
        "https://release-assets.githubusercontent.com/download?signature=value",
        "github.com",
    )

    assert accepted.startswith("https://release-assets.githubusercontent.com/")
    with pytest.raises(RepositoryUnavailableError, match="invalid redirect"):
        repository._validated_outcome_redirect_url(  # noqa: SLF001
            "https://evil.example/download?signature=value",
            "github.com",
        )


def test_sentry_events_drop_visitor_request_data() -> None:
    event = {
        "user": {"ip_address": "127.0.0.1"},
        "request": {
            "url": "https://api.example.test/results?mesa=secret#fragment",
            "headers": {"authorization": "secret"},
            "cookies": {"session": "secret"},
            "data": {"visitor": "secret"},
            "query_string": "mesa=secret",
            "env": {"REMOTE_ADDR": "127.0.0.1"},
        },
        "exception": {"values": []},
    }
    scrubbed = _scrub_sentry_event(cast(Event, event), {})
    assert "user" not in scrubbed
    assert scrubbed["request"] == {"url": "https://api.example.test/results"}
    assert "exception" in scrubbed


def test_keyset_cursor_rejects_oversized_and_legacy_payloads() -> None:
    cursor = encode_keyset_cursor(("department", "r1:dep:01", "source", "fact"), "scope", "secret")
    assert decode_keyset_cursor(cursor, "scope", "secret")[0] == "department"
    with pytest.raises(CursorError, match="too large"):
        decode_keyset_cursor("x" * 1025, "scope", "secret")


def test_normalized_seek_sql_binds_all_filters_and_never_uses_offset() -> None:
    sql, values = PostgresReadRepository._result_statement(
        "release-1",
        "election-1",
        {
            "geography_id": "mesa-1",
            "geography_path": "CO/11/001",
            "geography_level": "mesa",
            "source_type": "scrutiny",
            "source_id": "source-1",
            "category_key": "ballot:blank",
            "status": "unavailable",
        },
        ("mesa", "mesa-1", "source-1", "fact-1"),
        51,
    )
    assert "OFFSET" not in sql
    assert "LIMIT :n" in sql
    assert "EXISTS (SELECT 1 FROM release_category_facts cf" in sql
    assert "EXISTS (SELECT 1 FROM release_category_facts sf" in sql
    assert values["n"] == 51
    assert values["geography_path_desc"] == "CO/11/001/%"


def test_normalized_fact_rejects_malformed_source_or_metric_data() -> None:
    row: dict[str, object] = {
        "id": "fact-1",
        "geography_id": "mesa-1",
        "geography_level": "mesa",
        "mesa_id": "mesa-1",
        "source_id": "source-1",
        "source_type": "not-a-source",
        "legal_status": "preliminary",
        "source_url": "https://official.example/source",
        "retrieved_at": "2026-08-03T12:00:00Z",
        "content_hash": "a" * 64,
        "parser_version": "v1",
        "transform_version": "v1",
        "metrics": {
            name: {"value": None, "status": "unavailable"}
            for name in (
                "registered_electors",
                "voters",
                "valid_votes",
                "blank_votes",
                "null_votes",
                "unmarked_votes",
            )
        },
    }
    with pytest.raises(RepositoryUnavailableError):
        _normalized_fact(row, "release-1", "election-1")


def test_standard_summary_uses_persisted_candidate_slate_metadata() -> None:
    repository = object.__new__(PostgresReadRepository)

    def normalized(statement: str, _values: dict[str, object]) -> list[dict[str, object]]:
        if "FROM release_elections" in statement:
            return [
                {
                    "name_es": "Elección",
                    "name_en": "Election",
                    "round": 2,
                    "election_date": "2026-06-21",
                    "status": "candidate",
                    "synthetic": False,
                }
            ]
        if "FROM release_summaries" in statement:
            return [
                {
                    "release_class": "standard",
                    "completion": {"expected": 1, "reported": 1, "percent": 1},
                    "coverage": {"expected": 1, "retrieved": 1, "parsed": 1, "missing": 0},
                    "geographic_collection_coverage": {"status": "full_scope"},
                    "reconciliation": {"status": "blocked", "exceptions": 3},
                    "turnout": 0.5,
                    "preview_caveat_es": None,
                    "preview_caveat_en": None,
                }
            ]
        if "FROM release_result_facts" in statement:
            return [
                {
                    "id": "national",
                    "metrics": {
                        "valid_votes": {"value": 100, "status": "observed"},
                    },
                    "source_id": "national-source",
                    "source_type": "pre_count",
                    "legal_status": "preliminary",
                    "source_url": "https://official.example/results",
                    "retrieved_at": "2026-06-21T22:00:00Z",
                    "content_hash": "a" * 64,
                    "parser_version": "parser-v1",
                    "transform_version": "transform-v1",
                }
            ]
        if "FROM release_candidates" in statement:
            return [
                {
                    "id": "candidate-a",
                    "ballot_number": 7,
                    "name_es": "Nombre completo",
                    "name_en": "Full name",
                    "short_name_es": "Nombre",
                    "short_name_en": "Name",
                }
            ]
        raise AssertionError(statement)

    repository._normalized = normalized  # type: ignore[method-assign,assignment]
    repository.normalized_categories = lambda *_args: [  # type: ignore[method-assign,assignment]
        {
            "category_key": "candidate:candidate-a",
            "category_code": "candidate-a",
            "category_name": "Fallback name",
            "votes": {"value": 60, "status": "observed"},
        }
    ]

    summary = repository._standard_summary(
        "release-1",
        "election-1",
        {
            "class": "preliminary",
            "caveat": {"es": "Preliminar", "en": "Preliminary"},
        },
    )

    candidate = cast(list[dict[str, object]], summary["candidates"])[0]["candidate"]
    assert candidate == {
        "id": "candidate-a",
        "ballot_number": 7,
        "name": {"es": "Nombre completo", "en": "Full name"},
        "short_name": {"es": "Nombre", "en": "Name"},
    }


class ProductionFixtureRepository(FixtureRepository):
    """A fixture-shaped snapshot used to exercise the production redirect branch."""

    @property
    def is_fixture(self) -> bool:
        return False

    def dataset_artifact_url(self, dataset_id: str, version: str | None) -> str:
        self.dataset(dataset_id, version)
        return "https://artifacts.example.test/releases/results.json"


def test_every_frozen_endpoint_is_available() -> None:
    requests = [
        f"/api/v1/elections/{SLUG}/summary",
        f"/api/v1/elections/{SLUG}/results",
        "/api/v1/geographies/CO",
        "/api/v1/mesas/2026-R2-11-001-001-003",
        "/api/v1/mesas/2026-R2-11-001-001-003/evidence",
        "/api/v1/mesas/2026-R2-11-001-001-003/comparisons",
        f"/api/v1/bulletins?election_slug={SLUG}",
        "/api/v1/bulletins/bulletin-01/results",
        f"/api/v1/review-signals?election_slug={SLUG}",
        f"/api/v1/datasets?election_slug={SLUG}",
        "/api/v1/datasets/fixture-results-json/download",
        "/api/v1/openapi.json",
    ]
    with client() as api:
        statuses = [api.get(path, follow_redirects=False).status_code for path in requests]
    assert statuses == [200] * 10 + [302, 200]


def test_public_signal_analysis_is_typed_and_fixture_outcomes_are_not_exposed() -> None:
    outcome_path = f"/api/v1/releases/fixture-2026-round2-v1/elections/{SLUG}/outcome-sensitivity"
    with client() as api:
        signals = api.get(f"/api/v1/review-signals?election_slug={SLUG}")
        outcome = api.get(outcome_path)
    peer = next(
        component
        for signal in signals.json()["items"]
        for component in signal["components"]
        if component["component_type"] == "peer_distribution"
    )
    analysis = peer["analysis"]
    assert analysis["kind"] == "peer_distribution"
    assert analysis["observed_rate"] == {"value": 0.55, "status": "observed"}
    assert analysis["expected_rate"] == {"value": None, "status": "unknown"}
    assert analysis["public_point_eligible"] is False
    assert analysis["reason"] == "synthetic_fixture_not_production_eligible"
    # Fixture/candidate data can never make an outcome artifact public; only
    # the PostgreSQL normalized adapter checks the published release exposure.
    assert outcome.status_code == 404


def test_outcome_read_checks_release_exposure_before_reading_any_artifact() -> None:
    repository = object.__new__(PostgresReadRepository)

    def reject_release(_release_id: str, _election_slug: str) -> None:
        raise ReleaseNotFoundError("not public")

    repository._authorized = reject_release  # type: ignore[method-assign,assignment]
    with pytest.raises(ReleaseNotFoundError, match="not public"):
        repository.normalized_outcome_sensitivity("candidate", "election")


def test_outcome_requires_independent_immutable_bytes_and_rejects_self_attachment() -> None:
    repository = object.__new__(PostgresReadRepository)

    def allow_release(_release_id: str, _election_slug: str) -> None:
        return None

    artifact = _outcome_artifact()
    raw, declaration = _outcome_dataset(artifact)
    manifest: dict[str, object] = {
        "outcome_sensitivity": {"election": artifact},
        "sources": [],
        "datasets": [declaration],
    }
    approved_hash = [
        hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    ]

    def normalized(_statement: str, _values: dict[str, object]) -> list[dict[str, object]]:
        return [{"manifest": manifest, "manifest_hash": approved_hash[0]}]

    repository._authorized = allow_release  # type: ignore[method-assign,assignment]
    repository._normalized = normalized  # type: ignore[method-assign,assignment]
    repository._allowed_artifact_hosts = {"artifacts.example.test"}
    fetched = [raw]
    repository._outcome_artifact_fetcher = lambda _url: fetched[0]

    # This is the old vulnerability: an arbitrary inline value, a self-consistent
    # output hash, and a matching declaration were accepted as if pipeline-bound.
    with pytest.raises(ResourceNotFoundError, match="Inline"):
        repository.normalized_outcome_sensitivity("release", "election")

    # A core abstention is read only from separately hashed, content-addressed
    # JSON bytes declared by the exact authenticated release manifest.
    manifest.pop("outcome_sensitivity")
    approved_hash[0] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert (
        repository.normalized_outcome_sensitivity("release", "election").status == "not_evaluable"
    )

    # The declaration binds the exact bytes independently of the core's
    # self-hash, so modifying those bytes fails before schema interpretation.
    fetched[0] = raw.replace(b"only", b"evil", 1)
    with pytest.raises(RepositoryUnavailableError, match="bytes"):
        repository.normalized_outcome_sensitivity("release", "election")

    # Wrapping the core with caller-controlled release metadata is ambiguous
    # even when the outer bytes and release manifest are re-hashed.
    wrapped = {**artifact, "release_id": "release"}
    wrapped_raw = json.dumps(
        wrapped, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    wrapped_declaration = dict(declaration)
    wrapped_hash = hashlib.sha256(wrapped_raw).hexdigest()
    wrapped_declaration.update(
        {
            "url": f"https://artifacts.example.test/releases/release/{wrapped_hash}.json",
            "byte_size": len(wrapped_raw),
            "content_hash": wrapped_hash,
        }
    )
    manifest["datasets"] = [wrapped_declaration]
    approved_hash[0] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    fetched[0] = wrapped_raw
    with pytest.raises(RepositoryUnavailableError, match="unwrapped core"):
        repository.normalized_outcome_sensitivity("release", "election")


def test_self_consistent_forged_outcome_bounds_fail_without_typed_replay() -> None:
    repository = object.__new__(PostgresReadRepository)

    def allow_forged(_release_id: str, _election_slug: str) -> None:
        return None

    repository._authorized = allow_forged  # type: ignore[method-assign,assignment]
    repository._allowed_artifact_hosts = {"artifacts.example.test"}

    forged = _outcome_artifact()
    forged.update(
        {
            "status": "lead_change_within_verified_bound",
            "evaluable": True,
            "issues": [],
            "scope": {"level": "national", "key": ["CO"]},
            "outcome_source": {
                "source_id": "scrutiny-total",
                "fact_grain": "national",
                "source_type": "scrutiny",
                "legal_status": "official_scrutiny",
            },
            "leader_id": "leader",
            "runner_up_id": "runner-up",
            "leader_votes": 100,
            "runner_up_votes": 90,
            "observed_margin_votes": 10,
            "verified_record_ids": ["forged-review"],
            "unresolved_record_ids": [],
            "verified_affected_votes": 10,
            "verified_margin_shift_bound": 20,
            "unresolved_affected_vote_upper_bound": 0,
            "unresolved_margin_shift_upper_bound": 0,
            "combined_affected_vote_upper_bound": 10,
            "combined_margin_shift_upper_bound": 20,
            "verified_margin_headroom": -10,
            "combined_margin_headroom": -10,
            "tie_possible_from_verified": True,
            "lead_change_possible_from_verified": True,
            "tie_possible_including_unresolved": True,
            "lead_change_possible_including_unresolved": True,
            "source_links": ["https://official.example/source"],
            "evidence_hash": "b" * 64,
        }
    )
    payload = {key: value for key, value in forged.items() if key != "output_hash"}
    forged["output_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    raw, declaration = _outcome_dataset(forged)
    manifest: dict[str, object] = {"sources": [], "datasets": [declaration]}
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    def normalized_forged(_statement: str, _values: dict[str, object]) -> list[dict[str, object]]:
        return [{"manifest": manifest, "manifest_hash": manifest_hash}]

    repository._normalized = normalized_forged  # type: ignore[method-assign,assignment]
    repository._outcome_artifact_fetcher = lambda _url: raw

    # Re-hashing the forged core, the exact JSON bytes, and the manifest still
    # cannot substitute for replay against typed source and review artifacts.
    with pytest.raises(ResourceNotFoundError, match="replay"):
        repository.normalized_outcome_sensitivity("release", "election")


def test_legacy_evidence_is_readable_but_its_document_processing_fields_are_never_served() -> None:
    fixture = json.loads((ROOT / "data/fixtures/fixture-release.json").read_text())
    mesa_id = "2026-R2-11-001-001-003"
    repository = FixtureRepository.from_snapshot(fixture, is_fixture=False)
    with TestClient(create_app(repository=repository)) as api:
        response = api.get(f"/api/v1/mesas/{mesa_id}/evidence")
    assert response.status_code == 200
    assert response.json()["documents"] == []

    fixture["evidence_handling"] = {"legacy": {}}
    unsafe_repository = FixtureRepository.from_snapshot(fixture, is_fixture=False)
    with TestClient(create_app(repository=unsafe_repository)) as api:
        blocked = api.get(f"/api/v1/mesas/{mesa_id}/evidence")
    assert blocked.status_code == 200
    assert blocked.json()["documents"] == []


def test_inactive_immutable_candidate_snapshot_remains_readable() -> None:
    """Index-only projection must not strand previously materialized releases."""
    snapshot_path = ROOT / "data/releases/candidate-2026-r2-b657eb58e613516a/api-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    repository = FixtureRepository.from_snapshot(snapshot, is_fixture=False)
    summary = repository.summary("presidencia-2026-segunda-vuelta", None)
    assert summary.data_version == "candidate-2026-r2-b657eb58e613516a"
    assert summary.synthetic is False


def test_evidence_urls_are_rechecked_at_the_public_api_boundary() -> None:
    fixture = json.loads((ROOT / "data/fixtures/fixture-release.json").read_text())
    mesa_id = "2026-R2-11-001-001-003"
    fixture["evidence"] = [
        {
            "id": "e14-index-only",
            "mesa_id": mesa_id,
            "document_type": "e14_delegate",
            "official_url": "https://untrusted.example/f.pdf",
            "source_index_url": "https://example.invalid/fixture/e14/index.json",
            "source_index_hash": "c111111111111111111111111111111111111111111111111111111111111111",
            "indexed_at": "2026-07-15T11:50:00Z",
            "index_status": "indexed",
            "provenance": {
                "data_version": "fixture-2026-round2-v1",
                "source_type": "e14_delegate",
                "legal_status": "documentary_evidence",
                "source_url": "https://example.invalid/fixture/e14/index.json",
                "retrieved_at": "2026-07-15T11:50:00Z",
                "content_hash": "c111111111111111111111111111111111111111111111111111111111111111",
                "parser_version": "fixture-indexer@1.0.0",
                "transform_version": "fixture-indexer@1.0.0",
                "methodology_version": None,
            },
        }
    ]
    fixture["evidence_handling"] = {}
    repository = FixtureRepository.from_snapshot(fixture, is_fixture=True)
    with TestClient(create_app(repository=repository)) as api:
        response = api.get(f"/api/v1/mesas/{mesa_id}/evidence")
    assert response.status_code == 503
    assert response.json()["title"] == "Invalid document evidence"


def test_public_openapi_is_the_frozen_document_and_paths_match() -> None:
    with client() as api:
        response = api.get("/api/v1/openapi.json")
        runtime_paths: set[str] = set()
        for route in cast(FastAPI, api.app).routes:
            path = getattr(route, "path", None)
            if isinstance(path, str) and path.startswith("/api/v1/"):
                runtime_paths.add(path)
    frozen = json.loads((ROOT / "packages/contracts/openapi.json").read_text())
    assert response.json() == frozen
    assert set(response.json()["paths"]) == runtime_paths
    schemas = frozen["components"]["schemas"]
    for name in (
        "ResultPage",
        "NormalizedCategoryPage",
        "ScopedGeographyResponse",
        "ScopedGeographyPathResponse",
        "GeographyChildPage",
        "ScopedMesa",
    ):
        assert {
            "exposure_class",
            "preliminary",
            "preliminary_caveat",
        } <= schemas[name]["properties"].keys()
    summary_schema = frozen["paths"][
        "/api/v1/releases/{release_id}/elections/{election_slug}/summary"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert {item["$ref"] for item in summary_schema["anyOf"]} == {
        "#/components/schemas/ContextElectionSummary",
        "#/components/schemas/PreliminaryElectionSummary",
    }


def test_results_filters_csv_and_cursor_tampering() -> None:
    with client() as api:
        first = api.get(f"/api/v1/elections/{SLUG}/results?limit=2")
        cursor = first.json()["page"]["next_cursor"]
        second = api.get(f"/api/v1/elections/{SLUG}/results?limit=2&cursor={cursor}")
        bad_cursor = api.get(f"/api/v1/elections/{SLUG}/results?cursor={cursor}tampered")
        csv_response = api.get(
            f"/api/v1/elections/{SLUG}/results?format=csv&geography_id=place-bog-001"
        )
        department_response = api.get(
            f"/api/v1/elections/{SLUG}/results?limit=200&geography_id=CO-DC"
        )
        national_response = api.get(f"/api/v1/elections/{SLUG}/results?limit=200&geography_id=CO")
        candidate_response = api.get(
            f"/api/v1/elections/{SLUG}/results?limit=200&candidate_id=candidatura-horizonte"
        )
        candidate_csv = api.get(
            f"/api/v1/elections/{SLUG}/results?format=csv&candidate_id=candidatura-horizonte"
        )
    assert [item["id"] for item in first.json()["items"]] == ["result-001", "result-002"]
    assert [item["id"] for item in second.json()["items"]] == ["result-003", "result-004"]
    assert bad_cursor.status_code == 400
    assert bad_cursor.headers["content-type"].startswith("application/problem+json")
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert len(rows) == 3
    assert {row["geography_id"] for row in rows} == {"place-bog-001"}
    assert len(department_response.json()["items"]) == 3
    assert len(national_response.json()["items"]) == 6
    assert all(
        [candidate["candidate_id"] for candidate in result["candidates"]]
        == ["candidatura-horizonte"]
        for result in candidate_response.json()["items"]
    )
    assert all(
        [candidate["candidate_id"] for candidate in json.loads(row["candidates"])]
        == ["candidatura-horizonte"]
        for row in csv.DictReader(io.StringIO(candidate_csv.text))
    )
    assert candidate_csv.headers["content-disposition"] == (
        'attachment; filename="filtered-results.csv"'
    )


def test_cache_provenance_and_unknown_vs_zero_are_preserved() -> None:
    with client() as api:
        summary = api.get(f"/api/v1/elections/{SLUG}/summary")
        not_modified = api.get(
            f"/api/v1/elections/{SLUG}/summary", headers={"If-None-Match": summary.headers["etag"]}
        )
        weak_not_modified = api.get(
            f"/api/v1/elections/{SLUG}/summary",
            headers={"If-None-Match": f'"unrelated,tag", W/{summary.headers["etag"]}'},
        )
        wildcard_not_modified = api.get(
            f"/api/v1/elections/{SLUG}/summary", headers={"If-None-Match": "*"}
        )
        result = api.get(f"/api/v1/elections/{SLUG}/results?limit=200").json()
        bulletin = api.get("/api/v1/bulletins/bulletin-01/results").json()
    assert "max-age=3600" in summary.headers["cache-control"]
    assert not_modified.status_code == 304
    assert weak_not_modified.status_code == 304
    assert wildcard_not_modified.status_code == 304
    zero = next(item for item in result["items"] if item["id"] == "result-006")
    assert zero["unmarked_votes"] == {"value": 0, "status": "observed"}
    assert bulletin["result"]["registered_electors"] == {"value": None, "status": "unknown"}
    provenance = zero["provenance"]
    assert provenance["content_hash"] == "a" + "6" * 63
    assert provenance["source_type"] == "pre_count"


def test_optional_geographic_collection_coverage_is_exposed_without_changing_completion() -> None:
    fixture = json.loads((ROOT / "data/fixtures/fixture-release.json").read_text())
    fixture["summary"]["geographic_collection_coverage"] = {
        "status": "sample_limited",
        "expected_polling_places": 1,
        "retrieved_polling_places": 1,
        "expected_mesas": 122_020,
        "retrieved_mesas": 36,
    }
    repository = FixtureRepository.from_snapshot(fixture, is_fixture=False)
    with TestClient(create_app(repository=repository)) as api:
        summary = api.get(f"/api/v1/elections/{SLUG}/summary").json()
    assert (
        summary["geographic_collection_coverage"]
        == fixture["summary"]["geographic_collection_coverage"]
    )
    assert summary["completion"] == fixture["summary"]["completion"]


def test_fixture_arithmetic_and_safe_dataset_redirect() -> None:
    with client() as api:
        results = api.get(f"/api/v1/elections/{SLUG}/results?limit=200").json()["items"]
        redirect = api.get("/api/v1/datasets/fixture-results-json/download", follow_redirects=False)
        downloaded = api.get("/api/v1/datasets/fixture-results-json/download")
    for result in results:
        assert (
            sum(candidate["votes"]["value"] for candidate in result["candidates"])
            == result["valid_votes"]["value"]
        )
    assert redirect.status_code == 302
    assert "example.invalid" not in redirect.headers["location"]
    assert downloaded.status_code == 200
    assert "immutable" in redirect.headers["cache-control"]


def test_fixture_download_redirect_is_relative_and_untrusted_hosts_are_rejected() -> None:
    with client() as api:
        response = api.get(
            "/api/v1/datasets/fixture-results-json/download",
            headers={"host": "attacker.example"},
            follow_redirects=False,
        )
    assert response.status_code == 400

    app = create_app(
        settings=Settings(trusted_hosts="testserver,attacker.example"),
        repository=FixtureRepository(ROOT / "data/fixtures/fixture-release.json"),
    )
    with TestClient(app) as api:
        response = api.get(
            "/api/v1/datasets/fixture-results-json/download",
            headers={"host": "attacker.example"},
            follow_redirects=False,
        )
    assert response.headers["location"] == "/api/v1/datasets/fixture-results-json/download?raw=true"


def test_csv_export_neutralizes_spreadsheet_formula_cells() -> None:
    fixture = json.loads((ROOT / "data/fixtures/fixture-release.json").read_text())
    result = fixture["results"][0]
    result["id"] = "=formula"
    result["geography_id"] = "+place"
    result["mesa_id"] = "-mesa"
    repository = FixtureRepository.from_snapshot(fixture, is_fixture=True)
    with TestClient(create_app(repository=repository)) as api:
        response = api.get(f"/api/v1/elections/{SLUG}/results?format=csv")
    row = next(csv.DictReader(io.StringIO(response.text)))
    assert row["id"] == "'=formula"
    assert row["geography_id"] == "'+place"
    assert row["mesa_id"] == "'-mesa"


def test_normalized_csv_export_neutralizes_spreadsheet_formula_cells() -> None:
    metrics = {
        name: {"value": None, "status": "unavailable"}
        for name in (
            "registered_electors",
            "voters",
            "valid_votes",
            "blank_votes",
            "null_votes",
            "unmarked_votes",
        )
    }
    row: dict[str, object] = {
        "id": "=formula",
        "geography_id": "+place",
        "geography_level": "mesa",
        "mesa_id": "-mesa",
        "source_id": "@source",
        "source_type": "scrutiny",
        "legal_status": "official_scrutiny",
        "source_url": "https://official.example/source",
        "retrieved_at": "2026-08-03T12:00:00Z",
        "content_hash": "a" * 64,
        "parser_version": "v1",
        "transform_version": "v1",
        "metrics": metrics,
    }
    exported = _normalized_csv_row(row, "release-1", "election-1")
    parsed = next(
        csv.DictReader(
            io.StringIO(exported), fieldnames=_normalized_csv_header().strip().split(",")
        )
    )
    assert parsed["id"] == "'=formula"
    assert parsed["geography_id"] == "'+place"
    assert parsed["mesa_id"] == "'-mesa"
    assert parsed["source_id"] == "'@source"


def test_empty_review_page_keeps_permanent_methodology_disclosure() -> None:
    with client() as api:
        response = api.get(f"/api/v1/review-signals?election_slug={SLUG}&minimum_score=99")
    body = response.json()
    assert body["items"] == []
    assert body["methodology_version"] == "audit-priority-v1.0.0"
    assert body["disclosure"]["en"].startswith("This score prioritizes")


def test_release_with_no_scored_records_still_exposes_permanent_disclosure() -> None:
    fixture = json.loads((ROOT / "data/fixtures/fixture-release.json").read_text())
    fixture["review_signals"] = []
    repository = FixtureRepository.from_snapshot(fixture, is_fixture=False)
    with TestClient(create_app(repository=repository)) as api:
        response = api.get(f"/api/v1/review-signals?election_slug={SLUG}")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["disclosure"]["es"].startswith("Este puntaje prioriza registros")


def test_production_repository_selection_security_and_artifact_redirect() -> None:
    with pytest.raises(ValidationError, match="CURSOR_SECRET"):
        Settings(database_url="postgresql://reader@db.example.test/elections")
    settings = Settings(
        database_url="postgresql://reader@db.example.test/elections",
        cursor_secret=TEST_CURSOR_SECRET,
    )
    assert isinstance(select_repository(settings), PostgresReadRepository)
    with pytest.raises(ValueError, match="PostgreSQL"):
        select_repository(
            Settings(database_url="sqlite:///not-production.db", cursor_secret=TEST_CURSOR_SECRET)
        )

    fixture = ProductionFixtureRepository(ROOT / "data/fixtures/fixture-release.json")
    app = create_app(
        settings=Settings(
            cursor_secret=TEST_CURSOR_SECRET,
            artifact_hosts="artifacts.example.test",
        ),
        repository=fixture,
    )
    with TestClient(app) as api:
        response = api.get("/api/v1/datasets/fixture-results-json/download", follow_redirects=False)
        raw = api.get("/api/v1/datasets/fixture-results-json/download?raw=true")
    assert response.status_code == 302
    assert response.headers["location"] == "https://artifacts.example.test/releases/results.json"
    assert raw.status_code == 400


def test_active_release_override_pointer_and_database_mode_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = tmp_path / "current-release.json"
    pointer.write_text('{"release_id":"pointer-release"}', encoding="utf-8")
    monkeypatch.setenv("ACTIVE_RELEASE", "environment-release")
    selected = select_repository(
        Settings(
            database_url="postgresql://reader@db.example.test/elections",
            cursor_secret=TEST_CURSOR_SECRET,
            active_release_pointer=pointer,
        )
    )
    assert isinstance(selected, PostgresReadRepository)
    assert selected.active_release_id == "environment-release"

    monkeypatch.delenv("ACTIVE_RELEASE")
    pointer_selected = select_repository(
        Settings(
            database_url="postgresql://reader@db.example.test/elections",
            cursor_secret=TEST_CURSOR_SECRET,
            active_release_pointer=pointer,
        )
    )
    assert isinstance(pointer_selected, PostgresReadRepository)
    assert pointer_selected.active_release_id == "pointer-release"

    invalid_pointer = tmp_path / "invalid-release.json"
    invalid_pointer.write_text("{}", encoding="utf-8")
    for unavailable_pointer in (invalid_pointer, tmp_path / "missing-release.json"):
        with pytest.raises(ValueError, match="ACTIVE_RELEASE|release_id"):
            select_repository(
                Settings(
                    database_url="postgresql://reader@db.example.test/elections",
                    cursor_secret=TEST_CURSOR_SECRET,
                    active_release_pointer=unavailable_pointer,
                )
            )

    fixture = select_repository(
        Settings(
            active_release_pointer=tmp_path / "missing-does-not-matter-in-fixture-mode.json",
            fixture_path=ROOT / "data/fixtures/fixture-release.json",
        )
    )
    assert isinstance(fixture, FixtureRepository)


def test_release_owned_database_keys_and_relations_are_composite() -> None:
    scoped_id_tables = {
        "candidate_slates",
        "crawls",
        "source_provenance",
        "polling_places",
        "mesas",
        "result_facts",
        "candidate_votes",
        "documents",
        "reconciliations",
        "signal_scores",
        "signal_components",
        "datasets",
    }
    for table_name in scoped_id_tables:
        table = Base.metadata.tables[table_name]
        assert {column.name for column in table.primary_key.columns} == {"id", "release_id"}
    methodologies = Base.metadata.tables["methodologies"]
    assert {column.name for column in methodologies.primary_key.columns} == {
        "version",
        "release_id",
    }

    def foreign_key_targets(table_name: str) -> set[tuple[str, ...]]:
        table = Base.metadata.tables[table_name]
        return {
            tuple(element.target_fullname for element in constraint.elements)
            for constraint in table.foreign_key_constraints
        }

    assert ("mesas.id", "mesas.release_id") in foreign_key_targets("documents")
    assert ("result_facts.id", "result_facts.release_id") in foreign_key_targets("candidate_votes")
    assert ("candidate_slates.id", "candidate_slates.release_id") in foreign_key_targets(
        "candidate_votes"
    )
    assert ("signal_scores.id", "signal_scores.release_id") in foreign_key_targets(
        "signal_components"
    )


@pytest.mark.parametrize(
    ("value", "status"),
    [(None, "observed"), (0, "unknown"), (5, "unavailable"), (1, "not_applicable")],
)
def test_metric_value_rejects_invalid_unknown_vs_zero_combinations(
    value: int | None, status: str
) -> None:
    from elecciones_api.schemas import MetricValue

    with pytest.raises(ValidationError):
        MetricValue.model_validate({"value": value, "status": status})
