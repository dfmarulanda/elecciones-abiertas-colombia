from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from .peer_signals import MesaMetrics, Metric, cohort_digest, family_digest

_METRIC_STATUSES = frozenset({"observed", "unknown", "unavailable", "not_applicable"})
_HASH_CHARS = frozenset("0123456789abcdef")
_ARTIFACT_KIND = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HASH_CHARS


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _tree_hash(root: Path) -> str:
    files = sorted(path for path in root.rglob("*.py") if path.is_file())
    if not files:
        raise ValueError("detector source directory contains no Python files")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(value: object, *, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be an array")
    return value


class AnalysisExposureTier(StrEnum):
    INTERNAL = "internal"
    PRELIMINARY_RESEARCH = "preliminary_research"
    CERTIFIED_PUBLIC = "certified_public"


@dataclass(frozen=True)
class CanonicalMetricValue:
    value: int | None
    status: str

    def __post_init__(self) -> None:
        if self.status not in _METRIC_STATUSES:
            raise ValueError("metric status is invalid")
        if (self.status == "observed") != (self.value is not None):
            raise ValueError("only observed metrics may contain a value")
        if self.value is not None and (type(self.value) is not int or self.value < 0):
            raise ValueError("metric values must be nonnegative integers")


@dataclass(frozen=True)
class CanonicalAnalysisRow:
    mesa_id: str
    polling_place_id: str
    municipality_id: str
    department_id: str
    metric: str
    candidate_id: str | None
    numerator: CanonicalMetricValue
    denominator: CanonicalMetricValue
    complete_ballot_vector: bool
    source_type: str
    legal_status: str
    source_url: str
    source_hash: str


@dataclass(frozen=True)
class _CanonicalRowContext:
    mesa_id: str
    polling_place_id: str
    municipality_id: str
    department_id: str
    complete_ballot_vector: bool
    source_type: str
    legal_status: str
    source_url: str
    source_hash: str


def _analysis_row(
    context: _CanonicalRowContext,
    metric: str,
    candidate_id: str | None,
    numerator: CanonicalMetricValue,
    denominator: CanonicalMetricValue,
) -> CanonicalAnalysisRow:
    return CanonicalAnalysisRow(
        mesa_id=context.mesa_id,
        polling_place_id=context.polling_place_id,
        municipality_id=context.municipality_id,
        department_id=context.department_id,
        metric=metric,
        candidate_id=candidate_id,
        numerator=numerator,
        denominator=denominator,
        complete_ballot_vector=context.complete_ballot_vector,
        source_type=context.source_type,
        legal_status=context.legal_status,
        source_url=context.source_url,
        source_hash=context.source_hash,
    )


@dataclass(frozen=True)
class DocumentaryAttestation:
    claim_id: str
    official_document_url: str
    source_identifier: str
    expected_document_type: str
    reviewer_ids: tuple[str, str]
    reviewer_signatures: tuple[str, str]
    structured_fields_hash: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.official_document_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("documentary evidence requires an official HTTPS link")
        if len(set(self.reviewer_ids)) != 2 or any(not item for item in self.reviewer_ids):
            raise ValueError("documentary claims require two distinct identified reviewers")
        if any(not item for item in self.reviewer_signatures):
            raise ValueError("both documentary reviewers must sign the structured claim")
        if not _is_sha256(self.structured_fields_hash):
            raise ValueError("structured documentary fields require a SHA-256 hash")


@dataclass(frozen=True)
class GeocodeLedger:
    source_url: str
    source_byte_hash: str
    retrieval_metadata_hash: str
    crosswalk_hash: str
    matched_place_ids: tuple[str, ...]
    expected_place_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("geocodes require an authenticated HTTPS source")
        for value in (
            self.source_byte_hash,
            self.retrieval_metadata_hash,
            self.crosswalk_hash,
        ):
            if not _is_sha256(value):
                raise ValueError("geocode provenance requires SHA-256 hashes")
        if len(set(self.matched_place_ids)) != len(self.matched_place_ids):
            raise ValueError("geocode matches must be one-to-one")
        if tuple(sorted(self.matched_place_ids)) != tuple(sorted(self.expected_place_ids)):
            raise ValueError("geocode matching must fail closed on missing or ambiguous places")


@dataclass(frozen=True)
class CanonicalInputRegistry:
    source_release_id: str
    election_slug: str
    source_manifest_hash: str
    detector_code_hash: str
    configuration_hash: str
    seed_registry_hash: str
    runtime_fingerprint: str
    documentary_attestations: tuple[DocumentaryAttestation, ...]
    geocode_ledger: GeocodeLedger | None
    snapshot: Mapping[str, object] = field(repr=False, compare=False)
    historical_context_hashes: tuple[str, ...] = ()
    historical_context_artifacts: tuple[Mapping[str, object], ...] = field(
        default=(), repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for value in (
            self.source_manifest_hash,
            self.detector_code_hash,
            self.configuration_hash,
            self.seed_registry_hash,
            self.runtime_fingerprint,
            *self.historical_context_hashes,
        ):
            if not _is_sha256(value):
                raise ValueError("canonical input registry hashes must be SHA-256")
        release = _mapping(self.snapshot.get("release"), name="snapshot.release")
        election = _mapping(self.snapshot.get("election"), name="snapshot.election")
        if release.get("release_id") != self.source_release_id:
            raise ValueError("snapshot source release does not match the canonical registry")
        if election.get("slug") != self.election_slug:
            raise ValueError("snapshot election does not match the canonical registry")


@dataclass(frozen=True)
class EligibilityDecision:
    status: str
    eligible_units: int
    total_units: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PeerFamilyInput:
    metric: Metric
    candidate_id: str | None
    mesas: tuple[MesaMetrics, ...]
    excluded_units: tuple[tuple[str, str], ...]
    family_digest: str
    cohort_digest: str


@dataclass(frozen=True)
class AnalysisArtifact:
    artifact_id: str
    kind: str
    schema_version: str
    media_type: str
    record_count: int
    byte_size: int
    byte_hash: str
    content_hash: str
    status: str
    status_reason: str | None
    content: bytes = field(repr=False)

    def manifest_record(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "schema_version": self.schema_version,
            "media_type": self.media_type,
            "record_count": self.record_count,
            "byte_size": self.byte_size,
            "byte_hash": self.byte_hash,
            "content_hash": self.content_hash,
            "status": self.status,
            "status_reason": self.status_reason,
            "immutable_url": (
                f"/api/v1/analysis/artifacts/{self.artifact_id}/download"
                if self.status == "available"
                else None
            ),
            "filename": f"artifacts/{self.kind}.json",
        }


@dataclass(frozen=True)
class AnalysisBundle:
    analysis_release_id: str
    source_release_id: str
    election_slug: str
    methodology_version: str
    canonical_input_hash: str
    producer_runtime_fingerprint: str
    exposure_tier: AnalysisExposureTier
    generated_at: datetime
    eligibility: Mapping[str, EligibilityDecision]
    descriptive: Mapping[str, object]
    artifacts: tuple[AnalysisArtifact, ...]
    manifest: Mapping[str, object]
    manifest_hash: str


@dataclass(frozen=True)
class PassBPacket:
    analysis_release_id: str
    source_release_id: str
    election_slug: str
    methodology_version: str
    canonical_input_hash: str
    manifest_hash: str
    detector_code_hash: str
    producer_runtime_fingerprint: str
    replay_runtime_fingerprint: str
    producer_operator_id: str
    replay_operator_id: str
    reviewer_id: str
    reviewer_key_id: str
    reviewer_signature: str
    decision: str
    reviewed_at: datetime

    def signed_payload(self) -> bytes:
        payload = asdict(self)
        payload.pop("reviewer_signature")
        payload["reviewed_at"] = self.reviewed_at.isoformat()
        return _canonical_json(payload)


def _metric(value: object, *, name: str) -> CanonicalMetricValue:
    item = _mapping(value, name=name)
    metric_value = item.get("value")
    status = item.get("status")
    if not isinstance(status, str):
        raise ValueError(f"{name}.status must be a string")
    if metric_value is not None and type(metric_value) is not int:
        raise ValueError(f"{name}.value must be an integer or null")
    return CanonicalMetricValue(metric_value, status)


def _combined_metric(
    left: CanonicalMetricValue, right: CanonicalMetricValue
) -> CanonicalMetricValue:
    if left.status == right.status == "observed":
        assert left.value is not None and right.value is not None
        return CanonicalMetricValue(left.value + right.value, "observed")
    for status in ("unavailable", "unknown", "not_applicable"):
        if status in {left.status, right.status}:
            return CanonicalMetricValue(None, status)
    raise ValueError("combined metric states are invalid")


def canonical_rows_from_snapshot(
    snapshot: Mapping[str, object],
) -> tuple[CanonicalAnalysisRow, ...]:
    release = _mapping(snapshot.get("release"), name="snapshot.release")
    election = _mapping(snapshot.get("election"), name="snapshot.election")
    release_id = release.get("release_id")
    election_slug = election.get("slug")
    if not isinstance(release_id, str) or not isinstance(election_slug, str):
        raise ValueError("snapshot release and election identities are required")
    mesa_index: dict[str, Mapping[str, object]] = {}
    for value in _sequence(snapshot.get("mesas"), name="snapshot.mesas"):
        mesa = _mapping(value, name="snapshot.mesas[]")
        mesa_id = mesa.get("id")
        if not isinstance(mesa_id, str) or mesa_id in mesa_index:
            raise ValueError("mesa identities must be unique strings")
        mesa_index[mesa_id] = mesa

    rows: list[CanonicalAnalysisRow] = []
    seen_results: set[str] = set()
    for value in _sequence(snapshot.get("results"), name="snapshot.results"):
        result = _mapping(value, name="snapshot.results[]")
        mesa_id = result.get("mesa_id")
        if not isinstance(mesa_id, str):
            continue
        if mesa_id in seen_results:
            raise ValueError("analysis requires exactly one result vector per mesa")
        seen_results.add(mesa_id)
        mesa_value = mesa_index.get(mesa_id)
        if mesa_value is None:
            raise ValueError("result facts cannot cross the canonical mesa registry")
        mesa = mesa_value
        if result.get("election_slug") != election_slug:
            raise ValueError("result facts cannot cross the canonical election")

        candidates = _sequence(result.get("candidates"), name="result.candidates")
        candidate_values: list[tuple[str, CanonicalMetricValue]] = []
        candidate_total = 0
        candidates_observed = True
        for candidate_value in candidates:
            candidate = _mapping(candidate_value, name="result.candidates[]")
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, str):
                raise ValueError("candidate facts require an identity")
            votes = _metric(candidate.get("votes"), name="candidate.votes")
            candidate_values.append((candidate_id, votes))
            if votes.value is None:
                candidates_observed = False
            else:
                candidate_total += votes.value

        valid = _metric(result.get("valid_votes"), name="result.valid_votes")
        blank = _metric(result.get("blank_votes"), name="result.blank_votes")
        null_votes = _metric(result.get("null_votes"), name="result.null_votes")
        unmarked = _metric(result.get("unmarked_votes"), name="result.unmarked_votes")
        voters = _metric(result.get("voters"), name="result.voters")
        registered = _metric(result.get("registered_electors"), name="result.registered_electors")
        null_unmarked = _combined_metric(null_votes, unmarked)
        complete = bool(
            candidates_observed
            and valid.value is not None
            and blank.value is not None
            and candidate_total + blank.value == valid.value
            and voters.value is not None
            and null_unmarked.value is not None
            and valid.value + null_unmarked.value == voters.value
        )
        provenance = _mapping(result.get("provenance"), name="result.provenance")
        source_url = provenance.get("source_url")
        source_hash = provenance.get("content_hash")
        source_type = provenance.get("source_type")
        legal_status = provenance.get("legal_status")
        if not isinstance(source_url, str) or not _is_sha256(source_hash):
            raise ValueError("each canonical row requires source URL and SHA-256 provenance")
        if not isinstance(source_type, str) or not isinstance(legal_status, str):
            raise ValueError("each canonical row requires source type and legal status")
        polling_place_id = mesa.get("polling_place_id")
        municipality_id = mesa.get("municipality_id")
        department_id = mesa.get("department_id")
        if not all(
            isinstance(item, str) for item in (polling_place_id, municipality_id, department_id)
        ):
            raise ValueError("canonical mesas require complete geography identities")
        assert isinstance(polling_place_id, str)
        assert isinstance(municipality_id, str)
        assert isinstance(department_id, str)
        assert isinstance(source_hash, str)

        context = _CanonicalRowContext(
            mesa_id=mesa_id,
            polling_place_id=polling_place_id,
            municipality_id=municipality_id,
            department_id=department_id,
            complete_ballot_vector=complete,
            source_type=source_type,
            legal_status=legal_status,
            source_url=source_url,
            source_hash=source_hash,
        )
        rows.append(_analysis_row(context, "blank", None, blank, valid))
        rows.extend(
            _analysis_row(context, "candidate_share", candidate_id, votes, valid)
            for candidate_id, votes in candidate_values
        )
        rows.append(_analysis_row(context, "null_unmarked", None, null_unmarked, voters))
        rows.append(_analysis_row(context, "turnout", None, voters, registered))
    return tuple(sorted(rows, key=lambda row: (row.mesa_id, row.metric, row.candidate_id or "")))


def _family_key(row: CanonicalAnalysisRow) -> str:
    return row.metric if row.candidate_id is None else f"{row.metric}:{row.candidate_id}"


def peer_family_from_canonical_rows(
    rows: Sequence[CanonicalAnalysisRow],
    *,
    metric: Metric,
    candidate_id: str | None,
    source_release_id: str,
    election_slug: str,
    input_artifact_hash: str,
) -> PeerFamilyInput:
    if metric == "candidate_share" and not candidate_id:
        raise ValueError("candidate share peer families require a candidate identity")
    if metric != "candidate_share" and candidate_id is not None:
        raise ValueError("noncandidate peer families cannot declare a candidate identity")
    by_mesa: dict[str, dict[tuple[str, str | None], CanonicalAnalysisRow]] = defaultdict(dict)
    for row in rows:
        key = (row.metric, row.candidate_id)
        if key in by_mesa[row.mesa_id]:
            raise ValueError("canonical peer input contains a duplicate metric row")
        by_mesa[row.mesa_id][key] = row
    target_key = (metric, candidate_id)
    identifiers = sorted(mesa_id for mesa_id, values in by_mesa.items() if target_key in values)
    expected_digest = family_digest(identifiers)
    if not identifiers:
        raise ValueError("peer family has no canonical target rows")
    source_pairs = {
        (by_mesa[mesa_id][target_key].source_type, by_mesa[mesa_id][target_key].legal_status)
        for mesa_id in identifiers
    }
    if len(source_pairs) != 1:
        raise ValueError("peer family cannot mix source or legal-status layers")
    source_type, legal_status = next(iter(source_pairs))
    cohort_hash = cohort_digest(
        election_slug=election_slug,
        data_version=source_release_id,
        source_layer=source_type,
        source_type=source_type,
        legal_status=legal_status,
        metric=metric,
        candidate_id=candidate_id,
        expected_family_count=len(identifiers),
        expected_family_digest=expected_digest,
        input_artifact_hash=input_artifact_hash,
    )
    peer_rows: list[MesaMetrics] = []
    exclusions: list[tuple[str, str]] = []
    for mesa_id in identifiers:
        values = by_mesa[mesa_id]
        target = values[target_key]
        blank = values.get(("blank", None))
        null_unmarked = values.get(("null_unmarked", None))
        turnout = values.get(("turnout", None))
        candidates = [
            row for (row_metric, _), row in values.items() if row_metric == "candidate_share"
        ]
        required = (target, blank, null_unmarked, turnout)
        if any(row is None for row in required):
            exclusions.append((mesa_id, "canonical_metric_component_unavailable"))
            continue
        assert blank is not None and null_unmarked is not None and turnout is not None
        observed = (
            target.numerator.value,
            blank.numerator.value,
            blank.denominator.value,
            null_unmarked.numerator.value,
            turnout.numerator.value,
        )
        if any(value is None for value in observed):
            exclusions.append((mesa_id, "canonical_metric_value_unavailable"))
            continue
        target_value, blank_value, valid_value, null_value, ballots_value = observed
        assert target_value is not None
        assert blank_value is not None
        assert valid_value is not None
        assert null_value is not None
        assert ballots_value is not None
        candidate_values = [row.numerator.value for row in candidates]
        complete_candidate_total = (
            sum(value for value in candidate_values if value is not None)
            if target.complete_ballot_vector
            and all(value is not None for value in candidate_values)
            else None
        )
        peer_rows.append(
            MesaMetrics(
                mesa_id=mesa_id,
                place_id=target.polling_place_id,
                municipality_id=target.municipality_id,
                department_id=target.department_id,
                metric=metric,
                registered=turnout.denominator.value,
                ballots=ballots_value,
                candidate_votes=target_value if metric == "candidate_share" else 0,
                valid_votes=valid_value,
                blank_votes=blank_value,
                null_unmarked_votes=null_value,
                candidate_id=candidate_id,
                election_slug=election_slug,
                data_version=source_release_id,
                source_layer=source_type,
                source_type=source_type,
                legal_status=legal_status,
                expected_family_count=len(identifiers) - len(exclusions),
                expected_family_digest=expected_digest,
                input_artifact_hash=input_artifact_hash,
                cohort_hash=cohort_hash,
                source_links=(target.source_url,),
                candidate_total_votes=complete_candidate_total,
                denominator_provenance=(
                    "joined_official" if complete_candidate_total is not None else "unavailable"
                ),
            )
        )
    if exclusions:
        included_ids = [row.mesa_id for row in peer_rows]
        expected_digest = family_digest(included_ids)
        cohort_hash = cohort_digest(
            election_slug=election_slug,
            data_version=source_release_id,
            source_layer=source_type,
            source_type=source_type,
            legal_status=legal_status,
            metric=metric,
            candidate_id=candidate_id,
            expected_family_count=len(peer_rows),
            expected_family_digest=expected_digest,
            input_artifact_hash=input_artifact_hash,
        )
        peer_rows = [
            replace(
                row,
                expected_family_count=len(peer_rows),
                expected_family_digest=expected_digest,
                cohort_hash=cohort_hash,
            )
            for row in peer_rows
        ]
    return PeerFamilyInput(
        metric=metric,
        candidate_id=candidate_id,
        mesas=tuple(peer_rows),
        excluded_units=tuple(exclusions),
        family_digest=expected_digest,
        cohort_digest=cohort_hash,
    )


def _peer_eligibility(rows: tuple[CanonicalAnalysisRow, ...]) -> dict[str, EligibilityDecision]:
    by_family: dict[str, list[CanonicalAnalysisRow]] = defaultdict(list)
    for row in rows:
        by_family[_family_key(row)].append(row)
    decisions: dict[str, EligibilityDecision] = {}
    for family, values in sorted(by_family.items()):
        eligible_base = [
            row
            for row in values
            if row.complete_ballot_vector
            and row.denominator.status == "observed"
            and row.denominator.value is not None
            and row.denominator.value >= 80
        ]
        place_counts: dict[str, int] = defaultdict(int)
        municipality_counts: dict[str, int] = defaultdict(int)
        department_counts: dict[str, int] = defaultdict(int)
        for row in eligible_base:
            place_counts[row.polling_place_id] += 1
            municipality_counts[row.municipality_id] += 1
            department_counts[row.department_id] += 1
        eligible_units = sum(
            1
            for row in eligible_base
            if place_counts[row.polling_place_id] - 1 >= 30
            or municipality_counts[row.municipality_id] - 1 >= 30
            or department_counts[row.department_id] - 1 >= 30
        )
        reasons: list[str] = []
        if family == "turnout" and len(eligible_base) < len(values):
            eligible_units = 0
            reasons.append("registered_electors_coverage_insufficient")
        elif not eligible_base:
            reasons.append("metric_denominator_or_ballot_vector_unavailable")
        elif not eligible_units:
            reasons.append("fewer_than_30_eligible_peers")
        decisions[family] = EligibilityDecision(
            status="evaluable" if eligible_units else "not_evaluable",
            eligible_units=eligible_units,
            total_units=len(values),
            reasons=tuple(reasons),
        )
    decisions["spatial"] = EligibilityDecision(
        status="not_evaluable",
        eligible_units=0,
        total_units=len({row.mesa_id for row in rows}),
        reasons=(
            "authenticated_coordinates_unavailable",
            "mesa_to_place_crosswalk_unavailable",
        ),
    )
    decisions["outcome_sensitivity"] = EligibilityDecision(
        status="not_evaluable",
        eligible_units=0,
        total_units=len({row.mesa_id for row in rows}),
        reasons=(
            "documentary_trust_registry_unavailable",
            "two_reviewer_attestations_unavailable",
            "canonical_replay_bounds_unavailable",
        ),
    )
    return decisions


def _cohort_registry(
    rows: tuple[CanonicalAnalysisRow, ...],
    *,
    source_release_id: str,
    election_slug: str,
) -> tuple[dict[str, object], int]:
    by_family: dict[str, list[CanonicalAnalysisRow]] = defaultdict(list)
    for row in rows:
        by_family[_family_key(row)].append(row)
    families: list[dict[str, object]] = []
    for family, values in sorted(by_family.items()):
        eligible = [
            row
            for row in values
            if row.complete_ballot_vector
            and row.numerator.status == "observed"
            and row.denominator.status == "observed"
            and row.denominator.value is not None
            and row.denominator.value >= 80
        ]
        pools: tuple[tuple[str, Callable[[CanonicalAnalysisRow], str]], ...] = (
            ("polling_place", lambda row: row.polling_place_id),
            ("municipality", lambda row: row.municipality_id),
            ("department", lambda row: row.department_id),
        )
        counts: dict[str, dict[str, int]] = {level: defaultdict(int) for level, _ in pools}
        for row in eligible:
            for level, selector in pools:
                counts[level][selector(row)] += 1
        selections: list[dict[str, object]] = []
        for row in sorted(eligible, key=lambda item: item.mesa_id):
            selection: dict[str, object] = {
                "mesa_id": row.mesa_id,
                "selected_pool": None,
                "peer_count": 0,
                "target_excluded": True,
            }
            for level, selector in pools:
                peer_count = counts[level][selector(row)] - 1
                if peer_count >= 30:
                    selection["selected_pool"] = level
                    selection["peer_count"] = peer_count
                    break
            selections.append(selection)
        metric, _, candidate = family.partition(":")
        family_ids = [row.mesa_id for row in eligible]
        family_entry: dict[str, object] = {
            "source_release_id": source_release_id,
            "election_slug": election_slug,
            "metric": metric,
            "candidate_id": candidate or None,
            "family_count": len(family_ids),
            "family_digest": family_digest(family_ids),
            "fallback_order": [level for level, _ in pools],
            "selections": selections,
        }
        family_entry["cohort_digest"] = _hash(family_entry)
        families.append(family_entry)
    return {"families": families}, sum(
        len(selections)
        for family in families
        for selections in [family["selections"]]
        if isinstance(selections, list)
    )


def _descriptive(
    snapshot: Mapping[str, object], rows: tuple[CanonicalAnalysisRow, ...]
) -> dict[str, object]:
    summary = _mapping(snapshot.get("summary"), name="snapshot.summary")
    reconciliation = _mapping(summary.get("reconciliation"), name="summary.reconciliation")
    completion = _mapping(summary.get("completion"), name="summary.completion")
    mesa_rows = {row.mesa_id for row in rows}
    metric_coverage: dict[str, dict[str, int]] = {}
    by_family: dict[str, list[CanonicalAnalysisRow]] = defaultdict(list)
    for row in rows:
        by_family[_family_key(row)].append(row)
    for family, values in sorted(by_family.items()):
        statuses: dict[str, int] = {status: 0 for status in sorted(_METRIC_STATUSES)}
        for row in values:
            statuses[row.denominator.status] += 1
        metric_coverage[family] = statuses

    candidate_totals: dict[str, int] = defaultdict(int)
    department_candidates: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row.metric == "candidate_share" and row.numerator.value is not None:
            assert row.candidate_id is not None
            candidate_totals[row.candidate_id] += row.numerator.value
            department_candidates[row.department_id][row.candidate_id] += row.numerator.value
    ordered_candidates = sorted(candidate_totals.items(), key=lambda item: (-item[1], item[0]))
    national_margin = (
        ordered_candidates[0][1] - ordered_candidates[1][1]
        if len(ordered_candidates) >= 2
        else None
    )
    exception_value = reconciliation.get("exceptions", 0)
    if type(exception_value) is not int or exception_value < 0:
        raise ValueError("summary reconciliation exceptions must be a nonnegative integer")
    expected = completion.get("expected")
    reported = completion.get("reported")
    if (
        type(expected) is not int
        or type(reported) is not int
        or expected < 0
        or reported < 0
        or reported > expected
    ):
        raise ValueError("summary completion counts are invalid")
    return {
        "mesa_count": len(mesa_rows),
        "mesa_completion": {"expected": expected, "reported": reported},
        "metric_missingness": metric_coverage,
        "candidate_totals": dict(sorted(candidate_totals.items())),
        "candidate_shares": {
            candidate: votes / sum(candidate_totals.values())
            for candidate, votes in sorted(candidate_totals.items())
        }
        if candidate_totals
        else {},
        "national_margin_votes": national_margin,
        "department_candidate_totals": {
            department: dict(sorted(values.items()))
            for department, values in sorted(department_candidates.items())
        },
        "reconciliation_exceptions": exception_value,
        "historical_context_is_anomaly_evidence": False,
        "benford_analysis": "not_run",
    }


def _artifact(
    *,
    analysis_release_id: str,
    kind: str,
    schema_version: str,
    value: object,
    record_count: int,
    status: str = "available",
    status_reason: str | None = None,
) -> AnalysisArtifact:
    if not _ARTIFACT_KIND.fullmatch(kind):
        raise ValueError("artifact kind is not a safe immutable filename")
    content = _canonical_json(value)
    digest = hashlib.sha256(content).hexdigest()
    return AnalysisArtifact(
        artifact_id=f"{analysis_release_id}:{kind}",
        kind=kind,
        schema_version=schema_version,
        media_type="application/json",
        record_count=record_count,
        byte_size=len(content),
        byte_hash=digest,
        content_hash=digest,
        status=status,
        status_reason=status_reason,
        content=content,
    )


def build_analysis_bundle(
    registry: CanonicalInputRegistry,
    *,
    methodology_version: str,
    generated_at: datetime,
) -> AnalysisBundle:
    if not methodology_version:
        raise ValueError("analysis methodology version is required")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("analysis generation time must be timezone-aware")
    rows = canonical_rows_from_snapshot(registry.snapshot)
    if not rows:
        raise ValueError("analysis input contains no canonical mesa rows")
    row_payload = [asdict(row) for row in rows]
    all_mesa_ids = sorted(
        str(_mapping(value, name="snapshot.mesas[]").get("id"))
        for value in _sequence(registry.snapshot.get("mesas"), name="snapshot.mesas")
    )
    included_unit_ids = sorted({row.mesa_id for row in rows})
    included_unit_set = set(included_unit_ids)
    excluded_units = [
        {"unit_id": mesa_id, "reason": "result_unavailable"}
        for mesa_id in all_mesa_ids
        if mesa_id not in included_unit_set
    ]
    registry_payload = {
        "source_release_id": registry.source_release_id,
        "election_slug": registry.election_slug,
        "source_manifest_hash": registry.source_manifest_hash,
        "included_unit_ids": included_unit_ids,
        "excluded_units": excluded_units,
        "metric_dimensions": sorted({_family_key(row) for row in rows}),
        "detector_code_hash": registry.detector_code_hash,
        "configuration_hash": registry.configuration_hash,
        "seed_registry_hash": registry.seed_registry_hash,
        "runtime_fingerprint": registry.runtime_fingerprint,
        "documentary_attestations": [asdict(item) for item in registry.documentary_attestations],
        "geocode_ledger": (
            asdict(registry.geocode_ledger) if registry.geocode_ledger is not None else None
        ),
        "historical_context_hashes": sorted(registry.historical_context_hashes),
        "canonical_rows_hash": _hash(row_payload),
    }
    canonical_input_hash = _hash(registry_payload)
    identity_hash = _hash(
        {
            "source_release_id": registry.source_release_id,
            "election_slug": registry.election_slug,
            "methodology_version": methodology_version,
            "canonical_input_hash": canonical_input_hash,
        }
    )
    analysis_release_id = f"analysis-{identity_hash[:24]}"
    eligibility = _peer_eligibility(rows)
    if registry.geocode_ledger is not None:
        eligibility["spatial"] = EligibilityDecision(
            status="research_preview",
            eligible_units=len({row.mesa_id for row in rows}),
            total_units=len({row.mesa_id for row in rows}),
            reasons=("spatial_pass_a_required",),
        )
    descriptive = _descriptive(registry.snapshot, rows)
    canonical_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="canonical_input",
        schema_version="canonical-analysis-rows-v1",
        value={"registry": registry_payload, "rows": row_payload},
        record_count=len(rows),
    )
    eligibility_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="eligibility",
        schema_version="analysis-eligibility-v1",
        value={key: asdict(value) for key, value in sorted(eligibility.items())},
        record_count=len(eligibility),
    )
    cohort_registry, cohort_record_count = _cohort_registry(
        rows,
        source_release_id=registry.source_release_id,
        election_slug=registry.election_slug,
    )
    cohort_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="cohort_registry",
        schema_version="analysis-cohort-registry-v1",
        value=cohort_registry,
        record_count=cohort_record_count,
    )
    descriptive_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="descriptive_summary",
        schema_version="descriptive-analysis-v1",
        value=descriptive,
        record_count=1,
    )
    exception_value = descriptive["reconciliation_exceptions"]
    if type(exception_value) is not int:
        raise ValueError("descriptive reconciliation count is invalid")
    exception_count = exception_value
    deterministic_anomalies: list[dict[str, object]] = [
        {
            "id": f"{analysis_release_id}:coverage:{index + 1}",
            "family": "identity_coverage",
            "evidence_tier": "deterministic",
            "evaluable": True,
            "audit_priority_points": 0,
            "reason": "result_unavailable",
            "unit_id": excluded["unit_id"],
            "explanation": "Expected mesa has no result fact in the immutable source release.",
            "calculations": {"expected_fact_count": 1, "observed_fact_count": 0},
            "limitations": ["No vote total is inferred for the absent fact."],
            "provenance": {
                "source_release_id": registry.source_release_id,
                "election_slug": registry.election_slug,
            },
            "affected_votes": None,
        }
        for index, excluded in enumerate(excluded_units)
    ]
    rows_by_mesa: dict[str, list[CanonicalAnalysisRow]] = defaultdict(list)
    for row in rows:
        rows_by_mesa[row.mesa_id].append(row)
    arithmetic_rows = [
        mesa_rows
        for _, mesa_rows in sorted(rows_by_mesa.items())
        if not mesa_rows[0].complete_ballot_vector
    ]
    deterministic_anomalies.extend(
        {
            "id": f"{analysis_release_id}:reconciliation:{index + 1}",
            "family": "structural_arithmetic",
            "evidence_tier": "deterministic",
            "evaluable": True,
            "audit_priority_points": 0,
            "reason": "ballot_vector_inconsistent",
            "unit_id": mesa_rows[0].mesa_id,
            "explanation": "Observed ballot components do not satisfy the registered identities.",
            "calculations": {
                "candidate_votes": sum(
                    row.numerator.value or 0 for row in mesa_rows if row.metric == "candidate_share"
                ),
                "blank_votes": next(
                    row.numerator.value for row in mesa_rows if row.metric == "blank"
                ),
                "valid_votes": next(
                    row.denominator.value for row in mesa_rows if row.metric == "blank"
                ),
                "null_unmarked_votes": next(
                    row.numerator.value for row in mesa_rows if row.metric == "null_unmarked"
                ),
                "voters": next(
                    row.denominator.value for row in mesa_rows if row.metric == "null_unmarked"
                ),
            },
            "limitations": ["This deterministic check does not attribute a cause."],
            "provenance": {
                "source_release_id": registry.source_release_id,
                "election_slug": registry.election_slug,
                "source_url": mesa_rows[0].source_url,
                "source_hash": mesa_rows[0].source_hash,
            },
            "affected_votes": None,
        }
        for index, mesa_rows in enumerate(arithmetic_rows)
    )
    identified_reconciliation = min(exception_count, len(arithmetic_rows) + len(excluded_units))
    deterministic_anomalies.extend(
        {
            "id": f"{analysis_release_id}:reconciliation:unlocated:{index + 1}",
            "family": "structural_arithmetic",
            "evidence_tier": "deterministic",
            "evaluable": True,
            "audit_priority_points": 0,
            "reason": "stored_reconciliation_exception",
            "unit_id": None,
            "explanation": "The source release records a reconciliation exception.",
            "calculations": None,
            "limitations": ["The snapshot does not identify this exception at mesa level."],
            "provenance": {
                "source_release_id": registry.source_release_id,
                "election_slug": registry.election_slug,
            },
            "affected_votes": None,
        }
        for index in range(max(0, exception_count - identified_reconciliation))
    )
    anomalies_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="deterministic_anomalies",
        schema_version="analysis-anomalies-v1",
        value=deterministic_anomalies,
        record_count=len(deterministic_anomalies),
    )
    status_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="research_status",
        schema_version="analysis-research-status-v1",
        value={
            "peer_distribution": "pass_a_required",
            "spatial": asdict(eligibility["spatial"]),
            "outcome_sensitivity": asdict(eligibility["outcome_sensitivity"]),
            "hierarchical": "research_only",
            "cluster": "research_only_geographic_confounding",
            "runs_replication": "research_only",
            "longitudinal": "descriptive_context_only",
            "statistical_public_priority_points": 0,
        },
        record_count=1,
        status="available",
        status_reason="independent_validation_required",
    )
    family_diagnostics: list[dict[str, object]] = []
    cohort_families = cohort_registry.get("families")
    if isinstance(cohort_families, list):
        for family in cohort_families:
            if not isinstance(family, dict):
                continue
            selections = family.get("selections")
            fallback_counts: dict[str, int] = defaultdict(int)
            peer_counts: list[int] = []
            if isinstance(selections, list):
                for selection in selections:
                    if not isinstance(selection, dict):
                        continue
                    selected = selection.get("selected_pool")
                    fallback_counts[str(selected) if selected is not None else "none"] += 1
                    peers = selection.get("peer_count")
                    if type(peers) is int:
                        peer_counts.append(peers)
            family_diagnostics.append(
                {
                    "metric": family.get("metric"),
                    "candidate_id": family.get("candidate_id"),
                    "family_count": family.get("family_count"),
                    "family_digest": family.get("family_digest"),
                    "cohort_digest": family.get("cohort_digest"),
                    "fallback_counts": dict(sorted(fallback_counts.items())),
                    "peer_count_minimum": min(peer_counts) if peer_counts else None,
                    "peer_count_maximum": max(peer_counts) if peer_counts else None,
                }
            )
    model_diagnostics_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="model_diagnostics",
        schema_version="analysis-model-diagnostics-v1",
        value={
            "families": family_diagnostics,
            "p_value_distribution": "not_run_pass_a_required",
            "q_value_distribution": "not_run_pass_a_required",
            "effect_size_distribution": "not_run_pass_a_required",
            "known_weakness": "whole_place_shift_may_not_be_detected_by_peer_comparison",
        },
        record_count=len(family_diagnostics),
    )
    validation_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="validation",
        schema_version="analysis-validation-v1",
        value={
            "pass_a": {
                "status": "not_run",
                "required_null_simulations_per_stratum": 100,
                "required_alternative_simulations_per_stratum": 100,
                "maximum_error_rate": 0.05,
                "minimum_power": 0.8,
                "confidence": 0.95,
            },
            "pass_b": {
                "status": "not_run",
                "required_null_simulations_per_stratum": 1000,
                "required_alternative_simulations_per_stratum": 1000,
                "distinct_runtime_required": True,
                "distinct_operator_required": True,
                "independent_human_signature_required": True,
            },
        },
        record_count=2,
        status="not_evaluable",
        status_reason="pass_a_and_independent_pass_b_not_completed",
    )
    local_sensitivity_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="local_sensitivity",
        schema_version="analysis-local-sensitivity-v1",
        value={"status": "not_evaluable", "trusted_statistical_signals": 0},
        record_count=0,
        status="not_evaluable",
        status_reason="validated_statistical_signal_artifact_unavailable",
    )
    spatial_status_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="spatial_status",
        schema_version="analysis-spatial-status-v1",
        value=asdict(eligibility["spatial"]),
        record_count=0,
        status="not_evaluable",
        status_reason="authenticated_coordinates_and_crosswalk_unavailable",
    )
    outcome_issues = [
        {"code": reason, "record_ids": []} for reason in eligibility["outcome_sensitivity"].reasons
    ]
    outcome_payload: dict[str, object] = {
        "status": "not_evaluable",
        "evaluable": False,
        "issues": outcome_issues,
        "scope": None,
        "outcome_source": None,
        "leader_id": None,
        "runner_up_id": None,
        "leader_votes": None,
        "runner_up_votes": None,
        "observed_margin_votes": None,
        "verified_record_ids": None,
        "unresolved_record_ids": None,
        "verified_affected_votes": None,
        "verified_margin_shift_bound": None,
        "unresolved_affected_vote_upper_bound": None,
        "unresolved_margin_shift_upper_bound": None,
        "combined_affected_vote_upper_bound": None,
        "combined_margin_shift_upper_bound": None,
        "verified_margin_headroom": None,
        "combined_margin_headroom": None,
        "tie_possible_from_verified": None,
        "lead_change_possible_from_verified": None,
        "tie_possible_including_unresolved": None,
        "lead_change_possible_including_unresolved": None,
        "source_links": [],
        "evidence_hash": None,
        "methodology_version": "outcome-sensitivity-v3.0.0",
        "calculation": "No outcome bound is calculated until every registered prerequisite passes.",
        "limitations": list(eligibility["outcome_sensitivity"].reasons),
    }
    outcome_payload["output_hash"] = _hash(outcome_payload)
    outcome_status_artifact = _artifact(
        analysis_release_id=analysis_release_id,
        kind="outcome_sensitivity",
        schema_version="outcome-sensitivity-v3.0.0",
        value=outcome_payload,
        record_count=1,
        status_reason="documentary_registry_two_reviewer_bounds_and_replay_unavailable",
    )
    artifact_values = [
        canonical_artifact,
        eligibility_artifact,
        cohort_artifact,
        descriptive_artifact,
        anomalies_artifact,
        status_artifact,
        model_diagnostics_artifact,
        validation_artifact,
        local_sensitivity_artifact,
        spatial_status_artifact,
        outcome_status_artifact,
    ]
    if registry.historical_context_artifacts:
        artifact_values.append(
            _artifact(
                analysis_release_id=analysis_release_id,
                kind="historical_comparison_context",
                schema_version="historical-comparison-context-v1",
                value={
                    "context_only": True,
                    "anomaly_evidence": False,
                    "artifacts": registry.historical_context_artifacts,
                },
                record_count=len(registry.historical_context_artifacts),
            )
        )
    artifacts = tuple(artifact_values)
    manifest = {
        "schema_version": "analysis-release-manifest-v1",
        "analysis_release_id": analysis_release_id,
        "source_release_id": registry.source_release_id,
        "election_slug": registry.election_slug,
        "methodology_version": methodology_version,
        "canonical_input_hash": canonical_input_hash,
        "producer_runtime_fingerprint": registry.runtime_fingerprint,
        "detector_code_hash": registry.detector_code_hash,
        "configuration_hash": registry.configuration_hash,
        "seed_registry_hash": registry.seed_registry_hash,
        "generated_at": generated_at.isoformat(),
        "exposure_tier": AnalysisExposureTier.INTERNAL.value,
        "artifacts": [artifact.manifest_record() for artifact in artifacts],
    }
    return AnalysisBundle(
        analysis_release_id=analysis_release_id,
        source_release_id=registry.source_release_id,
        election_slug=registry.election_slug,
        methodology_version=methodology_version,
        canonical_input_hash=canonical_input_hash,
        producer_runtime_fingerprint=registry.runtime_fingerprint,
        exposure_tier=AnalysisExposureTier.INTERNAL,
        generated_at=generated_at,
        eligibility=eligibility,
        descriptive=descriptive,
        artifacts=artifacts,
        manifest=manifest,
        manifest_hash=_hash(manifest),
    )


