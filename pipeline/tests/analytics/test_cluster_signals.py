from __future__ import annotations

from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.cluster_signals import METHODOLOGY_VERSION, cluster_signals
from elecciones_pipeline.analytics.peer_signals import (
    MesaMetrics,
    cohort_digest,
    family_digest,
)


def _family(
    places: int = 40,
    per_place: int = 4,
    *,
    shifted_place: int | None = None,
    shift_votes: int = 0,
    incomplete_place: int | None = None,
) -> tuple[MesaMetrics, ...]:
    ids = tuple(f"mesa-{p:03d}-{m:02d}" for p in range(places) for m in range(per_place))
    digest = family_digest(ids)
    input_hash = "a" * 64
    cohort = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version="cluster-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        expected_family_count=len(ids),
        expected_family_digest=digest,
        input_artifact_hash=input_hash,
    )
    rows: list[MesaMetrics] = []
    for place in range(places):
        for mesa in range(per_place):
            valid, blank = 400, 20
            candidate_total = valid - blank
            votes = 120 + (place % 5) + mesa
            if shifted_place is not None and place == shifted_place:
                votes += shift_votes
            incomplete = incomplete_place is not None and place == incomplete_place and mesa == 0
            rows.append(
                MesaMetrics(
                    mesa_id=f"mesa-{place:03d}-{mesa:02d}",
                    place_id=f"place-{place:03d}",
                    municipality_id="municipality-1",
                    department_id="department-1",
                    metric="candidate_share",
                    registered=600,
                    ballots=valid + 20,
                    candidate_votes=votes,
                    valid_votes=valid,
                    blank_votes=blank,
                    null_unmarked_votes=20,
                    candidate_id="candidate-a",
                    election_slug="presidencia-2026-r2",
                    data_version="cluster-v1",
                    source_layer="pre_count",
                    source_type="pre_count",
                    legal_status="preliminary",
                    expected_family_count=len(ids),
                    expected_family_digest=digest,
                    input_artifact_hash=input_hash,
                    cohort_hash=cohort,
                    source_links=("https://official.example/results.json",),
                    candidate_total_votes=None if incomplete else candidate_total,
                    denominator_provenance="unavailable" if incomplete else "joined_official",
                )
            )
    return tuple(rows)


def test_one_incomplete_mesa_makes_its_whole_place_unknown_not_smaller() -> None:
    """A place total built from a partial ballot vector would silently understate
    that place. Unknown is not a smaller number, so the place is refused."""
    signals = cluster_signals(_family(incomplete_place=3))
    refused = next(item for item in signals if item.place_id == "place-003")
    assert refused.eligible is False
    assert refused.reason == "incomplete_mesa_in_place_not_evaluable"
    assert refused.tail_probability is None
    assert refused.adjusted_q_value is None
    assert refused.research_signal is False
    # Every other place still evaluates; one bad place does not poison the family.
    assert sum(item.eligible for item in signals) == 39


def test_target_cluster_is_removed_whole_from_its_own_reference() -> None:
    signals = cluster_signals(_family())
    evaluated = [item for item in signals if item.eligible]
    assert evaluated
    for item in evaluated:
        # 40 places in the pool, the target removed: 39 peers, never 40.
        assert item.peers == 39
        assert item.pool_level == "municipality"
        assert item.mesas == 4


def test_a_place_below_the_peer_floor_is_refused_rather_than_pooled_upward() -> None:
    signals = cluster_signals(_family(places=12))
    assert all(not item.eligible for item in signals)
    assert {item.reason for item in signals} == {"fewer_than_30_eligible_peer_places"}


def test_a_shifted_place_is_flagged_as_research_only_and_never_public() -> None:
    signals = cluster_signals(_family(shifted_place=0, shift_votes=90))
    flagged = [item for item in signals if item.research_signal]
    assert [item.place_id for item in flagged] == ["place-000"]
    target = flagged[0]
    assert target.effect_pp is not None and target.effect_pp > 8
    assert target.adjusted_q_value is not None and target.adjusted_q_value <= 0.05
    # Research only, at the type level, for every row without exception.
    assert all(item.signal is False for item in signals)
    assert all(item.public_point_eligible is False for item in signals)
    assert all(item.claim_state == "neutral_research_association" for item in signals)


def test_a_homogeneous_family_produces_no_leads() -> None:
    signals = cluster_signals(_family())
    assert not any(item.research_signal for item in signals)


def test_output_is_deterministic_and_content_addressed() -> None:
    first = cluster_signals(_family())
    assert first == cluster_signals(_family())
    assert all(len(item.output_hash) == 64 for item in first)
    assert all(item.methodology_version == METHODOLOGY_VERSION for item in first)


def test_a_family_must_describe_exactly_one_metric() -> None:
    """Two metrics in one family would pool incomparable rates into one
    reference distribution. blank uses the same ballot universe as
    candidate_share, so the row itself stays valid and only the family is
    rejected."""
    rows = list(_family())
    rows[0] = replace(rows[0], metric="blank", candidate_id=None, candidate_votes=0)
    with pytest.raises(ValueError, match="exactly one metric"):
        cluster_signals(rows)


def test_no_emitted_field_carries_fraud_vocabulary() -> None:
    forbidden = ("fraud", "fraude", "tamper", "manipul", "rigged", "stolen")
    for item in cluster_signals(_family(shifted_place=0, shift_votes=90)):
        blob = " ".join(
            [item.claim_state, item.calculation, item.methodology_version, *item.limitations]
        ).lower()
        assert not any(word in blob for word in forbidden)
