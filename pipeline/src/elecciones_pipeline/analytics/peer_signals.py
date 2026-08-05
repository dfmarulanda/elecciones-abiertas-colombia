"""Complete-family leave-one-out empirical-Bayes peer screening.

One call represents exactly one immutable metric/candidate family.  Expected
mesa count and digest are verified before fitting, so callers cannot obtain a
different multiplicity adjustment by submitting a subset.  Numerical
fallbacks and large-state approximations remain descriptive and are never
eligible for public priority points.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, replace
from math import exp, log, sqrt
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.special import betaln, digamma  # type: ignore[import-untyped]
from scipy.stats import betabinom  # type: ignore[import-untyped]

from .fingerprints import derive_analyzer_fingerprint
from .hierarchical_reference import (
    BinomialPeerObservation,
    HierarchicalBetaBinomialReference,
    ReferencePrediction,
)

Metric = Literal["turnout", "candidate_share", "blank", "null_unmarked"]
_METRICS = frozenset({"turnout", "candidate_share", "blank", "null_unmarked"})
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
    "contextual_baseline": "context_only",
}
_MIN_DENOMINATOR = 80
_MIN_PEERS = 30
# The plug-in predictive tail evaluates betabinom at the leave-one-out point
# estimates as though alpha and beta were known.  Measured under a correctly
# specified beta-binomial null (300,000 replications per cell, so this is pure
# hyperparameter-estimation error rather than misspecification), the realized
# rate at the 0.001 endpoint is 2.93x nominal at 31 peers, 2.04x at 51, 1.42x
# at 101, 1.25x at 151, and 1.00x at 201.  The strict research endpoint fires
# at p <= 0.001, exactly where that error is worst, so it requires a pool large
# enough for the plug-in tail to be calibrated.
_STRICT_TAIL_MIN_PEERS = 200
_MAX_EXACT_LOO_STATES = 512
_LOG_PARAMETER_BOUNDS = (log(1e-3), log(1e6))
_ADJUSTMENT_METHOD = "benjamini-yekutieli"
_METHODOLOGY_VERSION = "peer-beta-binomial-eb-v5"
_ARTIFACT_SCHEMA_VERSION = "peer-signal-artifact-v6"
_ALLOWED_ELECTIONS = frozenset({"presidencia-2026-r2", "presidencia-2026-segunda-vuelta"})
_ANALYZER_SOURCES = (Path(__file__), Path(__file__).with_name("fingerprints.py"))
_CODE_HASH = derive_analyzer_fingerprint(
    analyzer="peer_signals",
    artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
    source_files=_ANALYZER_SOURCES,
    components={
        "adjustment": "benjamini-yekutieli",
        "artifact": "PeerSignal",
        "fit": "leave-one-out-beta-binomial-mle",
        "numerics": "numpy-scipy",
    },
)
_METHOD_HASH = derive_analyzer_fingerprint(
    analyzer="peer_signals",
    artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
    source_files=_ANALYZER_SOURCES,
    components={
        "adjustment": "benjamini-yekutieli",
        "decision_rule": "p001-q05-z35-effect8-or3",
        "fit": "leave-one-out-beta-binomial-mle",
        "numerics": "numpy-scipy",
    },
)
CODE_HASH = _CODE_HASH
METHOD_HASH = _METHOD_HASH
METHODOLOGY_VERSION = _METHODOLOGY_VERSION
ARTIFACT_SCHEMA_VERSION = _ARTIFACT_SCHEMA_VERSION

# This is intentionally separate from the frozen PeerSignal production
# artifact.  Changing or validating the reference model cannot silently alter
# the established priority path.
HIERARCHICAL_REFERENCE_METHODOLOGY_VERSION = "hierarchical-peer-eb-reference-v2"
HIERARCHICAL_REFERENCE_ARTIFACT_SCHEMA_VERSION = "hierarchical-peer-reference-artifact-v2"
_HIERARCHICAL_REFERENCE_SOURCES = (
    Path(__file__),
    Path(__file__).with_name("hierarchical_reference.py"),
    Path(__file__).with_name("fingerprints.py"),
)
HIERARCHICAL_REFERENCE_CODE_HASH = derive_analyzer_fingerprint(
    analyzer="hierarchical_peer_reference",
    artifact_schema_version=HIERARCHICAL_REFERENCE_ARTIFACT_SCHEMA_VERSION,
    source_files=_HIERARCHICAL_REFERENCE_SOURCES,
    components={
        "artifact": "HierarchicalPeerSignal",
        "fit": "nested-beta-binomial-empirical-bayes-reference",
        "numerics": "numpy-scipy",
        "publication": "research-preview-no-priority-points",
    },
)
HIERARCHICAL_REFERENCE_METHOD_HASH = derive_analyzer_fingerprint(
    analyzer="hierarchical_peer_reference",
    artifact_schema_version=HIERARCHICAL_REFERENCE_ARTIFACT_SCHEMA_VERSION,
    source_files=_HIERARCHICAL_REFERENCE_SOURCES,
    components={
        "decision_rule": "p001-q05-z35-effect8-or3-exact-refit",
        "fit": "nested-beta-binomial-empirical-bayes-reference",
        "loo": "one-target-excluded-hierarchical-refit-per-mesa",
        "publication": "research-preview-no-priority-points",
    },
)


def family_digest(identifiers: Iterable[str]) -> str:
    """Canonical digest for a complete expected family."""
    values = sorted(identifiers)
    encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def cohort_digest(
    *,
    election_slug: str,
    data_version: str,
    source_layer: str,
    source_type: str,
    legal_status: str,
    metric: Metric,
    candidate_id: str | None,
    expected_family_count: int,
    expected_family_digest: str,
    input_artifact_hash: str,
) -> str:
    """Hash the exact immutable family declaration, excluding the hash itself."""
    payload = {
        "candidate_id": candidate_id,
        "data_version": data_version,
        "election_slug": election_slug,
        "expected_family_count": expected_family_count,
        "expected_family_digest": expected_family_digest,
        "input_artifact_hash": input_artifact_hash,
        "legal_status": legal_status,
        "metric": metric,
        "source_layer": source_layer,
        "source_type": source_type,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MesaMetrics:
    mesa_id: str
    place_id: str
    municipality_id: str
    department_id: str
    metric: Metric
    registered: int | None
    ballots: int
    candidate_votes: int
    valid_votes: int
    blank_votes: int
    null_unmarked_votes: int
    candidate_id: str | None
    election_slug: str
    data_version: str
    source_layer: str
    source_type: str
    legal_status: str
    expected_family_count: int
    expected_family_digest: str
    input_artifact_hash: str
    cohort_hash: str
    source_links: tuple[str, ...] = ()
    # ``candidate_votes`` is the focal candidate in a candidate-share family;
    # it is never a substitute for the all-candidate total.  Older research
    # fixtures may omit the two fields below, but that is an explicitly
    # incomplete vector and cannot be evaluated by a denominator-based model.
    candidate_total_votes: int | None = None
    denominator_provenance: str = "unavailable"

    def __post_init__(self) -> None:
        if self.metric not in _METRICS:
            raise ValueError("peer metric is invalid")
        counts = (
            self.ballots,
            self.candidate_votes,
            self.valid_votes,
            self.blank_votes,
            self.null_unmarked_votes,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("mesa metrics must be nonnegative integers")
        if self.registered is not None and (
            type(self.registered) is not int or self.registered < 0
        ):
            raise ValueError("registered electors must be a nonnegative integer or None")
        if self.registered is not None and self.ballots > self.registered:
            raise ValueError("voters cannot exceed registered electors")
        if self.valid_votes > self.ballots:
            raise ValueError("valid votes cannot exceed ballots/voters")
        if self.candidate_votes > self.valid_votes:
            raise ValueError("candidate votes cannot exceed valid votes")
        if self.candidate_total_votes is not None and (
            type(self.candidate_total_votes) is not int or self.candidate_total_votes < 0
        ):
            raise ValueError("candidate_total_votes must be a nonnegative integer or None")
        if self.candidate_total_votes is not None:
            if self.candidate_votes > self.candidate_total_votes:
                raise ValueError("focal candidate votes cannot exceed all-candidate votes")
            if self.valid_votes != self.candidate_total_votes + self.blank_votes:
                raise ValueError("complete vectors require valid votes = candidates + blank")
            if self.ballots != self.valid_votes + self.null_unmarked_votes:
                raise ValueError(
                    "complete vectors require ballots = valid votes + null/unmarked votes"
                )
        if self.blank_votes > self.valid_votes or self.null_unmarked_votes > self.ballots:
            raise ValueError("blank and null/unmarked votes cannot exceed their ballot universe")
        if self.denominator_provenance not in {"joined_official", "unavailable"}:
            raise ValueError("denominator_provenance must be joined_official or unavailable")
        if self.candidate_total_votes is None and self.denominator_provenance != "unavailable":
            raise ValueError("incomplete vectors must declare denominator provenance unavailable")
        if self.metric == "candidate_share":
            if (
                not isinstance(self.candidate_id, str)
                or not self.candidate_id.strip()
                or "|" in self.candidate_id
            ):
                raise ValueError("candidate_id is required for candidate-share families")
        elif self.candidate_id is not None or self.candidate_votes != 0:
            raise ValueError(
                "noncandidate families require null candidate_id and zero candidate_votes"
            )
        if self.election_slug not in _ALLOWED_ELECTIONS:
            raise ValueError("election/round is not allowlisted for peer analytics")
        if self.source_type == "contextual_baseline" or self.legal_status == "context_only":
            raise ValueError("contextual inputs cannot be used for peer analytics")
        if self.source_layer in {"context_only", "contextual_baseline"}:
            raise ValueError("contextual source layers cannot be used for peer analytics")
        if self.source_type not in _SOURCE_LEGAL_STATUS:
            raise ValueError("peer source_type is invalid")
        if self.legal_status != _SOURCE_LEGAL_STATUS[self.source_type]:
            raise ValueError("peer source_type/legal_status is incompatible")
        if self.source_layer != self.source_type:
            raise ValueError("peer source_layer must equal its canonical source_type")
        for name, value in (
            ("mesa_id", self.mesa_id),
            ("place_id", self.place_id),
            ("municipality_id", self.municipality_id),
            ("department_id", self.department_id),
            ("data_version", self.data_version),
            ("source_layer", self.source_layer),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if "|" in self.data_version or "|" in self.source_layer:
            raise ValueError("peer family identifiers cannot contain '|'")
        if type(self.expected_family_count) is not int or self.expected_family_count < 1:
            raise ValueError("expected_family_count must be positive")
        for name, value in (
            ("expected_family_digest", self.expected_family_digest),
            ("input_artifact_hash", self.input_artifact_hash),
            ("cohort_hash", self.cohort_hash),
        ):
            if not _is_sha256(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if any(not _is_https_url(link) for link in self.source_links):
            raise ValueError("peer source links must be absolute HTTPS URLs")


@dataclass(frozen=True)
class PeerSignal:
    mesa_id: str
    metric: Metric
    candidate_id: str | None
    election_slug: str
    data_version: str
    source_layer: str
    source_type: str
    legal_status: str
    family_id: str
    eligible: bool
    public_point_eligible: bool
    signal: bool
    reason: str | None
    peer_level: str | None
    peers: int
    observed_rate: float | None
    expected_rate: float | None
    standardized_residual: float | None
    effect_pp: float | None
    tail_probability: float | None
    adjusted_q_value: float | None
    adjustment_method: str
    family_size: int
    family_rank: int | None
    expected_family_count: int
    expected_family_digest: str
    cohort_hash: str
    input_artifact_hash: str
    code_hash: str
    method_hash: str
    fit_method: str | None
    output_hash: str = ""
    affected_vote_estimate: int | None = None
    methodology_version: str = _METHODOLOGY_VERSION
    limitations: tuple[str, ...] = (
        "Complete-family empirical-Bayes peer screening is a review lead, not proof.",
        "Fallback or approximate fits are ineligible for public priority points.",
        "Statistical signals do not estimate or verify affected votes.",
        "Row-declared family counts and digests require an independently authenticated "
        "external ledger before any public use.",
        "Predictive tails are plug-in: they evaluate the beta-binomial at the leave-one-out "
        "point estimates as if those hyperparameters were known, so estimation uncertainty "
        "is not propagated. Measured under a correctly specified null, the realized rate at "
        "the 0.001 endpoint is about 2.9x nominal at 31 peers, 1.4x at 101, and reaches "
        "nominal near 200. The research endpoint therefore requires a calibrated pool; "
        "smaller pools keep their published tail as a descriptive quantity only.",
    )
    calculation: str = "leave-one-out beta-binomial empirical-Bayes predictive tail"
    peer_definition: str | None = None
    source_links: tuple[str, ...] = ()
    family_ledger_status: str = "external_registry_required_unverified"


@dataclass(frozen=True)
class HierarchicalPeerSignal:
    """Non-production hierarchical empirical-Bayes peer reference output.

    ``research_flag`` is a reproducible review candidate, never a published
    priority point.  The separate type prevents accidental substitution for
    the frozen :class:`PeerSignal` contract.
    """

    mesa_id: str
    metric: Metric
    candidate_id: str | None
    election_slug: str
    data_version: str
    source_layer: str
    source_type: str
    legal_status: str
    family_id: str
    eligible: bool
    public_point_eligible: bool
    research_flag: bool
    reason: str | None
    peer_level: str | None
    peer_hierarchy: tuple[str, ...]
    peers: int
    department_peers: int
    municipality_peers: int
    polling_place_peers: int
    observed_rate: float | None
    expected_rate: float | None
    predictive_interval_low: float | None
    predictive_interval_high: float | None
    standardized_residual: float | None
    effect_pp: float | None
    discrete_two_sided_p_value: float | None
    adjusted_q_value: float | None
    adjustment_method: str
    family_size: int
    family_rank: int | None
    loo_refit_status: str | None
    convergence_status: str | None
    influence_diagnostic: str | None
    fit_method: str | None
    expected_family_count: int
    expected_family_digest: str
    cohort_hash: str
    input_artifact_hash: str
    code_hash: str
    method_hash: str
    methodology_version: str = HIERARCHICAL_REFERENCE_METHODOLOGY_VERSION
    publication_status: str = "research_preview_not_for_public_priority"
    limitations: tuple[str, ...] = (
        "Research preview: nested empirical Bayes is not full Bayesian hierarchical inference.",
        "No PSIS-LOO or posterior-chain diagnostics are available in the current Python stack.",
        "A research flag is a review lead, not evidence of an anomaly or affected votes.",
        "Row-declared family counts and digests do not self-authenticate a roster.",
    )
    source_links: tuple[str, ...] = ()
    output_hash: str = ""
    family_ledger_status: str = "external_registry_required_unverified"


@dataclass(frozen=True)
class _BetaFit:
    alpha: float
    beta: float
    method: str
    public_eligible: bool


class _LeaveOneOutPool:
    def __init__(self, rows: tuple[MesaMetrics, ...]) -> None:
        metric = rows[0].metric
        pairs = [_numerator_denominator(row, metric) for row in rows]
        self._counts = Counter((y, n) for y, n in pairs if n is not None)
        self._cache: dict[tuple[int, int], _BetaFit] = {}
        self._large_state_fit: _BetaFit | None = None

    @property
    def size(self) -> int:
        return sum(self._counts.values())

    def fit_without(self, pair: tuple[int, int]) -> _BetaFit:
        if len(self._counts) > _MAX_EXACT_LOO_STATES:
            if self._large_state_fit is None:
                fit = _fit_beta_binomial(self._counts)
                self._large_state_fit = replace(
                    fit,
                    method="large-state-full-pool-approximation",
                    public_eligible=False,
                )
            return self._large_state_fit
        cached = self._cache.get(pair)
        if cached is not None:
            return cached
        counts = self._counts.copy()
        counts[pair] -= 1
        if counts[pair] == 0:
            del counts[pair]
        fitted = _fit_beta_binomial(counts)
        self._cache[pair] = fitted
        return fitted


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _numerator_denominator(row: MesaMetrics, metric: Metric) -> tuple[int, int | None]:
    if metric == "turnout":
        return row.ballots, row.registered
    if metric == "candidate_share":
        return row.candidate_votes, row.valid_votes
    if metric == "blank":
        # Blank votes are part of the valid-vote ballot universe.
        return row.blank_votes, row.valid_votes
    # Null/unmarked votes are evaluated against voters, not valid votes.
    return row.null_unmarked_votes, row.ballots


def _eligible(row: MesaMetrics) -> bool:
    _, denominator = _numerator_denominator(row, row.metric)
    # An individual denominator is not enough: all public/research
    # denominator comparisons require a complete, source-joined ballot vector.
    return bool(
        row.candidate_total_votes is not None
        and row.denominator_provenance == "joined_official"
        and denominator is not None
        and denominator >= _MIN_DENOMINATOR
    )


def _ineligibility_reason(row: MesaMetrics) -> str | None:
    if row.candidate_total_votes is None or row.denominator_provenance != "joined_official":
        return "incomplete_ballot_vector_not_evaluable"
    _, denominator = _numerator_denominator(row, row.metric)
    if denominator is None:
        return "metric_denominator_unavailable"
    if denominator < _MIN_DENOMINATOR:
        return "metric_denominator_below_80"
    return None


def _fallback_fit(counts: Counter[tuple[int, int]]) -> _BetaFit:
    total_n = sum(n * frequency for (y, n), frequency in counts.items())
    total_y = sum(y * frequency for (y, _), frequency in counts.items())
    mean = min(max((total_y + 0.5) / (total_n + 1), 1e-6), 1 - 1e-6)
    rates = np.fromiter((y / n for y, n in counts), dtype=float)
    weights = np.fromiter(counts.values(), dtype=float)
    variance = float(np.average((rates - mean) ** 2, weights=weights))
    concentration = min(max(mean * (1 - mean) / max(variance, 1e-9) - 1, 1e-3), 1e6)
    return _BetaFit(
        mean * concentration,
        (1 - mean) * concentration,
        "bounded-smoothed-moment-fallback",
        False,
    )


def _fit_beta_binomial(counts: Counter[tuple[int, int]]) -> _BetaFit:
    if not counts:
        raise ValueError("cannot fit an empty peer pool")
    y = np.fromiter((pair[0] for pair in counts), dtype=float)
    n = np.fromiter((pair[1] for pair in counts), dtype=float)
    weights = np.fromiter(counts.values(), dtype=float)
    start = _fallback_fit(counts)

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        alpha, beta = exp(float(parameters[0])), exp(float(parameters[1]))
        likelihood = np.sum(weights * (betaln(y + alpha, n - y + beta) - betaln(alpha, beta)))
        alpha_gradient = np.sum(
            weights
            * (
                digamma(y + alpha)
                - digamma(n + alpha + beta)
                - digamma(alpha)
                + digamma(alpha + beta)
            )
        )
        beta_gradient = np.sum(
            weights
            * (
                digamma(n - y + beta)
                - digamma(n + alpha + beta)
                - digamma(beta)
                + digamma(alpha + beta)
            )
        )
        gradient = -np.asarray((alpha_gradient * alpha, beta_gradient * beta))
        return -float(likelihood), gradient

    result = minimize(
        objective,
        np.asarray((log(start.alpha), log(start.beta))),
        jac=True,
        method="L-BFGS-B",
        bounds=(_LOG_PARAMETER_BOUNDS, _LOG_PARAMETER_BOUNDS),
        options={"maxiter": 80, "ftol": 1e-10, "gtol": 1e-7},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return start
    alpha, beta = exp(float(result.x[0])), exp(float(result.x[1]))
    boundary = any(
        abs(float(value) - bound) < 1e-5 for value in result.x for bound in _LOG_PARAMETER_BOUNDS
    )
    if boundary or not np.isfinite(alpha + beta):
        return replace(start, method="boundary-mle-fallback")
    return _BetaFit(alpha, beta, "leave-one-out-marginal-likelihood-mle", True)


def _family_id(row: MesaMetrics) -> str:
    candidate = row.candidate_id or "none"
    return "|".join((row.data_version, row.election_slug, row.source_layer, row.metric, candidate))


def _validate_family(rows: tuple[MesaMetrics, ...]) -> None:
    identifiers = [row.mesa_id for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("mesa_id must be unique")
    declared = {
        (
            row.metric,
            row.candidate_id,
            row.election_slug,
            row.data_version,
            row.source_layer,
            row.source_type,
            row.legal_status,
            row.expected_family_count,
            row.expected_family_digest,
            row.input_artifact_hash,
            row.cohort_hash,
        )
        for row in rows
    }
    if len(declared) != 1:
        raise ValueError("peer call contains fragmented immutable families")
    expected_count = rows[0].expected_family_count
    expected_digest = rows[0].expected_family_digest
    if len(rows) != expected_count or family_digest(identifiers) != expected_digest:
        raise ValueError("supplied peer family does not match expected ID count and digest")
    first = rows[0]
    expected_cohort = cohort_digest(
        election_slug=first.election_slug,
        data_version=first.data_version,
        source_layer=first.source_layer,
        source_type=first.source_type,
        legal_status=first.legal_status,
        metric=first.metric,
        candidate_id=first.candidate_id,
        expected_family_count=first.expected_family_count,
        expected_family_digest=first.expected_family_digest,
        input_artifact_hash=first.input_artifact_hash,
    )
    if first.cohort_hash != expected_cohort:
        raise ValueError("peer cohort_hash does not match the immutable family declaration")


def _pool_key(row: MesaMetrics, level: str) -> tuple[str, str]:
    identifier = {
        "polling_place": row.place_id,
        "municipality": row.municipality_id,
        "department": row.department_id,
    }[level]
    return level, identifier


def _by_adjust(p_values: list[float]) -> tuple[list[float], list[int]]:
    if not p_values:
        return [], []
    order = np.argsort(np.asarray(p_values), kind="stable")
    m = len(order)
    harmonic = float(np.sum(1 / np.arange(1, m + 1)))
    ordered = np.asarray(p_values)[order]
    adjusted = np.empty(m)
    running = 1.0
    for index in range(m - 1, -1, -1):
        running = min(running, float(ordered[index]) * m * harmonic / (index + 1))
        adjusted[index] = running
    output = np.empty(m)
    ranks = np.empty(m, dtype=int)
    output[order] = adjusted
    ranks[order] = np.arange(1, m + 1)
    return [float(value) for value in output], [int(value) for value in ranks]


def _canonical_output_hash(signal: PeerSignal) -> str:
    payload = asdict(signal)
    payload.pop("output_hash")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def peer_research_detection(signal: PeerSignal) -> bool:
    """Frozen research calibration endpoint, independent of public eligibility."""
    effect_threshold = 8.0 if signal.metric in {"turnout", "candidate_share"} else 3.0
    return bool(
        signal.eligible
        and signal.fit_method == "leave-one-out-marginal-likelihood-mle"
        and signal.peers >= _STRICT_TAIL_MIN_PEERS
        and signal.tail_probability is not None
        and signal.tail_probability <= 0.001
        and signal.adjusted_q_value is not None
        and signal.adjusted_q_value <= 0.05
        and signal.standardized_residual is not None
        and abs(signal.standardized_residual) >= 3.5
        and signal.effect_pp is not None
        and signal.effect_pp >= effect_threshold
    )


def _peer_signal_iterator(records: Iterable[MesaMetrics]) -> Iterator[PeerSignal]:
    rows = tuple(sorted(records, key=lambda row: row.mesa_id))
    if not rows:
        return
    _validate_family(rows)
    metric = rows[0].metric
    eligible_rows = tuple(row for row in rows if _eligible(row))
    pools: dict[tuple[str, str], list[MesaMetrics]] = defaultdict(list)
    for row in eligible_rows:
        for pool_level in ("polling_place", "municipality", "department"):
            pools[_pool_key(row, pool_level)].append(row)
    frozen_pools = {key: tuple(value) for key, value in pools.items()}
    fitters: dict[tuple[str, str], _LeaveOneOutPool] = {}
    provisional: list[PeerSignal] = []
    common = rows[0]

    for row in rows:
        numerator, denominator = _numerator_denominator(row, metric)
        level: str | None = None
        selected_pool: tuple[MesaMetrics, ...] = ()
        complete_vector = _ineligibility_reason(row) is None
        if complete_vector and denominator is not None and denominator >= _MIN_DENOMINATOR:
            for candidate_level in ("polling_place", "municipality", "department"):
                candidate_pool = frozen_pools.get(_pool_key(row, candidate_level), ())
                if len(candidate_pool) - 1 >= _MIN_PEERS:
                    level, selected_pool = candidate_level, candidate_pool
                    break
        reason: str | None = None
        reason = _ineligibility_reason(row)
        if reason is None and level is None:
            reason = "fewer_than_30_eligible_peers"
        if reason is not None:
            provisional.append(
                PeerSignal(
                    row.mesa_id,
                    metric,
                    row.candidate_id,
                    row.election_slug,
                    row.data_version,
                    row.source_layer,
                    row.source_type,
                    row.legal_status,
                    _family_id(row),
                    False,
                    False,
                    False,
                    reason,
                    level,
                    max(0, len(frozen_pools.get(_pool_key(row, "department"), ())) - 1),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    _ADJUSTMENT_METHOD,
                    0,
                    None,
                    common.expected_family_count,
                    common.expected_family_digest,
                    common.cohort_hash,
                    common.input_artifact_hash,
                    _CODE_HASH,
                    _METHOD_HASH,
                    None,
                    source_links=tuple(sorted(set(row.source_links))),
                )
            )
            continue
        assert denominator is not None and level is not None
        key = _pool_key(row, level)
        fitter = fitters.get(key)
        if fitter is None:
            fitter = _LeaveOneOutPool(selected_pool)
            fitters[key] = fitter
        fit = fitter.fit_without((numerator, denominator))
        alpha, beta = fit.alpha, fit.beta
        expected = alpha / (alpha + beta)
        variance = (
            denominator
            * alpha
            * beta
            * (alpha + beta + denominator)
            / ((alpha + beta) ** 2 * (alpha + beta + 1))
        )
        observed = numerator / denominator
        residual = (numerator - denominator * expected) / sqrt(max(variance, 1e-12))
        lower = float(betabinom.cdf(numerator, denominator, alpha, beta))
        upper = float(betabinom.sf(numerator - 1, denominator, alpha, beta))
        tail = min(1.0, 2 * min(lower, upper))
        provisional.append(
            PeerSignal(
                row.mesa_id,
                metric,
                row.candidate_id,
                row.election_slug,
                row.data_version,
                row.source_layer,
                row.source_type,
                row.legal_status,
                _family_id(row),
                True,
                # An analyzer cannot self-attest the independently reviewed
                # release artifact required for public scoring.
                False,
                False,
                "independent_artifact_gate_required",
                level,
                len(selected_pool) - 1,
                observed,
                expected,
                residual,
                abs(observed - expected) * 100,
                tail,
                None,
                _ADJUSTMENT_METHOD,
                0,
                None,
                common.expected_family_count,
                common.expected_family_digest,
                common.cohort_hash,
                common.input_artifact_hash,
                _CODE_HASH,
                _METHOD_HASH,
                fit.method,
                peer_definition=f"leave-one-out {level} pool; fit={fit.method}",
                source_links=tuple(sorted(set(row.source_links))),
            )
        )

    eligible_positions = [index for index, item in enumerate(provisional) if item.eligible]
    p_values: list[float] = []
    for position in eligible_positions:
        p_value = provisional[position].tail_probability
        assert p_value is not None
        p_values.append(p_value)
    q_values, ranks = _by_adjust(p_values)
    adjustments = dict(zip(eligible_positions, zip(q_values, ranks, strict=True), strict=True))
    for index, item in enumerate(provisional):
        adjusted = adjustments.get(index)
        q_value, rank = adjusted if adjusted is not None else (None, None)
        result = replace(
            item,
            # The public signal remains closed until an independently trusted
            # release artifact is supplied at a boundary outside this analyzer.
            signal=False,
            adjusted_q_value=q_value,
            family_size=len(eligible_positions),
            family_rank=rank,
        )
        yield replace(result, output_hash=_canonical_output_hash(result))


def peer_signals(records: Iterable[MesaMetrics]) -> tuple[PeerSignal, ...]:
    """Return one complete adjusted family in canonical mesa order."""
    return tuple(_peer_signal_iterator(records))


def peer_signal_batches(
    records: Iterable[MesaMetrics], *, batch_size: int = 4096
) -> Iterator[tuple[PeerSignal, ...]]:
    """Yield serialized-family-sized output batches after one full BY adjustment."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    batch: list[PeerSignal] = []
    for result in _peer_signal_iterator(records):
        batch.append(result)
        if len(batch) == batch_size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


