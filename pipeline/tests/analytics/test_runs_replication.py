from __future__ import annotations

from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.runs_replication import (
    RunsMesa,
    runs_cohort_digest,
    runs_family_digest,
    runs_replication_signals,
)


def _rows() -> tuple[RunsMesa, ...]:
    raw = [
        (f"a-{index}", "a", "place-a", index, "x" if index % 2 else "y") for index in range(1, 7)
    ] + [(f"b-{index}", "b", "place-b", index, "x" if index <= 3 else "y") for index in range(1, 7)]
    digest = runs_family_digest(item[0] for item in raw)
    artifact = "a" * 64
    cohort = runs_cohort_digest(
        input_artifact_hash=artifact,
        expected_family_count=len(raw),
        expected_family_digest=digest,
    )
    return tuple(
        RunsMesa(
            mesa_id=mesa_id,
            municipality_id=municipality,
            polling_place_id=place,
            election_year=2026,
            election_round="r2",
            sequence_number=sequence,
            category=category,
            input_artifact_hash=artifact,
            expected_family_count=len(raw),
            expected_family_digest=digest,
            cohort_hash=cohort,
        )
        for mesa_id, municipality, place, sequence, category in raw
    )


def test_runs_replication_is_deterministic_neutral_and_resolution_bounded() -> None:
    first = runs_replication_signals(_rows(), permutations=999)
    assert first == runs_replication_signals(_rows(), permutations=999)
    assert len(first) == 2
    # The permutation draw is data-derived and recorded, so an independent
    # replicator can regenerate the p-value and no caller can shop for a seed.
    assert all(item.randomization_seed == first[0].randomization_seed for item in first)
    assert first[0].randomization_seed > 0
    assert all(item.eligible and not item.public_point_eligible for item in first)
    assert all(item.claim_state == "neutral_research_association" for item in first)
    assert all(
        item.permutation_p_value is not None and item.permutation_p_value >= 1 / 1000
        for item in first
    )
    assert all(
        item.adjustment_method == "synchronized-max-t-within-place-permutation" for item in first
    )
    assert all(len(item.output_hash) == 64 for item in first)


def test_runs_gaps_break_sequences_and_complete_family_is_required() -> None:
    rows = list(_rows())
    rows[2] = replace(rows[2], category=None)
    signals = runs_replication_signals(rows, permutations=999)
    a = next(item for item in signals if item.municipality_id == "a")
    assert not a.eligible
    assert a.reason == "fewer_than_six_contiguous_mesas_or_two_categories_within_place"
    with pytest.raises(ValueError, match="complete family"):
        runs_replication_signals(rows[:-1], permutations=999)
