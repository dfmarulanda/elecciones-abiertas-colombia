"""Source-bound spatial residual screening with conditional random-label nulls.

The unit of inference is a mesa only when coordinates are mesa-grain.  Polling
place coordinates are collapsed to an explicit polling-place analysis unit, so
co-located mesas are never counted as independent neighbours or tests.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import numpy as np
from scipy.spatial import cKDTree  # type: ignore[import-untyped]

from .fingerprints import derive_analyzer_fingerprint
from .peer_signals import METHODOLOGY_VERSION as PEER_METHODOLOGY_VERSION

_MIN_UNITS_PER_MUNICIPALITY = 100
_MIN_PERMUTATIONS = 9_999
_MAX_ADAPTIVE_PERMUTATIONS = 99_999
_MIN_NEIGHBORS = 3
_MAX_NEIGHBORS = 5
_MAX_NEIGHBOR_DISTANCE_KM = 20.0
_MIN_LOCAL_EFFECT_SIZE = 0.25
_MAX_COORDINATE_ACCURACY_M = 500.0
# Public so downstream evidence boundaries can enforce the same frozen floor
# without copying a caller-owned literal.
MIN_PERMUTATIONS = _MIN_PERMUTATIONS
MAX_COORDINATE_ACCURACY_M = _MAX_COORDINATE_ACCURACY_M
_ADJUSTMENT_METHOD = "synchronized-max-t-permutation"
_ALLOWED_ELECTIONS = frozenset({"presidencia-2026-r2", "presidencia-2026-segunda-vuelta"})
METHODOLOGY_VERSION = "spatial-residual-v5"
_ARTIFACT_SCHEMA_VERSION = "spatial-signal-artifact-v7"
_ANALYZER_SOURCES = (
    Path(__file__),
    Path(__file__).with_name("fingerprints.py"),
    Path(__file__).with_name("peer_signals.py"),
)
_CODE_HASH = derive_analyzer_fingerprint(
    analyzer="spatial_residual_signals",
    artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
    source_files=_ANALYZER_SOURCES,
    components={
        "adjustment": "synchronized-max-t-permutation",
        "artifact": "SpatialSignal",
        "coordinates": (
            "same-municipality-fixed-row-standardized-five-nearest-within-20km-"
            "accuracy-at-most-500m"
        ),
        "null": "synchronized-family-max-t-within-municipality-blocks-minimum-9999-adaptive-99999",
        "peer_residual_contract": PEER_METHODOLOGY_VERSION,
    },
)
_METHOD_HASH = derive_analyzer_fingerprint(
    analyzer="spatial_residual_signals",
    artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
    source_files=_ANALYZER_SOURCES,
    components={
        "adjustment": "synchronized-max-t-permutation",
        "decision_rule": "p001-q05-local-moran-effect025",
        "null": "synchronized-family-max-t-within-municipality-blocks-minimum-9999-adaptive-99999",
        "peer_residual_contract": PEER_METHODOLOGY_VERSION,
    },
)
CODE_HASH = _CODE_HASH
METHOD_HASH = _METHOD_HASH
ARTIFACT_SCHEMA_VERSION = _ARTIFACT_SCHEMA_VERSION
Metric = Literal["turnout", "candidate_share", "blank", "null_unmarked"]
_METRICS = frozenset({"turnout", "candidate_share", "blank", "null_unmarked"})
_COORDINATE_GRAINS = frozenset({"mesa", "polling_place"})
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
    "contextual_baseline": "context_only",
}


@dataclass(frozen=True)
class SpatialMesa:
    mesa_id: str
    municipality_id: str
    latitude: float | None
    longitude: float | None
    residual: float
    peer_residual_artifact_hash: str
    election_slug: str
    data_version: str
    source_layer: str
    source_type: str
    legal_status: str
    metric: Metric
    candidate_id: str | None
    peer_methodology_version: str
    coordinate_source_url: str
    coordinate_source_hash: str
    coordinate_accuracy_m: float
    coordinate_grain: Literal["mesa", "polling_place"]
    expected_family_count: int
    expected_family_digest: str
    expected_mesa_count: int
    expected_mesa_digest: str
    expected_mesa_membership_digest: str
    cohort_hash: str
    spatial_unit_id: str | None = None
    cross_border: bool = False
    source_links: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mesa_id, str) or not self.mesa_id.strip():
            raise ValueError("spatial mesa and municipality ids are required")
        if not isinstance(self.municipality_id, str) or not self.municipality_id.strip():
            raise ValueError("spatial mesa and municipality ids are required")
        if isinstance(self.residual, bool) or not isinstance(self.residual, (int, float)):
            raise ValueError("spatial residual must be finite")
        if not isfinite(self.residual):
            raise ValueError("spatial residual must be finite")
        if self.latitude is not None and (
            isinstance(self.latitude, bool)
            or not isinstance(self.latitude, (int, float))
            or not isfinite(self.latitude)
            or not -90 <= self.latitude <= 90
        ):
            raise ValueError("latitude is outside its valid range")
        if self.longitude is not None and (
            isinstance(self.longitude, bool)
            or not isinstance(self.longitude, (int, float))
            or not isfinite(self.longitude)
            or not -180 <= self.longitude <= 180
        ):
            raise ValueError("longitude is outside its valid range")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("coordinates must be supplied together")
        if not _https_url(self.coordinate_source_url):
            raise ValueError("coordinates need an HTTPS source URL")
        if not (_sha256(self.coordinate_source_hash) and _sha256(self.peer_residual_artifact_hash)):
            raise ValueError("coordinate and peer residual artifacts need SHA-256 hashes")
        if (
            isinstance(self.coordinate_accuracy_m, bool)
            or not isinstance(self.coordinate_accuracy_m, (int, float))
            or not isfinite(self.coordinate_accuracy_m)
            or self.coordinate_accuracy_m <= 0
        ):
            raise ValueError("coordinate accuracy must be a positive finite number")
        if not all(
            isinstance(value, str) and value
            for value in (
                self.election_slug,
                self.data_version,
                self.source_layer,
                self.peer_methodology_version,
            )
        ):
            raise ValueError("spatial family and peer methodology fields are required")
        if self.source_layer in {"context_only", "contextual_baseline"}:
            raise ValueError("contextual source layers cannot be used for analytics")
        if self.source_type == "contextual_baseline" or self.legal_status == "context_only":
            raise ValueError("contextual inputs cannot be used for spatial analytics")
        if self.source_type not in _SOURCE_LEGAL_STATUS:
            raise ValueError("spatial source_type is invalid")
        if self.legal_status != _SOURCE_LEGAL_STATUS[self.source_type]:
            raise ValueError("spatial source_type/legal_status is incompatible")
        if self.source_layer != self.source_type:
            raise ValueError("spatial source_layer must equal its canonical source_type")
        if self.election_slug not in _ALLOWED_ELECTIONS:
            raise ValueError("election/round is not allowlisted for spatial analytics")
        if self.metric == "candidate_share":
            if (
                not isinstance(self.candidate_id, str)
                or not self.candidate_id
                or "|" in self.candidate_id
            ):
                raise ValueError("candidate_id is required for candidate-share spatial inputs")
        elif self.candidate_id is not None:
            raise ValueError("candidate_id must be null for noncandidate spatial metrics")
        if self.metric not in _METRICS:
            raise ValueError("spatial metric is invalid")
        if self.coordinate_grain not in _COORDINATE_GRAINS:
            raise ValueError("coordinate_grain must be mesa or polling_place")
        if self.coordinate_grain == "polling_place" and (
            not isinstance(self.spatial_unit_id, str) or not self.spatial_unit_id
        ):
            raise ValueError("polling-place coordinates require a spatial_unit_id")
        if self.coordinate_grain == "mesa" and self.spatial_unit_id is not None:
            raise ValueError("mesa coordinates cannot claim a different spatial_unit_id")
        if self.peer_methodology_version != PEER_METHODOLOGY_VERSION:
            raise ValueError("spatial inputs require the frozen peer methodology")
        if "|" in self.data_version or "|" in self.source_layer:
            raise ValueError("spatial family identifiers cannot contain '|'")
        if type(self.expected_family_count) is not int or self.expected_family_count < 1:
            raise ValueError("expected_family_count must be positive")
        if type(self.expected_mesa_count) is not int or self.expected_mesa_count < 1:
            raise ValueError("expected_mesa_count must be positive")
        if not all(
            _sha256(value)
            for value in (
                self.expected_family_digest,
                self.expected_mesa_digest,
                self.expected_mesa_membership_digest,
                self.cohort_hash,
            )
        ):
            raise ValueError("spatial expected families and cohort need SHA-256 digests")
        if type(self.cross_border) is not bool:
            raise ValueError("cross_border must be boolean")
        if any(not _https_url(link) for link in self.source_links):
            raise ValueError("spatial source links must be absolute HTTPS URLs")


@dataclass(frozen=True)
class SpatialSignal:
    mesa_id: str
    analysis_unit_id: str
    eligible: bool
    signal: bool
    signal_kind: Literal["positive_cluster", "negative_spatial_contrast"] | None
    reason: str | None
    neighbors: tuple[str, ...]
    local_residual: float | None
    permutation_p_value: float | None
    adjusted_q_value: float | None
    family_id: str
    family_size: int
    family_rank: int | None
    adjustment_method: str
    randomization_seed: int | None
    permutations: int
    peer_residual_artifact_hash: str
    coordinate_source_url: str
    coordinate_source_hash: str
    coordinate_accuracy_m: float
    coordinate_grain: Literal["mesa", "polling_place"]
    input_artifact_hash: str
    election_slug: str
    data_version: str
    source_layer: str
    source_type: str
    legal_status: str
    metric: Metric
    candidate_id: str | None
    peer_methodology_version: str
    expected_family_count: int
    expected_family_digest: str
    analysis_unit_digest: str
    expected_mesa_count: int
    expected_mesa_digest: str
    mesa_membership_digest: str
    expected_mesa_membership_digest: str
    cohort_hash: str
    code_hash: str
    method_hash: str
    output_hash: str = ""
    methodology_version: str = METHODOLOGY_VERSION
    limitations: tuple[str, ...] = (
        "Conditional random-label spatial screening is a review lead, not proof of an error.",
        "Spatial signals never estimate affected votes.",
        "Public scoring requires an independently authenticated external family ledger; "
        "row-declared counts and digests cannot self-certify it.",
    )
    observed_value: float | None = None
    comparator: str = ""
    calculation: str = (
        "row-standardized local Moran-style residual statistic under a joint "
        "within-municipality random-label null with synchronized family max-T correction"
    )
    peer_definition: str = (
        "fixed row-standardized five-nearest same-municipality analysis units within 20 km"
    )
    source_links: tuple[str, ...] = ()
    permutation_resolution: float | None = None
    minimum_effect_size: float = _MIN_LOCAL_EFFECT_SIZE
    research_signal: bool = False
    public_point_eligible: bool = False
    family_ledger_status: str = "external_registry_required_unverified"


@dataclass(frozen=True)
class _Unit:
    unit_id: str
    municipality_id: str
    latitude: float
    longitude: float
    residual: float
    mesas: tuple[SpatialMesa, ...]


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _family_id(row: SpatialMesa) -> str:
    candidate = row.candidate_id if row.metric == "candidate_share" else "none"
    assert candidate is not None
    return "|".join((row.data_version, row.election_slug, row.source_layer, row.metric, candidate))


def _municipality_seed(row: SpatialMesa, municipality_id: str) -> int:
    material = f"{row.data_version}|{_family_id(row)}|{municipality_id}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _distance_km(left: _Unit, right: _Unit) -> float:
    radius = 6371.0088
    delta_lat = radians(right.latitude - left.latitude)
    delta_lon = radians(right.longitude - left.longitude)
    a = (
        sin(delta_lat / 2) ** 2
        + cos(radians(left.latitude)) * cos(radians(right.latitude)) * sin(delta_lon / 2) ** 2
    )
    return 2 * radius * asin(sqrt(a))


def _xyz(units: list[_Unit]) -> np.ndarray:
    latitude = np.radians(np.asarray([unit.latitude for unit in units]))
    longitude = np.radians(np.asarray([unit.longitude for unit in units]))
    return np.column_stack(
        (
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        )
    )


def _valid(row: SpatialMesa) -> bool:
    return bool(
        row.latitude is not None
        and row.longitude is not None
        and not row.cross_border
        and row.coordinate_accuracy_m <= _MAX_COORDINATE_ACCURACY_M
    )


def spatial_family_digest(identifiers: Iterable[str]) -> str:
    """Canonical digest of the expected analysis-unit IDs."""
    values = sorted(identifiers)
    if len(set(values)) != len(values):
        raise ValueError("analysis-unit IDs used for a spatial digest must be unique")
    encoded = json.dumps(values, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def spatial_mesa_digest(identifiers: Iterable[str]) -> str:
    """Canonical digest of the exact expected mesa IDs before any collapse."""
    values = sorted(identifiers)
    if len(set(values)) != len(values):
        raise ValueError("mesa IDs used for a spatial digest must be unique")
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def _analysis_unit_id(row: SpatialMesa) -> str:
    return row.mesa_id if row.coordinate_grain == "mesa" else str(row.spatial_unit_id)


def spatial_mesa_membership_digest(records: Iterable[SpatialMesa]) -> str:
    """Bind every mesa, its unit assignment, and all spatial input values.

    Declaration hashes (expected digests and cohort) are deliberately excluded
    so the declaration can verify this digest without a circular dependency.
    """
    rows = tuple(sorted(records, key=lambda row: row.mesa_id))
    if len({row.mesa_id for row in rows}) != len(rows):
        raise ValueError("spatial mesa membership requires unique mesa IDs")
    payload = [
        {
            "analysis_unit_id": _analysis_unit_id(row),
            "coordinate_accuracy_m": float(row.coordinate_accuracy_m),
            "coordinate_grain": row.coordinate_grain,
            "coordinate_source_hash": row.coordinate_source_hash,
            "coordinate_source_url": row.coordinate_source_url,
            "cross_border": row.cross_border,
            "latitude": None if row.latitude is None else float(row.latitude),
            "longitude": None if row.longitude is None else float(row.longitude),
            "mesa_id": row.mesa_id,
            "municipality_id": row.municipality_id,
            "peer_residual_artifact_hash": row.peer_residual_artifact_hash,
            "residual": float(row.residual),
            "source_links": sorted(set(row.source_links)),
        }
        for row in rows
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def spatial_cohort_digest(
    *,
    peer_residual_artifact_hash: str,
    election_slug: str,
    data_version: str,
    source_layer: str,
    source_type: str,
    legal_status: str,
    metric: Metric,
    candidate_id: str | None,
    peer_methodology_version: str,
    coordinate_source_url: str,
    coordinate_source_hash: str,
    coordinate_accuracy_m: float,
    coordinate_grain: Literal["mesa", "polling_place"],
    expected_family_count: int,
    expected_family_digest: str,
    expected_mesa_count: int,
    expected_mesa_digest: str,
    expected_mesa_membership_digest: str,
) -> str:
    """Hash the exact residual/co-ordinate family declaration."""
    payload = {
        "candidate_id": candidate_id,
        "coordinate_accuracy_m": float(coordinate_accuracy_m),
        "coordinate_grain": coordinate_grain,
        "coordinate_source_hash": coordinate_source_hash,
        "coordinate_source_url": coordinate_source_url,
        "data_version": data_version,
        "election_slug": election_slug,
        "expected_family_count": expected_family_count,
        "expected_family_digest": expected_family_digest,
        "expected_mesa_count": expected_mesa_count,
        "expected_mesa_digest": expected_mesa_digest,
        "expected_mesa_membership_digest": expected_mesa_membership_digest,
        "legal_status": legal_status,
        "metric": metric,
        "peer_methodology_version": peer_methodology_version,
        "peer_residual_artifact_hash": peer_residual_artifact_hash,
        "source_layer": source_layer,
        "source_type": source_type,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _units(rows: tuple[SpatialMesa, ...]) -> tuple[dict[str, _Unit], dict[str, str]]:
    """Return explicit analysis units and fail-closed row reasons."""
    grouped: dict[str, list[SpatialMesa]] = defaultdict(list)
    reasons: dict[str, str] = {}
    for row in rows:
        if not _valid(row):
            reasons[row.mesa_id] = (
                "coordinate_accuracy_above_500m"
                if row.coordinate_accuracy_m > _MAX_COORDINATE_ACCURACY_M
                else "poor_geocode_or_cross_border"
            )
            continue
        unit_id = _analysis_unit_id(row)
        grouped[unit_id].append(row)
    candidates: dict[str, _Unit] = {}
    for unit_id, group in grouped.items():
        first = group[0]
        assert first.latitude is not None and first.longitude is not None
        if any(
            row.municipality_id != first.municipality_id
            or row.latitude != first.latitude
            or row.longitude != first.longitude
            or row.coordinate_grain != first.coordinate_grain
            for row in group
        ):
            for row in group:
                reasons[row.mesa_id] = "inconsistent_coordinate_analysis_unit"
            continue
        candidates[unit_id] = _Unit(
            unit_id,
            first.municipality_id,
            first.latitude,
            first.longitude,
            float(np.mean([row.residual for row in group])),
            tuple(sorted(group, key=lambda row: row.mesa_id)),
        )
    by_coordinate: dict[tuple[str, float, float], list[_Unit]] = defaultdict(list)
    for unit in candidates.values():
        by_coordinate[(unit.municipality_id, unit.latitude, unit.longitude)].append(unit)
    result: dict[str, _Unit] = {}
    for coordinate_units in by_coordinate.values():
        if len(coordinate_units) > 1:
            for unit in coordinate_units:
                for row in unit.mesas:
                    reasons[row.mesa_id] = "co_located_analysis_units"
            continue
        unit = coordinate_units[0]
        result[unit.unit_id] = unit
    return result, reasons


def _neighbors(units: list[_Unit]) -> dict[str, tuple[str, ...]]:
    """Build the fixed within-municipality 5-NN row-standardized graph.

    The returned IDs are the non-zero entries of a row of ``W``.  Every row
    receives equal weight ``1 / len(neighbors)`` when its local Moran-style
    statistic is calculated; ties are resolved by analysis-unit ID.
    """
    tree = cKDTree(_xyz(units))
    output: dict[str, tuple[str, ...]] = {}
    for index, unit in enumerate(units):
        distances, _ = tree.query(_xyz([unit])[0], k=min(6, len(units)))
        boundary = float(np.atleast_1d(distances)[-1]) + 1e-12
        candidates = tree.query_ball_point(_xyz([unit])[0], boundary)
        ordered = sorted(
            (
                (other.unit_id, _distance_km(unit, other))
                for candidate in candidates
                if candidate != index
                for other in (units[candidate],)
                if _distance_km(unit, other) <= _MAX_NEIGHBOR_DISTANCE_KM
            ),
            key=lambda item: (item[1], item[0]),
        )
        output[unit.unit_id] = tuple(identifier for identifier, _ in ordered[:_MAX_NEIGHBORS])
    return output


def _local_moran_values(
    centered_residuals: np.ndarray, neighbor_indices: tuple[tuple[int, ...], ...]
) -> np.ndarray:
    """Calculate all local Moran-style values for a fixed row-standardized W."""
    variance = float(np.mean(centered_residuals**2))
    if variance <= np.finfo(float).eps:
        return np.zeros(len(centered_residuals), dtype=float)
    values = np.empty(len(centered_residuals), dtype=float)
    for index, indices in enumerate(neighbor_indices):
        values[index] = (
            centered_residuals[index] * float(np.mean(centered_residuals[list(indices)])) / variance
        )
    return values


def _joint_permutation_p_values(
    centered_residuals: np.ndarray,
    neighbor_indices: tuple[tuple[int, ...], ...],
    *,
    seed: int,
    permutations: int,
    max_permutations: int,
) -> tuple[np.ndarray, int]:
    """Jointly permute all municipality labels and recompute every local I.

    A single residual-label permutation is used for every analysis unit in a
    municipality.  The first 9,999 draws establish a public resolution of at
    least 1/10,000.  Only a family with a potentially reportable raw tail is
    extended to 99,999 draws, preserving one shared null family and avoiding
    needless compute for unremarkable municipalities.
    """
    observed = _local_moran_values(centered_residuals, neighbor_indices)
    extreme = np.zeros(len(centered_residuals), dtype=np.int64)
    rng = np.random.default_rng(seed)
    completed = 0
    target = permutations
    size = len(centered_residuals)
    variance = float(np.mean(centered_residuals**2))
    while completed < target:
        batch = min(256, target - completed)
        # Sorting independent continuous uniforms gives a deterministic,
        # independent full permutation in every row without focal conditioning.
        labels = np.argsort(rng.random((batch, size)), axis=1)
        permuted = centered_residuals[labels]
        if variance <= np.finfo(float).eps:
            statistics = np.zeros((batch, size), dtype=float)
        else:
            statistics = np.empty((batch, size), dtype=float)
            for index, indices in enumerate(neighbor_indices):
                statistics[:, index] = (
                    permuted[:, index] * np.mean(permuted[:, list(indices)], axis=1) / variance
                )
        extreme += np.sum(np.abs(statistics) >= np.abs(observed), axis=0, dtype=np.int64)
        completed += batch
        if completed == permutations:
            provisional = (extreme + 1) / (completed + 1)
            if np.any(provisional <= 0.01) and target < max_permutations:
                target = max_permutations
    return (extreme + 1) / (completed + 1), completed


def _synchronized_max_t_p_values(
    blocks: tuple[tuple[np.ndarray, tuple[tuple[int, ...], ...], tuple[int, ...]], ...],
    *,
    seed: int,
    permutations: int,
    max_permutations: int,
) -> tuple[tuple[np.ndarray, ...], int]:
    """Single-step max-|T| calibration across all preregistered units.

    Every draw independently shuffles labels *within* each municipality block,
    then uses the maximum absolute local statistic over the whole submitted
    family.  This is a synchronized Westfall--Young style correction: it does
    not turn separately simulated marginal p-values into a second adjustment.
    """
    observed = tuple(_local_moran_values(values, neighbors) for values, neighbors, _ in blocks)
    observed_flat = np.concatenate(
        tuple(
            values[list(indexes)] for values, (_, _, indexes) in zip(observed, blocks, strict=True)
        )
    )
    extremes = np.zeros(len(observed_flat), dtype=np.int64)
    rng = np.random.default_rng(seed)
    completed = 0
    target = permutations
    while completed < target:
        batch = min(128, target - completed)
        maxima = np.zeros(batch, dtype=float)
        for centered, neighbors, indexes in blocks:
            size = len(centered)
            labels = np.argsort(rng.random((batch, size)), axis=1)
            permuted = centered[labels]
            variance = float(np.mean(centered**2))
            if variance <= np.finfo(float).eps:
                continue
            statistics = np.empty((batch, len(neighbors)), dtype=float)
            for index, local_neighbors in enumerate(neighbors):
                statistics[:, index] = (
                    permuted[:, index]
                    * np.mean(permuted[:, list(local_neighbors)], axis=1)
                    / variance
                )
            maxima = np.maximum(maxima, np.max(np.abs(statistics[:, list(indexes)]), axis=1))
        extremes += np.sum(maxima[:, None] >= np.abs(observed_flat), axis=0, dtype=np.int64)
        completed += batch
        if completed == permutations and target < max_permutations:
            provisional = (extremes + 1) / (completed + 1)
            if np.any(provisional <= 0.01):
                target = max_permutations
    p_values = (extremes + 1) / (completed + 1)
    result: list[np.ndarray] = []
    cursor = 0
    for _, _, indexes in blocks:
        current = np.ones(len(indexes), dtype=float)
        length = len(indexes)
        current[:] = p_values[cursor : cursor + length]
        result.append(current)
        cursor += length
    return tuple(result), completed


def _family_seed(row: SpatialMesa) -> int:
    material = (
        f"{row.data_version}|{_family_id(row)}|{row.expected_family_digest}|synchronized-max-t-v1"
    ).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _canonical_output_hash(signal: SpatialSignal) -> str:
    payload = asdict(signal)
    payload.pop("output_hash")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def input_artifact_hash(
    *,
    peer_residual_artifact_hash: str,
    coordinate_source_hash: str,
    analysis_unit_digest: str,
    mesa_membership_digest: str,
) -> str:
    """Bind source artifacts and exact mesas/residuals supplied to the analyzer."""
    payload = {
        "analysis_unit_digest": analysis_unit_digest,
        "coordinate_source_hash": coordinate_source_hash,
        "mesa_membership_digest": mesa_membership_digest,
        "peer_residual_artifact_hash": peer_residual_artifact_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _by_adjust(p_values: list[float]) -> tuple[list[float], list[int]]:
    if not p_values:
        return [], []
    order = np.argsort(np.asarray(p_values), kind="stable")
    m = len(order)
    harmonic = float(np.sum(1 / np.arange(1, m + 1)))
    adjusted = np.empty(m)
    running = 1.0
    for index in range(m - 1, -1, -1):
        running = min(running, float(p_values[int(order[index])]) * m * harmonic / (index + 1))
        adjusted[index] = running
    values = np.empty(m)
    ranks = np.empty(m, dtype=int)
    values[order] = adjusted
    ranks[order] = np.arange(1, m + 1)
    return [float(value) for value in values], [int(rank) for rank in ranks]


def spatial_residual_signals(
    records: Iterable[SpatialMesa],
    *,
    permutations: int = _MIN_PERMUTATIONS,
    max_permutations: int = _MAX_ADAPTIVE_PERMUTATIONS,
    minimum_effect_size: float = _MIN_LOCAL_EFFECT_SIZE,
) -> tuple[SpatialSignal, ...]:
    """Screen full residual families using a municipality-conditional local-I null.

    Coordinates only define a fixed, same-municipality graph.  Residual labels
    are jointly permuted within each municipality; no score is calculated for
    invalid geocodes, cross-border rows, sparse units, or municipalities with
    fewer than 100 eligible mesas.
    """
    if (
        isinstance(permutations, bool)
        or not isinstance(permutations, int)
        or permutations < _MIN_PERMUTATIONS
    ):
        raise ValueError("spatial v2 requires at least 9,999 permutations")
    if (
        isinstance(max_permutations, bool)
        or not isinstance(max_permutations, int)
        or max_permutations < permutations
    ):
        raise ValueError("maximum spatial permutations must be an integer at least the minimum")
    if (
        isinstance(minimum_effect_size, bool)
        or not isinstance(minimum_effect_size, (int, float))
        or not isfinite(float(minimum_effect_size))
        or float(minimum_effect_size) < _MIN_LOCAL_EFFECT_SIZE
    ):
        raise ValueError("minimum spatial effect size cannot weaken the frozen production gate")
    rows = tuple(sorted(records, key=lambda row: row.mesa_id))
    if not rows:
        return ()
    if len({row.mesa_id for row in rows}) != len(rows):
        raise ValueError("mesa_id must be unique")
    expected_unit_ids = {_analysis_unit_id(row) for row in rows}
    if (
        len(expected_unit_ids) != rows[0].expected_family_count
        or spatial_family_digest(expected_unit_ids) != rows[0].expected_family_digest
    ):
        raise ValueError("supplied spatial family does not match expected unit count and digest")
    mesa_ids = [row.mesa_id for row in rows]
    if (
        len(rows) != rows[0].expected_mesa_count
        or spatial_mesa_digest(mesa_ids) != rows[0].expected_mesa_digest
    ):
        raise ValueError("supplied spatial family does not match exact expected mesa IDs")
    actual_membership_digest = spatial_mesa_membership_digest(rows)
    if actual_membership_digest != rows[0].expected_mesa_membership_digest:
        raise ValueError(
            "supplied spatial mesas do not match the declared membership and input digest"
        )
    family = {
        (
            row.peer_residual_artifact_hash,
            row.election_slug,
            row.data_version,
            row.source_layer,
            row.source_type,
            row.legal_status,
            row.metric,
            row.candidate_id,
            row.peer_methodology_version,
            row.coordinate_source_url,
            row.coordinate_source_hash,
            row.coordinate_accuracy_m,
            row.coordinate_grain,
            row.expected_family_count,
            row.expected_family_digest,
            row.expected_mesa_count,
            row.expected_mesa_digest,
            row.expected_mesa_membership_digest,
            row.cohort_hash,
        )
        for row in rows
    }
    if len(family) != 1:
        raise ValueError("spatial calls cannot fragment an immutable peer-residual family")
    first = rows[0]
    expected_cohort = spatial_cohort_digest(
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
        expected_family_count=first.expected_family_count,
        expected_family_digest=first.expected_family_digest,
        expected_mesa_count=first.expected_mesa_count,
        expected_mesa_digest=first.expected_mesa_digest,
        expected_mesa_membership_digest=first.expected_mesa_membership_digest,
    )
    if first.cohort_hash != expected_cohort:
        raise ValueError("spatial cohort_hash does not match the immutable family declaration")
    canonical_input_artifact_hash = input_artifact_hash(
        peer_residual_artifact_hash=first.peer_residual_artifact_hash,
        coordinate_source_hash=first.coordinate_source_hash,
        analysis_unit_digest=first.expected_family_digest,
        mesa_membership_digest=actual_membership_digest,
    )
    units, reasons = _units(rows)
    municipality_units: dict[str, list[_Unit]] = defaultdict(list)
    for unit in units.values():
        municipality_units[unit.municipality_id].append(unit)
    neighbors: dict[str, tuple[str, ...]] = {}
    for _municipality, items in municipality_units.items():
        neighbors.update(_neighbors(sorted(items, key=lambda item: item.unit_id)))
    municipality_eligible_mesas = {
        municipality_id: sum(
            len(unit.mesas) for unit in items if len(neighbors[unit.unit_id]) >= _MIN_NEIGHBORS
        )
        for municipality_id, items in municipality_units.items()
    }
    municipality_eligible_units = {
        municipality_id: sum(len(neighbors[unit.unit_id]) >= _MIN_NEIGHBORS for unit in items)
        for municipality_id, items in municipality_units.items()
    }
    eligible_units = {
        unit_id: unit
        for unit_id, unit in units.items()
        if (
            len(neighbors[unit_id]) >= _MIN_NEIGHBORS
            and municipality_eligible_mesas[unit.municipality_id] >= _MIN_UNITS_PER_MUNICIPALITY
            and municipality_eligible_units[unit.municipality_id] >= _MIN_UNITS_PER_MUNICIPALITY
        )
    }

    raw: dict[str, tuple[float, tuple[str, ...]]] = {}
    permutation_blocks: list[tuple[np.ndarray, tuple[tuple[int, ...], ...], tuple[int, ...]]] = []
    scorable_ids: list[tuple[str, ...]] = []
    for _municipality_id, items in municipality_units.items():
        all_units_here = sorted(items, key=lambda item: item.unit_id)
        units_here = [unit for unit in all_units_here if unit.unit_id in eligible_units]
        if not units_here:
            continue
        # The exchangeability pool is every valid unit in the municipality,
        # including units that are not themselves scorable.  Only the fixed-W
        # statistic rows below are excluded from testing.
        centered = np.asarray([unit.residual for unit in all_units_here], dtype=float)
        centered -= float(np.mean(centered))
        lookup = {unit.unit_id: index for index, unit in enumerate(all_units_here)}
        scorable = units_here
        # The null recomputes the whole scorable statistic family under each
        # joint label permutation.  Isolated units deliberately remain absent.
        # Sparse rows receive a harmless self row solely to retain the common
        # municipality permutation matrix.  They are never emitted as scored.
        all_neighbors = tuple(
            tuple(lookup[neighbor] for neighbor in neighbors[unit.unit_id])
            if len(neighbors[unit.unit_id]) >= _MIN_NEIGHBORS
            else (index,)
            for index, unit in enumerate(all_units_here)
        )
        observed_all = _local_moran_values(centered, all_neighbors)
        indexes: list[int] = []
        scorable_identifiers: list[str] = []
        for unit in scorable:
            index = lookup[unit.unit_id]
            raw[unit.unit_id] = (float(observed_all[index]), neighbors[unit.unit_id])
            indexes.append(index)
            scorable_identifiers.append(unit.unit_id)
        permutation_blocks.append((centered, all_neighbors, tuple(indexes)))
        scorable_ids.append(tuple(scorable_identifiers))

    max_t_p_values: tuple[np.ndarray, ...]
    if permutation_blocks:
        max_t_p_values, completed = _synchronized_max_t_p_values(
            tuple(permutation_blocks),
            seed=_family_seed(first),
            permutations=permutations,
            max_permutations=max_permutations,
        )
    else:
        max_t_p_values = ()
        completed = permutations
    adjusted_p_values: dict[str, float] = {}
    for block_index, identifiers in enumerate(scorable_ids):
        values = max_t_p_values[block_index]
        adjusted_p_values.update(
            (identifier, float(value))
            for identifier, value in zip(identifiers, values, strict=True)
        )
    ranks = {
        unit_id: rank
        for rank, unit_id in enumerate(
            sorted(adjusted_p_values, key=lambda value: (adjusted_p_values[value], value)), start=1
        )
    }
    family_size = len(raw)
    output: list[SpatialSignal] = []
    representative_mesa = {unit_id: unit.mesas[0].mesa_id for unit_id, unit in units.items()}
    for row in rows:
        unit_id = _analysis_unit_id(row)
        common: dict[str, Any] = dict(
            peer_residual_artifact_hash=row.peer_residual_artifact_hash,
            coordinate_source_url=row.coordinate_source_url,
            coordinate_source_hash=row.coordinate_source_hash,
            coordinate_accuracy_m=row.coordinate_accuracy_m,
            coordinate_grain=row.coordinate_grain,
            input_artifact_hash=canonical_input_artifact_hash,
            election_slug=row.election_slug,
            data_version=row.data_version,
            source_layer=row.source_layer,
            source_type=row.source_type,
            legal_status=row.legal_status,
            metric=row.metric,
            candidate_id=row.candidate_id,
            peer_methodology_version=row.peer_methodology_version,
            expected_family_count=row.expected_family_count,
            expected_family_digest=row.expected_family_digest,
            analysis_unit_digest=row.expected_family_digest,
            expected_mesa_count=row.expected_mesa_count,
            expected_mesa_digest=row.expected_mesa_digest,
            mesa_membership_digest=actual_membership_digest,
            expected_mesa_membership_digest=row.expected_mesa_membership_digest,
            cohort_hash=row.cohort_hash,
            code_hash=_CODE_HASH,
            method_hash=_METHOD_HASH,
            family_id=_family_id(row),
            adjustment_method=_ADJUSTMENT_METHOD,
            family_size=family_size,
            source_links=tuple(sorted(set(row.source_links))),
            permutations=permutations,
            comparator=(f"{permutations:,} synchronized max-T within-municipality permutations"),
        )
        if row.mesa_id in reasons:
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    False,
                    False,
                    None,
                    reasons[row.mesa_id],
                    (),
                    None,
                    None,
                    None,
                    family_rank=None,
                    randomization_seed=None,
                    **common,
                )
            )
        elif (
            row.coordinate_grain == "polling_place" and row.mesa_id != representative_mesa[unit_id]
        ):
            # A polling place is the analysis unit.  Its result is published
            # once, against the deterministic representative, never copied to
            # each colocated mesa as if they were independent tests.
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    False,
                    False,
                    None,
                    "nonrepresentative_polling_place_mesa",
                    (),
                    None,
                    None,
                    None,
                    family_rank=None,
                    randomization_seed=None,
                    **common,
                )
            )
        elif len(neighbors.get(unit_id, ())) < _MIN_NEIGHBORS:
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    False,
                    False,
                    None,
                    "isolated_or_sparse_within_20km",
                    (),
                    None,
                    None,
                    None,
                    family_rank=None,
                    randomization_seed=None,
                    **common,
                )
            )
        elif unit_id not in eligible_units:
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    False,
                    False,
                    None,
                    "municipality_below_100_eligible_units",
                    (),
                    None,
                    None,
                    None,
                    family_rank=None,
                    randomization_seed=None,
                    **common,
                )
            )
        elif unit_id not in raw:
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    False,
                    False,
                    None,
                    "isolated_or_sparse_within_20km",
                    (),
                    None,
                    None,
                    None,
                    family_rank=None,
                    randomization_seed=None,
                    **common,
                )
            )
        else:
            observed, selected = raw[unit_id]
            p_value = adjusted_p_values[unit_id]
            rank = ranks[unit_id]
            scored_common = {
                **common,
                "permutations": completed,
                "comparator": (
                    f"{completed:,} synchronized max-T within-municipality permutations"
                ),
            }
            kind: Literal["positive_cluster", "negative_spatial_contrast"] = (
                "positive_cluster" if observed >= 0 else "negative_spatial_contrast"
            )
            research_signal = bool(
                p_value <= 0.001 and p_value <= 0.05 and abs(observed) >= float(minimum_effect_size)
            )
            output.append(
                SpatialSignal(
                    row.mesa_id,
                    unit_id,
                    True,
                    False,
                    kind,
                    None,
                    selected,
                    observed,
                    p_value,
                    p_value,
                    family_rank=rank,
                    randomization_seed=_family_seed(first),
                    observed_value=observed,
                    permutation_resolution=1 / (completed + 1),
                    minimum_effect_size=float(minimum_effect_size),
                    research_signal=research_signal,
                    **scored_common,
                )
            )
    ordered = sorted(output, key=lambda item: item.mesa_id)
    return tuple(replace(item, output_hash=_canonical_output_hash(item)) for item in ordered)
