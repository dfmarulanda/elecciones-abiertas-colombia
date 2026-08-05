"""End-to-end public normalized-read tests against a disposable PostgreSQL cluster."""
# ruff: noqa: E501, S603, S106

import csv
import io
import json
import socket
import subprocess
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from elecciones_api.config import Settings
from elecciones_api.main import create_app
from elecciones_api.repository import PostgresReadRepository
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

BIN = Path("/opt/homebrew/bin")
pytestmark = pytest.mark.skipif(
    not (BIN / "initdb").exists(), reason="PostgreSQL binaries unavailable"
)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    data = tmp_path_factory.mktemp("normalized-pg")
    port = _port()
    print("pg phase: initdb", flush=True)
    subprocess.run(
        [str(BIN / "initdb"), "-D", str(data), "-A", "trust", "-U", "clusteradmin"],
        check=True,
        capture_output=True,
        timeout=20,
    )
    print("pg phase: start", flush=True)
    subprocess.run(
        [str(BIN / "pg_ctl"), "-D", str(data), "-o", f"-p {port} -h 127.0.0.1", "-w", "start"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )
    try:
        admin = f"postgresql+psycopg://clusteradmin@127.0.0.1:{port}/postgres"
        engine = create_engine(admin)
        print("pg phase: create role/database", flush=True)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("CREATE ROLE elecciones_app LOGIN NOSUPERUSER"))
            conn.execute(text("CREATE DATABASE elecciones_it OWNER elecciones_app"))
        url = f"postgresql+psycopg://elecciones_app@127.0.0.1:{port}/elecciones_it"
        cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", url)
        print("pg phase: migrate", flush=True)
        command.upgrade(cfg, "head")
        print("pg phase: migrated", flush=True)
        yield url
    finally:
        subprocess.run(
            [str(BIN / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
            check=True,
            capture_output=True,
        )


def _seed(url: str) -> None:
    engine = create_engine(url)
    metrics = json.dumps(
        {
            metric: {
                "value": 0 if metric == "unmarked_votes" else None,
                "status": "observed" if metric == "unmarked_votes" else "unavailable",
            }
            for metric in (
                "registered_electors",
                "voters",
                "valid_votes",
                "blank_votes",
                "null_votes",
                "unmarked_votes",
            )
        }
    )
    now = datetime.now(UTC)
    with engine.begin() as c:
        for release, status in (
            ("current", "published"),
            ("baseline", "published"),
            ("ordinary", "published"),
            ("unapproved", "published"),
            ("candidate", "candidate"),
        ):
            c.execute(
                text(
                    "INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES(:r,:s,false,:now,'{}')"
                ),
                {"r": release, "s": status, "now": now},
            )
            c.execute(
                text(
                    "INSERT INTO release_elections VALUES(:r,'election', 'Elección', 'Election',1,:d)"
                ),
                {"r": release, "d": date(2026, 1, 1)},
            )
            c.execute(
                text(
                    "INSERT INTO release_geographies VALUES(:r,'election','CO','national','CO','Colombia',NULL,'CO')"
                ),
                {"r": release},
            )
            c.execute(
                text(
                    "INSERT INTO release_geographies VALUES(:r,'election','DEP','department','11','Departamento','CO','CO/DEP')"
                ),
                {"r": release},
            )
            c.execute(
                text(
                    "INSERT INTO release_geographies VALUES(:r,'election','MUN','municipality','001','Municipio','DEP','CO/DEP/MUN')"
                ),
                {"r": release},
            )
            c.execute(
                text(
                    "INSERT INTO release_geographies VALUES(:r,'election','PLACE','polling_place','01','Puesto','MUN','CO/DEP/MUN/PLACE')"
                ),
                {"r": release},
            )
            c.execute(
                text(
                    "INSERT INTO release_geographies VALUES(:r,'election','MESA','mesa','1','Mesa','PLACE','CO/DEP/MUN/PLACE/MESA')"
                ),
                {"r": release},
            )
            c.execute(
                text(
                    "INSERT INTO release_mesas VALUES(:r,'election','MESA','1','PLACE','MUN','DEP')"
                ),
                {"r": release},
            )
        for release, source, kind, legal in (
            ("current", "src-current", "scrutiny", "official_scrutiny"),
            ("current", "src-pre", "pre_count", "preliminary"),
            ("baseline", "src-base", "contextual_baseline", "context_only"),
            ("ordinary", "src-ordinary", "scrutiny", "official_scrutiny"),
            ("unapproved", "src-unapproved", "scrutiny", "official_scrutiny"),
            ("candidate", "src-secret", "scrutiny", "official_scrutiny"),
        ):
            c.execute(
                text(
                    "INSERT INTO release_sources VALUES(:r,'election',:id,:t,:l,'https://official.example/source',:now,:h,'p1','t1')"
                ),
                {"r": release, "id": source, "t": kind, "l": legal, "now": now, "h": "b" * 64},
            )
            fact_id = f"fact-{release}-{source}"
            c.execute(
                text(
                    "INSERT INTO release_result_facts VALUES(:r,'election',:f,'MESA','mesa','MESA',:s,CAST(:m AS json))"
                ),
                {"r": release, "f": fact_id, "s": source, "m": metrics},
            )
            c.execute(
                text(
                    "INSERT INTO release_category_facts VALUES(:r,'election',:f,'ballot:blank','blank','Blank','ballot',:v,'observed')"
                ),
                {"r": release, "f": fact_id, "v": 7 if source == "src-current" else 5},
            )
        # Exposure is the immutable-read-model gate and must be installed only
        # after every row for the release/election has been validated and written.
        for release in ("current", "baseline", "ordinary", "unapproved"):
            c.execute(
                text("INSERT INTO release_exposures VALUES(:r,'election','internal',NULL,:h)"),
                {"r": release, "h": "a" * 64},
            )
            c.execute(
                text(
                    "UPDATE release_exposures SET access_scope='public',approved_at=:now WHERE release_id=:r AND election_slug='election'"
                ),
                {"r": release, "now": now},
            )
        # current->baseline: approved geography and semantic mapping produces descriptive context.
        c.execute(
            text(
                "INSERT INTO comparison_crosswalks VALUES('current','election','baseline','election','MESA','MESA','mesa','ctx-v1','g1',:now)"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO semantic_category_crosswalks(current_release_id,current_election_slug,baseline_release_id,baseline_election_slug,comparison_key,current_category_key,baseline_category_key,category_kind,version,approved_at,current_source_id,baseline_source_id) VALUES('current','election','baseline','election','ctx-v1','ballot:blank','ballot:blank','ballot','s1',:now,'src-current','src-base')"
            ),
            {"now": now},
        )
        # Ordinary non-context comparison is independently approved.
        c.execute(
            text(
                "INSERT INTO comparison_crosswalks VALUES('current','election','ordinary','election','MESA','MESA','mesa','ordinary-v1','g1',:now)"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO semantic_category_crosswalks(current_release_id,current_election_slug,baseline_release_id,baseline_election_slug,comparison_key,current_category_key,baseline_category_key,category_kind,version,approved_at,current_source_id,baseline_source_id) VALUES('current','election','ordinary','election','ordinary-v1','ballot:blank','ballot:blank','ballot','s1',:now,'src-current','src-ordinary')"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO comparison_crosswalks VALUES('current','election','unapproved','election','MESA','MESA','mesa','unapproved-v1','g1',:now)"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO semantic_category_crosswalks(current_release_id,current_election_slug,baseline_release_id,baseline_election_slug,comparison_key,current_category_key,baseline_category_key,category_kind,version,approved_at,current_source_id,baseline_source_id) VALUES('current','election','unapproved','election','unapproved-v1','ballot:blank','ballot:blank','ballot','s1',NULL,NULL,NULL)"
            )
        )


def test_normalized_public_read_path(postgres_url: str) -> None:
    print("pg phase: seed", flush=True)
    _seed(postgres_url)
    repository = PostgresReadRepository(postgres_url, "current")
    app = create_app(
        settings=Settings(
            database_url=postgres_url, active_release="current", cursor_secret="integration-secret"
        ),
        repository=repository,
    )
    print("pg phase: app", flush=True)
    with TestClient(app) as api:
        print("pg phase: HTTP public elections", flush=True)
        releases = api.get("/api/v1/release-elections").json()
        assert {item["release_id"] for item in releases} == {
            "current",
            "baseline",
            "ordinary",
            "unapproved",
        }
        # Legacy routes without an election slug must not reveal an internal
        # candidate's snapshot materialization state.
        assert api.get("/api/v1/geographies/CO?data_version=candidate").status_code == 404
        base = "/api/v1/releases/current/elections/election"
        print("pg phase: HTTP results", flush=True)
        first = api.get(
            f"{base}/results?limit=1&geography_path=CO&geography_level=mesa&category_key=ballot:blank&status=observed"
        )
        assert first.status_code == 200 and first.json()["items"][0]["unmarked_votes"] == {
            "value": 0,
            "status": "observed",
        }
        cursor = first.json()["page"]["next_cursor"]
        assert cursor
        second = api.get(
            f"{base}/results?limit=1&geography_path=CO&geography_level=mesa&category_key=ballot:blank&status=observed&cursor={cursor}"
        )
        assert (
            second.status_code == 200
            and second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
        )
        assert (
            api.get(f"{base}/results?limit=1&geography_path=CO/DEP&cursor={cursor}").status_code
            == 400
        )
        assert (
            "LIMIT" in repository._result_statement("current", "election", {}, None, 2)[0]
            and "OFFSET" not in repository._result_statement("current", "election", {}, None, 2)[0]
        )
        assert api.get(f"{base}/results?cursor={cursor}tampered").status_code == 400
        csv_response = api.get(f"{base}/results?format=csv&source_id=src-current")
        csv_ids = [row["id"] for row in csv.DictReader(io.StringIO(csv_response.text))]
        json_ids = [
            item["id"]
            for item in api.get(f"{base}/results?limit=200&source_id=src-current").json()["items"]
        ]
        assert csv_ids == json_ids == ["fact-current-src-current"]
        assert (
            api.get(
                f"{base}/results?format=csv&source_id=src-current",
                headers={"If-None-Match": csv_response.headers["etag"]},
            ).status_code
            == 304
        )
        categories = api.get(f"{base}/result-facts/fact-current-src-current/categories").json()
        assert categories["items"][0]["provenance"]["source_type"] == "scrutiny"
        assert [
            item["id"] for item in api.get(f"{base}/geographies/MESA/path").json()["items"]
        ] == ["CO", "DEP", "MUN", "PLACE", "MESA"]
        children = api.get(f"{base}/geographies/MUN/children?level=polling_place").json()
        assert children["items"] == [
            {
                "id": "PLACE",
                "level": "polling_place",
                "code": "01",
                "name": "Puesto",
                "parent_id": "MUN",
                "canonical_path": "CO/DEP/MUN/PLACE",
                "has_published_facts": False,
            }
        ]
        mesa = api.get(f"{base}/mesas/MESA?source_id=src-current").json()
        assert (
            mesa["municipality_id"] == "MUN"
            and [item["id"] for item in mesa["geography_path"]][-1] == "MESA"
        )
        assert [item["id"] for item in mesa["results"]] == ["fact-current-src-current"]
        descriptive = api.get(
            f"{base}/historical-comparison?baseline_release_id=baseline&baseline_election_slug=election&geography_id=MESA&grain=mesa"
        ).json()
        assert (
            descriptive["comparison_status"] == "descriptive_context_only"
            and not descriptive["eligible_for_integrity_analysis"]
        )
        assert (
            descriptive["items"][0]["baseline_value"] == 5
            and descriptive["items"][0]["baseline_provenance"]["legal_status"] == "context_only"
        )
        ordinary = api.get(
            f"{base}/historical-comparison?baseline_release_id=ordinary&baseline_election_slug=election&geography_id=MESA&grain=mesa"
        ).json()
        assert (
            ordinary["comparison_status"] == "comparable"
            and ordinary["eligible_for_integrity_analysis"]
        )
        assert (
            len(ordinary["items"]) == 1
            and ordinary["items"][0]["current_provenance"]["source_type"] == "scrutiny"
        )
        unapproved = api.get(
            f"{base}/historical-comparison?baseline_release_id=unapproved&baseline_election_slug=election&geography_id=MESA&grain=mesa"
        ).json()
        assert unapproved["reason"] == "semantic_crosswalk_unapproved"
        missing = api.get(
            f"{base}/historical-comparison?baseline_release_id=ordinary&baseline_election_slug=election&geography_id=CO&grain=national"
        ).json()
        assert missing["reason"] == "missing_geography_crosswalk"
        assert api.get("/api/v1/releases/candidate/elections/election/results").status_code == 404


def test_exposure_serializes_with_a_concurrent_writer(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('race','candidate',false,:now,'{}')"
            ),
            {"now": now},
        )
        c.execute(
            text("INSERT INTO release_elections VALUES('race','election','Carrera','Race',1,:day)"),
            {"day": date(2026, 1, 1)},
        )

    def wait_until_blocked(application_name: str) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with engine.connect() as probe:
                blocked = probe.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock')"
                    ),
                    {"name": application_name},
                ).scalar_one()
            if blocked:
                return
            time.sleep(0.01)
        pytest.fail(f"{application_name} did not wait on the release-election lock")

    def write_invalid_mesa() -> str:
        with engine.begin() as c:
            c.execute(text("SET LOCAL application_name='release_gate_writer'"))
            c.execute(text("SET LOCAL lock_timeout='10s'"))
            c.execute(
                text(
                    "INSERT INTO release_mesas VALUES('race','election','missing-mesa','1','missing-place','missing-mun','missing-dep')"
                )
            )
        return "committed"

    def expose() -> str:
        try:
            with engine.begin() as c:
                c.execute(text("SET LOCAL application_name='release_gate_exposure'"))
                c.execute(text("SET LOCAL lock_timeout='10s'"))
                c.execute(
                    text(
                        "INSERT INTO release_exposures VALUES('race','election','internal',NULL,:hash)"
                    ),
                    {"hash": "c" * 64},
                )
        except DBAPIError as exc:
            return str(exc.orig)
        return "committed"

    blocker = engine.connect()
    blocker_transaction = blocker.begin()
    blocker.execute(
        text(
            "SELECT 1 FROM release_elections WHERE release_id='race' AND election_slug='election' FOR NO KEY UPDATE"
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(write_invalid_mesa)
        try:
            wait_until_blocked("release_gate_writer")
            exposure = pool.submit(expose)
            wait_until_blocked("release_gate_exposure")
        finally:
            blocker_transaction.commit()
            blocker.close()
        assert writer.result(timeout=10) == "committed"
        assert "invalid mesa geography lineage" in exposure.result(timeout=10)

    with engine.begin() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM release_exposures WHERE release_id='race'")
            ).scalar_one()
            == 0
        )
        assert (
            c.execute(
                text("SELECT count(*) FROM release_mesas WHERE release_id='race'")
            ).scalar_one()
            == 1
        )
        c.execute(text("DELETE FROM release_mesas WHERE release_id='race'"))
        c.execute(text("DELETE FROM release_elections WHERE release_id='race'"))
        c.execute(text("DELETE FROM releases WHERE id='race'"))


