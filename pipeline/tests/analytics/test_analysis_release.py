from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from elecciones_pipeline.analytics.analysis_release import (
    AnalysisExposureTier,
    CanonicalInputRegistry,
    DocumentaryAttestation,
    PassBPacket,
    build_analysis_bundle,
    canonical_rows_from_snapshot,
    load_analysis_bundle,
    peer_family_from_canonical_rows,
    verify_pass_b_packet,
    write_analysis_bundle,
)
from elecciones_pipeline.analytics.peer_signals import peer_signals
from elecciones_pipeline.cli import _postgresql_engine, app
from typer.testing import CliRunner

SOURCE_RELEASE = "candidate-2026-r2-dacb28aa766eec87"
ELECTION = "presidencia-2026-segunda-vuelta"
HASH = "a" * 64


def _metric(value: int | None, status: str = "observed") -> dict[str, object]:
    return {"value": value, "status": status}


def _snapshot(*, mesa_count: int = 32) -> dict[str, object]:
    candidates = [
        {"id": "candidate-a", "ballot_number": 1},
        {"id": "candidate-b", "ballot_number": 2},
    ]
    mesas = []
    results = []
    for index in range(mesa_count + 3):
        mesa_id = f"mesa-{index:03d}"
        mesas.append(
            {
                "id": mesa_id,
                "polling_place_id": "place-1",
                "municipality_id": "municipality-1",
                "department_id": "department-1",
            }
        )
        if index >= mesa_count:
            continue
        results.append(
            {
                "id": f"fact-{mesa_id}",
                "mesa_id": mesa_id,
                "geography_id": "place-1",
                "geography_level": "mesa",
                "election_slug": ELECTION,
                "registered_electors": _metric(None, "unavailable"),
                "voters": _metric(100),
                "valid_votes": _metric(97),
                "blank_votes": _metric(2),
                "null_votes": _metric(1),
                "unmarked_votes": _metric(2),
                "candidates": [
                    {"candidate_id": "candidate-a", "votes": _metric(50 + index % 3)},
                    {"candidate_id": "candidate-b", "votes": _metric(45 - index % 3)},
                ],
                "provenance": {
                    "source_type": "pre_count",
                    "legal_status": "preliminary",
                    "source_url": f"https://official.example/{mesa_id}.json",
                    "content_hash": hashlib.sha256(mesa_id.encode()).hexdigest(),
                },
            }
        )
    return {
        "release": {
            "release_id": SOURCE_RELEASE,
            "data_version": SOURCE_RELEASE,
            "status": "candidate",
            "synthetic": False,
        },
        "election": {"slug": ELECTION, "candidates": candidates},
        "mesas": mesas,
        "results": results,
        "summary": {
            "reconciliation": {"status": "blocked", "exceptions": 3},
            "completion": {"reported": mesa_count, "expected": mesa_count + 3},
        },
    }


def _registry(snapshot: dict[str, object]) -> CanonicalInputRegistry:
    return CanonicalInputRegistry(
        source_release_id=SOURCE_RELEASE,
        election_slug=ELECTION,
        source_manifest_hash=HASH,
        detector_code_hash="b" * 64,
        configuration_hash="c" * 64,
        seed_registry_hash="d" * 64,
        runtime_fingerprint="e" * 64,
        documentary_attestations=(),
        geocode_ledger=None,
        snapshot=snapshot,
    )


def test_canonical_rows_preserve_missingness_and_are_deterministic() -> None:
    snapshot = _snapshot(mesa_count=2)
    rows = canonical_rows_from_snapshot(snapshot)

    assert [(row.mesa_id, row.metric, row.candidate_id or "") for row in rows] == sorted(
        (row.mesa_id, row.metric, row.candidate_id or "") for row in rows
    )
    assert len(rows) == 10
    turnout = next(row for row in rows if row.metric == "turnout")
    assert turnout.denominator.status == "unavailable"
    assert turnout.denominator.value is None
    assert all(row.denominator.value != 0 for row in rows)


