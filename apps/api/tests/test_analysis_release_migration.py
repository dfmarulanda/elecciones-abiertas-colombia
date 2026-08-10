"""Persistence contract for immutable statistical-analysis release overlays."""
# ruff: noqa: E501, S603, S106

import json
import socket
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from elecciones_api.repository import PostgresReadRepository
from elecciones_pipeline.analytics.analysis_release import (
    CanonicalInputRegistry,
    build_analysis_bundle,
    write_analysis_bundle,
)
from elecciones_pipeline.releases.analysis_postgres_loader import (
    approve_preliminary_analysis_release,
    load_analysis_release,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

BIN = Path("/opt/homebrew/bin")
MIGRATIONS = Path(__file__).parents[1] / "alembic.ini"
PREVIOUS_REVISION = "20260808_01"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64

pytestmark = pytest.mark.skipif(
    not (BIN / "initdb").exists(), reason="PostgreSQL binaries unavailable"
)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _upgrade(url: str, revision: str) -> None:
    config = Config(str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, revision)


def _downgrade(url: str, revision: str) -> None:
    config = Config(str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, revision)


@pytest.fixture(scope="module")
def analysis_databases(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, str]]:
    data = tmp_path_factory.mktemp("analysis-release-pg")
    port = _port()
    subprocess.run(
        [str(BIN / "initdb"), "-D", str(data), "-A", "trust", "-U", "clusteradmin"],
        check=True,
        capture_output=True,
        timeout=20,
    )
    subprocess.run(
        [str(BIN / "pg_ctl"), "-D", str(data), "-o", f"-p {port} -h 127.0.0.1", "-w", "start"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )
    try:
        admin_url = f"postgresql+psycopg://clusteradmin@127.0.0.1:{port}/postgres"
        admin = create_engine(admin_url)
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE ROLE elecciones_app LOGIN NOSUPERUSER"))
            connection.execute(text("CREATE DATABASE analysis_current OWNER elecciones_app"))
            connection.execute(text("CREATE DATABASE analysis_clean OWNER elecciones_app"))

        current = f"postgresql+psycopg://elecciones_app@127.0.0.1:{port}/analysis_current"
        clean = f"postgresql+psycopg://elecciones_app@127.0.0.1:{port}/analysis_clean"
        _upgrade(current, PREVIOUS_REVISION)
        assert "analysis_releases" not in inspect(create_engine(current)).get_table_names()
        _upgrade(current, "head")
        _upgrade(clean, "head")
        yield {"current": current, "clean": clean}
    finally:
        subprocess.run(
            [str(BIN / "pg_ctl"), "-D", str(data), "-m", "fast", "stop"],
            check=True,
            capture_output=True,
        )


def _seed_source(url: str, release_id: str, status: str, exposure: str) -> None:
    now = datetime.now(UTC)
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO releases(id,status,synthetic,created_at,manifest) "
                "VALUES(:release_id,:status,false,:now,'{}')"
            ),
            {"release_id": release_id, "status": status, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO release_elections "
                "VALUES(:release_id,'election','Elección','Election',1,:election_date)"
            ),
            {"release_id": release_id, "election_date": date(2026, 6, 21)},
        )
        connection.execute(
            text(
                "INSERT INTO release_exposures "
                "(release_id,election_slug,access_scope,approved_at,manifest_hash) "
                "VALUES(:release_id,'election','internal',NULL,:manifest_hash)"
            ),
            {"release_id": release_id, "manifest_hash": HASH_A},
        )
        if exposure == "preliminary":
            connection.execute(
                text(
                    "UPDATE release_exposures SET access_scope='preliminary',"
                    "preliminary_approved_at=:now,preliminary_caveat_es='Preliminar',"
                    "preliminary_caveat_en='Preliminary' "
                    "WHERE release_id=:release_id AND election_slug='election'"
                ),
                {"release_id": release_id, "now": now},
            )
        elif exposure == "public":
            connection.execute(
                text(
                    "UPDATE release_exposures SET access_scope='public',approved_at=:now "
                    "WHERE release_id=:release_id AND election_slug='election'"
                ),
                {"release_id": release_id, "now": now},
            )


