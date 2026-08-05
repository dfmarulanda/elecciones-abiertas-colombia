from __future__ import annotations

from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.peer_signals import (
    CODE_HASH,
    METHOD_HASH,
    PeerSignal,
    cohort_digest,
)
from elecciones_pipeline.analytics.priority import (
    METHODOLOGY_VERSION,
    DocumentReviewArtifact,
    _analysis_hash,
    audit_priority,
)
from elecciones_pipeline.analytics.reconciliation import (
    ArithmeticIssue,
    ArithmeticRule,
    MesaIdentity,
    ReconciliationResult,
)
from elecciones_pipeline.analytics.spatial import (
    CODE_HASH as SPATIAL_CODE_HASH,
)
from elecciones_pipeline.analytics.spatial import (
    METHOD_HASH as SPATIAL_METHOD_HASH,
)
from elecciones_pipeline.analytics.spatial import (
    SpatialSignal,
    input_artifact_hash,
    spatial_cohort_digest,
)

LINKS = ("https://official.example/acta",)


def _priority(**kwargs: object):
    peer = kwargs.get("peer_analysis")
    spatial = kwargs.get("spatial_analysis")
    reviews = tuple(kwargs.get("document_review_artifacts", ()))
    if reviews:
        kwargs.setdefault("target_record_id", reviews[0].record_id)
    if peer is not None or spatial is not None:
        kwargs.setdefault("target_mesa_id", (peer or spatial).mesa_id)
    return audit_priority(
        **kwargs,  # type: ignore[arg-type]
        trusted_document_review_hashes=tuple(review.output_hash for review in reviews),
    )


def _review(kind: str, **kwargs: object) -> DocumentReviewArtifact:
    return DocumentReviewArtifact(
        record_id="record-1",
        review_kind=kind,
        source_links=LINKS,
        input_artifact_hashes=("a" * 64,),
        **kwargs,  # type: ignore[arg-type]
    ).with_hash()


def _peer_signal() -> PeerSignal:
    cohort_hash = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version="release-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        expected_family_count=32,
        expected_family_digest="a" * 64,
        input_artifact_hash="c" * 64,
    )
    signal = PeerSignal(
        mesa_id="mesa-1",
        metric="candidate_share",
        candidate_id="candidate-a",
        election_slug="presidencia-2026-r2",
        data_version="release-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        family_id="release-v1|presidencia-2026-r2|pre_count|candidate_share|candidate-a",
        eligible=True,
        public_point_eligible=False,
        signal=True,
        reason=None,
        peer_level="municipality",
        peers=31,
        observed_rate=0.95,
        expected_rate=0.5,
        standardized_residual=5.0,
        effect_pp=45.0,
        tail_probability=0.0001,
        adjusted_q_value=0.01,
        adjustment_method="benjamini-yekutieli",
        family_size=32,
        family_rank=1,
        expected_family_count=32,
        expected_family_digest="a" * 64,
        cohort_hash=cohort_hash,
        input_artifact_hash="c" * 64,
        code_hash=CODE_HASH,
        method_hash=METHOD_HASH,
        fit_method="leave-one-out-marginal-likelihood-mle",
        source_links=LINKS,
    )
    return replace(signal, output_hash=_analysis_hash(signal))


def _spatial_signal() -> SpatialSignal:
    peer_hash = "1" * 64
    coordinate_hash = "2" * 64
    expected_digest = "3" * 64
    membership_digest = "4" * 64
    combined_input_hash = input_artifact_hash(
        peer_residual_artifact_hash=peer_hash,
        coordinate_source_hash=coordinate_hash,
        analysis_unit_digest=expected_digest,
        mesa_membership_digest=membership_digest,
    )
    cohort_hash = spatial_cohort_digest(
        peer_residual_artifact_hash=peer_hash,
        election_slug="presidencia-2026-r2",
        data_version="release-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="turnout",
        candidate_id=None,
        peer_methodology_version="peer-beta-binomial-eb-v5",
        coordinate_source_url="https://official.example/coordinates.json",
        coordinate_source_hash=coordinate_hash,
        coordinate_accuracy_m=10.0,
        coordinate_grain="mesa",
        expected_family_count=100,
        expected_family_digest=expected_digest,
        expected_mesa_count=100,
        expected_mesa_digest=expected_digest,
        expected_mesa_membership_digest=membership_digest,
    )
    signal = SpatialSignal(
        mesa_id="mesa-1",
        analysis_unit_id="mesa-1",
        eligible=True,
        signal=True,
        signal_kind="positive_cluster",
        reason=None,
        neighbors=("mesa-2", "mesa-3", "mesa-4"),
        local_residual=2.0,
        permutation_p_value=0.0001,
        adjusted_q_value=0.01,
        family_id="release-v1|presidencia-2026-r2|pre_count|turnout|none",
        family_size=100,
        family_rank=1,
        adjustment_method="benjamini-yekutieli",
        randomization_seed=7,
        permutations=12_345,
        peer_residual_artifact_hash=peer_hash,
        coordinate_source_url="https://official.example/coordinates.json",
        coordinate_source_hash=coordinate_hash,
        coordinate_accuracy_m=10.0,
        coordinate_grain="mesa",
        input_artifact_hash=combined_input_hash,
        election_slug="presidencia-2026-r2",
        data_version="release-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="turnout",
        candidate_id=None,
        peer_methodology_version="peer-beta-binomial-eb-v5",
        expected_family_count=100,
        expected_family_digest=expected_digest,
        analysis_unit_digest=expected_digest,
        expected_mesa_count=100,
        expected_mesa_digest=expected_digest,
        mesa_membership_digest=membership_digest,
        expected_mesa_membership_digest=membership_digest,
        cohort_hash=cohort_hash,
        code_hash=SPATIAL_CODE_HASH,
        method_hash=SPATIAL_METHOD_HASH,
        observed_value=2.0,
        comparator="12,345 deterministic conditional random-label permutations",
        source_links=LINKS,
    )
    return replace(signal, output_hash=_analysis_hash(signal))