def test_bundle_reports_current_eligibility_and_three_reconciliation_exceptions() -> None:
    bundle = build_analysis_bundle(
        _registry(_snapshot()),
        methodology_version="analysis-v1.0.0",
        generated_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert bundle.source_release_id == SOURCE_RELEASE
    assert bundle.exposure_tier == AnalysisExposureTier.INTERNAL
    assert bundle.eligibility["turnout"].status == "not_evaluable"
    assert bundle.eligibility["turnout"].reasons == ("registered_electors_coverage_insufficient",)
    assert bundle.eligibility["spatial"].status == "not_evaluable"
    assert bundle.eligibility["spatial"].reasons == (
        "authenticated_coordinates_unavailable",
        "mesa_to_place_crosswalk_unavailable",
    )
    assert bundle.eligibility["outcome_sensitivity"].status == "not_evaluable"
    for metric in (
        "candidate_share:candidate-a",
        "candidate_share:candidate-b",
        "blank",
        "null_unmarked",
    ):
        assert bundle.eligibility[metric].status == "evaluable"
    assert bundle.descriptive["reconciliation_exceptions"] == 3
    assert bundle.descriptive["mesa_completion"] == {"expected": 35, "reported": 32}
    assert bundle.descriptive["historical_context_is_anomaly_evidence"] is False
    assert bundle.manifest["canonical_input_hash"] == bundle.canonical_input_hash
    artifact_statuses = {artifact.kind: artifact.status for artifact in bundle.artifacts}
    assert artifact_statuses["model_diagnostics"] == "available"
    assert artifact_statuses["validation"] == "not_evaluable"
    assert artifact_statuses["local_sensitivity"] == "not_evaluable"
    assert artifact_statuses["spatial_status"] == "not_evaluable"
    assert artifact_statuses["outcome_sensitivity"] == "available"
    outcome_artifact = next(
        artifact for artifact in bundle.artifacts if artifact.kind == "outcome_sensitivity"
    )
    outcome_payload = json.loads(outcome_artifact.content)
    assert outcome_artifact.record_count == 1
    assert outcome_payload["status"] == "not_evaluable"
    assert outcome_payload["evaluable"] is False
    assert [issue["code"] for issue in outcome_payload["issues"]] == [
        "documentary_trust_registry_unavailable",
        "two_reviewer_attestations_unavailable",
        "canonical_replay_bounds_unavailable",
    ]
    assert outcome_payload["verified_affected_votes"] is None
    output_hash = outcome_payload.pop("output_hash")
    assert (
        output_hash
        == hashlib.sha256(
            json.dumps(
                outcome_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
    )
    canonical_artifact = next(
        artifact for artifact in bundle.artifacts if artifact.kind == "canonical_input"
    )
    canonical_payload = json.loads(canonical_artifact.content)
    assert canonical_payload["registry"]["excluded_units"] == [
        {"reason": "result_unavailable", "unit_id": "mesa-032"},
        {"reason": "result_unavailable", "unit_id": "mesa-033"},
        {"reason": "result_unavailable", "unit_id": "mesa-034"},
    ]
    anomalies = json.loads(
        next(
            artifact for artifact in bundle.artifacts if artifact.kind == "deterministic_anomalies"
        ).content
    )
    assert [item["unit_id"] for item in anomalies] == [
        "mesa-032",
        "mesa-033",
        "mesa-034",
    ]
    cohorts = json.loads(
        next(
            artifact for artifact in bundle.artifacts if artifact.kind == "cohort_registry"
        ).content
    )
    candidate_family = next(
        family for family in cohorts["families"] if family["candidate_id"] == "candidate-a"
    )
    assert candidate_family["family_count"] == 32
    assert candidate_family["fallback_order"] == [
        "polling_place",
        "municipality",
        "department",
    ]
    assert all(
        selection["selected_pool"] == "polling_place"
        and selection["peer_count"] == 31
        and selection["target_excluded"] is True
        for selection in candidate_family["selections"]
    )


def test_canonical_rows_bind_complete_leave_one_out_peer_family() -> None:
    rows = canonical_rows_from_snapshot(_snapshot())
    family = peer_family_from_canonical_rows(
        rows,
        metric="candidate_share",
        candidate_id="candidate-a",
        source_release_id=SOURCE_RELEASE,
        election_slug=ELECTION,
        input_artifact_hash=HASH,
    )

    assert not family.excluded_units
    assert len(family.mesas) == 32
    assert all(row.expected_family_digest == family.family_digest for row in family.mesas)
    signals = peer_signals(family.mesas)
    assert all(signal.peers == 31 for signal in signals)
    assert all(signal.peer_level == "polling_place" for signal in signals)
    assert all(not signal.public_point_eligible for signal in signals)


def test_bundle_generation_is_content_deterministic() -> None:
    registry = _registry(_snapshot())
    generated_at = datetime(2026, 8, 10, tzinfo=UTC)
    first = build_analysis_bundle(
        registry,
        methodology_version="analysis-v1.0.0",
        generated_at=generated_at,
    )
    replay = build_analysis_bundle(
        registry,
        methodology_version="analysis-v1.0.0",
        generated_at=generated_at,
    )

    assert first.analysis_release_id == replay.analysis_release_id
    assert first.canonical_input_hash == replay.canonical_input_hash
    assert first.manifest_hash == replay.manifest_hash
    assert first.artifacts == replay.artifacts


def test_bundle_materialization_is_immutable_idempotent_and_tamper_evident(
    tmp_path: Path,
) -> None:
    bundle = build_analysis_bundle(
        _registry(_snapshot()),
        methodology_version="analysis-v1.0.0",
        generated_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    target = write_analysis_bundle(bundle, tmp_path)
    assert target == tmp_path / bundle.analysis_release_id
    assert write_analysis_bundle(bundle, tmp_path) == target
    loaded = load_analysis_bundle(target / "manifest.json")
    assert loaded["analysis_release_id"] == bundle.analysis_release_id
    assert loaded["manifest_hash"] == bundle.manifest_hash

    artifact_path = target / "artifacts" / "eligibility.json"
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="byte (size|hash)"):
        load_analysis_bundle(target / "manifest.json")


def test_bundle_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"analysis_release_id":"one","analysis_release_id":"two"}')

    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_analysis_bundle(manifest)


def test_analysis_release_cli_builds_internal_bundle_without_exposure(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    manifest_path = tmp_path / "source-manifest.json"
    configuration_path = tmp_path / "configuration.json"
    output = tmp_path / "analysis-releases"
    snapshot_path.write_text(json.dumps(_snapshot()))
    manifest_path.write_text(json.dumps({"release_id": SOURCE_RELEASE, "election_slug": ELECTION}))
    configuration_path.write_text(json.dumps({"simulation_profiles": {"preliminary": {"seed": 0}}}))
    arguments = [
        "analysis-release-build",
        "--snapshot",
        str(snapshot_path),
        "--source-manifest",
        str(manifest_path),
        "--configuration",
        str(configuration_path),
        "--generated-at",
        "2026-08-10T10:00:00-05:00",
        "--runtime-fingerprint",
        "e" * 64,
        "--output-dir",
        str(output),
    ]

    first = CliRunner().invoke(app, arguments)
    replay = CliRunner().invoke(app, arguments)

    assert first.exit_code == 0, first.output
    assert replay.exit_code == 0, replay.output
    payload = json.loads(first.output)
    assert payload["exposure_tier"] == "internal"
    assert payload["publication_performed"] is False
    assert json.loads(replay.output) == payload


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://operator:secret@db.example.test/elections",
        "postgres://operator:secret@db.example.test/elections",
        "postgresql+psycopg://operator:secret@db.example.test/elections",
    ),
)
def test_postgresql_engine_uses_the_installed_psycopg3_driver(database_url: str) -> None:
    engine = _postgresql_engine(database_url)

    assert engine.url.drivername == "postgresql+psycopg"
    engine.dispose()


def test_documentary_attestations_are_links_only_and_require_two_reviewers() -> None:
    with pytest.raises(ValueError, match="two distinct"):
        DocumentaryAttestation(
            claim_id="claim-1",
            official_document_url="https://official.example/e14/1",
            source_identifier="e14-1",
            expected_document_type="E-14",
            reviewer_ids=("reviewer-1", "reviewer-1"),
            reviewer_signatures=("sig-1", "sig-2"),
            structured_fields_hash=HASH,
        )
    with pytest.raises(ValueError, match="official HTTPS"):
        DocumentaryAttestation(
            claim_id="claim-1",
            official_document_url="data:application/pdf;base64,abc",
            source_identifier="e14-1",
            expected_document_type="E-14",
            reviewer_ids=("reviewer-1", "reviewer-2"),
            reviewer_signatures=("sig-1", "sig-2"),
            structured_fields_hash=HASH,
        )


def test_pass_b_requires_distinct_runtime_operator_and_external_signature_verification() -> None:
    bundle = build_analysis_bundle(
        _registry(_snapshot()),
        methodology_version="analysis-v1.0.0",
        generated_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    packet = PassBPacket(
        analysis_release_id=bundle.analysis_release_id,
        source_release_id=SOURCE_RELEASE,
        election_slug=ELECTION,
        methodology_version="analysis-v1.0.0",
        canonical_input_hash=bundle.canonical_input_hash,
        manifest_hash=bundle.manifest_hash,
        detector_code_hash="b" * 64,
        producer_runtime_fingerprint="e" * 64,
        replay_runtime_fingerprint="f" * 64,
        producer_operator_id="producer-1",
        replay_operator_id="operator-2",
        reviewer_id="reviewer-3",
        reviewer_key_id="stats-key-1",
        reviewer_signature="signed-externally",
        decision="approve",
        reviewed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    verified = verify_pass_b_packet(
        packet,
        bundle,
        signature_verifier=lambda message, signature, key: (
            json.loads(message)["manifest_hash"] == bundle.manifest_hash
            and signature == "signed-externally"
            and key == "stats-key-1"
        ),
    )
    assert verified
    with pytest.raises(ValueError, match="distinct runtime"):
        verify_pass_b_packet(
            replace(packet, replay_runtime_fingerprint="e" * 64),
            bundle,
            signature_verifier=lambda *_: True,
        )
    with pytest.raises(ValueError, match="distinct operator"):
        verify_pass_b_packet(
            replace(packet, replay_operator_id="producer-1"),
            bundle,
            signature_verifier=lambda *_: True,
        )
    with pytest.raises(ValueError, match="signature"):
        verify_pass_b_packet(packet, bundle, signature_verifier=lambda *_: False)