def _canonical_hierarchical_output_hash(signal: HierarchicalPeerSignal) -> str:
    payload = asdict(signal)
    payload.pop("output_hash")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _hierarchical_empty_signal(
    row: MesaMetrics,
    *,
    reason: str,
    common: MesaMetrics,
) -> HierarchicalPeerSignal:
    return HierarchicalPeerSignal(
        mesa_id=row.mesa_id,
        metric=row.metric,
        candidate_id=row.candidate_id,
        election_slug=row.election_slug,
        data_version=row.data_version,
        source_layer=row.source_layer,
        source_type=row.source_type,
        legal_status=row.legal_status,
        family_id=_family_id(row),
        eligible=False,
        public_point_eligible=False,
        research_flag=False,
        reason=reason,
        peer_level=None,
        peer_hierarchy=(),
        peers=0,
        department_peers=0,
        municipality_peers=0,
        polling_place_peers=0,
        observed_rate=None,
        expected_rate=None,
        predictive_interval_low=None,
        predictive_interval_high=None,
        standardized_residual=None,
        effect_pp=None,
        discrete_two_sided_p_value=None,
        adjusted_q_value=None,
        adjustment_method=_ADJUSTMENT_METHOD,
        family_size=0,
        family_rank=None,
        loo_refit_status=None,
        convergence_status=None,
        influence_diagnostic=None,
        fit_method=None,
        expected_family_count=common.expected_family_count,
        expected_family_digest=common.expected_family_digest,
        cohort_hash=common.cohort_hash,
        input_artifact_hash=common.input_artifact_hash,
        code_hash=HIERARCHICAL_REFERENCE_CODE_HASH,
        method_hash=HIERARCHICAL_REFERENCE_METHOD_HASH,
        source_links=tuple(sorted(set(row.source_links))),
    )


