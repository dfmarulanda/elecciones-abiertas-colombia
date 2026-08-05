from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import polars as pl
import pytest
from elecciones_pipeline.analytics.longitudinal import (
    CROSSWALK_VERSION,
    FUTURE_2026_ADAPTER_VERSION,
    DescriptiveCompositionChange,
    FutureCompleted2026FactsAdapter,
    HistoricalInputBinding,
    LoadedHistoricalRelease,
    LongitudinalError,
    MunicipalityObservation,
    ObservedCategoryRecord,
    build_default_preview,
    build_longitudinal_preview,
    build_municipality_crosswalk,
    descriptive_composition_changes,
    observed_record_compositions,
    write_research_preview,
)


def _municipality(
    year: int,
    round_number: int,
    *,
    department_code: str = "05",
    municipality_code: str = "001",
    department_name: str = "Antioquía",
    municipality_name: str = "Medellín",
) -> MunicipalityObservation:
    return MunicipalityObservation(
        year=year,
        round_number=round_number,
        department_code=department_code,
        municipality_code=municipality_code,
        department_name=department_name,
        municipality_name=municipality_name,
    )


def _record(
    year: int,
    category_code: str,
    votes: int,
    *,
    round_number: int = 1,
    party_code: str | None = None,
    category_name: str | None = None,
) -> ObservedCategoryRecord:
    return ObservedCategoryRecord(
        year=year,
        round_number=round_number,
        department_code="05",
        municipality_code="001",
        department_name="ANTIOQUIA",
        municipality_name="MEDELLIN",
        party_code=party_code or category_code,
        category_code=category_code,
        category_name=category_name or f"CATEGORY {category_code}",
        votes=votes,
    )


def _binding(year: int) -> HistoricalInputBinding:
    return HistoricalInputBinding(
        year=year,
        release_id=f"historical-{year}-test",
        manifest_filename=f"historical-{year}-test.json",
        manifest_hash=("a" if year == 2018 else "b") * 64,
        source_artifact_hashes=(("c" if year == 2018 else "d") * 64,),
        parquet_artifacts=(),
    )


def test_crosswalk_matches_only_same_round_exact_codes_and_normalized_exact_labels() -> None:
    match = build_municipality_crosswalk(
        (_municipality(2018, 1),),
        (_municipality(2022, 1, department_name="ANTIOQUIA", municipality_name="MEDELLIN"),),
        round_number=1,
    )[0]
    assert match.status == "high_code_name_descriptive_only"
    assert match.crosswalk_version == CROSSWALK_VERSION
    assert not match.verified_physical_identity
    assert not match.mesa_code_comparison_allowed
    assert not match.integrity_inference_allowed
    assert match.audit_priority_points == 0

    with pytest.raises(LongitudinalError, match="only 2022 round 1"):
        build_municipality_crosswalk(
            (_municipality(2018, 1),),
            (_municipality(2022, 2),),
            round_number=1,
        )


def test_sparse_unknown_is_distinct_from_an_explicit_zero_record() -> None:
    composition = observed_record_compositions(
        (
            _record(2018, "001", 60),
            _record(2018, "002", 40),
            _record(2018, "996", 0, category_name="VOTOS EN BLANCO"),
            _record(2018, "998", 5, category_name="VOTOS NO MARCADOS"),
        )
    )[0]
    assert composition.estimand_scope == "observed_record_composition"
    assert composition.top1_observed_candidate_concentration == 0.6
    assert composition.top2_observed_candidate_concentration == 1.0
    assert composition.observed_candidate_hhi == 0.52
    assert composition.observed_candidate_effective_number == pytest.approx(1 / 0.52)
    assert composition.blank_record_present
    assert composition.blank_observed_votes == 0
    assert composition.blank_observed_record_composition == 0.0
    assert not composition.null_record_present
    assert composition.null_observed_votes is None
    assert composition.null_observed_record_composition is None
    assert composition.unmarked_record_present
    assert composition.unmarked_observed_votes == 5
    assert composition.audit_priority_points == 0
    assert not any(
        forbidden in field
        for field in asdict(composition)
        for forbidden in ("turnout", "valid_share", "registered_electors")
    )


def test_code_name_mismatch_and_2018_placeholder_both_abstain() -> None:
    mismatch = build_municipality_crosswalk(
        (_municipality(2018, 1, municipality_name="MUNICIPIO A"),),
        (_municipality(2022, 1, municipality_name="MUNICIPIO B"),),
        round_number=1,
    )[0]
    assert mismatch.status == "unmatched"
    assert mismatch.match_basis == "exact_code_present_but_normalized_exact_label_mismatch"

    placeholder = build_municipality_crosswalk(
        (
            _municipality(
                2018,
                1,
                department_name="official-department-code-05",
                municipality_name="official-municipality-code-05-001",
            ),
        ),
        (_municipality(2022, 1),),
        round_number=1,
    )[0]
    assert placeholder.status == "unmatched"
    assert placeholder.match_basis == "provisional_code_candidate_excluded"


def test_extraterritorial_and_split_merge_candidates_are_excluded() -> None:
    exterior = build_municipality_crosswalk(
        (
            _municipality(
                2018,
                1,
                department_code="88",
                department_name="CONSULADOS",
                municipality_name="ALEMANIA",
            ),
        ),
        (
            _municipality(
                2022,
                1,
                department_code="88",
                department_name="CONSULADOS",
                municipality_name="ALEMANIA",
            ),
        ),
        round_number=1,
    )[0]
    assert exterior.status == "extraterritorial"

    left = (
        _municipality(2018, 1, municipality_code="001", municipality_name="SAN PEDRO"),
        _municipality(2018, 1, municipality_code="002", municipality_name="SAN PEDRO"),
    )
    right = (_municipality(2022, 1, municipality_code="001", municipality_name="SAN PEDRO"),)
    split_merge = build_municipality_crosswalk(left, right, round_number=1)
    assert {row.status for row in split_merge} == {"ambiguous"}
    assert not descriptive_composition_changes((*split_merge, exterior), ())


