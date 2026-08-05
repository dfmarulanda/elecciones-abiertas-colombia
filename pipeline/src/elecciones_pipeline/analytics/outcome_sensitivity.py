"""Authenticated, deterministic top-two outcome sensitivity.

The calculation is a bounded robustness check, not a causal model.  Only
trusted content-addressed source facts and independently authenticated review
artifacts may enter verified totals.  Statistical screening signals and
historical context are ineligible by construction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from urllib.parse import urlsplit

METHODOLOGY_VERSION = "outcome-sensitivity-v3.0.0"
_FACT_SCHEMA = "outcome-source-fact-v1"
_REVIEW_SCHEMA = "outcome-review-v1"
_MARGIN_CERTIFICATE_SCHEMA = "margin-shift-certificate-v1"

_LEVELS = ("mesa", "place", "municipality", "department", "national")
_LEVEL_RANK = {level: rank for rank, level in enumerate(_LEVELS)}
_KEY_LENGTH = {
    "mesa": 4,
    "place": 3,
    "municipality": 2,
    "department": 1,
    "national": 1,
}
_ANALYSIS_LEVELS = frozenset({"mesa", "municipality"})
_ALLOWED_ELECTIONS = frozenset({"presidencia-2026-r2", "presidencia-2026-segunda-vuelta"})
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
    "contextual_baseline": "context_only",
}


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


def _is_sha256(value: object) -> bool:
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


class EvidenceBasis(StrEnum):
    """Permitted and explicitly excluded evidence families."""

    DOCUMENTARY_COMPARISON = "documentary_comparison"
    SOURCE_ACCOUNTING = "source_accounting"
    STATISTICAL_SIGNAL = "statistical_signal"
    HISTORICAL_CONTEXT = "historical_context"


class BoundBasis(StrEnum):
    """Source-observed bases from which an unresolved upper bound may be made."""

    REGISTERED_ELECTORS = "registered_electors"
    REPORTED_BALLOTS = "reported_ballots"
    DOCUMENTED_RECORD_LIMIT = "documented_record_limit"
    STATISTICAL_ESTIMATE = "statistical_estimate"


class SensitivityStatus(StrEnum):
    NOT_EVALUABLE = "not_evaluable"
    ROBUST_WITHIN_EVALUATED_BOUNDS = "robust_within_evaluated_bounds"
    TIE_WITHIN_VERIFIED_BOUND = "tie_within_verified_bound"
    LEAD_CHANGE_WITHIN_VERIFIED_BOUND = "lead_change_within_verified_bound"
    TIE_ONLY_WITH_UNRESOLVED_BOUND = "tie_only_with_unresolved_bound"
    LEAD_CHANGE_ONLY_WITH_UNRESOLVED_BOUND = "lead_change_only_with_unresolved_bound"


@dataclass(frozen=True, order=True)
class GeographicScope:
    """Canonical geographic key using reconciliation's hierarchy order."""

    level: str
    key: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = _KEY_LENGTH.get(self.level)
        if expected is None:
            raise ValueError(f"unknown geographic level: {self.level}")
        if len(self.key) != expected or any(
            not isinstance(part, str) or not part.strip() for part in self.key
        ):
            raise ValueError(f"{self.level} requires {expected} non-empty key components")
        if self.level == "national" and self.key != ("CO",):
            raise ValueError("national scope must use the canonical ('CO',) key")


@dataclass(frozen=True, order=True)
class SourceFactScope:
    """Source layer and the finest published fact grain used in a calculation."""

    source_id: str
    fact_grain: str
    source_type: str = "pre_count"
    legal_status: str = "preliminary"

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("outcome source_id is required")
        if self.fact_grain not in _LEVEL_RANK:
            raise ValueError("outcome fact_grain is invalid")
        if self.source_type not in _SOURCE_LEGAL_STATUS:
            raise ValueError("outcome source_type is invalid")
        if self.legal_status != _SOURCE_LEGAL_STATUS[self.source_type]:
            raise ValueError("outcome source_type/legal_status is incompatible")


@dataclass(frozen=True)
class SourceFactArtifact:
    """A content-addressed source fact whose hash must be externally trusted."""

    fact_ids: tuple[str, ...]
    release_id: str
    election_slug: str
    scope: GeographicScope
    source: SourceFactScope
    values: Mapping[str, int]
    source_links: tuple[str, ...]
    source_content_hash: str
    ballot_universe: str = ""
    expected: int = 1
    retrieved: int = 1
    parsed: int = 1
    missing: int = 0
    ambiguous: int = 0
    excluded: int = 0
    exact_rollup: bool = True
    artifact_hash: str = ""
    schema_version: str = _FACT_SCHEMA

    def __post_init__(self) -> None:
        if (
            not self.fact_ids
            or tuple(sorted(set(self.fact_ids))) != self.fact_ids
            or any(not isinstance(value, str) or not value.strip() for value in self.fact_ids)
        ):
            raise ValueError("source fact IDs must be sorted, unique, and non-empty")
        if not self.release_id or not self.election_slug:
            raise ValueError("source facts require release and election IDs")
        copied: dict[str, int] = {}
        for field, value in self.values.items():
            if not isinstance(field, str) or not field.strip():
                raise ValueError("source fact fields must be non-empty strings")
            _optional_nonnegative_integer("source fact value", value)
            copied[field] = value
        if not copied:
            raise ValueError("source facts require at least one observed value")
        object.__setattr__(self, "values", copied)
        coverage = (
            self.expected,
            self.retrieved,
            self.parsed,
            self.missing,
            self.ambiguous,
            self.excluded,
        )
        if any(type(value) is not int or value < 0 for value in coverage):
            raise ValueError("source fact coverage counts must be nonnegative integers")
        if type(self.exact_rollup) is not bool:
            raise ValueError("source fact exact_rollup must be boolean")
        if not _is_sha256(self.source_content_hash):
            raise ValueError("source facts require a source-content SHA-256")
        if self.ballot_universe and not isinstance(self.ballot_universe, str):
            raise ValueError("source fact ballot_universe must be a string")
        if not self.source_links or any(not _https_url(link) for link in self.source_links):
            raise ValueError("source fact links must be absolute HTTPS URLs")
        if self.artifact_hash and not _is_sha256(self.artifact_hash):
            raise ValueError("source fact artifact_hash must be a SHA-256")
        if self.schema_version != _FACT_SCHEMA:
            raise ValueError("source fact schema version is not frozen")

    def artifact_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("artifact_hash")
        return payload

    def with_hash(self) -> SourceFactArtifact:
        return replace(self, artifact_hash=_hash(self.artifact_payload()))


