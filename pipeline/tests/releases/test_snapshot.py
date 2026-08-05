from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from elecciones_api.repository import FixtureRepository
from elecciones_pipeline.analytics.peer_signals import (
    CODE_HASH as PEER_CODE_HASH,
)
from elecciones_pipeline.analytics.peer_signals import (
    METHOD_HASH as PEER_METHOD_HASH,
)
from elecciones_pipeline.analytics.peer_signals import (
    cohort_digest,
)
from elecciones_pipeline.analytics.spatial import (
    CODE_HASH as SPATIAL_CODE_HASH,
)
from elecciones_pipeline.analytics.spatial import (
    METHOD_HASH as SPATIAL_METHOD_HASH,
)
from elecciones_pipeline.analytics.spatial import (
    input_artifact_hash as spatial_input_artifact_hash,
)
from elecciones_pipeline.analytics.spatial import (
    spatial_cohort_digest,
    spatial_family_digest,
    spatial_mesa_digest,
)
from elecciones_pipeline.releases.snapshot import (
    DocumentaryTotalsAttestation,
    SnapshotError,
    _validate_release_state,
    canonical_snapshot_bytes,
    documentary_totals_digest,
    materialize_api_snapshot,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "data/fixtures/fixture-release.json"
MANIFEST_PATH = ROOT / "data/manifests/fixture-2026-round2-v1.json"


def release_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, release = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    )
    # Fixture records stand in for freshly recomputed analyzer output; bind
    # their code provenance to the analyzer actually imported by this test.
    for signal in release["review_signals"]:
        if signal.get("score") == 10:
            signal["tier"] = "no_review_signals"
        for component in signal["components"]:
            if component["component_type"] == "peer_distribution":
                component["code_hash"] = PEER_CODE_HASH
                component["method_hash"] = PEER_METHOD_HASH
                component["evidence_artifact_hash"] = None
                component["evidence_artifact_kind"] = None
            elif component["component_type"] != "spatial_cluster":
                component["evidence_artifact_hash"] = str(manifest["sources"][0]["content_hash"])
                component["evidence_artifact_kind"] = "document_review"
    declared_hash = str(manifest["sources"][0]["content_hash"])
    for comparisons in release["comparisons"].values():
        for comparison in comparisons:
            comparison["left_artifact_hash"] = declared_hash
            comparison["right_artifact_hash"] = declared_hash
    return manifest, release