def _hierarchical_signal(
    row: MesaMetrics,
    prediction: ReferencePrediction,
    *,
    common: MesaMetrics,
) -> HierarchicalPeerSignal:
    numerator, denominator = _numerator_denominator(row, row.metric)
    assert denominator is not None
    observed = numerator / denominator
    residual = (numerator - denominator * prediction.expected_rate) / sqrt(
        max(prediction.predictive_variance, 1e-12)
    )
    level = prediction.hierarchy_level
    peers = {
        "department": prediction.department_peers,
        "municipality": prediction.municipality_peers,
        "polling_place": prediction.polling_place_peers,
    }[level]
    hierarchy: tuple[str, ...] = ("family_hyperprior", "department")
    if level in {"municipality", "polling_place"}:
        hierarchy += ("municipality",)
    if level == "polling_place":
        hierarchy += ("polling_place",)
    return HierarchicalPeerSignal(
        mesa_id=row.mesa_id,
        metric=row.metric,
        candidate_id=row.candidate_id,
        election_slug=row.election_slug,
        data_version=row.data_version,
        source_layer=row.source_layer,
        source_type=row.source_type,
        legal_status=row.legal_status,
        family_id=_family_id(row),
        eligible=prediction.department_peers >= _MIN_PEERS,
        public_point_eligible=False,
        research_flag=False,
        reason=None,
        peer_level=level,
        peer_hierarchy=hierarchy,
        peers=peers,
        department_peers=prediction.department_peers,
        municipality_peers=prediction.municipality_peers,
        polling_place_peers=prediction.polling_place_peers,
        observed_rate=observed,
        expected_rate=prediction.expected_rate,
        predictive_interval_low=prediction.interval_low,
        predictive_interval_high=prediction.interval_high,
        standardized_residual=residual,
        effect_pp=abs(observed - prediction.expected_rate) * 100,
        discrete_two_sided_p_value=prediction.discrete_two_sided_p_value,
        adjusted_q_value=None,
        adjustment_method=_ADJUSTMENT_METHOD,
        family_size=0,
        family_rank=None,
        loo_refit_status=prediction.loo_refit_status,
        convergence_status=prediction.convergence_status,
        influence_diagnostic=prediction.influence_diagnostic,
        fit_method="nested-beta-binomial-empirical-bayes-reference",
        expected_family_count=common.expected_family_count,
        expected_family_digest=common.expected_family_digest,
        cohort_hash=common.cohort_hash,
        input_artifact_hash=common.input_artifact_hash,
        code_hash=HIERARCHICAL_REFERENCE_CODE_HASH,
        method_hash=HIERARCHICAL_REFERENCE_METHOD_HASH,
        source_links=tuple(sorted(set(row.source_links))),
    )


