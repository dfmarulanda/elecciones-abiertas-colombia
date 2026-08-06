"""Stage A/Stage B tests for the standard 2026 release loader.

The fixture snapshot is deliberately built with the *same* id-width trap as the
real release: polling-place codes are 9 and 11 characters and mesa ids are
therefore 15 and 17.  Any loader that recovers a mesa's polling place by slicing
its id fails these tests instead of silently misassigning half the country.
"""
# ruff: noqa: S603

import json
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from elecciones_pipeline.releases._bulk import ReleaseLoadError
from elecciones_pipeline.releases.snapshot_parquet import (
    CATEGORY_ARTIFACT,
    ELECTION_SLUG,
    FACT_ARTIFACT,
    GEOGRAPHY_ARTIFACT,
    LOAD_MANIFEST,
    MESA_ARTIFACT,
    SOURCE_MESA,
    SOURCE_NATIONAL,
    SOURCE_PLACE,
    SOURCE_ROLLUP,
    snapshot_to_parquet,
)
from elecciones_pipeline.releases.standard_postgres_loader import load_standard_2026_release
from sqlalchemy import create_engine, text

REPOSITORY = Path(__file__).resolve().parents[3]
REAL_ARTIFACTS = (
    REPOSITORY
    / "data/releases/candidate-2026-r2-dacb28aa766eec87/postgres-load"
    / LOAD_MANIFEST
)
BIN = Path("/opt/homebrew/bin")
CANDIDATES = ("ivan-cepeda-aida-quilcue", "abelardo-de-la-espriella-jose-manuel-restrepo")
# 19 published geographies, 16 mesas, 25 published facts, 10 derived aggregates.
FIXTURE_GEOGRAPHIES = 19
FIXTURE_MESAS = 16
FIXTURE_FACTS = 25
FIXTURE_AGGREGATES = 10


def _metric(value: int | None) -> dict[str, Any]:
    return {"value": value, "status": "observed" if value is not None else "unavailable"}


def _fact(
    fact_id: str,
    geography_id: str,
    level: str,
    mesa_id: str | None,
    totals: dict[str, int],
    slate: dict[str, int],
    url: str,
    content_hash: str,
) -> dict[str, Any]:
    return {
        "id": fact_id,
        "election_slug": ELECTION_SLUG,
        "geography_id": geography_id,
        "geography_level": level,
        "mesa_id": mesa_id,
        **{name: _metric(totals[name]) for name in totals},
        "registered_electors": _metric(None),
        "candidates": [
            {"candidate_id": candidate, "votes": _metric(votes)}
            for candidate, votes in slate.items()
        ],
        "provenance": {
            "data_version": "candidate-2026-r2-fixture",
            "source_type": "pre_count",
            "legal_status": "preliminary",
            "source_url": url,
            "retrieved_at": "2026-08-03T23:47:10.005016+00:00",
            "content_hash": content_hash,
            "parser_version": "registraduria-precount-act@1.0.0",
            "transform_version": "precount-normalized@1.0.0",
            "methodology_version": None,
        },
    }