def test_exposure_freezes_provenance_and_release_metadata(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,methodology_version,manifest) VALUES('frozen','candidate',false,:now,'m1','{}')"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO release_elections VALUES('frozen','election','Congelada','Frozen',1,:day)"
            ),
            {"day": date(2026, 1, 1)},
        )
        c.execute(
            text(
                "INSERT INTO release_sources VALUES('frozen','election','source','scrutiny','official_scrutiny','https://official.example/source',:now,:hash,'p1','t1')"
            ),
            {"now": now, "hash": "d" * 64},
        )
        c.execute(
            text("INSERT INTO release_exposures VALUES('frozen','election','internal',NULL,:hash)"),
            {"hash": "e" * 64},
        )

    for statement in (
        "UPDATE release_sources SET parser_version='p2' WHERE release_id='frozen'",
        "UPDATE release_elections SET name_en='Changed' WHERE release_id='frozen'",
        "UPDATE releases SET methodology_version='m2' WHERE id='frozen'",
    ):
        with pytest.raises(DBAPIError, match="immutable"), engine.begin() as c:
            c.execute(text(statement))

    with engine.begin() as c:
        c.execute(text("UPDATE releases SET status='published' WHERE id='frozen'"))
        assert (
            c.execute(text("SELECT status FROM releases WHERE id='frozen'")).scalar_one()
            == "published"
        )
        c.execute(text("UPDATE releases SET status='withdrawn' WHERE id='frozen'"))
        assert (
            c.execute(text("SELECT status FROM releases WHERE id='frozen'")).scalar_one()
            == "withdrawn"
        )
        c.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('withdraw-candidate','candidate',false,:now,'{}')"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO release_elections VALUES('withdraw-candidate','election','Retirada','Withdrawn',1,:day)"
            ),
            {"day": date(2026, 1, 1)},
        )
        c.execute(
            text(
                "INSERT INTO release_exposures VALUES('withdraw-candidate','election','internal',NULL,:hash)"
            ),
            {"hash": "f" * 64},
        )
        c.execute(text("UPDATE releases SET status='withdrawn' WHERE id='withdraw-candidate'"))