def _insert_analysis_release(
    url: str,
    analysis_release_id: str,
    source_release_id: str,
    *,
    input_hash: str = HASH_B,
    methodology: str = "peer-distribution-v1.0.0",
    runtime_hash: str = HASH_C,
    manifest_hash: str = HASH_D,
) -> None:
    now = datetime.now(UTC)
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_releases("
                "analysis_release_id,source_release_id,source_election_slug,"
                "methodology_version,canonical_input_hash,producer_runtime_fingerprint,"
                "producer_operator_id,lifecycle_state,generated_at,created_at,manifest_hash"
                ") VALUES(:analysis_release_id,:source_release_id,'election',:methodology,"
                ":input_hash,:runtime_hash,'producer-a','validated',:now,:now,:manifest_hash)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "methodology": methodology,
                "input_hash": input_hash,
                "runtime_hash": runtime_hash,
                "manifest_hash": manifest_hash,
                "now": now,
            },
        )


def _seed_analysis_content(url: str, analysis_release_id: str, source_release_id: str) -> None:
    artifact_url = f"https://official.example/analysis/{HASH_E}.json"
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_artifact_hosts(host) VALUES('official.example') ON CONFLICT DO NOTHING"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_artifacts(analysis_release_id,source_release_id,"
                "source_election_slug,artifact_id,kind,schema_version,media_type,record_count,"
                "byte_size,byte_hash,content_hash,immutable_url,artifact_status) VALUES("
                ":analysis_release_id,:source_release_id,'election','summary','summary','1.0.0',"
                "'application/json',1,120,:byte_hash,:content_hash,:url,'available')"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "byte_hash": HASH_E,
                "content_hash": HASH_F,
                "url": artifact_url,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_anomalies(analysis_release_id,source_release_id,"
                "source_election_slug,anomaly_id,family,evidence_tier,audit_priority,"
                "evaluability,explanation_es,explanation_en,evidence,calculations,limitations,"
                "provenance_hash) VALUES(:analysis_release_id,:source_release_id,'election',"
                "'anomaly-1','arithmetic','deterministic',40,'evaluable','Explicación',"
                "'Explanation','{}','{}','[]',:provenance_hash)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "provenance_hash": HASH_F,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_anomaly_components(analysis_release_id,source_release_id,"
                "source_election_slug,anomaly_id,component_id,component_type,evidence_type,points,"
                "value,unit,payload,provenance_hash) VALUES(:analysis_release_id,:source_release_id,"
                "'election','anomaly-1','component-1','arithmetic_exception','trusted_fact',40,1,"
                "'exception','{}',:provenance_hash)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "provenance_hash": HASH_F,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_reports(analysis_release_id,source_release_id,"
                "source_election_slug,report_id,report_kind,schema_version,evaluability,"
                "status_reason,diagnostics,validation,local_sensitivity,artifact_id,"
                "provenance_hash) VALUES(:analysis_release_id,:source_release_id,'election',"
                "'peer-validation','model_diagnostics','1.0.0','evaluable',NULL,'{}','{}','{}',"
                "'summary',:provenance_hash)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "provenance_hash": HASH_F,
            },
        )


