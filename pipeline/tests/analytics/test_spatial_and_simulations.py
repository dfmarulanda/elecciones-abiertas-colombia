from __future__ import annotations

from dataclasses import replace
from time import perf_counter

import numpy as np
import pytest
from elecciones_pipeline.analytics.spatial import (
    CODE_HASH,
    METHOD_HASH,
    SpatialMesa,
    _joint_permutation_p_values,
    spatial_cohort_digest,
    spatial_family_digest,
    spatial_mesa_digest,
    spatial_mesa_membership_digest,
    spatial_residual_signals,
)

HASH = "a" * 64
DEFAULT_DIGEST = spatial_family_digest(str(index) for index in range(100))


def _mesa(
    identifier: str,
    residual: float,
    *,
    latitude: float | None = None,
    longitude: float | None = -74.0,
    grain: str = "mesa",
    unit: str | None = None,
    artifact_hash: str = HASH,
    municipality: str = "m",
    accuracy: float = 10.0,
    expected_count: int = 100,
    expected_digest: str = DEFAULT_DIGEST,
) -> SpatialMesa:
    index = int(identifier.split("-")[-1]) if "-" in identifier else int(identifier)
    cohort_hash = spatial_cohort_digest(
        peer_residual_artifact_hash=artifact_hash,
        election_slug="presidencia-2026-r2",
        data_version="release-2026-r2-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        peer_methodology_version="peer-beta-binomial-eb-v5",
        coordinate_source_url="https://official.example/coordinates.geojson",
        coordinate_source_hash="b" * 64,
        coordinate_accuracy_m=accuracy,
        coordinate_grain=grain,  # type: ignore[arg-type]
        expected_family_count=expected_count,
        expected_family_digest=expected_digest,
        expected_mesa_count=1,
        expected_mesa_digest=spatial_mesa_digest((identifier,)),
        expected_mesa_membership_digest="c" * 64,
    )
    return SpatialMesa(
        mesa_id=identifier,
        municipality_id=municipality,
        latitude=4.0 + index * 0.001 if latitude is None else latitude,
        longitude=longitude,
        residual=residual,
        peer_residual_artifact_hash=artifact_hash,
        election_slug="presidencia-2026-r2",
        data_version="release-2026-r2-v1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        peer_methodology_version="peer-beta-binomial-eb-v5",
        coordinate_source_url="https://official.example/coordinates.geojson",
        coordinate_source_hash="b" * 64,
        coordinate_accuracy_m=accuracy,
        coordinate_grain=grain,  # type: ignore[arg-type]
        expected_family_count=expected_count,
        expected_family_digest=expected_digest,
        expected_mesa_count=1,
        expected_mesa_digest=spatial_mesa_digest((identifier,)),
        expected_mesa_membership_digest="c" * 64,
        cohort_hash=cohort_hash,
        spatial_unit_id=unit,
        source_links=("https://official.example/source.json",),
    )


def _bound(rows: list[SpatialMesa]) -> list[SpatialMesa]:
    """Apply the immutable complete-family declaration to raw test inputs."""
    analysis_units = [
        row.mesa_id if row.coordinate_grain == "mesa" else str(row.spatial_unit_id) for row in rows
    ]
    analysis_unit_digest = spatial_family_digest(set(analysis_units))
    mesa_digest = spatial_mesa_digest(row.mesa_id for row in rows)
    membership_digest = spatial_mesa_membership_digest(rows)
    first = rows[0]
    cohort = spatial_cohort_digest(
        peer_residual_artifact_hash=first.peer_residual_artifact_hash,
        election_slug=first.election_slug,
        data_version=first.data_version,
        source_layer=first.source_layer,
        source_type=first.source_type,
        legal_status=first.legal_status,
        metric=first.metric,
        candidate_id=first.candidate_id,
        peer_methodology_version=first.peer_methodology_version,
        coordinate_source_url=first.coordinate_source_url,
        coordinate_source_hash=first.coordinate_source_hash,
        coordinate_accuracy_m=first.coordinate_accuracy_m,
        coordinate_grain=first.coordinate_grain,
        expected_family_count=len(set(analysis_units)),
        expected_family_digest=analysis_unit_digest,
        expected_mesa_count=len(rows),
        expected_mesa_digest=mesa_digest,
        expected_mesa_membership_digest=membership_digest,
    )
    return [
        replace(
            row,
            expected_family_count=len(set(analysis_units)),
            expected_family_digest=analysis_unit_digest,
            expected_mesa_count=len(rows),
            expected_mesa_digest=mesa_digest,
            expected_mesa_membership_digest=membership_digest,
            cohort_hash=cohort,
        )
        for row in rows
    ]


