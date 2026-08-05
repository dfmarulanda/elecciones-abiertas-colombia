from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.outcome_sensitivity import (
    METHODOLOGY_VERSION,
    AffectedVoteVerification,
    BoundBasis,
    EvidenceBasis,
    GeographicScope,
    OutcomeObservation,
    SensitivityStatus,
    SourceFactArtifact,
    SourceFactScope,
    UnresolvedRecordBound,
    VerifiedAffectedRecord,
    _canonical_coverage_ids,
    fact_set_hash,
    margin_shift_certificate,
)
from elecciones_pipeline.analytics.outcome_sensitivity import (
    analyze_outcome_sensitivity as _analyze_outcome_sensitivity,
)

OUTCOME_SOURCE = SourceFactScope("precount", "mesa")
COMPARISON_SOURCE = SourceFactScope("e14", "mesa")
OUTCOME_LINK = "https://official.example/precount.json"
EVIDENCE_LINK = "https://official.example/e14.pdf"
MESA = GeographicScope("mesa", ("D", "M", "P", "1"))
SECOND_MESA = GeographicScope("mesa", ("D", "M", "P", "2"))
MUNICIPALITY = GeographicScope("municipality", ("D", "M"))
REVIEWERS = {
    "reviewer-a": hashlib.sha256(b"reviewer-a-key").hexdigest(),
    "reviewer-b": hashlib.sha256(b"reviewer-b-key").hexdigest(),
}