def test_exposure_gate_rejects_cross_municipality_lineage(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('lineage','candidate',false,:now,'{}')"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO release_elections VALUES('lineage','election','Linaje','Lineage',1,:day)"
            ),
            {"day": date(2026, 1, 1)},
        )
        c.execute(
            text(
                "INSERT INTO release_geographies VALUES "
                "('lineage','election','CO','national','CO','Colombia',NULL,'CO'), "
                "('lineage','election','DEP','department','11','Departamento','CO','CO/DEP'), "
                "('lineage','election','MUN-A','municipality','001','Municipio A','DEP','CO/DEP/MUN-A'), "
                "('lineage','election','MUN-B','municipality','002','Municipio B','DEP','CO/DEP/MUN-B'), "
                "('lineage','election','PLACE','polling_place','01','Puesto','MUN-A','CO/DEP/MUN-A/PLACE'), "
                "('lineage','election','MESA','mesa','1','Mesa','PLACE','CO/DEP/MUN-A/PLACE/MESA')"
            )
        )
        c.execute(
            text(
                "INSERT INTO release_mesas VALUES('lineage','election','MESA','1','PLACE','MUN-B','DEP')"
            )
        )

    with pytest.raises(DBAPIError, match="invalid mesa geography lineage"), engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO release_exposures VALUES('lineage','election','internal',NULL,:hash)"
            ),
            {"hash": "1" * 64},
        )

    with engine.begin() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM release_exposures WHERE release_id='lineage'")
            ).scalar_one()
            == 0
        )
        c.execute(text("DELETE FROM release_mesas WHERE release_id='lineage'"))
        c.execute(text("DELETE FROM release_geographies WHERE release_id='lineage'"))
        c.execute(text("DELETE FROM release_elections WHERE release_id='lineage'"))
        c.execute(text("DELETE FROM releases WHERE id='lineage'"))