def test_spatial_v2_is_seeded_family_bound_and_uses_by() -> None:
    rows = _bound([_mesa(str(index), 10.0 if index < 6 else 0.0) for index in range(100)])
    first = spatial_residual_signals(rows)
    second = spatial_residual_signals(rows)
    assert first == second
    assert len(first) == 100
    assert all(item.eligible for item in first)
    assert all(
        item.family_size == 100 and item.adjustment_method == "synchronized-max-t-permutation"
        for item in first
    )
    assert all(
        item.permutation_p_value is not None and item.family_rank is not None for item in first
    )
    assert all(not item.signal and not item.public_point_eligible for item in first)
    assert all(
        item.family_ledger_status == "external_registry_required_unverified" for item in first
    )
    assert all(item.randomization_seed is not None for item in first)
    assert len({item.randomization_seed for item in first}) == 1
    assert all(len(item.neighbors) == 5 for item in first)
    assert all(item.permutations >= 9_999 for item in first)
    assert all(
        item.comparator
        == f"{item.permutations:,} synchronized max-T within-municipality permutations"
        for item in first
    )
    assert all(
        item.permutation_resolution == pytest.approx(1 / (item.permutations + 1))
        and item.minimum_effect_size == pytest.approx(0.25)
        for item in first
    )
    assert all(
        item.coordinate_source_hash == "b" * 64
        and len(item.input_artifact_hash) == 64
        and item.code_hash == CODE_HASH
        and item.method_hash == METHOD_HASH
        and item.source_type == "pre_count"
        and item.legal_status == "preliminary"
        for item in first
    )


def test_spatial_effect_size_gate_is_independent_of_tail_calibration() -> None:
    rows = _bound([_mesa(str(index), 10.0 if index < 6 else 0.0) for index in range(100)])
    signals = spatial_residual_signals(rows, minimum_effect_size=1_000.0)
    assert all(not item.signal for item in signals)
    assert all(item.minimum_effect_size == 1_000.0 for item in signals)


def test_spatial_null_calibration_is_not_a_raw_residual_detector() -> None:
    rng = np.random.default_rng(7)
    rows = _bound(
        [_mesa(str(index), float(value)) for index, value in enumerate(rng.normal(size=100))]
    )
    signals = spatial_residual_signals(rows)
    p_values = [
        item.permutation_p_value for item in signals if item.permutation_p_value is not None
    ]
    assert len(p_values) == 100
    assert sum(value <= 0.01 for value in p_values) <= 10
    assert sum(item.signal for item in signals) == 0


def test_joint_null_permutates_whole_municipality_and_never_returns_zero() -> None:
    residuals = np.asarray([4.6, -0.4, -1.4, 4.6, -2.4, -0.4, 2.6, 1.6, -4.4, -4.4])
    neighborhoods = (
        (1, 2, 3),
        (0, 2, 3),
        (0, 1, 3),
        (0, 1, 2),
        (5, 6, 7),
        (4, 6, 7),
        (4, 5, 7),
        (4, 5, 6),
        (5, 6, 7),
        (4, 5, 6),
    )
    p_values, completed = _joint_permutation_p_values(
        residuals - np.mean(residuals),
        neighborhoods,
        seed=7,
        permutations=9_999,
        max_permutations=9_999,
    )
    replay, replay_completed = _joint_permutation_p_values(
        residuals - np.mean(residuals),
        neighborhoods,
        seed=7,
        permutations=9_999,
        max_permutations=9_999,
    )
    assert completed == replay_completed == 9_999
    assert np.array_equal(p_values, replay)
    assert np.all(p_values >= 1 / 10_000)


def test_polling_place_coordinates_are_collapsed_not_treated_as_independent_mesas() -> None:
    polling_digest = spatial_family_digest(f"place-{index}" for index in range(100))
    rows = _bound(
        [
            _mesa(
                f"mesa-{unit}-{copy}",
                1.0 if unit < 4 else 0.0,
                latitude=4.0 + unit * 0.001,
                grain="polling_place",
                unit=f"place-{unit}",
                expected_digest=polling_digest,
            )
            for unit in range(100)
            for copy in range(2)
        ]
    )
    signals = spatial_residual_signals(rows)
    assert len(signals) == 200
    assert {item.analysis_unit_id for item in signals} == {f"place-{index}" for index in range(100)}
    scored = [item for item in signals if item.eligible]
    copied = [item for item in signals if item.reason == "nonrepresentative_polling_place_mesa"]
    assert len(scored) == 100
    assert len(copied) == 100
    assert all(item.family_size == 100 for item in scored)
    assert all(not item.signal for item in copied)


def test_spatial_membership_fails_closed_before_polling_place_collapse() -> None:
    rows = _bound(
        [
            _mesa(
                f"mesa-{unit}-{copy}",
                float(unit),
                latitude=4.0 + unit * 0.001,
                grain="polling_place",
                unit=f"place-{unit}",
            )
            for unit in range(100)
            for copy in range(2)
        ]
    )
    output = spatial_residual_signals(rows)
    assert all(item.analysis_unit_digest == rows[0].expected_family_digest for item in output)
    assert all(
        item.mesa_membership_digest == rows[0].expected_mesa_membership_digest and item.output_hash
        for item in output
    )
    with pytest.raises(ValueError, match="exact expected mesa IDs"):
        spatial_residual_signals(rows[:-1])
    with pytest.raises(ValueError, match="membership"):
        spatial_residual_signals([*rows[:-1], replace(rows[-1], spatial_unit_id="place-98")])
    with pytest.raises(ValueError, match="membership"):
        spatial_residual_signals([*rows[:-1], replace(rows[-1], residual=999.0)])


