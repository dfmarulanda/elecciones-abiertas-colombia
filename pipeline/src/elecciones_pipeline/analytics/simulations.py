"""End-to-end, content-bound statistical validation artifacts.

Pure-null runs estimate familywise error.  Independently seeded alternative
runs estimate per-run false discovery proportion and injected-discrepancy
power.  Every simulated analyzer input receives a new content hash and cohort
hash before the real peer and spatial detectors are called.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Literal

import numpy as np
from scipy.stats import beta as beta_distribution  # type: ignore[import-untyped]

from .fingerprints import derive_analyzer_fingerprint
from .peer_signals import (
    CODE_HASH as PEER_CODE_HASH,
)
from .peer_signals import (
    METHOD_HASH as PEER_METHOD_HASH,
)
from .peer_signals import (
    METHODOLOGY_VERSION as PEER_METHODOLOGY_VERSION,
)
from .peer_signals import (
    MesaMetrics,
    cohort_digest,
    family_digest,
    peer_research_detection,
    peer_signals,
)
from .spatial import (
    CODE_HASH as SPATIAL_CODE_HASH,
)
from .spatial import (
    METHOD_HASH as SPATIAL_METHOD_HASH,
)
from .spatial import (
    METHODOLOGY_VERSION as SPATIAL_METHODOLOGY_VERSION,
)
from .spatial import (
    SpatialMesa,
    SpatialSignal,
    spatial_cohort_digest,
    spatial_family_digest,
    spatial_mesa_digest,
    spatial_mesa_membership_digest,
    spatial_residual_signals,
)

METHODOLOGY_VERSION = "synthetic-validation-v8"
_ARTIFACT_SCHEMA_VERSION = "simulation-validation-artifact-v7"
_TARGET = 0.05
_POWER_TARGET = 0.80
_POWER_CONFIDENCE = 0.95


@dataclass(frozen=True)
class SimulationProfile:
    """Predeclared, reproducible validation compute budget and design."""

    name: str
    null_simulations: int
    alternative_simulations: int
    seed: int
    spatial_initial_permutations: int
    spatial_max_permutations: int
    independent_artifact_required: bool
    policy_boundary_injections: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("simulation profile name is required")
        if any(
            type(value) is not int or value < 100
            for value in (self.null_simulations, self.alternative_simulations)
        ):
            raise ValueError("simulation profiles require at least 100 runs per arm")
        if self.null_simulations != self.alternative_simulations:
            raise ValueError("simulation profile arms must be balanced")
        if self.name.startswith("full-release") and self.null_simulations < 1_000:
            raise ValueError("full-release profiles require at least 1000 runs per arm")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("simulation profile seed must be a nonnegative integer")
        if (
            any(
                type(value) is not int or value < 9_999
                for value in (self.spatial_initial_permutations, self.spatial_max_permutations)
            )
            or self.spatial_max_permutations < self.spatial_initial_permutations
        ):
            raise ValueError("simulation profile spatial permutation budget is invalid")
        if type(self.independent_artifact_required) is not bool:
            raise ValueError("independent_artifact_required must be boolean")
        if type(self.policy_boundary_injections) is not bool:
            raise ValueError("policy_boundary_injections must be boolean")

    def artifact_payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def artifact_hash(self) -> str:
        return _hash(self.artifact_payload())


CI_PROFILE = SimulationProfile(
    name="ci-deterministic",
    null_simulations=100,
    alternative_simulations=100,
    seed=0,
    spatial_initial_permutations=9_999,
    spatial_max_permutations=9_999,
    independent_artifact_required=True,
    policy_boundary_injections=False,
)
FULL_RELEASE_PROFILE = SimulationProfile(
    name="full-release-1000x1000",
    null_simulations=1_000,
    alternative_simulations=1_000,
    seed=20260804,
    spatial_initial_permutations=9_999,
    spatial_max_permutations=99_999,
    independent_artifact_required=True,
    policy_boundary_injections=True,
)
SIMULATION_PROFILES = {
    CI_PROFILE.name: CI_PROFILE,
    FULL_RELEASE_PROFILE.name: FULL_RELEASE_PROFILE,
}


_RUNTIME_CONTRACT = "numpy-generator-pcg64/scipy-beta-clopper-pearson"


def simulation_runtime_fingerprint() -> str:
    """Hash the runtime identity of the host that executed this run.

    This value identifies a *machine*, not a measurement.  It must never enter
    the artifact content hash: two hosts that agree on every measured number
    still disagree here, so a content hash containing it makes "independently
    replayed" and "bit-identical" mutually exclusive conditions that no honest
    artifact can satisfy at once.  It is recorded in the attestation section
    instead, where a differing value is the evidence of independence rather
    than a hash mismatch.
    """
    return _hash(
        {
            "numpy": np.__version__,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "runtime_contract": _RUNTIME_CONTRACT,
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def detector_bindings(*, include_spatial: bool = True) -> dict[str, dict[str, str]]:
    """Return immutable analyzer code, method, and methodology bindings."""
    bindings = {
        "peer": {
            "code_hash": PEER_CODE_HASH,
            "method_hash": PEER_METHOD_HASH,
            "methodology_version": PEER_METHODOLOGY_VERSION,
        }
    }
    if include_spatial:
        bindings["spatial"] = {
            "code_hash": SPATIAL_CODE_HASH,
            "method_hash": SPATIAL_METHOD_HASH,
            "methodology_version": SPATIAL_METHODOLOGY_VERSION,
        }
    return bindings


def detector_binding_hash(bindings: Mapping[str, object]) -> str:
    return _hash(bindings)


def simulation_methodology_hash(bindings: Mapping[str, object]) -> str:
    """Fingerprint simulator/analyzer code, lockfile, runtime and schema."""
    return derive_analyzer_fingerprint(
        analyzer="run_end_to_end_validation",
        artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
        source_files=(
            Path(__file__),
            Path(__file__).with_name("fingerprints.py"),
            Path(__file__).with_name("peer_signals.py"),
            Path(__file__).with_name("spatial.py"),
        ),
        components={
            "detector_bindings": detector_binding_hash(bindings),
            "simulation_methodology_version": METHODOLOGY_VERSION,
        },
    )


def signal_key(detector_id: str, family_id: str, analysis_unit_id: str) -> str:
    """Encode a collision-safe detector/family/analysis-unit identity.

    A peer mesa and a spatial analysis unit may share their human-facing id.  A
    detector name is therefore part of the identity, rather than presentation
    metadata which can accidentally be dropped when confusion tables are made.
    """
    if not detector_id or not family_id or not analysis_unit_id:
        raise ValueError("signal identities require non-empty detector, family, and unit IDs")
    return _canonical_json([detector_id, family_id, analysis_unit_id])


def decode_signal_key(value: str) -> tuple[str, str, str]:
    """Decode and enforce the canonical signal-key representation."""
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("signal key is not canonical JSON") from exc
    if (
        not isinstance(parsed, list)
        or len(parsed) != 3
        or any(not isinstance(item, str) or not item for item in parsed)
        or signal_key(parsed[0], parsed[1], parsed[2]) != value
    ):
        raise ValueError("signal key is not a canonical family/mesa identity")
    return parsed[0], parsed[1], parsed[2]


@dataclass(frozen=True)
class InjectionEvidence:
    """One realized, nonzero, denominator-bound synthetic alternative."""

    signal_key: str
    metric: str
    direction: Literal["positive", "negative"]
    shape: Literal["scattered", "clustered"]
    denominator_band: str
    effect_boundary: str
    realized_effect_band: str
    requested_effect_fraction: float
    realized_effect_pp: float
    numerator_before: int
    numerator_after: int
    denominator_before: int
    denominator_after: int
    detected: bool = False


@dataclass(frozen=True)
class SimulationRunEvidence:
    """Content bindings and exact classification results for one run."""

    run_index: int
    mode: Literal["pure_null", "alternative"]
    seed: int
    peer_input_artifact_hash: str
    peer_cohort_hash: str
    spatial_residual_data_hash: str | None
    spatial_peer_residual_artifact_hash: str | None
    spatial_cohort_hash: str | None
    spatial_input_artifact_hash: str | None
    injected_keys: tuple[str, ...]
    injections: tuple[InjectionEvidence, ...]
    flagged_keys: tuple[str, ...]
    public_flagged_keys: tuple[str, ...]
    true_positive: int
    false_positive: int
    false_negative: int
    false_discoveries: int
    fdp: float | None
    spatial_permutations: int | None = None
    injection_effect_fraction: float | None = None
    injection_direction: Literal["positive", "negative"] | None = None


@dataclass(frozen=True)
class TrustedSimulationInputs:
    """Original typed rows and hashes authenticated outside the artifact.

    The validation artifact must never be its own source of truth.  Callers
    obtain this bundle from their content-addressed ingestion boundary.
    """

    peer_records: tuple[MesaMetrics, ...]
    spatial_records: tuple[SpatialMesa, ...] = ()
    canonical_input_hash_registry: Mapping[str, str] | None = None
    registry_artifact_hash: str | None = None


def canonical_input_hashes(inputs: TrustedSimulationInputs) -> dict[str, str]:
    """Hash exact typed original inputs in the artifact's canonical order."""
    result = {"peer": _rows_hash(tuple(sorted(inputs.peer_records, key=lambda row: row.mesa_id)))}
    if inputs.spatial_records:
        result["spatial"] = _rows_hash(
            tuple(sorted(inputs.spatial_records, key=lambda row: row.mesa_id))
        )
    return result


