"""Research-only longitudinal composition groundwork for 2018 and 2022.

This module deliberately does less than a conventional longitudinal join.  It
compares first round with first round and second round with second round, and
only admits a municipality crosswalk candidate when exact election codes and
normalized exact labels agree.  The result is descriptive context, never
verified physical identity, an integrity inference, or audit-priority evidence.

The historical MMV tables use sparse records: an absent category is unknown,
not zero.  Every metric below is therefore explicitly an
``observed_record_composition`` estimand.  No turnout or valid-vote denominator
is invented.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import polars as pl
import pyarrow.parquet as pq  # type: ignore[import-untyped]

METHODOLOGY_VERSION = "longitudinal-observed-record-composition-v1"
SCHEMA_VERSION = "longitudinal-research-preview-v1"
CROSSWALK_VERSION = "municipality-crosswalk-candidate-v1"
FUTURE_2026_ADAPTER_VERSION = "completed-2026-facts-adapter-v1"

PINNED_RELEASES = {
    2018: "historical-2018-mmv-context-v2-c456aeb032917d5c",
    2022: "historical-2022-mmv-context-v2-705d3d71523003b8",
}
ROUND_PAIRS: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((2018, 1), (2022, 1)),
    ((2018, 2), (2022, 2)),
)

CrosswalkStatus = Literal[
    "high_code_name_descriptive_only",
    "extraterritorial",
    "unmatched",
    "ambiguous",
]
SpecialCategory = Literal["blank", "null", "unmarked"]

_SPECIAL_CATEGORY_BY_CODE: dict[str, SpecialCategory] = {
    "996": "blank",
    "997": "null",
    "998": "unmarked",
}
_EXTRATERRITORIAL_DEPARTMENT_CODES = frozenset({"88"})
_EXTRATERRITORIAL_LABELS = frozenset({"CONSULADOS", "EXTERIOR"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MUNICIPALITY_ID = re.compile(r"^r([12]):mun:([^:]+):([^:]+)$")

ESTIMANDS = (
    {
        "name": "top1_observed_candidate_concentration",
        "scope": "observed_record_composition",
        "numerator": "largest observed candidate-category vote total",
        "denominator": "sum of observed candidate-category vote totals",
        "availability": "unknown when no positive observed candidate-category denominator exists",
    },
    {
        "name": "top2_observed_candidate_concentration",
        "scope": "observed_record_composition",
        "numerator": "sum of the two largest observed candidate-category vote totals",
        "denominator": "sum of observed candidate-category vote totals",
        "availability": "unknown when no positive observed candidate-category denominator exists",
    },
    {
        "name": "observed_candidate_hhi_and_effective_number",
        "scope": "observed_record_composition",
        "numerator": "squared observed candidate-category shares; reciprocal for effective number",
        "denominator": "sum of observed candidate-category vote totals",
        "availability": "unknown when no positive observed candidate-category denominator exists",
    },
    {
        "name": "normalized_observed_candidate_entropy",
        "scope": "observed_record_composition",
        "numerator": "Shannon entropy of observed candidate-category shares",
        "denominator": "log of the number of explicitly observed candidate categories",
        "availability": (
            "zero by convention for one observed category; unknown for no positive denominator"
        ),
    },
    {
        "name": "observed_blank_null_unmarked_composition",
        "scope": "observed_record_composition",
        "numerator": "votes in the explicitly present special-category record",
        "denominator": "sum of all observed category-record vote totals",
        "availability": (
            "unknown when that special category is absent; an explicit zero remains zero"
        ),
    },
)

LIMITATIONS = (
    "Research preview only; it is not a public release and is not selected by a release pointer.",
    "Historical MMV inputs are contextual_baseline/context_only candidate artifacts.",
    "Municipality matches are descriptive candidates based only on exact election codes and "
    "normalized exact labels; they do not verify unchanged physical identity.",
    "The reviewed 2018 XLSX schema contains DEP/MUN codes but no department or municipality "
    "label columns; generated code placeholders are not names, so code coincidence with 2022 "
    "cannot satisfy the exact-label match rule.",
    "Extraterritorial records are excluded from matched-universe coverage and changes.",
    "Split, merge, duplicate-label, and conflicting-label cases abstain as ambiguous.",
    "Mesa codes are never compared across years without official evidence of the same "
    "physical unit.",
    "Absent MMV category rows are unavailable/unknown, never inferred zero.",
    "All denominators are sums of observed category records; they are not turnout, registered "
    "electors, valid votes, or complete expected coverage.",
    "Candidate identities are not linked across elections; only candidate-agnostic composition "
    "summaries are compared.",
    "Historical change contributes zero audit-priority points and supports no integrity inference.",
    "2026 facts are not incorporated; a completed-facts adapter remains disabled until separately "
    "implemented and reviewed.",
)


class LongitudinalError(ValueError):
    """Raised when a research comparison cannot satisfy the frozen contract."""


@dataclass(frozen=True)
class MunicipalityObservation:
    year: int
    round_number: int
    department_code: str
    municipality_code: str
    department_name: str
    municipality_name: str

    def __post_init__(self) -> None:
        if self.year not in {2018, 2022}:
            raise LongitudinalError("municipality observation year must be 2018 or 2022")
        if self.round_number not in {1, 2}:
            raise LongitudinalError("municipality observation round must be 1 or 2")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.department_code,
                self.municipality_code,
                self.department_name,
                self.municipality_name,
            )
        ):
            raise LongitudinalError("municipality observation fields must be non-empty strings")

    @property
    def code_key(self) -> tuple[str, str]:
        return self.department_code, self.municipality_code


@dataclass(frozen=True)
class MunicipalityCrosswalkCandidate:
    round_number: int
    department_code: str
    municipality_code: str
    department_name_2018: str | None
    municipality_name_2018: str | None
    department_name_2022: str | None
    municipality_name_2022: str | None
    normalized_department_name_2018: str | None
    normalized_municipality_name_2018: str | None
    normalized_department_name_2022: str | None
    normalized_municipality_name_2022: str | None
    label_candidates_2018: int
    label_candidates_2022: int
    status: CrosswalkStatus
    match_basis: str
    verified_physical_identity: bool = False
    mesa_code_comparison_allowed: bool = False
    integrity_inference_allowed: bool = False
    audit_priority_points: int = 0
    crosswalk_version: str = CROSSWALK_VERSION


@dataclass(frozen=True)
class ObservedCategoryRecord:
    year: int
    round_number: int
    department_code: str
    municipality_code: str
    department_name: str
    municipality_name: str
    party_code: str
    category_code: str
    category_name: str
    votes: int

    def __post_init__(self) -> None:
        if self.year not in {2018, 2022} or self.round_number not in {1, 2}:
            raise LongitudinalError("observed category record has an unsupported year or round")
        if type(self.votes) is not int or self.votes < 0:
            raise LongitudinalError("observed category votes must be a nonnegative integer")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.department_code,
                self.municipality_code,
                self.department_name,
                self.municipality_name,
                self.party_code,
                self.category_code,
                self.category_name,
            )
        ):
            raise LongitudinalError("observed category fields must be non-empty strings")


@dataclass(frozen=True)
class ObservedRecordComposition:
    year: int
    round_number: int
    department_code: str
    municipality_code: str
    department_name: str
    municipality_name: str
    estimand_scope: str
    observed_category_record_count: int
    observed_candidate_category_count: int
    observed_record_votes: int
    observed_candidate_category_votes: int
    top1_observed_candidate_concentration: float | None
    top2_observed_candidate_concentration: float | None
    observed_candidate_hhi: float | None
    observed_candidate_effective_number: float | None
    normalized_observed_candidate_entropy: float | None
    blank_record_present: bool
    blank_observed_votes: int | None
    blank_observed_record_composition: float | None
    null_record_present: bool
    null_observed_votes: int | None
    null_observed_record_composition: float | None
    unmarked_record_present: bool
    unmarked_observed_votes: int | None
    unmarked_observed_record_composition: float | None
    candidate_denominator_label: str = "sum_of_observed_candidate_category_votes"
    special_category_denominator_label: str = "sum_of_all_observed_category_record_votes"
    expected_physical_coverage: str = "unknown"
    integrity_inference_allowed: bool = False
    audit_priority_points: int = 0
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class DescriptiveCompositionChange:
    round_number: int
    department_code: str
    municipality_code: str
    crosswalk_status: CrosswalkStatus
    estimand_scope: str
    delta_top1_observed_candidate_concentration: float | None
    delta_top2_observed_candidate_concentration: float | None
    delta_observed_candidate_hhi: float | None
    delta_observed_candidate_effective_number: float | None
    delta_normalized_observed_candidate_entropy: float | None
    delta_blank_observed_record_composition: float | None
    delta_null_observed_record_composition: float | None
    delta_unmarked_observed_record_composition: float | None
    interpretation: str = "2022_minus_2018_descriptive_observed_record_composition"
    verified_physical_identity: bool = False
    integrity_inference_allowed: bool = False
    audit_priority_points: int = 0
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class MatchedUniverseCoverage:
    round_number: int
    comparison_pair: str
    observed_municipalities_2018: int
    observed_municipalities_2022: int
    domestic_observed_municipalities_2018: int
    domestic_observed_municipalities_2022: int
    high_code_name_descriptive_only: int
    provisional_code_candidate_excluded: int
    extraterritorial: int
    unmatched: int
    ambiguous: int
    matched_share_of_2018_domestic_observed_universe: float | None
    matched_share_of_2022_domestic_observed_universe: float | None
    expected_physical_coverage_2018: str = "unknown"
    expected_physical_coverage_2022: str = "unknown"
    coverage_kind: str = "observed_municipality_candidate_coverage_not_physical_coverage"


@dataclass(frozen=True)
class HistoricalArtifactBinding:
    dataset_id: str
    filename: str
    content_hash: str
    byte_size: int
    record_count: int


@dataclass(frozen=True)
class HistoricalInputBinding:
    year: int
    release_id: str
    manifest_filename: str
    manifest_hash: str
    source_artifact_hashes: tuple[str, ...]
    parquet_artifacts: tuple[HistoricalArtifactBinding, ...]
    source_type: str = "contextual_baseline"
    legal_status: str = "context_only"


@dataclass(frozen=True)
class LoadedHistoricalRelease:
    binding: HistoricalInputBinding
    municipalities: tuple[MunicipalityObservation, ...]
    category_records: tuple[ObservedCategoryRecord, ...]


@dataclass(frozen=True)
class FutureCompleted2026FactsAdapter:
    """Metadata-only contract for a later, separately reviewed 2026 adapter."""

    adapter_version: str
    round_number: int
    release_id: str
    release_manifest_hash: str
    facts_artifact_hash: str
    expected_universe_hash: str
    facts_complete: bool
    expected_coverage_verified: bool
    sparse_category_semantics_declared: bool


@dataclass(frozen=True)
class LongitudinalResearchPreview:
    input_releases: tuple[HistoricalInputBinding, ...]
    crosswalk: tuple[MunicipalityCrosswalkCandidate, ...]
    compositions: tuple[ObservedRecordComposition, ...]
    descriptive_changes: tuple[DescriptiveCompositionChange, ...]
    coverage: tuple[MatchedUniverseCoverage, ...]
    crosswalk_rows_hash: str
    composition_rows_hash: str
    descriptive_change_rows_hash: str
    artifact_hash: str = ""
    schema_version: str = SCHEMA_VERSION
    methodology_version: str = METHODOLOGY_VERSION
    crosswalk_version: str = CROSSWALK_VERSION
    research_only: bool = True
    public_release: bool = False
    current_2026_included: bool = False
    verified_physical_identity: bool = False
    integrity_inference_allowed: bool = False
    audit_priority_points: int = 0
    limitations: tuple[str, ...] = LIMITATIONS

    def artifact_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "methodology_version": self.methodology_version,
            "crosswalk_version": self.crosswalk_version,
            "research_only": self.research_only,
            "public_release": self.public_release,
            "current_2026_included": self.current_2026_included,
            "verified_physical_identity": self.verified_physical_identity,
            "integrity_inference_allowed": self.integrity_inference_allowed,
            "audit_priority_points": self.audit_priority_points,
            "round_pairs": ROUND_PAIRS,
            "input_releases": [asdict(value) for value in self.input_releases],
            "coverage": [asdict(value) for value in self.coverage],
            "crosswalk": {
                "row_count": len(self.crosswalk),
                "rows_hash": self.crosswalk_rows_hash,
            },
            "compositions": {
                "row_count": len(self.compositions),
                "rows_hash": self.composition_rows_hash,
            },
            "descriptive_changes": {
                "row_count": len(self.descriptive_changes),
                "rows_hash": self.descriptive_change_rows_hash,
            },
            "estimands": ESTIMANDS,
            "limitations": self.limitations,
            "mesa_code_policy": "excluded_without_official_same_physical_unit_evidence",
            "source_schema_evidence": {
                "2018": {
                    "reviewed_source_container": "XLSX",
                    "department_code_column": "DEP",
                    "municipality_code_column": "MUN",
                    "department_label_column": None,
                    "municipality_label_column": None,
                    "generated_code_placeholders_are_names": False,
                },
                "2022": {
                    "reviewed_source_container": "CSV",
                    "department_code_column": "DEP",
                    "municipality_code_column": "MUN",
                    "department_label_column": "DEPNOMBRE",
                    "municipality_label_column": "MUNNOMBRE",
                },
            },
            "historical_geography_adapter_contract": {
                "status": "verified_geography_crosswalk_required",
                "code_only_bridge_allowed": False,
                "2022_or_2026_labels_may_backfill_2018": False,
                "required_before_changes": (
                    "independently reviewed 2018 municipality labels or an official versioned "
                    "geography crosswalk with explicit split/merge dispositions"
                ),
            },
            "future_2026_adapter_contract": {
                "adapter_version": FUTURE_2026_ADAPTER_VERSION,
                "status": "disabled_not_implemented",
                "requires_completed_facts": True,
                "requires_verified_expected_coverage": True,
                "requires_exact_release_and_artifact_hashes": True,
                "requires_declared_sparse_category_semantics": True,
            },
        }

    def with_hash(self) -> LongitudinalResearchPreview:
        return replace(self, artifact_hash=_hash_json(self.artifact_payload()))


ResearchRow = (
    MunicipalityCrosswalkCandidate | ObservedRecordComposition | DescriptiveCompositionChange
)


def normalize_exact_label(value: str) -> str:
    """Normalize accents, case, punctuation, and whitespace without fuzzy matching."""
    if not isinstance(value, str) or not value.strip():
        raise LongitudinalError("exact-label normalization requires a non-empty string")
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    tokens = "".join(character if character.isalnum() else " " for character in unaccented)
    return " ".join(tokens.upper().split())


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hash_rows(rows: Iterable[ResearchRow]) -> str:
    return _hash_json([vars(row) for row in rows])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_float(value: float) -> float:
    return round(value, 15)


def _optional_delta(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return _stable_float(later - earlier)


def _special_values(
    category: SpecialCategory,
    present: set[SpecialCategory],
    totals: Mapping[SpecialCategory, int],
    observed_votes: int,
) -> tuple[bool, int | None, float | None]:
    if category not in present:
        return False, None, None
    votes = totals[category]
    share = _stable_float(votes / observed_votes) if observed_votes > 0 else None
    return True, votes, share


def _is_extraterritorial(
    department_code: str,
    department_names: Iterable[str],
) -> bool:
    if department_code in _EXTRATERRITORIAL_DEPARTMENT_CODES:
        return True
    return any(normalize_exact_label(name) in _EXTRATERRITORIAL_LABELS for name in department_names)


def _is_placeholder_label(value: str) -> bool:
    normalized = normalize_exact_label(value)
    return normalized.startswith("OFFICIAL DEPARTMENT CODE ") or normalized.startswith(
        "OFFICIAL MUNICIPALITY CODE "
    )


def _index_municipalities(
    observations: Iterable[MunicipalityObservation],
    *,
    year: int,
    round_number: int,
) -> dict[tuple[str, str], set[tuple[str, str, str, str]]]:
    result: dict[tuple[str, str], set[tuple[str, str, str, str]]] = defaultdict(set)
    for observation in observations:
        if observation.year != year or observation.round_number != round_number:
            raise LongitudinalError(
                f"crosswalk side must contain only {year} round {round_number} observations"
            )
        result[observation.code_key].add(
            (
                observation.department_name,
                observation.municipality_name,
                normalize_exact_label(observation.department_name),
                normalize_exact_label(observation.municipality_name),
            )
        )
    return result


def build_municipality_crosswalk(
    observations_2018: Iterable[MunicipalityObservation],
    observations_2022: Iterable[MunicipalityObservation],
    *,
    round_number: int,
) -> tuple[MunicipalityCrosswalkCandidate, ...]:
    """Build a conservative municipality candidate crosswalk for one like-for-like round."""
    if round_number not in {1, 2}:
        raise LongitudinalError("longitudinal comparisons support only rounds 1 and 2")
    left = _index_municipalities(
        observations_2018,
        year=2018,
        round_number=round_number,
    )
    right = _index_municipalities(
        observations_2022,
        year=2022,
        round_number=round_number,
    )

    ambiguous_keys: set[tuple[str, str]] = {
        key for key, labels in (*left.items(), *right.items()) if len(labels) != 1
    }
    for index in (left, right):
        keys_by_label: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        for key, candidates in index.items():
            if len(candidates) == 1:
                candidate = next(iter(candidates))
                keys_by_label[(candidate[2], candidate[3])].add(key)
        for keys in keys_by_label.values():
            if len(keys) > 1:
                ambiguous_keys.update(keys)

    rows: list[MunicipalityCrosswalkCandidate] = []
    for department_code, municipality_code in sorted(set(left) | set(right)):
        key = (department_code, municipality_code)
        left_values = left.get(key, set())
        right_values = right.get(key, set())
        left_value = next(iter(left_values)) if len(left_values) == 1 else None
        right_value = next(iter(right_values)) if len(right_values) == 1 else None
        department_names = (
            *(value[0] for value in left_values),
            *(value[0] for value in right_values),
        )

        if _is_extraterritorial(department_code, department_names):
            status: CrosswalkStatus = "extraterritorial"
            basis = "extraterritorial_department_excluded"
        elif key in ambiguous_keys:
            status = "ambiguous"
            basis = "conflicting_or_split_merge_exact_labels_abstain"
        elif left_value is None or right_value is None:
            status = "unmatched"
            basis = "code_absent_from_one_observed_round_universe"
        elif _is_placeholder_label(left_value[0]) or _is_placeholder_label(left_value[1]):
            status = "unmatched"
            basis = "provisional_code_candidate_excluded"
        elif (left_value[2], left_value[3]) != (right_value[2], right_value[3]):
            status = "unmatched"
            basis = "exact_code_present_but_normalized_exact_label_mismatch"
        else:
            status = "high_code_name_descriptive_only"
            basis = "exact_election_codes_and_normalized_exact_labels"

        rows.append(
            MunicipalityCrosswalkCandidate(
                round_number=round_number,
                department_code=department_code,
                municipality_code=municipality_code,
                department_name_2018=left_value[0] if left_value else None,
                municipality_name_2018=left_value[1] if left_value else None,
                department_name_2022=right_value[0] if right_value else None,
                municipality_name_2022=right_value[1] if right_value else None,
                normalized_department_name_2018=left_value[2] if left_value else None,
                normalized_municipality_name_2018=left_value[3] if left_value else None,
                normalized_department_name_2022=right_value[2] if right_value else None,
                normalized_municipality_name_2022=right_value[3] if right_value else None,
                label_candidates_2018=len(left_values),
                label_candidates_2022=len(right_values),
                status=status,
                match_basis=basis,
            )
        )
    return tuple(rows)


def observed_record_compositions(
    records: Iterable[ObservedCategoryRecord],
) -> tuple[ObservedRecordComposition, ...]:
    """Compute composition conditional only on explicitly observed category records."""
    grouped: dict[tuple[int, int, str, str, str, str], list[ObservedCategoryRecord]] = defaultdict(
        list
    )
    for record in records:
        key = (
            record.year,
            record.round_number,
            record.department_code,
            record.municipality_code,
            record.department_name,
            record.municipality_name,
        )
        grouped[key].append(record)

    result: list[ObservedRecordComposition] = []
    for key, rows in sorted(grouped.items()):
        candidate_totals: dict[tuple[str, str, str], int] = defaultdict(int)
        special_totals: dict[SpecialCategory, int] = defaultdict(int)
        special_present: set[SpecialCategory] = set()
        observed_votes = 0
        for row in rows:
            observed_votes += row.votes
            special = _SPECIAL_CATEGORY_BY_CODE.get(row.category_code)
            if special is None:
                candidate_totals[
                    (row.party_code, row.category_code, normalize_exact_label(row.category_name))
                ] += row.votes
            else:
                special_present.add(special)
                special_totals[special] += row.votes

        candidate_votes = sum(candidate_totals.values())
        top1: float | None = None
        top2: float | None = None
        hhi: float | None = None
        effective: float | None = None
        entropy: float | None = None
        if candidate_votes > 0 and candidate_totals:
            shares = sorted(
                (votes / candidate_votes for votes in candidate_totals.values()),
                reverse=True,
            )
            top1 = _stable_float(shares[0])
            top2 = _stable_float(sum(shares[:2]))
            hhi = _stable_float(sum(share * share for share in shares))
            effective = _stable_float(1 / hhi)
            if len(shares) == 1:
                entropy = 0.0
            else:
                raw_entropy = -sum(share * math.log(share) for share in shares if share > 0)
                entropy = _stable_float(raw_entropy / math.log(len(shares)))

        blank_present, blank_votes, blank_share = _special_values(
            "blank", special_present, special_totals, observed_votes
        )
        null_present, null_votes, null_share = _special_values(
            "null", special_present, special_totals, observed_votes
        )
        unmarked_present, unmarked_votes, unmarked_share = _special_values(
            "unmarked", special_present, special_totals, observed_votes
        )
        result.append(
            ObservedRecordComposition(
                year=key[0],
                round_number=key[1],
                department_code=key[2],
                municipality_code=key[3],
                department_name=key[4],
                municipality_name=key[5],
                estimand_scope="observed_record_composition",
                observed_category_record_count=len(rows),
                observed_candidate_category_count=len(candidate_totals),
                observed_record_votes=observed_votes,
                observed_candidate_category_votes=candidate_votes,
                top1_observed_candidate_concentration=top1,
                top2_observed_candidate_concentration=top2,
                observed_candidate_hhi=hhi,
                observed_candidate_effective_number=effective,
                normalized_observed_candidate_entropy=entropy,
                blank_record_present=blank_present,
                blank_observed_votes=blank_votes,
                blank_observed_record_composition=blank_share,
                null_record_present=null_present,
                null_observed_votes=null_votes,
                null_observed_record_composition=null_share,
                unmarked_record_present=unmarked_present,
                unmarked_observed_votes=unmarked_votes,
                unmarked_observed_record_composition=unmarked_share,
            )
        )
    return tuple(result)


def descriptive_composition_changes(
    crosswalk: Iterable[MunicipalityCrosswalkCandidate],
    compositions: Iterable[ObservedRecordComposition],
) -> tuple[DescriptiveCompositionChange, ...]:
    """Compare only high-status same-round municipality composition candidates."""
    by_key = {
        (row.year, row.round_number, row.department_code, row.municipality_code): row
        for row in compositions
    }
    changes: list[DescriptiveCompositionChange] = []
    for match in sorted(
        crosswalk,
        key=lambda row: (row.round_number, row.department_code, row.municipality_code),
    ):
        if match.status != "high_code_name_descriptive_only":
            continue
        earlier = by_key.get(
            (2018, match.round_number, match.department_code, match.municipality_code)
        )
        later = by_key.get(
            (2022, match.round_number, match.department_code, match.municipality_code)
        )
        if earlier is None or later is None:
            continue
        changes.append(
            DescriptiveCompositionChange(
                round_number=match.round_number,
                department_code=match.department_code,
                municipality_code=match.municipality_code,
                crosswalk_status=match.status,
                estimand_scope="observed_record_composition",
                delta_top1_observed_candidate_concentration=_optional_delta(
                    later.top1_observed_candidate_concentration,
                    earlier.top1_observed_candidate_concentration,
                ),
                delta_top2_observed_candidate_concentration=_optional_delta(
                    later.top2_observed_candidate_concentration,
                    earlier.top2_observed_candidate_concentration,
                ),
                delta_observed_candidate_hhi=_optional_delta(
                    later.observed_candidate_hhi,
                    earlier.observed_candidate_hhi,
                ),
                delta_observed_candidate_effective_number=_optional_delta(
                    later.observed_candidate_effective_number,
                    earlier.observed_candidate_effective_number,
                ),
                delta_normalized_observed_candidate_entropy=_optional_delta(
                    later.normalized_observed_candidate_entropy,
                    earlier.normalized_observed_candidate_entropy,
                ),
                delta_blank_observed_record_composition=_optional_delta(
                    later.blank_observed_record_composition,
                    earlier.blank_observed_record_composition,
                ),
                delta_null_observed_record_composition=_optional_delta(
                    later.null_observed_record_composition,
                    earlier.null_observed_record_composition,
                ),
                delta_unmarked_observed_record_composition=_optional_delta(
                    later.unmarked_observed_record_composition,
                    earlier.unmarked_observed_record_composition,
                ),
            )
        )
    return tuple(changes)


def _coverage(
    crosswalk: Sequence[MunicipalityCrosswalkCandidate],
    observations: Sequence[MunicipalityObservation],
) -> tuple[MatchedUniverseCoverage, ...]:
    result: list[MatchedUniverseCoverage] = []
    for round_number in (1, 2):
        round_crosswalk = [row for row in crosswalk if row.round_number == round_number]
        keys_by_year = {
            year: {
                row.code_key
                for row in observations
                if row.year == year and row.round_number == round_number
            }
            for year in (2018, 2022)
        }
        domestic_keys_by_year = {
            year: {
                row.code_key
                for row in observations
                if row.year == year
                and row.round_number == round_number
                and not _is_extraterritorial(row.department_code, (row.department_name,))
            }
            for year in (2018, 2022)
        }
        status_counts = {
            status: sum(row.status == status for row in round_crosswalk)
            for status in (
                "high_code_name_descriptive_only",
                "extraterritorial",
                "unmatched",
                "ambiguous",
            )
        }
        matched = status_counts["high_code_name_descriptive_only"]
        provisional_code_candidates = sum(
            row.match_basis == "provisional_code_candidate_excluded" for row in round_crosswalk
        )
        denominator_2018 = len(domestic_keys_by_year[2018])
        denominator_2022 = len(domestic_keys_by_year[2022])
        share_2018 = _stable_float(matched / denominator_2018) if denominator_2018 else None
        share_2022 = _stable_float(matched / denominator_2022) if denominator_2022 else None

        result.append(
            MatchedUniverseCoverage(
                round_number=round_number,
                comparison_pair=f"2018-r{round_number}_to_2022-r{round_number}",
                observed_municipalities_2018=len(keys_by_year[2018]),
                observed_municipalities_2022=len(keys_by_year[2022]),
                domestic_observed_municipalities_2018=len(domestic_keys_by_year[2018]),
                domestic_observed_municipalities_2022=len(domestic_keys_by_year[2022]),
                high_code_name_descriptive_only=matched,
                provisional_code_candidate_excluded=provisional_code_candidates,
                extraterritorial=status_counts["extraterritorial"],
                unmatched=status_counts["unmatched"],
                ambiguous=status_counts["ambiguous"],
                matched_share_of_2018_domestic_observed_universe=share_2018,
                matched_share_of_2022_domestic_observed_universe=share_2022,
            )
        )
    return tuple(result)


def build_longitudinal_preview(
    release_2018: LoadedHistoricalRelease,
    release_2022: LoadedHistoricalRelease,
    *,
    future_2026_adapter: FutureCompleted2026FactsAdapter | None = None,
) -> LongitudinalResearchPreview:
    """Build an immutable research preview; 2026 integration is intentionally disabled."""
    if release_2018.binding.year != 2018 or release_2022.binding.year != 2022:
        raise LongitudinalError("longitudinal preview requires 2018 followed by 2022")
    if future_2026_adapter is not None:
        reject_future_2026_adapter(future_2026_adapter)

    observations = tuple(
        sorted(
            (*release_2018.municipalities, *release_2022.municipalities),
            key=lambda row: (
                row.year,
                row.round_number,
                row.department_code,
                row.municipality_code,
                row.department_name,
                row.municipality_name,
            ),
        )
    )
    crosswalk = tuple(
        row
        for round_number in (1, 2)
        for row in build_municipality_crosswalk(
            (row for row in release_2018.municipalities if row.round_number == round_number),
            (row for row in release_2022.municipalities if row.round_number == round_number),
            round_number=round_number,
        )
    )
    compositions = observed_record_compositions(
        (*release_2018.category_records, *release_2022.category_records)
    )
    changes = descriptive_composition_changes(crosswalk, compositions)
    preview = LongitudinalResearchPreview(
        input_releases=tuple(
            sorted((release_2018.binding, release_2022.binding), key=lambda value: value.year)
        ),
        crosswalk=crosswalk,
        compositions=compositions,
        descriptive_changes=changes,
        coverage=_coverage(crosswalk, observations),
        crosswalk_rows_hash=_hash_rows(crosswalk),
        composition_rows_hash=_hash_rows(compositions),
        descriptive_change_rows_hash=_hash_rows(changes),
    )
    return preview.with_hash()


def reject_future_2026_adapter(adapter: FutureCompleted2026FactsAdapter) -> None:
    """Validate the future contract, then fail because integration is not implemented."""
    if adapter.adapter_version != FUTURE_2026_ADAPTER_VERSION:
        raise LongitudinalError("future 2026 adapter version is not frozen")
    if adapter.round_number not in {1, 2}:
        raise LongitudinalError("future 2026 adapter round must be 1 or 2")
    if not adapter.release_id.strip():
        raise LongitudinalError("future 2026 adapter release_id is required")
    for value in (
        adapter.release_manifest_hash,
        adapter.facts_artifact_hash,
        adapter.expected_universe_hash,
    ):
        if not _SHA256.fullmatch(value):
            raise LongitudinalError("future 2026 adapter hashes must be lowercase SHA-256")
    if not (
        adapter.facts_complete
        and adapter.expected_coverage_verified
        and adapter.sparse_category_semantics_declared
    ):
        raise LongitudinalError("future 2026 adapter requires completed, coverage-verified facts")
    raise LongitudinalError(
        "2026 longitudinal integration is disabled until a separate reviewed implementation exists"
    )


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise LongitudinalError(f"{label} must be an object with string keys")
    return cast(dict[str, object], value)


def _string(mapping: Mapping[str, object], key: str, *, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise LongitudinalError(f"{label} {key} must be a non-empty string")
    return value


def _integer(mapping: Mapping[str, object], key: str, *, label: str) -> int:
    value = mapping.get(key)
    if type(value) is not int or value < 0:
        raise LongitudinalError(f"{label} {key} must be a nonnegative integer")
    return value


def _manifest_items(mapping: Mapping[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise LongitudinalError(f"manifest {key} must be a list")
    return tuple(_mapping(item, label=f"manifest {key} item") for item in value)


def _verify_parquet_artifacts(
    manifest: Mapping[str, object],
    release_directory: Path,
    *,
    year: int,
) -> tuple[HistoricalArtifactBinding, ...]:
    expected = {
        f"historical-{year}-mmv-parquet": f"historical-{year}-mmv.parquet",
        f"historical-{year}-rollups-parquet": f"historical-{year}-rollups.parquet",
        f"historical-{year}-geography-parquet": f"historical-{year}-geography.parquet",
    }
    datasets = _manifest_items(manifest, "datasets")
    if {item.get("id") for item in datasets} != set(expected):
        raise LongitudinalError(
            "historical manifest must bind exactly three reviewed Parquet datasets"
        )
    bindings: list[HistoricalArtifactBinding] = []
    for dataset in datasets:
        dataset_id = _string(dataset, "id", label="dataset")
        if dataset.get("format") != "parquet":
            raise LongitudinalError("historical comparison accepts only Parquet datasets")
        content_hash = _string(dataset, "content_hash", label="dataset")
        if not _SHA256.fullmatch(content_hash):
            raise LongitudinalError("dataset content_hash must be lowercase SHA-256")
        path = release_directory / expected[dataset_id]
        if not path.is_file():
            raise LongitudinalError(f"historical Parquet artifact is missing: {path.name}")
        byte_size = _integer(dataset, "byte_size", label="dataset")
        record_count = _integer(dataset, "record_count", label="dataset")
        if path.stat().st_size != byte_size:
            raise LongitudinalError(f"historical Parquet byte size mismatch: {path.name}")
        if _sha256_file(path) != content_hash:
            raise LongitudinalError(f"historical Parquet content hash mismatch: {path.name}")
        parquet_rows = int(pq.ParquetFile(path).metadata.num_rows)
        if parquet_rows != record_count:
            raise LongitudinalError(f"historical Parquet record count mismatch: {path.name}")
        bindings.append(
            HistoricalArtifactBinding(
                dataset_id=dataset_id,
                filename=path.name,
                content_hash=content_hash,
                byte_size=byte_size,
                record_count=record_count,
            )
        )
    return tuple(sorted(bindings, key=lambda item: item.dataset_id))


def _source_hashes(manifest: Mapping[str, object], *, year: int) -> dict[int, str]:
    result: dict[int, str] = {}
    for source in _manifest_items(manifest, "sources"):
        expected_prefix = f"registraduria-observatorio-{year}-round-"
        source_id = _string(source, "id", label="source")
        if not source_id.startswith(expected_prefix):
            raise LongitudinalError("historical source id does not match its year")
        try:
            round_number = int(source_id.removeprefix(expected_prefix))
        except ValueError as exc:
            raise LongitudinalError("historical source round is invalid") from exc
        content_hash = _string(source, "content_hash", label="source")
        if (
            round_number not in {1, 2}
            or round_number in result
            or not _SHA256.fullmatch(content_hash)
            or source.get("source_type") != "contextual_baseline"
            or source.get("legal_status") != "context_only"
        ):
            raise LongitudinalError("historical source provenance is invalid")
        result[round_number] = content_hash
    if set(result) != {1, 2}:
        raise LongitudinalError("historical source manifest must contain rounds 1 and 2 exactly")
    return result


def _provenance_ok(
    *,
    year: int,
    round_number: int,
    election_slug: object,
    content_hash: object,
    data_version: object,
    source_type: object,
    legal_status: object,
    release_id: str,
    source_hashes: Mapping[int, str],
) -> bool:
    return (
        round_number in {1, 2}
        and election_slug == f"presidencia-{year}-round-{round_number}"
        and content_hash == source_hashes[round_number]
        and data_version == release_id
        and source_type == "contextual_baseline"
        and legal_status == "context_only"
    )


def _load_municipalities(
    path: Path,
    *,
    year: int,
    release_id: str,
    source_hashes: Mapping[int, str],
) -> tuple[MunicipalityObservation, ...]:
    department_names: dict[tuple[int, str], str] = {}
    departments = pl.read_parquet(
        path,
        columns=["round", "level", "code", "name"],
    ).filter(pl.col("level") == "department")
    for round_value, _level, code, name in departments.iter_rows():
        if type(round_value) is not int or not isinstance(code, str) or not isinstance(name, str):
            raise LongitudinalError("department geography fields are invalid")
        key = (round_value, code)
        if key in department_names and department_names[key] != name:
            raise LongitudinalError("conflicting department geography labels")
        department_names[key] = name

    frame = pl.read_parquet(
        path,
        columns=[
            "round",
            "election_slug",
            "level",
            "id",
            "code",
            "name",
            "parent_id",
            "content_hash",
            "data_version",
            "source_type",
            "legal_status",
        ],
    ).filter(pl.col("level") == "municipality")
    result: list[MunicipalityObservation] = []
    seen: set[tuple[object, ...]] = set()
    for values in frame.iter_rows():
        (
            round_value,
            election_slug,
            _level,
            geography_id,
            municipality_code,
            municipality_name,
            parent_id,
            content_hash,
            data_version,
            source_type,
            legal_status,
        ) = values
        if type(round_value) is not int:
            raise LongitudinalError("geography round is invalid")
        round_number = round_value
        if not all(
            isinstance(value, str)
            for value in (
                geography_id,
                municipality_code,
                municipality_name,
                parent_id,
            )
        ):
            raise LongitudinalError("geography municipality fields are invalid")
        match = _MUNICIPALITY_ID.fullmatch(geography_id)
        if (
            match is None
            or int(match.group(1)) != round_number
            or match.group(3) != municipality_code
            or parent_id != f"r{round_number}:dep:{match.group(2)}"
            or not _provenance_ok(
                year=year,
                round_number=round_number,
                election_slug=election_slug,
                content_hash=content_hash,
                data_version=data_version,
                source_type=source_type,
                legal_status=legal_status,
                release_id=release_id,
                source_hashes=source_hashes,
            )
        ):
            raise LongitudinalError("geography municipality identity or provenance is invalid")
        identity = (
            round_number,
            match.group(2),
            municipality_code,
            municipality_name,
        )
        if identity in seen:
            raise LongitudinalError("duplicate municipality geography record")
        seen.add(identity)
        department_name = department_names.get((round_number, match.group(2)))
        if department_name is None:
            raise LongitudinalError("municipality geography lacks its department parent")
        result.append(
            MunicipalityObservation(
                year=year,
                round_number=round_number,
                department_code=match.group(2),
                municipality_code=municipality_code,
                department_name=department_name,
                municipality_name=municipality_name,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda row: (
                row.round_number,
                row.department_code,
                row.municipality_code,
                row.municipality_name,
            ),
        )
    )


def _load_category_records(
    path: Path,
    *,
    year: int,
    release_id: str,
    source_hashes: Mapping[int, str],
    municipalities: Sequence[MunicipalityObservation],
) -> tuple[ObservedCategoryRecord, ...]:
    municipality_by_key = {
        (row.round_number, row.department_code, row.municipality_code): row
        for row in municipalities
    }
    frame = pl.read_parquet(
        path,
        columns=[
            "round",
            "election_slug",
            "geography_level",
            "geography_id",
            "category_code",
            "category_name",
            "party_code",
            "votes",
            "content_hash",
            "data_version",
            "source_type",
            "legal_status",
        ],
    ).filter(pl.col("geography_level") == "municipality")
    result: list[ObservedCategoryRecord] = []
    seen: set[tuple[object, ...]] = set()
    for values in frame.iter_rows():
        (
            round_value,
            election_slug,
            _level,
            geography_id,
            category_code,
            category_name,
            party_code,
            votes,
            content_hash,
            data_version,
            source_type,
            legal_status,
        ) = values
        if type(round_value) is not int or type(votes) is not int:
            raise LongitudinalError("rollup round or votes are invalid")
        round_number = round_value
        if not all(
            isinstance(value, str)
            for value in (geography_id, category_code, category_name, party_code)
        ):
            raise LongitudinalError("rollup category fields are invalid")
        match = _MUNICIPALITY_ID.fullmatch(geography_id)
        if (
            match is None
            or int(match.group(1)) != round_number
            or not _provenance_ok(
                year=year,
                round_number=round_number,
                election_slug=election_slug,
                content_hash=content_hash,
                data_version=data_version,
                source_type=source_type,
                legal_status=legal_status,
                release_id=release_id,
                source_hashes=source_hashes,
            )
        ):
            raise LongitudinalError("municipality rollup identity or provenance is invalid")
        municipality = municipality_by_key.get((round_number, match.group(2), match.group(3)))
        if municipality is None:
            raise LongitudinalError("municipality rollup lacks a geography record")
        semantic_key = (
            round_number,
            match.group(2),
            match.group(3),
            party_code,
            category_code,
        )
        if semantic_key in seen:
            raise LongitudinalError("duplicate municipality/category rollup record")
        seen.add(semantic_key)
        result.append(
            ObservedCategoryRecord(
                year=year,
                round_number=round_number,
                department_code=match.group(2),
                municipality_code=match.group(3),
                department_name=municipality.department_name,
                municipality_name=municipality.municipality_name,
                party_code=party_code,
                category_code=category_code,
                category_name=category_name,
                votes=votes,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda row: (
                row.round_number,
                row.department_code,
                row.municipality_code,
                row.party_code,
                row.category_code,
            ),
        )
    )


def load_historical_release(
    manifest_path: Path,
    release_directory: Path,
    *,
    year: int,
) -> LoadedHistoricalRelease:
    """Read and content-verify one historical manifest and its three Parquet artifacts."""
    if year not in {2018, 2022}:
        raise LongitudinalError("historical longitudinal inputs support only 2018 and 2022")
    try:
        parsed: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LongitudinalError("historical manifest cannot be read") from exc
    manifest = _mapping(parsed, label="historical manifest")
    release_id = _string(manifest, "release_id", label="manifest")
    if (
        manifest.get("data_version") != release_id
        or not release_id.startswith(f"historical-{year}-mmv-context-")
        or manifest.get("synthetic") is not False
        or manifest.get("statistical_validation_passed") is not False
    ):
        raise LongitudinalError("historical manifest is not a fail-closed context candidate")
    source_hashes = _source_hashes(manifest, year=year)
    artifacts = _verify_parquet_artifacts(manifest, release_directory, year=year)
    artifact_by_id = {item.dataset_id: release_directory / item.filename for item in artifacts}
    municipalities = _load_municipalities(
        artifact_by_id[f"historical-{year}-geography-parquet"],
        year=year,
        release_id=release_id,
        source_hashes=source_hashes,
    )
    records = _load_category_records(
        artifact_by_id[f"historical-{year}-rollups-parquet"],
        year=year,
        release_id=release_id,
        source_hashes=source_hashes,
        municipalities=municipalities,
    )
    binding = HistoricalInputBinding(
        year=year,
        release_id=release_id,
        manifest_filename=manifest_path.name,
        manifest_hash=_sha256_file(manifest_path),
        source_artifact_hashes=tuple(source_hashes[round_number] for round_number in (1, 2)),
        parquet_artifacts=artifacts,
    )
    return LoadedHistoricalRelease(binding, municipalities, records)


def build_default_preview(repository_root: Path = Path(".")) -> LongitudinalResearchPreview:
    """Build from the two pinned, real local historical candidate releases."""
    loaded: dict[int, LoadedHistoricalRelease] = {}
    for year, release_id in PINNED_RELEASES.items():
        loaded[year] = load_historical_release(
            repository_root / "data" / "manifests" / f"{release_id}.json",
            repository_root / "data" / "releases" / release_id,
            year=year,
        )
    return build_longitudinal_preview(loaded[2018], loaded[2022])


_CROSSWALK_SCHEMA = pl.Schema(
    {
        "round_number": pl.Int8,
        "department_code": pl.String,
        "municipality_code": pl.String,
        "department_name_2018": pl.String,
        "municipality_name_2018": pl.String,
        "department_name_2022": pl.String,
        "municipality_name_2022": pl.String,
        "normalized_department_name_2018": pl.String,
        "normalized_municipality_name_2018": pl.String,
        "normalized_department_name_2022": pl.String,
        "normalized_municipality_name_2022": pl.String,
        "label_candidates_2018": pl.Int16,
        "label_candidates_2022": pl.Int16,
        "status": pl.String,
        "match_basis": pl.String,
        "verified_physical_identity": pl.Boolean,
        "mesa_code_comparison_allowed": pl.Boolean,
        "integrity_inference_allowed": pl.Boolean,
        "audit_priority_points": pl.Int8,
        "crosswalk_version": pl.String,
    }
)

_COMPOSITION_SCHEMA = pl.Schema(
    {
        "year": pl.Int16,
        "round_number": pl.Int8,
        "department_code": pl.String,
        "municipality_code": pl.String,
        "department_name": pl.String,
        "municipality_name": pl.String,
        "estimand_scope": pl.String,
        "observed_category_record_count": pl.Int32,
        "observed_candidate_category_count": pl.Int16,
        "observed_record_votes": pl.Int64,
        "observed_candidate_category_votes": pl.Int64,
        "top1_observed_candidate_concentration": pl.Float64,
        "top2_observed_candidate_concentration": pl.Float64,
        "observed_candidate_hhi": pl.Float64,
        "observed_candidate_effective_number": pl.Float64,
        "normalized_observed_candidate_entropy": pl.Float64,
        "blank_record_present": pl.Boolean,
        "blank_observed_votes": pl.Int64,
        "blank_observed_record_composition": pl.Float64,
        "null_record_present": pl.Boolean,
        "null_observed_votes": pl.Int64,
        "null_observed_record_composition": pl.Float64,
        "unmarked_record_present": pl.Boolean,
        "unmarked_observed_votes": pl.Int64,
        "unmarked_observed_record_composition": pl.Float64,
        "candidate_denominator_label": pl.String,
        "special_category_denominator_label": pl.String,
        "expected_physical_coverage": pl.String,
        "integrity_inference_allowed": pl.Boolean,
        "audit_priority_points": pl.Int8,
        "methodology_version": pl.String,
    }
)

_CHANGE_SCHEMA = pl.Schema(
    {
        "round_number": pl.Int8,
        "department_code": pl.String,
        "municipality_code": pl.String,
        "crosswalk_status": pl.String,
        "estimand_scope": pl.String,
        "delta_top1_observed_candidate_concentration": pl.Float64,
        "delta_top2_observed_candidate_concentration": pl.Float64,
        "delta_observed_candidate_hhi": pl.Float64,
        "delta_observed_candidate_effective_number": pl.Float64,
        "delta_normalized_observed_candidate_entropy": pl.Float64,
        "delta_blank_observed_record_composition": pl.Float64,
        "delta_null_observed_record_composition": pl.Float64,
        "delta_unmarked_observed_record_composition": pl.Float64,
        "interpretation": pl.String,
        "verified_physical_identity": pl.Boolean,
        "integrity_inference_allowed": pl.Boolean,
        "audit_priority_points": pl.Int8,
        "methodology_version": pl.String,
    }
)


def _write_parquet(path: Path, rows: Sequence[ResearchRow], schema: pl.Schema) -> None:
    material = [vars(row) for row in rows]
    frame = pl.DataFrame(material, schema=schema, strict=True)
    frame.write_parquet(
        path,
        compression="zstd",
        compression_level=9,
        statistics=True,
        row_group_size=65_536,
    )


def write_research_preview(
    preview: LongitudinalResearchPreview,
    output_directory: Path,
) -> dict[str, Path]:
    """Write deterministic non-public JSON/Parquet research artifacts."""
    if not preview.artifact_hash or preview != preview.with_hash():
        raise LongitudinalError("research preview artifact hash is invalid")
    output_directory.mkdir(parents=True, exist_ok=True)
    crosswalk_path = output_directory / "municipality-crosswalk-candidate-v1.parquet"
    composition_path = output_directory / "observed-record-composition-v1.parquet"
    changes_path = output_directory / "descriptive-composition-changes-v1.parquet"
    _write_parquet(crosswalk_path, preview.crosswalk, _CROSSWALK_SCHEMA)
    _write_parquet(composition_path, preview.compositions, _COMPOSITION_SCHEMA)
    _write_parquet(changes_path, preview.descriptive_changes, _CHANGE_SCHEMA)
    output_artifacts = tuple(
        {
            "filename": path.name,
            "content_hash": _sha256_file(path),
            "byte_size": path.stat().st_size,
            "record_count": count,
            "format": "parquet",
        }
        for path, count in (
            (crosswalk_path, len(preview.crosswalk)),
            (composition_path, len(preview.compositions)),
            (changes_path, len(preview.descriptive_changes)),
        )
    )
    manifest_payload = {
        **preview.artifact_payload(),
        "research_artifact_hash": preview.artifact_hash,
        "output_artifacts": output_artifacts,
    }
    manifest_path = output_directory / "longitudinal-research-preview-v1.json"
    manifest_path.write_text(_canonical_json(manifest_payload) + "\n", encoding="utf-8")
    return {
        "manifest": manifest_path,
        "crosswalk": crosswalk_path,
        "compositions": composition_path,
        "changes": changes_path,
    }


def generate_default_research_preview(
    repository_root: Path = Path("."),
) -> dict[str, Path]:
    """Generate the pinned preview under the ignored research workspace."""
    preview = build_default_preview(repository_root)
    return write_research_preview(
        preview,
        repository_root / ".pipeline" / "research" / "longitudinal",
    )


if __name__ == "__main__":
    generated = generate_default_research_preview()
    print(_canonical_json({name: str(path) for name, path in generated.items()}))
