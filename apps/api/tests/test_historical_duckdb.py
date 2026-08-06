"""Real immutable historical Parquet API contract tests."""
# ruff: noqa: S106

import hashlib
import os
from pathlib import Path

import duckdb
import pytest
from elecciones_api.config import Settings
from elecciones_api.historical_repository import (
    HistoricalDuckDBRepository,
    HistoricalReleaseError,
)
from elecciones_api.federated_repository import FederatedRepository
from elecciones_api.main import create_app, select_repository
from fastapi.testclient import TestClient

DATA = Path(__file__).parents[3] / "data"
RELEASES = (
    "historical-2018-mmv-context-v2-c456aeb032917d5c",
    "historical-2022-mmv-context-v2-288e9b41c14730e9",
)


def _packaged(tmp_path: Path) -> Path:
    """The image's /app/data layout, symlinked to the real checked-in releases."""
    packaged = tmp_path / "data"
    (packaged / "manifests").mkdir(parents=True)
    (packaged / "releases").mkdir()
    for release_id in RELEASES:
        os.symlink(
            DATA / "manifests" / f"{release_id}.json",
            packaged / "manifests" / f"{release_id}.json",
        )
        os.symlink(DATA / "releases" / release_id, packaged / "releases" / release_id)
    return packaged


def test_build_time_geography_index_is_read_only_and_serves_all_scopes(
    tmp_path: Path,
) -> None:
    packaged = tmp_path / "data"
    (packaged / "manifests").mkdir(parents=True)
    (packaged / "releases").mkdir()
    for release_id in RELEASES:
        os.symlink(
            DATA / "manifests" / f"{release_id}.json",
            packaged / "manifests" / f"{release_id}.json",
        )
        os.symlink(
            DATA / "releases" / release_id,
            packaged / "releases" / release_id,
        )
    repository = HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])
    index = packaged / "historical-geography.duckdb"
    repository.build_geography_read_model(index)
    repository.close()
    index.chmod(0o444)

    indexed = HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])
    for release_id, year in zip(RELEASES, ("2018", "2022"), strict=True):
        for round_number in (1, 2):
            rows = indexed.normalized_results(
                release_id,
                f"presidencia-{year}-round-{round_number}",
                {"geography_level": "mesa"},
                None,
                1,
            )
            assert len(rows) == 2
            assert rows[0]["geography_level"] == "mesa"
    filtered = indexed.normalized_results(
        RELEASES[1],
        "presidencia-2022-round-2",
        {"geography_level": "mesa", "category_key": "1235:002"},
        None,
        1,
    )
    assert filtered
    summary = indexed.normalized_summary(RELEASES[1], "presidencia-2022-round-2")
    coverage = summary["coverage"]
    assert isinstance(coverage, dict)
    observed_categories = coverage["observed_category_facts"]
    assert isinstance(observed_categories, int) and observed_categories > 400_000
    indexed.close()

    connection = duckdb.connect(str(index), read_only=True)
    try:
        with pytest.raises(duckdb.InvalidInputException):
            connection.execute("CREATE TABLE forbidden(value INTEGER)")
    finally:
        connection.close()

    index.chmod(0o644)
    connection = duckdb.connect(str(index))
    try:
        original_name = connection.execute(
            """SELECT name FROM geography
               WHERE election_slug='presidencia-2022-round-2'
                 AND id='r2:co'"""
        ).fetchone()
        assert original_name is not None
        connection.execute(
            """UPDATE geography SET name='CORRUPTED'
               WHERE election_slug='presidencia-2022-round-2'
               AND id='r2:co'"""
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    index.chmod(0o444)
    with pytest.raises(HistoricalReleaseError, match="content digest"):
        HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])

    # Restoring geography but changing category data, its group digest, and the
    # mutable metadata together must still fail against the independently pinned
    # source digest.
    index.chmod(0o644)
    connection = duckdb.connect(str(index))
    try:
        connection.execute(
            """UPDATE geography SET name=?
               WHERE election_slug='presidencia-2022-round-2'
                 AND id='r2:co'""",
            [original_name[0]],
        )
        category_row = connection.execute(
            """SELECT categories FROM category_groups
               WHERE election_slug='presidencia-2022-round-2'
                 AND geography_id='r2:co'"""
        ).fetchone()
        assert category_row is not None
        altered_categories = category_row[0]
        altered_categories[0]["votes"] += 1
        altered_digest = connection.execute(
            "SELECT sha256(to_json(?))", [altered_categories]
        ).fetchone()
        assert altered_digest is not None
        connection.execute(
            """UPDATE category_groups
               SET categories=?,category_digest=?
               WHERE election_slug='presidencia-2022-round-2'
                 AND geography_id='r2:co'""",
            [altered_categories, altered_digest[0]],
        )
        release_digest = HistoricalDuckDBRepository._category_digest(
            connection,
            "category_groups",
            [],
            {"presidencia-2022-round-1", "presidencia-2022-round-2"},
            grouped=True,
        )
        connection.execute(
            """UPDATE read_model_metadata SET category_served_digest=?
               WHERE release_id=?""",
            [release_digest, RELEASES[1]],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    index.chmod(0o444)
    with pytest.raises(HistoricalReleaseError, match="metadata|content digest"):
        HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])