def _hierarchical_observation(row: MesaMetrics) -> BinomialPeerObservation:
    numerator, denominator = _numerator_denominator(row, row.metric)
    if denominator is None:
        raise ValueError("eligible hierarchical observation has no denominator")
    return BinomialPeerObservation(
        observation_id=row.mesa_id,
        department_id=row.department_id,
        municipality_id=row.municipality_id,
        polling_place_id=row.place_id,
        successes=numerator,
        trials=denominator,
    )


def hierarchical_peer_signals_research_preview(
    records: Iterable[MesaMetrics],
) -> tuple[HierarchicalPeerSignal, ...]:
    """Return a quarantined nested empirical-Bayes peer reference artifact.

    Every prediction is fitted once with the target mesa removed from global
    and local evidence.  The returned type permanently sets
    ``public_point_eligible`` to ``False``.
    """
    rows = tuple(sorted(records, key=lambda row: row.mesa_id))
    if not rows:
        return ()
    _validate_family(rows)
    common = rows[0]
    eligible_rows = tuple(row for row in rows if _eligible(row))
    if len(eligible_rows) < 2:
        results = tuple(
            _hierarchical_empty_signal(
                row,
                reason=_ineligibility_reason(row) or "fewer_than_two_eligible_research_rows",
                common=common,
            )
            for row in rows
        )
        return tuple(
            replace(item, output_hash=_canonical_hierarchical_output_hash(item)) for item in results
        )

    observations = tuple(_hierarchical_observation(row) for row in eligible_rows)
    model = HierarchicalBetaBinomialReference(observations)
    predictions = {row.mesa_id: model.predict(index) for index, row in enumerate(eligible_rows)}

    provisional: list[HierarchicalPeerSignal] = []
    for row in rows:
        ineligibility_reason = _ineligibility_reason(row)
        if ineligibility_reason is not None:
            provisional.append(
                _hierarchical_empty_signal(row, reason=ineligibility_reason, common=common)
            )
            continue
        denominator = _numerator_denominator(row, row.metric)[1]
        assert denominator is not None
        prediction = predictions[row.mesa_id]
        signal = _hierarchical_signal(row, prediction, common=common)
        if not signal.eligible:
            signal = replace(
                signal,
                reason="fewer_than_30_department_eligible_peers",
                peer_level=None,
                peer_hierarchy=(),
                peers=0,
                observed_rate=None,
                expected_rate=None,
                predictive_interval_low=None,
                predictive_interval_high=None,
                standardized_residual=None,
                effect_pp=None,
                discrete_two_sided_p_value=None,
                loo_refit_status=None,
            )
        provisional.append(signal)

    eligible_positions = [index for index, item in enumerate(provisional) if item.eligible]
    p_values: list[float] = []
    for index in eligible_positions:
        p_value = provisional[index].discrete_two_sided_p_value
        assert p_value is not None
        p_values.append(p_value)
    q_values, ranks = _by_adjust(p_values)
    adjustments = dict(zip(eligible_positions, zip(q_values, ranks, strict=True), strict=True))
    final: list[HierarchicalPeerSignal] = []
    for index, item in enumerate(provisional):
        q_value, rank = adjustments.get(index, (None, None))
        threshold = 8.0 if item.metric in {"turnout", "candidate_share"} else 3.0
        flag = bool(
            item.loo_refit_status == "target-excluded-hierarchical-refit"
            and item.convergence_status == "converged"
            and item.discrete_two_sided_p_value is not None
            and item.discrete_two_sided_p_value <= 0.001
            and q_value is not None
            and q_value <= 0.05
            and item.standardized_residual is not None
            and abs(item.standardized_residual) >= 3.5
            and item.effect_pp is not None
            and item.effect_pp >= threshold
        )
        reason = item.reason
        if item.eligible and not flag:
            reason = "research_preview_not_flagged"
        result = replace(
            item,
            research_flag=flag,
            reason=reason,
            adjusted_q_value=q_value,
            family_size=len(eligible_positions),
            family_rank=rank,
        )
        final.append(replace(result, output_hash=_canonical_hierarchical_output_hash(result)))
    return tuple(final)
