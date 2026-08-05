from __future__ import annotations

import importlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

import pytest
from elecciones_pipeline.analytics.fingerprints import derive_analyzer_fingerprint
from elecciones_pipeline.analytics.hierarchical_reference import (
    BinomialPeerObservation,
    HierarchicalBetaBinomialReference,
    beta_binomial_variance,
)
from elecciones_pipeline.analytics.peer_signals import (
    ARTIFACT_SCHEMA_VERSION,
    CODE_HASH,
    HIERARCHICAL_REFERENCE_CODE_HASH,
    HIERARCHICAL_REFERENCE_METHOD_HASH,
    METHOD_HASH,
    MesaMetrics,
    cohort_digest,
    family_digest,
    hierarchical_peer_signals_research_preview,
    peer_signal_batches,
    peer_signals,
)

HASH = "a" * 64


def test_analyzer_fingerprint_binds_source_lock_schema_and_advertised_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "analyzer.py"
    helper = tmp_path / "helper.py"
    lock = tmp_path / "uv.lock"
    source.write_text("def analyze() -> int: return 1\n")
    helper.write_text("def helper() -> int: return 1\n")
    lock.write_text("lock-version = 1\n")
    args = {
        "analyzer": "test-analyzer",
        "artifact_schema_version": "schema-v1",
        "source_files": (source, helper),
        "components": {"artifact": "TestOutput", "numerics": "numpy-scipy"},
        "lock_file": lock,
        "runtime": {"implementation": "cpython", "python": "3.13.0"},
    }
    baseline = derive_analyzer_fingerprint(**args)
    assert baseline == derive_analyzer_fingerprint(**args)
    source.write_text("def analyze() -> int: return 2\n")
    assert derive_analyzer_fingerprint(**args) != baseline
    source.write_text("def analyze() -> int: return 1\n")
    lock.write_text("lock-version = 2\n")
    assert derive_analyzer_fingerprint(**args) != baseline
    lock.write_text("lock-version = 1\n")
    assert (
        derive_analyzer_fingerprint(**{**args, "artifact_schema_version": "schema-v2"}) != baseline
    )

    peer_module = importlib.import_module("elecciones_pipeline.analytics.peer_signals")
    sources = (Path(peer_module.__file__), Path(peer_module.__file__).with_name("fingerprints.py"))
    assert (
        derive_analyzer_fingerprint(
            analyzer="peer_signals",
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            source_files=sources,
            components={
                "adjustment": "benjamini-yekutieli",
                "artifact": "PeerSignal",
                "fit": "leave-one-out-beta-binomial-mle",
                "numerics": "numpy-scipy",
            },
        )
        == CODE_HASH
    )
    assert (
        derive_analyzer_fingerprint(
            analyzer="peer_signals",
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            source_files=sources,
            components={
                "adjustment": "benjamini-yekutieli",
                "decision_rule": "p001-q05-z35-effect8-or3",
                "fit": "leave-one-out-beta-binomial-mle",
                "numerics": "numpy-scipy",
            },
        )
        == METHOD_HASH
    )
    assert all(
        item.code_hash == CODE_HASH and item.method_hash == METHOD_HASH
        for item in peer_signals(_rows(32))
    )


def _rows(
    count: int,
    *,
    metric: str = "candidate_share",
    candidate: str | None = "candidate-a",
    votes: int = 50,
) -> list[MesaMetrics]:
    identifiers = [f"mesa-{index}" for index in range(count)]
    digest = family_digest(identifiers)
    input_hash = HASH
    cohort_hash = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version="release-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric=metric,  # type: ignore[arg-type]
        candidate_id=candidate if metric == "candidate_share" else None,
        expected_family_count=count,
        expected_family_digest=digest,
        input_artifact_hash=input_hash,
    )
    return [
        MesaMetrics(
            mesa_id=identifier,
            place_id="place",
            municipality_id="municipality",
            department_id="department",
            metric=metric,  # type: ignore[arg-type]
            registered=100,
            ballots=100,
            candidate_votes=votes if metric == "candidate_share" else 0,
            valid_votes=100,
            blank_votes=0,
            null_unmarked_votes=0,
            candidate_id=candidate if metric == "candidate_share" else None,
            election_slug="presidencia-2026-r2",
            data_version="release-v1",
            source_layer="pre_count",
            source_type="pre_count",
            legal_status="preliminary",
            expected_family_count=count,
            expected_family_digest=digest,
            input_artifact_hash=input_hash,
            cohort_hash=cohort_hash,
            source_links=("https://official.example/results",),
            candidate_total_votes=100,
            denominator_provenance="joined_official",
        )
        for identifier in identifiers
    ]