def _snapshot() -> dict[str, Any]:
    """A miniature release with the real id-width trap and real arithmetic."""
    root = "https://resultadosprecpresidente2026-2v.registraduria.gov.co/json/ACT/PR/"
    geographies = [
        {"id": "CO", "level": "national", "code": "00", "name": "COLOMBIA", "parent_id": None}
    ]
    mesas: list[dict[str, Any]] = []
    places: list[tuple[str, str, str]] = []
    for department in ("01", "02"):
        geographies.append(
            {
                "id": f"scope:{department}",
                "level": "department",
                "code": department,
                "name": f"DEP {department}",
                "parent_id": "CO",
            }
        )
        for municipality in ("001", "002"):
            municipality_code = f"{department}{municipality}"
            geographies.append(
                {
                    "id": f"scope:{municipality_code}",
                    "level": "municipality",
                    "code": municipality_code,
                    "name": f"MUN {municipality_code}",
                    "parent_id": f"scope:{department}",
                }
            )
            zone_code = f"{municipality_code}01"
            geographies.append(
                {
                    "id": f"scope:{zone_code}",
                    "level": "zone",
                    "code": zone_code,
                    "name": f"ZONA {zone_code}",
                    "parent_id": f"scope:{municipality_code}",
                }
            )
            # One 9-character place code and one 11-character place code under
            # the same 7-character zone: exactly the real width distribution.
            for suffix in ("01", "0102"):
                place_code = f"{zone_code}{suffix}"
                geographies.append(
                    {
                        "id": f"scope:{place_code}",
                        "level": "polling_place",
                        "code": place_code,
                        "name": f"PUESTO {place_code}",
                        "parent_id": f"scope:{zone_code}",
                    }
                )
                places.append((place_code, municipality_code, department))
                for number in (1, 2):
                    display_number = f"{number:06d}"
                    mesas.append(
                        {
                            "id": f"{place_code}{display_number}",
                            "display_number": display_number,
                            "polling_place_id": f"scope:{place_code}",
                            "municipality_id": f"scope:{municipality_code}",
                            "department_id": f"scope:{department}",
                        }
                    )
    for geography in geographies:
        geography["authoritative_coordinates"] = None

    results: list[dict[str, Any]] = []
    national = dict.fromkeys(("voters", "valid_votes", "blank_votes", "null_votes"), 0)
    national["unmarked_votes"] = 0
    national_slate = dict.fromkeys(CANDIDATES, 0)
    for index, (place_code, _municipality, _department) in enumerate(places):
        place_totals = dict.fromkeys(national, 0)
        place_slate = dict.fromkeys(CANDIDATES, 0)
        for number in (1, 2):
            display_number = f"{number:06d}"
            mesa_id = f"{place_code}{display_number}"
            first = 10 + index + number
            second = 20 + index * 2 + number
            blank, null, unmarked = 1, 2, 3
            valid = first + second + blank
            totals = {
                "voters": valid + null + unmarked,
                "valid_votes": valid,
                "blank_votes": blank,
                "null_votes": null,
                "unmarked_votes": unmarked,
            }
            slate = {CANDIDATES[0]: first, CANDIDATES[1]: second}
            results.append(
                _fact(
                    f"precount-mesa-{mesa_id}",
                    # The snapshot files a mesa fact against its POLLING PLACE.
                    f"scope:{place_code}",
                    "mesa",
                    mesa_id,
                    totals,
                    slate,
                    f"{root}{mesa_id}.json",
                    f"{index:02d}{number}" + "a" * 61,
                )
            )
            for name, value in totals.items():
                place_totals[name] += value
            for candidate, votes in slate.items():
                place_slate[candidate] += votes
        results.append(
            _fact(
                f"precount-place-{place_code}",
                f"scope:{place_code}",
                "polling_place",
                None,
                place_totals,
                place_slate,
                f"{root}{place_code}.json",
                f"{index:02d}0" + "b" * 61,
            )
        )
        for name, value in place_totals.items():
            national[name] += value
        for candidate, votes in place_slate.items():
            national_slate[candidate] += votes
    results.append(
        _fact(
            "precount-national-00",
            "CO",
            "national",
            None,
            national,
            national_slate,
            f"{root}00.json",
            "c" * 64,
        )
    )
    results[-1]["provenance"]["transform_version"] = "precount-national-candidate@1.0.0"
    results[-1]["registered_electors"] = _metric(41421973)
    return {
        "election": {
            "slug": ELECTION_SLUG,
            "round": 2,
            "election_date": "2026-06-21",
            "name": {"es": "Presidencia 2026", "en": "2026 presidency"},
            "candidates": [
                {"id": candidate, "ballot_number": number, "name": {"es": candidate, "en": candidate}}
                for number, candidate in enumerate(CANDIDATES, start=1)
            ],
        },
        "release": {
            "release_id": "candidate-2026-r2-fixture",
            "data_version": "candidate-2026-r2-fixture",
            "status": "candidate",
            "synthetic": False,
            "methodology_version": "audit-priority-v1.0.0",
            "created_at": "2026-08-03T23:29:43.947689Z",
        },
        "summary": {
            "data_version": "candidate-2026-r2-fixture",
            "completion": {"expected": 16, "reported": 15, "percent": 0.9375},
            "coverage": {"expected": 1, "retrieved": 1, "parsed": 1, "missing": 0},
            "geographic_collection_coverage": {"status": "full_scope", "expected_mesas": 16},
            "reconciliation": {"status": "blocked", "checked_facts": 24, "exceptions": 3},
            "turnout": 0.6360238803690013,
        },
        "geographies": geographies,
        "mesas": mesas,
        "results": results,
    }