def test_spatial_structural_rejections_fail_closed() -> None:
    rows = _bound([_mesa(str(index), 0.0) for index in range(100)])
    with pytest.raises(ValueError, match="unique"):
        spatial_residual_signals([*rows, rows[0]])
    mixed = [*rows[:-1], replace(rows[-1], peer_residual_artifact_hash="d" * 64)]
    with pytest.raises(ValueError, match="membership"):
        spatial_residual_signals(mixed)
    mixed_coordinates = [*rows[:-1], replace(rows[-1], coordinate_source_hash="d" * 64)]
    with pytest.raises(ValueError, match="membership"):
        spatial_residual_signals(mixed_coordinates)
    mixed_accuracy = [*rows[:-1], replace(rows[-1], coordinate_accuracy_m=25.0)]
    with pytest.raises(ValueError, match="membership"):
        spatial_residual_signals(mixed_accuracy)
    with pytest.raises(ValueError, match="9,999"):
        spatial_residual_signals(rows, permutations=999)
    with pytest.raises(ValueError, match="9,999"):
        spatial_residual_signals(rows, permutations=9_999.0)  # type: ignore[arg-type]
    identifiers = [str(index) for index in range(100)] + ["poor"]
    digest = spatial_family_digest(identifiers)
    complete = [
        _mesa(str(index), 0.0, expected_count=101, expected_digest=digest) for index in range(100)
    ]
    poor = replace(
        _mesa("0", 0.0, expected_count=101, expected_digest=digest),
        mesa_id="poor",
        latitude=None,
        longitude=None,
    )
    output = spatial_residual_signals(_bound([*complete, poor]))
    poor_signal = next(item for item in output if item.mesa_id == "poor")
    assert poor_signal.reason == "poor_geocode_or_cross_border"
    with pytest.raises(ValueError, match="contextual"):
        replace(rows[0], source_type="contextual_baseline", legal_status="context_only")
    with pytest.raises(ValueError, match="allowlisted"):
        replace(rows[0], election_slug="presidencia-2022-historical-context")
    with pytest.raises(ValueError, match="incompatible"):
        replace(rows[0], legal_status="official_scrutiny")
    with pytest.raises(ValueError, match="canonical source_type"):
        replace(rows[0], source_layer="scrutiny")
    with pytest.raises(ValueError, match="frozen peer methodology"):
        replace(rows[0], peer_methodology_version="peer-unreviewed-v999")
    with pytest.raises(ValueError, match="coordinate_grain"):
        replace(rows[0], coordinate_grain="municipality")  # type: ignore[arg-type]


def test_coordinate_grain_and_colocated_mesa_rejections() -> None:
    with pytest.raises(ValueError, match="spatial_unit_id"):
        _mesa("1", 0.0, grain="polling_place")
    rows = [_mesa(str(index), 0.0) for index in range(100)]
    rows[1] = _mesa("1", 0.0, latitude=4.0)
    rows = _bound(rows)
    output = spatial_residual_signals(rows)
    zero_signal = next(item for item in output if item.mesa_id == "0")
    one_signal = next(item for item in output if item.mesa_id == "1")
    unaffected = next(item for item in output if item.mesa_id == "2")
    assert zero_signal.reason == "co_located_analysis_units"
    assert one_signal.reason == "co_located_analysis_units"
    assert unaffected.reason == "municipality_below_100_eligible_units"
    assert all(item.family_size == 0 for item in output)


def test_coordinate_accuracy_above_frozen_ceiling_is_explicitly_excluded() -> None:
    rows = [_mesa(str(index), 0.0, accuracy=501.0) for index in range(100)]
    output = spatial_residual_signals(_bound(rows))
    assert all(not item.eligible for item in output)
    assert all(item.reason == "coordinate_accuracy_above_500m" for item in output)
    assert all(not item.signal and not item.public_point_eligible for item in output)


def test_spatial_complete_10k_city_polling_place_partition_benchmark() -> None:
    unit_ids = [f"place-{index}" for index in range(100)]
    digest = spatial_family_digest(unit_ids)
    rows = _bound(
        [
            _mesa(
                f"mesa-{place}-{mesa}",
                float(np.sin(place / 7)),
                latitude=4.0 + (place // 10) * 0.005,
                longitude=-74.0 + (place % 10) * 0.005,
                grain="polling_place",
                unit=f"place-{place}",
                municipality="bogota",
                expected_count=len(unit_ids),
                expected_digest=digest,
            )
            for place in range(100)
            for mesa in range(100)
        ]
    )
    started = perf_counter()
    output = spatial_residual_signals(rows)
    elapsed = perf_counter() - started
    assert len(output) == len(rows)
    assert len({item.analysis_unit_id for item in output}) == 100
    assert sum(item.eligible for item in output) == 100
    assert sum(item.reason == "nonrepresentative_polling_place_mesa" for item in output) == 9_900
    assert all(item.family_size == 100 for item in output if item.eligible)
    assert elapsed < 10