def test_complete_candidate_family_has_canonical_hashes_and_by_metadata() -> None:
    rows = _rows(32)
    rows[-1] = replace(rows[-1], candidate_votes=95)
    results = peer_signals(rows)
    assert len(results) == 32
    assert all(item.family_size == 32 for item in results)
    assert all(item.family_rank is not None for item in results)
    assert all(item.adjustment_method == "benjamini-yekutieli" for item in results)
    assert all(len(item.output_hash) == 64 for item in results)
    assert all(item.expected_family_digest == rows[0].expected_family_digest for item in results)
    assert all(
        item.source_type == "pre_count" and item.legal_status == "preliminary" for item in results
    )
    assert all(
        item.family_ledger_status == "external_registry_required_unverified"
        and not item.public_point_eligible
        for item in results
    )


def test_family_subset_extra_duplicate_and_noncandidate_fragmentation_fail_closed() -> None:
    complete = _rows(32)
    with pytest.raises(ValueError, match="expected ID"):
        peer_signals(complete[:31])
    with pytest.raises(ValueError, match="unique"):
        peer_signals([*complete, complete[0]])
    turnout = _rows(32, metric="turnout", candidate=None)
    fragmented = replace(turnout[-1], expected_family_digest="c" * 64)
    with pytest.raises(ValueError, match="fragmented"):
        peer_signals([*turnout[:-1], fragmented])
    with pytest.raises(ValueError, match="noncandidate"):
        replace(turnout[0], candidate_id="candidate-a")


def test_metric_denominator_and_broader_pool_rules() -> None:
    rows = _rows(32)
    rows[-1] = replace(
        rows[-1],
        valid_votes=40,
        candidate_total_votes=40,
        candidate_votes=35,
        ballots=100,
        null_unmarked_votes=60,
    )
    result = next(item for item in peer_signals(rows) if item.mesa_id == rows[-1].mesa_id)
    assert not result.eligible and result.reason == "metric_denominator_below_80"

    rows = _rows(32, votes=10)
    for index in range(10):
        rows[index] = replace(rows[index], place_id="target-place", candidate_votes=90)
    rows[9] = replace(rows[9], mesa_id=rows[9].mesa_id)
    target = next(item for item in peer_signals(rows) if item.mesa_id == rows[9].mesa_id)
    assert target.peer_level == "municipality"
    assert not target.signal


def test_contextual_and_impossible_counts_are_rejected() -> None:
    row = _rows(1)[0]
    with pytest.raises(ValueError, match="contextual"):
        replace(row, source_type="contextual_baseline", legal_status="context_only")
    with pytest.raises(ValueError, match="valid votes"):
        replace(row, ballots=100, valid_votes=200)
    with pytest.raises(ValueError, match="allowlisted"):
        replace(row, election_slug="presidencia-2022-history")
    with pytest.raises(ValueError, match="incompatible"):
        replace(row, legal_status="official_scrutiny")
    with pytest.raises(ValueError, match="canonical source_type"):
        replace(row, source_layer="scrutiny")
    with pytest.raises(ValueError, match="metric is invalid"):
        replace(row, metric="invented_metric")  # type: ignore[arg-type]


def test_complete_ballot_vectors_are_accounted_and_incomplete_vectors_abstain() -> None:
    row = _rows(1)[0]
    with pytest.raises(ValueError, match="complete vectors require"):
        replace(row, candidate_total_votes=99)
    with pytest.raises(ValueError, match="ballots = valid votes"):
        replace(row, null_unmarked_votes=1)
    with pytest.raises(ValueError, match="focal candidate"):
        replace(row, candidate_total_votes=49)
    incomplete = replace(row, candidate_total_votes=None, denominator_provenance="unavailable")
    results = peer_signals([replace(incomplete, expected_family_count=1)])
    assert results[0].reason == "incomplete_ballot_vector_not_evaluable"
    assert not results[0].eligible and not results[0].public_point_eligible


def test_boundary_or_large_state_fit_abstains_from_public_points() -> None:
    homogeneous = peer_signals(_rows(32))
    assert not any(item.signal for item in homogeneous)
    assert all(item.fit_method for item in homogeneous if item.eligible)
    assert all(not item.public_point_eligible for item in homogeneous if item.eligible)

    large_state_rows = [
        replace(
            row,
            registered=1_000,
            ballots=1_000,
            valid_votes=1_000,
            candidate_votes=index,
            candidate_total_votes=1_000,
        )
        for index, row in enumerate(_rows(513))
    ]
    large_state = peer_signals(large_state_rows)
    assert all(
        item.fit_method == "large-state-full-pool-approximation"
        and not item.public_point_eligible
        and not item.signal
        for item in large_state
    )


def test_real_12k_family_benchmark_includes_hashing_adjustment_and_batches() -> None:
    count = 12_200
    rows = _rows(count)
    # A realistic repeated-count family exercises exact leave-one-out fits,
    # complete-family adjustment, canonical hashing, and bounded output batches.
    rows = [
        replace(
            row,
            valid_votes=600,
            ballots=600,
            registered=600,
            candidate_votes=250 + index % 101,
            candidate_total_votes=600,
        )
        for index, row in enumerate(rows)
    ]
    started = perf_counter()
    batches = tuple(peer_signal_batches(rows, batch_size=2048))
    serialized = json.dumps([asdict(item) for batch in batches for item in batch])
    elapsed = perf_counter() - started
    assert sum(len(batch) for batch in batches) == count
    assert "output_hash" in serialized
    assert all(
        item.fit_method != "large-state-full-pool-approximation"
        for batch in batches
        for item in batch
    )
    assert elapsed < 15