def test_verified_bundle_loader_is_transactional_internal_and_idempotent(
    analysis_databases: dict[str, str], tmp_path: Path
) -> None:
    url = analysis_databases["clean"]
    _seed_source(url, "source-load", "candidate", "preliminary")

    def metric(value: int | None, status: str = "observed") -> dict[str, object]:
        return {"value": value, "status": status}

    snapshot = {
        "release": {"release_id": "source-load"},
        "election": {"slug": "election"},
        "mesas": [
            {
                "id": "mesa-load",
                "polling_place_id": "place-load",
                "municipality_id": "municipality-load",
                "department_id": "department-load",
            }
        ],
        "results": [
            {
                "mesa_id": "mesa-load",
                "election_slug": "election",
                "registered_electors": metric(None, "unavailable"),
                "voters": metric(100),
                "valid_votes": metric(97),
                "blank_votes": metric(2),
                "null_votes": metric(1),
                "unmarked_votes": metric(2),
                "candidates": [
                    {"candidate_id": "candidate-a", "votes": metric(50)},
                    {"candidate_id": "candidate-b", "votes": metric(45)},
                ],
                "provenance": {
                    "source_type": "pre_count",
                    "legal_status": "preliminary",
                    "source_url": "https://official.example/mesa-load.json",
                    "content_hash": HASH_A,
                },
            }
        ],
        "summary": {
            "reconciliation": {"status": "passed", "exceptions": 0},
            "completion": {"reported": 1, "expected": 1},
        },
    }
    registry = CanonicalInputRegistry(
        source_release_id="source-load",
        election_slug="election",
        source_manifest_hash=HASH_A,
        detector_code_hash=HASH_B,
        configuration_hash=HASH_C,
        seed_registry_hash=HASH_D,
        runtime_fingerprint=HASH_E,
        documentary_attestations=(),
        geocode_ledger=None,
        snapshot=snapshot,
    )
    bundle = build_analysis_bundle(
        registry,
        methodology_version="analysis-release-v1.0.0",
        generated_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    target = write_analysis_bundle(bundle, tmp_path)
    engine = create_engine(url)

    installed = load_analysis_release(
        engine,
        target / "manifest.json",
        producer_operator_id="producer-load",
        artifact_base_url="https://eleccionesabiertas.co/analysis-artifacts",
    )
    replay = load_analysis_release(
        engine,
        target / "manifest.json",
        producer_operator_id="producer-load",
        artifact_base_url="https://eleccionesabiertas.co/analysis-artifacts",
    )

    assert installed.installed is True
    assert replay.installed is False
    assert replay.analysis_release_id == installed.analysis_release_id
    assert replay.manifest_hash == installed.manifest_hash
    assert replay.artifact_count == installed.artifact_count
    approved_at = datetime(2026, 8, 10, 16, 45, tzinfo=UTC)
    approval = approve_preliminary_analysis_release(
        engine,
        bundle.analysis_release_id,
        approved_by="dfmarulanda",
        approved_at=approved_at,
        approval_signature_hash=HASH_F,
        caveat_es="Investigación preliminar; no prueba fraude ni votos afectados.",
        caveat_en="Preliminary research; it does not prove fraud or affected votes.",
    )
    approval_replay = approve_preliminary_analysis_release(
        engine,
        bundle.analysis_release_id,
        approved_by="dfmarulanda",
        approved_at=approved_at,
        approval_signature_hash=HASH_F,
        caveat_es="Investigación preliminar; no prueba fraude ni votos afectados.",
        caveat_en="Preliminary research; it does not prove fraud or affected votes.",
    )

    assert approval.approved is True
    assert approval_replay.approved is False
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT lifecycle_state FROM analysis_releases "
                "WHERE analysis_release_id=:analysis_release_id"
            ),
            {"analysis_release_id": bundle.analysis_release_id},
        ).scalar_one() == "validated"
        assert (
            connection.execute(
                text(
                    "SELECT exposure_tier FROM analysis_exposures "
                    "WHERE analysis_release_id=:analysis_release_id"
                ),
                {"analysis_release_id": bundle.analysis_release_id},
            ).scalar_one()
            == "preliminary_research"
        )
        assert connection.execute(
            text(
                "SELECT count(*) FROM analysis_artifacts "
                "WHERE analysis_release_id=:analysis_release_id"
            ),
            {"analysis_release_id": bundle.analysis_release_id},
        ).scalar_one() == len(bundle.artifacts)
        reports = {
            row.report_kind: (row.diagnostics, row.validation, row.local_sensitivity)
            for row in connection.execute(
                text(
                    "SELECT report_kind,diagnostics,validation,local_sensitivity "
                    "FROM analysis_reports WHERE analysis_release_id=:analysis_release_id"
                ),
                {"analysis_release_id": bundle.analysis_release_id},
            )
        }
        assert reports["validation"][0] == {}
        assert reports["validation"][1] == json.loads(
            (target / "artifacts/validation.json").read_bytes()
        )
        assert reports["local_sensitivity"][0] == {}
        assert reports["local_sensitivity"][2] == json.loads(
            (target / "artifacts/local_sensitivity.json").read_bytes()
        )