def test_statistical_outputs_are_research_metadata_and_never_score() -> None:
    none = audit_priority()
    assert (none.score, none.tier, none.components) == (0, "no_review_signals", ())
    peer = _peer_signal()
    statistical = _priority(peer_analysis=peer)
    assert (statistical.score, statistical.statistical_points, statistical.tier) == (
        0,
        0,
        "no_review_signals",
    )
    component = statistical.components[0]
    assert component.points == 0
    assert component.affected_votes == 0
    assert component.analyzer_output_hash == peer.output_hash
    assert component.expected_family_count == 32
    assert component.p_value == 0.0001 and component.q_value == 0.01
    assert component.public_point_eligible is False

    spatial = _priority(spatial_analysis=_spatial_signal())
    assert (spatial.score, spatial.statistical_points, spatial.tier) == (
        0,
        0,
        "no_review_signals",
    )
    assert spatial.components[0].points == 0
    assert spatial.components[0].input_artifact_hash == _spatial_signal().input_artifact_hash
    assert spatial.components[0].analyzer_mesa_id == "mesa-1"
    assert spatial.components[0].analysis_unit_id == "mesa-1"
    assert spatial.components[0].coordinate_grain == "mesa"
    assert spatial.components[0].spatial_permutations == 12_345
    assert spatial.components[0].permutations == 12_345
    assert spatial.components[0].randomization_seed == _spatial_signal().randomization_seed
    assert spatial.components[0].spatial_neighbors == _spatial_signal().neighbors
    assert spatial.components[0].public_point_eligible is False

    deterministic = _priority(
        document_review_artifacts=(
            _review("verified_accounting_failure", affected_votes=5, independently_verified=True),
        ),
        peer_analysis=peer,
    )
    assert deterministic.score == 100
    assert deterministic.statistical_points == 0
    assert deterministic.methodology_version == METHODOLOGY_VERSION


def test_raw_statistical_booleans_are_not_an_api() -> None:
    with pytest.raises(ValueError, match="raw priority"):
        audit_priority(peer_signal=True, source_links=LINKS)  # type: ignore[call-arg]


def test_reconciliation_priority_is_scoped_to_one_canonical_mesa() -> None:
    target = MesaIdentity("D", "M", "P", "1")
    other = MesaIdentity("D", "M", "P", "2")
    rule = ArithmeticRule("precount", ("candidate",), "total")
    artifact = ReconciliationResult(
        arithmetic_issues=(
            ArithmeticIssue(target, "precount", rule, 8, 7, LINKS[0]),
            ArithmeticIssue(other, "precount", rule, 9, 7, LINKS[0]),
        ),
        elector_bound_issues=(),
        duplicate_identities={},
        conflicting_identities={},
        completeness={},
        completeness_by_source={},
        aggregates=(),
        comparisons=(),
    ).with_hash()
    result = audit_priority(
        reconciliation_artifacts=(artifact,),
        trusted_reconciliation_hashes=(artifact.output_hash,),
        target_mesa_identity=target,
    )
    assert result.score == 100
    assert len(result.components) == 1
    assert result.components[0].evidence_artifact_hash == artifact.output_hash
    assert result.components[0].evidence_artifact_kind == "reconciliation_result"
    with pytest.raises(ValueError, match="target_mesa_identity"):
        audit_priority(
            reconciliation_artifacts=(artifact,),
            trusted_reconciliation_hashes=(artifact.output_hash,),
        )


