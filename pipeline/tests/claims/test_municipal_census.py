# ruff: noqa: E501
from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import pytest
from elecciones_pipeline.claims.municipal_aliases_v1 import rows
from elecciones_pipeline.claims.municipal_census import (
    CensusRecord,
    DivipolaCatalogRecord,
    MunicipalCensusClaimError,
    PopulationRecord,
    ReviewedAlias,
    SourceProvenance,
    build_claim_assessment,
    census_validation,
    join_by_divipola,
    parse_dane_2025_population,
    parse_divipola_catalog,
    parse_registraduria_census,
    summarize_join,
    validate_pinned_source_bytes,
    validate_reviewed_aliases,
    write_research_outputs,
)


def _census_bytes(rows: list[dict[str, object]]) -> bytes:
    return json.dumps(rows).encode()


def _census_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "COD_DEPTO": "25",
        "DEPARTAMENTO": "NORTE DE SANTANDER",
        "COD_MUN": "553",
        "MUNICIPIO": "PUERTO SANTANDER",
        "TOTAL": 21306,
        "MUJERES": 1,
        "HOMBRES": 1,
        "MESAS": 1,
        "PUESTOS": 1,
    }
    row.update(overrides)
    return row


def _dane_xlsx(rows: list[tuple[str, str, str, str, str, str, str]]) -> bytes:
    shared = ["DP", "DPNOM", "MPIO", "DPMP", "AÑO", "ÁREA GEOGRÁFICA", "TOTAL"]
    for row in rows:
        shared.extend(row)
    unique = list(dict.fromkeys(shared))
    indexes = {value: index for index, value in enumerate(unique)}
    xml_rows: list[str] = []
    header: tuple[str, str, str, str, str, str, str] = (
        "DP", "DPNOM", "MPIO", "DPMP", "AÑO", "ÁREA GEOGRÁFICA", "TOTAL"
    )
    for number, row in enumerate([header, *rows], start=8):
        cells = "".join(
            f'<c r="{chr(65 + index)}{number}" t="s"><v>{indexes[value]}</v></c>'
            for index, value in enumerate(row)
        )
        xml_rows.append(f'<row r="{number}">{cells}</row>')
    strings = "".join(f"<si><t>{value}</t></si>" for value in unique)
    worksheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{strings}</sst>')
        archive.writestr("xl/worksheets/sheet3.xml", worksheet)
    return buffer.getvalue()


def _provenance() -> SourceProvenance:
    return SourceProvenance("https://example.test", "2026-08-04T00:00:00Z", "application/json", 1, "a" * 64, "x", "test", "test")


def test_census_parser_normalizes_codes_and_reports_source_drift() -> None:
    records = parse_registraduria_census(_census_bytes([_census_row(COD_DEPTO=54, COD_MUN=553)]))
    assert records[0].source_key == "54553"
    validation = census_validation(records)
    assert validation["matches_expected_row_count"] is False
    assert validation["matches_expected_total_sum"] is False
    assert validation["has_unique_registraduria_department_municipality_keys"] is True


def test_frozen_registraduria_source_fixture_parses_without_rewriting_codes() -> None:
    fixture = Path("pipeline/tests/fixtures/claims/registraduria_census_mini.json")
    records = parse_registraduria_census(fixture.read_bytes())
    assert records == (CensusRecord("25", "069", "NORTE DE SAN", "PUERTO SANTANDER", 21306, 1),)


@pytest.mark.parametrize("row", [_census_row(COD_MUN="bad"), _census_row(TOTAL="-1"), _census_row(MUNICIPIO="")])
def test_census_parser_rejects_invalid_frozen_source_shapes(row: dict[str, object]) -> None:
    with pytest.raises(MunicipalCensusClaimError):
        parse_registraduria_census(_census_bytes([row]))


def test_dane_parser_selects_only_2025_total_rows() -> None:
    content = _dane_xlsx(
        [
                ("54", "Norte", "54553", "Puerto Santander", "2024", "Total", "9000"),
                ("54", "Norte", "54553", "Puerto Santander", "2025", "Cabecera Municipal", "5000"),
                ("54", "Norte", "54553", "Puerto Santander", "2025", "Total", "9483"),
        ]
    )
    parsed = parse_dane_2025_population(content)
    assert parsed == (PopulationRecord("54553", "Norte", "Puerto Santander", 9483, 11),)


def test_divipola_parser_and_alias_bijection_reject_duplicate_targets() -> None:
    catalog = parse_divipola_catalog(
        json.dumps(
            {
                "features": [
                    {
                        "attributes": {
                            "MPIO_CDPMP": "54553",
                            "MPIO_TIPO": "MUNICIPIO",
                            "DPTO_CNMBRE": "Norte de Santander",
                            "MPIO_CNMBRE": "Puerto Santander",
                        }
                    }
                ]
            }
        ).encode()
    )
    assert catalog == (DivipolaCatalogRecord("54553", "MUNICIPIO", "Norte de Santander", "Puerto Santander"),)
    census = (CensusRecord("25", "553", "Norte de San", "Puerto Santander", 1, 1),)
    population = (PopulationRecord("54553", "Norte de Santander", "Puerto Santander", 1, 1),)
    alias = ReviewedAlias("25000", "54553", "review", "https://example.test", "reviewer", "note")
    with pytest.raises(MunicipalCensusClaimError, match="source"):
        validate_reviewed_aliases((alias,), census, population, catalog)
    duplicate_target = (
        ReviewedAlias("25553", "54553", "review", "https://example.test", "reviewer", "note"),
        ReviewedAlias("25554", "54553", "review", "https://example.test", "reviewer", "note"),
    )
    with pytest.raises(MunicipalCensusClaimError, match="one-to-one"):
        validate_reviewed_aliases(duplicate_target, census, population, catalog)