@dataclass(frozen=True)
class RuntimeAttestation:
    """Who executed one run, on what machine, and when.

    This is the artifact's attestation section.  It is deliberately excluded
    from :meth:`SimulationSummary.artifact_payload`, and therefore from the
    content hash, so that one content hash can carry N attestations from N
    hosts.  Nothing here is a measurement and nothing here may gate a release
    on its own; it is the record that lets a verifier tell an independent
    replay apart from the producer re-running itself.
    """

    runtime_fingerprint: str
    numpy_version: str
    python_version: str
    platform_identity: str
    runtime_contract: str
    executed_at: str
    attests_artifact_hash: str = ""


def runtime_attestation() -> RuntimeAttestation:
    """Capture the executing host's identity and wall clock."""
    return RuntimeAttestation(
        runtime_fingerprint=simulation_runtime_fingerprint(),
        numpy_version=np.__version__,
        python_version=platform.python_version(),
        platform_identity=platform.platform(),
        runtime_contract=_RUNTIME_CONTRACT,
        executed_at=datetime.now(UTC).isoformat(timespec="microseconds"),
    )


# Everything outside the content-hashed measurement section.  A verifier that
# compares two artifacts for equality must strip exactly these fields.
ATTESTATION_FIELDS = frozenset({"artifact_hash", "attestation"})


def artifact_content_section(summary: Mapping[str, object]) -> dict[str, object]:
    """Return only the content-hashed measurements of an artifact mapping."""
    return {key: value for key, value in summary.items() if key not in ATTESTATION_FIELDS}


@dataclass(frozen=True)
class SimulationSummary:
    """A canonical, self-hashed Pass B statistical validation artifact.

    The artifact has two sections.  Every measured quantity is content-hashed
    into :attr:`artifact_hash`; host identity and wall clock live in
    :attr:`attestation`, which is not hashed.  An independent replay on a
    different machine therefore reproduces the content hash exactly while
    carrying its own attestation.
    """

    simulations: int
    null_simulations: int
    alternative_simulations: int
    seed: int
    mean_false_discoveries: float
    false_discovery_probability: float
    injected_discrepancy_detection_rate: float
    false_discovery_target: float
    false_discovery_gate_passed: bool
    injected_discrepancy_gate_passed: bool
    release_gate_passed: bool
    release_id: str
    cohort_hash: str
    detector_hash: str
    methodology_hash: str
    detector_bindings: dict[str, dict[str, str]]
    input_data_hashes: dict[str, str]
    cohort_declarations: dict[str, dict[str, object]]
    family_sizes: dict[str, int]
    seeds: tuple[int, ...]
    null_seeds: tuple[int, ...]
    alternative_seeds: tuple[int, ...]
    run_spec: dict[str, object]
    injection_spec: dict[str, object]
    detector_validation: dict[str, dict[str, object]]
    null_runs: tuple[SimulationRunEvidence, ...]
    alternative_runs: tuple[SimulationRunEvidence, ...]
    confusion_totals: dict[str, int]
    confusion_by_signal_key: dict[str, dict[str, int]]
    power_by_family: dict[str, dict[str, int | float | str | None]]
    power_by_stratum: dict[str, dict[str, int | float]]
    null_error_by_metric: dict[str, dict[str, int | float]]
    family_error_upper_confidence: float
    empirical_fdr: float
    family_error_count: int
    profile_name: str = "unprofiled"
    profile_hash: str = ""
    independent_full_artifact_required: bool = True
    independent_full_artifact_passed: bool = False
    production_eligible: bool = False
    trusted_input_registry_verified: bool = False
    external_family_ledger_verified: bool = False
    artifact_hash: str = ""
    attestation: RuntimeAttestation | None = None
    methodology_version: str = METHODOLOGY_VERSION
    limitations: tuple[str, ...] = (
        "Synthetic calibration assesses the declared detector under the simulated design, "
        "not prevalence or outcomes.",
        "Power is conditional on the declared injected alternatives and is not a claim "
        "about unidentified real-world discrepancies.",
        "Pooled power is descriptive only; gates are evaluated separately by metric, direction, "
        "injection shape, denominator band, requested boundary, and realized-effect band.",
        "Cluster-shaped alternatives are measured as their own stratum. A leave-one-mesa-out "
        "peer screen keeps the rest of a contaminated polling place in its own reference pool, "
        "so a puesto-wide, jurado-wide, or transmission-batch irregularity partly masks itself "
        "and measured clustered power is far below scattered power. Scattered power alone must "
        "not be read as the detector's power.",
        "Production remains ineligible until an independently executed full-release artifact "
        "is reviewed and accepted outside this simulator.",
    )

    def artifact_payload(self) -> dict[str, object]:
        """The content-hashed section: measurements only, no host identity."""
        payload = asdict(self)
        for field in ATTESTATION_FIELDS:
            payload.pop(field)
        return payload

    def with_hash(self) -> SimulationSummary:
        content_hash = _hash(self.artifact_payload())
        attestation = self.attestation
        if attestation is not None:
            attestation = replace(attestation, attests_artifact_hash=content_hash)
        return replace(self, artifact_hash=content_hash, attestation=attestation)