def test_historical_sort_spill_does_not_write_to_application_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = HistoricalDuckDBRepository(DATA, RELEASES, RELEASES[1])
    monkeypatch.chdir(tmp_path)
    tmp_path.chmod(0o555)
    try:
        rows = repository.normalized_results(
            RELEASES[1],
            "presidencia-2022-round-2",
            {"geography_level": "mesa"},
            None,
            1,
        )
    finally:
        tmp_path.chmod(0o755)
        repository.close()
    assert len(rows) == 2
    assert rows[0]["geography_level"] == "mesa"
    assert not (tmp_path / ".tmp").exists()


def test_real_context_api_is_preview_and_fail_closed() -> None:
    repository = HistoricalDuckDBRepository(DATA, RELEASES, RELEASES[1])
    settings = Settings(
        historical_releases=",".join(RELEASES),
        historical_data_path=DATA,
        active_release_id=RELEASES[1],
        cursor_secret="historical-test-secret-with-enough-entropy",
        trusted_hosts="testserver",
        cors_origins="https://one.vercel.app,https://two.vercel.app",
    )
    base = f"/api/v1/releases/{RELEASES[1]}/elections/presidencia-2022-round-2"
    with TestClient(create_app(settings, repository)) as client:
        assert client.get("/readyz").json() == {
            "status": "ready",
            "release_status": "candidate",
            "release_class": "context_only",
        }
        first = client.get(f"{base}/results?geography_path=r2:co&limit=2").json()
        second = client.get(
            f"{base}/results?geography_path=r2:co&limit=2&cursor={first['page']['next_cursor']}"
        ).json()
        assert first["items"][0]["registered_electors"] == {
            "value": None,
            "status": "unavailable",
        }
        assert second["items"][0]["geography_level"] == "department"
        assert client.get(f"{base}/results?source_id=wrong").json()["items"] == []
        assert client.get(f"{base}/results?category_key=malformed").json()["items"] == []
        summary = client.get(f"{base}/summary").json()
        assert summary["release_status"] == "candidate"
        assert summary["release_class"] == "context_only"
        assert summary["completion"]["status"] == "unknown"
        assert summary["coverage"]["status"] == "unknown"
        assert "candidates" not in summary
        assert summary["coverage"]["observed_result_facts"] > 100_000
        assert summary["national_categories"]
        assert summary["provenance"]["preview_caveat"]
        assert all(
            item["provenance"]["legal_status"] == "context_only"
            for item in summary["national_categories"]
        )
        assert client.get(f"{base}/analysis/summary").status_code == 404
        assert client.get(f"{base}/outcome-sensitivity").status_code == 404
        datasets = client.get(f"{base}/datasets").json()
        assert len(datasets) == 3
        assert all(item["schema_url"] is None for item in datasets)
        assert all(item["url"].startswith("/api/v1/") for item in datasets)
        downloaded = client.get(datasets[0]["url"])
        assert downloaded.status_code == 200
        assert len(downloaded.content) == datasets[0]["byte_size"]
        assert hashlib.sha256(downloaded.content).hexdigest() == datasets[0]["content_hash"]
        comparison = client.get(
            f"{base}/historical-comparison",
            params={
                "baseline_release_id": RELEASES[0],
                "baseline_election_slug": "presidencia-2018-round-2",
                "geography_id": "r2:co",
                "grain": "national",
            },
        ).json()
        assert comparison["eligible_for_integrity_analysis"] is False
        assert "score" not in comparison and "affected_votes" not in comparison

        mesa_id = "r2:mesa:01:001:01:01:001"
        geography = client.get(f"{base}/geographies/{mesa_id}")
        assert geography.status_code == 200
        assert geography.json()["item"]["level"] == "mesa"
        path = client.get(f"{base}/geographies/{mesa_id}/path").json()
        assert [item["level"] for item in path["items"]] == [
            "national",
            "department",
            "municipality",
            "zone",
            "polling_place",
            "mesa",
        ]
        mesa = client.get(f"{base}/mesas/{mesa_id}").json()
        assert mesa["id"] == mesa_id
        fact_id = mesa["results"][0]["id"]
        categories = client.get(f"{base}/result-facts/{fact_id}/categories").json()
        assert categories["items"]
        assert all(item["status"] == "observed" for item in categories["items"])

        legacy_routes = (
            f"/api/v1/elections/presidencia-2022-round-2/summary?data_version={RELEASES[1]}",
            f"/api/v1/elections/presidencia-2022-round-2/results?data_version={RELEASES[1]}",
            f"/api/v1/geographies/r2:co?data_version={RELEASES[1]}",
            f"/api/v1/mesas/r2:mesa:01:001:01:01:001?data_version={RELEASES[1]}",
            f"/api/v1/mesas/r2:mesa:01:001:01:01:001/evidence?data_version={RELEASES[1]}",
            f"/api/v1/mesas/r2:mesa:01:001:01:01:001/comparisons?data_version={RELEASES[1]}",
            f"/api/v1/bulletins?election_slug=presidencia-2022-round-2&data_version={RELEASES[1]}",
            f"/api/v1/bulletins/context-only/results?data_version={RELEASES[1]}",
            f"/api/v1/review-signals?election_slug=presidencia-2022-round-2&data_version={RELEASES[1]}",
            f"/api/v1/datasets?election_slug=presidencia-2022-round-2&data_version={RELEASES[1]}",
            f"/api/v1/datasets/historical-2022-mmv-parquet/download?data_version={RELEASES[1]}",
        )
        for path in legacy_routes:
            response = client.get(path)
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["title"] == "Legacy contract unavailable"
            assert "release-scoped" in response.json()["detail"]