def materialize(manifest: dict[str, Any], release: dict[str, Any], **overrides: Any):
    validated_families = [
        {
            "detector_id": "peer",
            "family_id": component.get("family_id"),
            "code_hash": component.get("code_hash"),
            "method_hash": component.get("method_hash"),
            "input_artifact_hash": component.get("input_artifact_hash"),
            "cohort_hash": component.get("cohort_hash"),
        }
        for signal in release["review_signals"]
        for component in signal["components"]
        if component["component_type"] == "peer_distribution"
    ]
    authorization_payload = {
        "schema": "statistical-authorization-v1",
        "validated_families": validated_families,
    }
    authorization_hash = hashlib.sha256(
        canonical_snapshot_bytes(authorization_payload)
        ).hexdigest()
    deterministic_components = [
        {
            "mesa_id": signal["mesa_id"],
            "component_hash": hashlib.sha256(canonical_snapshot_bytes(component)).hexdigest(),
            "evidence_artifact_hash": component["evidence_artifact_hash"],
            "evidence_artifact_kind": component["evidence_artifact_kind"],
        }
        for signal in release["review_signals"]
        for component in signal["components"]
        if component["component_type"] not in {"peer_distribution", "spatial_cluster"}
    ]
    deterministic_components.sort(
        key=lambda item: (str(item["mesa_id"]), str(item["component_hash"]))
    )
    evidence_payload = {
        "schema": "deterministic-evidence-authorization-v1",
        "components": deterministic_components,
    }
    evidence_hash = hashlib.sha256(canonical_snapshot_bytes(evidence_payload)).hexdigest()
    comparison_entries = [
        {
            "mesa_id": mesa_id,
            "comparison_hash": hashlib.sha256(canonical_snapshot_bytes(comparison)).hexdigest(),
        }
        for mesa_id, comparisons in release["comparisons"].items()
        for comparison in comparisons
    ]
    comparison_entries.sort(key=lambda item: (str(item["mesa_id"]), str(item["comparison_hash"])))
    comparison_payload = {
        "schema": "comparison-authorization-v1",
        "comparisons": comparison_entries,
    }
    comparison_hash = hashlib.sha256(canonical_snapshot_bytes(comparison_payload)).hexdigest()
    if not any(item["id"] == "statistical-authorization" for item in manifest["datasets"]):
        manifest["datasets"].append(
            {
                "id": "statistical-authorization",
                "title": {"es": "Autorización estadística", "en": "Statistical authorization"},
                "format": "json",
                "url": "https://example.invalid/fixture/statistical-authorization.json",
                "schema_url": "https://example.invalid/schema/statistical-authorization.json",
                "record_count": 1,
                "byte_size": len(canonical_snapshot_bytes(authorization_payload)),
                "content_hash": authorization_hash,
                "filters": {},
            }
        )
    if not any(
        item["id"] == "deterministic-evidence-authorization" for item in manifest["datasets"]
    ):
        manifest["datasets"].append(
            {
                "id": "deterministic-evidence-authorization",
                "title": {"es": "Autorización documental", "en": "Documentary authorization"},
                "format": "json",
                "url": "https://example.invalid/fixture/deterministic-evidence-authorization.json",
                "schema_url": "https://example.invalid/schema/deterministic-evidence-authorization.json",
                "record_count": len(deterministic_components),
                "byte_size": len(canonical_snapshot_bytes(evidence_payload)),
                "content_hash": evidence_hash,
                "filters": {},
            }
        )
    if not any(item["id"] == "comparison-authorization" for item in manifest["datasets"]):
        manifest["datasets"].append(
            {
                "id": "comparison-authorization",
                "title": {"es": "Autorización de comparación", "en": "Comparison authorization"},
                "format": "json",
                "url": "https://example.invalid/fixture/comparison-authorization.json",
                "schema_url": "https://example.invalid/schema/comparison-authorization.json",
                "record_count": len(comparison_entries),
                "byte_size": len(canonical_snapshot_bytes(comparison_payload)),
                "content_hash": comparison_hash,
                "filters": {},
            }
        )
    arguments: dict[str, Any] = {
        "manifest": manifest,
        "election": release["election"],
        "summary": release["summary"],
        "geographies": release["geographies"],
        "mesas": release["mesas"],
        "results": release["results"],
        "provenance": release["provenance"],
        "evidence": release["evidence"],
        "evidence_handling": release["evidence_handling"],
        "comparisons": release["comparisons"],
        "bulletins": release["bulletins"],
        "review_signals": release["review_signals"],
        "statistical_authorization": {
            "artifact_hash": authorization_hash,
            "validated_families": validated_families,
        },
        "evidence_authorization": {
            "artifact_hash": evidence_hash,
            "components": deterministic_components,
        },
        "comparison_authorization": {
            "artifact_hash": comparison_hash,
            "comparisons": comparison_entries,
        },
    }
    arguments.update(overrides)
    return materialize_api_snapshot(**arguments)