def _fact(
    fact_ids: tuple[str, ...],
    *,
    scope: GeographicScope,
    source: SourceFactScope,
    values: dict[str, int],
    links: tuple[str, ...],
    expected: int = 1,
    retrieved: int = 1,
    parsed: int = 1,
    missing: int = 0,
    ambiguous: int = 0,
    excluded: int = 0,
    exact_rollup: bool = True,
    release_id: str = "release-unspecified",
    election_slug: str = "presidencia-2026-r2",
) -> SourceFactArtifact:
    source_hash = hashlib.sha256(
        json.dumps(
            {
                "fact_ids": sorted(fact_ids),
                "source": source.source_id,
                "values": values,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return SourceFactArtifact(
        fact_ids=tuple(sorted(fact_ids)),
        release_id=release_id,
        election_slug=election_slug,
        scope=scope,
        source=source,
        values=values,
        source_links=links,
        source_content_hash=source_hash,
        ballot_universe="presidencia-2026-r2-ballots",
        expected=expected,
        retrieved=retrieved,
        parsed=parsed,
        missing=missing,
        ambiguous=ambiguous,
        excluded=excluded,
        exact_rollup=exact_rollup,
    ).with_hash()


def analyze_outcome_sensitivity(
    observation: OutcomeObservation | None,
    *,
    verified_affected_records: object,
    unresolved_record_bounds: object,
    trusted_fact_hashes: object = None,
    reviewer_registry: object = None,
    trusted_review_hashes: object = None,
):
    verified = (
        None if verified_affected_records is None else tuple(verified_affected_records)  # type: ignore[arg-type]
    )
    unresolved = (
        None if unresolved_record_bounds is None else tuple(unresolved_record_bounds)  # type: ignore[arg-type]
    )
    facts: list[SourceFactArtifact] = []
    if observation is not None:
        facts.extend(observation.fact_artifacts)
    for record in verified or ():
        facts.extend(record.outcome_fact_artifacts)
        facts.extend(record.comparison_fact_artifacts)
    for record in unresolved or ():
        facts.extend(record.outcome_fact_artifacts)
        facts.extend(record.bounded_fact_artifacts)
    trusted = (
        {fact.artifact_hash for fact in facts}
        if trusted_fact_hashes is None
        else trusted_fact_hashes
    )
    registry = REVIEWERS if reviewer_registry is None else reviewer_registry
    trusted_reviews = (
        {
            review.review_artifact_hash
            for record in verified or ()
            for review in record.verifications
        }
        if trusted_review_hashes is None
        else trusted_review_hashes
    )
    return _analyze_outcome_sensitivity(
        observation,
        verified_affected_records=verified,
        unresolved_record_bounds=unresolved,
        trusted_fact_hashes=trusted,  # type: ignore[arg-type]
        reviewer_registry=registry,  # type: ignore[arg-type]
        trusted_review_hashes=trusted_reviews,  # type: ignore[arg-type]
    )


def _observation(
    *,
    scope: GeographicScope = MESA,
    source: SourceFactScope = OUTCOME_SOURCE,
    votes: dict[str, int] | None = None,
    links: tuple[str, ...] = (OUTCOME_LINK,),
) -> OutcomeObservation:
    candidate_votes = votes or {"leader": 100, "runner": 90}
    fact = _fact(
        ("observed-total",),
        scope=scope,
        source=source,
        values=candidate_votes,
        links=links,
    )
    return OutcomeObservation(
        scope,
        source,
        candidate_votes,
        links,
        source_fact_ids=("observed-total",),
        fact_artifacts=(fact,),
    )


def _verified(
    record_id: str = "verified-1",
    *,
    coverage_ids: tuple[str, ...] | None = None,
    scope: GeographicScope = MESA,
    affected: int = 2,
    shift: int = 4,
    basis: EvidenceBasis | str = EvidenceBasis.DOCUMENTARY_COMPARISON,
    outcome_source: SourceFactScope = OUTCOME_SOURCE,
    comparison_source: SourceFactScope | None = COMPARISON_SOURCE,
    verifications: tuple[AffectedVoteVerification, ...] | None = None,
    links: tuple[str, ...] = (EVIDENCE_LINK,),
) -> VerifiedAffectedRecord:
    ids = tuple(sorted(coverage_ids if coverage_ids is not None else (record_id,)))
    outcome_fact = _fact(
        ids,
        scope=scope,
        source=outcome_source,
        values={"affected_votes": affected},
        links=(OUTCOME_LINK,),
    )
    comparison_facts: tuple[SourceFactArtifact, ...] = ()
    if comparison_source is not None:
        comparison_fact = _fact(
            ids,
            scope=scope,
            source=comparison_source,
            values={"affected_votes": affected, "max_margin_shift_votes": shift},
            links=links,
        )
        comparison_facts = (comparison_fact,)
    facts = (outcome_fact, *comparison_facts)
    fact_hashes = tuple(sorted(fact.artifact_hash for fact in facts))
    certificate = (
        margin_shift_certificate(
            record_id=record_id,
            fact_artifact_hashes=fact_hashes,
            affected_votes=affected,
            max_margin_shift_votes=shift,
        )
        if shift < 2 * affected
        else None
    )
    agreed = verifications or tuple(
        AffectedVoteVerification(
            verifier_id,
            affected,
            shift,
            record_id,
            fact_hashes,
            REVIEWERS[verifier_id],
            certificate,
        ).with_hash()
        for verifier_id in ("reviewer-a", "reviewer-b")
    )
    return VerifiedAffectedRecord(
        record_id,
        ids,
        scope,
        outcome_source,
        comparison_source,
        basis,
        agreed,
        links,
        (outcome_fact,),
        comparison_facts,
    )


def _unresolved(
    record_id: str = "unresolved-1",
    *,
    coverage_ids: tuple[str, ...] | None = None,
    scope: GeographicScope = MESA,
    affected: int | None = 1,
    shift: int | None = 2,
    outcome_source: SourceFactScope = OUTCOME_SOURCE,
    bounded_source: SourceFactScope = COMPARISON_SOURCE,
    basis: BoundBasis | str | None = BoundBasis.REGISTERED_ELECTORS,
    links: tuple[str, ...] = (EVIDENCE_LINK,),
) -> UnresolvedRecordBound:
    ids = tuple(sorted(coverage_ids if coverage_ids is not None else (record_id,)))
    outcome_fact = _fact(
        ids,
        scope=scope,
        source=outcome_source,
        values={"record_present": 1},
        links=(OUTCOME_LINK,),
    )
    bound_values = {"registered_electors": 0 if affected is None else affected}
    effective_shift = None if affected is None else (2 * affected if shift is None else shift)
    if affected is not None and effective_shift is not None and effective_shift < 2 * affected:
        bound_values.update(
            {
                "affected_votes": affected,
                "max_margin_shift_votes": effective_shift,
            }
        )
    bounded_fact = _fact(
        ids,
        scope=scope,
        source=bounded_source,
        values=bound_values,
        links=links,
    )
    bounded_hashes = (bounded_fact.artifact_hash,)
    certificate = (
        margin_shift_certificate(
            record_id=record_id,
            fact_artifact_hashes=bounded_hashes,
            affected_votes=affected,
            max_margin_shift_votes=effective_shift,
        )
        if affected is not None and effective_shift is not None and effective_shift < 2 * affected
        else None
    )
    return UnresolvedRecordBound(
        record_id=record_id,
        coverage_ids=ids,
        scope=scope,
        outcome_source=outcome_source,
        bounded_source=bounded_source,
        affected_vote_upper_bound=affected,
        max_margin_shift_upper_bound=shift,
        bound_basis=basis,
        source_links=links,
        source_observed_field="registered_electors",
        source_observed_value=affected,
        source_observed_hash=fact_set_hash(bounded_hashes),
        methodology_version=METHODOLOGY_VERSION,
        source_fact_ids=ids,
        margin_shift_certificate=certificate,
        outcome_fact_artifacts=(outcome_fact,),
        bounded_fact_artifacts=(bounded_fact,),
    )


def test_robust_result_reports_separate_affected_vote_and_margin_shift_totals() -> None:
    result = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=(_verified(),),
        unresolved_record_bounds=(_unresolved(scope=SECOND_MESA),),
    )
    assert result.status == SensitivityStatus.ROBUST_WITHIN_EVALUATED_BOUNDS
    assert result.evaluable
    assert result.observed_margin_votes == 10
    assert result.verified_affected_votes == 2
    assert result.verified_margin_shift_bound == 4
    assert result.unresolved_affected_vote_upper_bound == 1
    assert result.unresolved_margin_shift_upper_bound == 2
    assert result.combined_affected_vote_upper_bound == 3
    assert result.combined_margin_shift_upper_bound == 6
    assert result.verified_margin_headroom == 6
    assert result.combined_margin_headroom == 4
    assert result.tie_possible_including_unresolved is False
    assert result.lead_change_possible_including_unresolved is False
    assert result.source_links == (EVIDENCE_LINK, OUTCOME_LINK)


@pytest.mark.parametrize(
    ("verified_shift", "unresolved_shift", "expected"),
    (
        (4, 0, SensitivityStatus.TIE_WITHIN_VERIFIED_BOUND),
        (5, 0, SensitivityStatus.LEAD_CHANGE_WITHIN_VERIFIED_BOUND),
        (2, 2, SensitivityStatus.TIE_ONLY_WITH_UNRESOLVED_BOUND),
        (2, 3, SensitivityStatus.LEAD_CHANGE_ONLY_WITH_UNRESOLVED_BOUND),
        (1, 1, SensitivityStatus.ROBUST_WITHIN_EVALUATED_BOUNDS),
    ),
)
def test_tie_and_lead_change_boundaries_are_not_conflated(
    verified_shift: int,
    unresolved_shift: int,
    expected: SensitivityStatus,
) -> None:
    observation = _observation(scope=MUNICIPALITY, votes={"leader": 10, "runner": 6})
    verified = _verified(affected=3, shift=verified_shift)
    unresolved = (
        ()
        if unresolved_shift == 0
        else (_unresolved(scope=SECOND_MESA, affected=2, shift=unresolved_shift),)
    )
    result = analyze_outcome_sensitivity(
        observation,
        verified_affected_records=(verified,),
        unresolved_record_bounds=unresolved,
    )
    assert result.status == expected
    assert result.tie_possible_from_verified is (verified_shift >= 4)
    assert result.lead_change_possible_from_verified is (verified_shift > 4)
    assert result.tie_possible_including_unresolved is (verified_shift + unresolved_shift >= 4)
    assert result.lead_change_possible_including_unresolved is (
        verified_shift + unresolved_shift > 4
    )


def test_empty_assessment_and_none_are_not_evaluable() -> None:
    assessed = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert not assessed.evaluable
    assert assessed.reason_codes == ("outcome_assessment_empty",)

    unassessed = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=None,
        unresolved_record_bounds=None,
    )
    assert unassessed.status == SensitivityStatus.NOT_EVALUABLE
    assert set(unassessed.reason_codes) == {
        "verified_affected_records_unassessed",
        "unresolved_records_unassessed",
    }
    assert unassessed.verified_affected_votes is None
    assert unassessed.combined_margin_shift_upper_bound is None


def test_missing_observation_votes_and_tied_outcome_abstain() -> None:
    missing = analyze_outcome_sensitivity(
        None,
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert missing.status == SensitivityStatus.NOT_EVALUABLE
    assert "observation_missing" in missing.reason_codes

    missing_votes = analyze_outcome_sensitivity(
        OutcomeObservation(MESA, OUTCOME_SOURCE, None, (OUTCOME_LINK,)),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert "candidate_votes_missing" in missing_votes.reason_codes

    tied = analyze_outcome_sensitivity(
        _observation(votes={"candidate-b": 10, "candidate-a": 10}),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert tied.status == SensitivityStatus.NOT_EVALUABLE
    assert "observed_result_has_no_unique_leader" in tied.reason_codes
    assert tied.observed_margin_votes == 0


def test_municipality_accepts_disjoint_descendant_mesas_and_is_deterministic() -> None:
    mesa_one = GeographicScope("mesa", ("D", "M", "P", "1"))
    mesa_two = GeographicScope("mesa", ("D", "M", "P", "2"))
    mesa_three = GeographicScope("mesa", ("D", "M", "Q", "1"))
    records = (
        _verified("z-record", scope=mesa_two, affected=1, shift=1),
        _verified("a-record", scope=mesa_one, affected=2, shift=3),
    )
    unresolved = (_unresolved("u-record", scope=mesa_three, affected=2, shift=2),)
    first = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=records,
        unresolved_record_bounds=unresolved,
    )
    second = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=reversed(records),
        unresolved_record_bounds=unresolved,
    )
    assert first == second
    assert first.verified_record_ids == ("a-record", "z-record")
    assert first.verified_affected_votes == 3
    assert first.verified_margin_shift_bound == 4
    assert first.unresolved_affected_vote_upper_bound == 2


def test_outside_geography_and_source_layer_mismatch_are_not_evaluable() -> None:
    outside = _verified(scope=GeographicScope("mesa", ("D", "OTHER", "P", "1")))
    wrong_source = _verified(
        "wrong-source",
        scope=GeographicScope("mesa", ("D", "M", "P", "2")),
        outcome_source=SourceFactScope("scrutiny", "mesa"),
    )
    result = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=(outside, wrong_source),
        unresolved_record_bounds=(),
    )
    assert result.status == SensitivityStatus.NOT_EVALUABLE
    assert "affected_record_outside_geography" in result.reason_codes
    assert "affected_record_outcome_source_mismatch" in result.reason_codes
    assert result.combined_affected_vote_upper_bound is None


def test_coarser_source_fact_is_never_coerced_to_mesa_grain() -> None:
    aggregate_observation = _observation(source=SourceFactScope("scrutiny", "municipality"))
    observation_result = analyze_outcome_sensitivity(
        aggregate_observation,
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert observation_result.status == SensitivityStatus.NOT_EVALUABLE
    assert "outcome_source_grain_incompatible" in observation_result.reason_codes

    coarse_comparison = _verified(comparison_source=SourceFactScope("scrutiny", "municipality"))
    comparison_result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(coarse_comparison,),
        unresolved_record_bounds=(),
    )
    assert comparison_result.status == SensitivityStatus.NOT_EVALUABLE
    assert "affected_record_source_grain_incompatible" in comparison_result.reason_codes


def test_overlapping_or_duplicate_record_coverage_abstains_instead_of_double_counting() -> None:
    municipality_record = _verified(
        "municipality-total", scope=MUNICIPALITY, coverage_ids=("mesa-1", "mesa-2")
    )
    mesa_record = _verified("mesa-detail", scope=MESA, coverage_ids=("mesa-1",))
    overlap = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=(municipality_record, mesa_record),
        unresolved_record_bounds=(),
    )
    assert overlap.status == SensitivityStatus.NOT_EVALUABLE
    assert overlap.reason_codes == ("overlapping_record_coverage",)
    assert overlap.issues[0].record_ids == ("mesa-detail", "municipality-total")

    duplicate = analyze_outcome_sensitivity(
        _observation(scope=MUNICIPALITY),
        verified_affected_records=(_verified("same", scope=MESA),),
        unresolved_record_bounds=(_unresolved("same", scope=MESA),),
    )
    assert "duplicate_record_id" in duplicate.reason_codes
    assert "overlapping_record_coverage" in duplicate.reason_codes