@dataclass(frozen=True)
class OutcomeObservation:
    """Observed candidate totals bound to trusted source-fact artifacts."""

    scope: GeographicScope
    source: SourceFactScope
    candidate_votes: Mapping[str, int] | None
    source_links: tuple[str, ...] = ()
    expected: int = 1
    retrieved: int = 1
    parsed: int = 1
    missing: int = 0
    ambiguous: int = 0
    excluded: int = 0
    release_id: str = "release-unspecified"
    election_slug: str = "presidencia-2026-r2"
    source_fact_ids: tuple[str, ...] = ("observed-total",)
    fact_artifacts: tuple[SourceFactArtifact, ...] = ()

    def __post_init__(self) -> None:
        coverage = (
            self.expected,
            self.retrieved,
            self.parsed,
            self.missing,
            self.ambiguous,
            self.excluded,
        )
        if any(type(value) is not int or value < 0 for value in coverage):
            raise ValueError("observation coverage counts must be nonnegative integers")
        if not self.release_id or not self.election_slug:
            raise ValueError("observation needs immutable release and election IDs")
        if self.candidate_votes is None:
            return
        copied: dict[str, int] = {}
        for candidate_id, votes in self.candidate_votes.items():
            if not isinstance(candidate_id, str) or not candidate_id.strip():
                raise ValueError("candidate IDs must be non-empty strings")
            _optional_nonnegative_integer("candidate votes", votes)
            copied[candidate_id] = votes
        object.__setattr__(self, "candidate_votes", copied)


@dataclass(frozen=True, order=True)
class AffectedVoteVerification:
    """One registry-bound, content-addressed record-level review."""

    verifier_id: str
    affected_votes: int | None
    max_margin_shift_votes: int | None = None
    record_id: str = ""
    fact_artifact_hashes: tuple[str, ...] = ()
    reviewer_key_hash: str = ""
    margin_shift_certificate: str | None = None
    review_artifact_hash: str = ""
    schema_version: str = _REVIEW_SCHEMA

    def __post_init__(self) -> None:
        _optional_nonnegative_integer("affected_votes", self.affected_votes)
        _optional_nonnegative_integer("max_margin_shift_votes", self.max_margin_shift_votes)
        if self.affected_votes is not None and self.max_margin_shift_votes is None:
            object.__setattr__(self, "max_margin_shift_votes", 2 * self.affected_votes)
        _validate_margin_shift_bound(
            self.affected_votes,
            self.max_margin_shift_votes,
            label="verification",
        )
        if self.fact_artifact_hashes and (
            tuple(sorted(set(self.fact_artifact_hashes))) != self.fact_artifact_hashes
            or any(not _is_sha256(value) for value in self.fact_artifact_hashes)
        ):
            raise ValueError("review fact hashes must be sorted, unique SHA-256 digests")
        for value, label in (
            (self.reviewer_key_hash, "reviewer_key_hash"),
            (self.review_artifact_hash, "review_artifact_hash"),
        ):
            if value and not _is_sha256(value):
                raise ValueError(f"{label} must be a SHA-256 digest")
        if self.margin_shift_certificate is not None and not _is_sha256(
            self.margin_shift_certificate
        ):
            raise ValueError("margin_shift_certificate must be a SHA-256 digest")
        if self.schema_version != _REVIEW_SCHEMA:
            raise ValueError("review schema version is not frozen")

    def artifact_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("review_artifact_hash")
        return payload

    def with_hash(self) -> AffectedVoteVerification:
        return replace(self, review_artifact_hash=_hash(self.artifact_payload()))


@dataclass(frozen=True)
class VerifiedAffectedRecord:
    """A non-overlapping record with two trusted, agreeing reviews."""

    record_id: str
    coverage_ids: tuple[str, ...]
    scope: GeographicScope
    outcome_source: SourceFactScope
    comparison_source: SourceFactScope | None
    basis: EvidenceBasis | str
    verifications: tuple[AffectedVoteVerification, ...]
    source_links: tuple[str, ...]
    outcome_fact_artifacts: tuple[SourceFactArtifact, ...] = ()
    comparison_fact_artifacts: tuple[SourceFactArtifact, ...] = ()


@dataclass(frozen=True)
class UnresolvedRecordBound:
    """A non-overlapping unresolved record with an authenticated upper bound."""

    record_id: str
    coverage_ids: tuple[str, ...]
    scope: GeographicScope
    outcome_source: SourceFactScope
    bounded_source: SourceFactScope
    affected_vote_upper_bound: int | None
    max_margin_shift_upper_bound: int | None
    bound_basis: BoundBasis | str | None
    source_links: tuple[str, ...]
    source_observed_field: str = ""
    source_observed_value: int | None = None
    source_observed_hash: str = ""
    methodology_version: str = METHODOLOGY_VERSION
    source_fact_ids: tuple[str, ...] = ()
    margin_shift_certificate: str | None = None
    outcome_fact_artifacts: tuple[SourceFactArtifact, ...] = ()
    bounded_fact_artifacts: tuple[SourceFactArtifact, ...] = ()

    def __post_init__(self) -> None:
        _optional_nonnegative_integer("affected_vote_upper_bound", self.affected_vote_upper_bound)
        _optional_nonnegative_integer(
            "max_margin_shift_upper_bound", self.max_margin_shift_upper_bound
        )
        if self.affected_vote_upper_bound is not None and self.max_margin_shift_upper_bound is None:
            object.__setattr__(
                self,
                "max_margin_shift_upper_bound",
                2 * self.affected_vote_upper_bound,
            )
        _validate_margin_shift_bound(
            self.affected_vote_upper_bound,
            self.max_margin_shift_upper_bound,
            label="unresolved bound",
        )
        if self.margin_shift_certificate is not None and not _is_sha256(
            self.margin_shift_certificate
        ):
            raise ValueError("margin_shift_certificate must be a SHA-256 digest")