def fixture_with_spatial_component(
    *, coordinate_grain: Literal["mesa", "polling_place"] = "mesa"
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, release = release_inputs()
    signal = next(
        item
        for item in release["review_signals"]
        if item["components"][0]["component_type"] == "peer_distribution"
    )
    mesas_by_id = {str(mesa["id"]): mesa for mesa in release["mesas"]}
    expected_units = (
        set(mesas_by_id)
        if coordinate_grain == "mesa"
        else {str(mesa["polling_place_id"]) for mesa in mesas_by_id.values()}
    )
    expected_digest = spatial_family_digest(expected_units)
    expected_mesa_digest = spatial_mesa_digest(mesas_by_id)
    membership_digest = "8" * 64
    peer_residual_hash = str(manifest["datasets"][0]["content_hash"])
    coordinate_source = manifest["sources"][0]
    combined_input_hash = spatial_input_artifact_hash(
        peer_residual_artifact_hash=peer_residual_hash,
        coordinate_source_hash=coordinate_source["content_hash"],
        analysis_unit_digest=expected_digest,
        mesa_membership_digest=membership_digest,
    )
    cohort_hash = spatial_cohort_digest(
        peer_residual_artifact_hash=peer_residual_hash,
        election_slug=release["election"]["slug"],
        data_version=manifest["data_version"],
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="turnout",
        candidate_id=None,
        peer_methodology_version="peer-beta-binomial-eb-v3",
        coordinate_source_url=coordinate_source["source_url"],
        coordinate_source_hash=coordinate_source["content_hash"],
        coordinate_accuracy_m=10.0,
        coordinate_grain=coordinate_grain,
        expected_family_count=len(expected_units),
        expected_family_digest=expected_digest,
        expected_mesa_count=len(mesas_by_id),
        expected_mesa_digest=expected_mesa_digest,
        expected_mesa_membership_digest=membership_digest,
    )
    signal["components"] = [
        {
            "component_type": "spatial_cluster",
            "evidence_artifact_hash": None,
            "evidence_artifact_kind": None,
            "points": 10,
            "observed_value": 2.0,
            "comparator": "all spatial gates passed",
            "calculation": "conditional random-label null",
            "peer_definition": "nearest same-municipality analysis units",
            "limitations": {"es": "Guía experimental.", "en": "Experimental lead."},
            "source_links": [
                signal["provenance"]["source_url"],
                coordinate_source["source_url"],
            ],
            "analyzer_output_hash": str(manifest["datasets"][0]["content_hash"]),
            "family_id": "|".join(
                (
                    manifest["data_version"],
                    release["election"]["slug"],
                    "pre_count",
                    "turnout",
                    "none",
                )
            ),
            "expected_family_count": len(expected_units),
            "expected_family_digest": expected_digest,
            "cohort_hash": cohort_hash,
            "input_artifact_hash": combined_input_hash,
            "code_hash": SPATIAL_CODE_HASH,
            "method_hash": SPATIAL_METHOD_HASH,
            "p_value": 0.0001,
            "q_value": 0.01,
            "family_rank": 1,
            "family_size": len(expected_units),
            "adjustment_method": "benjamini-yekutieli",
            "analyzer_mesa_id": signal["mesa_id"],
            "randomization_seed": 7,
            "spatial_permutations": 9_999,
            "spatial_neighbors": ["mesa-2", "mesa-3", "mesa-4"],
            "spatial_signal_kind": "positive_cluster",
            "spatial_local_residual": 2.0,
            "analysis_unit_id": (
                signal["mesa_id"]
                if coordinate_grain == "mesa"
                else mesas_by_id[str(signal["mesa_id"])]["polling_place_id"]
            ),
            "peer_residual_artifact_hash": peer_residual_hash,
            "peer_methodology_version": "peer-beta-binomial-eb-v3",
            "coordinate_source_url": coordinate_source["source_url"],
            "coordinate_source_hash": coordinate_source["content_hash"],
            "coordinate_accuracy_m": 10.0,
            "coordinate_grain": coordinate_grain,
            "expected_mesa_count": len(mesas_by_id),
            "expected_mesa_digest": expected_mesa_digest,
            "analysis_unit_digest": expected_digest,
            "mesa_membership_digest": membership_digest,
            "expected_mesa_membership_digest": membership_digest,
            "neighbors": ["mesa-2", "mesa-3", "mesa-4"],
            "signal_kind": "positive_cluster",
            "local_statistic": 2.0,
            "local_residual": 2.0,
            "permutations": 9_999,
        }
    ]
    return manifest, release


def candidate_with_documentary_summary() -> tuple[dict[str, Any], dict[str, Any], str]:
    manifest, release = release_inputs()
    data_version = "candidate-2026-round2-v1"
    manifest["release_id"] = data_version
    manifest["data_version"] = data_version
    manifest["status"] = "candidate"
    manifest["synthetic"] = False
    release["summary"]["data_version"] = data_version
    release["summary"]["release_status"] = "candidate"
    release["summary"]["synthetic"] = False
    for result in [release["summary"], *release["results"]]:
        candidate_total = sum(candidate["votes"]["value"] for candidate in result["candidates"])
        valid_votes = candidate_total + result["blank_votes"]["value"]
        result["valid_votes"]["value"] = valid_votes
        result["voters"]["value"] = (
            valid_votes + result["null_votes"]["value"] + result["unmarked_votes"]["value"]
        )
    release["summary"]["turnout"] = (
        release["summary"]["voters"]["value"] / release["summary"]["registered_electors"]["value"]
    )
    for candidate in release["summary"]["candidates"]:
        candidate["share"] = (
            candidate["votes"]["value"] / release["summary"]["valid_votes"]["value"]
        )
    for provenance in [
        release["provenance"],
        release["summary"]["provenance"],
        *(item["provenance"] for item in release["results"]),
        *(item["provenance"] for item in release["evidence"]),
        *(item["provenance"] for item in release["review_signals"]),
    ]:
        provenance["data_version"] = data_version
    for bulletin in release["bulletins"]:
        bulletin["data_version"] = data_version
    for signal in release["review_signals"]:
        for component in signal["components"]:
            if component["component_type"] not in {"peer_distribution", "spatial_cluster"}:
                continue
            component["analyzer_mesa_id"] = signal["mesa_id"]
            if component["component_type"] != "peer_distribution":
                continue
            family_parts = component["family_id"].split("|")
            family_parts[0] = data_version
            component["family_id"] = "|".join(family_parts)
            component["cohort_hash"] = cohort_digest(
                election_slug=family_parts[1],
                data_version=data_version,
                source_layer=family_parts[2],
                source_type=signal["provenance"]["source_type"],
                legal_status=signal["provenance"]["legal_status"],
                metric=family_parts[3],
                candidate_id=family_parts[4] if family_parts[4] != "none" else None,
                expected_family_count=component["expected_family_count"],
                expected_family_digest=component["expected_family_digest"],
                input_artifact_hash=component["input_artifact_hash"],
            )

    source_hash = "f" * 64
    final_source = deepcopy(manifest["sources"][0])
    final_source.update(
        {
            "id": "cne-final-declaration",
            "source_type": "final_declaration",
            "legal_status": "controlling_final",
            "source_url": "https://www.cne.gov.co/declaracion-final.pdf",
            "content_hash": source_hash,
            "media_type": "application/pdf",
        }
    )
    manifest["sources"].append(final_source)
    manifest["parser_versions"]["cne-final-declaration"] = final_source["parser_version"]
    release["summary"]["provenance"].update(
        {
            "source_type": "final_declaration",
            "legal_status": "controlling_final",
            "source_url": final_source["source_url"],
            "content_hash": source_hash,
        }
    )
    return manifest, release, source_hash


def test_snapshot_is_repository_shaped_stable_and_preserves_unknown_vs_zero() -> None:
    manifest, release = release_inputs()
    release["results"][4]["registered_electors"] = {"value": None, "status": "unknown"}
    release["summary"]["registered_electors"] = {"value": None, "status": "unknown"}
    first = materialize(manifest, release)

    shuffled_manifest = deepcopy(manifest)
    shuffled_manifest["datasets"].reverse()
    shuffled = deepcopy(release)
    for key in ("geographies", "mesas", "results", "evidence", "bulletins", "review_signals"):
        shuffled[key].reverse()
    shuffled["election"]["candidates"].reverse()
    shuffled["summary"]["candidates"].reverse()
    for result in shuffled["results"]:
        result["candidates"].reverse()
    for bulletin in shuffled["bulletins"]:
        bulletin["candidate_votes"] = dict(reversed(bulletin["candidate_votes"].items()))
    second = materialize(shuffled_manifest, shuffled)

    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256 == hashlib.sha256(first.canonical_bytes).hexdigest()
    assert canonical_snapshot_bytes(first.snapshot) == first.canonical_bytes
    assert set(first.snapshot) == {
        "release",
        "election",
        "summary",
        "geographies",
        "mesas",
        "results",
        "evidence",
        "evidence_handling",
        "comparisons",
        "bulletins",
        "review_signals",
        "datasets",
        "provenance",
    }
    unknown = next(item for item in first.snapshot["results"] if item["id"] == "result-005")
    zero = next(item for item in first.snapshot["results"] if item["id"] == "result-006")
    assert unknown["registered_electors"] == {"value": None, "status": "unknown"}
    assert zero["unmarked_votes"] == {"value": 0, "status": "observed"}

    repository = FixtureRepository.from_snapshot(first.manifest_value(), is_fixture=True)
    assert (
        repository.summary(release["election"]["slug"], None).data_version
        == (manifest["release_id"])
    )
    assert len(repository.results(release["election"]["slug"], None)) == 6
    # The historical fixture remains byte-stable. Its retired derivative
    # fields are safely omitted by the index-only public projection.
    assert repository.evidence("2026-R2-11-001-001-003", None) == []
    assert (
        repository.review_methodology_version(release["election"]["slug"], None)
        == (manifest["methodology_version"])
    )


def test_nested_data_version_and_metric_state_mismatches_fail_closed() -> None:
    manifest, release = release_inputs()
    release["results"][0]["provenance"]["data_version"] = "different-release"
    with pytest.raises(SnapshotError, match="data_version"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    release["results"][0]["unmarked_votes"] = {"value": 0, "status": "unknown"}
    with pytest.raises(SnapshotError, match="non-observed values as null"):
        materialize(manifest, release)


def test_review_signal_boundary_rejects_statistical_vote_claims_and_duplicate_components() -> None:
    manifest, release = release_inputs()
    statistical = next(
        item
        for item in release["review_signals"]
        if item["components"][0]["component_type"] == "peer_distribution"
    )
    statistical["affected_vote_estimate"] = 1
    with pytest.raises(SnapshotError, match="statistical-only"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    release["review_signals"][0]["components"].append(
        deepcopy(release["review_signals"][0]["components"][0])
    )
    with pytest.raises(SnapshotError, match="duplicate component"):
        materialize(manifest, release)


def test_deterministic_component_values_need_canonical_evidence_authorization() -> None:
    manifest, release = release_inputs()
    signal, deterministic = next(
        (signal, component)
        for signal in release["review_signals"]
        for component in signal["components"]
        if component["component_type"] == "documentary_difference_major"
    )
    authorization_components = [
        {
            "mesa_id": signal["mesa_id"],
            "component_hash": hashlib.sha256(canonical_snapshot_bytes(deterministic)).hexdigest(),
            "evidence_artifact_hash": deterministic["evidence_artifact_hash"],
            "evidence_artifact_kind": deterministic["evidence_artifact_kind"],
        }
    ]
    authorization_payload = {
        "schema": "deterministic-evidence-authorization-v1",
        "components": authorization_components,
    }
    authorization_hash = hashlib.sha256(canonical_snapshot_bytes(authorization_payload)).hexdigest()
    manifest["datasets"].append(
        {
            "id": "original-deterministic-evidence-authorization",
            "title": {"es": "Autorización original", "en": "Original authorization"},
            "format": "json",
            "url": "https://example.invalid/fixture/original-evidence-authorization.json",
            "schema_url": "https://example.invalid/schema/original-evidence-authorization.json",
            "record_count": 1,
            "byte_size": len(canonical_snapshot_bytes(authorization_payload)),
            "content_hash": authorization_hash,
            "filters": {},
        }
    )
    deterministic["observed_value"] = float(deterministic["observed_value"]) + 1
    with pytest.raises(SnapshotError, match="deterministic evidence authorization"):
        materialize(
            manifest,
            release,
            evidence_authorization={
                "artifact_hash": authorization_hash,
                "components": authorization_components,
            },
        )


def test_self_minted_authorizations_cannot_publish_public_evidence_or_operands() -> None:
    manifest, release = release_inputs()
    # Even when a caller makes source grains appear mesa-level and regenerates
    # the comparison authorization, the snapshot has no typed fact replay and
    # therefore cannot expose the supplied operands as facts.
    for source in manifest["sources"]:
        source["published_grain"] = "mesa"
    comparison = next(iter(release["comparisons"].values()))[0]
    comparison["left_value"] = {"value": 999_999, "status": "observed"}
    comparison["right_value"] = {"value": 0, "status": "observed"}
    comparison["signed_difference"] = 999_999
    comparison["affected_vote_estimate"] = 999_999
    snapshot = materialize(manifest, release).snapshot
    exposed = next(iter(snapshot["comparisons"].values()))[0]
    assert exposed["left_value"] == exposed["right_value"] == {
        "value": None,
        "status": "unknown",
    }
    assert exposed["signed_difference"] is None
    assert exposed["affected_vote_estimate"] is None

    manifest, release, _source_hash = candidate_with_documentary_summary()
    with pytest.raises(SnapshotError, match="typed deterministic artifact replay"):
        materialize(manifest, release)


def test_statistical_review_component_requires_matching_authenticated_family() -> None:
    manifest, release = release_inputs()
    with pytest.raises(SnapshotError, match="validated-family authorization"):
        materialize(manifest, release, statistical_authorization=None)

    authorization = {
        "artifact_hash": str(manifest["datasets"][0]["content_hash"]),
        "validated_families": [],
    }
    with pytest.raises(SnapshotError, match="authorization artifact hash"):
        materialize(manifest, release, statistical_authorization=authorization)

    manifest, release = release_inputs()
    statistical = next(
        item
        for item in release["review_signals"]
        if item["components"][0]["component_type"] == "peer_distribution"
    )
    statistical["components"][0].pop("code_hash")
    with pytest.raises(SnapshotError, match="SHA-256"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    statistical = next(
        item
        for item in release["review_signals"]
        if item["components"][0]["component_type"] == "peer_distribution"
    )
    statistical["components"][0]["input_artifact_hash"] = "f" * 64
    with pytest.raises(SnapshotError, match="not declared by the release"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    statistical = next(
        item
        for item in release["review_signals"]
        if item["components"][0]["component_type"] == "peer_distribution"
    )
    statistical["components"][0]["q_value"] = 0.1
    with pytest.raises(SnapshotError, match="frozen p/q"):
        materialize(manifest, release)


def test_spatial_component_is_bound_to_exact_release_units_and_artifacts() -> None:
    manifest, release = fixture_with_spatial_component()
    with pytest.raises(SnapshotError, match="ineligible until spatial calibration"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    ten_point = next(item for item in release["review_signals"] if item["score"] == 10)
    ten_point["tier"] = "statistical_or_coverage_issue"
    with pytest.raises(SnapshotError, match="tier does not match"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    release["review_signals"][0]["provenance"].update(
        {"source_type": "contextual_baseline", "legal_status": "context_only"}
    )
    with pytest.raises(SnapshotError, match="contextual provenance"):
        materialize(manifest, release)


def test_snapshot_recomputes_accounting_and_complete_summary_rollups() -> None:
    manifest, release = release_inputs()
    release["results"][0]["valid_votes"]["value"] = 189
    with pytest.raises(SnapshotError, match="candidate votes do not equal valid votes"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    release["summary"]["voters"]["value"] = 1199
    release["summary"]["turnout"] = 1199 / 1500
    with pytest.raises(SnapshotError, match="do not equal voters"):
        materialize(manifest, release)

    manifest, release = release_inputs()
    release["summary"]["candidates"][0]["votes"]["value"] = 601
    release["summary"]["valid_votes"]["value"] = 1149
    release["summary"]["voters"]["value"] = 1199
    release["summary"]["turnout"] = 1199 / 1500
    release["summary"]["candidates"][0]["share"] = 601 / 1149
    release["summary"]["candidates"][1]["share"] = 548 / 1149
    with pytest.raises(SnapshotError, match="exact mesa rollup"):
        materialize(manifest, release)


def test_completed_release_may_have_zero_review_signals() -> None:
    manifest, release = release_inputs()
    release["review_signals"] = []
    assert materialize(manifest, release).snapshot["review_signals"] == []

    manifest, release = release_inputs()
    no_signal = deepcopy(release["review_signals"][-1])
    no_signal.update(
        {
            "id": "signal-none",
            "score": 0,
            "tier": "no_review_signals",
            "components": [],
        }
    )
    release["review_signals"] = [no_signal]
    assert materialize(manifest, release).snapshot["review_signals"][0]["score"] == 0


def test_context_only_snapshot_rejects_review_signals_and_statistical_validation() -> None:
    manifest = {
        "status": "published",
        "synthetic": False,
        "release_class": "context_only",
        "aggregate_reconciled": True,
        "wording_validation_passed": True,
        "statistical_validation_passed": False,
    }
    summary = {"provenance": {"source_type": "contextual_baseline"}}
    _validate_release_state(manifest, summary, [])
    with pytest.raises(SnapshotError, match="cannot contain review signals"):
        _validate_release_state(manifest, summary, [{"id": "forbidden"}])
    manifest["statistical_validation_passed"] = True
    with pytest.raises(SnapshotError, match="disable statistical validation"):
        _validate_release_state(manifest, summary, [])


def test_synthetic_and_publication_state_mismatches_fail_closed() -> None:
    manifest, release = release_inputs()
    manifest["status"] = "candidate"
    release["summary"]["release_status"] = "candidate"
    with pytest.raises(SnapshotError, match="synthetic must be true exactly"):
        materialize(manifest, release)

    manifest, release, source_hash = candidate_with_documentary_summary()
    release["review_signals"] = []
    manifest["status"] = "published"
    release["summary"]["release_status"] = "published"
    digest = documentary_totals_digest(
        source_content_hash=source_hash,
        summary=release["summary"],
        results=release["results"],
    )
    attestation = DocumentaryTotalsAttestation(
        source_content_hash=source_hash,
        values_digest=digest,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        verified_at=datetime(2026, 8, 3, tzinfo=UTC),
    )
    with pytest.raises(SnapshotError, match="every manifest release gate"):
        materialize(
            manifest,
            release,
            documentary_totals_attestations=(attestation,),
        )
    manifest["statistical_validation_passed"] = True
    assert (
        materialize(
            manifest,
            release,
            documentary_totals_attestations=(attestation,),
        ).snapshot["release"]["status"]
        == "published"
    )


def test_documentary_totals_require_explicit_matching_two_human_attestation() -> None:
    manifest, release, source_hash = candidate_with_documentary_summary()
    release["review_signals"] = []
    # The legacy fixture contains retired document-processing fields. The
    # index-only projection omits them; they cannot be reused or inferred as
    # verification of these final-declaration totals.
    assert release["evidence"]
    with pytest.raises(SnapshotError, match="human double-entry attestation"):
        materialize(manifest, release)

    undeclared = deepcopy(release)
    undeclared["summary"]["provenance"]["content_hash"] = "e" * 64
    with pytest.raises(SnapshotError, match="immutable manifest source"):
        materialize(manifest, undeclared)

    with pytest.raises(SnapshotError, match="two distinct human reviewers"):
        DocumentaryTotalsAttestation(
            source_content_hash=source_hash,
            values_digest="a" * 64,
            reviewer_ids=("same-reviewer", "same-reviewer"),
            verified_at=datetime(2026, 8, 3, tzinfo=UTC),
        )

    digest = documentary_totals_digest(
        source_content_hash=source_hash,
        summary=release["summary"],
        results=release["results"],
    )
    bad_attestation = DocumentaryTotalsAttestation(
        source_content_hash=source_hash,
        values_digest="a" * 64,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        verified_at=datetime(2026, 8, 3, tzinfo=UTC),
    )
    with pytest.raises(SnapshotError, match="does not match the values"):
        materialize(
            manifest,
            release,
            documentary_totals_attestations=(bad_attestation,),
        )

    attestation = DocumentaryTotalsAttestation(
        source_content_hash=source_hash,
        values_digest=digest,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        verified_at=datetime(2026, 8, 3, tzinfo=UTC),
    )
    artifact = materialize(
        manifest,
        release,
        documentary_totals_attestations=(attestation,),
    )
    assert artifact.snapshot["summary"]["provenance"]["source_type"] == "final_declaration"
    assert b"reviewer-a" not in artifact.canonical_bytes
    assert b"reviewer-b" not in artifact.canonical_bytes
    assert "documentary_totals_attestation" not in artifact.snapshot


def test_materializer_detaches_output_from_mutable_inputs() -> None:
    manifest, release = release_inputs()
    artifact = materialize(manifest, release)
    release["summary"]["voters"]["value"] = 0
    manifest["datasets"][0]["url"] = "https://mutated.example.test/data.json"
    assert artifact.snapshot["summary"]["voters"]["value"] == 1200
    assert "mutated.example.test" not in artifact.canonical_bytes.decode("utf-8")