def build_registry_from_files(
    *,
    snapshot_path: Path,
    source_manifest_path: Path,
    configuration_path: Path,
    detector_source_directory: Path,
    runtime_fingerprint: str,
    historical_context_paths: Sequence[Path] = (),
) -> CanonicalInputRegistry:
    if not _is_sha256(runtime_fingerprint):
        raise ValueError("producer runtime requires a SHA-256 fingerprint")
    snapshot_value = _strict_json(snapshot_path.read_bytes(), name="source snapshot")
    manifest_value = _strict_json(source_manifest_path.read_bytes(), name="source release manifest")
    configuration_value = _strict_json(
        configuration_path.read_bytes(), name="analysis configuration"
    )
    if not isinstance(snapshot_value, dict):
        raise ValueError("source snapshot must be a JSON object")
    if not isinstance(manifest_value, dict):
        raise ValueError("source release manifest must be a JSON object")
    if not isinstance(configuration_value, dict):
        raise ValueError("analysis configuration must be a JSON object")
    release = _mapping(snapshot_value.get("release"), name="source snapshot.release")
    election = _mapping(snapshot_value.get("election"), name="source snapshot.election")
    release_id = release.get("release_id")
    election_slug = election.get("slug")
    if not isinstance(release_id, str) or not isinstance(election_slug, str):
        raise ValueError("source snapshot identities are required")
    if manifest_value.get("release_id") != release_id:
        raise ValueError("source manifest and snapshot release identities differ")
    if manifest_value.get("election_slug") != election_slug:
        raise ValueError("source manifest and snapshot election identities differ")
    simulation_profiles = _mapping(
        configuration_value.get("simulation_profiles"),
        name="analysis configuration.simulation_profiles",
    )
    historical_values: list[Mapping[str, object]] = []
    for path in sorted(historical_context_paths):
        context = _strict_json(path.read_bytes(), name=f"historical context {path.name}")
        if not isinstance(context, dict):
            raise ValueError(f"historical context {path.name} must be a JSON object")
        historical_values.append(context)
    return CanonicalInputRegistry(
        source_release_id=release_id,
        election_slug=election_slug,
        source_manifest_hash=hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
        detector_code_hash=_tree_hash(detector_source_directory),
        configuration_hash=hashlib.sha256(configuration_path.read_bytes()).hexdigest(),
        seed_registry_hash=_hash(simulation_profiles),
        runtime_fingerprint=runtime_fingerprint,
        documentary_attestations=(),
        geocode_ledger=None,
        snapshot=snapshot_value,
        historical_context_hashes=tuple(
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(historical_context_paths)
        ),
        historical_context_artifacts=tuple(historical_values),
    )