def test_research_preview_components_cannot_contribute_public_points(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    _seed_source(url, "source-preview-points", "candidate", "preliminary")
    _insert_analysis_release(url, "analysis-preview-points", "source-preview-points")
    _seed_analysis_content(url, "analysis-preview-points", "source-preview-points")

    with (
        pytest.raises(DBAPIError, match="ck_analysis_component_preview_zero_points"),
        create_engine(url).begin() as connection,
    ):
        connection.execute(
            text(
                "INSERT INTO analysis_anomaly_components(analysis_release_id,source_release_id,"
                "source_election_slug,anomaly_id,component_id,component_type,evidence_type,points,"
                "payload,provenance_hash) VALUES('analysis-preview-points',"
                "'source-preview-points','election','anomaly-1','peer-preview',"
                "'peer_distribution','research_preview',10,'{}',:provenance_hash)"
            ),
            {"provenance_hash": HASH_F},
        )


def test_current_schema_upgrade_and_clean_upgrade_create_the_same_analysis_tables(
    analysis_databases: dict[str, str],
) -> None:
    expected = {
        "analysis_releases",
        "analysis_artifact_hosts",
        "analysis_artifacts",
        "analysis_anomalies",
        "analysis_anomaly_components",
        "analysis_reports",
        "analysis_exposures",
    }
    for url in analysis_databases.values():
        assert expected <= set(inspect(create_engine(url)).get_table_names())

    current = analysis_databases["current"]
    _downgrade(current, PREVIOUS_REVISION)
    assert expected.isdisjoint(inspect(create_engine(current)).get_table_names())
    _upgrade(current, "head")
    assert expected <= set(inspect(create_engine(current)).get_table_names())


def test_analysis_release_binding_is_unique_and_artifacts_cannot_cross_scope(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    _seed_source(url, "source-a", "candidate", "preliminary")
    _seed_source(url, "source-b", "published", "public")
    _insert_analysis_release(url, "analysis-a", "source-a")

    with pytest.raises(
        DBAPIError,
        match="unique|duplicate",
    ):
        _insert_analysis_release(url, "analysis-duplicate", "source-a")

    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_artifact_hosts(host) VALUES('official.example') "
                "ON CONFLICT DO NOTHING"
            )
        )
    with pytest.raises(DBAPIError, match="foreign key"), create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_artifacts(analysis_release_id,source_release_id,"
                "source_election_slug,artifact_id,kind,schema_version,media_type,record_count,"
                "byte_size,byte_hash,content_hash,immutable_url,artifact_status) VALUES("
                "'analysis-a','source-b','election','cross-scope','summary','1.0.0',"
                "'application/json',1,1,:byte_hash,:content_hash,:url,'available')"
            ),
            {
                "byte_hash": HASH_E,
                "content_hash": HASH_F,
                "url": f"https://official.example/analysis/{HASH_E}.json",
            },
        )