def test_deterministic_preview_hash_is_order_independent_and_golden() -> None:
    municipalities_2018 = (_municipality(2018, 1), _municipality(2018, 2))
    municipalities_2022 = (_municipality(2022, 1), _municipality(2022, 2))
    records_2018 = (
        _record(2018, "001", 60),
        _record(2018, "002", 40),
        _record(2018, "996", 2),
    )
    records_2022 = (
        _record(2022, "001", 50),
        _record(2022, "002", 50),
        _record(2022, "996", 1),
    )
    first = build_longitudinal_preview(
        LoadedHistoricalRelease(_binding(2018), municipalities_2018, records_2018),
        LoadedHistoricalRelease(_binding(2022), municipalities_2022, records_2022),
    )
    shuffled = build_longitudinal_preview(
        LoadedHistoricalRelease(
            _binding(2018), tuple(reversed(municipalities_2018)), tuple(reversed(records_2018))
        ),
        LoadedHistoricalRelease(
            _binding(2022), tuple(reversed(municipalities_2022)), tuple(reversed(records_2022))
        ),
    )
    assert first == shuffled
    assert first.artifact_hash == "c2945225af0ec8a8e9cc1fb69faa6f4a619c787595780a175c13370d9c05d6dc"
    assert all(isinstance(row, DescriptiveCompositionChange) for row in first.descriptive_changes)
    assert all(row.audit_priority_points == 0 for row in first.descriptive_changes)


def test_future_2026_adapter_is_fail_closed_even_when_complete() -> None:
    incomplete = FutureCompleted2026FactsAdapter(
        adapter_version=FUTURE_2026_ADAPTER_VERSION,
        round_number=1,
        release_id="completed-2026",
        release_manifest_hash="a" * 64,
        facts_artifact_hash="b" * 64,
        expected_universe_hash="c" * 64,
        facts_complete=False,
        expected_coverage_verified=False,
        sparse_category_semantics_declared=True,
    )
    release_2018 = LoadedHistoricalRelease(_binding(2018), (), ())
    release_2022 = LoadedHistoricalRelease(_binding(2022), (), ())
    with pytest.raises(LongitudinalError, match="completed, coverage-verified"):
        build_longitudinal_preview(
            release_2018,
            release_2022,
            future_2026_adapter=incomplete,
        )
    complete = FutureCompleted2026FactsAdapter(
        **{**asdict(incomplete), "facts_complete": True, "expected_coverage_verified": True}
    )
    with pytest.raises(LongitudinalError, match="integration is disabled"):
        build_longitudinal_preview(
            release_2018,
            release_2022,
            future_2026_adapter=complete,
        )


def test_real_pinned_artifacts_produce_zero_match_golden_and_reproducible_outputs(
    tmp_path: Path,
) -> None:
    preview = build_default_preview(Path("."))
    assert [
        (item.year, item.release_id, item.manifest_hash) for item in preview.input_releases
    ] == [
        (
            2018,
            "historical-2018-mmv-context-v2-c456aeb032917d5c",
            "ef5daf8fbfebe4cc8d62006cd17801ee7255b15db8bbca8bd01731e261834710",
        ),
        (
            2022,
            "historical-2022-mmv-context-v2-705d3d71523003b8",
            "51bb931efb4f8afd3c0b8dbcac42f01eca5d6bbfce97f360774947c784e6cc34",
        ),
    ]
    assert len(preview.crosswalk) == 2_384
    assert len(preview.compositions) == 4_758
    assert not preview.descriptive_changes
    assert (
        preview.artifact_hash == "44f89f9c92fc9ccdba41f303a4ae8586872aa3c2148ae06eeca5f6623af597a2"
    )
    for coverage in preview.coverage:
        assert coverage.observed_municipalities_2018 == 1_191
        assert coverage.observed_municipalities_2022 == 1_188
        assert coverage.domestic_observed_municipalities_2018 == 1_122
        assert coverage.domestic_observed_municipalities_2022 == 1_121
        assert coverage.high_code_name_descriptive_only == 0
        assert coverage.provisional_code_candidate_excluded == 1_121
        assert coverage.extraterritorial == 70
        assert coverage.unmatched == 1_122
        assert coverage.ambiguous == 0
        assert coverage.matched_share_of_2018_domestic_observed_universe == 0.0
        assert coverage.matched_share_of_2022_domestic_observed_universe == 0.0

    first = write_research_preview(preview, tmp_path / "first")
    second = write_research_preview(preview, tmp_path / "second")
    for key in first:
        assert first[key].read_bytes() == second[key].read_bytes()
    payload = json.loads(first["manifest"].read_text(encoding="utf-8"))
    assert payload["research_only"] is True
    assert payload["public_release"] is False
    assert payload["current_2026_included"] is False
    assert payload["audit_priority_points"] == 0
    assert payload["historical_geography_adapter_contract"]["status"] == (
        "verified_geography_crosswalk_required"
    )
    assert payload["mesa_code_policy"] == ("excluded_without_official_same_physical_unit_evidence")
    assert pl.read_parquet(first["crosswalk"]).height == 2_384
    assert pl.read_parquet(first["compositions"]).height == 4_758
    assert pl.read_parquet(first["changes"]).is_empty()
