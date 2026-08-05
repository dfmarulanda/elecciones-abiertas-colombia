# ruff: noqa: E501, S314
"""Reproduce a municipal electoral-census versus population claim safely.

This is a research-only calculation.  A ratio above one is an anomaly worth
describing, not evidence of fraud or of duplicated people.  The two official
sources measure different administrative concepts and use different vintages.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import statistics
import unicodedata
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET

import polars as pl

REGISTRADURIA_CENSUS_URL = "https://www.registraduria.gov.co/IMG/json/censomunicipios.json"
DANE_PROJECTIONS_URL = (
    "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/"
    "PPED-AreaMun-2018-2042_VP.xlsx"
)
DIVIPOLA_CATALOG_URL = (
    "https://geoportal.dane.gov.co/mparcgis/rest/services/Divipola/"
    "Serv_DIVIPOLA_MGN_2025/FeatureServer/317/query"
)
ASSESSMENT_VERSION = "municipal-census-claim/2.1.0"
_SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DANE_HEADERS = ("DP", "DPNOM", "MPIO", "DPMP", "AÑO", "ÁREA GEOGRÁFICA", "TOTAL")

# This research reproduction is intentionally tied to the reviewed acquisition,
# rather than pretending that a future response from the same URL is equivalent.
PINNED_REGISTRADURIA_SHA256 = "89d07a22a3d96f74e1e51825d071ed8b7b408c8c5710d969c2e4f8958a0cceec"
PINNED_REGISTRADURIA_BYTE_SIZE = 310_472
PINNED_DANE_SHA256 = "1ea83594ad308becff39934a3977c102919c25740f60439be95d797396d11283"
PINNED_DANE_BYTE_SIZE = 3_948_350
PINNED_DIVIPOLA_SHA256 = "e57a46868fa708a7794f197630810a16eafcf5db34e11f8273c54b46d7ce1ea5"
PINNED_DIVIPOLA_BYTE_SIZE = 128_658
PINNED_DANE_2025_TOTAL_ROW_COUNT = 1_123
PINNED_DANE_2025_TOTAL_POPULATION_SUM = 53_057_212
PINNED_DIVIPOLA_UNIT_TYPE_COUNTS = {
    "MUNICIPIO": 1_103,
    "ÁREA NO MUNICIPALIZADA": 18,
    "ISLA": 1,
}


class MunicipalCensusClaimError(ValueError):
    """Raised when a claimed official source cannot be parsed safely."""


@dataclass(frozen=True)
class SourceProvenance:
    source_url: str
    retrieved_at: str
    content_type: str
    byte_size: int
    sha256: str
    storage_path: str
    retrieval_method: str
    representation: str


@dataclass(frozen=True)
class CensusRecord:
    dep_code: str
    mun_code: str
    dep_name: str
    mun_name: str
    total: int
    source_row: int

    @property
    def source_key(self) -> str:
        return f"{self.dep_code}{self.mun_code}"


@dataclass(frozen=True)
class PopulationRecord:
    divipola: str
    dep_name: str
    mun_name: str
    population_2025: int
    source_row: int


@dataclass(frozen=True)
class DivipolaCatalogRecord:
    divipola: str
    unit_type: str
    dep_name: str
    mun_name: str


@dataclass(frozen=True)
class ReviewedAlias:
    source_key: str
    target_divipola: str
    method: str
    evidence_url: str
    reviewer: str
    reviewer_note: str


@dataclass(frozen=True)
class JoinedMunicipality:
    divipola: str
    join_status: str
    registraduria_dep_code: str | None
    registraduria_mun_code: str | None
    department_crosswalk_method: str | None
    municipality_crosswalk_method: str | None
    divipola_unit_type: str | None
    divipola_catalog_status: str | None
    dane_population_label_unit_type_hint: str | None
    dep_name_census: str | None
    mun_name_census: str | None
    census_total_2026: int | None
    dep_name_population: str | None
    mun_name_population: str | None
    population_2025: int | None
    census_to_population_ratio: float | None
    census_source_rows: str
    population_source_rows: str
    table_support_ge_85pct: bool


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_pinned_source_bytes(
    content: bytes, *, label: str, expected_sha256: str, expected_byte_size: int
) -> None:
    """Refuse a reproduction if its supposedly pinned raw bytes changed."""
    if len(content) != expected_byte_size:
        raise MunicipalCensusClaimError(
            f"{label} byte-size drift: expected {expected_byte_size}, received {len(content)}"
        )
    actual_sha256 = _sha256(content)
    if actual_sha256 != expected_sha256:
        raise MunicipalCensusClaimError(
            f"{label} SHA-256 drift: expected {expected_sha256}, received {actual_sha256}"
        )


def preserve_source_bytes(
    source_path: Path,
    *,
    raw_directory: Path,
    source_url: str,
    content_type: str,
    retrieved_at: str,
    retrieval_method: str,
    representation: str,
) -> SourceProvenance:
    """Copy exact acquired bytes under their digest before parsing them."""
    content = source_path.read_bytes()
    digest = _sha256(content)
    destination = raw_directory / "sha256" / f"{digest}{source_path.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != content:
        raise MunicipalCensusClaimError("content-addressed source path has different bytes")
    if not destination.exists():
        shutil.copyfile(source_path, destination)
    return SourceProvenance(
        source_url=source_url,
        retrieved_at=retrieved_at,
        content_type=content_type,
        byte_size=len(content),
        sha256=digest,
        storage_path=str(destination),
        retrieval_method=retrieval_method,
        representation=representation,
    )


def _code(value: object, width: int, field: str) -> str:
    if isinstance(value, bool):
        raise MunicipalCensusClaimError(f"{field} cannot be boolean")
    raw = str(value).strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > width:
        raise MunicipalCensusClaimError(f"invalid {field}: {value!r}")
    return raw.zfill(width)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise MunicipalCensusClaimError(f"{field} cannot be boolean")
    raw = str(value).strip()
    if not raw.isascii() or not raw.isdigit():
        raise MunicipalCensusClaimError(f"invalid {field}: {value!r}")
    result = int(raw)
    if result < 0:
        raise MunicipalCensusClaimError(f"negative {field}")
    return result


def _name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MunicipalCensusClaimError(f"invalid {field}")
    return value.strip()


def parse_registraduria_census(content: bytes) -> tuple[CensusRecord, ...]:
    """Parse the official municipal census JSON without silently coercing keys."""
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MunicipalCensusClaimError("census JSON is invalid") from exc
    if not isinstance(decoded, list):
        raise MunicipalCensusClaimError("census JSON root must be a list")
    records: list[CensusRecord] = []
    for source_row, item in enumerate(decoded, start=1):
        if not isinstance(item, dict):
            raise MunicipalCensusClaimError(f"census row {source_row} is not an object")
        row = cast(dict[str, object], item)
        records.append(
            CensusRecord(
                dep_code=_code(row.get("COD_DEPTO"), 2, "COD_DEPTO"),
                mun_code=_code(row.get("COD_MUN"), 3, "COD_MUN"),
                dep_name=_name(row.get("DEPARTAMENTO"), "DEPARTAMENTO"),
                mun_name=_name(row.get("MUNICIPIO"), "MUNICIPIO"),
                total=_integer(row.get("TOTAL"), "TOTAL"),
                source_row=source_row,
            )
        )
    return tuple(records)


def census_validation(records: Sequence[CensusRecord]) -> dict[str, object]:
    keys = [record.source_key for record in records]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    return {
        "row_count": len(records),
        "total_sum": sum(record.total for record in records),
        "duplicate_registraduria_department_municipality_keys": duplicates,
        "expected_row_count": 1189,
        "expected_total_sum": 41_421_973,
        "matches_expected_row_count": len(records) == 1189,
        "matches_expected_total_sum": sum(record.total for record in records) == 41_421_973,
        "has_unique_registraduria_department_municipality_keys": not duplicates,
    }


def _spreadsheet_column(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    if not letters:
        raise MunicipalCensusClaimError("worksheet cell lacks a column reference")
    number = 0
    for character in letters:
        number = number * 26 + ord(character.upper()) - ord("A") + 1
    return number - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(_SPREADSHEET_NS + "t")) for item in root]


def _row_values(row: ET.Element, shared_strings: Sequence[str]) -> dict[int, str]:
    values: dict[int, str] = {}
    for cell in row.findall(_SPREADSHEET_NS + "c"):
        index = _spreadsheet_column(cell.get("r", ""))
        value_node = cell.find(_SPREADSHEET_NS + "v")
        if value_node is None:
            continue
        value = value_node.text or ""
        if cell.get("t") == "s":
            try:
                value = shared_strings[int(value)]
            except (IndexError, ValueError) as exc:
                raise MunicipalCensusClaimError("invalid shared-string reference") from exc
        values[index] = value.strip()
    return values


def parse_dane_2025_population(content: bytes) -> tuple[PopulationRecord, ...]:
    """Parse only the 2025 municipal *Total* rows in the DANE XLSX archive."""
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise MunicipalCensusClaimError("DANE source is not a valid XLSX archive") from exc
    with archive:
        shared_strings = _shared_strings(archive)
        try:
            worksheet = archive.open("xl/worksheets/sheet3.xml")
        except KeyError as exc:
            raise MunicipalCensusClaimError("DANE workbook lacks municipal-area worksheet") from exc
        records: list[PopulationRecord] = []
        headers: tuple[str, ...] | None = None
        with worksheet:
            for _event, row in ET.iterparse(worksheet, events=("end",)):
                if row.tag != _SPREADSHEET_NS + "row":
                    continue
                values = _row_values(row, shared_strings)
                source_row = int(row.get("r", "0"))
                dense = tuple(values.get(index, "") for index in range(7))
                if dense == _DANE_HEADERS:
                    headers = dense
                    row.clear()
                    continue
                if headers is None or len(values) < 7:
                    row.clear()
                    continue
                year, area = dense[4], dense[5]
                if year == "2025" and area == "Total":
                    divipola = _code(dense[2], 5, "MPIO")
                    records.append(
                        PopulationRecord(
                            divipola=divipola,
                            dep_name=_name(dense[1], "DPNOM"),
                            mun_name=_name(dense[3], "DPMP"),
                            population_2025=_integer(dense[6], "TOTAL"),
                            source_row=source_row,
                        )
                    )
                row.clear()
    if headers != _DANE_HEADERS:
        raise MunicipalCensusClaimError("DANE municipal worksheet header drifted")
    if not records:
        raise MunicipalCensusClaimError("DANE workbook has no 2025 Total municipal rows")
    return tuple(records)


def parse_divipola_catalog(content: bytes) -> tuple[DivipolaCatalogRecord, ...]:
    """Parse the official DANE MGN 2025 Municipio feature-service response."""
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MunicipalCensusClaimError("DIVIPOLA catalog JSON is invalid") from exc
    if not isinstance(decoded, dict) or not isinstance(decoded.get("features"), list):
        raise MunicipalCensusClaimError("DIVIPOLA catalog lacks a features list")
    records: list[DivipolaCatalogRecord] = []
    for feature in decoded["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
            raise MunicipalCensusClaimError("DIVIPOLA catalog feature lacks attributes")
        attributes = cast(dict[str, object], feature["attributes"])
        records.append(
            DivipolaCatalogRecord(
                divipola=_code(attributes.get("MPIO_CDPMP"), 5, "MPIO_CDPMP"),
                unit_type=_name(attributes.get("MPIO_TIPO"), "MPIO_TIPO"),
                dep_name=_name(attributes.get("DPTO_CNMBRE"), "DPTO_CNMBRE"),
                mun_name=_name(attributes.get("MPIO_CNMBRE"), "MPIO_CNMBRE"),
            )
        )
    codes = [record.divipola for record in records]
    if len(codes) != len(set(codes)):
        raise MunicipalCensusClaimError("DIVIPOLA catalog has duplicate codes")
    return tuple(records)


def validate_pinned_parsed_sources(
    census_records: Sequence[CensusRecord],
    population_records: Sequence[PopulationRecord],
    catalog_records: Sequence[DivipolaCatalogRecord],
) -> None:
    """Fail closed on a row, arithmetic, or pinned-catalog shape change."""
    census_report = census_validation(census_records)
    if not (
        census_report["matches_expected_row_count"]
        and census_report["matches_expected_total_sum"]
        and census_report["has_unique_registraduria_department_municipality_keys"]
    ):
        raise MunicipalCensusClaimError("Registraduria parsed-source validation drift")
    population_codes = [record.divipola for record in population_records]
    if (
        len(population_records) != PINNED_DANE_2025_TOTAL_ROW_COUNT
        or len(population_codes) != len(set(population_codes))
        or sum(record.population_2025 for record in population_records)
        != PINNED_DANE_2025_TOTAL_POPULATION_SUM
    ):
        raise MunicipalCensusClaimError("DANE parsed-source validation drift")
    catalog_type_counts: dict[str, int] = defaultdict(int)
    for record in catalog_records:
        catalog_type_counts[record.unit_type] += 1
    if dict(sorted(catalog_type_counts.items())) != dict(sorted(PINNED_DIVIPOLA_UNIT_TYPE_COUNTS.items())):
        raise MunicipalCensusClaimError("DIVIPOLA parsed-source validation drift")
    mapiripana = [record for record in population_records if record.divipola == "94663"]
    if len(mapiripana) != 1:
        raise MunicipalCensusClaimError("pinned Mapiripana population-row validation drift")
    mapiripana_record = mapiripana[0]
    if (
        mapiripana_record.dep_name != "Guainía"
        or mapiripana_record.mun_name != "Mapiripana (ANM)"
        or mapiripana_record.population_2025 != 0
        or any(record.divipola == "94663" for record in catalog_records)
    ):
        raise MunicipalCensusClaimError("pinned Mapiripana catalog-gap classification drift")


def reviewed_aliases_v1() -> tuple[ReviewedAlias, ...]:
    """Materialize the finite manually reviewed alias table with evidence fields."""
    from .municipal_aliases_v1 import (
        ALIAS_CROSSWALK_VERSION,
        CATALOG_QUERY_BASE,
        REVIEWER,
        rows,
    )

    aliases: list[ReviewedAlias] = []
    for source_key, target_divipola, method in rows():
        note = (
            "Manually reviewed against DANE MGN 2025; the RNE label is a one-to-one "
            "qualifier, spelling, or diacritic variation."
        )
        if method == "reviewed_short_or_historical_label":
            note = (
                "Manually reviewed short or historical RNE label against the single "
                "DANE MGN 2025 unit in its department; retained only for sensitivity."
            )
        elif method == "reviewed_official_anm_label":
            note = (
                "Manually reviewed against the DANE MGN 2025 Área No Municipalizada "
                "unit; this is not a municipality classification."
            )
        aliases.append(
            ReviewedAlias(
                source_key=source_key,
                target_divipola=target_divipola,
                method=f"{ALIAS_CROSSWALK_VERSION}:{method}",
                evidence_url=(
                    f"{CATALOG_QUERY_BASE}?where=MPIO_CDPMP%3D%27{target_divipola}%27"
                    "&outFields=MPIO_CDPMP%2CMPIO_TIPO%2CDPTO_CNMBRE%2CMPIO_CNMBRE"
                    "&returnGeometry=false&f=json"
                ),
                reviewer=REVIEWER,
                reviewer_note=note,
            )
        )
    return tuple(aliases)


def validate_reviewed_aliases(
    aliases: Sequence[ReviewedAlias],
    census_records: Sequence[CensusRecord],
    population_records: Sequence[PopulationRecord],
    catalog_records: Sequence[DivipolaCatalogRecord],
) -> None:
    """Require a verified source/target bijection before an expanded sensitivity runs."""
    source_keys = [record.source_key for record in aliases]
    target_keys = [record.target_divipola for record in aliases]
    if len(source_keys) != len(set(source_keys)) or len(target_keys) != len(set(target_keys)):
        raise MunicipalCensusClaimError("reviewed aliases must be one-to-one")
    census_keys = {record.source_key for record in census_records}
    census_by_key = {record.source_key: record for record in census_records}
    population_keys = {record.divipola for record in population_records}
    catalog_keys = {record.divipola for record in catalog_records}
    crosswalk = department_crosswalk(census_records, population_records)
    population_by_department: dict[str, list[PopulationRecord]] = defaultdict(list)
    for population in population_records:
        population_by_department[population.divipola[:2]].append(population)
    for alias in aliases:
        if alias.source_key not in census_keys:
            raise MunicipalCensusClaimError("reviewed alias source is absent from census")
        if alias.target_divipola not in population_keys:
            raise MunicipalCensusClaimError("reviewed alias target is absent from population")
        if alias.target_divipola not in catalog_keys:
            raise MunicipalCensusClaimError("reviewed alias target is absent from DIVIPOLA catalog")
        source = census_by_key[alias.source_key]
        expected_department = crosswalk.get(source.dep_code)
        if expected_department is None or alias.target_divipola[:2] != expected_department[0]:
            raise MunicipalCensusClaimError("reviewed alias crosses a department boundary")
        direct_matches = [
            population
            for population in population_by_department[expected_department[0]]
            if _normalized_label(population.mun_name) == _normalized_label(source.mun_name)
        ]
        if direct_matches:
            raise MunicipalCensusClaimError(
                "reviewed alias source must belong to the pre-alias unmatched set"
            )


def _group_by_divipola[T](records: Iterable[T], key: Callable[[T], str]) -> dict[str, list[T]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for record in records:
        grouped[key(record)].append(record)
    return dict(grouped)


def _normalized_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in decomposed.casefold()
        if not unicodedata.combining(character) and character.isalnum()
    )


def _dane_population_label_unit_type_hint(population: PopulationRecord | None) -> str | None:
    """Expose only an explicit source-label hint; it is not a catalog classification."""
    if population is not None and population.mun_name.rstrip().endswith("(ANM)"):
        return "ANM (literal DANE population-label suffix; not an MGN catalog classification)"
    return None


def department_crosswalk(
    census_records: Sequence[CensusRecord], population_records: Sequence[PopulationRecord]
) -> dict[str, tuple[str, str]]:
    """Build a deterministic department-code crosswalk from the two official labels.

    The census's department codes are not DANE DIVIPOLA codes.  This permits
    only literal normalized label equality, a unique literal prefix, or a
    unique token containment match.  It never chooses among multiple matches.
    """
    census_names: dict[str, set[str]] = defaultdict(set)
    for record in census_records:
        census_names[record.dep_code].add(record.dep_name)
    dane_names: dict[str, set[str]] = defaultdict(set)
    for population_record in population_records:
        dane_names[population_record.divipola[:2]].add(population_record.dep_name)
    canonical_dane_names = {
        code: next(iter(names)) for code, names in dane_names.items() if len(names) == 1
    }
    crosswalk: dict[str, tuple[str, str]] = {}
    for census_code, names in census_names.items():
        if census_code == "88" or len(names) != 1:
            continue
        census_name = next(iter(names))
        normalized = _normalized_label(census_name)
        exact = [
            code
            for code, dane_name in canonical_dane_names.items()
            if _normalized_label(dane_name) == normalized
        ]
        prefix = [
            code
            for code, dane_name in canonical_dane_names.items()
            if _normalized_label(dane_name).startswith(normalized)
            or normalized.startswith(_normalized_label(dane_name))
        ]
        tokens = {_normalized_label(token) for token in census_name.split()}
        containment = [
            code
            for code, dane_name in canonical_dane_names.items()
            if tokens <= {_normalized_label(token) for token in dane_name.replace(",", " ").split()}
        ]
        if len(exact) == 1:
            crosswalk[census_code] = (exact[0], "normalized_exact_label")
        elif len(prefix) == 1:
            crosswalk[census_code] = (prefix[0], "unique_literal_prefix")
        elif len(containment) == 1:
            crosswalk[census_code] = (containment[0], "unique_literal_token_containment")
    return crosswalk


def join_by_divipola(
    census_records: Sequence[CensusRecord],
    population_records: Sequence[PopulationRecord],
    *,
    aliases: Sequence[ReviewedAlias] = (),
    catalog_records: Sequence[DivipolaCatalogRecord] = (),
) -> tuple[JoinedMunicipality, ...]:
    """Join through literal official labels; no fuzzy municipality matching is allowed."""
    if aliases:
        validate_reviewed_aliases(aliases, census_records, population_records, catalog_records)
    crosswalk = department_crosswalk(census_records, population_records)
    aliases_by_source = {alias.source_key: alias for alias in aliases}
    catalog_by_divipola = {record.divipola: record for record in catalog_records}
    census_by_key: dict[str, list[CensusRecord]] = defaultdict(list)
    unmatched: list[tuple[CensusRecord, str]] = []
    population_by_department: dict[str, list[PopulationRecord]] = defaultdict(list)
    for population_record in population_records:
        population_by_department[population_record.divipola[:2]].append(population_record)
    for record in census_records:
        if record.dep_code == "88":
            census_by_key[f"extraterritorial:{record.source_key}"].append(record)
        elif record.dep_code not in crosswalk:
            unmatched.append((record, "unresolved_department_crosswalk"))
        else:
            target_department = crosswalk[record.dep_code][0]
            candidates = [
                population_record
                for population_record in population_by_department[target_department]
                if _normalized_label(population_record.mun_name) == _normalized_label(record.mun_name)
            ]
            if len(candidates) == 1:
                census_by_key[candidates[0].divipola].append(record)
            elif record.source_key in aliases_by_source:
                alias = aliases_by_source[record.source_key]
                census_by_key[alias.target_divipola].append(record)
            elif len(candidates) == 0:
                unmatched.append((record, "unmatched_municipality_label"))
            else:
                unmatched.append((record, "ambiguous_municipality_label"))
    population_by_key = _group_by_divipola(population_records, lambda record: record.divipola)
    joined: list[JoinedMunicipality] = []
    for record, status in unmatched:
        joined.append(
            JoinedMunicipality(
                divipola=f"{status}:{record.source_key}",
                join_status=status,
                registraduria_dep_code=record.dep_code,
                registraduria_mun_code=record.mun_code,
                department_crosswalk_method=(
                    crosswalk[record.dep_code][1] if record.dep_code in crosswalk else None
                ),
                municipality_crosswalk_method=None,
                divipola_unit_type=None,
                divipola_catalog_status=None,
                dane_population_label_unit_type_hint=None,
                dep_name_census=record.dep_name,
                mun_name_census=record.mun_name,
                census_total_2026=record.total,
                dep_name_population=None,
                mun_name_population=None,
                population_2025=None,
                census_to_population_ratio=None,
                census_source_rows=str(record.source_row),
                population_source_rows="",
                table_support_ge_85pct=False,
            )
        )
    for divipola in sorted(set(census_by_key) | set(population_by_key)):
        census = census_by_key.get(divipola, [])
        population = population_by_key.get(divipola, [])
        census_rows = ";".join(str(record.source_row) for record in census)
        population_rows = ";".join(str(record.source_row) for record in population)
        primary_census = census[0] if len(census) == 1 else None
        primary_population = population[0] if len(population) == 1 else None
        catalog_record = catalog_by_divipola.get(divipola)
        crosswalk_value = crosswalk.get(primary_census.dep_code) if primary_census else None
        if primary_census is not None and primary_census.dep_code == "88":
            status = "outside_divipola_extraterritorial"
        elif len(census) > 1:
            status = "duplicate_census_key"
        elif len(population) > 1:
            status = "duplicate_population_key"
        elif primary_census is None:
            status = "population_missing_census"
        elif primary_population is None:
            status = "census_missing_population"
        elif primary_census is not None and primary_census.source_key in aliases_by_source:
            status = "matched_reviewed_alias"
        else:
            status = "matched_exact_divipola"
        ratio = (
            primary_census.total / primary_population.population_2025
            if status in {"matched_exact_divipola", "matched_reviewed_alias"}
            and primary_census
            and primary_population
            else None
        )
        joined.append(
            JoinedMunicipality(
                divipola=divipola,
                join_status=status,
                registraduria_dep_code=primary_census.dep_code if primary_census else None,
                registraduria_mun_code=primary_census.mun_code if primary_census else None,
                department_crosswalk_method=crosswalk_value[1] if crosswalk_value else None,
                municipality_crosswalk_method=(
                    (
                        aliases_by_source[primary_census.source_key].method
                        if primary_census and primary_census.source_key in aliases_by_source
                        else "normalized_exact_label"
                    )
                    if primary_census and primary_population
                    else None
                ),
                divipola_unit_type=(
                    catalog_record.unit_type if catalog_record is not None else None
                ),
                divipola_catalog_status=(
                    "matched_pinned_catalog"
                    if catalog_record is not None
                    else "absent_from_pinned_catalog"
                    if primary_population is not None
                    else None
                ),
                dane_population_label_unit_type_hint=_dane_population_label_unit_type_hint(
                    primary_population
                ),
                dep_name_census=primary_census.dep_name if primary_census else None,
                mun_name_census=primary_census.mun_name if primary_census else None,
                census_total_2026=primary_census.total if primary_census else None,
                dep_name_population=primary_population.dep_name if primary_population else None,
                mun_name_population=primary_population.mun_name if primary_population else None,
                population_2025=primary_population.population_2025 if primary_population else None,
                census_to_population_ratio=ratio,
                census_source_rows=census_rows,
                population_source_rows=population_rows,
                table_support_ge_85pct=ratio is not None and ratio >= 0.85,
            )
        )
    return tuple(joined)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise MunicipalCensusClaimError("cannot calculate percentile without matched ratios")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_join(joined: Sequence[JoinedMunicipality]) -> dict[str, object]:
    exact_matched = [row for row in joined if row.join_status == "matched_exact_divipola"]
    reviewed_matched = [row for row in joined if row.join_status == "matched_reviewed_alias"]
    matched = [*exact_matched, *reviewed_matched]
    ratios = [row.census_to_population_ratio for row in matched if row.census_to_population_ratio is not None]
    assert ratios  # guarded by caller/source expectations; improves type narrowing.
    duplicates = {
        "census": sum(row.join_status == "duplicate_census_key" for row in joined),
        "population": sum(row.join_status == "duplicate_population_key" for row in joined),
    }
    counts_by_unit_type: dict[str, dict[str, int]] = {}
    for row in matched:
        if row.census_to_population_ratio is None:
            continue
        unit_type = row.divipola_unit_type or "unclassified_in_this_join"
        counts = counts_by_unit_type.setdefault(
            unit_type,
            {
                "evaluable_units": 0,
                "greater_than_85pct": 0,
                "greater_than_100pct": 0,
                "greater_or_equal_100pct": 0,
                "exactly_100pct": 0,
                "greater_or_equal_200pct": 0,
            },
        )
        counts["evaluable_units"] += 1
        counts["greater_than_85pct"] += int(row.census_to_population_ratio > 0.85)
        counts["greater_than_100pct"] += int(row.census_to_population_ratio > 1.0)
        counts["greater_or_equal_100pct"] += int(row.census_to_population_ratio >= 1.0)
        counts["exactly_100pct"] += int(row.census_total_2026 == row.population_2025)
        counts["greater_or_equal_200pct"] += int(row.census_to_population_ratio >= 2.0)
    return {
        "joined_rows": len(joined),
        "matched_exact_divipola": len(exact_matched),
        "matched_reviewed_alias": len(reviewed_matched),
        "matched_evaluable_total": len(matched),
        "census_missing_population": sum(row.join_status == "census_missing_population" for row in joined),
        "population_missing_census": sum(row.join_status == "population_missing_census" for row in joined),
        "unmatched_municipality_label": sum(
            row.join_status == "unmatched_municipality_label" for row in joined
        ),
        "ambiguous_municipality_label": sum(
            row.join_status == "ambiguous_municipality_label" for row in joined
        ),
        "unresolved_department_crosswalk": sum(
            row.join_status == "unresolved_department_crosswalk" for row in joined
        ),
        "outside_divipola_extraterritorial": sum(
            row.join_status == "outside_divipola_extraterritorial" for row in joined
        ),
        "duplicate_keys": duplicates,
        "ratio_formula": "census_total_2026 / DANE_population_2025_total",
        "ratio_summary": {
            "min": min(ratios),
            "median": statistics.median(ratios),
            "p95_inclusive_linear": _percentile(ratios, 0.95),
            "max": max(ratios),
        },
        "counts": {
            "greater_than_85pct": sum(ratio > 0.85 for ratio in ratios),
            "greater_than_100pct": sum(ratio > 1.0 for ratio in ratios),
            "greater_or_equal_100pct": sum(ratio >= 1.0 for ratio in ratios),
            "exactly_100pct": sum(
                row.census_total_2026 == row.population_2025 for row in matched
            ),
            "greater_or_equal_200pct": sum(ratio >= 2.0 for ratio in ratios),
            "table_filter_greater_or_equal_85pct": sum(ratio >= 0.85 for ratio in ratios),
        },
        "counts_by_divipola_unit_type": dict(sorted(counts_by_unit_type.items())),
    }


def build_claim_assessment(
    *,
    census_provenance: SourceProvenance,
    dane_provenance: SourceProvenance,
    census_records: Sequence[CensusRecord],
    population_records: Sequence[PopulationRecord],
    joined: Sequence[JoinedMunicipality],
    expanded_joined: Sequence[JoinedMunicipality] | None = None,
    catalog_records: Sequence[DivipolaCatalogRecord] = (),
    catalog_provenance: SourceProvenance | None = None,
) -> dict[str, object]:
    exact_summary = summarize_join(joined)
    expanded = expanded_joined if expanded_joined is not None else joined
    expanded_summary = summarize_join(expanded)
    exact_counts = cast(Mapping[str, int], exact_summary["counts"])
    expanded_counts = cast(Mapping[str, int], expanded_summary["counts"])
    expanded_by_type = cast(
        Mapping[str, Mapping[str, int]], expanded_summary["counts_by_divipola_unit_type"]
    )
    expanded_municipality_counts = expanded_by_type.get("MUNICIPIO", {})
    crosswalk = department_crosswalk(census_records, population_records)
    crosswalk_methods: dict[str, int] = defaultdict(int)
    for _dane_code, method in crosswalk.values():
        crosswalk_methods[method] += 1
    matched = [
        row
        for row in expanded
        if row.join_status in {"matched_exact_divipola", "matched_reviewed_alias"}
    ]
    double_population = [
        row
        for row in matched
        if row.census_to_population_ratio is not None and row.census_to_population_ratio >= 2.0
    ]
    double_population_count = len(double_population)
    exceeds_population_count = expanded_counts["greater_than_100pct"]
    exact_unresolved_rne = sum(
        row.join_status in {"unmatched_municipality_label", "ambiguous_municipality_label"}
        for row in joined
    )
    catalog_types: dict[str, int] = defaultdict(int)
    for record in catalog_records:
        catalog_types[record.unit_type] += 1
    return {
        "assessment_version": ASSESSMENT_VERSION,
        "generated_at": _utc_now(),
        "claims": {
            "duplicating_population_ge_200pct": {
                "statement": "93 municipalities have electoral census duplicating population",
                "operationalization": "census_total_2026 / DANE_population_2025_total >= 2.0",
                "reviewed_expanded_observed_count": double_population_count,
                "reviewed_expanded_municipio_observed_count": expanded_municipality_counts.get(
                    "greater_or_equal_200pct"
                ),
                "exact_only_status": "inconclusive_lower_bound",
                "exact_only_unresolved_rne_units": exact_unresolved_rne,
                "claim_count": 93,
                "status": (
                    "not_reproduced_with_pinned_sources"
                    if double_population_count != 93
                    else "count_reproduced_not_explained"
                ),
            },
            "census_exceeds_population_gt_100pct": {
                "statement": "93 municipalities have electoral census exceeding population",
                "operationalization": "census_total_2026 / DANE_population_2025_total > 1.0",
                "exact_only_lower_bound": exact_counts["greater_than_100pct"],
                "exact_only_unresolved_rne_units": exact_unresolved_rne,
                "exact_only_upper_bound_if_every_unresolved_unit_exceeded": (
                    exact_counts["greater_than_100pct"] + exact_unresolved_rne
                ),
                "reviewed_expanded_observed_count": exceeds_population_count,
                "reviewed_expanded_municipio_observed_count": expanded_municipality_counts.get(
                    "greater_than_100pct"
                ),
                "reviewed_expanded_municipio_count_at_or_above_100pct": (
                    expanded_municipality_counts.get("greater_or_equal_100pct")
                ),
                "reviewed_expanded_municipio_count_exactly_100pct": (
                    expanded_municipality_counts.get("exactly_100pct")
                ),
                "exact_only_status": "inconclusive_lower_bound",
                "claim_count": 93,
                "status": (
                    "not_reproduced_with_pinned_sources"
                    if exceeds_population_count != 93
                    else "count_reproduced_not_explained"
                ),
            },
        },
        "anomaly_not_fraud": "A ratio is a descriptive anomaly and is not evidence, probability, or finding of fraud.",
        "formula": "census_total_2026 / DANE_population_2025_total",
        "source_validation": {
            "registraduria": census_validation(census_records),
            "dane_2025_total_population_rows": len(population_records),
        },
        "sensitivity": {
            "exact_only_lower_bound": exact_summary,
            "reviewed_expanded_join": expanded_summary,
            "exact_only_unresolved_units_can_change_each_threshold_by_at_most": exact_unresolved_rne,
            "reviewed_expanded_unresolved_rne_units": sum(
                row.join_status in {"unmatched_municipality_label", "ambiguous_municipality_label"}
                for row in expanded
            ),
            "dane_units_without_rne_equivalent_after_review": [
                asdict(row)
                for row in expanded
                if row.join_status == "population_missing_census"
            ],
            "divipola_domestic_unit_types": dict(sorted(catalog_types.items())),
            "reviewed_alias_bijection": {
                "accepted_source_target_pairs": sum(
                    row.join_status == "matched_reviewed_alias" for row in expanded
                ),
                "consolidations_or_splits_accepted": 0,
                "rule": "Every accepted source and target occurs exactly once; validation blocks duplicates.",
            },
        },
        "deterministic_crosswalk": {
            "department_mappings": len(crosswalk),
            "department_methods": dict(sorted(crosswalk_methods.items())),
            "municipality_method": "normalized_exact_label_only",
            "unmatched_and_ambiguous_records_are_excluded_from_ratio_inference": True,
        },
        "source_vintage_and_geography": {
            "census_reference": "Registraduría electoral census published as of 2026-05-07",
            "population_reference": "DANE municipal total-population projection for 2025",
            "effect": "Different time reference and administrative definitions limit causal interpretation.",
            "threshold_sensitivity": {
                "municipality": "Togüí",
                "divipola": "15816",
                "census_total_2026": 4469,
                "pinned_dane_population_2025": 4459,
                "difference_people": 10,
                "ratio": 4469 / 4459,
                "interpretation": (
                    "A 10-person denominator change would cross the >100% threshold. "
                    "This establishes threshold sensitivity; a source-vintage or rounding "
                    "explanation is plausible but not proven by the pinned sources."
                ),
            },
            "third_party_visible_puerto_santander_comparison": {
                "third_party_visible_population_value": 9483,
                "pinned_official_dane_xlsx_value": 9563,
                "difference_people": 80,
                "interpretation": (
                    "The difference supports a source-vintage or transcription hypothesis, "
                    "but does not establish its cause."
                ),
            },
        },
        "rows_at_or_above_200pct_reviewed_expanded": [asdict(row) for row in double_population],
        "closest_to_100pct_reviewed_expanded": [
            asdict(row)
            for row in sorted(
                matched,
                key=lambda row: abs((row.census_to_population_ratio or 0.0) - 1.0),
            )[:10]
        ],
        "possible_explanations": [
            "The sources use different reference dates (2026 electoral census versus 2025 population projection).",
            "The sources measure different administrative concepts; this calculation does not establish a person-level duplication mechanism.",
            "Population projections have model uncertainty and may not track local migration or geographic changes exactly.",
            "Only an official, documented crosswalk can resolve any boundary or source-definition mismatch; no fuzzy name matching was used here.",
        ],
        "limitations": [
            "The census source includes extraterritorial consulates, which are classified outside Colombian municipal DIVIPOLA and excluded from ratios.",
            "The calculation does not contain individual-level records, voter residence, citizenship, age eligibility, registration history, or an audit trail of electoral-address changes.",
            "No causal explanation is established by a high ratio. If the listed explanations cannot be tested with available data, no explanation was found in available data.",
        ],
        "provenance": {
            "registraduria": asdict(census_provenance),
            "dane": asdict(dane_provenance),
            "dane_divipola_catalog": asdict(catalog_provenance) if catalog_provenance else None,
        },
    }


def write_research_outputs(
    output_directory: Path,
    *,
    joined: Sequence[JoinedMunicipality],
    assessment: Mapping[str, object],
    exact_joined: Sequence[JoinedMunicipality] | None = None,
    aliases: Sequence[ReviewedAlias] = (),
) -> dict[str, Path]:
    """Write research artifacts only; callers must never treat them as releases."""
    output_directory.mkdir(parents=True, exist_ok=True)
    fieldnames = list(JoinedMunicipality.__dataclass_fields__)

    def write_csv(path: Path, selected: Sequence[JoinedMunicipality]) -> None:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(asdict(row) for row in selected)

    rows = [asdict(row) for row in joined]
    csv_path = output_directory / "reviewed_expanded_join.csv"
    write_csv(csv_path, joined)
    if exact_joined is not None:
        write_csv(output_directory / "exact_only_join.csv", exact_joined)
        write_csv(
            output_directory / "exact_only_unmatched_rne.csv",
            [
                row
                for row in exact_joined
                if row.join_status in {"unmatched_municipality_label", "ambiguous_municipality_label"}
            ],
        )
        write_csv(
            output_directory / "exact_only_unmatched_dane.csv",
            [row for row in exact_joined if row.join_status == "population_missing_census"],
        )
    if aliases:
        alias_path = output_directory / "reviewed_alias_crosswalk_v1.csv"
        with alias_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(ReviewedAlias.__dataclass_fields__))
            writer.writeheader()
            writer.writerows(asdict(alias) for alias in aliases)
    # Backward-compatible research filename; its content is the explicit reviewed sensitivity.
    write_csv(output_directory / "municipal_census_population_join.csv", joined)
    parquet_path = output_directory / "reviewed_expanded_join.parquet"
    schema = {
        "divipola": pl.String,
        "join_status": pl.String,
        "registraduria_dep_code": pl.String,
        "registraduria_mun_code": pl.String,
        "department_crosswalk_method": pl.String,
        "municipality_crosswalk_method": pl.String,
        "divipola_unit_type": pl.String,
        "divipola_catalog_status": pl.String,
        "dane_population_label_unit_type_hint": pl.String,
        "dep_name_census": pl.String,
        "mun_name_census": pl.String,
        "census_total_2026": pl.Int64,
        "dep_name_population": pl.String,
        "mun_name_population": pl.String,
        "population_2025": pl.Int64,
        "census_to_population_ratio": pl.Float64,
        "census_source_rows": pl.String,
        "population_source_rows": pl.String,
        "table_support_ge_85pct": pl.Boolean,
    }
    pl.DataFrame(rows, schema=schema, strict=True).write_parquet(parquet_path, compression="zstd")
    legacy_parquet_path = output_directory / "municipal_census_population_join.parquet"
    shutil.copyfile(parquet_path, legacy_parquet_path)
    assessment_path = output_directory / "claim_assessment.json"
    assessment_path.write_text(json.dumps(assessment, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {
        "csv": csv_path,
        "parquet": parquet_path,
        "assessment": assessment_path,
        "exact_unmatched_rne": output_directory / "exact_only_unmatched_rne.csv",
        "exact_unmatched_dane": output_directory / "exact_only_unmatched_dane.csv",
        "reviewed_alias_crosswalk": output_directory / "reviewed_alias_crosswalk_v1.csv",
    }


def reproduce_from_paths(
    *,
    census_path: Path,
    dane_path: Path,
    catalog_path: Path,
    raw_directory: Path,
    output_directory: Path,
    census_retrieved_at: str,
    dane_retrieved_at: str,
    catalog_retrieved_at: str,
) -> dict[str, object]:
    """Run the complete source-preserving research reproduction from local bytes."""
    census_content = census_path.read_bytes()
    dane_content = dane_path.read_bytes()
    catalog_content = catalog_path.read_bytes()
    validate_pinned_source_bytes(
        census_content,
        label="Registraduria census",
        expected_sha256=PINNED_REGISTRADURIA_SHA256,
        expected_byte_size=PINNED_REGISTRADURIA_BYTE_SIZE,
    )
    validate_pinned_source_bytes(
        dane_content,
        label="DANE projections",
        expected_sha256=PINNED_DANE_SHA256,
        expected_byte_size=PINNED_DANE_BYTE_SIZE,
    )
    validate_pinned_source_bytes(
        catalog_content,
        label="DANE DIVIPOLA catalog",
        expected_sha256=PINNED_DIVIPOLA_SHA256,
        expected_byte_size=PINNED_DIVIPOLA_BYTE_SIZE,
    )
    census_provenance = preserve_source_bytes(
        census_path,
        raw_directory=raw_directory,
        source_url=REGISTRADURIA_CENSUS_URL,
        content_type="application/json",
        retrieved_at=census_retrieved_at,
        retrieval_method="named_playwright_browser_session",
        representation="decoded HTTP response body captured through Playwright response-body",
    )
    dane_provenance = preserve_source_bytes(
        dane_path,
        raw_directory=raw_directory,
        source_url=DANE_PROJECTIONS_URL,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        retrieved_at=dane_retrieved_at,
        retrieval_method="direct_official_https_download",
        representation="exact downloaded XLSX bytes",
    )
    catalog_provenance = preserve_source_bytes(
        catalog_path,
        raw_directory=raw_directory,
        source_url=DIVIPOLA_CATALOG_URL,
        content_type="application/json",
        retrieved_at=catalog_retrieved_at,
        retrieval_method="direct_official_https_feature_service_query",
        representation="exact JSON response bytes from the DANE MGN 2025 Municipio layer",
    )
    census = parse_registraduria_census(census_content)
    population = parse_dane_2025_population(dane_content)
    catalog = parse_divipola_catalog(catalog_content)
    validate_pinned_parsed_sources(census, population, catalog)
    exact_joined = join_by_divipola(census, population, catalog_records=catalog)
    aliases = reviewed_aliases_v1()
    joined = join_by_divipola(census, population, aliases=aliases, catalog_records=catalog)
    assessment = build_claim_assessment(
        census_provenance=census_provenance,
        dane_provenance=dane_provenance,
        census_records=census,
        population_records=population,
        joined=exact_joined,
        expanded_joined=joined,
        catalog_records=catalog,
        catalog_provenance=catalog_provenance,
    )
    outputs = write_research_outputs(
        output_directory,
        joined=joined,
        exact_joined=exact_joined,
        aliases=aliases,
        assessment=assessment,
    )
    return {"assessment": assessment, "outputs": {name: str(path) for name, path in outputs.items()}}