def test_preliminary_source_is_visible_in_the_release_election_catalogue(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    release_id = "source-catalog-preliminary"
    _seed_source(url, release_id, "candidate", "preliminary")
    repository = PostgresReadRepository(url, release_id)
    try:
        selected = next(
            item for item in repository.public_elections() if item["release_id"] == release_id
        )
    finally:
        repository._engine.dispose()  # noqa: SLF001

    assert selected["status"] == "candidate"
    assert selected["exposure_approved_at"] is None


def test_artifact_urls_are_allowlisted_content_addressed_and_fail_closed(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    for artifact_id, artifact_url, message in (
        ("wrong-host", f"https://untrusted.example/analysis/{HASH_E}.json", "allowlisted"),
        ("mutable-url", "https://official.example/analysis/latest.json", "content-addressed"),
        ("url-query", f"https://official.example/analysis/{HASH_E}.json?download=1", "immutable"),
    ):
        with pytest.raises(DBAPIError, match=message), create_engine(url).begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO analysis_artifacts(analysis_release_id,source_release_id,"
                    "source_election_slug,artifact_id,kind,schema_version,media_type,record_count,"
                    "byte_size,byte_hash,content_hash,immutable_url,artifact_status) VALUES("
                    "'analysis-a','source-a','election',:artifact_id,'summary','1.0.0',"
                    "'application/json',1,1,:byte_hash,:content_hash,:url,'available')"
                ),
                {
                    "artifact_id": artifact_id,
                    "byte_hash": HASH_E,
                    "content_hash": HASH_F,
                    "url": artifact_url,
                },
            )


def test_preliminary_and_certified_exposures_have_disjoint_source_gates(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    _seed_analysis_content(url, "analysis-a", "source-a")
    now = datetime.now(UTC)
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_exposures(analysis_release_id,source_release_id,"
                "source_election_slug,exposure_tier,manifest_hash,exposed_at) VALUES("
                "'analysis-a','source-a','election','internal',:manifest_hash,:now)"
            ),
            {"manifest_hash": HASH_D, "now": now},
        )
        connection.execute(
            text(
                "UPDATE analysis_exposures SET exposure_tier='preliminary_research',"
                "approved_by='reviewer-a',approved_at=:now,approval_signature_hash=:signature,"
                "caveat_es='Investigación preliminar',caveat_en='Preliminary research' "
                "WHERE analysis_release_id='analysis-a'"
            ),
            {"now": now, "signature": HASH_A},
        )

    with (
        pytest.raises(DBAPIError, match="internal to preliminary_research or certified_public"),
        create_engine(url).begin() as connection,
    ):
        connection.execute(
            text(
                "UPDATE analysis_exposures SET exposure_tier='certified_public',"
                "pass_b_packet_hash=:pass_b,pass_b_runtime_fingerprint=:runtime,"
                "pass_b_operator_id='operator-b',independent_reviewer_id='reviewer-b',"
                "independent_review_signature_hash=:review_signature "
                "WHERE analysis_release_id='analysis-a'"
            ),
            {
                "pass_b": HASH_B,
                "runtime": HASH_E,
                "review_signature": HASH_F,
            },
        )

    _insert_analysis_release(url, "analysis-candidate-cert", "source-a", input_hash=HASH_C)
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_exposures(analysis_release_id,source_release_id,"
                "source_election_slug,exposure_tier,manifest_hash,exposed_at) VALUES("
                "'analysis-candidate-cert','source-a','election','internal',:manifest_hash,:now)"
            ),
            {"manifest_hash": HASH_D, "now": now},
        )
    with (
        pytest.raises(DBAPIError, match="certified source release"),
        create_engine(url).begin() as connection,
    ):
        connection.execute(
            text(
                "UPDATE analysis_exposures SET exposure_tier='certified_public',"
                "approved_by='reviewer-c',approved_at=:now,approval_signature_hash=:approval,"
                "caveat_es='Certificado',caveat_en='Certified',pass_b_packet_hash=:pass_b,"
                "pass_b_runtime_fingerprint=:runtime,pass_b_operator_id='operator-b',"
                "independent_reviewer_id='reviewer-c',"
                "independent_review_signature_hash=:review_signature "
                "WHERE analysis_release_id='analysis-candidate-cert'"
            ),
            {
                "now": now,
                "approval": HASH_A,
                "pass_b": HASH_B,
                "runtime": HASH_E,
                "review_signature": HASH_F,
            },
        )

    _insert_analysis_release(url, "analysis-certified", "source-b", input_hash=HASH_C)
    _seed_analysis_content(url, "analysis-certified", "source-b")
    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO analysis_exposures(analysis_release_id,source_release_id,"
                "source_election_slug,exposure_tier,manifest_hash,exposed_at) VALUES("
                "'analysis-certified','source-b','election','internal',:manifest_hash,:now)"
            ),
            {"manifest_hash": HASH_D, "now": now},
        )
        connection.execute(
            text(
                "UPDATE analysis_exposures SET exposure_tier='certified_public',"
                "approved_by='reviewer-c',approved_at=:now,approval_signature_hash=:approval,"
                "caveat_es='Certificado',caveat_en='Certified',pass_b_packet_hash=:pass_b,"
                "pass_b_runtime_fingerprint=:runtime,pass_b_operator_id='operator-b',"
                "independent_reviewer_id='reviewer-c',"
                "independent_review_signature_hash=:review_signature "
                "WHERE analysis_release_id='analysis-certified'"
            ),
            {
                "now": now,
                "approval": HASH_A,
                "pass_b": HASH_B,
                "runtime": HASH_E,
                "review_signature": HASH_F,
            },
        )