def test_hierarchical_reference_is_quarantined_and_target_excluded() -> None:
    rows = _rows(64)
    rows = [
        replace(
            row,
            municipality_id=f"municipality-{index // 32}",
            place_id=f"place-{index // 10}",
            candidate_votes=40 + index % 21,
        )
        for index, row in enumerate(rows)
    ]
    # The first place has exactly ten eligible mesas.  Its extreme target is
    # The target is excluded once from the complete hierarchical refit.
    rows[0] = replace(rows[0], candidate_votes=95)
    results = hierarchical_peer_signals_research_preview(rows)
    target = next(item for item in results if item.mesa_id == "mesa-0")
    assert target.eligible
    assert not target.public_point_eligible
    assert target.publication_status == "research_preview_not_for_public_priority"
    assert target.family_ledger_status == "external_registry_required_unverified"
    assert target.peer_level == "polling_place"
    assert target.polling_place_peers == 9
    assert target.department_peers == 63
    assert target.loo_refit_status == "target-excluded-hierarchical-refit"
    assert target.convergence_status in {
        "converged",
        "mesa-level-beta-binomial-shrinkage-not-converged",
    }
    assert target.expected_rate is not None
    assert target.predictive_interval_low is not None
    assert target.predictive_interval_high is not None
    assert target.predictive_interval_low <= target.expected_rate <= target.predictive_interval_high
    assert target.discrete_two_sided_p_value is not None
    assert target.adjusted_q_value is not None
    assert target.code_hash == HIERARCHICAL_REFERENCE_CODE_HASH
    assert target.method_hash == HIERARCHICAL_REFERENCE_METHOD_HASH
    assert len(target.output_hash) == 64

    # Changing only the held-out target cannot change its
    # expected rate: it is excluded from the hyperprior and every local level.
    changed = list(rows)
    changed[0] = replace(changed[0], candidate_votes=90)
    comparison = next(
        item
        for item in hierarchical_peer_signals_research_preview(changed)
        if item.mesa_id == "mesa-0"
    )
    assert comparison.loo_refit_status == "target-excluded-hierarchical-refit"
    assert comparison.expected_rate == pytest.approx(target.expected_rate)


def test_hierarchical_reference_uses_municipality_when_place_has_fewer_than_ten() -> None:
    rows = [
        replace(row, place_id=f"place-{index // 9}")
        for index, row in enumerate(_rows(40, votes=30))
    ]
    target = next(
        item
        for item in hierarchical_peer_signals_research_preview(rows)
        if item.mesa_id == "mesa-0"
    )
    assert target.eligible
    assert target.peer_level == "municipality"
    assert target.polling_place_peers == 8
    assert target.public_point_eligible is False


def test_hierarchical_incomplete_vector_abstains_without_lookup_failure() -> None:
    rows = _rows(32)
    rows[0] = replace(rows[0], candidate_total_votes=None, denominator_provenance="unavailable")
    target = next(
        item
        for item in hierarchical_peer_signals_research_preview(rows)
        if item.mesa_id == "mesa-0"
    )
    assert not target.eligible
    assert target.reason == "incomplete_ballot_vector_not_evaluable"
    assert target.observed_rate is None


def test_municipal_lomo_uses_shared_latent_beta_binomial_variance_and_abstains_on_p() -> None:
    assert beta_binomial_variance(20, 2.0, 3.0) == pytest.approx(20.0)
    assert beta_binomial_variance(20, 2.0, 3.0) > 2 * beta_binomial_variance(10, 2.0, 3.0)
    observations = tuple(
        BinomialPeerObservation(
            observation_id=f"target-{index}",
            department_id="d",
            municipality_id="target",
            polling_place_id="target-place",
            successes=4 + index,
            trials=10,
        )
        for index in range(2)
    ) + tuple(
        BinomialPeerObservation(
            observation_id=f"peer-{index}",
            department_id="d",
            municipality_id="peer",
            polling_place_id="peer-place",
            successes=3 + index % 4,
            trials=10,
        )
        for index in range(12)
    )
    prediction = HierarchicalBetaBinomialReference(observations).predict_municipality("d", "target")
    assert prediction.total_trials == 20
    assert prediction.predictive_variance == pytest.approx(
        beta_binomial_variance(20, prediction.alpha, prediction.beta)
    )
    marginal_sum = 2 * beta_binomial_variance(10, prediction.alpha, prediction.beta)
    assert prediction.predictive_variance > marginal_sum
    assert prediction.standardized_residual is None
    assert prediction.approximate_two_sided_p_value is None
    assert prediction.inference_status == "not_evaluable_hyperparameter_uncertainty"