def _upper_binomial_bound(events: int, trials: int) -> float:
    if trials <= 0 or events >= trials:
        return 1.0
    return float(beta_distribution.ppf(0.95, events + 1, trials - events))


def lower_binomial_bound(events: int, trials: int) -> float:
    """Exact two-sided 95% Clopper--Pearson lower confidence limit.

    This is the single implementation.  The release verifier recomputes power
    bounds independently but must import this function rather than restate the
    formula: an independently written copy differed by one ULP in the quantile
    argument and disagreed on roughly a third of all (events, trials) pairs,
    which an exact artifact comparison reports as a forged artifact.
    """
    if trials <= 0 or events <= 0:
        return 0.0
    return float(beta_distribution.ppf((1 - _POWER_CONFIDENCE) / 2, events, trials - events + 1))


_lower_binomial_bound = lower_binomial_bound


def _rows_hash(rows: Iterable[MesaMetrics | SpatialMesa]) -> str:
    material = [asdict(row) for row in rows]
    return _hash(material)


def _peer_artifact_hash(rows: tuple[MesaMetrics, ...]) -> str:
    material: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: item.mesa_id):
        payload = asdict(row)
        payload.pop("input_artifact_hash")
        payload.pop("cohort_hash")
        material.append(payload)
    return _hash({"schema": "synthetic-peer-input-v1", "rows": material})


def _spatial_residual_hash(rows: tuple[SpatialMesa, ...]) -> str:
    material: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: item.mesa_id):
        payload = asdict(row)
        payload.pop("peer_residual_artifact_hash")
        payload.pop("cohort_hash")
        material.append(payload)
    return _hash({"schema": "synthetic-spatial-residual-v1", "rows": material})


def _synthetic_peer_rows(
    rows: tuple[MesaMetrics, ...], rng: np.random.Generator
) -> tuple[MesaMetrics, ...]:
    """Generate a deliberately demanding count null from observed hierarchy.

    Registered electors and missing-registration patterns are kept from the
    authenticated rows.  Counts include department/municipality/place effects,
    beta-binomial overdispersion, a shared compositional shock, zero inflation,
    Student-t tails, and a small mixture component intentionally outside the
    fitted peer model.  This is a calibration scaffold, not a claim that the
    simulated mechanism is the electoral data-generating process.
    """
    generated: list[MesaMetrics] = []
    numerator, denominator = zip(*(_simulation_pair(row) for row in rows), strict=True)
    usable = [value / total for value, total in zip(numerator, denominator, strict=True) if total]
    base_rate = float(np.clip(np.mean(usable) if usable else 0.1, 0.002, 0.998))
    zero_probability = sum(value == 0 for value in numerator) / len(numerator)
    department_effects: dict[str, float] = {}
    municipality_effects: dict[str, float] = {}
    place_effects: dict[str, float] = {}

    def effect(mapping: dict[str, float], key: str, scale: float) -> float:
        return mapping.setdefault(key, float(rng.normal(scale=scale)))

    def draw_rate(row: MesaMetrics) -> float:
        hierarchy = (
            effect(department_effects, row.department_id, 0.18)
            + effect(municipality_effects, row.municipality_id, 0.28)
            + effect(place_effects, row.place_id, 0.20)
        )
        # Heavy tails and a 10% unmodelled mixture make the calibration more
        # conservative than a simple independent binomial generator.
        heavy_tail = float(rng.standard_t(df=4) * 0.12)
        misspecified = float(rng.normal(0.45, 0.15)) if rng.random() < 0.10 else 0.0
        logit = np.log(base_rate / (1 - base_rate)) + hierarchy + heavy_tail + misspecified
        mean = float(1 / (1 + np.exp(-np.clip(logit, -25, 25))))
        concentration = float(rng.uniform(12, 75))
        return float(
            rng.beta(
                max(mean * concentration, 1e-3),
                max((1 - mean) * concentration, 1e-3),
            )
        )

    for row in rows:
        turnout_base = (
            row.ballots / row.registered if row.registered else min(row.ballots / 1_000, 0.95)
        )
        turnout_rate = (
            draw_rate(row)
            if row.metric == "turnout"
            else float(rng.beta(max(turnout_base * 45, 1e-3), max((1 - turnout_base) * 45, 1e-3)))
        )
        # Missing registration remains missing; it is not silently imputed.
        ballots = (
            row.ballots
            if row.registered is None
            else int(rng.binomial(row.registered, turnout_rate))
        )
        rate = draw_rate(row) if row.metric != "turnout" else 0.0
        if row.metric != "turnout" and rng.random() < zero_probability:
            rate = 0.0
        candidate = 0
        if row.metric == "null_unmarked":
            null_unmarked = int(rng.binomial(ballots, rate))
            valid = ballots - null_unmarked
            blank = int(rng.binomial(valid, float(rng.beta(2, 35)))) if valid else 0
            candidate_total = valid - blank
        else:
            null_unmarked = int(rng.binomial(ballots, float(rng.beta(3, 40))))
            valid = ballots - null_unmarked
            if row.metric == "blank":
                blank = int(rng.binomial(valid, rate)) if valid else 0
                candidate_total = valid - blank
            elif row.metric == "candidate_share" and valid:
                blank_rate = min(float(rng.beta(2, 35)), max(0.0, 1 - rate))
                candidate, blank, other_candidates = (
                    int(value)
                    for value in rng.multinomial(valid, (rate, blank_rate, 1 - rate - blank_rate))
                )
                candidate_total = candidate + other_candidates
            else:
                blank = int(rng.binomial(valid, float(rng.beta(2, 35)))) if valid else 0
                candidate_total = valid - blank
        # Noncandidate families retain the all-candidate total while their
        # focal candidate fields remain exactly zero/null by contract.
        generated.append(
            replace(
                row,
                ballots=ballots,
                valid_votes=valid,
                candidate_votes=candidate,
                candidate_total_votes=candidate_total,
                blank_votes=blank,
                null_unmarked_votes=null_unmarked,
                denominator_provenance="joined_official",
            )
        )
    return tuple(generated)