def test_public_exposure_must_use_guarded_transition(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('direct-public','candidate',false,:now,'{}')"
            ),
            {"now": now},
        )
        c.execute(
            text(
                "INSERT INTO release_elections VALUES('direct-public','election','Directa','Direct',1,:day)"
            ),
            {"day": date(2026, 1, 1)},
        )
    with pytest.raises(DBAPIError, match="internal gate"), engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO release_exposures VALUES('direct-public','election','public',:now,:hash)"
            ),
            {"now": now, "hash": "2" * 64},
        )


def _seed_compact_context(url: str) -> None:
    engine = create_engine(url)
    now = datetime.now(UTC)
    manifest = json.dumps(
        {
            "release_class": "context_only",
            "statistical_validation_passed": False,
            "datasets": [
                {
                    "id": "context-parquet",
                    "title": {"es": "Contexto", "en": "Context"},
                    "format": "parquet",
                    "url": "https://official.example/context.parquet",
                    "schema_url": "https://official.example/context.schema.json",
                    "record_count": 6,
                    "byte_size": 123,
                    "content_hash": "c" * 64,
                    "filters": {"legal_status": "context_only"},
                }
            ],
        }
    )
    with engine.begin() as c:
        c.execute(text("INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('compact','published',false,:now,CAST(:manifest AS jsonb))"), {"now": now, "manifest": manifest})
        c.execute(text("INSERT INTO release_elections VALUES('compact','historical','Histórica','Historical',1,:day)"), {"day": date(2022, 5, 29)})
        c.execute(text("INSERT INTO release_sources VALUES('compact','historical','historical-source','contextual_baseline','context_only','https://official.example/source',:now,:hash,'p1','t1')"), {"now": now, "hash": "d" * 64})
        scope = int(c.execute(text("INSERT INTO context_release_scopes(release_id,election_slug) VALUES('compact','historical') RETURNING id")).scalar_one())
        c.execute(text("INSERT INTO context_sources VALUES(:scope,1,'historical-source')"), {"scope": scope})
        geographies = [
            (1, "r:co", 0, "CO", "Colombia", None, 1, 12),
            (2, "r:dep:01", 1, "01", "Departamento", 1, 2, 11),
            (3, "r:mun:01:001", 2, "001", "Municipio", 2, 3, 10),
            (4, "r:zone:01:001:01", 3, "01", "Zona", 3, 4, 9),
            (5, "r:place:01:001:01:01", 4, "01", "Puesto", 4, 5, 8),
            (6, "r:mesa:01:001:01:01:001", 5, "001", "Mesa", 5, 6, 7),
        ]
        for item in geographies:
            c.execute(text("INSERT INTO context_geographies(scope_id,id,external_id,level,code,name,parent_id,tree_left,tree_right) VALUES(:scope,:id,:external,:level,:code,:name,:parent,:left,:right)"), {"scope": scope, "id": item[0], "external": item[1], "level": item[2], "code": item[3], "name": item[4], "parent": item[5], "left": item[6], "right": item[7]})
        # registered_electors is observed zero; voters unknown; remaining metrics unavailable.
        mask = (1 << 2) + sum(2 << (offset * 2) for offset in range(2, 6))
        for geography_id in range(1, 7):
            c.execute(text("INSERT INTO context_result_facts(scope_id,geography_id,source_ordinal,metrics_status,registered_electors,voters,valid_votes,blank_votes,null_votes,unmarked_votes) VALUES(:scope,:geo,1,:mask,0,NULL,NULL,NULL,NULL,NULL)"), {"scope": scope, "geo": geography_id, "mask": mask})
        c.execute(text("INSERT INTO context_categories VALUES(:scope,1,'candidate:a','A','Candidata A','published_mmv_category')"), {"scope": scope})
        c.execute(text("INSERT INTO context_categories VALUES(:scope,2,'ballot:unknown','UNK','Desconocido','published_mmv_category')"), {"scope": scope})
        c.execute(text("INSERT INTO context_category_facts VALUES(:scope,1,1,1,0,0)"), {"scope": scope})
        c.execute(text("INSERT INTO context_category_facts VALUES(:scope,1,1,2,NULL,1)"), {"scope": scope})
        c.execute(
            text(
                "UPDATE context_release_scopes SET geography_count=6,result_fact_count=6,"
                "category_fact_count=2,semantic_key_hash=:semantic,content_row_hash=:content "
                "WHERE id=:scope"
            ),
            {"scope": scope, "semantic": "a" * 64, "content": "b" * 64},
        )
        c.execute(text("INSERT INTO release_exposures VALUES('compact','historical','internal',NULL,:hash)"), {"hash": "e" * 64})
        c.execute(text("UPDATE release_exposures SET access_scope='public',approved_at=:now WHERE release_id='compact' AND election_slug='historical'"), {"now": now})