@dataclass(frozen=True, order=True)
class SensitivityIssue:
    code: str
    record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutcomeSensitivity:
    """Transparent result for release serialization or an explicit abstention."""

    status: SensitivityStatus
    evaluable: bool
    issues: tuple[SensitivityIssue, ...]
    scope: GeographicScope | None
    outcome_source: SourceFactScope | None
    leader_id: str | None
    runner_up_id: str | None
    leader_votes: int | None
    runner_up_votes: int | None
    observed_margin_votes: int | None
    verified_record_ids: tuple[str, ...] | None
    unresolved_record_ids: tuple[str, ...] | None
    verified_affected_votes: int | None
    verified_margin_shift_bound: int | None
    unresolved_affected_vote_upper_bound: int | None
    unresolved_margin_shift_upper_bound: int | None
    combined_affected_vote_upper_bound: int | None
    combined_margin_shift_upper_bound: int | None
    verified_margin_headroom: int | None
    combined_margin_headroom: int | None
    tie_possible_from_verified: bool | None
    lead_change_possible_from_verified: bool | None
    tie_possible_including_unresolved: bool | None
    lead_change_possible_including_unresolved: bool | None
    source_links: tuple[str, ...]
    evidence_hash: str | None
    output_hash: str = ""
    methodology_version: str = METHODOLOGY_VERSION
    calculation: str = (
        "Sum non-overlapping, independently agreeing authenticated record bounds; compare "
        "the observed leader-minus-runner-up margin with verified and "
        "verified-plus-unresolved maximum margin shifts. A tie requires shift >= margin; "
        "a lead change requires shift > margin."
    )
    limitations: tuple[str, ...] = (
        "This is a worst-case bound over the supplied records, not evidence that any bound "
        "was realized.",
        "Robustness applies only to trusted source facts and authenticated independent "
        "reviews supplied at compatible source and geographic grains.",
        "Statistical screening signals and historical context are excluded; this analysis "
        "does not assess fraud or intent.",
    )

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted({issue.code for issue in self.issues}))

    def artifact_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("output_hash")
        return payload

    def with_hash(self) -> OutcomeSensitivity:
        return replace(self, output_hash=_hash(self.artifact_payload()))

    def as_dict(self) -> dict[str, object]:
        """Return a release-builder-friendly, self-hashed representation."""
        return asdict(self)