def _simulation_pair(row: MesaMetrics) -> tuple[int, int]:
    """Return the observed numerator/denominator without inventing a denominator."""
    if row.metric == "turnout":
        return row.ballots, row.registered or 0
    if row.metric == "candidate_share":
        return row.candidate_votes, row.valid_votes
    if row.metric == "blank":
        return row.blank_votes, row.valid_votes
    return row.null_unmarked_votes, row.ballots


def _inject(
    row: MesaMetrics, injection_size: float, *, direction: Literal["positive", "negative"]
) -> MesaMetrics:
    """Apply a signed, accounting-preserving alternative to one category."""
    numerator, denominator = _simulation_pair(row)
    if denominator <= 0:
        raise ValueError("cannot inject a row with no metric denominator")
    capacity = _injection_capacity(row, direction)
    if capacity <= 0:
        raise ValueError("cannot inject a saturated row")
    increment = min(capacity, max(1, round(denominator * injection_size)))
    if direction == "negative":
        if row.metric == "turnout":
            return replace(
                row,
                ballots=row.ballots - increment,
                valid_votes=row.valid_votes - increment,
                candidate_total_votes=(row.candidate_total_votes or 0) - increment,
            )
        if row.metric == "candidate_share":
            return replace(row, candidate_votes=row.candidate_votes - increment)
        if row.metric == "blank":
            return replace(
                row,
                candidate_total_votes=(row.candidate_total_votes or 0) + increment,
                blank_votes=row.blank_votes - increment,
            )
        return replace(
            row,
            candidate_total_votes=(row.candidate_total_votes or 0) + increment,
            valid_votes=row.valid_votes + increment,
            null_unmarked_votes=row.null_unmarked_votes - increment,
        )
    if row.metric == "turnout":
        assert row.registered is not None
        return replace(
            row,
            ballots=row.ballots + increment,
            valid_votes=row.valid_votes + increment,
            candidate_total_votes=(row.candidate_total_votes or 0) + increment,
        )
    if row.metric == "candidate_share":
        assert row.candidate_total_votes is not None
        return replace(
            row,
            candidate_votes=row.candidate_votes + increment,
        )
    if row.metric == "blank":
        # Move candidate ballots to blank: valid votes and ballot total stay
        # fixed, while the denominator remains valid votes.
        assert row.candidate_total_votes is not None
        return replace(
            row,
            candidate_total_votes=row.candidate_total_votes - increment,
            blank_votes=row.blank_votes + increment,
        )
    from_candidates = min(row.candidate_total_votes or 0, increment)
    from_blank = increment - from_candidates
    # Move valid candidate ballots to null/unmarked; both accounting identities
    # remain exact.
    return replace(
        row,
        candidate_total_votes=(row.candidate_total_votes or 0) - from_candidates,
        valid_votes=row.valid_votes - increment,
        blank_votes=row.blank_votes - from_blank,
        null_unmarked_votes=row.null_unmarked_votes + increment,
    )


def _injection_capacity(row: MesaMetrics, direction: Literal["positive", "negative"]) -> int:
    """Maximum count change that preserves the declared ballot vector."""
    if row.candidate_total_votes is None:
        return 0
    if row.metric == "turnout":
        if row.registered is None:
            return 0
        return (
            row.registered - row.ballots if direction == "positive" else row.candidate_total_votes
        )
    if row.metric == "candidate_share":
        return (
            row.candidate_total_votes - row.candidate_votes
            if direction == "positive"
            else row.candidate_votes
        )
    if row.metric == "blank":
        return row.candidate_total_votes if direction == "positive" else row.blank_votes
    return row.valid_votes if direction == "positive" else row.null_unmarked_votes


def _denominator_band(denominator: int) -> str:
    if denominator < 80:
        return "below_80"
    if denominator < 200:
        return "80_199"
    if denominator < 500:
        return "200_499"
    return "500_plus"


def _effect_boundary(effect_fraction: float) -> str:
    if effect_fraction <= 0.08:
        return "at_or_below_8pp"
    if effect_fraction <= 0.25:
        return "above_8_to_25pp"
    return "above_25pp"


def _realized_effect_band(effect_pp: float) -> str:
    if effect_pp < 3:
        return "below_3pp"
    if effect_pp < 8:
        return "3_to_below_8pp"
    if effect_pp < 25:
        return "8_to_below_25pp"
    return "25pp_plus"


def _injection_stratum(injection: InjectionEvidence) -> str:
    return _canonical_json(
        [
            injection.metric,
            injection.direction,
            injection.shape,
            injection.denominator_band,
            injection.effect_boundary,
            injection.realized_effect_band,
        ]
    )


def _policy_boundary_injection_size(run_index: int, requested: float) -> float:
    """Cycle declared alternatives across practical decision-boundary effects."""
    boundary_effects = (0.08, 0.25, requested)
    return float(min(requested, boundary_effects[run_index % len(boundary_effects)]))


def _bind_peer_rows(rows: tuple[MesaMetrics, ...]) -> tuple[MesaMetrics, ...]:
    artifact_hash = _peer_artifact_hash(rows)
    first = rows[0]
    cohort_hash = cohort_digest(
        election_slug=first.election_slug,
        data_version=first.data_version,
        source_layer=first.source_layer,
        source_type=first.source_type,
        legal_status=first.legal_status,
        metric=first.metric,
        candidate_id=first.candidate_id,
        expected_family_count=first.expected_family_count,
        expected_family_digest=first.expected_family_digest,
        input_artifact_hash=artifact_hash,
    )
    return tuple(
        replace(row, input_artifact_hash=artifact_hash, cohort_hash=cohort_hash) for row in rows
    )


def _synthetic_spatial_rows(
    rows: tuple[SpatialMesa, ...], rng: np.random.Generator
) -> tuple[SpatialMesa, ...]:
    """Preserve coordinate coverage while stressing the residual null shape."""
    municipal_effects: dict[str, float] = {}
    generated = tuple(
        replace(
            row,
            residual=(
                0.0
                if rng.random() < 0.03
                else municipal_effects.setdefault(
                    row.municipality_id,
                    float(rng.normal(scale=0.25)),
                )
                + float(rng.standard_t(df=4))
                + (float(rng.normal(0.4, 0.12)) if rng.random() < 0.10 else 0.0)
            ),
        )
        for row in rows
    )
    residual_hash = _spatial_residual_hash(generated)
    first = generated[0]
    expected_mesa_digest = spatial_mesa_digest(row.mesa_id for row in generated)
    # Membership digest deliberately includes residuals and mesa-to-unit mapping.
    provisional = tuple(
        replace(
            row,
            peer_residual_artifact_hash=residual_hash,
            expected_mesa_count=len(generated),
            expected_mesa_digest=expected_mesa_digest,
            expected_mesa_membership_digest="0" * 64,
            cohort_hash="0" * 64,
        )
        for row in generated
    )
    membership_digest = spatial_mesa_membership_digest(provisional)
    cohort_hash = spatial_cohort_digest(
        peer_residual_artifact_hash=residual_hash,
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
        expected_mesa_count=len(generated),
        expected_mesa_digest=expected_mesa_digest,
        expected_mesa_membership_digest=membership_digest,
    )
    return tuple(
        replace(row, expected_mesa_membership_digest=membership_digest, cohort_hash=cohort_hash)
        for row in provisional
    )


