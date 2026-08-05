"""Registered, research-only replication of a Wald--Wolfowitz runs claim.

The module deliberately states a neutral association result.  A departure from
the within-place random-label null is not evidence of fraud, injection, or an
affected-vote estimate, and it is not connected to audit-priority scoring.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from math import sqrt
from pathlib import Path

import numpy as np

from .fingerprints import derive_analyzer_fingerprint

METHODOLOGY_VERSION = "runs-replication-reference-v1"
ARTIFACT_SCHEMA_VERSION = "runs-replication-artifact-v1"
_MIN_MESAS = 6
_MIN_PERMUTATIONS = 999
_SOURCE = (Path(__file__), Path(__file__).with_name("fingerprints.py"))
CODE_HASH = derive_analyzer_fingerprint(
    analyzer="wald_wolfowitz_runs_replication",
    artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
    source_files=_SOURCE,
    components={
        "null": "within-place-block-permutation-synchronized-max-t",
        "claim": "neutral-research-preview-no-priority-points",
    },
)
METHOD_HASH = derive_analyzer_fingerprint(
    analyzer="wald_wolfowitz_runs_replication",
    artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
    source_files=_SOURCE,
    components={
        "minimum": "six-mesas-two-categories-gaps-break-blocks",
        "multiplicity": "synchronized-max-t-year-round-municipality",
    },
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def runs_family_digest(identifiers: Iterable[str]) -> str:
    values = sorted(identifiers)
    if len(values) != len(set(values)):
        raise ValueError("runs replication mesa identifiers must be unique")
    return _hash(values)


def runs_cohort_digest(
    *, input_artifact_hash: str, expected_family_count: int, expected_family_digest: str
) -> str:
    return _hash(
        {
            "input_artifact_hash": input_artifact_hash,
            "expected_family_count": expected_family_count,
            "expected_family_digest": expected_family_digest,
            "methodology_version": METHODOLOGY_VERSION,
        }
    )


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )


@dataclass(frozen=True)
class RunsMesa:
    """One ordered mesa category; ``category=None`` is an observed sequence gap."""

    mesa_id: str
    municipality_id: str
    polling_place_id: str
    election_year: int
    election_round: str
    sequence_number: int
    category: str | None
    input_artifact_hash: str
    expected_family_count: int
    expected_family_digest: str
    cohort_hash: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(item, str) and item.strip()
            for item in (
                self.mesa_id,
                self.municipality_id,
                self.polling_place_id,
                self.election_round,
            )
        ):
            raise ValueError("runs replication IDs and round are required")
        if type(self.election_year) is not int or not 1900 <= self.election_year <= 2100:
            raise ValueError("runs replication election year is invalid")
        if type(self.sequence_number) is not int:
            raise ValueError("runs replication sequence_number must be an integer")
        if self.category is not None and (
            not isinstance(self.category, str) or not self.category.strip()
        ):
            raise ValueError("runs replication category must be a non-empty string or None")
        if type(self.expected_family_count) is not int or self.expected_family_count < 1:
            raise ValueError("runs replication expected_family_count must be positive")
        if not all(
            _sha256(item)
            for item in (self.input_artifact_hash, self.expected_family_digest, self.cohort_hash)
        ):
            raise ValueError("runs replication artifact bindings must be SHA-256 hashes")


@dataclass(frozen=True)
class RunsReplicationSignal:
    year: int
    round: str
    municipality_id: str
    eligible: bool
    public_point_eligible: bool
    claim_state: str
    reason: str | None
    valid_places: int
    observed_statistic: float | None
    permutation_p_value: float | None
    permutations: int
    permutation_resolution: float | None
    adjustment_method: str
    input_artifact_hash: str
    cohort_hash: str
    expected_family_count: int
    expected_family_digest: str
    code_hash: str = CODE_HASH
    method_hash: str = METHOD_HASH
    methodology_version: str = METHODOLOGY_VERSION
    output_hash: str = ""
    limitations: tuple[str, ...] = (
        "Contextual 2018/2022 comparisons are not accepted as integrity signals.",
        "A runs result is a neutral research association result, never a fraud or injection claim.",
        "This research preview is never eligible for public audit-priority points.",
    )

    def with_hash(self) -> RunsReplicationSignal:
        payload = asdict(self)
        payload.pop("output_hash")
        return replace(self, output_hash=_hash(payload))


def _runs_and_moments(values: list[str]) -> tuple[int, float, float] | None:
    categories = sorted(set(values))
    if len(values) < _MIN_MESAS or len(categories) != 2:
        return None
    first_count = values.count(categories[0])
    second_count = len(values) - first_count
    expected = 1 + 2 * first_count * second_count / len(values)
    variance = (
        2
        * first_count
        * second_count
        * (2 * first_count * second_count - len(values))
        / (len(values) ** 2 * (len(values) - 1))
    )
    if variance <= 0:
        return None
    runs = 1 + sum(values[index] != values[index + 1] for index in range(len(values) - 1))
    return runs, expected, variance


def _place_blocks(rows: list[RunsMesa]) -> tuple[tuple[str, ...], ...]:
    ordered = sorted(rows, key=lambda item: (item.sequence_number, item.mesa_id))
    blocks: list[list[str]] = []
    current: list[str] = []
    previous: int | None = None
    for row in ordered:
        if row.category is None or (previous is not None and row.sequence_number != previous + 1):
            if current:
                blocks.append(current)
            current = []
        if row.category is not None:
            current.append(row.category)
        previous = row.sequence_number
    if current:
        blocks.append(current)
    valid = tuple(tuple(block) for block in blocks if _runs_and_moments(block) is not None)
    return valid


def _place_z(
    blocks: tuple[tuple[str, ...], ...], rng: np.random.Generator | None = None
) -> float | None:
    observed_runs = expected = variance = 0.0
    for raw in blocks:
        values = list(raw)
        if rng is not None:
            values = list(rng.permutation(values))
        moments = _runs_and_moments(values)
        assert moments is not None
        runs, mean, current_variance = moments
        observed_runs += runs
        expected += mean
        variance += current_variance
    return (observed_runs - expected) / sqrt(variance) if variance > 0 else None


def runs_replication_signals(
    records: Iterable[RunsMesa], *, permutations: int = 9_999, seed: int = 0
) -> tuple[RunsReplicationSignal, ...]:
    """Run the preregistered within-place, family-synchronized max-T test."""
    if type(permutations) is not int or permutations < _MIN_PERMUTATIONS:
        raise ValueError("runs replication needs at least 999 permutations")
    if type(seed) is not int or seed < 0:
        raise ValueError("runs replication seed must be a nonnegative integer")
    rows = tuple(sorted(records, key=lambda item: item.mesa_id))
    if not rows:
        return ()
    first = rows[0]
    if len({item.mesa_id for item in rows}) != len(rows):
        raise ValueError("runs replication mesa IDs must be unique")
    if (
        len(rows) != first.expected_family_count
        or runs_family_digest(item.mesa_id for item in rows) != first.expected_family_digest
    ):
        raise ValueError("runs replication requires the declared complete family")
    if any(
        (
            item.input_artifact_hash,
            item.expected_family_count,
            item.expected_family_digest,
            item.cohort_hash,
        )
        != (
            first.input_artifact_hash,
            first.expected_family_count,
            first.expected_family_digest,
            first.cohort_hash,
        )
        for item in rows
    ) or first.cohort_hash != runs_cohort_digest(
        input_artifact_hash=first.input_artifact_hash,
        expected_family_count=first.expected_family_count,
        expected_family_digest=first.expected_family_digest,
    ):
        raise ValueError("runs replication cohort declaration is fragmented or unauthenticated")
    places: dict[tuple[int, str, str, str], list[RunsMesa]] = defaultdict(list)
    for row in rows:
        places[
            (row.election_year, row.election_round, row.municipality_id, row.polling_place_id)
        ].append(row)
    municipal_blocks: dict[tuple[int, str, str], list[tuple[tuple[str, ...], ...]]] = defaultdict(
        list
    )
    for (year, round_, municipality, _place), place_rows in places.items():
        blocks = _place_blocks(place_rows)
        if blocks:
            municipal_blocks[(year, round_, municipality)].append(blocks)
    keys = sorted({(row.election_year, row.election_round, row.municipality_id) for row in rows})
    observed: dict[tuple[int, str, str], float] = {}
    for key, place_values in municipal_blocks.items():
        z_values = [value for blocks in place_values if (value := _place_z(blocks)) is not None]
        if z_values:
            observed[key] = float(sum(z_values) / sqrt(len(z_values)))
    extremes = {key: 0 for key in observed}
    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        maximum = 0.0
        for _key, place_values in municipal_blocks.items():
            z_values = [
                value for blocks in place_values if (value := _place_z(blocks, rng)) is not None
            ]
            if z_values:
                maximum = max(maximum, abs(sum(z_values) / sqrt(len(z_values))))
        for key, value in observed.items():
            extremes[key] += maximum >= abs(value)
    output: list[RunsReplicationSignal] = []
    for year, round_, municipality in keys:
        key = (year, round_, municipality)
        value = observed.get(key)
        places_here = len(municipal_blocks.get(key, ()))
        output.append(
            RunsReplicationSignal(
                year=year,
                round=round_,
                municipality_id=municipality,
                eligible=value is not None,
                public_point_eligible=False,
                claim_state="neutral_research_association",
                reason=None
                if value is not None
                else "fewer_than_six_contiguous_mesas_or_two_categories_within_place",
                valid_places=places_here,
                observed_statistic=value,
                permutation_p_value=(extremes[key] + 1) / (permutations + 1)
                if value is not None
                else None,
                permutations=permutations,
                permutation_resolution=1 / (permutations + 1) if value is not None else None,
                adjustment_method="synchronized-max-t-within-place-permutation",
                input_artifact_hash=first.input_artifact_hash,
                cohort_hash=first.cohort_hash,
                expected_family_count=first.expected_family_count,
                expected_family_digest=first.expected_family_digest,
            ).with_hash()
        )
    return tuple(output)