def test_malformed_context_summary_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = HistoricalDuckDBRepository(DATA, RELEASES, RELEASES[1])
    original = repository.normalized_summary

    def malformed(release_id: str, election_slug: str) -> dict[str, object]:
        payload = original(release_id, election_slug)
        payload["completion"] = {"expected": 0, "reported": 0, "percent": 0}
        return payload

    monkeypatch.setattr(repository, "normalized_summary", malformed)
    settings = Settings(
        historical_releases=",".join(RELEASES),
        historical_data_path=DATA,
        active_release_id=RELEASES[1],
        cursor_secret="historical-test-secret-with-enough-entropy",
        trusted_hosts="testserver",
    )
    path = (
        f"/api/v1/releases/{RELEASES[1]}"
        "/elections/presidencia-2022-round-2/summary"
    )
    with TestClient(create_app(settings, repository)) as client:
        response = client.get(path)
    assert response.status_code == 503
    assert response.json()["title"] == "Read model unavailable"


def test_public_elections_never_advertises_another_release_elections(tmp_path: Path) -> None:
    """The shared read model holds every release's geography in one table, so
    the listing must be scoped by the manifest's own declared slugs. Otherwise
    each release advertises all four elections -- misstating provenance and
    producing release/election URLs the data path correctly rejects with 404."""
    packaged = tmp_path / "data"
    (packaged / "manifests").mkdir(parents=True)
    (packaged / "releases").mkdir()
    for release_id in RELEASES:
        os.symlink(
            DATA / "manifests" / f"{release_id}.json",
            packaged / "manifests" / f"{release_id}.json",
        )
        os.symlink(DATA / "releases" / release_id, packaged / "releases" / release_id)

    repository = HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])
    index = packaged / "historical-geography.duckdb"
    repository.build_geography_read_model(index)
    repository.close()

    indexed = HistoricalDuckDBRepository(packaged, RELEASES, RELEASES[1])
    listed = indexed.public_elections()

    # Exactly the two rounds each release actually carries.
    assert len(listed) == 4, listed
    by_release: dict[str, set[str]] = {}
    for entry in listed:
        by_release.setdefault(str(entry["release_id"]), set()).add(str(entry["election_slug"]))
    assert by_release == {
        RELEASES[0]: {"presidencia-2018-round-1", "presidencia-2018-round-2"},
        RELEASES[1]: {"presidencia-2022-round-1", "presidencia-2022-round-2"},
    }
    # Every advertised pairing must actually resolve.
    for entry in listed:
        rows = indexed.normalized_results(
            str(entry["release_id"]), str(entry["election_slug"]), {}, None, 1
        )
        assert rows


