"""Source-aware reconciliation at mesa and administrative hierarchy grains."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlsplit


class Completeness(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"
    DUPLICATED = "duplicated"
    AMBIGUOUS = "ambiguous"


class CheckStatus(StrEnum):
    """Every declared check has an explicit result; missing fields are not passes."""

    PASS = "pass"  # noqa: S105 - status token, not a credential
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class ExplanationStatus(StrEnum):
    """Research conclusion, deliberately independent from anomaly detection."""

    EXPLAINED = "explained"
    PARTIALLY_EXPLAINED = "partially_explained"
    NO_EXPLANATION_FOUND = "no_explanation_found_in_available_data"
    NON_EVALUABLE = "non_evaluable"


class ComparisonStatus(StrEnum):
    EVALUABLE = "evaluable"
    NOT_EVALUABLE = "not_evaluable"


HIERARCHY = ("mesa", "place", "municipality", "department", "national")
METHODOLOGY_VERSION = "reconciliation-v2.0.0"
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, order=True)
class MesaIdentity:
    """Canonical identity; all components are required to prevent false joins."""

    department: str
    municipality: str
    place: str
    mesa: str


@dataclass(frozen=True)
class MesaRecord:
    source: str
    identity: MesaIdentity
    values: Mapping[str, int]
    registered: int | None = None
    source_url: str | None = None
    observed_at: str | None = None
    retrieved_at: str | None = None
    release_id: str | None = None
    election_slug: str | None = None
    data_version: str | None = None
    source_type: str | None = None
    legal_status: str | None = None
    content_hash: str | None = None
    parser_version: str | None = None
    transform_version: str | None = None
    published_grain: str = "mesa"
    field_states: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        for name, value in self.values.items():
            _nonnegative_integer(name, value)
        if self.registered is not None:
            _nonnegative_integer("registered", self.registered)
        if self.published_grain not in HIERARCHY:
            raise ValueError("published_grain is invalid")
        if self.field_states is not None:
            copied_states = dict(self.field_states)
            expected_fields = set(self.values)
            if self.registered is not None:
                expected_fields.add("registered")
            if set(copied_states) != expected_fields or any(
                state != "observed" for state in copied_states.values()
            ):
                raise ValueError("field_states must classify exactly the published fields")
            object.__setattr__(self, "field_states", copied_states)


@dataclass(frozen=True)
class ArithmeticRule:
    """A source-local accounting identity.

    ``left_fields`` must sum to ``right_field``.  Rules are never applied
    across sources because publication formats can legitimately differ.
    """

    source: str
    left_fields: tuple[str, ...]
    right_field: str


@dataclass(frozen=True)
class ArithmeticIssue:
    identity: MesaIdentity
    source: str
    rule: ArithmeticRule
    observed_left: int
    observed_right: int
    source_url: str | None


@dataclass(frozen=True)
class ArithmeticCheck:
    """One declared arithmetic rule evaluated against one source record."""

    identity: MesaIdentity
    source: str
    rule: ArithmeticRule
    status: CheckStatus
    observed_left: int | None
    observed_right: int | None
    reason: str | None
    source_url: str | None


@dataclass(frozen=True)
class ElectorBoundRule:
    """Apply a voter/elector bound only to a source that publishes both fields."""

    source: str
    voters_field: str


@dataclass(frozen=True)
class ElectorBoundIssue:
    identity: MesaIdentity
    source: str
    voters: int
    registered: int
    source_url: str | None


@dataclass(frozen=True)
class Aggregate:
    level: str
    key: tuple[str, ...]
    source: str
    values: Mapping[str, int]
    registered_observed: int | None
    mesas: int
    unavailable_fields: tuple[str, ...] = ()
    release_id: str | None = None
    election_slug: str | None = None
    data_version: str | None = None
    source_type: str | None = None
    legal_status: str | None = None
    source_content_hashes: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    published_grain: str = "mesa"


@dataclass(frozen=True)
class Comparison:
    level: str
    key: tuple[str, ...]
    field: str
    left_source: str
    right_source: str
    left_value: int
    right_value: int
    signed_difference: int
    minimum_ballot_edits: int | None
    minimum_ballot_edits_status: ComparisonStatus
    non_evaluable_reason: str | None = None
    # Compatibility projection for old immutable artifacts only.  New consumers
    # must use ``minimum_ballot_edits`` and its status, never this field.
    affected_votes_estimate: int | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    arithmetic_issues: tuple[ArithmeticIssue, ...]
    elector_bound_issues: tuple[ElectorBoundIssue, ...]
    duplicate_identities: Mapping[str, tuple[MesaIdentity, ...]]
    conflicting_identities: Mapping[str, tuple[MesaIdentity, ...]]
    completeness: Mapping[MesaIdentity, Completeness]
    completeness_by_source: Mapping[str, Mapping[MesaIdentity, Completeness]]
    aggregates: tuple[Aggregate, ...]
    comparisons: tuple[Comparison, ...]
    arithmetic_checks: tuple[ArithmeticCheck, ...] = ()
    release_id: str | None = None
    election_slug: str | None = None
    data_version: str | None = None
    source_provenance: Mapping[str, Mapping[str, object]] | None = None
    output_hash: str = ""
    methodology_version: str = METHODOLOGY_VERSION

    def artifact_payload(self) -> dict[str, object]:
        payload = _artifact_value(self)
        assert isinstance(payload, dict)
        payload.pop("output_hash")
        return payload

    def with_hash(self) -> ReconciliationResult:
        return replace(self, output_hash=_hash(self.artifact_payload()))


def _artifact_value(value: object) -> object:
    """Convert dataclass-keyed completeness maps into canonical JSON values."""
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {field.name: _artifact_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return [
            {"key": _artifact_value(key), "value": _artifact_value(item)}
            for key, item in sorted(
                value.items(), key=lambda pair: _canonical_json(_artifact_value(pair[0]))
            )
        ]
    if isinstance(value, tuple | list):
        return [_artifact_value(item) for item in value]
    return value


def _nonnegative_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def validate_source_arithmetic(
    records: Iterable[MesaRecord], rules: Iterable[ArithmeticRule]
) -> tuple[ArithmeticIssue, ...]:
    """Validate only the accounting identities declared for each source."""
    rules_by_source: dict[str, list[ArithmeticRule]] = defaultdict(list)
    for rule in rules:
        rules_by_source[rule.source].append(rule)
    issues: list[ArithmeticIssue] = []
    for record in records:
        for rule in rules_by_source[record.source]:
            if any(name not in record.values for name in (*rule.left_fields, rule.right_field)):
                continue
            left = sum(record.values[name] for name in rule.left_fields)
            right = record.values[rule.right_field]
            if left != right:
                issues.append(
                    ArithmeticIssue(
                        record.identity,
                        record.source,
                        rule,
                        left,
                        right,
                        record.source_url,
                    )
                )
    return tuple(
        sorted(issues, key=lambda issue: (issue.source, issue.identity, issue.rule.right_field))
    )


def evaluate_source_arithmetic(
    records: Iterable[MesaRecord], rules: Iterable[ArithmeticRule]
) -> tuple[ArithmeticCheck, ...]:
    """Evaluate all declared accounting checks as pass/fail/not-evaluable.

    A source that does not publish a required field is a *not evaluable* check,
    not an implicit pass and not an inferred zero.  ``validate_source_arithmetic``
    remains as a compact backwards-compatible view containing only failures.
    """
    rules_by_source: dict[str, list[ArithmeticRule]] = defaultdict(list)
    for rule in rules:
        rules_by_source[rule.source].append(rule)
    checks: list[ArithmeticCheck] = []
    for record in records:
        for rule in rules_by_source[record.source]:
            required = (*rule.left_fields, rule.right_field)
            missing = tuple(name for name in required if name not in record.values)
            if missing:
                checks.append(
                    ArithmeticCheck(
                        record.identity,
                        record.source,
                        rule,
                        CheckStatus.NOT_EVALUABLE,
                        None,
                        None,
                        "missing_published_fields:" + ",".join(missing),
                        record.source_url,
                    )
                )
                continue
            left = sum(record.values[name] for name in rule.left_fields)
            right = record.values[rule.right_field]
            checks.append(
                ArithmeticCheck(
                    record.identity,
                    record.source,
                    rule,
                    CheckStatus.PASS if left == right else CheckStatus.FAIL,
                    left,
                    right,
                    None if left == right else "accounting_identity_failed",
                    record.source_url,
                )
            )
    return tuple(
        sorted(checks, key=lambda item: (item.source, item.identity, item.rule.right_field))
    )


def validate_elector_bounds(
    records: Iterable[MesaRecord], rules: Iterable[ElectorBoundRule]
) -> tuple[ElectorBoundIssue, ...]:
    """Check voters <= registered only where the source publishes registered electors."""
    rules_by_source = {rule.source: rule for rule in rules}
    issues: list[ElectorBoundIssue] = []
    for record in records:
        rule = rules_by_source.get(record.source)
        if rule is None or record.registered is None:
            continue
        voters = record.values.get(rule.voters_field)
        if voters is not None and voters > record.registered:
            issues.append(
                ElectorBoundIssue(
                    record.identity,
                    record.source,
                    voters,
                    record.registered,
                    record.source_url,
                )
            )
    return tuple(sorted(issues, key=lambda issue: (issue.source, issue.identity)))


def identity_conflicts(
    records: Iterable[MesaRecord],
) -> tuple[dict[str, tuple[MesaIdentity, ...]], dict[str, tuple[MesaIdentity, ...]]]:
    """Return duplicate and contradictory canonical identities per source."""
    grouped: dict[tuple[str, MesaIdentity], list[MesaRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.source, record.identity)].append(record)
    duplicates: dict[str, list[MesaIdentity]] = defaultdict(list)
    conflicts: dict[str, list[MesaIdentity]] = defaultdict(list)
    for (source, identity), rows in grouped.items():
        if len(rows) > 1:
            duplicates[source].append(identity)
            fingerprints = {(tuple(sorted(row.values.items())), row.registered) for row in rows}
            if len(fingerprints) > 1:
                conflicts[source].append(identity)
    return (
        {source: tuple(sorted(ids)) for source, ids in sorted(duplicates.items())},
        {source: tuple(sorted(ids)) for source, ids in sorted(conflicts.items())},
    )


def classify_completeness(
    expected: Iterable[MesaIdentity], records: Iterable[MesaRecord]
) -> dict[MesaIdentity, Completeness]:
    """Classify expected official-document coverage without inferring absence."""
    by_identity: dict[MesaIdentity, list[MesaRecord]] = defaultdict(list)
    for record in records:
        by_identity[record.identity].append(record)
    outcome: dict[MesaIdentity, Completeness] = {}
    for identity in sorted(set(expected)):
        rows = by_identity.get(identity, [])
        if not rows:
            outcome[identity] = Completeness.MISSING
        elif len(rows) > 1:
            fingerprints = {(tuple(sorted(row.values.items())), row.registered) for row in rows}
            outcome[identity] = (
                Completeness.AMBIGUOUS if len(fingerprints) > 1 else Completeness.DUPLICATED
            )
        else:
            outcome[identity] = Completeness.COMPLETE
    return outcome


def classify_completeness_by_source(
    expected_by_source: Mapping[str, Iterable[MesaIdentity]],
    records: Iterable[MesaRecord],
) -> dict[str, dict[MesaIdentity, Completeness]]:
    """Keep coverage independent for every official source layer."""
    rows_by_source: dict[str, list[MesaRecord]] = defaultdict(list)
    for record in records:
        rows_by_source[record.source].append(record)
    return {
        source: classify_completeness(expected, rows_by_source.get(source, ()))
        for source, expected in sorted(expected_by_source.items())
    }


def _key(identity: MesaIdentity, level: str) -> tuple[str, ...]:
    if level not in HIERARCHY:
        raise ValueError(f"unknown level: {level}")
    if level == "mesa":
        return (identity.department, identity.municipality, identity.place, identity.mesa)
    if level == "place":
        return (identity.department, identity.municipality, identity.place)
    if level == "municipality":
        return (identity.department, identity.municipality)
    if level == "department":
        return (identity.department,)
    return ("CO",)


def _assert_exact_identity_coverage(
    records: tuple[MesaRecord, ...], expected_by_source: Mapping[str, Iterable[MesaIdentity]]
) -> None:
    """Require an exact, unique, complete identity universe before a roll-up.

    This is intentionally a release-builder gate.  Callers using the historic
    standalone helper can omit ``expected_by_source`` while immutable public
    reconciliation always supplies it through ``reconcile``.
    """
    sources = {record.source for record in records}
    if set(expected_by_source) != sources:
        raise ValueError("aggregate identity gate requires expected identities for every source")
    for source in sorted(sources):
        expected_rows = tuple(expected_by_source[source])
        expected_set = set(expected_rows)
        if len(expected_rows) != len(expected_set):
            raise ValueError("aggregate identity gate requires unique expected identities")
        observed = tuple(record for record in records if record.source == source)
        coverage = classify_completeness(expected_rows, observed)
        if any(status is not Completeness.COMPLETE for status in coverage.values()):
            raise ValueError("aggregate identity gate requires complete expected identities")
        if {record.identity for record in observed} != expected_set:
            raise ValueError("aggregate identity gate requires an exact expected identity universe")


def aggregate_hierarchy(
    records: Iterable[MesaRecord],
    *,
    expected_by_source: Mapping[str, Iterable[MesaIdentity]] | None = None,
) -> tuple[Aggregate, ...]:
    """Aggregate mesas exactly upward; an observed elector bound is preserved only when known."""
    records_list = list(records)
    if any(record.published_grain != "mesa" for record in records_list):
        raise ValueError("MesaRecord aggregation requires records published at mesa grain")
    duplicates, _ = identity_conflicts(records_list)
    if duplicates:
        raise ValueError("cannot aggregate duplicate mesa identities; reconcile them first")
    if expected_by_source is not None:
        _assert_exact_identity_coverage(tuple(records_list), expected_by_source)
    totals: dict[tuple[str, str, tuple[str, ...]], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    field_counts: dict[tuple[str, str, tuple[str, ...]], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    mesas: dict[tuple[str, str, tuple[str, ...]], int] = defaultdict(int)
    registered: dict[tuple[str, str, tuple[str, ...]], int] = defaultdict(int)
    complete_registered: dict[tuple[str, str, tuple[str, ...]], bool] = defaultdict(lambda: True)
    for record in records_list:
        for level in HIERARCHY:
            composite = (record.source, level, _key(record.identity, level))
            mesas[composite] += 1
            for field, value in record.values.items():
                totals[composite][field] += value
                field_counts[composite][field] += 1
            if record.registered is None:
                complete_registered[composite] = False
            else:
                registered[composite] += record.registered
    return tuple(
        Aggregate(
            level=level,
            key=key,
            source=source,
            values={
                field: value
                for field, value in sorted(totals[composite].items())
                if field_counts[composite][field] == mesas[composite]
            },
            registered_observed=registered[composite] if complete_registered[composite] else None,
            mesas=mesas[composite],
            unavailable_fields=tuple(
                field
                for field in sorted(totals[composite])
                if field_counts[composite][field] != mesas[composite]
            ),
            release_id=_source_metadata(records_list, source, "release_id"),
            election_slug=_source_metadata(records_list, source, "election_slug"),
            data_version=_source_metadata(records_list, source, "data_version"),
            source_type=_source_metadata(records_list, source, "source_type"),
            legal_status=_source_metadata(records_list, source, "legal_status"),
            source_content_hashes=tuple(
                sorted(
                    row.content_hash
                    for row in records_list
                    if row.source == source and row.content_hash is not None
                )
            ),
            source_urls=tuple(
                sorted(
                    {
                        row.source_url
                        for row in records_list
                        if row.source == source and row.source_url is not None
                    }
                )
            ),
            published_grain=_source_metadata(records_list, source, "published_grain") or "mesa",
        )
        for composite in sorted(totals)
        for source, level, key in [composite]
    )


def _source_metadata(records: Iterable[MesaRecord], source: str, field: str) -> str | None:
    values = {getattr(record, field) for record in records if record.source == source}
    value = next(iter(values)) if len(values) == 1 else None
    return value if isinstance(value, str) else None


def _validated_provenance(
    rows: tuple[MesaRecord, ...],
) -> tuple[str, str, str, dict[str, dict[str, object]]]:
    if not rows:
        raise ValueError("authenticated reconciliation requires at least one mesa record")
    provenance: dict[str, dict[str, object]] = {}
    release_ids: set[str] = set()
    elections: set[str] = set()
    versions: set[str] = set()
    for source in sorted({row.source for row in rows}):
        source_rows = [row for row in rows if row.source == source]
        fields = (
            "release_id",
            "election_slug",
            "data_version",
            "source_type",
            "legal_status",
            "published_grain",
            "parser_version",
            "transform_version",
        )
        values = {field: {getattr(row, field) for row in source_rows} for field in fields}
        if any(len(value) != 1 or next(iter(value)) in {None, ""} for value in values.values()):
            raise ValueError("source provenance must be homogeneous and complete")
        if next(iter(values["published_grain"])) != "mesa":
            raise ValueError(
                "authenticated MesaRecord reconciliation requires published_grain='mesa'"
            )
        source_type = next(iter(values["source_type"]))
        legal_status = next(iter(values["legal_status"]))
        if (
            source_type not in _SOURCE_LEGAL_STATUS
            or legal_status != _SOURCE_LEGAL_STATUS[source_type]
        ):
            raise ValueError("source provenance has incompatible source_type/legal_status")
        if any(not _is_sha256(row.content_hash) for row in source_rows):
            raise ValueError("authenticated reconciliation requires content-addressed records")
        if any(
            row.field_states is None
            or not _is_https_url(row.source_url)
            or not _is_timezone_aware(row.retrieved_at)
            for row in source_rows
        ):
            raise ValueError(
                "authenticated reconciliation requires field states, HTTPS source URLs, "
                "and timezone-aware retrieval times"
            )
        release_ids.add(next(iter(values["release_id"])))
        elections.add(next(iter(values["election_slug"])))
        versions.add(next(iter(values["data_version"])))
        provenance[source] = {field: next(iter(value)) for field, value in values.items()}
        provenance[source]["content_hashes"] = tuple(
            sorted(row.content_hash for row in source_rows if isinstance(row.content_hash, str))
        )
        provenance[source]["source_urls"] = tuple(
            sorted({row.source_url for row in source_rows if row.source_url is not None})
        )
        provenance[source]["retrievals"] = tuple(
            {
                "content_hash": row.content_hash,
                "retrieved_at": row.retrieved_at,
                "source_url": row.source_url,
            }
            for row in sorted(
                source_rows, key=lambda item: (item.content_hash or "", item.retrieved_at or "")
            )
        )
    if len(release_ids) != 1 or len(elections) != 1 or len(versions) != 1:
        raise ValueError("reconciliation sources must share release, election, and data version")
    return next(iter(release_ids)), next(iter(elections)), next(iter(versions)), provenance


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _is_timezone_aware(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def compare_aggregates(
    aggregates: Iterable[Aggregate],
    left_source: str,
    right_source: str,
    field: str,
    level: str,
    *,
    ballot_categories: tuple[str, ...] | None = None,
) -> tuple[Comparison, ...]:
    """Compare matching grains and, when possible, a complete ballot vector.

    ``minimum_ballot_edits`` is the lower bound ``A_min=max(P,N)`` where P/N
    are positive/negative sums over mutually-exclusive, complete ballot
    categories.  A single field difference is retained only as a legacy
    projection and is never used as this bound or as outcome uncertainty.
    """
    if level not in HIERARCHY:
        raise ValueError(f"unknown level: {level}")
    index = {(item.source, item.level, item.key): item for item in aggregates}
    left_keys = {
        key for source, item_level, key in index if source == left_source and item_level == level
    }
    right_keys = {
        key for source, item_level, key in index if source == right_source and item_level == level
    }
    comparisons: list[Comparison] = []
    for key in sorted(left_keys & right_keys):
        left_values = index[(left_source, level, key)].values
        right_values = index[(right_source, level, key)].values
        if field not in left_values or field not in right_values:
            continue
        left = left_values[field]
        right = right_values[field]
        difference = left - right
        lower_bound: int | None = None
        status = ComparisonStatus.NOT_EVALUABLE
        reason: str | None = "complete_mutually_exclusive_ballot_categories_not_declared"
        if ballot_categories is not None:
            if not ballot_categories or len(set(ballot_categories)) != len(ballot_categories):
                raise ValueError("ballot categories must be non-empty and unique")
            left_categories = set(left_values)
            right_categories = set(right_values)
            declared = set(ballot_categories)
            if not declared <= left_categories or not declared <= right_categories:
                reason = "incompatible_or_unpublished_ballot_categories"
            elif left_categories != right_categories:
                reason = "incompatible_category_sets"
            else:
                deltas = [
                    left_values[category] - right_values[category] for category in ballot_categories
                ]
                positive = sum(delta for delta in deltas if delta > 0)
                negative = sum(-delta for delta in deltas if delta < 0)
                lower_bound = max(positive, negative)
                status = ComparisonStatus.EVALUABLE
                reason = None
        comparisons.append(
            Comparison(
                level,
                key,
                field,
                left_source,
                right_source,
                left,
                right,
                difference,
                lower_bound,
                status,
                reason,
                # Compatibility only.  This does not represent a ballot-edit
                # bound without an explicit complete category vector.
                abs(difference),
            )
        )
    return tuple(comparisons)


def classify_official_correction(
    previous: MesaRecord, current: MesaRecord, *, official_correction_marker: bool
) -> str:
    """Classify a revision without treating all source disagreement as a correction."""
    if previous.identity != current.identity:
        return "incompatible_identity"
    if previous.source != current.source:
        return "cross_source_difference"
    if previous.values == current.values and previous.registered == current.registered:
        return "unchanged"
    return "official_correction" if official_correction_marker else "unmarked_revision"


def reconcile(
    records: Iterable[MesaRecord],
    *,
    expected_identities: Iterable[MesaIdentity] = (),
    expected_by_source: Mapping[str, Iterable[MesaIdentity]] | None = None,
    arithmetic_rules: Iterable[ArithmeticRule] = (),
    elector_bound_rules: Iterable[ElectorBoundRule] = (),
    compare: tuple[str, str, str, str] | None = None,
) -> ReconciliationResult:
    """Run deterministic validation, aggregation and (optionally) compatible-grain comparison."""
    rows = tuple(records)
    release_id, election_slug, data_version, provenance = _validated_provenance(rows)
    arithmetic_rules = tuple(arithmetic_rules)
    arithmetic = validate_source_arithmetic(rows, arithmetic_rules)
    arithmetic_checks = evaluate_source_arithmetic(rows, arithmetic_rules)
    elector_bounds = validate_elector_bounds(rows, elector_bound_rules)
    duplicates, conflicts = identity_conflicts(rows)
    legacy_expected = tuple(expected_identities)
    if legacy_expected and len({row.source for row in rows}) > 1:
        raise ValueError(
            "mixed-source completeness requires expected_by_source to prevent layer coercion"
        )
    completeness = classify_completeness(legacy_expected, rows)
    completeness_by_source = classify_completeness_by_source(expected_by_source or {}, rows)
    aggregate_expected = expected_by_source
    if aggregate_expected is None and legacy_expected and len({row.source for row in rows}) == 1:
        aggregate_expected = {rows[0].source: legacy_expected}
    aggregates = (
        aggregate_hierarchy(rows, expected_by_source=aggregate_expected)
        if not duplicates and aggregate_expected is not None
        else ()
    )
    comparisons = compare_aggregates(aggregates, *compare) if compare and aggregates else ()
    return ReconciliationResult(
        arithmetic_issues=arithmetic,
        elector_bound_issues=elector_bounds,
        duplicate_identities=duplicates,
        conflicting_identities=conflicts,
        completeness=completeness,
        completeness_by_source=completeness_by_source,
        aggregates=aggregates,
        comparisons=comparisons,
        arithmetic_checks=arithmetic_checks,
        release_id=release_id,
        election_slug=election_slug,
        data_version=data_version,
        source_provenance=provenance,
    ).with_hash()