def _optional_nonnegative_integer(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer or None")


def _validate_margin_shift_bound(
    affected_votes: int | None,
    margin_shift: int | None,
    *,
    label: str,
) -> None:
    if (
        affected_votes is not None
        and margin_shift is not None
        and margin_shift > 2 * affected_votes
    ):
        raise ValueError(f"{label} margin shift cannot exceed twice its affected-vote count")


def fact_set_hash(fact_artifact_hashes: Iterable[str]) -> str:
    """Bind an exact, non-duplicated set of authenticated fact artifacts."""
    values = tuple(sorted(fact_artifact_hashes))
    if not values or len(set(values)) != len(values) or any(not _is_sha256(v) for v in values):
        raise ValueError("fact set needs unique SHA-256 artifact hashes")
    return _hash({"fact_artifact_hashes": values})


def margin_shift_certificate(
    *,
    record_id: str,
    fact_artifact_hashes: Iterable[str],
    affected_votes: int,
    max_margin_shift_votes: int,
) -> str:
    """Create the deterministic certificate identity for a sub-2x bound."""
    hashes = tuple(sorted(fact_artifact_hashes))
    if not record_id or not hashes or any(not _is_sha256(value) for value in hashes):
        raise ValueError("margin certificate needs a record and authenticated fact hashes")
    _optional_nonnegative_integer("affected_votes", affected_votes)
    _optional_nonnegative_integer("max_margin_shift_votes", max_margin_shift_votes)
    _validate_margin_shift_bound(
        affected_votes,
        max_margin_shift_votes,
        label="certificate",
    )
    return _hash(
        {
            "affected_votes": affected_votes,
            "fact_artifact_hashes": hashes,
            "max_margin_shift_votes": max_margin_shift_votes,
            "record_id": record_id,
            "schema_version": _MARGIN_CERTIFICATE_SCHEMA,
        }
    )


def _issue(issues: list[SensitivityIssue], code: str, *record_ids: str) -> None:
    issues.append(SensitivityIssue(code, tuple(sorted(record_ids))))


def _grain_supports_scope(grain: str, level: str) -> bool:
    grain_rank = _LEVEL_RANK.get(grain)
    level_rank = _LEVEL_RANK.get(level)
    return grain_rank is not None and level_rank is not None and grain_rank <= level_rank


def _within(child: GeographicScope, parent: GeographicScope) -> bool:
    if _LEVEL_RANK[child.level] > _LEVEL_RANK[parent.level]:
        return False
    if parent.level == "national":
        return True
    return child.key[: len(parent.key)] == parent.key


def _source_issues(
    issues: list[SensitivityIssue],
    source: SourceFactScope,
    scope: GeographicScope,
    *,
    missing_code: str,
    grain_code: str,
    record_id: str | None = None,
) -> None:
    identifiers = () if record_id is None else (record_id,)
    if not source.source_id.strip():
        _issue(issues, missing_code, *identifiers)
    if source.source_type == "contextual_baseline" or source.legal_status == "context_only":
        _issue(issues, "contextual_source_ineligible", *identifiers)
    if not _grain_supports_scope(source.fact_grain, scope.level):
        _issue(issues, grain_code, *identifiers)


def _links(links: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({link for link in links if _https_url(link)}))


def _top_two(
    observation: OutcomeObservation | None,
) -> tuple[str | None, str | None, int | None, int | None, int | None]:
    if observation is None or observation.candidate_votes is None:
        return None, None, None, None, None
    ordered = sorted(observation.candidate_votes.items(), key=lambda item: (-item[1], item[0]))
    if len(ordered) < 2:
        return None, None, None, None, None
    leader, runner_up = ordered[:2]
    return leader[0], runner_up[0], leader[1], runner_up[1], leader[1] - runner_up[1]


def _canonical_coverage_ids(
    *,
    release_id: str,
    election_slug: str,
    source_id: str,
    fact_ids: Iterable[str],
) -> frozenset[str]:
    values = tuple(sorted(fact_ids))
    if (
        not values
        or len(set(values)) != len(values)
        or any(not isinstance(value, str) or not value.strip() for value in values)
    ):
        return frozenset()
    return frozenset(
        _hash(
            {
                "election_slug": election_slug,
                "fact_id": fact_id,
                "release_id": release_id,
                "source_id": source_id,
            }
        )
        for fact_id in values
    )


def _coverage_complete(value: SourceFactArtifact | OutcomeObservation) -> bool:
    return (
        type(getattr(value, "expected", None)) is int
        and value.expected > 0
        and getattr(value, "retrieved", None) == value.expected
        and getattr(value, "parsed", None) == value.expected
        and getattr(value, "missing", None) == 0
        and getattr(value, "ambiguous", None) == 0
        and getattr(value, "excluded", None) == 0
    )


def _fact_atoms(facts: Iterable[SourceFactArtifact]) -> frozenset[str]:
    """Canonical coverage atoms; caller-facing fact IDs are never sufficient."""
    atoms: set[str] = set()
    for fact in facts:
        if not fact.ballot_universe:
            continue
        for fact_id in fact.fact_ids:
            for field in fact.values:
                atoms.add(
                    _hash(
                        {
                            "ballot_universe": fact.ballot_universe,
                            "election_slug": fact.election_slug,
                            "fact_grain": fact.source.fact_grain,
                            "fact_id": fact_id,
                            "field": field,
                            "release_id": fact.release_id,
                            "source_id": fact.source.source_id,
                        }
                    )
                )
    return frozenset(atoms)


def _scopes_intersect(left: GeographicScope, right: GeographicScope) -> bool:
    return _within(left, right) or _within(right, left)


def _record_overlap_issues(
    issues: list[SensitivityIssue],
    records: tuple[tuple[str, GeographicScope, frozenset[str]], ...],
) -> None:
    for index, (left_id, left_scope, left_atoms) in enumerate(records):
        for right_id, right_scope, right_atoms in records[index + 1 :]:
            # This schema has no independently authenticated disjoint-ballot
            # certificate. Distinct caller fact IDs/fields cannot prove it.
            if (
                left_id == right_id
                or left_atoms & right_atoms
                or _scopes_intersect(left_scope, right_scope)
            ):
                _issue(issues, "overlapping_record_coverage", left_id, right_id)


def _all_fact_artifacts(
    observation: OutcomeObservation | None,
    verified: tuple[VerifiedAffectedRecord, ...] | None,
    unresolved: tuple[UnresolvedRecordBound, ...] | None,
) -> tuple[SourceFactArtifact, ...]:
    facts: list[SourceFactArtifact] = []
    if observation is not None:
        facts.extend(observation.fact_artifacts)
    if verified is not None:
        for verified_record in verified:
            facts.extend(verified_record.outcome_fact_artifacts)
            facts.extend(verified_record.comparison_fact_artifacts)
    if unresolved is not None:
        for unresolved_record in unresolved:
            facts.extend(unresolved_record.outcome_fact_artifacts)
            facts.extend(unresolved_record.bounded_fact_artifacts)
    unique = {fact.artifact_hash: fact for fact in facts}
    return tuple(unique[key] for key in sorted(unique))


def _validate_fact_authentication(
    issues: list[SensitivityIssue],
    facts: tuple[SourceFactArtifact, ...],
    trusted_fact_hashes: Iterable[str] | None,
) -> frozenset[str]:
    trusted: frozenset[str]
    if trusted_fact_hashes is None:
        _issue(issues, "source_fact_trust_registry_missing")
        trusted = frozenset()
    else:
        raw_trusted = tuple(trusted_fact_hashes)
        if len(set(raw_trusted)) != len(raw_trusted) or any(
            not _is_sha256(value) for value in raw_trusted
        ):
            _issue(issues, "source_fact_trust_registry_invalid")
            trusted = frozenset()
        else:
            trusted = frozenset(raw_trusted)
    for fact in facts:
        expected_hash = _hash(fact.artifact_payload())
        if fact.artifact_hash != expected_hash:
            _issue(issues, "source_fact_artifact_hash_invalid")
        if fact.artifact_hash not in trusted:
            _issue(issues, "source_fact_artifact_untrusted")
        if not _coverage_complete(fact):
            _issue(issues, "source_fact_coverage_incomplete_or_ambiguous")
        if not fact.ballot_universe:
            _issue(issues, "source_fact_ballot_universe_missing")
    return trusted


def _fact_group_issues(
    issues: list[SensitivityIssue],
    *,
    facts: tuple[SourceFactArtifact, ...],
    coverage_ids: tuple[str, ...],
    release_id: str,
    election_slug: str,
    source: SourceFactScope,
    scope: GeographicScope,
    code: str,
    record_id: str | None = None,
) -> None:
    identifiers = () if record_id is None else (record_id,)
    if not facts:
        _issue(issues, code, *identifiers)
        return
    fact_ids = tuple(sorted({fact_id for fact in facts for fact_id in fact.fact_ids}))
    if (
        tuple(sorted(coverage_ids)) != fact_ids
        or len(set(coverage_ids)) != len(coverage_ids)
        or any(
            fact.release_id != release_id
            or fact.election_slug != election_slug
            or fact.source != source
            or not _within(fact.scope, scope)
            or not _grain_supports_scope(fact.source.fact_grain, fact.scope.level)
            for fact in facts
        )
    ):
        _issue(issues, code, *identifiers)
    if any(not _coverage_complete(fact) for fact in facts):
        _issue(issues, code, *identifiers)
    if (
        len(facts) > 1
        or any(fact.scope != scope or fact.expected > 1 for fact in facts)
        or any(_LEVEL_RANK[fact.source.fact_grain] < _LEVEL_RANK[scope.level] for fact in facts)
    ) and any(not fact.exact_rollup for fact in facts):
        _issue(issues, "exact_rollup_unauthenticated", *identifiers)


def _facts_support_smaller_bound(
    facts: Iterable[SourceFactArtifact], *, affected_votes: int, margin_shift: int
) -> bool:
    return any(
        fact.values.get("affected_votes") == affected_votes
        and fact.values.get("max_margin_shift_votes") == margin_shift
        for fact in facts
    )


def _review_valid(
    review: AffectedVoteVerification,
    *,
    record_id: str,
    fact_hashes: tuple[str, ...],
    reviewer_registry: Mapping[str, str],
    trusted_review_hashes: frozenset[str],
    facts: tuple[SourceFactArtifact, ...],
) -> bool:
    if (
        not review.verifier_id
        or review.record_id != record_id
        or review.fact_artifact_hashes != fact_hashes
        or reviewer_registry.get(review.verifier_id) != review.reviewer_key_hash
        or review.review_artifact_hash not in trusted_review_hashes
        or review.review_artifact_hash != _hash(review.artifact_payload())
    ):
        return False
    affected = review.affected_votes
    shift = review.max_margin_shift_votes
    if affected is None or shift is None:
        return True
    if shift == 2 * affected:
        return review.margin_shift_certificate is None
    expected_certificate = margin_shift_certificate(
        record_id=record_id,
        fact_artifact_hashes=fact_hashes,
        affected_votes=affected,
        max_margin_shift_votes=shift,
    )
    return review.margin_shift_certificate == expected_certificate and _facts_support_smaller_bound(
        facts,
        affected_votes=affected,
        margin_shift=shift,
    )


def _not_evaluable(
    observation: OutcomeObservation | None,
    issues: list[SensitivityIssue],
    verified: tuple[VerifiedAffectedRecord, ...] | None,
    unresolved: tuple[UnresolvedRecordBound, ...] | None,
    links: tuple[str, ...],
) -> OutcomeSensitivity:
    leader, runner_up, leader_votes, runner_up_votes, margin = _top_two(observation)
    return OutcomeSensitivity(
        status=SensitivityStatus.NOT_EVALUABLE,
        evaluable=False,
        issues=tuple(sorted(set(issues))),
        scope=observation.scope if observation is not None else None,
        outcome_source=observation.source if observation is not None else None,
        leader_id=leader,
        runner_up_id=runner_up,
        leader_votes=leader_votes,
        runner_up_votes=runner_up_votes,
        observed_margin_votes=margin,
        verified_record_ids=(
            None if verified is None else tuple(sorted(item.record_id for item in verified))
        ),
        unresolved_record_ids=(
            None if unresolved is None else tuple(sorted(item.record_id for item in unresolved))
        ),
        verified_affected_votes=None,
        verified_margin_shift_bound=None,
        unresolved_affected_vote_upper_bound=None,
        unresolved_margin_shift_upper_bound=None,
        combined_affected_vote_upper_bound=None,
        combined_margin_shift_upper_bound=None,
        verified_margin_headroom=None,
        combined_margin_headroom=None,
        tie_possible_from_verified=None,
        lead_change_possible_from_verified=None,
        tie_possible_including_unresolved=None,
        lead_change_possible_including_unresolved=None,
        source_links=links,
        evidence_hash=None,
    ).with_hash()


def analyze_outcome_sensitivity(
    observation: OutcomeObservation | None,
    *,
    verified_affected_records: Iterable[VerifiedAffectedRecord] | None,
    unresolved_record_bounds: Iterable[UnresolvedRecordBound] | None,
    trusted_fact_hashes: Iterable[str] | None = None,
    reviewer_registry: Mapping[str, str] | None = None,
    trusted_review_hashes: Iterable[str] | None = None,
) -> OutcomeSensitivity:
    """Compare a top-two margin with authenticated, non-overlapping bounds.

    ``None`` means a layer was not assessed.  An empty iterable means the layer
    was assessed and contains zero records.  Missing trust registries,
    incompatible facts, unbound reviews, overlap, or incomplete values make the
    whole calculation non-evaluable rather than being silently discarded.
    """
    verified = None if verified_affected_records is None else tuple(verified_affected_records)
    unresolved = None if unresolved_record_bounds is None else tuple(unresolved_record_bounds)
    issues: list[SensitivityIssue] = []
    all_links: list[str] = []
    all_facts = _all_fact_artifacts(observation, verified, unresolved)
    trusted = _validate_fact_authentication(issues, all_facts, trusted_fact_hashes)
    if reviewer_registry is None:
        reviewers: Mapping[str, str] = {}
        if verified:
            _issue(issues, "reviewer_registry_missing")
    elif any(
        not isinstance(key, str) or not key.strip() or not _is_sha256(value)
        for key, value in reviewer_registry.items()
    ) or len(set(reviewer_registry.values())) != len(reviewer_registry):
        reviewers = {}
        _issue(issues, "reviewer_registry_invalid")
    else:
        reviewers = reviewer_registry
    trusted_reviews: frozenset[str]
    if verified:
        if trusted_review_hashes is None:
            trusted_reviews = frozenset()
            _issue(issues, "review_trust_registry_missing")
        else:
            raw_trusted_reviews = tuple(trusted_review_hashes)
            if len(set(raw_trusted_reviews)) != len(raw_trusted_reviews) or any(
                not _is_sha256(value) for value in raw_trusted_reviews
            ):
                trusted_reviews = frozenset()
                _issue(issues, "review_trust_registry_invalid")
            else:
                trusted_reviews = frozenset(raw_trusted_reviews)
    else:
        trusted_reviews = frozenset()

    if observation is None:
        _issue(issues, "observation_missing")
    else:
        all_links.extend(observation.source_links)
        if observation.election_slug not in _ALLOWED_ELECTIONS:
            _issue(issues, "election_round_not_allowlisted")
        if observation.scope.level not in _ANALYSIS_LEVELS:
            _issue(issues, "unsupported_analysis_level")
        _source_issues(
            issues,
            observation.source,
            observation.scope,
            missing_code="outcome_source_missing",
            grain_code="outcome_source_grain_incompatible",
        )
        if observation.candidate_votes is None:
            _issue(issues, "candidate_votes_missing")
        elif len(observation.candidate_votes) < 2:
            _issue(issues, "fewer_than_two_candidates")
        else:
            ordered_votes = sorted(observation.candidate_votes.values(), reverse=True)
            if ordered_votes[0] == ordered_votes[1]:
                _issue(issues, "observed_result_has_no_unique_leader")
        if not _links(observation.source_links) or _links(observation.source_links) != tuple(
            sorted(set(observation.source_links))
        ):
            _issue(issues, "outcome_source_links_missing")
        if not _coverage_complete(observation):
            _issue(issues, "outcome_coverage_incomplete_or_ambiguous")
        _fact_group_issues(
            issues,
            facts=observation.fact_artifacts,
            coverage_ids=observation.source_fact_ids,
            release_id=observation.release_id,
            election_slug=observation.election_slug,
            source=observation.source,
            scope=observation.scope,
            code="outcome_fact_authentication_invalid",
        )
        if observation.fact_artifacts:
            aggregate_values: dict[str, int] = {}
            for fact in observation.fact_artifacts:
                for field, value in fact.values.items():
                    aggregate_values[field] = aggregate_values.get(field, 0) + value
            coverage = tuple(
                sum(getattr(fact, field) for fact in observation.fact_artifacts)
                for field in (
                    "expected",
                    "retrieved",
                    "parsed",
                    "missing",
                    "ambiguous",
                    "excluded",
                )
            )
            if aggregate_values != observation.candidate_votes:
                _issue(issues, "outcome_fact_values_mismatch")
            if coverage != (
                observation.expected,
                observation.retrieved,
                observation.parsed,
                observation.missing,
                observation.ambiguous,
                observation.excluded,
            ):
                _issue(issues, "outcome_fact_coverage_mismatch")
            if any(not fact.exact_rollup for fact in observation.fact_artifacts):
                _issue(issues, "outcome_exact_rollup_unauthenticated")
            fact_links = _links(
                link for fact in observation.fact_artifacts for link in fact.source_links
            )
            if fact_links != _links(observation.source_links):
                _issue(issues, "outcome_fact_links_mismatch")
    if verified is None:
        _issue(issues, "verified_affected_records_unassessed")
    if unresolved is None:
        _issue(issues, "unresolved_records_unassessed")
    if verified is not None and unresolved is not None and not verified and not unresolved:
        _issue(issues, "outcome_assessment_empty")

    verified_totals: list[tuple[int, int]] = []
    if verified is not None and observation is not None:
        for record in verified:
            all_links.extend(record.source_links)
            if not record.record_id.strip():
                _issue(issues, "affected_record_id_missing")
            canonical = _canonical_coverage_ids(
                release_id=observation.release_id,
                election_slug=observation.election_slug,
                source_id=record.outcome_source.source_id,
                fact_ids=record.coverage_ids,
            )
            if not canonical:
                _issue(issues, "affected_record_coverage_ids_invalid", record.record_id)
            if not _within(record.scope, observation.scope):
                _issue(issues, "affected_record_outside_geography", record.record_id)
            if record.outcome_source != observation.source:
                _issue(issues, "affected_record_outcome_source_mismatch", record.record_id)
            _source_issues(
                issues,
                record.outcome_source,
                record.scope,
                missing_code="affected_record_source_missing",
                grain_code="affected_record_source_grain_incompatible",
                record_id=record.record_id,
            )
            _fact_group_issues(
                issues,
                facts=record.outcome_fact_artifacts,
                coverage_ids=record.coverage_ids,
                release_id=observation.release_id,
                election_slug=observation.election_slug,
                source=record.outcome_source,
                scope=record.scope,
                code="affected_record_outcome_facts_invalid",
                record_id=record.record_id,
            )
            if record.comparison_source is not None:
                _source_issues(
                    issues,
                    record.comparison_source,
                    record.scope,
                    missing_code="affected_record_comparison_source_missing",
                    grain_code="affected_record_source_grain_incompatible",
                    record_id=record.record_id,
                )
            if record.basis in {
                EvidenceBasis.STATISTICAL_SIGNAL,
                EvidenceBasis.HISTORICAL_CONTEXT,
            }:
                _issue(
                    issues,
                    "affected_record_basis_is_not_verified_evidence",
                    record.record_id,
                )
            elif record.basis not in {
                EvidenceBasis.DOCUMENTARY_COMPARISON,
                EvidenceBasis.SOURCE_ACCOUNTING,
            }:
                _issue(issues, "affected_record_basis_unknown", record.record_id)
            if record.basis == EvidenceBasis.DOCUMENTARY_COMPARISON:
                if record.comparison_source is None:
                    _issue(issues, "documentary_comparison_source_missing", record.record_id)
                elif record.comparison_source.source_id == record.outcome_source.source_id:
                    _issue(
                        issues,
                        "documentary_comparison_sources_not_distinct",
                        record.record_id,
                    )
                else:
                    _fact_group_issues(
                        issues,
                        facts=record.comparison_fact_artifacts,
                        coverage_ids=record.coverage_ids,
                        release_id=observation.release_id,
                        election_slug=observation.election_slug,
                        source=record.comparison_source,
                        scope=record.scope,
                        code="affected_record_comparison_facts_invalid",
                        record_id=record.record_id,
                    )
            elif (
                record.basis == EvidenceBasis.SOURCE_ACCOUNTING and record.comparison_fact_artifacts
            ):
                _issue(issues, "source_accounting_comparison_facts_unexpected", record.record_id)
            facts = (*record.outcome_fact_artifacts, *record.comparison_fact_artifacts)
            fact_hashes = tuple(sorted(fact.artifact_hash for fact in facts))
            fact_links = _links(link for fact in facts for link in fact.source_links)
            if not _links(record.source_links) or not set(_links(record.source_links)) <= set(
                fact_links
            ):
                _issue(issues, "affected_record_source_links_missing", record.record_id)
            verifier_ids = [review.verifier_id for review in record.verifications]
            verifier_keys = [review.reviewer_key_hash for review in record.verifications]
            if (
                len(verifier_ids) < 2
                or any(not value.strip() for value in verifier_ids)
                or len(set(verifier_ids)) != len(verifier_ids)
                or len(set(verifier_keys)) != len(verifier_keys)
            ):
                _issue(
                    issues,
                    "affected_record_not_independently_verified",
                    record.record_id,
                )
            if any(
                not _review_valid(
                    review,
                    record_id=record.record_id,
                    fact_hashes=fact_hashes,
                    reviewer_registry=reviewers,
                    trusted_review_hashes=trusted_reviews,
                    facts=facts,
                )
                for review in record.verifications
            ):
                _issue(issues, "affected_record_review_authentication_invalid", record.record_id)
            pairs = {
                (review.affected_votes, review.max_margin_shift_votes)
                for review in record.verifications
            }
            if any(value is None for pair in pairs for value in pair):
                _issue(
                    issues,
                    "affected_record_verification_value_missing",
                    record.record_id,
                )
            elif len(pairs) > 1:
                _issue(
                    issues,
                    "affected_record_verification_disagreement",
                    record.record_id,
                )
            elif pairs:
                affected, shift = next(iter(pairs))
                assert affected is not None and shift is not None
                verified_totals.append((affected, shift))

    unresolved_totals: list[tuple[int, int]] = []
    if unresolved is not None and observation is not None:
        for unresolved_record in unresolved:
            all_links.extend(unresolved_record.source_links)
            if not unresolved_record.record_id.strip():
                _issue(issues, "unresolved_record_id_missing")
            canonical = _canonical_coverage_ids(
                release_id=observation.release_id,
                election_slug=observation.election_slug,
                source_id=unresolved_record.outcome_source.source_id,
                fact_ids=unresolved_record.coverage_ids,
            )
            if not canonical:
                _issue(
                    issues,
                    "unresolved_record_coverage_ids_invalid",
                    unresolved_record.record_id,
                )
            if tuple(sorted(unresolved_record.coverage_ids)) != tuple(
                sorted(unresolved_record.source_fact_ids)
            ):
                _issue(
                    issues,
                    "unresolved_record_fact_coverage_mismatch",
                    unresolved_record.record_id,
                )
            if not _within(unresolved_record.scope, observation.scope):
                _issue(
                    issues,
                    "unresolved_record_outside_geography",
                    unresolved_record.record_id,
                )
            if unresolved_record.outcome_source != observation.source:
                _issue(
                    issues,
                    "unresolved_record_outcome_source_mismatch",
                    unresolved_record.record_id,
                )
            for source in (
                unresolved_record.outcome_source,
                unresolved_record.bounded_source,
            ):
                _source_issues(
                    issues,
                    source,
                    unresolved_record.scope,
                    missing_code="unresolved_record_source_missing",
                    grain_code="unresolved_record_source_grain_incompatible",
                    record_id=unresolved_record.record_id,
                )
            _fact_group_issues(
                issues,
                facts=unresolved_record.outcome_fact_artifacts,
                coverage_ids=unresolved_record.coverage_ids,
                release_id=observation.release_id,
                election_slug=observation.election_slug,
                source=unresolved_record.outcome_source,
                scope=unresolved_record.scope,
                code="unresolved_record_outcome_facts_invalid",
                record_id=unresolved_record.record_id,
            )
            _fact_group_issues(
                issues,
                facts=unresolved_record.bounded_fact_artifacts,
                coverage_ids=unresolved_record.source_fact_ids,
                release_id=observation.release_id,
                election_slug=observation.election_slug,
                source=unresolved_record.bounded_source,
                scope=unresolved_record.scope,
                code="unresolved_record_bounded_facts_invalid",
                record_id=unresolved_record.record_id,
            )
            if (
                unresolved_record.affected_vote_upper_bound is not None
                and unresolved_record.affected_vote_upper_bound <= 0
            ):
                _issue(
                    issues,
                    "unresolved_record_bound_not_positive",
                    unresolved_record.record_id,
                )
            if (
                unresolved_record.bound_basis == BoundBasis.REGISTERED_ELECTORS
                and unresolved_record.affected_vote_upper_bound == 0
            ):
                _issue(
                    issues,
                    "unresolved_registered_elector_bound_not_positive",
                    unresolved_record.record_id,
                )
            bounded_hashes = tuple(
                sorted(fact.artifact_hash for fact in unresolved_record.bounded_fact_artifacts)
            )
            observed_bound = any(
                fact.values.get(unresolved_record.source_observed_field)
                == unresolved_record.source_observed_value
                for fact in unresolved_record.bounded_fact_artifacts
            )
            try:
                expected_source_hash = fact_set_hash(bounded_hashes)
            except ValueError:
                expected_source_hash = ""
            if (
                not unresolved_record.source_observed_field
                or type(unresolved_record.source_observed_value) is not int
                or unresolved_record.source_observed_value <= 0
                or unresolved_record.source_observed_value
                != unresolved_record.affected_vote_upper_bound
                or unresolved_record.source_observed_hash != expected_source_hash
                or not observed_bound
                or unresolved_record.methodology_version != METHODOLOGY_VERSION
            ):
                _issue(
                    issues,
                    "unresolved_record_basis_provenance_invalid",
                    unresolved_record.record_id,
                )
            affected = unresolved_record.affected_vote_upper_bound
            shift = unresolved_record.max_margin_shift_upper_bound
            if affected is None or shift is None:
                _issue(
                    issues,
                    "unresolved_record_bound_missing",
                    unresolved_record.record_id,
                )
            else:
                if shift < 2 * affected:
                    expected_certificate = margin_shift_certificate(
                        record_id=unresolved_record.record_id,
                        fact_artifact_hashes=bounded_hashes,
                        affected_votes=affected,
                        max_margin_shift_votes=shift,
                    )
                    if (
                        unresolved_record.margin_shift_certificate != expected_certificate
                        or not _facts_support_smaller_bound(
                            unresolved_record.bounded_fact_artifacts,
                            affected_votes=affected,
                            margin_shift=shift,
                        )
                    ):
                        _issue(
                            issues,
                            "unresolved_margin_shift_certificate_invalid",
                            unresolved_record.record_id,
                        )
                elif unresolved_record.margin_shift_certificate is not None:
                    _issue(
                        issues,
                        "unresolved_margin_shift_certificate_unnecessary",
                        unresolved_record.record_id,
                    )
                unresolved_totals.append((affected, shift))
            if unresolved_record.bound_basis is None:
                _issue(
                    issues,
                    "unresolved_record_bound_basis_missing",
                    unresolved_record.record_id,
                )
            elif unresolved_record.bound_basis == BoundBasis.STATISTICAL_ESTIMATE:
                _issue(
                    issues,
                    "unresolved_record_statistical_bound",
                    unresolved_record.record_id,
                )
            elif unresolved_record.bound_basis not in {
                BoundBasis.REGISTERED_ELECTORS,
                BoundBasis.REPORTED_BALLOTS,
                BoundBasis.DOCUMENTED_RECORD_LIMIT,
            }:
                _issue(
                    issues,
                    "unresolved_record_bound_basis_unknown",
                    unresolved_record.record_id,
                )
            facts = (
                *unresolved_record.outcome_fact_artifacts,
                *unresolved_record.bounded_fact_artifacts,
            )
            fact_links = _links(link for fact in facts for link in fact.source_links)
            if not _links(unresolved_record.source_links) or not set(
                _links(unresolved_record.source_links)
            ) <= set(fact_links):
                _issue(
                    issues,
                    "unresolved_record_source_links_missing",
                    unresolved_record.record_id,
                )

    records: list[tuple[str, GeographicScope, frozenset[str]]] = []
    if verified is not None and observation is not None:
        records.extend(
            (
                record.record_id,
                record.scope,
                _fact_atoms((*record.outcome_fact_artifacts, *record.comparison_fact_artifacts)),
            )
            for record in verified
        )
    if unresolved is not None and observation is not None:
        records.extend(
            (
                record.record_id,
                record.scope,
                _fact_atoms((*record.outcome_fact_artifacts, *record.bounded_fact_artifacts)),
            )
            for record in unresolved
        )
    ids = [record_id for record_id, _scope, _atoms in records]
    for record_id in sorted({record_id for record_id in ids if ids.count(record_id) > 1}):
        _issue(issues, "duplicate_record_id", record_id)
    _record_overlap_issues(
        issues,
        tuple(sorted(records, key=lambda item: (item[0], item[1], tuple(sorted(item[2]))))),
    )

    normalized_links = _links(all_links)
    if issues or observation is None or verified is None or unresolved is None:
        return _not_evaluable(observation, issues, verified, unresolved, normalized_links)

    leader, runner_up, leader_votes, runner_up_votes, margin = _top_two(observation)
    assert leader is not None and runner_up is not None
    assert leader_votes is not None and runner_up_votes is not None and margin is not None
    verified_affected = sum(item[0] for item in verified_totals)
    verified_shift = sum(item[1] for item in verified_totals)
    unresolved_affected = sum(item[0] for item in unresolved_totals)
    unresolved_shift = sum(item[1] for item in unresolved_totals)
    combined_affected = verified_affected + unresolved_affected
    combined_shift = verified_shift + unresolved_shift
    tie_verified = verified_shift >= margin
    change_verified = verified_shift > margin
    tie_combined = combined_shift >= margin
    change_combined = combined_shift > margin
    if change_verified:
        status = SensitivityStatus.LEAD_CHANGE_WITHIN_VERIFIED_BOUND
    elif change_combined:
        status = SensitivityStatus.LEAD_CHANGE_ONLY_WITH_UNRESOLVED_BOUND
    elif tie_verified:
        status = SensitivityStatus.TIE_WITHIN_VERIFIED_BOUND
    elif tie_combined:
        status = SensitivityStatus.TIE_ONLY_WITH_UNRESOLVED_BOUND
    else:
        status = SensitivityStatus.ROBUST_WITHIN_EVALUATED_BOUNDS
    evidence_hash = _hash(
        {
            "methodology_version": METHODOLOGY_VERSION,
            "observation": asdict(observation),
            "reviewer_registry": dict(sorted(reviewers.items())),
            "trusted_fact_hashes": sorted(trusted),
            "trusted_review_hashes": sorted(trusted_reviews),
            "unresolved_records": [
                asdict(record) for record in sorted(unresolved, key=lambda item: item.record_id)
            ],
            "verified_records": [
                asdict(record) for record in sorted(verified, key=lambda item: item.record_id)
            ],
        }
    )
    return OutcomeSensitivity(
        status=status,
        evaluable=True,
        issues=(),
        scope=observation.scope,
        outcome_source=observation.source,
        leader_id=leader,
        runner_up_id=runner_up,
        leader_votes=leader_votes,
        runner_up_votes=runner_up_votes,
        observed_margin_votes=margin,
        verified_record_ids=tuple(sorted(record.record_id for record in verified)),
        unresolved_record_ids=tuple(sorted(record.record_id for record in unresolved)),
        verified_affected_votes=verified_affected,
        verified_margin_shift_bound=verified_shift,
        unresolved_affected_vote_upper_bound=unresolved_affected,
        unresolved_margin_shift_upper_bound=unresolved_shift,
        combined_affected_vote_upper_bound=combined_affected,
        combined_margin_shift_upper_bound=combined_shift,
        verified_margin_headroom=margin - verified_shift,
        combined_margin_headroom=margin - combined_shift,
        tie_possible_from_verified=tie_verified,
        lead_change_possible_from_verified=change_verified,
        tie_possible_including_unresolved=tie_combined,
        lead_change_possible_including_unresolved=change_combined,
        source_links=normalized_links,
        evidence_hash=evidence_hash,
    ).with_hash()