@pytest.mark.parametrize(
    ("verifications", "reason"),
    (
        (
            (AffectedVoteVerification("reviewer-a", 2, 3),),
            "affected_record_not_independently_verified",
        ),
        (
            (
                AffectedVoteVerification("reviewer-a", 2, 3),
                AffectedVoteVerification("reviewer-a", 2, 3),
            ),
            "affected_record_not_independently_verified",
        ),
        (
            (
                AffectedVoteVerification("reviewer-a", 2, 3),
                AffectedVoteVerification("reviewer-b", 2, 4),
            ),
            "affected_record_verification_disagreement",
        ),
        (
            (
                AffectedVoteVerification("reviewer-a", None, None),
                AffectedVoteVerification("reviewer-b", None, None),
            ),
            "affected_record_verification_value_missing",
        ),
    ),
)
def test_verified_total_requires_two_distinct_agreeing_measurements(
    verifications: tuple[AffectedVoteVerification, ...], reason: str
) -> None:
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(_verified(verifications=verifications),),
        unresolved_record_bounds=(),
    )
    assert result.status == SensitivityStatus.NOT_EVALUABLE
    assert reason in result.reason_codes
    assert result.verified_affected_votes is None


def test_statistical_signal_cannot_be_laundered_into_affected_votes_or_bounds() -> None:
    statistical_record = _verified(basis=EvidenceBasis.STATISTICAL_SIGNAL)
    as_affected = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(statistical_record,),
        unresolved_record_bounds=(),
    )
    assert as_affected.status == SensitivityStatus.NOT_EVALUABLE
    assert as_affected.reason_codes == ("affected_record_basis_is_not_verified_evidence",)
    assert as_affected.verified_affected_votes is None

    statistical_bound = _unresolved(basis=BoundBasis.STATISTICAL_ESTIMATE)
    as_bound = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(statistical_bound,),
    )
    assert as_bound.status == SensitivityStatus.NOT_EVALUABLE
    assert as_bound.reason_codes == ("unresolved_record_statistical_bound",)