def test_duckdb_only_mode_still_refuses_an_unpackaged_active_release(tmp_path: Path) -> None:
    """The invariant that makes the federated case below non-obvious: with no
    Postgres backend, ACTIVE_RELEASE must name a release this repository holds."""
    packaged = _packaged(tmp_path)
    with pytest.raises(HistoricalReleaseError, match="ACTIVE_RELEASE"):
        HistoricalDuckDBRepository(packaged, RELEASES, "candidate-2026-r2-dacb28aa766eec87")


def test_federated_startup_survives_a_postgres_owned_active_release(tmp_path: Path) -> None:
    """The production configuration: ACTIVE_RELEASE is the 2026 release Postgres
    holds, while the packaged DuckDB releases keep serving 2018 and 2022.

    Passing that id straight through to the DuckDB half aborted startup with
    "ACTIVE_RELEASE is not one of the verified packaged releases", so importing
    the app raised and the container never bound a port.
    """
    packaged = _packaged(tmp_path)
    settings = Settings(
        database_url="postgresql://reader@db.example.test/elections",
        cursor_secret="a" * 64,
        historical_releases=",".join(RELEASES),
        historical_data_path=packaged,
        active_release_id="candidate-2026-r2-dacb28aa766eec87",
    )
    selected = select_repository(settings)
    assert isinstance(selected, FederatedRepository)
    # Both halves are reachable, and the 2026 id routes to Postgres.
    assert selected.holds_historical(RELEASES[0])
    assert selected.holds_historical(RELEASES[1])
    assert not selected.holds_historical("candidate-2026-r2-dacb28aa766eec87")
    assert {str(row["release_id"]) for row in selected._historical.public_elections()} == set(
        RELEASES
    )
    # Postgres keeps the true active release; the DuckDB half defaults to the
    # newest release it actually verified.
    assert selected._postgres.active_release_id == "candidate-2026-r2-dacb28aa766eec87"
    assert selected._historical.active_release_id == RELEASES[1]
    selected.close()


def test_federated_rollback_to_a_historical_active_release_keeps_it(tmp_path: Path) -> None:
    """Rolling ACTIVE_RELEASE back to a packaged release must not silently
    retarget the DuckDB half at a different election."""
    packaged = _packaged(tmp_path)
    selected = select_repository(
        Settings(
            database_url="postgresql://reader@db.example.test/elections",
            cursor_secret="a" * 64,
            historical_releases=",".join(RELEASES),
            historical_data_path=packaged,
            active_release_id=RELEASES[0],
        )
    )
    assert isinstance(selected, FederatedRepository)
    assert selected._historical.active_release_id == RELEASES[0]
    selected.close()