def _peer_declaration(row: MesaMetrics) -> dict[str, object]:
    return {
        "candidate_id": row.candidate_id,
        "data_version": row.data_version,
        "election_slug": row.election_slug,
        "expected_family_count": row.expected_family_count,
        "expected_family_digest": row.expected_family_digest,
        "input_artifact_hash": row.input_artifact_hash,
        "legal_status": row.legal_status,
        "metric": row.metric,
        "source_layer": row.source_layer,
        "source_type": row.source_type,
        "cohort_hash": row.cohort_hash,
    }


def _spatial_declaration(row: SpatialMesa) -> dict[str, object]:
    return {
        "candidate_id": row.candidate_id,
        "coordinate_accuracy_m": float(row.coordinate_accuracy_m),
        "coordinate_grain": row.coordinate_grain,
        "coordinate_source_hash": row.coordinate_source_hash,
        "coordinate_source_url": row.coordinate_source_url,
        "data_version": row.data_version,
        "election_slug": row.election_slug,
        "expected_family_count": row.expected_family_count,
        "expected_family_digest": row.expected_family_digest,
        "expected_mesa_count": row.expected_mesa_count,
        "expected_mesa_digest": row.expected_mesa_digest,
        "expected_mesa_membership_digest": row.expected_mesa_membership_digest,
        "legal_status": row.legal_status,
        "metric": row.metric,
        "peer_methodology_version": row.peer_methodology_version,
        "peer_residual_artifact_hash": row.peer_residual_artifact_hash,
        "source_layer": row.source_layer,
        "source_type": row.source_type,
        "cohort_hash": row.cohort_hash,
    }


def _family_id(row: MesaMetrics | SpatialMesa) -> str:
    candidate = row.candidate_id or "none"
    return "|".join((row.data_version, row.election_slug, row.source_layer, row.metric, candidate))


def _cross_detector_compatible(peer_row: MesaMetrics, spatial_row: SpatialMesa) -> bool:
    return (
        peer_row.election_slug,
        peer_row.data_version,
        peer_row.source_layer,
        peer_row.source_type,
        peer_row.legal_status,
        peer_row.metric,
        peer_row.candidate_id,
    ) == (
        spatial_row.election_slug,
        spatial_row.data_version,
        spatial_row.source_layer,
        spatial_row.source_type,
        spatial_row.legal_status,
        spatial_row.metric,
        spatial_row.candidate_id,
    )


def _validate_original_inputs(
    peer_rows: tuple[MesaMetrics, ...], spatial_rows: tuple[SpatialMesa, ...]
) -> None:
    if len({row.mesa_id for row in peer_rows}) != len(peer_rows):
        raise ValueError("peer validation mesa IDs must be unique")
    if len({_canonical_json(_peer_declaration(row)) for row in peer_rows}) != 1:
        raise ValueError("peer validation input fragments an immutable family")
    peer_first = peer_rows[0]
    if (
        len(peer_rows) != peer_first.expected_family_count
        or family_digest(row.mesa_id for row in peer_rows) != peer_first.expected_family_digest
        or cohort_digest(
            election_slug=peer_first.election_slug,
            data_version=peer_first.data_version,
            source_layer=peer_first.source_layer,
            source_type=peer_first.source_type,
            legal_status=peer_first.legal_status,
            metric=peer_first.metric,
            candidate_id=peer_first.candidate_id,
            expected_family_count=peer_first.expected_family_count,
            expected_family_digest=peer_first.expected_family_digest,
            input_artifact_hash=peer_first.input_artifact_hash,
        )
        != peer_first.cohort_hash
    ):
        raise ValueError("peer validation input does not match its declared cohort")
    if not spatial_rows:
        return
    if len({row.mesa_id for row in spatial_rows}) != len(spatial_rows):
        raise ValueError("spatial validation mesa IDs must be unique")
    if len({_canonical_json(_spatial_declaration(row)) for row in spatial_rows}) != 1:
        raise ValueError("spatial validation input fragments an immutable family")
    spatial_first = spatial_rows[0]
    unit_ids = {
        row.mesa_id if row.coordinate_grain == "mesa" else str(row.spatial_unit_id)
        for row in spatial_rows
    }
    if (
        len(unit_ids) != spatial_first.expected_family_count
        or spatial_family_digest(unit_ids) != spatial_first.expected_family_digest
        or len(spatial_rows) != spatial_first.expected_mesa_count
        or spatial_mesa_digest(row.mesa_id for row in spatial_rows)
        != spatial_first.expected_mesa_digest
        or spatial_mesa_membership_digest(spatial_rows)
        != spatial_first.expected_mesa_membership_digest
        or spatial_cohort_digest(
            peer_residual_artifact_hash=spatial_first.peer_residual_artifact_hash,
            election_slug=spatial_first.election_slug,
            data_version=spatial_first.data_version,
            source_layer=spatial_first.source_layer,
            source_type=spatial_first.source_type,
            legal_status=spatial_first.legal_status,
            metric=spatial_first.metric,
            candidate_id=spatial_first.candidate_id,
            peer_methodology_version=spatial_first.peer_methodology_version,
            coordinate_source_url=spatial_first.coordinate_source_url,
            coordinate_source_hash=spatial_first.coordinate_source_hash,
            coordinate_accuracy_m=spatial_first.coordinate_accuracy_m,
            coordinate_grain=spatial_first.coordinate_grain,
            expected_family_count=spatial_first.expected_family_count,
            expected_family_digest=spatial_first.expected_family_digest,
            expected_mesa_count=spatial_first.expected_mesa_count,
            expected_mesa_digest=spatial_first.expected_mesa_digest,
            expected_mesa_membership_digest=spatial_first.expected_mesa_membership_digest,
        )
        != spatial_first.cohort_hash
    ):
        raise ValueError("spatial validation input does not match its declared cohort")