def test_postgres_repository_resolves_exact_certified_analysis_and_artifacts(
    analysis_databases: dict[str, str],
) -> None:
    repository = PostgresReadRepository(
        analysis_databases["clean"],
        "source-b",
        allowed_artifact_hosts={"official.example"},
    )
    preliminary_repository = PostgresReadRepository(
        analysis_databases["clean"],
        "source-a",
        allowed_artifact_hosts={"official.example"},
    )
    try:
        metadata = repository.analysis_release_metadata(
            "election", "source-b", "analysis-certified"
        )
        artifacts = repository.analysis_artifacts(
            "election", "source-b", metadata.analysis_release_id
        )
        preliminary = preliminary_repository.analysis_release_metadata("election", "source-a")
    finally:
        repository._engine.dispose()  # noqa: SLF001
        preliminary_repository._engine.dispose()  # noqa: SLF001

    assert metadata.source_release_id == "source-b"
    assert metadata.election_slug == "election"
    assert metadata.exposure_tier == "certified_public"
    assert metadata.preliminary_caveat is None
    assert [artifact.artifact_id for artifact in artifacts] == ["summary"]
    assert str(artifacts[0].url) == f"https://official.example/analysis/{HASH_E}.json"
    assert preliminary.analysis_release_id == "analysis-a"
    assert preliminary.exposure_tier == "preliminary_research"
    assert preliminary.preliminary_caveat is not None


def test_any_exposure_freezes_analysis_content_but_can_be_revoked_independently(
    analysis_databases: dict[str, str],
) -> None:
    url = analysis_databases["clean"]
    now = datetime.now(UTC)
    for statement in (
        "UPDATE analysis_releases SET methodology_version='changed' WHERE analysis_release_id='analysis-a'",
        "UPDATE analysis_artifacts SET record_count=2 WHERE analysis_release_id='analysis-a'",
        "UPDATE analysis_anomalies SET audit_priority=0 WHERE analysis_release_id='analysis-a'",
        "UPDATE analysis_anomaly_components SET points=0 WHERE analysis_release_id='analysis-a'",
        "UPDATE analysis_reports SET diagnostics='[]' WHERE analysis_release_id='analysis-a'",
        "DELETE FROM analysis_artifacts WHERE analysis_release_id='analysis-a'",
    ):
        with (
            pytest.raises(DBAPIError, match="exposed analysis release rows are immutable"),
            create_engine(url).begin() as connection,
        ):
            connection.execute(text(statement))

    with create_engine(url).begin() as connection:
        connection.execute(
            text(
                "UPDATE analysis_exposures SET revoked_at=:now,revoked_by='release-manager',"
                "revocation_reason='Independent rollback' WHERE analysis_release_id='analysis-a'"
            ),
            {"now": now},
        )
        assert connection.execute(
            text(
                "SELECT revoked_at IS NOT NULL FROM analysis_exposures WHERE analysis_release_id='analysis-a'"
            )
        ).scalar_one()

    with (
        pytest.raises(DBAPIError, match="revocation is immutable"),
        create_engine(url).begin() as connection,
    ):
        connection.execute(
            text(
                "UPDATE analysis_exposures SET revoked_at=NULL,revoked_by=NULL,"
                "revocation_reason=NULL WHERE analysis_release_id='analysis-a'"
            )
        )

    with (
        pytest.raises(DBAPIError, match="must be revoked, not deleted"),
        create_engine(url).begin() as connection,
    ):
        connection.execute(
            text("DELETE FROM analysis_exposures WHERE analysis_release_id='analysis-a'")
        )