def test_reviewed_alias_must_be_in_the_pre_alias_unmatched_set() -> None:
    census = (CensusRecord("25", "553", "NORTE DE SAN", "PUERTO SANTANDER", 1, 1),)
    population = (PopulationRecord("54553", "Norte de Santander", "Puerto Santander", 1, 1),)
    catalog = (DivipolaCatalogRecord("54553", "MUNICIPIO", "Norte de Santander", "Puerto Santander"),)
    alias = ReviewedAlias("25553", "54553", "review", "https://example.test", "reviewer", "note")
    with pytest.raises(MunicipalCensusClaimError, match="pre-alias unmatched"):
        validate_reviewed_aliases((alias,), census, population, catalog)


def test_versioned_reviewed_alias_table_has_85_explicit_bijective_pairs() -> None:
    aliases = rows()
    assert len(aliases) == 85
    assert len({source for source, _target, _method in aliases}) == 85
    assert len({target for _source, target, _method in aliases}) == 85


def test_exact_divipola_join_classifies_extraterritorial_and_duplicate_keys() -> None:
    census = (
        CensusRecord("25", "553", "Norte de San", "Puerto Santander", 21306, 1),
        CensusRecord("88", "001", "Consulados", "X", 20, 2),
        CensusRecord("05", "001", "Antioquia", "Medellín", 1, 3),
        CensusRecord("05", "001", "Antioquia", "Medellín", 2, 4),
    )
    population = (
        PopulationRecord("54553", "Norte de Santander", "Puerto Santander", 9483, 10),
        PopulationRecord("05001", "Antioquia", "Medellín", 2_500_000, 11),
    )
    joined = {row.divipola: row for row in join_by_divipola(census, population)}
    assert joined["54553"].join_status == "matched_exact_divipola"
    assert joined["54553"].census_to_population_ratio == pytest.approx(21306 / 9483)
    assert joined["extraterritorial:88001"].join_status == "outside_divipola_extraterritorial"
    assert joined["05001"].join_status == "duplicate_census_key"


def test_exact_join_preserves_catalog_types_and_mapiripana_catalog_gap() -> None:
    census = (CensusRecord("25", "553", "Norte de San", "Puerto Santander", 21306, 1),)
    population = (
        PopulationRecord("54553", "Norte de Santander", "Puerto Santander", 9483, 10),
        PopulationRecord("94663", "Guainía", "Mapiripana (ANM)", 0, 11),
    )
    catalog = (DivipolaCatalogRecord("54553", "MUNICIPIO", "Norte de Santander", "Puerto Santander"),)
    joined = {row.divipola: row for row in join_by_divipola(census, population, catalog_records=catalog)}
    summary = summarize_join(tuple(joined.values()))
    assert summary["counts_by_divipola_unit_type"] == {
        "MUNICIPIO": {
            "evaluable_units": 1,
            "greater_than_85pct": 1,
            "greater_than_100pct": 1,
            "greater_or_equal_100pct": 1,
            "exactly_100pct": 0,
            "greater_or_equal_200pct": 1,
        }
    }
    assert joined["94663"].join_status == "population_missing_census"
    assert joined["94663"].divipola_unit_type is None
    assert joined["94663"].divipola_catalog_status == "absent_from_pinned_catalog"
    assert joined["94663"].dane_population_label_unit_type_hint.startswith("ANM ")


def test_pinned_source_byte_gate_fails_closed() -> None:
    payload = b"frozen source"
    validate_pinned_source_bytes(
        payload,
        label="fixture",
        expected_sha256=sha256(payload).hexdigest(),
        expected_byte_size=len(payload),
    )
    with pytest.raises(MunicipalCensusClaimError, match="SHA-256 drift"):
        validate_pinned_source_bytes(
            payload,
            label="fixture",
            expected_sha256="0" * 64,
            expected_byte_size=len(payload),
        )
    with pytest.raises(MunicipalCensusClaimError, match="byte-size drift"):
        validate_pinned_source_bytes(
            payload,
            label="fixture",
            expected_sha256=sha256(payload).hexdigest(),
            expected_byte_size=len(payload) + 1,
        )


def test_claim_assessment_does_not_reproduce_93_and_writes_machine_readable_outputs(tmp_path: Path) -> None:
    census = (CensusRecord("25", "553", "Norte de San", "Puerto Santander", 21306, 1),)
    population = (PopulationRecord("54553", "Norte de Santander", "Puerto Santander", 9483, 10),)
    joined = join_by_divipola(census, population)
    assessment = build_claim_assessment(
        census_provenance=_provenance(),
        dane_provenance=_provenance(),
        census_records=census,
        population_records=population,
        joined=joined,
    )
    assert (
        assessment["claims"]["duplicating_population_ge_200pct"]["status"]  # type: ignore[index]
        == "not_reproduced_with_pinned_sources"
    )
    assert assessment["sensitivity"]["exact_only_lower_bound"]["counts"]["greater_or_equal_200pct"] == 1  # type: ignore[index]
    outputs = write_research_outputs(tmp_path, joined=joined, assessment=assessment)
    assert (
        json.loads(outputs["assessment"].read_text())["claims"]
        ["duplicating_population_ge_200pct"]["reviewed_expanded_observed_count"]
        == 1
    )
    assert pl.read_parquet(outputs["parquet"]).height == 1
