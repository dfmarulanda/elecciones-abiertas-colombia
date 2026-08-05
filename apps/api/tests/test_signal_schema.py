from __future__ import annotations

import hashlib
import json

import pytest
from elecciones_api.schemas import OutcomeSensitivity, SignalComponent, review_signal_tier
from pydantic import ValidationError


def _statistical_component(**overrides: object) -> dict[str, object]:
    component: dict[str, object] = {
        "component_type": "peer_distribution",
        "points": 10,
        "observed_value": 0.5,
        "comparator": "all frozen gates",
        "calculation": "predictive tail",
        "peer_definition": "leave-one-out peers",
        "limitations": {"es": "Guía experimental.", "en": "Experimental lead."},
        "source_links": ["https://official.example/mesa"],
        "evidence_artifact_hash": None,
        "evidence_artifact_kind": None,
        "analyzer_output_hash": "a" * 64,
        "family_id": "release|presidencia-2026-r2|pre_count|turnout|none",
        "expected_family_count": 100,
        "expected_family_digest": "b" * 64,
        "cohort_hash": "c" * 64,
        "input_artifact_hash": "d" * 64,
        "code_hash": "e" * 64,
        "method_hash": "f" * 64,
        "p_value": 0.001,
        "q_value": 0.01,
        "family_rank": 1,
        "family_size": 100,
        "adjustment_method": "benjamini-yekutieli",
    }
    component.update(overrides)
    return component


def test_optional_analyzer_provenance_is_backward_compatible_and_complete() -> None:
    legacy_peer = SignalComponent.model_validate(_statistical_component())
    assert legacy_peer.analyzer_mesa_id is None

    spatial = _statistical_component(
        component_type="spatial_cluster",
        analyzer_mesa_id="mesa-1",
        analysis_unit_id="mesa-1",
        peer_residual_artifact_hash="1" * 64,
        peer_methodology_version="peer-beta-binomial-eb-v3",
        coordinate_source_url="https://official.example/coordinates",
        coordinate_source_hash="2" * 64,
        coordinate_accuracy_m=10.0,
        coordinate_grain="mesa",
        neighbors=("mesa-2", "mesa-3"),
        signal_kind="positive_cluster",
        local_statistic=1.25,
        local_residual=2.5,
        randomization_seed=7,
        spatial_permutations=9999,
        public_point_eligible=True,
        analyzer_reason=None,
        analysis_unit_digest="3" * 64,
        expected_mesa_count=100,
        expected_mesa_digest="4" * 64,
        mesa_membership_digest="5" * 64,
        expected_mesa_membership_digest="6" * 64,
        methodology_version="spatial-local-randomization-v1",
    )
    materialized_spatial = SignalComponent.model_validate(spatial)
    assert materialized_spatial.coordinate_grain == "mesa"
    assert materialized_spatial.analysis.kind == "spatial_cluster"
    assert materialized_spatial.analysis.permutations.value == 9999
    assert materialized_spatial.analysis.expected_mesa_count.value == 100

    spatial.pop("coordinate_source_hash")
    with pytest.raises(ValidationError, match="geocode_source_hash"):
        SignalComponent.model_validate(spatial)

    with pytest.raises(ValidationError):
        SignalComponent.model_validate(_statistical_component(p_value=0.01))
    with pytest.raises(ValidationError, match="expected family coverage"):
        SignalComponent.model_validate(_statistical_component(family_size=101))


def test_pipeline_peer_fields_are_materialized_without_float_counts() -> None:
    component = SignalComponent.model_validate(
        _statistical_component(
            observed_rate=0.5,
            expected_rate=0.4,
            peers=30,
            standardized_residual=3.7,
            effect_pp=10.0,
            fit_method="beta-binomial-mle",
            public_point_eligible=True,
            analyzer_reason=None,
            methodology_version="peer-beta-binomial-eb-v3",
        )
    )
    assert component.analysis.kind == "peer_distribution"
    assert component.analysis.peer_count.value == 30
    assert component.analysis.expected_rate.value == 0.4
    assert component.analysis.analyzer_methodology_version == "peer-beta-binomial-eb-v3"
    with pytest.raises(ValidationError, match="integer"):
        SignalComponent.model_validate(
            _statistical_component(peers=30.5, methodology_version="peer-v3")
        )


def test_outcome_contract_keeps_zero_distinct_from_unknown_without_signal_claims() -> None:
    artifact: dict[str, object] = {
        "status": "tie_within_verified_bound",
        "evaluable": True,
        "issues": [],
        "scope": {"level": "national", "key": ["CO"]},
        "outcome_source": {
            "source_id": "scrutiny-total",
            "fact_grain": "national",
            "source_type": "scrutiny",
            "legal_status": "official_scrutiny",
        },
        "leader_id": "a",
        "runner_up_id": "b",
        "leader_votes": 0,
        "runner_up_votes": 0,
        "observed_margin_votes": 0,
        "verified_record_ids": [],
        "unresolved_record_ids": [],
        "verified_affected_votes": 0,
        "verified_margin_shift_bound": 0,
        "unresolved_affected_vote_upper_bound": 0,
        "unresolved_margin_shift_upper_bound": 0,
        "combined_affected_vote_upper_bound": 0,
        "combined_margin_shift_upper_bound": 0,
        "verified_margin_headroom": 0,
        "combined_margin_headroom": 0,
        "tie_possible_from_verified": True,
        "lead_change_possible_from_verified": False,
        "tie_possible_including_unresolved": True,
        "lead_change_possible_including_unresolved": False,
        "source_links": ["https://official.example/source"],
        "evidence_hash": "a" * 64,
        "methodology_version": "outcome-sensitivity-v3.0.0",
        "calculation": "authenticated bounds compared with the observed margin",
        "limitations": ["This context excludes statistical screening signals."],
    }
    artifact["output_hash"] = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    outcome = OutcomeSensitivity.model_validate(
        {
            **artifact,
            "release_id": "release-1",
            "election_slug": "election-1",
            "data_version": "release-1",
            "margin_shift_factor": 2,
        }
    )
    assert outcome.verified_affected_votes == 0
    assert outcome.margin_shift_factor == 2
    assert "fraud probability" not in outcome.model_dump_json().lower()
    with pytest.raises(ValidationError):
        OutcomeSensitivity.model_validate(
            {**outcome.model_dump(mode="json"), "data_version": "other"}
        )
    with pytest.raises(ValidationError, match="output_hash"):
        OutcomeSensitivity.model_validate(
            {**outcome.model_dump(mode="json"), "verified_affected_votes": 1}
        )


def test_review_signal_tier_boundaries_are_frozen() -> None:
    assert review_signal_tier(0) == "no_review_signals"
    assert review_signal_tier(14) == "no_review_signals"
    assert review_signal_tier(15) == "statistical_or_coverage_issue"