def _manifest() -> dict[str, Any]:
    return {
        "release_id": "candidate-2026-r2-fixture",
        "data_version": "candidate-2026-r2-fixture",
        "election_slug": ELECTION_SLUG,
        "release_class": "standard",
        "status": "candidate",
        "synthetic": False,
        "methodology_version": "audit-priority-v1.0.0",
        "sources": [
            {
                "id": SOURCE_NATIONAL,
                "source_type": "pre_count",
                "legal_status": "preliminary",
                "source_url": (
                    "https://resultadosprecpresidente2026-2v.registraduria.gov.co"
                    "/json/ACT/PR/00.json"
                ),
                "content_hash": "c" * 64,
                "parser_version": "registraduria-precount-act@1.0.0",
                "transform_version": "precount-national-candidate@1.0.0",
                "retrieved_at": "2026-08-03T23:29:43.947689+00:00",
            }
        ],
    }


@pytest.fixture
def staged(tmp_path: Path) -> tuple[Path, Path]:
    snapshot = tmp_path / "api-snapshot.json"
    snapshot.write_text(json.dumps(_snapshot()), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    snapshot_to_parquet(snapshot, tmp_path / "artifacts")
    return manifest, tmp_path / "artifacts"


def _table(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def test_stage_a_emits_every_artifact_with_matching_counts(staged: tuple[Path, Path]) -> None:
    _, artifacts = staged
    load_manifest = json.loads((artifacts / LOAD_MANIFEST).read_text())
    counts = {entry["filename"]: entry["record_count"] for entry in load_manifest["artifacts"]}
    assert counts == {
        GEOGRAPHY_ARTIFACT: FIXTURE_GEOGRAPHIES,
        MESA_ARTIFACT: FIXTURE_MESAS,
        FACT_ARTIFACT: FIXTURE_FACTS,
        CATEGORY_ARTIFACT: FIXTURE_FACTS * len(CANDIDATES),
    }
    for entry in load_manifest["artifacts"]:
        assert len(entry["content_hash"]) == 64
        assert entry["byte_size"] == (artifacts / entry["filename"]).stat().st_size
    # Verbatim, not recomputed: a blocked reconciliation stays blocked.
    assert load_manifest["summary"]["reconciliation"] == {
        "status": "blocked",
        "checked_facts": 24,
        "exceptions": 3,
    }
    assert {source["id"] for source in load_manifest["sources"]} == {
        SOURCE_NATIONAL,
        SOURCE_PLACE,
        SOURCE_MESA,
        SOURCE_ROLLUP,
    }


def test_stage_a_never_derives_a_polling_place_from_a_mesa_id(staged: tuple[Path, Path]) -> None:
    _, artifacts = staged
    mesas = {row["id"]: row for row in _table(artifacts / MESA_ARTIFACT)}
    widths = {len(identifier) for identifier in mesas}
    assert widths == {15, 17}, "the fixture must reproduce the variable-width trap"
    places = {
        row["code"]: row["id"]
        for row in _table(artifacts / GEOGRAPHY_ARTIFACT)
        if row["level"] == "polling_place"
    }
    assert {len(code) for code in places} == {9, 11}
    for identifier, mesa in mesas.items():
        assert mesa["polling_place_id"] == places[identifier[: -len(mesa["display_number"])]]
        # And the slice a careless loader would take is wrong for half of them.
        sliced = places.get(identifier[:9])
        if len(identifier) == 17:
            assert sliced != mesa["polling_place_id"]


def test_stage_a_rewrites_mesa_facts_onto_their_own_mesa(staged: tuple[Path, Path]) -> None:
    _, artifacts = staged
    facts = _table(artifacts / FACT_ARTIFACT)
    mesa_facts = [fact for fact in facts if fact["geography_level"] == "mesa"]
    assert len(mesa_facts) == FIXTURE_MESAS
    for fact in mesa_facts:
        assert fact["geography_id"] == fact["mesa_id"]
        # The pre-rewrite value survives, and it is the polling place.
        assert fact["source_geography_id"].startswith("scope:")
        assert fact["source_geography_id"] != fact["geography_id"]
        assert fact["source_id"] == SOURCE_MESA
    for fact in facts:
        if fact["geography_level"] != "mesa":
            assert fact["mesa_id"] is None
            assert fact["geography_id"] == fact["source_geography_id"]


def test_stage_a_computes_canonical_paths_by_walking_parents(staged: tuple[Path, Path]) -> None:
    _, artifacts = staged
    rows = {row["id"]: row for row in _table(artifacts / GEOGRAPHY_ARTIFACT)}
    assert rows["CO"]["canonical_path"] == "CO"
    for row in rows.values():
        if row["parent_id"] is not None:
            expected = f"{rows[row['parent_id']]['canonical_path']}/{row['id']}"
            assert row["canonical_path"] == expected


def test_stage_a_rejects_a_mesa_whose_id_is_not_place_code_plus_number(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["mesas"][0]["display_number"] = "999999"
    path = tmp_path / "api-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ReleaseLoadError, match="polling-place code plus"):
        snapshot_to_parquet(path, tmp_path / "artifacts")


def test_stage_a_rejects_a_mesa_fact_filed_against_a_foreign_place(tmp_path: Path) -> None:
    snapshot = _snapshot()
    mesa_fact = next(row for row in snapshot["results"] if row["geography_level"] == "mesa")
    other = next(
        row["id"]
        for row in snapshot["geographies"]
        if row["level"] == "polling_place" and row["id"] != mesa_fact["geography_id"]
    )
    mesa_fact["geography_id"] = other
    path = tmp_path / "api-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ReleaseLoadError, match="foreign polling place"):
        snapshot_to_parquet(path, tmp_path / "artifacts")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"api_snapshot": {"geographies": []}}, "must not embed an api_snapshot"),
        ({"release_class": "context_only"}, "release_class 'standard'"),
        ({"synthetic": True}, "synthetic releases cannot be loaded"),
        ({"election_slug": "presidencia-2022-round-2"}, "election_slug must be"),
        ({"status": "draft"}, "candidate/published"),
    ],
)
def test_stage_b_rejects_an_unloadable_manifest(
    tmp_path: Path, mutation: dict[str, Any], message: str
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({**_manifest(), **mutation}), encoding="utf-8")
    engine = create_engine("postgresql+psycopg://invalid/invalid")
    with pytest.raises(ReleaseLoadError, match=message):
        load_standard_2026_release(engine, manifest, tmp_path)