def _strict_json(raw: bytes, *, name: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"{name} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"{name} contains non-finite number {value}")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from exc
    return value


def _bundle_files(bundle: AnalysisBundle) -> dict[str, bytes]:
    manifest = {**bundle.manifest, "manifest_hash": bundle.manifest_hash}
    files = {"manifest.json": _canonical_json(manifest)}
    for artifact in bundle.artifacts:
        if not artifact.artifact_id.startswith(f"{bundle.analysis_release_id}:"):
            raise ValueError("artifact is not bound to the analysis release")
        files[f"artifacts/{artifact.kind}.json"] = artifact.content
    return files


def write_analysis_bundle(bundle: AnalysisBundle, release_root: Path) -> Path:
    """Atomically materialize immutable analysis bytes, or return an exact no-op."""
    files = _bundle_files(bundle)
    release_root.mkdir(parents=True, exist_ok=True)
    target = release_root / bundle.analysis_release_id
    if target.exists():
        load_analysis_bundle(target / "manifest.json")
        existing = {
            str(path.relative_to(target)): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        if existing != files:
            raise ValueError("refusing to overwrite a non-identical immutable analysis release")
        return target
    with TemporaryDirectory(prefix=".analysis-staging-", dir=release_root) as temporary:
        staging = Path(temporary) / "bundle"
        for relative, content in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        os.replace(staging, target)
    return target


def load_analysis_bundle(manifest_path: Path) -> dict[str, object]:
    """Validate an immutable on-disk bundle and return its detached manifest."""
    value = _strict_json(manifest_path.read_bytes(), name="analysis manifest")
    if not isinstance(value, dict):
        raise ValueError("analysis manifest must be a JSON object")
    manifest = value
    manifest_hash = manifest.get("manifest_hash")
    if not _is_sha256(manifest_hash):
        raise ValueError("analysis manifest requires a SHA-256 manifest hash")
    hash_payload = dict(manifest)
    hash_payload.pop("manifest_hash")
    if _hash(hash_payload) != manifest_hash:
        raise ValueError("analysis manifest hash does not match its canonical content")
    analysis_release_id = manifest.get("analysis_release_id")
    if not isinstance(analysis_release_id, str) or not analysis_release_id:
        raise ValueError("analysis manifest requires an analysis release identity")
    artifacts = _sequence(manifest.get("artifacts"), name="analysis manifest.artifacts")
    seen: set[str] = set()
    for value in artifacts:
        artifact = _mapping(value, name="analysis manifest.artifacts[]")
        artifact_id = artifact.get("artifact_id")
        kind = artifact.get("kind")
        filename = artifact.get("filename")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id.startswith(f"{analysis_release_id}:")
            or not isinstance(kind, str)
            or not _ARTIFACT_KIND.fullmatch(kind)
            or filename != f"artifacts/{kind}.json"
            or artifact_id in seen
        ):
            raise ValueError("analysis artifact scope or filename is invalid")
        seen.add(artifact_id)
        path = manifest_path.parent / filename
        content = path.read_bytes()
        if len(content) != artifact.get("byte_size"):
            raise ValueError(f"analysis artifact {kind} byte size does not match")
        digest = hashlib.sha256(content).hexdigest()
        if digest != artifact.get("byte_hash"):
            raise ValueError(f"analysis artifact {kind} byte hash does not match")
        if digest != artifact.get("content_hash"):
            raise ValueError(f"analysis artifact {kind} content hash does not match")
        _strict_json(content, name=f"analysis artifact {kind}")
    return manifest


def verify_pass_b_packet(
    packet: PassBPacket,
    bundle: AnalysisBundle,
    *,
    signature_verifier: Callable[[str, str, str], bool],
) -> bool:
    expected = {
        "analysis_release_id": bundle.analysis_release_id,
        "source_release_id": bundle.source_release_id,
        "election_slug": bundle.election_slug,
        "methodology_version": bundle.methodology_version,
        "canonical_input_hash": bundle.canonical_input_hash,
        "manifest_hash": bundle.manifest_hash,
    }
    actual = {key: getattr(packet, key) for key in expected}
    if actual != expected:
        raise ValueError("Pass B packet does not bind the exact analysis release")
    detector_hash = bundle.manifest.get("detector_code_hash")
    if packet.detector_code_hash != detector_hash:
        raise ValueError("Pass B packet detector code hash does not match")
    if packet.producer_runtime_fingerprint != bundle.producer_runtime_fingerprint:
        raise ValueError("Pass B packet producer runtime does not match")
    if not _is_sha256(packet.replay_runtime_fingerprint):
        raise ValueError("Pass B clean-room runtime requires a SHA-256 fingerprint")
    if packet.replay_runtime_fingerprint == packet.producer_runtime_fingerprint:
        raise ValueError("Pass B clean-room replay requires a distinct runtime")
    if packet.replay_operator_id == packet.producer_operator_id:
        raise ValueError("Pass B clean-room replay requires a distinct operator")
    if packet.decision != "approve":
        raise ValueError("Pass B packet does not approve certification")
    if not packet.reviewer_id or not packet.reviewer_key_id or not packet.reviewer_signature:
        raise ValueError("Pass B packet requires an identified signed reviewer decision")
    message = packet.signed_payload().decode()
    if not signature_verifier(message, packet.reviewer_signature, packet.reviewer_key_id):
        raise ValueError("Pass B reviewer signature verification failed")
    if not isfinite(packet.reviewed_at.timestamp()):
        raise ValueError("Pass B review time is invalid")
    return True