def _run_evidence(
    *,
    mode: Literal["pure_null", "alternative"],
    run_index: int,
    run_seed: int,
    peer_rows: tuple[MesaMetrics, ...],
    spatial_rows: tuple[SpatialMesa, ...],
    injected_discrepancies: int,
    injection_size: float,
    spatial_initial_permutations: int,
    spatial_max_permutations: int,
    policy_boundary_injections: bool,
) -> SimulationRunEvidence:
    simulated_peer = list(_synthetic_peer_rows(peer_rows, np.random.default_rng([run_seed, 0])))
    injected: set[str] = set()
    injection_records: list[InjectionEvidence] = []
    effective_injection_size: float | None = None
    injection_direction: Literal["positive", "negative"] | None = None
    if mode == "alternative":
        effective_injection_size = (
            _policy_boundary_injection_size(run_index, injection_size)
            if policy_boundary_injections
            else injection_size
        )
        injection_direction = "positive" if run_index % 2 == 0 else "negative"
        # Alternatives alternate over direction AND shape.  A scattered arm of
        # independent single mesas is the easy case for a leave-one-mesa-out
        # peer screen; the irregularities an audit actually cares about are
        # cluster-shaped -- one puesto, one jurado team, one transmission
        # batch -- and those partly mask themselves because the contaminated
        # peers stay in the reference pool.  Shape is a stratum dimension, so
        # the per-stratum power gate must clear the clustered arm too.
        injection_shape: Literal["scattered", "clustered"] = (
            "scattered" if (run_index // 2) % 2 == 0 else "clustered"
        )
        injectable_indices = []
        for index, row in enumerate(simulated_peer):
            _numerator, denominator = _simulation_pair(row)
            if denominator >= 80 and _injection_capacity(row, injection_direction) > 0:
                injectable_indices.append(index)
        if len(injectable_indices) < injected_discrepancies:
            raise ValueError("simulated family has too few non-saturated injectable records")
        selector = np.random.default_rng([run_seed, 1])
        if injection_shape == "clustered":
            clusters: dict[str, list[int]] = defaultdict(list)
            for index in injectable_indices:
                clusters[simulated_peer[index].place_id].append(index)
            # A cluster must be a genuine multi-mesa *proper subset*: shifting
            # every injectable mesa leaves no unshifted reference, which is a
            # family-wide shift rather than a cluster-shaped irregularity.
            usable = sorted(
                place_id
                for place_id, members in clusters.items()
                if 2 <= len(members) < len(injectable_indices)
            )
            if usable:
                chosen_place = usable[int(selector.integers(0, len(usable)))]
                selected = np.array(clusters[chosen_place], dtype=int)
            else:
                # No multi-mesa cluster exists in this family.  Fall back rather
                # than fabricate one: the shape is recorded honestly as
                # scattered so no stratum claims clustered coverage it lacks.
                injection_shape = "scattered"
                selected = selector.choice(
                    injectable_indices, size=injected_discrepancies, replace=False
                )
        else:
            selected = selector.choice(
                injectable_indices,
                size=injected_discrepancies,
                replace=False,
            )
        for raw_index in selected:
            index = int(raw_index)
            before = simulated_peer[index]
            numerator_before, denominator_before = _simulation_pair(before)
            after = _inject(before, effective_injection_size, direction=injection_direction)
            numerator_after, denominator_after = _simulation_pair(after)
            realized_effect_pp = (
                abs(numerator_after / denominator_after - numerator_before / denominator_before)
                * 100
            )
            if realized_effect_pp <= 0:
                raise ValueError("synthetic injection produced no metric-rate change")
            simulated_peer[index] = after
            key = signal_key("peer", _family_id(after), after.mesa_id)
            injected.add(key)
            injection_records.append(
                InjectionEvidence(
                    signal_key=key,
                    metric=after.metric,
                    direction=injection_direction,
                    shape=injection_shape,
                    denominator_band=_denominator_band(denominator_before),
                    effect_boundary=_effect_boundary(effective_injection_size),
                    realized_effect_band=_realized_effect_band(realized_effect_pp),
                    requested_effect_fraction=effective_injection_size,
                    realized_effect_pp=realized_effect_pp,
                    numerator_before=numerator_before,
                    numerator_after=numerator_after,
                    denominator_before=denominator_before,
                    denominator_after=denominator_after,
                )
            )
    bound_peer = _bind_peer_rows(tuple(simulated_peer))
    peer_output = peer_signals(bound_peer)

    bound_spatial: tuple[SpatialMesa, ...] = ()
    spatial_output: tuple[SpatialSignal, ...] = ()
    if spatial_rows:
        bound_spatial = _synthetic_spatial_rows(spatial_rows, np.random.default_rng([run_seed, 2]))
        spatial_output = spatial_residual_signals(
            bound_spatial,
            permutations=spatial_initial_permutations,
            max_permutations=spatial_max_permutations,
        )

    # Never union untyped detector identities: a spatial flag must not become a
    # peer true positive merely because it names the same mesa/family.
    public_flagged = {
        signal_key("peer", item.family_id, item.mesa_id) for item in peer_output if item.signal
    } | {
        signal_key("spatial", item.family_id, item.mesa_id)
        for item in spatial_output
        if item.signal
    }
    flagged = {
        signal_key("peer", item.family_id, item.mesa_id)
        for item in peer_output
        if peer_research_detection(item)
    } | {
        signal_key("spatial", item.family_id, item.mesa_id)
        for item in spatial_output
        if getattr(item, "research_signal", item.signal)
    }
    true_positive = len(flagged & injected)
    false_positive = len(flagged - injected)
    false_negative = len(injected - flagged)
    fdp = false_positive / max(len(flagged), 1) if mode == "alternative" else None
    spatial_residual_hash = bound_spatial[0].peer_residual_artifact_hash if bound_spatial else None
    return SimulationRunEvidence(
        run_index=run_index,
        mode=mode,
        seed=run_seed,
        peer_input_artifact_hash=bound_peer[0].input_artifact_hash,
        peer_cohort_hash=bound_peer[0].cohort_hash,
        spatial_residual_data_hash=(_rows_hash(bound_spatial) if bound_spatial else None),
        spatial_peer_residual_artifact_hash=spatial_residual_hash,
        spatial_cohort_hash=spatial_output[0].cohort_hash if spatial_output else None,
        spatial_input_artifact_hash=(
            spatial_output[0].input_artifact_hash if spatial_output else None
        ),
        injected_keys=tuple(sorted(injected)),
        injections=tuple(
            replace(item, detected=item.signal_key in flagged) for item in injection_records
        ),
        flagged_keys=tuple(sorted(flagged)),
        public_flagged_keys=tuple(sorted(public_flagged)),
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        false_discoveries=false_positive,
        fdp=fdp,
        spatial_permutations=spatial_output[0].permutations if spatial_output else None,
        injection_effect_fraction=effective_injection_size,
        injection_direction=injection_direction,
    )


def _unique_seeds(rng: np.random.Generator, count: int) -> tuple[int, ...]:
    result: list[int] = []
    seen: set[int] = set()
    while len(result) < count:
        value = int(rng.integers(0, 2**63 - 1))
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def run_end_to_end_validation(
    *,
    release_id: str,
    peer_records: Iterable[MesaMetrics],
    spatial_records: Iterable[SpatialMesa] = (),
    simulations: int | None = None,
    seed: int | None = None,
    injected_discrepancies: int = 1,
    injection_size: float = 0.25,
    profile: str | SimulationProfile = CI_PROFILE.name,
) -> SimulationSummary:
    """Run independent null and alternative arms through the real analyzers.

    The selected profile declares the number of runs in each arm.  The full
    release profile is 1,000 null and 1,000 alternative runs; the smaller CI
    profile is deterministic but never sufficient to make production eligible.
    Spatial families below their own eligibility floor remain ineligible; no
    coordinates or coverage are invented merely to obtain a signal.
    """
    if isinstance(profile, str):
        try:
            selected_profile = SIMULATION_PROFILES[profile]
        except KeyError as exc:
            raise ValueError("simulation profile is not recognized") from exc
    elif isinstance(profile, SimulationProfile):
        selected_profile = profile
        registered = SIMULATION_PROFILES.get(profile.name)
        if registered is not None and profile.artifact_hash != registered.artifact_hash:
            raise ValueError("registered simulation profile name cannot be redefined")
    else:
        raise ValueError("simulation profile must be a registered name or SimulationProfile")
    if seed is not None and seed != selected_profile.seed:
        raise ValueError("simulation profile seed is frozen and cannot be overridden")
    arm_simulations = selected_profile.null_simulations if simulations is None else simulations
    if selected_profile.null_simulations != selected_profile.alternative_simulations:
        raise ValueError("this validator requires balanced null and alternative profile arms")
    if type(arm_simulations) is not int or arm_simulations < 100:
        raise ValueError("at least 100 simulations per design arm are required")
    if arm_simulations < selected_profile.null_simulations:
        raise ValueError(
            f"profile {selected_profile.name} requires at least "
            f"{selected_profile.null_simulations} simulations per arm"
        )
    run_seed = selected_profile.seed if seed is None else seed
    if type(run_seed) is not int or run_seed < 0:
        raise ValueError("simulation seed must be a nonnegative integer")
    if (
        isinstance(injection_size, bool)
        or not isinstance(injection_size, (int, float))
        or not isfinite(float(injection_size))
        or not 0 < injection_size <= 1
        or type(injected_discrepancies) is not int
        or injected_discrepancies < 1
    ):
        raise ValueError("injection configuration is invalid")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("release_id is required")
    peer_rows = tuple(sorted(peer_records, key=lambda row: row.mesa_id))
    spatial_rows = tuple(sorted(spatial_records, key=lambda row: row.mesa_id))
    if not peer_rows:
        raise ValueError("end-to-end validation needs MesaMetrics records")
    if injected_discrepancies > len(peer_rows):
        raise ValueError("injected discrepancies exceed the peer family size")
    _validate_original_inputs(peer_rows, spatial_rows)
    if spatial_rows and any(
        not _cross_detector_compatible(peer_rows[0], row) for row in spatial_rows
    ):
        raise ValueError("peer and spatial validation cohorts must describe the same fact")

    include_spatial = bool(spatial_rows)
    bindings = detector_bindings(include_spatial=include_spatial)
    input_hashes = {"peer": _rows_hash(peer_rows)}
    declarations = {"peer": _peer_declaration(peer_rows[0])}
    family_sizes = {
        signal_key("peer", _family_id(peer_rows[0]), "__family__"): peer_rows[
            0
        ].expected_family_count
    }
    if spatial_rows:
        input_hashes["spatial"] = _rows_hash(spatial_rows)
        declarations["spatial"] = _spatial_declaration(spatial_rows[0])
        family_sizes[signal_key("spatial", _family_id(spatial_rows[0]), "__family__")] = (
            spatial_rows[0].expected_family_count
        )
    cohort_hash = _hash({"cohort_declarations": declarations, "input_data_hashes": input_hashes})

    master_rng = np.random.default_rng(run_seed)
    seeds = _unique_seeds(master_rng, arm_simulations * 2)
    null_seeds = seeds[:arm_simulations]
    alternative_seeds = seeds[arm_simulations:]
    null_runs = tuple(
        _run_evidence(
            mode="pure_null",
            run_index=index,
            run_seed=run_seed,
            peer_rows=peer_rows,
            spatial_rows=spatial_rows,
            injected_discrepancies=injected_discrepancies,
            injection_size=float(injection_size),
            spatial_initial_permutations=selected_profile.spatial_initial_permutations,
            spatial_max_permutations=selected_profile.spatial_max_permutations,
            policy_boundary_injections=selected_profile.policy_boundary_injections,
        )
        for index, run_seed in enumerate(null_seeds)
    )
    alternative_runs = tuple(
        _run_evidence(
            mode="alternative",
            run_index=index,
            run_seed=run_seed,
            peer_rows=peer_rows,
            spatial_rows=spatial_rows,
            injected_discrepancies=injected_discrepancies,
            injection_size=float(injection_size),
            spatial_initial_permutations=selected_profile.spatial_initial_permutations,
            spatial_max_permutations=selected_profile.spatial_max_permutations,
            policy_boundary_injections=selected_profile.policy_boundary_injections,
        )
        for index, run_seed in enumerate(alternative_seeds)
    )

    family_error_count = sum(1 for run in null_runs if run.flagged_keys)
    family_error_bound = _upper_binomial_bound(family_error_count, arm_simulations)
    mean_false_discoveries = sum(run.false_discoveries for run in null_runs) / arm_simulations
    false_discovery_probability = family_error_count / arm_simulations
    alternative_fdp = tuple(run.fdp for run in alternative_runs)
    assert all(value is not None for value in alternative_fdp)
    empirical_fdr = sum(value for value in alternative_fdp if value is not None) / arm_simulations

    by_key: dict[str, dict[str, int]] = defaultdict(
        lambda: {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    )
    for run in alternative_runs:
        injected = set(run.injected_keys)
        flagged = set(run.flagged_keys)
        for key in flagged & injected:
            by_key[key]["true_positive"] += 1
        for key in flagged - injected:
            by_key[key]["false_positive"] += 1
        for key in injected - flagged:
            by_key[key]["false_negative"] += 1
    confusion_by_key = {key: by_key[key] for key in sorted(by_key)}
    confusion_totals = {
        label: sum(counts[label] for counts in confusion_by_key.values())
        for label in ("true_positive", "false_positive", "false_negative")
    }
    injected_total = confusion_totals["true_positive"] + confusion_totals["false_negative"]
    power = confusion_totals["true_positive"] / injected_total if injected_total else 0.0
    family_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"detected": 0, "injected": 0})
    for key, counts in confusion_by_key.items():
        detector_id, family_id, _unit_id = decode_signal_key(key)
        detector_family = signal_key(detector_id, family_id, "__family__")
        family_counts[detector_family]["detected"] += counts["true_positive"]
        family_counts[detector_family]["injected"] += (
            counts["true_positive"] + counts["false_negative"]
        )
    power_by_family: dict[str, dict[str, int | float | str | None]] = {}
    for family_id in sorted(family_counts):
        counts = family_counts[family_id]
        # A detector family can appear here through a false positive alone, so
        # it may carry zero injected alternatives.  Power is then unmeasured,
        # which is not the same fact as zero power.
        measured = counts["injected"] > 0
        power_by_family[family_id] = {
            **counts,
            "power": counts["detected"] / counts["injected"] if measured else None,
            "lower_confidence_bound": _lower_binomial_bound(counts["detected"], counts["injected"]),
            "status": "measured" if measured else "no_injected_alternatives",
        }

    stratum_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"detected": 0, "injected": 0})
    for run in alternative_runs:
        for injection in run.injections:
            stratum = _injection_stratum(injection)
            stratum_counts[stratum]["injected"] += 1
            stratum_counts[stratum]["detected"] += int(injection.detected)
    power_by_stratum: dict[str, dict[str, int | float]] = {}
    for stratum in sorted(stratum_counts):
        counts = stratum_counts[stratum]
        power_by_stratum[stratum] = {
            **counts,
            "power": counts["detected"] / counts["injected"],
            "lower_confidence_bound": _lower_binomial_bound(counts["detected"], counts["injected"]),
        }

    metric = peer_rows[0].metric
    null_error_by_metric: dict[str, dict[str, int | float]] = {
        metric: {
            "family_errors": family_error_count,
            "runs": arm_simulations,
            "error_rate": false_discovery_probability,
            "upper_confidence_bound": family_error_bound,
        }
    }

    false_discovery_gate = family_error_bound <= _TARGET and empirical_fdr <= _TARGET
    # Spatial alternatives are deliberately not invented from peer rows.  They
    # remain explicitly ineligible until a separately predeclared spatial
    # calibration design is supplied.
    detector_validation: dict[str, dict[str, object]] = {
        "peer": {
            "status": "calibration_pending_independent_full_artifact",
            "profile": selected_profile.name,
            "production_eligible": False,
            "research_detection_endpoint": "peer_research_detection-v1",
            "public_signal_forced_false": True,
            "trusted_input_registry_verified": False,
            "external_family_ledger_verified": False,
            "roster_requirement": (
                "expected family count/digest must be authenticated by an external "
                "trusted registry; row declarations cannot self-certify"
            ),
            "power_target": _POWER_TARGET,
            "confidence": _POWER_CONFIDENCE,
        }
    }
    if spatial_rows:
        detector_validation["spatial"] = {
            "status": "unvalidated_ineligible",
            "reason": "no predeclared spatial alternative calibration design",
        }
    power_gate = bool(power_by_stratum) and all(
        float(item["lower_confidence_bound"]) >= _POWER_TARGET for item in power_by_stratum.values()
    )
    total_runs = arm_simulations * 2
    summary = SimulationSummary(
        simulations=total_runs,
        null_simulations=arm_simulations,
        alternative_simulations=arm_simulations,
        seed=run_seed,
        mean_false_discoveries=mean_false_discoveries,
        false_discovery_probability=false_discovery_probability,
        injected_discrepancy_detection_rate=power,
        false_discovery_target=_TARGET,
        false_discovery_gate_passed=false_discovery_gate,
        injected_discrepancy_gate_passed=power_gate,
        # The honest conjunction of the two computed gates, and nothing more.
        # It was previously hardcoded False to express "not production ready",
        # which made an artifact whose gates genuinely passed indistinguishable
        # from a forgery to the verifier.  Production readiness is expressed by
        # production_eligible / independent_full_artifact_passed below, which
        # remain False and do not read this field.
        release_gate_passed=false_discovery_gate and power_gate,
        release_id=release_id,
        cohort_hash=cohort_hash,
        detector_hash=detector_binding_hash(bindings),
        methodology_hash=simulation_methodology_hash(bindings),
        detector_bindings=bindings,
        input_data_hashes=input_hashes,
        cohort_declarations=declarations,
        family_sizes=family_sizes,
        seeds=seeds,
        null_seeds=null_seeds,
        alternative_seeds=alternative_seeds,
        run_spec={
            "alternative_runs": arm_simulations,
            "null": (
                "real-denominator hierarchy, beta-binomial overdispersion, compositional "
                "dependence, preserved missingness, heavy tails, zero inflation, and "
                "model-misspecification mixture"
            ),
            "null_runs": arm_simulations,
            "run_arms": ["pure_null", "alternative"],
            "spatial_adjustment": "synchronized family max-T within-municipality blocks",
            "spatial_permutation_budget": {
                "initial": selected_profile.spatial_initial_permutations,
                "maximum": selected_profile.spatial_max_permutations,
            },
        },
        injection_spec={
            "count_per_run": injected_discrepancies,
            "effect_fraction_of_denominator": float(injection_size),
            "key_schema": "canonical-json-[detector_id,family_id,analysis_unit_id]",
            "policy_boundary_injections": {
                "enabled": selected_profile.policy_boundary_injections,
                "effect_size_gate": "0.08 and 0.25 denominator fractions",
                "minimum_denominator": 80,
                "saturation": "excluded from injectable selection",
            },
            "types": [peer_rows[0].metric],
            "directions": ["positive", "negative"],
            "power_gate_scope": (
                "metric x direction x denominator-band x requested-effect-boundary x "
                "realized-effect-band; pooled power is descriptive only"
            ),
        },
        detector_validation=detector_validation,
        null_runs=null_runs,
        alternative_runs=alternative_runs,
        confusion_totals=confusion_totals,
        confusion_by_signal_key=confusion_by_key,
        power_by_family=power_by_family,
        power_by_stratum=power_by_stratum,
        null_error_by_metric=null_error_by_metric,
        family_error_upper_confidence=family_error_bound,
        empirical_fdr=empirical_fdr,
        family_error_count=family_error_count,
        profile_name=selected_profile.name,
        profile_hash=selected_profile.artifact_hash,
        attestation=runtime_attestation(),
        independent_full_artifact_required=selected_profile.independent_artifact_required,
        independent_full_artifact_passed=False,
        production_eligible=False,
        trusted_input_registry_verified=False,
        external_family_ledger_verified=False,
    )
    return summary.with_hash()


def run_synthetic_validation(*args: object, **kwargs: object) -> SimulationSummary:
    """Removed detector-stub entry point; validation must run real analyzers."""
    raise TypeError("use run_end_to_end_validation with MesaMetrics and SpatialMesa inputs")