def test_stage_b_rejects_the_historical_r1_r2_id_scheme(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    payload = {**_manifest(), "release_id": "r2:historical", "data_version": "r2:historical"}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    engine = create_engine("postgresql+psycopg://invalid/invalid")
    with pytest.raises(ReleaseLoadError, match="r1:/r2: id scheme"):
        load_standard_2026_release(engine, manifest, tmp_path)


def test_stage_b_requires_postgresql(tmp_path: Path, staged: tuple[Path, Path]) -> None:
    manifest, artifacts = staged
    with pytest.raises(ReleaseLoadError, match="requires PostgreSQL"):
        load_standard_2026_release(create_engine("sqlite://"), manifest, artifacts)


@pytest.mark.skipif(not REAL_ARTIFACTS.is_file(), reason="real 2026 artifacts not staged")
def test_real_release_artifacts_produce_the_expected_row_counts() -> None:
    """The counts the loaded database must contain, read from the real artifacts."""
    load_manifest = json.loads(REAL_ARTIFACTS.read_text())
    counts = {entry["filename"]: entry["record_count"] for entry in load_manifest["artifacts"]}
    assert counts == {
        GEOGRAPHY_ARTIFACT: 18_675,
        MESA_ARTIFACT: 122_020,
        FACT_ARTIFACT: 136_459,
        CATEGORY_ARTIFACT: 272_918,
    }
    levels: dict[str, int] = {}
    for row in _table(REAL_ARTIFACTS.parent / GEOGRAPHY_ARTIFACT):
        levels[row["level"]] = levels.get(row["level"], 0) + 1
    assert levels == {
        "national": 1,
        "department": 34,
        "municipality": 1_189,
        "zone": 3_013,
        "polling_place": 14_438,
    }
    aggregates = levels["zone"] + levels["municipality"] + levels["department"]
    assert aggregates == 4_236
    assert counts[GEOGRAPHY_ARTIFACT] + counts[MESA_ARTIFACT] == 140_695
    assert counts[FACT_ARTIFACT] + aggregates == 140_695
    assert counts[CATEGORY_ARTIFACT] + aggregates * 2 == 281_390


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if not (BIN / "initdb").exists():
        pytest.skip("PostgreSQL binaries unavailable")
    from alembic import command
    from alembic.config import Config

    data = tmp_path_factory.mktemp("standard-loader-pg")
    port = _port()
    subprocess.run(
        [str(BIN / "initdb"), "-D", str(data), "-A", "trust", "-U", "clusteradmin"],
        check=True,
        capture_output=True,
        timeout=60,
    )
    subprocess.run(
        [str(BIN / "pg_ctl"), "-D", str(data), "-o", f"-p {port} -h 127.0.0.1", "-w", "start"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )
    try:
        admin = create_engine(f"postgresql+psycopg://clusteradmin@127.0.0.1:{port}/postgres")
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE DATABASE elecciones_standard"))
        url = f"postgresql+psycopg://clusteradmin@127.0.0.1:{port}/elecciones_standard"
        config = Config(str(REPOSITORY / "apps/api/alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        yield url
    finally:
        subprocess.run(
            [str(BIN / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
            check=True,
            capture_output=True,
        )


def _counts(url: str, release_id: str) -> dict[str, int]:
    engine = create_engine(url)
    tables = (
        "release_geographies",
        "release_mesas",
        "release_result_facts",
        "release_category_facts",
        "release_sources",
        "release_summaries",
        "release_exposures",
    )
    with engine.begin() as connection:
        return {
            table: int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE release_id=:r"),  # noqa: S608
                    {"r": release_id},
                ).scalar_one()
            )
            for table in tables
        }


def test_stage_b_loads_derives_and_reconciles(
    postgres_url: str, staged: tuple[Path, Path]
) -> None:
    manifest, artifacts = staged
    engine = create_engine(postgres_url)
    assert load_standard_2026_release(engine, manifest, artifacts) == "loaded"
    counts = _counts(postgres_url, "candidate-2026-r2-fixture")
    assert counts == {
        "release_geographies": FIXTURE_GEOGRAPHIES + FIXTURE_MESAS,
        "release_mesas": FIXTURE_MESAS,
        "release_result_facts": FIXTURE_FACTS + FIXTURE_AGGREGATES,
        "release_category_facts": (FIXTURE_FACTS + FIXTURE_AGGREGATES) * len(CANDIDATES),
        "release_sources": 4,
        "release_summaries": 1,
        "release_exposures": 1,
    }
    with engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT access_scope FROM release_exposures WHERE release_id=:r"),
                {"r": "candidate-2026-r2-fixture"},
            ).scalar_one()
            == "internal"
        )
        # Every derived aggregate is attributed to the rollup source, and none
        # of them fabricates a registered-electors denominator.
        derived = connection.execute(
            text(
                "SELECT geography_level,COUNT(*),"
                " COUNT(*) FILTER (WHERE metrics->'registered_electors'->>'status'"
                "  <> 'unavailable') "
                "FROM release_result_facts WHERE release_id=:r AND source_id=:s "
                "GROUP BY geography_level ORDER BY geography_level"
            ),
            {"r": "candidate-2026-r2-fixture", "s": SOURCE_ROLLUP},
        ).all()
        assert [tuple(row) for row in derived] == [
            ("department", 2, 0),
            ("municipality", 4, 0),
            ("zone", 4, 0),
        ]
        # A mesa lookup filters on geography_id = mesa_id; that must find the fact.
        mesa_id = connection.execute(
            text("SELECT id FROM release_mesas WHERE release_id=:r ORDER BY id LIMIT 1"),
            {"r": "candidate-2026-r2-fixture"},
        ).scalar_one()
        assert (
            connection.execute(
                text(
                    "SELECT COUNT(*) FROM release_result_facts "
                    "WHERE release_id=:r AND geography_id=:g AND geography_level='mesa'"
                ),
                {"r": "candidate-2026-r2-fixture", "g": mesa_id},
            ).scalar_one()
            == 1
        )
        # The derived department totals reproduce the published national fact.
        national, departments = (
            connection.execute(
                text(
                    "SELECT (metrics->'voters'->>'value')::bigint "
                    "FROM release_result_facts "
                    "WHERE release_id=:r AND geography_level='national'"
                ),
                {"r": "candidate-2026-r2-fixture"},
            ).scalar_one(),
            connection.execute(
                text(
                    "SELECT SUM((metrics->'voters'->>'value')::bigint) "
                    "FROM release_result_facts "
                    "WHERE release_id=:r AND geography_level='department'"
                ),
                {"r": "candidate-2026-r2-fixture"},
            ).scalar_one(),
        )
        assert national == departments
        # The blocked reconciliation is served as recorded, not recomputed.
        assert connection.execute(
            text("SELECT reconciliation FROM release_summaries WHERE release_id=:r"),
            {"r": "candidate-2026-r2-fixture"},
        ).scalar_one() == {"status": "blocked", "checked_facts": 24, "exceptions": 3}


def test_stage_b_is_idempotent_on_an_identical_manifest(
    postgres_url: str, staged: tuple[Path, Path]
) -> None:
    manifest, artifacts = staged
    engine = create_engine(postgres_url)
    assert load_standard_2026_release(engine, manifest, artifacts) == "noop"


def test_stage_b_aborts_when_a_place_total_disagrees_with_its_mesas(
    postgres_url: str, tmp_path: Path
) -> None:
    snapshot = _snapshot()
    place_fact = next(
        row for row in snapshot["results"] if row["geography_level"] == "polling_place"
    )
    place_fact["voters"]["value"] += 1
    path = tmp_path / "api-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({**_manifest(), "release_id": "broken", "data_version": "broken"}),
        encoding="utf-8",
    )
    snapshot_to_parquet(path, tmp_path / "artifacts")
    engine = create_engine(postgres_url)
    with pytest.raises(ReleaseLoadError, match="does not equal the sum of its mesas"):
        load_standard_2026_release(engine, manifest, tmp_path / "artifacts")
    # The whole transaction rolled back: nothing from the broken release remains.
    assert _counts(postgres_url, "broken") == dict.fromkeys(
        (
            "release_geographies",
            "release_mesas",
            "release_result_facts",
            "release_category_facts",
            "release_sources",
            "release_summaries",
            "release_exposures",
        ),
        0,
    )