def test_documentary_thresholds_and_component_names() -> None:
    assert (
        _priority(
            document_review_artifacts=(
                _review(
                    "documentary_comparison",
                    documentary_difference_votes=4,
                    documentary_difference_pp=1.9,
                ),
            )
        ).score
        == 45
    )
    assert (
        _priority(
            document_review_artifacts=(
                _review(
                    "documentary_comparison",
                    documentary_difference_pp=2,
                    documentary_difference_votes=1,
                ),
            )
        ).score
        == 70
    )
    assert (
        _priority(
            document_review_artifacts=(
                _review(
                    "documentary_comparison",
                    documentary_difference_votes=0,
                    documentary_difference_pp=2,
                    affected_votes=1,
                ),
            )
        ).score
        == 70
    )
    result = _priority(
        document_review_artifacts=(
            _review("documentary_comparison", documentary_difference_votes=1),
            _review("document_coverage", expected_document_status="missing"),
        ),
        peer_analysis=_peer_signal(),
    )
    assert result.score == 45
    assert {component.name for component in result.components} == {
        "documentary_difference_minor",
        "document_coverage_incomplete",
        "peer_distribution",
    }


def test_self_hashed_impossible_statistical_artifacts_cannot_create_points() -> None:
    forged_peer = replace(
        _peer_signal(),
        peers=32,
        code_hash="f" * 64,
        public_point_eligible=True,
        output_hash="",
    )
    forged_peer = replace(forged_peer, output_hash=_analysis_hash(forged_peer))
    peer_result = _priority(peer_analysis=forged_peer)
    assert (peer_result.score, peer_result.statistical_points) == (0, 0)
    assert peer_result.components[0].points == 0

    forged_spatial = replace(
        _spatial_signal(),
        adjustment_method="synchronized-max-t-permutation",
        neighbors=("mesa-2", "mesa-2", "mesa-3"),
        coordinate_source_hash="f" * 64,
        public_point_eligible=False,
        output_hash="",
    )
    forged_spatial = replace(forged_spatial, output_hash=_analysis_hash(forged_spatial))
    spatial_result = _priority(spatial_analysis=forged_spatial)
    assert (spatial_result.score, spatial_result.statistical_points) == (0, 0)
    assert spatial_result.components[0].points == 0
    assert spatial_result.components[0].public_point_eligible is False


def test_current_max_t_research_artifact_fails_closed_without_legacy_by_validation() -> None:
    current = replace(
        _spatial_signal(),
        signal=False,
        research_signal=True,
        adjustment_method="synchronized-max-t-permutation",
        public_point_eligible=False,
        output_hash="",
    )
    current = replace(current, output_hash=_analysis_hash(current))
    result = _priority(spatial_analysis=current)
    assert (result.score, result.statistical_points) == (0, 0)
    assert len(result.components) == 1
    assert result.components[0].adjustment_method == "synchronized-max-t-permutation"
    assert result.components[0].public_point_eligible is False


def test_statistical_metadata_remains_scoped_when_a_target_is_supplied() -> None:
    other_mesa = replace(_spatial_signal(), mesa_id="mesa-other", output_hash="")
    other_mesa = replace(other_mesa, output_hash=_analysis_hash(other_mesa))
    with pytest.raises(ValueError, match="priority target"):
        _priority(peer_analysis=_peer_signal(), spatial_analysis=other_mesa)


def test_public_points_require_replay_capability_not_caller_hash_registries() -> None:
    peer = _peer_signal()
    result = audit_priority(peer_analysis=peer, target_mesa_id=peer.mesa_id)
    assert (result.score, result.statistical_points) == (0, 0)
    with pytest.raises(ValueError, match="raw priority inputs"):
        audit_priority(
            peer_analysis=peer,
            target_mesa_id=peer.mesa_id,
            synthetic_fixture=True,  # type: ignore[call-arg]
        )
    with pytest.raises(ValueError, match="raw priority inputs"):
        audit_priority(
            peer_analysis=peer,
            target_mesa_id=peer.mesa_id,
            trusted_analyzer_hashes=(peer.output_hash,),  # type: ignore[call-arg]
        )
    with pytest.raises(ValueError, match="priority target"):
        audit_priority(peer_analysis=peer, target_mesa_id="other-mesa")
    review = _review("documentary_comparison", documentary_difference_votes=5)
    with pytest.raises(ValueError, match="trust registry"):
        audit_priority(document_review_artifacts=(review,))
    forged = replace(review, output_hash="f" * 64)
    with pytest.raises(ValueError, match="output hash"):
        audit_priority(
            document_review_artifacts=(forged,),
            trusted_document_review_hashes=(forged.output_hash,),
        )