def test_unresolved_record_must_have_an_explicit_documentary_bound() -> None:
    missing = _unresolved(affected=None, shift=None, basis=None)
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(missing,),
    )
    assert result.status == SensitivityStatus.NOT_EVALUABLE
    assert {
        "unresolved_record_bound_basis_missing",
        "unresolved_record_bound_missing",
    } <= set(result.reason_codes)
    assert result.unresolved_affected_vote_upper_bound is None


def test_zero_is_not_an_observed_registered_elector_bound_for_an_unresolved_record() -> None:
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(_unresolved(affected=0, shift=0),),
    )
    assert result.status == SensitivityStatus.NOT_EVALUABLE
    assert "unresolved_registered_elector_bound_not_positive" in result.reason_codes


def test_every_input_needs_provenance_links() -> None:
    with pytest.raises(ValueError, match="source fact links"):
        _observation(links=())


def test_a_margin_shift_bound_cannot_exceed_two_votes_per_affected_item() -> None:
    with pytest.raises(ValueError, match="twice"):
        AffectedVoteVerification("reviewer", 2, 5)
    with pytest.raises(ValueError, match="twice"):
        _unresolved(affected=2, shift=5)


def test_release_builder_representation_contains_method_and_nested_scope() -> None:
    result = analyze_outcome_sensitivity(
        _observation(votes={"z": 90, "a": 100, "b": 90}),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    payload = result.as_dict()
    assert result.runner_up_id == "b"
    assert payload["status"] == "not_evaluable"
    assert payload["scope"] == {"level": "mesa", "key": ("D", "M", "P", "1")}
    assert payload["methodology_version"] == "outcome-sensitivity-v3.0.0"
    assert json.loads(json.dumps(payload, sort_keys=True))["status"] == result.status
    assert all("fraud" not in status.value for status in SensitivityStatus)


def test_incomplete_coverage_zero_bounds_and_forged_scope_ids_fail_closed() -> None:
    incomplete = OutcomeObservation(
        MESA,
        OUTCOME_SOURCE,
        {"leader": 100, "runner": 90},
        (OUTCOME_LINK,),
        expected=100,
        retrieved=1,
        parsed=1,
    )
    result = analyze_outcome_sensitivity(
        incomplete,
        verified_affected_records=(_verified(),),
        unresolved_record_bounds=(),
    )
    assert "outcome_coverage_incomplete_or_ambiguous" in result.reason_codes
    for basis in (
        BoundBasis.REGISTERED_ELECTORS,
        BoundBasis.REPORTED_BALLOTS,
        BoundBasis.DOCUMENTED_RECORD_LIMIT,
    ):
        zero = analyze_outcome_sensitivity(
            _observation(),
            verified_affected_records=(),
            unresolved_record_bounds=(_unresolved(affected=0, shift=0, basis=basis),),
        )
        assert "unresolved_record_bound_not_positive" in zero.reason_codes
    with pytest.raises(ValueError, match="certificate"):
        _unresolved(affected=100, shift=0, record_id="forged").__class__(
            "forged",
            ("same",),
            MESA,
            OUTCOME_SOURCE,
            COMPARISON_SOURCE,
            100,
            0,
            BoundBasis.REGISTERED_ELECTORS,
            (EVIDENCE_LINK,),
            "registered_electors",
            100,
            "a" * 64,
            True,
            "outcome-sensitivity-v2.0.0",
            ("same",),
            None,
        )


def test_contextual_sources_and_unallowlisted_elections_are_never_analyzed() -> None:
    contextual_source = SourceFactScope("history", "mesa", "contextual_baseline", "context_only")
    contextual = analyze_outcome_sensitivity(
        OutcomeObservation(
            MESA,
            contextual_source,
            {"leader": 100, "runner": 90},
            (OUTCOME_LINK,),
        ),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert "contextual_source_ineligible" in contextual.reason_codes

    wrong_election = analyze_outcome_sensitivity(
        OutcomeObservation(
            MESA,
            OUTCOME_SOURCE,
            {"leader": 100, "runner": 90},
            (OUTCOME_LINK,),
            election_slug="presidencia-2022-historical-context",
        ),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert "election_round_not_allowlisted" in wrong_election.reason_codes


def test_source_facts_and_reviews_require_external_trust_and_exact_content_hashes() -> None:
    observation = _observation()
    untrusted = _analyze_outcome_sensitivity(
        observation,
        verified_affected_records=(),
        unresolved_record_bounds=(),
        trusted_fact_hashes=(),
        reviewer_registry=REVIEWERS,
    )
    assert "source_fact_artifact_untrusted" in untrusted.reason_codes

    fact = observation.fact_artifacts[0]
    tampered_fact = replace(fact, values={"leader": 101, "runner": 90})
    tampered = analyze_outcome_sensitivity(
        replace(observation, fact_artifacts=(tampered_fact,)),
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert "source_fact_artifact_hash_invalid" in tampered.reason_codes

    record = _verified()
    forged_review = replace(record.verifications[0], verifier_id="reviewer-attacker").with_hash()
    forged = analyze_outcome_sensitivity(
        observation,
        verified_affected_records=(
            replace(
                record,
                verifications=(forged_review, record.verifications[1]),
            ),
        ),
        unresolved_record_bounds=(),
    )
    assert "affected_record_review_authentication_invalid" in forged.reason_codes

    authorized_forgery = replace(
        record.verifications[0], affected_votes=3, max_margin_shift_votes=6
    ).with_hash()
    rejected = _analyze_outcome_sensitivity(
        observation,
        verified_affected_records=(
            replace(
                record,
                verifications=(authorized_forgery, record.verifications[1]),
            ),
        ),
        unresolved_record_bounds=(),
        trusted_fact_hashes={
            fact.artifact_hash
            for fact in (
                *observation.fact_artifacts,
                *record.outcome_fact_artifacts,
                *record.comparison_fact_artifacts,
            )
        },
        reviewer_registry=REVIEWERS,
        trusted_review_hashes={review.review_artifact_hash for review in record.verifications},
    )
    assert "affected_record_review_authentication_invalid" in rejected.reason_codes


def test_default_margin_shift_is_two_times_affected_and_smaller_bounds_need_fact_support() -> None:
    assert AffectedVoteVerification("reviewer-a", 3).max_margin_shift_votes == 6
    defaulted = _unresolved(affected=3, shift=None)
    assert defaulted.max_margin_shift_upper_bound == 6
    evaluated = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(defaulted,),
    )
    assert evaluated.evaluable
    assert evaluated.unresolved_margin_shift_upper_bound == 6

    bounded = _unresolved(record_id="smaller", affected=4, shift=3)
    original_fact = bounded.bounded_fact_artifacts[0]
    unsupported_fact = replace(
        original_fact,
        values={"registered_electors": 4, "affected_votes": 4},
        artifact_hash="",
    ).with_hash()
    unsupported_hashes = (unsupported_fact.artifact_hash,)
    forged = replace(
        bounded,
        bounded_fact_artifacts=(unsupported_fact,),
        source_observed_hash=fact_set_hash(unsupported_hashes),
        margin_shift_certificate=margin_shift_certificate(
            record_id="smaller",
            fact_artifact_hashes=unsupported_hashes,
            affected_votes=4,
            max_margin_shift_votes=3,
        ),
    )
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(forged,),
    )
    assert "unresolved_margin_shift_certificate_invalid" in result.reason_codes


def test_fact_coverage_and_geographic_overlap_use_authenticated_atoms() -> None:
    observation = _observation()
    incomplete_fact = replace(
        observation.fact_artifacts[0], retrieved=0, artifact_hash=""
    ).with_hash()
    incomplete = replace(observation, fact_artifacts=(incomplete_fact,))
    result = analyze_outcome_sensitivity(
        incomplete,
        verified_affected_records=(),
        unresolved_record_bounds=(_unresolved(),),
    )
    assert "source_fact_coverage_incomplete_or_ambiguous" in result.reason_codes

    # Different fact IDs do not prove that same-mesa records cover disjoint ballots.
    same_mesa = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(_verified("one"), _verified("two")),
        unresolved_record_bounds=(),
    )
    assert "overlapping_record_coverage" in same_mesa.reason_codes
    missing_universe = replace(
        _verified().outcome_fact_artifacts[0], ballot_universe="", artifact_hash=""
    ).with_hash()
    unproven = _verified()
    unproven = replace(unproven, outcome_fact_artifacts=(missing_universe,))
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(unproven,),
        unresolved_record_bounds=(),
    )
    assert "source_fact_ballot_universe_missing" in result.reason_codes

    municipal_fact = _fact(
        ("municipal-total",),
        scope=MUNICIPALITY,
        source=OUTCOME_SOURCE,
        values={"leader": 100, "runner": 90},
        links=(OUTCOME_LINK,),
        exact_rollup=False,
    )
    municipal_observation = OutcomeObservation(
        MUNICIPALITY,
        OUTCOME_SOURCE,
        {"leader": 100, "runner": 90},
        (OUTCOME_LINK,),
        source_fact_ids=("municipal-total",),
        fact_artifacts=(municipal_fact,),
    )
    result = analyze_outcome_sensitivity(
        municipal_observation,
        verified_affected_records=(),
        unresolved_record_bounds=(),
    )
    assert "exact_rollup_unauthenticated" in result.reason_codes


def test_unresolved_fact_ids_cannot_diverge_and_delimiters_cannot_alias_identity() -> None:
    mismatched = replace(_unresolved(), source_fact_ids=("different-fact",))
    result = analyze_outcome_sensitivity(
        _observation(),
        verified_affected_records=(),
        unresolved_record_bounds=(mismatched,),
    )
    assert "unresolved_record_fact_coverage_mismatch" in result.reason_codes

    left = _canonical_coverage_ids(
        release_id="release|part",
        election_slug="election",
        source_id="source",
        fact_ids=("fact",),
    )
    right = _canonical_coverage_ids(
        release_id="release",
        election_slug="part|election",
        source_id="source",
        fact_ids=("fact",),
    )
    assert left.isdisjoint(right)