def test_compact_context_public_api(postgres_url: str) -> None:
    _seed_compact_context(postgres_url)
    app = create_app(settings=Settings(database_url=postgres_url, active_release="compact", cursor_secret="context-secret", artifact_hosts="official.example"), repository=PostgresReadRepository(postgres_url, "compact"))
    base = "/api/v1/releases/compact/elections/historical"
    with TestClient(app) as api:
        summary = api.get(f"{base}/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["completion"]["status"] == "unknown"
        assert payload["coverage"]["status"] == "unknown"
        assert payload["registered_electors"] == {"value": 0, "status": "observed"}
        assert payload["voters"] == {"value": None, "status": "unknown"}
        dataset = api.get(f"{base}/datasets").json()[0]
        assert dataset["id"] == "context-parquet"
        assert dataset["url"].startswith("/api/v1/")
        redirect = api.get(dataset["url"], follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "https://official.example/context.parquet"
        assert redirect.headers["etag"] == f'"{dataset["content_hash"]}"'
        first = api.get(f"{base}/results?limit=2")
        assert first.status_code == 200 and first.json()["page"]["has_more"]
        second = api.get(f"{base}/results?limit=2&cursor={first.json()['page']['next_cursor']}")
        assert second.status_code == 200 and second.json()["items"][0]["geography_level"] == "municipality"
        mesa = "r:mesa:01:001:01:01:001"
        mesa_payload = api.get(f"{base}/mesas/{mesa}").json()
        assert mesa_payload["municipality_id"] == "r:mun:01:001"
        assert mesa_payload["geography_path"][-1]["parent_id"] == "r:place:01:001:01:01"
        path = "r:co/r:dep:01/r:mun:01:001"
        geography = api.get(f"{base}/geographies/r:mun:01:001").json()["item"]
        assert geography["canonical_path"] == path
        descendants = api.get(f"{base}/results?geography_path={path}").json()["items"]
        assert {row["geography_id"] for row in descendants} >= {"r:mun:01:001", mesa}
        fact_id = "r:co:historical-source"
        categories = api.get(f"{base}/result-facts/{fact_id}/categories").json()["items"]
        candidate = next(item for item in categories if item["category_key"] == "candidate:a")
        assert candidate["votes"] == 0 and candidate["provenance"]["content_hash"] == "d" * 64
        assert api.get(f"{base}/result-facts/not-a-fact/categories").status_code == 404
        assert api.get(f"{base}/analysis/summary").status_code == 404
        comparison = api.get(f"{base}/historical-comparison?baseline_release_id=compact&baseline_election_slug=historical&geography_id=r:co&grain=national").json()
        assert comparison["comparison_status"] == "descriptive_context_only"
        comparison_text = json.dumps(comparison).lower()
        assert "audit_priority_score" not in comparison_text
        assert "affected_votes" not in comparison_text
        assert "fraud" not in comparison_text
    engine = create_engine(postgres_url)
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as c:
        c.execute(text("UPDATE context_result_facts SET registered_electors=1 WHERE scope_id=(SELECT id FROM context_release_scopes WHERE release_id='compact') AND geography_id=1"))
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(text("INSERT INTO releases(id,status,synthetic,created_at,manifest) VALUES('bad-compact','published',false,:now,'{}')"), {"now": now})
        c.execute(text("INSERT INTO release_elections VALUES('bad-compact','historical','Mala','Bad',1,:day)"), {"day": date(2022, 1, 1)})
        c.execute(text("INSERT INTO context_release_scopes(release_id,election_slug) VALUES('bad-compact','historical')"))
    with pytest.raises(DBAPIError, match="context_only"), engine.begin() as c:
        c.execute(text("INSERT INTO release_exposures VALUES('bad-compact','historical','internal',NULL,:hash)"), {"hash": "f" * 64})
