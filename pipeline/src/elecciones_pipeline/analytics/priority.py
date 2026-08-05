"""Public, deterministic audit-priority methodology v1."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import isfinite
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .peer_signals import PeerSignal
    from .reconciliation import MesaIdentity, ReconciliationResult
    from .spatial import SpatialSignal

METHODOLOGY_VERSION = "audit-priority-v2.0.0"
DISCLOSURE_ES = (
    "Este puntaje prioriza registros para revisión. No es una probabilidad ni un hallazgo "
    "de fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores."
)
DISCLOSURE_EN = (
    "This score prioritizes records for review. It is not a probability or finding of fraud. "
    "Absence of a signal does not prove that a mesa was error-free."
)


@dataclass(frozen=True)
class EvidenceComponent:
    name: str
    points: int
    observed_value: float | int | None
    comparator: str
    calculation: str
    peer_definition: str | None
    source_links: tuple[str, ...]
    limitations: tuple[str, ...]
    affected_votes: int
    evidence_artifact_hash: str | None = None
    evidence_artifact_kind: str | None = None
    analyzer_output_hash: str | None = None
    family_id: str | None = None
    expected_family_count: int | None = None
    expected_family_digest: str | None = None
    cohort_hash: str | None = None
    input_artifact_hash: str | None = None
    code_hash: str | None = None
    method_hash: str | None = None
    p_value: float | None = None
    q_value: float | None = None
    family_rank: int | None = None
    family_size: int | None = None
    adjustment_method: str | None = None
    analyzer_mesa_id: str | None = None
    analysis_unit_id: str | None = None
    peer_residual_artifact_hash: str | None = None
    peer_methodology_version: str | None = None
    coordinate_source_url: str | None = None
    coordinate_source_hash: str | None = None
    coordinate_accuracy_m: float | None = None
    coordinate_grain: str | None = None
    peer_observed_rate: float | None = None
    peer_expected_rate: float | None = None
    peer_count: int | None = None
    standardized_residual: float | None = None
    effect_pp: float | None = None
    fit_method: str | None = None
    public_point_eligible: bool | None = None
    analyzer_reason: str | None = None
    spatial_neighbors: tuple[str, ...] | None = None
    spatial_signal_kind: str | None = None
    spatial_local_residual: float | None = None
    randomization_seed: int | None = None
    spatial_permutations: int | None = None
    analysis_unit_digest: str | None = None
    expected_mesa_count: int | None = None
    expected_mesa_digest: str | None = None
    mesa_membership_digest: str | None = None
    expected_mesa_membership_digest: str | None = None
    observed_rate: float | None = None
    expected_rate: float | None = None
    peers: int | None = None
    neighbors: tuple[str, ...] | None = None
    signal_kind: str | None = None
    local_statistic: float | None = None
    local_residual: float | None = None
    permutations: int | None = None
    methodology_version: str = METHODOLOGY_VERSION

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AuditPriority:
    score: int
    tier: str
    deterministic_points: int
    statistical_points: int
    components: tuple[EvidenceComponent, ...]
    disclosure_es: str = DISCLOSURE_ES
    disclosure_en: str = DISCLOSURE_EN
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class DocumentReviewArtifact:
    """A trusted, self-hashed human-review conclusion used for public priority.

    This is deliberately an evidence artifact, not a caller-owned score input.
    The release builder must independently place its hash in the supplied trust
    registry before it can contribute points.
    """

    record_id: str
    review_kind: str
    source_links: tuple[str, ...]
    affected_votes: int = 0
    documentary_difference_votes: int = 0
    documentary_difference_pp: float = 0.0
    expected_document_status: str = "complete"
    independently_verified: bool = False
    input_artifact_hashes: tuple[str, ...] = ()
    output_hash: str = ""
    schema_version: str = "document-review-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("document review record_id is required")
        if self.review_kind not in {
            "verified_accounting_failure",
            "conflicting_official_records",
            "documentary_comparison",
            "document_coverage",
        }:
            raise ValueError("document review kind is invalid")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (self.affected_votes, self.documentary_difference_votes)
        ):
            raise ValueError("document review vote values must be nonnegative integers")
        if (
            not _finite_numeric(self.documentary_difference_pp)
            or not 0 <= float(self.documentary_difference_pp) <= 100
        ):
            raise ValueError("document review percentage-point difference is invalid")
        if self.expected_document_status not in {"complete", "missing", "duplicated", "ambiguous"}:
            raise ValueError("document review status is invalid")
        if not self.source_links or any(not _is_https_url(link) for link in self.source_links):
            raise ValueError("document review requires official source links")
        if (
            not self.input_artifact_hashes
            or tuple(sorted(set(self.input_artifact_hashes))) != self.input_artifact_hashes
            or any(not _is_sha256(value) for value in self.input_artifact_hashes)
        ):
            raise ValueError("document review requires sorted unique SHA-256 input hashes")
        if self.output_hash and not _is_sha256(self.output_hash):
            raise ValueError("document review output_hash must be SHA-256")

    def artifact_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("output_hash")
        return payload

    def with_hash(self) -> DocumentReviewArtifact:
        encoded = json.dumps(self.artifact_payload(), sort_keys=True, separators=(",", ":"))
        return replace(self, output_hash=sha256(encoded.encode()).hexdigest())


def _component(
    name: str,
    points: int,
    observed: float | int | None,
    comparator: str,
    calculation: str,
    links: Iterable[str],
    limitations: Iterable[str],
    affected_votes: int,
    peer_definition: str | None = None,
    evidence_artifact_hash: str | None = None,
    evidence_artifact_kind: str | None = None,
) -> EvidenceComponent:
    return EvidenceComponent(
        name=name,
        points=points,
        observed_value=observed,
        comparator=comparator,
        calculation=calculation,
        peer_definition=peer_definition,
        source_links=tuple(sorted(set(links))),
        limitations=tuple(limitations),
        affected_votes=max(0, affected_votes),
        evidence_artifact_hash=evidence_artifact_hash,
        evidence_artifact_kind=evidence_artifact_kind,
    )


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


def _finite_numeric(value: object) -> bool:
    return (
        not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(float(value))
    )


def _trusted_hash_registry(values: Iterable[str] | None, *, label: str) -> frozenset[str]:
    if values is None:
        raise ValueError(f"{label} trust registry is required")
    registry = tuple(values)
    if len(set(registry)) != len(registry) or any(not _is_sha256(value) for value in registry):
        raise ValueError(f"{label} trust registry is invalid")
    return frozenset(registry)


def audit_priority(
    *,
    reconciliation_artifacts: Iterable[object] = (),
    document_review_artifacts: Iterable[DocumentReviewArtifact] = (),
    trusted_reconciliation_hashes: Iterable[str] | None = None,
    trusted_document_review_hashes: Iterable[str] | None = None,
    limitations: Iterable[str] = (),
    peer_analysis: PeerSignal | None = None,
    spatial_analysis: SpatialSignal | None = None,
    target_mesa_identity: MesaIdentity | None = None,
    target_record_id: str | None = None,
    target_mesa_id: str | None = None,
    **legacy_raw_inputs: object,
) -> AuditPriority:
    """Apply the fixed v1 point table (maximum, never additive, deterministic base)."""
    if legacy_raw_inputs:
        raise ValueError("raw priority inputs are forbidden; provide trusted evidence artifacts")
    reconciliation_artifacts = tuple(reconciliation_artifacts)
    document_review_artifacts = tuple(document_review_artifacts)
    reconciliation_registry = (
        _trusted_hash_registry(trusted_reconciliation_hashes, label="reconciliation")
        if reconciliation_artifacts
        else frozenset()
    )
    review_registry = (
        _trusted_hash_registry(trusted_document_review_hashes, label="document review")
        if document_review_artifacts
        else frozenset()
    )
    components: list[EvidenceComponent] = []
    base: list[int] = []
    common_limits = tuple(limitations) or (
        "Requires inspection of the underlying official document.",
    )
    statistical_limits = (
        *common_limits,
        "A statistical signal is a review lead, never a verified affected-vote count.",
    )
    target_mesa_key: tuple[str, str, str, str] | None = None
    if reconciliation_artifacts:
        if target_mesa_identity is None:
            raise ValueError("reconciliation priority requires a target_mesa_identity")
        target_mesa_key = (
            target_mesa_identity.department,
            target_mesa_identity.municipality,
            target_mesa_identity.place,
            target_mesa_identity.mesa,
        )
    for artifact in reconciliation_artifacts:
        from .reconciliation import ReconciliationResult

        if not isinstance(artifact, ReconciliationResult):
            raise ValueError("priority reconciliation evidence has an invalid type")
        if artifact.output_hash != _reconciliation_hash(artifact):
            raise ValueError("reconciliation evidence output hash is invalid")
        if artifact.output_hash not in reconciliation_registry:
            raise ValueError("reconciliation evidence is not in the explicit trust registry")
        artifact_links = _reconciliation_links(artifact)
        for issue in artifact.arithmetic_issues:
            if issue.identity != target_mesa_identity:
                continue
            base.append(100)
            components.append(
                _component(
                    "source_accounting_failure",
                    100,
                    issue.observed_left - issue.observed_right,
                    "authenticated source-local accounting identity fails",
                    "100 points from trusted reconciliation output.",
                    (issue.source_url,) if issue.source_url else (),
                    common_limits,
                    0,
                    evidence_artifact_hash=artifact.output_hash,
                    evidence_artifact_kind="reconciliation_result",
                )
            )
        for _source, identities in artifact.conflicting_identities.items():
            for _identity in identities:
                if _identity != target_mesa_identity:
                    continue
                base.append(100)
                components.append(
                    _component(
                        "conflicting_official_records",
                        100,
                        None,
                        "authenticated records for the same canonical identity disagree",
                        "100 points from trusted reconciliation output.",
                        artifact_links,
                        common_limits,
                        0,
                        evidence_artifact_hash=artifact.output_hash,
                        evidence_artifact_kind="reconciliation_result",
                    )
                )
        for comparison in artifact.comparisons:
            if comparison.level != "mesa" or comparison.key != target_mesa_key:
                continue
            # A one-field source difference is not a ballot-edit estimate.
            # Only the explicitly declared complete-vector lower bound can
            # affect documentary review priority.
            edits = comparison.minimum_ballot_edits
            if comparison.minimum_ballot_edits_status.value != "evaluable" or edits is None:
                continue
            points = 70 if edits >= 5 else 45
            if edits == 0:
                continue
            base.append(points)
            components.append(
                _component(
                    "documentary_difference_major"
                    if points == 70
                    else "documentary_difference_minor",
                    points,
                    edits,
                    ">=5 votes" if points == 70 else "1–4 votes",
                    "Points derived from trusted reconciliation comparison.",
                    artifact_links,
                    common_limits,
                    edits,
                    evidence_artifact_hash=artifact.output_hash,
                    evidence_artifact_kind="reconciliation_result",
                )
            )
        for status in (
            *(
                status
                for identity, status in artifact.completeness.items()
                if identity == target_mesa_identity
            ),
            *(
                value
                for layer in artifact.completeness_by_source.values()
                for identity, value in layer.items()
                if identity == target_mesa_identity
            ),
        ):
            if status.value in {"missing", "duplicated", "ambiguous"}:
                base.append(25)
                components.append(
                    _component(
                        "document_coverage_incomplete",
                        25,
                        None,
                        "missing, duplicated, or ambiguous expected official document",
                        "25 points from trusted reconciliation coverage.",
                        artifact_links,
                        common_limits,
                        0,
                        evidence_artifact_hash=artifact.output_hash,
                        evidence_artifact_kind="reconciliation_result",
                    )
                )
    for artifact in document_review_artifacts:
        if artifact.output_hash != _document_review_hash(artifact):
            raise ValueError("document review output hash is invalid")
        if artifact.output_hash not in review_registry:
            raise ValueError("document review is not in the explicit trust registry")
        if not isinstance(target_record_id, str) or not target_record_id:
            raise ValueError("document review priority requires a target_record_id")
        if artifact.record_id != target_record_id:
            continue
        if artifact.review_kind == "verified_accounting_failure":
            if not artifact.independently_verified:
                raise ValueError("accounting review requires independent verification")
            base.append(100)
            components.append(
                _component(
                    "verified_accounting_failure",
                    100,
                    artifact.affected_votes,
                    "two authenticated independent reviews agree",
                    "100 points from trusted document review.",
                    artifact.source_links,
                    common_limits,
                    artifact.affected_votes,
                    evidence_artifact_hash=artifact.output_hash,
                    evidence_artifact_kind="document_review",
                )
            )
        elif artifact.review_kind == "conflicting_official_records":
            base.append(100)
            components.append(
                _component(
                    "conflicting_official_records",
                    100,
                    artifact.affected_votes,
                    "authenticated official records conflict",
                    "100 points from trusted document review.",
                    artifact.source_links,
                    common_limits,
                    artifact.affected_votes,
                    evidence_artifact_hash=artifact.output_hash,
                    evidence_artifact_kind="document_review",
                )
            )
        elif artifact.review_kind == "documentary_comparison":
            points = (
                70
                if artifact.documentary_difference_votes >= 5
                or artifact.documentary_difference_pp >= 2
                else 45
            )
            if artifact.documentary_difference_votes or artifact.documentary_difference_pp >= 2:
                base.append(points)
                components.append(
                    _component(
                        "documentary_difference_major"
                        if points == 70
                        else "documentary_difference_minor",
                        points,
                        artifact.documentary_difference_votes,
                        ">=5 votes or >=2 percentage points"
                        if points == 70
                        else "1–4 votes and <2 percentage points",
                        "Points derived from trusted document review.",
                        artifact.source_links,
                        common_limits,
                        max(artifact.affected_votes, artifact.documentary_difference_votes),
                        evidence_artifact_hash=artifact.output_hash,
                        evidence_artifact_kind="document_review",
                    )
                )
        elif (
            artifact.review_kind == "document_coverage"
            and artifact.expected_document_status != "complete"
        ):
            base.append(25)
            components.append(
                _component(
                    "document_coverage_incomplete",
                    25,
                    None,
                    "missing, duplicated, or ambiguous expected official document",
                    "25 points from trusted document review.",
                    artifact.source_links,
                    common_limits,
                    artifact.affected_votes,
                    evidence_artifact_hash=artifact.output_hash,
                    evidence_artifact_kind="document_review",
                )
            )
    # Statistical outputs remain useful research evidence, but a caller-owned
    # dataclass and self-declared hash are not a trust boundary.  Public points
    # stay disabled until a separate trusted registry and independent replay
    # verifier are implemented.
    statistical: list[EvidenceComponent] = []
    research_only_limits = (
        *statistical_limits,
        "No trusted statistical artifact registry and independent replay verifier is "
        "configured; this component contributes zero public priority points.",
    )
    peer_flagged = False
    spatial_flagged = False
    if peer_analysis is not None:
        from .peer_signals import PeerSignal, peer_research_detection

        if not isinstance(peer_analysis, PeerSignal):
            raise ValueError("priority peer evidence has an invalid type")
        peer_flagged = bool(peer_analysis.signal or peer_research_detection(peer_analysis))
        if target_mesa_id is not None and (
            not isinstance(target_mesa_id, str)
            or not target_mesa_id
            or peer_analysis.mesa_id != target_mesa_id
        ):
            raise ValueError("peer analyzer mesa does not match the priority target")
    if spatial_analysis is not None:
        from .spatial import SpatialSignal

        if not isinstance(spatial_analysis, SpatialSignal):
            raise ValueError("priority spatial evidence has an invalid type")
        spatial_flagged = bool(spatial_analysis.signal or spatial_analysis.research_signal)
        if target_mesa_id is not None and (
            not isinstance(target_mesa_id, str)
            or not target_mesa_id
            or spatial_analysis.mesa_id != target_mesa_id
        ):
            raise ValueError("spatial analyzer mesa does not match the priority target")
    if peer_flagged and spatial_flagged:
        assert peer_analysis is not None and spatial_analysis is not None
        peer_scope = (
            peer_analysis.mesa_id,
            peer_analysis.election_slug,
            peer_analysis.data_version,
            peer_analysis.source_layer,
            peer_analysis.source_type,
            peer_analysis.legal_status,
        )
        spatial_scope = (
            spatial_analysis.mesa_id,
            spatial_analysis.election_slug,
            spatial_analysis.data_version,
            spatial_analysis.source_layer,
            spatial_analysis.source_type,
            spatial_analysis.legal_status,
        )
        if peer_scope != spatial_scope:
            raise ValueError("statistical analyzer outputs refer to different release facts")
    if peer_flagged:
        assert peer_analysis is not None
        statistical.append(
            _component(
                "peer_distribution",
                0,
                peer_analysis.observed_rate,
                "research-only output; public statistical scoring is disabled",
                peer_analysis.calculation,
                peer_analysis.source_links,
                research_only_limits,
                0,
                peer_analysis.peer_definition,
            )
        )
        statistical[-1] = replace(
            statistical[-1],
            analyzer_output_hash=peer_analysis.output_hash or None,
            family_id=peer_analysis.family_id,
            expected_family_count=peer_analysis.expected_family_count,
            expected_family_digest=peer_analysis.expected_family_digest,
            cohort_hash=peer_analysis.cohort_hash,
            input_artifact_hash=peer_analysis.input_artifact_hash,
            code_hash=peer_analysis.code_hash,
            method_hash=peer_analysis.method_hash,
            p_value=peer_analysis.tail_probability,
            q_value=peer_analysis.adjusted_q_value,
            family_rank=peer_analysis.family_rank,
            family_size=peer_analysis.family_size,
            adjustment_method=peer_analysis.adjustment_method,
            analyzer_mesa_id=peer_analysis.mesa_id,
            peer_observed_rate=peer_analysis.observed_rate,
            peer_expected_rate=peer_analysis.expected_rate,
            peer_count=peer_analysis.peers,
            standardized_residual=peer_analysis.standardized_residual,
            effect_pp=peer_analysis.effect_pp,
            fit_method=peer_analysis.fit_method,
            public_point_eligible=peer_analysis.public_point_eligible,
            analyzer_reason=peer_analysis.reason,
            observed_rate=peer_analysis.observed_rate,
            expected_rate=peer_analysis.expected_rate,
            peers=peer_analysis.peers,
        )
    if spatial_flagged:
        assert spatial_analysis is not None
        statistical.append(
            _component(
                "spatial_cluster",
                0,
                spatial_analysis.observed_value,
                "research-only output; public statistical scoring is disabled",
                spatial_analysis.calculation,
                (*spatial_analysis.source_links, spatial_analysis.coordinate_source_url),
                research_only_limits,
                0,
                spatial_analysis.peer_definition,
            )
        )
        statistical[-1] = replace(
            statistical[-1],
            analyzer_output_hash=spatial_analysis.output_hash or None,
            family_id=spatial_analysis.family_id,
            expected_family_count=spatial_analysis.expected_family_count,
            expected_family_digest=spatial_analysis.expected_family_digest,
            cohort_hash=spatial_analysis.cohort_hash,
            input_artifact_hash=spatial_analysis.input_artifact_hash,
            code_hash=spatial_analysis.code_hash,
            method_hash=spatial_analysis.method_hash,
            p_value=spatial_analysis.permutation_p_value,
            q_value=spatial_analysis.adjusted_q_value,
            family_rank=spatial_analysis.family_rank,
            family_size=spatial_analysis.family_size,
            adjustment_method=spatial_analysis.adjustment_method,
            analyzer_mesa_id=spatial_analysis.mesa_id,
            analysis_unit_id=spatial_analysis.analysis_unit_id,
            peer_residual_artifact_hash=spatial_analysis.peer_residual_artifact_hash,
            peer_methodology_version=spatial_analysis.peer_methodology_version,
            coordinate_source_url=spatial_analysis.coordinate_source_url,
            coordinate_source_hash=spatial_analysis.coordinate_source_hash,
            coordinate_accuracy_m=spatial_analysis.coordinate_accuracy_m,
            coordinate_grain=spatial_analysis.coordinate_grain,
            spatial_neighbors=spatial_analysis.neighbors,
            spatial_signal_kind=spatial_analysis.signal_kind,
            spatial_local_residual=spatial_analysis.local_residual,
            randomization_seed=spatial_analysis.randomization_seed,
            spatial_permutations=spatial_analysis.permutations,
            analysis_unit_digest=spatial_analysis.analysis_unit_digest,
            expected_mesa_count=spatial_analysis.expected_mesa_count,
            expected_mesa_digest=spatial_analysis.expected_mesa_digest,
            mesa_membership_digest=spatial_analysis.mesa_membership_digest,
            expected_mesa_membership_digest=spatial_analysis.expected_mesa_membership_digest,
            public_point_eligible=spatial_analysis.public_point_eligible,
            analyzer_reason=spatial_analysis.reason,
            neighbors=spatial_analysis.neighbors,
            signal_kind=spatial_analysis.signal_kind,
            local_statistic=spatial_analysis.observed_value,
            local_residual=spatial_analysis.local_residual,
            permutations=spatial_analysis.permutations,
        )
    statistical_points = 0
    deterministic_points = max(base, default=0)
    score = min(100, deterministic_points + statistical_points)
    if any(component.points > 0 and not component.source_links for component in components):
        raise ValueError("every scored component requires at least one official source link")
    if score >= 70:
        tier = "documentary_review_prioritized"
    elif score >= 45:
        tier = "documentary_comparison_recommended"
    elif score >= 15:
        tier = "statistical_or_coverage_issue"
    else:
        tier = "no_review_signals"
    return AuditPriority(
        score, tier, deterministic_points, statistical_points, tuple(components + statistical)
    )


def _analysis_hash(value: Any) -> str:
    """Bind a public statistical component to the exact analyzer output."""
    if value is None:
        return ""
    payload = asdict(value)
    payload.pop("output_hash")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode()).hexdigest()


def _reconciliation_links(value: ReconciliationResult) -> tuple[str, ...]:
    links: set[str] = set()
    for provenance in (value.source_provenance or {}).values():
        source_urls = provenance.get("source_urls", ())
        if isinstance(source_urls, tuple):
            links.update(link for link in source_urls if _is_https_url(link))
    return tuple(sorted(links))


def _reconciliation_hash(value: ReconciliationResult) -> str:
    payload = value.artifact_payload()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode()).hexdigest()


def _document_review_hash(value: DocumentReviewArtifact) -> str:
    encoded = json.dumps(value.artifact_payload(), sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()
