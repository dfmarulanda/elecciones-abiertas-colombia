"""Deterministic materialization of the API's immutable release snapshot.

This module is deliberately a pure boundary: it accepts JSON-shaped release
records and performs no network, filesystem, or database work.  In particular,
it cannot infer that values transcribed from a documentary source were human
verified.  Such totals require an explicit :class:`DocumentaryTotalsAttestation`
bound to the exact values exposed by the snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast
from urllib.parse import urlsplit

from elecciones_pipeline.analytics.peer_signals import CODE_HASH as PEER_CODE_HASH
from elecciones_pipeline.analytics.peer_signals import METHOD_HASH as PEER_METHOD_HASH
from elecciones_pipeline.analytics.priority import DISCLOSURE_EN, DISCLOSURE_ES
from elecciones_pipeline.analytics.spatial import CODE_HASH as SPATIAL_CODE_HASH
from elecciones_pipeline.analytics.spatial import METHOD_HASH as SPATIAL_METHOD_HASH
from elecciones_pipeline.quality.release import validate_manifest


class SnapshotError(ValueError):
    """The supplied records cannot safely become a public API snapshot."""


_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
    "contextual_baseline": "context_only",
}
_METRIC_FIELDS = (
    "registered_electors",
    "voters",
    "valid_votes",
    "blank_votes",
    "null_votes",
    "unmarked_votes",
)
_METRIC_STATUSES = {"observed", "unknown", "unavailable", "not_applicable"}
_GEOGRAPHY_LEVELS = {
    "national": 0,
    "department": 1,
    "municipality": 2,
    "zone": 3,
    "polling_place": 4,
    "mesa": 5,
}
_PROVENANCE_FIELDS = {
    "data_version",
    "source_type",
    "legal_status",
    "source_url",
    "retrieved_at",
    "content_hash",
    "parser_version",
    "transform_version",
    "methodology_version",
}
_ROOT_FIELDS = {
    "release",
    "election",
    "summary",
    "geographies",
    "mesas",
    "results",
    "evidence",
    # Retained as an empty compatibility field.  E-14 references have no
    # handling/caching workflow under the index-only policy.
    "evidence_handling",
    "comparisons",
    "bulletins",
    "review_signals",
    "datasets",
    "provenance",
}
_DOCUMENTARY_SOURCE_TYPES = {
    "final_declaration",
    "scrutiny",
    "e14_delegate",
    "e14_transmission",
}
_COMPONENT_POINTS = {
    "verified_accounting_failure": 100,
    "conflicting_official_records": 100,
    "documentary_difference_major": 70,
    "documentary_difference_minor": 45,
    "document_missing_duplicated_ambiguous": 25,
    "peer_distribution": 10,
    "spatial_cluster": 10,
}
_STATISTICAL_COMPONENTS = {"peer_distribution", "spatial_cluster"}
_ANALYTICS_ELECTIONS = {
    "presidencia-2026-r2",
    "presidencia-2026-segunda-vuelta",
}


def _analyzer_hashes() -> dict[str, tuple[str, str]]:
    """Bind snapshot validation to the installed analyzer implementations.

    These values are imported from the analyzer modules at validation time,
    rather than copied as labels into the publication boundary.
    """
    return {
        "peer_distribution": (PEER_CODE_HASH, PEER_METHOD_HASH),
        "spatial_cluster": (SPATIAL_CODE_HASH, SPATIAL_METHOD_HASH),
    }


_STATISTICAL_BINDING_FIELDS = {
    "analyzer_output_hash",
    "family_id",
    "expected_family_count",
    "expected_family_digest",
    "cohort_hash",
    "input_artifact_hash",
    "code_hash",
    "method_hash",
    "p_value",
    "q_value",
    "family_rank",
    "family_size",
    "adjustment_method",
}
_OPTIONAL_ANALYZER_BINDING_FIELDS = {
    "analyzer_mesa_id",
    "analysis_unit_id",
    "peer_residual_artifact_hash",
    "peer_methodology_version",
    "coordinate_source_url",
    "coordinate_source_hash",
    "coordinate_accuracy_m",
    "coordinate_grain",
    "expected_mesa_count",
    "expected_mesa_digest",
    "expected_mesa_membership_digest",
    "randomization_seed",
    "spatial_permutations",
    "spatial_neighbors",
    "spatial_signal_kind",
    "spatial_local_residual",
    "analysis_unit_digest",
    "mesa_membership_digest",
    "neighbors",
    "signal_kind",
    "local_statistic",
    "local_residual",
    "permutations",
}
_SPATIAL_REPLAY_FIELDS = {
    "analysis_unit_id",
    "peer_residual_artifact_hash",
    "peer_methodology_version",
    "coordinate_source_url",
    "coordinate_source_hash",
    "coordinate_accuracy_m",
    "coordinate_grain",
    "randomization_seed",
    "spatial_permutations",
    "spatial_neighbors",
    "spatial_signal_kind",
    "spatial_local_residual",
    "analysis_unit_digest",
    "expected_mesa_count",
    "expected_mesa_digest",
    "mesa_membership_digest",
    "expected_mesa_membership_digest",
    "neighbors",
    "signal_kind",
    "local_statistic",
    "local_residual",
    "permutations",
}
_SPATIAL_PROVENANCE_FIELDS = {
    "analysis_unit_id",
    "peer_residual_artifact_hash",
    "peer_methodology_version",
    "coordinate_source_url",
    "coordinate_source_hash",
    "coordinate_accuracy_m",
    "coordinate_grain",
    "expected_mesa_count",
    "expected_mesa_digest",
    "expected_mesa_membership_digest",
}
# Official percentages are commonly published to two decimal percentage points.
# Keep their reported value while rejecting inconsistencies beyond that precision.
_RATE_TOLERANCE = 0.0001


@dataclass(frozen=True)
class DocumentaryTotalsAttestation:
    """Two-human attestation bound to one immutable documentary source.

    Reviewer identifiers are internal audit metadata.  They are validated here
    but intentionally omitted from :class:`ApiSnapshotArtifact` so the public
    API cannot disclose reviewer identity.
    """

    source_content_hash: str
    values_digest: str
    reviewer_ids: tuple[str, str]
    verified_at: datetime

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.source_content_hash):
            raise SnapshotError("documentary attestation needs a SHA-256 source_content_hash")
        if not _SHA256.fullmatch(self.values_digest):
            raise SnapshotError("documentary attestation needs a SHA-256 values_digest")
        if (
            len(self.reviewer_ids) != 2
            or any(not isinstance(value, str) or not value.strip() for value in self.reviewer_ids)
            or self.reviewer_ids[0].strip() == self.reviewer_ids[1].strip()
        ):
            raise SnapshotError("documentary totals require two distinct human reviewers")
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise SnapshotError("documentary attestation verified_at must be timezone-aware")


@dataclass(frozen=True)
class ApiSnapshotArtifact:
    """A detached API snapshot plus its canonical bytes and content digest."""

    snapshot: dict[str, Any]
    canonical_bytes: bytes
    sha256: str

    def manifest_value(self) -> dict[str, Any]:
        """Return a detached value safe to attach as ``manifest.api_snapshot``."""
        return deepcopy(self.snapshot)


def canonical_snapshot_bytes(snapshot: Mapping[str, Any]) -> bytes:
    """Encode a snapshot identically regardless of input mapping order."""
    try:
        encoded = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotError("api_snapshot must contain only finite JSON values") from exc
    return encoded.encode("utf-8")


def _json_clone(value: Any, label: str) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"{label} must contain only finite JSON values") from exc


def _object(
    value: object,
    *,
    label: str,
    fields: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotError(f"{label} must be an object")
    keys = set(value)
    missing = fields - optional - keys
    unexpected = keys - fields
    if missing:
        raise SnapshotError(f"{label} is missing fields: {sorted(missing)!r}")
    if unexpected:
        raise SnapshotError(f"{label} has unexpected fields: {sorted(unexpected)!r}")
    return cast(dict[str, Any], _json_clone(dict(value), label))


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotError(f"{label} must be a non-empty string")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SnapshotError(f"{label} must be a non-negative integer")
    return value


def _finite_number(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SnapshotError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise SnapshotError(f"{label} must be between {minimum} and {maximum}")
    return number


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SnapshotError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _https_url(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SnapshotError(f"{label} must be an absolute HTTPS URL")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise SnapshotError(f"{label} must be an absolute HTTPS URL without user info")
    return value


def _timestamp(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SnapshotError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotError(f"{label} must include a timezone")
    return value


def _localized(value: object, label: str) -> dict[str, str]:
    item = _object(value, label=label, fields={"es", "en"})
    _nonempty_string(item["es"], f"{label}.es")
    _nonempty_string(item["en"], f"{label}.en")
    return cast(dict[str, str], item)


def _metric(value: object, label: str) -> dict[str, Any]:
    item = _object(value, label=label, fields={"value", "status"})
    status = item["status"]
    if status not in _METRIC_STATUSES:
        raise SnapshotError(f"{label}.status is invalid")
    if status == "observed":
        _nonnegative_int(item["value"], f"{label}.value")
    elif item["value"] is not None:
        raise SnapshotError(f"{label} must preserve non-observed values as null")
    return item


def _validate_provenance(
    value: object,
    *,
    label: str,
    data_version: str,
    parser_versions: frozenset[str],
) -> dict[str, Any]:
    item = _object(value, label=label, fields=_PROVENANCE_FIELDS)
    if item["data_version"] != data_version:
        raise SnapshotError(f"{label}.data_version does not match the release")
    source_type = item["source_type"]
    if source_type not in _SOURCE_LEGAL_STATUS:
        raise SnapshotError(f"{label}.source_type is invalid")
    if item["legal_status"] != _SOURCE_LEGAL_STATUS[source_type]:
        raise SnapshotError(f"{label} has an incompatible source_type/legal_status")
    _https_url(item["source_url"], f"{label}.source_url")
    _timestamp(item["retrieved_at"], f"{label}.retrieved_at")
    _sha256(item["content_hash"], f"{label}.content_hash")
    parser_version = _nonempty_string(item["parser_version"], f"{label}.parser_version")
    if parser_version not in parser_versions:
        raise SnapshotError(f"{label}.parser_version is absent from the release manifest")
    _nonempty_string(item["transform_version"], f"{label}.transform_version")
    if item["methodology_version"] is not None:
        _nonempty_string(item["methodology_version"], f"{label}.methodology_version")
    return item


def _candidate(value: object, label: str) -> dict[str, Any]:
    item = _object(
        value,
        label=label,
        fields={"id", "ballot_number", "name", "short_name"},
    )
    _nonempty_string(item["id"], f"{label}.id")
    ballot = item["ballot_number"]
    if ballot is not None and (type(ballot) is not int or ballot < 1):
        raise SnapshotError(f"{label}.ballot_number must be null or a positive integer")
    item["name"] = _localized(item["name"], f"{label}.name")
    item["short_name"] = _localized(item["short_name"], f"{label}.short_name")
    return item


def _candidate_sort_key(item: Mapping[str, Any]) -> tuple[bool, int, str]:
    ballot = item["ballot_number"]
    return ballot is None, ballot if isinstance(ballot, int) else 0, str(item["id"])


def _result_candidate(value: object, label: str, candidate_ids: frozenset[str]) -> dict[str, Any]:
    item = _object(value, label=label, fields={"candidate_id", "votes"})
    candidate_id = _nonempty_string(item["candidate_id"], f"{label}.candidate_id")
    if candidate_id not in candidate_ids:
        raise SnapshotError(f"{label} refers to an unknown candidate")
    item["votes"] = _metric(item["votes"], f"{label}.votes")
    return item


def _candidate_result_list(
    value: object, label: str, candidate_ids: frozenset[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError(f"{label} must be a list")
    items = [
        _result_candidate(item, f"{label}[{index}]", candidate_ids)
        for index, item in enumerate(value)
    ]
    identifiers = [item["candidate_id"] for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise SnapshotError(f"{label} contains duplicate candidates")
    if set(identifiers) != set(candidate_ids):
        raise SnapshotError(f"{label} must preserve an explicit metric for every candidate")
    return sorted(items, key=lambda item: str(item["candidate_id"]))


def _observed_metric_value(item: Mapping[str, Any], field: str) -> int | None:
    metric = item[field]
    if isinstance(metric, Mapping) and metric.get("status") == "observed":
        value = metric.get("value")
        if type(value) is int:
            return value
    return None


def _validate_result_arithmetic(
    item: Mapping[str, Any],
    label: str,
    *,
    legacy_fixture_accounting: bool,
) -> None:
    """Apply Colombian result identities only when every operand is observed.

    Registraduria's ``votval`` total includes blank ballots.  The immutable
    synthetic v1 fixture predates that normalization rule, so fixture releases
    retain their historical accounting without weakening candidate or published
    releases.
    """
    registered = _observed_metric_value(item, "registered_electors")
    voters = _observed_metric_value(item, "voters")
    valid = _observed_metric_value(item, "valid_votes")
    blank = _observed_metric_value(item, "blank_votes")
    null = _observed_metric_value(item, "null_votes")
    unmarked = _observed_metric_value(item, "unmarked_votes")
    if registered is not None and voters is not None and voters > registered:
        raise SnapshotError(f"{label} has voters greater than registered electors")
    if voters is not None and valid is not None and valid > voters:
        raise SnapshotError(f"{label} has valid votes greater than voters")
    candidate_values = [
        candidate["votes"]["value"]
        for candidate in item["candidates"]
        if candidate["votes"]["status"] == "observed"
    ]
    if valid is not None and len(candidate_values) == len(item["candidates"]):
        candidate_total = sum(candidate_values)
        if legacy_fixture_accounting:
            if candidate_total != valid:
                raise SnapshotError(f"{label} candidate votes do not equal valid votes")
        elif blank is not None and candidate_total + blank != valid:
            raise SnapshotError(f"{label} candidate and blank votes do not equal valid votes")
    categories = (
        (valid, blank, null, unmarked) if legacy_fixture_accounting else (valid, null, unmarked)
    )
    if (
        voters is not None
        and all(value is not None for value in categories)
        and sum(cast(int, value) for value in categories) != voters
    ):
        raise SnapshotError(f"{label} vote categories do not equal voters")


def _validate_election(value: object, manifest: Mapping[str, Any]) -> dict[str, Any]:
    item = _object(
        value,
        label="election",
        fields={"slug", "name", "round", "election_date", "candidates"},
    )
    if item["slug"] != manifest["election_slug"]:
        raise SnapshotError("election.slug does not match manifest.election_slug")
    item["name"] = _localized(item["name"], "election.name")
    if type(item["round"]) is not int or item["round"] < 1:
        raise SnapshotError("election.round must be a positive integer")
    try:
        date.fromisoformat(_nonempty_string(item["election_date"], "election.election_date"))
    except ValueError as exc:
        raise SnapshotError("election.election_date must be an ISO date") from exc
    if not isinstance(item["candidates"], list) or not item["candidates"]:
        raise SnapshotError("election.candidates must be a non-empty list")
    candidates = [
        _candidate(candidate, f"election.candidates[{index}]")
        for index, candidate in enumerate(item["candidates"])
    ]
    identifiers = [candidate["id"] for candidate in candidates]
    ballot_numbers = [
        candidate["ballot_number"]
        for candidate in candidates
        if candidate["ballot_number"] is not None
    ]
    if len(set(identifiers)) != len(identifiers):
        raise SnapshotError("election.candidates contains duplicate ids")
    if len(set(ballot_numbers)) != len(ballot_numbers):
        raise SnapshotError("election.candidates contains duplicate ballot numbers")
    item["candidates"] = sorted(candidates, key=_candidate_sort_key)
    return item


def _validate_coverage(value: object, label: str) -> dict[str, int]:
    fields = {"expected", "retrieved", "parsed", "missing", "ambiguous", "excluded"}
    item = _object(value, label=label, fields=fields)
    counts = {field: _nonnegative_int(item[field], f"{label}.{field}") for field in fields}
    if not counts["parsed"] <= counts["retrieved"] <= counts["expected"]:
        raise SnapshotError(f"{label} violates parsed <= retrieved <= expected")
    classified = counts["parsed"] + counts["missing"] + counts["ambiguous"] + counts["excluded"]
    if classified != counts["expected"]:
        raise SnapshotError(f"{label} classifications must equal expected")
    return counts


def _validate_geographic_collection_coverage(value: object) -> dict[str, int | str]:
    fields = {
        "status",
        "expected_polling_places",
        "retrieved_polling_places",
        "expected_mesas",
        "retrieved_mesas",
    }
    item = _object(value, label="summary.geographic_collection_coverage", fields=fields)
    if item["status"] not in {"national_only", "sample_limited", "full_scope"}:
        raise SnapshotError("summary.geographic_collection_coverage.status is invalid")
    for field in fields - {"status"}:
        _nonnegative_int(item[field], f"summary.geographic_collection_coverage.{field}")
    if (
        item["retrieved_polling_places"] > item["expected_polling_places"]
        or item["retrieved_mesas"] > item["expected_mesas"]
    ):
        raise SnapshotError("summary.geographic_collection_coverage counts must be monotonic")
    return item


def _validate_summary(
    value: object,
    *,
    manifest: Mapping[str, Any],
    election: Mapping[str, Any],
    parser_versions: frozenset[str],
    legacy_fixture_accounting: bool,
) -> dict[str, Any]:
    fields = {
        "election_slug",
        "election_name",
        "round",
        "election_date",
        "data_version",
        "release_status",
        "synthetic",
        "completion",
        *_METRIC_FIELDS,
        "turnout",
        "candidates",
        "coverage",
        "geographic_collection_coverage",
        "reconciliation",
        "provenance",
    }
    item = _object(
        value,
        label="summary",
        fields=fields,
        optional={"geographic_collection_coverage"},
    )
    expected_identity = {
        "election_slug": election["slug"],
        "election_name": election["name"],
        "round": election["round"],
        "election_date": election["election_date"],
        "data_version": manifest["data_version"],
        "release_status": manifest["status"],
        "synthetic": manifest["synthetic"],
    }
    for field, expected in expected_identity.items():
        if item[field] != expected:
            raise SnapshotError(f"summary.{field} does not match its release/election value")
    completion = _object(
        item["completion"],
        label="summary.completion",
        fields={"expected", "reported", "percent"},
    )
    expected = _nonnegative_int(completion["expected"], "summary.completion.expected")
    reported = _nonnegative_int(completion["reported"], "summary.completion.reported")
    percent = _finite_number(
        completion["percent"], "summary.completion.percent", minimum=0, maximum=1
    )
    if reported > expected:
        raise SnapshotError("summary.completion.reported cannot exceed expected")
    calculated = reported / expected if expected else 0.0
    if not math.isclose(percent, calculated, rel_tol=0, abs_tol=_RATE_TOLERANCE):
        raise SnapshotError("summary.completion.percent does not match its counts")
    item["completion"] = completion
    for field in _METRIC_FIELDS:
        item[field] = _metric(item[field], f"summary.{field}")
    turnout = item["turnout"]
    if turnout is not None:
        turnout_number = _finite_number(turnout, "summary.turnout", minimum=0, maximum=1)
        voters = item["voters"]
        electors = item["registered_electors"]
        if (
            voters["status"] == electors["status"] == "observed"
            and electors["value"]
            and not math.isclose(
                turnout_number,
                voters["value"] / electors["value"],
                rel_tol=0,
                abs_tol=_RATE_TOLERANCE,
            )
        ):
            raise SnapshotError("summary.turnout does not match voters/registered_electors")
    if not isinstance(item["candidates"], list):
        raise SnapshotError("summary.candidates must be a list")
    known_candidates = {candidate["id"]: candidate for candidate in election["candidates"]}
    summaries: list[dict[str, Any]] = []
    for index, raw in enumerate(item["candidates"]):
        label = f"summary.candidates[{index}]"
        candidate_summary = _object(raw, label=label, fields={"candidate", "votes", "share"})
        candidate_summary["candidate"] = _candidate(
            candidate_summary["candidate"], f"{label}.candidate"
        )
        candidate_id = candidate_summary["candidate"]["id"]
        if candidate_summary["candidate"] != known_candidates.get(candidate_id):
            raise SnapshotError(f"{label}.candidate does not match election.candidates")
        candidate_summary["votes"] = _metric(candidate_summary["votes"], f"{label}.votes")
        share = candidate_summary["share"]
        if share is not None:
            share_number = _finite_number(share, f"{label}.share", minimum=0, maximum=1)
            valid = item["valid_votes"]
            votes = candidate_summary["votes"]
            if (
                votes["status"] == valid["status"] == "observed"
                and valid["value"]
                and not math.isclose(
                    share_number,
                    votes["value"] / valid["value"],
                    rel_tol=0,
                    abs_tol=_RATE_TOLERANCE,
                )
            ):
                raise SnapshotError(f"{label}.share does not match votes/valid_votes")
        summaries.append(candidate_summary)
    summary_ids = [summary["candidate"]["id"] for summary in summaries]
    if len(set(summary_ids)) != len(summary_ids) or set(summary_ids) != set(known_candidates):
        raise SnapshotError("summary.candidates must contain every election candidate exactly once")
    item["candidates"] = sorted(summaries, key=lambda value: str(value["candidate"]["id"]))
    _validate_result_arithmetic(
        item,
        "summary",
        legacy_fixture_accounting=legacy_fixture_accounting,
    )
    item["coverage"] = _validate_coverage(item["coverage"], "summary.coverage")
    if "geographic_collection_coverage" in item:
        item["geographic_collection_coverage"] = _validate_geographic_collection_coverage(
            item["geographic_collection_coverage"]
        )
    reconciliation = _object(
        item["reconciliation"],
        label="summary.reconciliation",
        fields={"status", "checked_facts", "exceptions"},
    )
    if reconciliation["status"] not in {"passed", "blocked", "not_run"}:
        raise SnapshotError("summary.reconciliation.status is invalid")
    _nonnegative_int(reconciliation["checked_facts"], "summary.reconciliation.checked_facts")
    exceptions = _nonnegative_int(reconciliation["exceptions"], "summary.reconciliation.exceptions")
    if reconciliation["status"] == "passed" and exceptions:
        raise SnapshotError("a passed reconciliation cannot retain exceptions")
    item["reconciliation"] = reconciliation
    item["provenance"] = _validate_provenance(
        item["provenance"],
        label="summary.provenance",
        data_version=str(manifest["data_version"]),
        parser_versions=parser_versions,
    )
    return item


def _validate_geographies(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("geographies must be a list")
    items: list[dict[str, Any]] = []
    fields = {"id", "level", "code", "name", "parent_id", "authoritative_coordinates"}
    coordinate_fields = {"latitude", "longitude", "quality", "source_url"}
    for index, raw in enumerate(value):
        label = f"geographies[{index}]"
        item = _object(raw, label=label, fields=fields)
        _nonempty_string(item["id"], f"{label}.id")
        _nonempty_string(item["code"], f"{label}.code")
        _nonempty_string(item["name"], f"{label}.name")
        if item["level"] not in _GEOGRAPHY_LEVELS or item["level"] == "mesa":
            raise SnapshotError(f"{label}.level is invalid for a geography")
        if item["parent_id"] is not None:
            _nonempty_string(item["parent_id"], f"{label}.parent_id")
        coordinates = item["authoritative_coordinates"]
        if coordinates is not None:
            coordinates = _object(
                coordinates, label=f"{label}.authoritative_coordinates", fields=coordinate_fields
            )
            _finite_number(
                coordinates["latitude"],
                f"{label}.authoritative_coordinates.latitude",
                minimum=-90,
                maximum=90,
            )
            _finite_number(
                coordinates["longitude"],
                f"{label}.authoritative_coordinates.longitude",
                minimum=-180,
                maximum=180,
            )
            if coordinates["quality"] not in {"authoritative", "approximate"}:
                raise SnapshotError(f"{label}.authoritative_coordinates.quality is invalid")
            _https_url(coordinates["source_url"], f"{label}.authoritative_coordinates.source_url")
            item["authoritative_coordinates"] = coordinates
        items.append(item)
    by_id = {str(item["id"]): item for item in items}
    if len(by_id) != len(items):
        raise SnapshotError("geographies contains duplicate ids")
    national = by_id.get("CO")
    if national is None or national["level"] != "national" or national["parent_id"] is not None:
        raise SnapshotError("geographies must contain the repository's CO national root")
    for item in items:
        parent_id = item["parent_id"]
        if item["level"] == "national":
            if parent_id is not None:
                raise SnapshotError(f"national geography {item['id']!r} cannot have a parent")
            continue
        parent = by_id.get(str(parent_id))
        if parent is None:
            raise SnapshotError(f"geography {item['id']!r} refers to an unknown parent")
        if _GEOGRAPHY_LEVELS[parent["level"]] >= _GEOGRAPHY_LEVELS[item["level"]]:
            raise SnapshotError(f"geography {item['id']!r} has a non-ancestor parent level")
    return sorted(items, key=lambda item: (_GEOGRAPHY_LEVELS[item["level"]], str(item["id"])))


def _ancestor_ids(identifier: str, geographies: Mapping[str, Mapping[str, Any]]) -> set[str]:
    ancestors: set[str] = set()
    current: str | None = identifier
    while current is not None:
        if current in ancestors:
            raise SnapshotError(f"geography ancestry for {identifier!r} contains a cycle")
        ancestors.add(current)
        parent = geographies[current]["parent_id"]
        current = str(parent) if parent is not None else None
    return ancestors


def _validate_mesas(
    value: object, geographies: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("mesas must be a list")
    fields = {"id", "display_number", "polling_place_id", "municipality_id", "department_id"}
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"mesas[{index}]"
        item = _object(raw, label=label, fields=fields)
        for field in fields:
            _nonempty_string(item[field], f"{label}.{field}")
        place = geographies.get(item["polling_place_id"])
        municipality = geographies.get(item["municipality_id"])
        department = geographies.get(item["department_id"])
        if place is None or place["level"] != "polling_place":
            raise SnapshotError(f"{label}.polling_place_id is not a polling place")
        if municipality is None or municipality["level"] != "municipality":
            raise SnapshotError(f"{label}.municipality_id is not a municipality")
        if department is None or department["level"] != "department":
            raise SnapshotError(f"{label}.department_id is not a department")
        ancestry = _ancestor_ids(str(item["polling_place_id"]), geographies)
        if item["municipality_id"] not in ancestry or item["department_id"] not in ancestry:
            raise SnapshotError(f"{label} has inconsistent geographic ancestry")
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("mesas contains duplicate ids")
    return sorted(items, key=lambda item: str(item["id"]))


def _validate_results(
    value: object,
    *,
    election_slug: str,
    data_version: str,
    candidate_ids: frozenset[str],
    geographies: Mapping[str, Mapping[str, Any]],
    mesas: Mapping[str, Mapping[str, Any]],
    parser_versions: frozenset[str],
    legacy_fixture_accounting: bool,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("results must be a list")
    fields = {
        "id",
        "election_slug",
        "geography_id",
        "geography_level",
        "mesa_id",
        *_METRIC_FIELDS,
        "candidates",
        "provenance",
    }
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"results[{index}]"
        item = _object(raw, label=label, fields=fields)
        _nonempty_string(item["id"], f"{label}.id")
        if item["election_slug"] != election_slug:
            raise SnapshotError(f"{label}.election_slug does not match the release")
        level = item["geography_level"]
        if level not in _GEOGRAPHY_LEVELS:
            raise SnapshotError(f"{label}.geography_level is invalid")
        geography_id = _nonempty_string(item["geography_id"], f"{label}.geography_id")
        mesa_id = item["mesa_id"]
        if level == "mesa":
            if not isinstance(mesa_id, str) or mesa_id not in mesas:
                raise SnapshotError(f"{label}.mesa_id must identify a known mesa")
            if geography_id != mesas[mesa_id]["polling_place_id"]:
                raise SnapshotError(f"{label}.geography_id must be its mesa's polling place")
        else:
            if mesa_id is not None:
                raise SnapshotError(f"{label}.mesa_id must be null for an aggregate fact")
            geography = geographies.get(geography_id)
            if geography is None or geography["level"] != level:
                raise SnapshotError(f"{label}.geography_id does not match geography_level")
        for field in _METRIC_FIELDS:
            item[field] = _metric(item[field], f"{label}.{field}")
        item["candidates"] = _candidate_result_list(
            item["candidates"], f"{label}.candidates", candidate_ids
        )
        item["provenance"] = _validate_provenance(
            item["provenance"],
            label=f"{label}.provenance",
            data_version=data_version,
            parser_versions=parser_versions,
        )
        _validate_result_arithmetic(
            item,
            label,
            legacy_fixture_accounting=legacy_fixture_accounting,
        )
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("results contains duplicate ids")
    return sorted(items, key=lambda item: str(item["id"]))


def _validate_exact_summary_rollup(
    summary: Mapping[str, Any], results: Sequence[Mapping[str, Any]]
) -> None:
    """Recompute a complete mesa-backed summary instead of trusting a gate flag."""
    coverage = summary["coverage"]
    completion = summary["completion"]
    if not (
        coverage["expected"] == coverage["parsed"]
        and coverage["missing"] == 0
        and coverage["ambiguous"] == 0
        and coverage["excluded"] == 0
        and completion["expected"] == completion["reported"]
    ):
        return
    provenance = summary["provenance"]
    rows = [
        result
        for result in results
        if result["geography_level"] == "mesa"
        and result["provenance"]["source_type"] == provenance["source_type"]
        and result["provenance"]["legal_status"] == provenance["legal_status"]
    ]
    # A separately published aggregate (for example, a final declaration at
    # national grain) is not represented as a mesa roll-up in this snapshot.
    if not rows:
        return
    expected = int(coverage["expected"])
    if len(rows) != expected or int(completion["expected"]) != expected:
        raise SnapshotError(
            "summary exact rollup requires every expected same-source mesa exactly once"
        )
    for field in _METRIC_FIELDS:
        summary_value = _observed_metric_value(summary, field)
        if summary_value is None:
            continue
        row_values = [_observed_metric_value(row, field) for row in rows]
        if (
            any(value is None for value in row_values)
            or sum(cast(int, value) for value in row_values) != summary_value
        ):
            raise SnapshotError(f"summary.{field} does not equal its exact mesa rollup")
    for candidate in summary["candidates"]:
        candidate_id = str(candidate["candidate"]["id"])
        summary_votes = _observed_metric_value(candidate, "votes")
        if summary_votes is None:
            continue
        row_values = [
            _observed_metric_value(
                next(value for value in row["candidates"] if value["candidate_id"] == candidate_id),
                "votes",
            )
            for row in rows
        ]
        if (
            any(value is None for value in row_values)
            or sum(cast(int, value) for value in row_values) != summary_votes
        ):
            raise SnapshotError(
                f"summary candidate {candidate_id!r} does not equal its exact mesa rollup"
            )


def _validate_evidence(
    value: object,
    *,
    data_version: str,
    mesas: Mapping[str, Mapping[str, Any]],
    parser_versions: frozenset[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("evidence must be a list")
    fields = {
        "id",
        "mesa_id",
        "document_type",
        "official_url",
        "source_index_url",
        "source_index_hash",
        "indexed_at",
        "index_status",
        "provenance",
    }
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(raw, Mapping):
            raise SnapshotError(f"{label} must be an object")
        # Immutable releases created before the index-only policy can be
        # rematerialized safely: retain their raw artifact unchanged, omit the
        # retired document-processing projection from the new public snapshot.
        if "source_index_url" not in raw:
            continue
        item = _object(raw, label=label, fields=fields)
        _nonempty_string(item["id"], f"{label}.id")
        if item["mesa_id"] not in mesas:
            raise SnapshotError(f"{label}.mesa_id refers to an unknown mesa")
        if item["document_type"] not in {"e14_delegate", "e14_transmission"}:
            raise SnapshotError(f"{label}.document_type is invalid")
        _https_url(item["official_url"], f"{label}.official_url")
        _https_url(item["source_index_url"], f"{label}.source_index_url")
        _sha256(item["source_index_hash"], f"{label}.source_index_hash")
        _timestamp(item["indexed_at"], f"{label}.indexed_at")
        if item["index_status"] not in {"indexed", "unavailable", "ambiguous"}:
            raise SnapshotError(f"{label}.index_status is invalid")
        item["provenance"] = _validate_provenance(
            item["provenance"],
            label=f"{label}.provenance",
            data_version=data_version,
            parser_versions=parser_versions,
        )
        if item["provenance"]["source_url"] != item["source_index_url"]:
            raise SnapshotError(f"{label}.provenance must identify source_index_url")
        if item["provenance"]["content_hash"] != item["source_index_hash"]:
            raise SnapshotError(f"{label}.provenance content_hash must equal source_index_hash")
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("evidence contains duplicate ids")
    return sorted(items, key=lambda item: (str(item["mesa_id"]), str(item["id"])))


def _validate_evidence_handling(
    value: object, evidence: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value:
        raise SnapshotError("evidence_handling must be an empty object under the index-only policy")
    return {}


def _validate_comparisons(
    value: object,
    mesas: Mapping[str, Mapping[str, Any]],
    *,
    artifact_hashes: frozenset[str],
    source_artifacts: Mapping[str, Sequence[Mapping[str, Any]]],
    comparison_authorization: Mapping[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        raise SnapshotError("comparisons must be an object keyed by mesa id")
    fields = {
        "field",
        "left_source_type",
        "right_source_type",
        "left_artifact_hash",
        "right_artifact_hash",
        "left_value",
        "right_value",
        "signed_difference",
        "affected_vote_estimate",
        "compatible_grain",
        "notes",
    }
    authorized_comparisons: set[tuple[str, str]] = set()
    if value and comparison_authorization is None:
        raise SnapshotError("comparisons require an authenticated comparison authorization")
    if comparison_authorization is not None:
        authorization = _object(
            comparison_authorization,
            label="comparison_authorization",
            fields={"artifact_hash", "comparisons"},
        )
        _sha256(authorization["artifact_hash"], "comparison_authorization.artifact_hash")
        if authorization["artifact_hash"] not in artifact_hashes:
            raise SnapshotError("comparison authorization is not an immutable release artifact")
        if not isinstance(authorization["comparisons"], list):
            raise SnapshotError("comparison_authorization.comparisons must be a list")
        expected_hash = hashlib.sha256(
            canonical_snapshot_bytes(
                {
                    "schema": "comparison-authorization-v1",
                    "comparisons": authorization["comparisons"],
                }
            )
        ).hexdigest()
        if authorization["artifact_hash"] != expected_hash:
            raise SnapshotError("comparison authorization artifact hash does not bind comparisons")
        for index, raw_entry in enumerate(authorization["comparisons"]):
            entry = _object(
                raw_entry,
                label=f"comparison_authorization.comparisons[{index}]",
                fields={"mesa_id", "comparison_hash"},
            )
            authorized_comparisons.add(
                (
                    _nonempty_string(entry["mesa_id"], "comparison authorization mesa_id"),
                    _sha256(entry["comparison_hash"], "comparison authorization comparison_hash"),
                )
            )
    result: dict[str, list[dict[str, Any]]] = {}
    for mesa_id in sorted(value):
        if not isinstance(mesa_id, str) or mesa_id not in mesas:
            raise SnapshotError("comparisons refers to an unknown mesa")
        raw_items = value[mesa_id]
        if not isinstance(raw_items, list):
            raise SnapshotError(f"comparisons[{mesa_id!r}] must be a list")
        items: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_items):
            label = f"comparisons[{mesa_id!r}][{index}]"
            if (
                mesa_id,
                hashlib.sha256(canonical_snapshot_bytes(raw)).hexdigest(),
            ) not in authorized_comparisons:
                raise SnapshotError(f"{label} lacks authenticated comparison authorization")
            item = _object(raw, label=label, fields=fields)
            _nonempty_string(item["field"], f"{label}.field")
            for side in ("left", "right"):
                if item[f"{side}_source_type"] not in _SOURCE_LEGAL_STATUS:
                    raise SnapshotError(f"{label}.{side}_source_type is invalid")
                _sha256(item[f"{side}_artifact_hash"], f"{label}.{side}_artifact_hash")
                if item[f"{side}_artifact_hash"] not in artifact_hashes:
                    raise SnapshotError(
                        f"{label}.{side}_artifact_hash is not a declared immutable artifact"
                    )
                item[f"{side}_value"] = _metric(item[f"{side}_value"], f"{label}.{side}_value")
            if type(item["compatible_grain"]) is not bool:
                raise SnapshotError(f"{label}.compatible_grain must be boolean")
            difference = item["signed_difference"]
            if difference is not None and type(difference) is not int:
                raise SnapshotError(f"{label}.signed_difference must be an integer or null")
            affected = item["affected_vote_estimate"]
            if affected is not None:
                _nonnegative_int(affected, f"{label}.affected_vote_estimate")
            left = item["left_value"]
            right = item["right_value"]
            # This boundary receives hashes, not the normalized signed fact
            # rows themselves.  It therefore cannot establish that caller
            # supplied values occur in either artifact.  Keep the comparison
            # as an explicitly unknown review lead; typed reconciliation is
            # the only path permitted to calculate a public difference.
            observed_compatible = False
            if not observed_compatible:
                # Values from unknown operands must not become snapshot facts
                # merely because a caller supplied an artifact hash.
                item["left_value"] = {"value": None, "status": "unknown"}
                item["right_value"] = {"value": None, "status": "unknown"}
                item["compatible_grain"] = False
                item["signed_difference"] = None
                item["affected_vote_estimate"] = None
            else:
                expected_difference = left["value"] - right["value"]
                expected_affected = abs(expected_difference)
                if difference != expected_difference or affected != expected_affected:
                    raise SnapshotError(
                        f"{label} must use recomputed signed difference and affected votes"
                    )
                item["compatible_grain"] = True
            item["notes"] = _localized(item["notes"], f"{label}.notes")
            items.append(item)
        result[mesa_id] = sorted(
            items,
            key=lambda item: (
                str(item["field"]),
                str(item["left_source_type"]),
                str(item["right_source_type"]),
            ),
        )
    return result


def _validate_bulletins(
    value: object, *, data_version: str, candidate_ids: frozenset[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("bulletins must be a list")
    fields = {
        "id",
        "sequence",
        "published_at",
        "completion_percent",
        "reported_mesas",
        "expected_mesas",
        "candidate_votes",
        "source_url",
        "content_hash",
        "data_version",
    }
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"bulletins[{index}]"
        item = _object(raw, label=label, fields=fields)
        _nonempty_string(item["id"], f"{label}.id")
        if type(item["sequence"]) is not int or item["sequence"] < 1:
            raise SnapshotError(f"{label}.sequence must be a positive integer")
        _timestamp(item["published_at"], f"{label}.published_at")
        reported = _nonnegative_int(item["reported_mesas"], f"{label}.reported_mesas")
        expected = _nonnegative_int(item["expected_mesas"], f"{label}.expected_mesas")
        percent = _finite_number(
            item["completion_percent"], f"{label}.completion_percent", minimum=0, maximum=1
        )
        if reported > expected:
            raise SnapshotError(f"{label}.reported_mesas cannot exceed expected_mesas")
        calculated = reported / expected if expected else 0.0
        if not math.isclose(percent, calculated, rel_tol=0, abs_tol=_RATE_TOLERANCE):
            raise SnapshotError(f"{label}.completion_percent does not match its counts")
        if item["data_version"] != data_version:
            raise SnapshotError(f"{label}.data_version does not match the release")
        _https_url(item["source_url"], f"{label}.source_url")
        _sha256(item["content_hash"], f"{label}.content_hash")
        votes = item["candidate_votes"]
        if not isinstance(votes, Mapping) or set(votes) != set(candidate_ids):
            raise SnapshotError(f"{label}.candidate_votes must contain every candidate")
        item["candidate_votes"] = {
            candidate_id: _nonnegative_int(votes[candidate_id], f"{label}.candidate_votes")
            for candidate_id in sorted(candidate_ids)
        }
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("bulletins contains duplicate ids")
    if len({item["sequence"] for item in items}) != len(items):
        raise SnapshotError("bulletins contains duplicate sequences")
    return sorted(items, key=lambda item: (int(item["sequence"]), str(item["id"])))


def _tier(score: int) -> str:
    if score >= 70:
        return "documentary_review_prioritized"
    if score >= 45:
        return "documentary_comparison_recommended"
    if score >= 15:
        return "statistical_or_coverage_issue"
    return "no_review_signals"


def _validate_review_signals(
    value: object,
    *,
    methodology_version: str,
    data_version: str,
    election_slug: str,
    candidate_ids: frozenset[str],
    mesas: Mapping[str, Mapping[str, Any]],
    parser_versions: frozenset[str],
    release_status: str,
    release_synthetic: bool,
    artifact_hashes: frozenset[str],
    artifact_locations: frozenset[tuple[str, str]],
    statistical_authorization: Mapping[str, Any] | None,
    evidence_authorization: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("review_signals must be a list")
    authorization_entries: set[tuple[str, str, str, str, str, str]] = set()
    deterministic_authorizations: set[tuple[str, str, str, str]] = set()
    if evidence_authorization is not None:
        authorization = _object(
            evidence_authorization,
            label="evidence_authorization",
            fields={"artifact_hash", "components"},
        )
        _sha256(authorization["artifact_hash"], "evidence_authorization.artifact_hash")
        if authorization["artifact_hash"] not in artifact_hashes:
            raise SnapshotError("evidence authorization is not an immutable release artifact")
        if not isinstance(authorization["components"], list):
            raise SnapshotError("evidence_authorization.components must be a list")
        expected_hash = hashlib.sha256(
            canonical_snapshot_bytes(
                {
                    "schema": "deterministic-evidence-authorization-v1",
                    "components": authorization["components"],
                }
            )
        ).hexdigest()
        if authorization["artifact_hash"] != expected_hash:
            raise SnapshotError("evidence authorization artifact hash does not bind components")
        for index, raw_entry in enumerate(authorization["components"]):
            entry = _object(
                raw_entry,
                label=f"evidence_authorization.components[{index}]",
                fields={
                    "mesa_id",
                    "component_hash",
                    "evidence_artifact_hash",
                    "evidence_artifact_kind",
                },
            )
            _nonempty_string(entry["mesa_id"], "evidence authorization mesa_id")
            _sha256(entry["component_hash"], "evidence authorization component_hash")
            _sha256(entry["evidence_artifact_hash"], "evidence authorization artifact_hash")
            if entry["evidence_artifact_kind"] not in {
                "reconciliation_result",
                "document_review",
            }:
                raise SnapshotError("evidence authorization artifact kind is invalid")
            deterministic_authorizations.add(
                (
                    str(entry["mesa_id"]),
                    str(entry["component_hash"]),
                    str(entry["evidence_artifact_hash"]),
                    str(entry["evidence_artifact_kind"]),
                )
            )
    if statistical_authorization is not None:
        authorization = _object(
            statistical_authorization,
            label="statistical_authorization",
            fields={"artifact_hash", "validated_families"},
        )
        _sha256(authorization["artifact_hash"], "statistical_authorization.artifact_hash")
        if authorization["artifact_hash"] not in artifact_hashes:
            raise SnapshotError("statistical authorization is not an immutable release artifact")
        if not isinstance(authorization["validated_families"], list):
            raise SnapshotError("statistical_authorization.validated_families must be a list")
        expected_authorization_hash = hashlib.sha256(
            canonical_snapshot_bytes(
                {
                    "schema": "statistical-authorization-v1",
                    "validated_families": authorization["validated_families"],
                }
            )
        ).hexdigest()
        if authorization["artifact_hash"] != expected_authorization_hash:
            raise SnapshotError(
                "statistical authorization artifact hash does not bind its validated families"
            )
        for index, entry in enumerate(authorization["validated_families"]):
            record = _object(
                entry,
                label=f"statistical_authorization.validated_families[{index}]",
                fields={
                    "detector_id",
                    "family_id",
                    "code_hash",
                    "method_hash",
                    "input_artifact_hash",
                    "cohort_hash",
                },
            )
            if record["detector_id"] != "peer":
                raise SnapshotError("only independently validated peer families are authorized")
            for field in (
                "family_id",
                "code_hash",
                "method_hash",
                "input_artifact_hash",
                "cohort_hash",
            ):
                if field == "family_id":
                    _nonempty_string(record[field], f"statistical authorization {field}")
                else:
                    _sha256(record[field], f"statistical authorization {field}")
            authorization_entries.add(
                (
                    str(record["detector_id"]),
                    str(record["family_id"]),
                    str(record["code_hash"]),
                    str(record["method_hash"]),
                    str(record["input_artifact_hash"]),
                    str(record["cohort_hash"]),
                )
            )
    mesa_family_digest = hashlib.sha256(
        json.dumps(sorted(mesas), ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    signal_fields = {
        "id",
        "mesa_id",
        "score",
        "tier",
        "affected_vote_estimate",
        "methodology_version",
        "components",
        "disclosure",
        "provenance",
    }
    component_fields = {
        "component_type",
        "points",
        "observed_value",
        "comparator",
        "calculation",
        "peer_definition",
        "limitations",
            "source_links",
            "evidence_artifact_hash",
            "evidence_artifact_kind",
        *_STATISTICAL_BINDING_FIELDS,
        *_OPTIONAL_ANALYZER_BINDING_FIELDS,
    }
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"review_signals[{index}]"
        item = _object(raw, label=label, fields=signal_fields)
        _nonempty_string(item["id"], f"{label}.id")
        if item["mesa_id"] not in mesas:
            raise SnapshotError(f"{label}.mesa_id refers to an unknown mesa")
        score = _nonnegative_int(item["score"], f"{label}.score")
        if score > 100 or item["tier"] != _tier(score):
            raise SnapshotError(f"{label}.tier does not match its score")
        if item["methodology_version"] != methodology_version:
            raise SnapshotError(f"{label}.methodology_version does not match the release")
        if item["affected_vote_estimate"] is not None:
            _nonnegative_int(item["affected_vote_estimate"], f"{label}.affected_vote_estimate")
        if not isinstance(item["components"], list):
            raise SnapshotError(f"{label}.components must be a list")
        components: list[dict[str, Any]] = []
        for component_index, raw_component in enumerate(item["components"]):
            component_label = f"{label}.components[{component_index}]"
            component = _object(
                raw_component,
                label=component_label,
                fields=component_fields,
                optional=_OPTIONAL_ANALYZER_BINDING_FIELDS,
            )
            component_type = component["component_type"]
            if component_type not in _COMPONENT_POINTS:
                raise SnapshotError(f"{component_label}.component_type is invalid")
            if component["points"] != _COMPONENT_POINTS[component_type]:
                raise SnapshotError(f"{component_label}.points does not match the methodology")
            if component["observed_value"] is not None:
                _finite_number(
                    component["observed_value"],
                    f"{component_label}.observed_value",
                    minimum=-math.inf,
                    maximum=math.inf,
                )
            _nonempty_string(component["comparator"], f"{component_label}.comparator")
            _nonempty_string(component["calculation"], f"{component_label}.calculation")
            if component["peer_definition"] is not None:
                _nonempty_string(component["peer_definition"], f"{component_label}.peer_definition")
            component["limitations"] = _localized(
                component["limitations"], f"{component_label}.limitations"
            )
            links = component["source_links"]
            if not isinstance(links, list) or not links:
                raise SnapshotError(f"{component_label}.source_links must be non-empty")
            component["source_links"] = sorted(
                {_https_url(link, f"{component_label}.source_links") for link in links}
            )
            statistical = component_type in _STATISTICAL_COMPONENTS
            evidence_hash = component["evidence_artifact_hash"]
            evidence_kind = component["evidence_artifact_kind"]
            if statistical:
                if evidence_hash is not None or evidence_kind is not None:
                    raise SnapshotError(
                        f"{component_label} cannot claim deterministic evidence provenance"
                    )
            else:
                if not release_synthetic:
                    raise SnapshotError(
                        f"{component_label} requires typed deterministic artifact replay"
                    )
                _sha256(evidence_hash, f"{component_label}.evidence_artifact_hash")
                if evidence_hash not in artifact_hashes:
                    raise SnapshotError(
                        f"{component_label}.evidence_artifact_hash is not declared by the release"
                    )
                if evidence_kind not in {"reconciliation_result", "document_review"}:
                    raise SnapshotError(f"{component_label}.evidence_artifact_kind is invalid")
                component_hash = hashlib.sha256(
                    canonical_snapshot_bytes(raw_component)
                ).hexdigest()
                if (
                    str(item["mesa_id"]),
                    component_hash,
                    str(evidence_hash),
                    str(evidence_kind),
                    ) not in deterministic_authorizations:
                    raise SnapshotError(
                        f"{component_label} lacks authenticated deterministic evidence "
                        "authorization"
                    )
            populated_binding_fields = {
                field for field in _STATISTICAL_BINDING_FIELDS if component[field] is not None
            }
            if statistical and populated_binding_fields != _STATISTICAL_BINDING_FIELDS:
                raise SnapshotError(f"{component_label} requires a complete typed analyzer binding")
            if not statistical and populated_binding_fields:
                raise SnapshotError(
                    f"{component_label} cannot claim a statistical analyzer binding"
                )
            optional_binding_values = {
                field: component.get(field) for field in _OPTIONAL_ANALYZER_BINDING_FIELDS
            }
            if not statistical and any(
                value is not None for value in optional_binding_values.values()
            ):
                raise SnapshotError(f"{component_label} cannot claim optional analyzer provenance")
            if statistical:
                if component_type == "spatial_cluster":
                    populated_spatial_replay = {
                        field
                        for field in _SPATIAL_REPLAY_FIELDS
                        if component.get(field) is not None
                    }
                    if populated_spatial_replay != _SPATIAL_REPLAY_FIELDS:
                        raise SnapshotError(
                            f"{component_label} requires complete spatial replay evidence"
                        )
                    # The replay artifact has no independently calibrated
                    # spatial alternative design yet.  Do not turn an
                    # unvalidated detector output into a public review score.
                    raise SnapshotError(
                        f"{component_label} is ineligible until spatial calibration "
                        "is authenticated"
                    )
                authorization_key = (
                    "peer",
                    str(component["family_id"]),
                    str(component["code_hash"]),
                    str(component["method_hash"]),
                    str(component["input_artifact_hash"]),
                    str(component["cohort_hash"]),
                )
                if authorization_key not in authorization_entries:
                    raise SnapshotError(
                        f"{component_label} has no authenticated validated-family authorization"
                    )
                analyzer_mesa_id = component.get("analyzer_mesa_id")
                if analyzer_mesa_id is not None:
                    _nonempty_string(analyzer_mesa_id, f"{component_label}.analyzer_mesa_id")
                    if analyzer_mesa_id != item["mesa_id"]:
                        raise SnapshotError(
                            f"{component_label}.analyzer_mesa_id does not match its review mesa"
                        )
                elif release_status in {"candidate", "published"} and not release_synthetic:
                    raise SnapshotError(
                        f"{component_label} needs an analyzer mesa binding for release"
                    )
                for field in (
                    "analyzer_output_hash",
                    "expected_family_digest",
                    "cohort_hash",
                    "input_artifact_hash",
                    "code_hash",
                    "method_hash",
                ):
                    _sha256(component[field], f"{component_label}.{field}")
                _nonempty_string(component["family_id"], f"{component_label}.family_id")
                expected_count = _nonnegative_int(
                    component["expected_family_count"],
                    f"{component_label}.expected_family_count",
                )
                family_rank = _nonnegative_int(
                    component["family_rank"], f"{component_label}.family_rank"
                )
                family_size = _nonnegative_int(
                    component["family_size"], f"{component_label}.family_size"
                )
                if (
                    expected_count < 1
                    or family_rank < 1
                    or family_size < 1
                    or family_rank > family_size
                    or family_size > expected_count
                ):
                    raise SnapshotError(f"{component_label} has invalid family coverage or rank")
                if component_type == "peer_distribution" and (
                    expected_count != len(mesas)
                    or component["expected_family_digest"] != mesa_family_digest
                ):
                    raise SnapshotError(
                        f"{component_label} does not cover the exact release mesa family"
                    )
                p_value = _finite_number(
                    component["p_value"], f"{component_label}.p_value", minimum=0, maximum=1
                )
                q_value = _finite_number(
                    component["q_value"], f"{component_label}.q_value", minimum=0, maximum=1
                )
                if q_value < p_value:
                    raise SnapshotError(f"{component_label}.q_value cannot be below p_value")
                if p_value > 0.001 or q_value > 0.05:
                    raise SnapshotError(
                        f"{component_label} does not pass the frozen p/q signal gates"
                    )
                if component["adjustment_method"] != "benjamini-yekutieli":
                    raise SnapshotError(f"{component_label}.adjustment_method is invalid")
                if (component["code_hash"], component["method_hash"]) != _analyzer_hashes()[
                    component_type
                ]:
                    raise SnapshotError(
                        f"{component_label} code/method hashes are not the frozen analyzer"
                    )
                if (
                    component_type == "peer_distribution"
                    and component["input_artifact_hash"] not in artifact_hashes
                ):
                    raise SnapshotError(
                        f"{component_label}.input_artifact_hash is not declared by the release"
                    )
                if component["analyzer_output_hash"] not in artifact_hashes:
                    raise SnapshotError(
                        f"{component_label}.analyzer_output_hash is not declared by the release"
                    )
            components.append(component)
        component_types = [str(component["component_type"]) for component in components]
        if len(set(component_types)) != len(component_types):
            raise SnapshotError(f"{label}.components contains duplicate component types")
        statistical_only = all(
            component["component_type"] in _STATISTICAL_COMPONENTS for component in components
        )
        if statistical_only and item["affected_vote_estimate"] not in {None, 0}:
            raise SnapshotError(
                f"{label}.affected_vote_estimate must be null or zero for statistical-only signals"
            )
        deterministic = max(
            (
                component["points"]
                for component in components
                if component["component_type"] not in _STATISTICAL_COMPONENTS
            ),
            default=0,
        )
        statistical = min(
            20,
            sum(
                component["points"]
                for component in components
                if component["component_type"] in _STATISTICAL_COMPONENTS
            ),
        )
        if score != min(100, deterministic + statistical):
            raise SnapshotError(f"{label}.score does not match its components")
        item["components"] = sorted(
            components,
            key=lambda component: (-int(component["points"]), str(component["component_type"])),
        )
        disclosure = _localized(item["disclosure"], f"{label}.disclosure")
        if disclosure != {"es": DISCLOSURE_ES, "en": DISCLOSURE_EN}:
            raise SnapshotError(f"{label}.disclosure is not the permanent methodology wording")
        item["disclosure"] = disclosure
        item["provenance"] = _validate_provenance(
            item["provenance"],
            label=f"{label}.provenance",
            data_version=data_version,
            parser_versions=parser_versions,
        )
        if (
            item["provenance"]["source_type"] == "contextual_baseline"
            or item["provenance"]["legal_status"] == "context_only"
        ):
            raise SnapshotError(f"{label} cannot use contextual provenance")
        for component in components:
            if component["component_type"] not in _STATISTICAL_COMPONENTS:
                continue
            if election_slug not in _ANALYTICS_ELECTIONS:
                raise SnapshotError(f"{label} uses analytics outside the election allowlist")
            family_parts = str(component["family_id"]).split("|")
            if len(family_parts) != 5 or tuple(family_parts[:3]) != (
                data_version,
                election_slug,
                item["provenance"]["source_type"],
            ):
                raise SnapshotError(f"{label} has a noncanonical statistical family_id")
            metric, candidate_id = family_parts[3:]
            if metric not in {"turnout", "candidate_share", "blank", "null_unmarked"}:
                raise SnapshotError(f"{label} statistical family metric is invalid")
            if (metric == "candidate_share" and candidate_id not in candidate_ids) or (
                metric != "candidate_share" and candidate_id != "none"
            ):
                raise SnapshotError(f"{label} statistical family candidate is invalid")
            if component["component_type"] == "peer_distribution":
                cohort_payload = {
                    "candidate_id": None if candidate_id == "none" else candidate_id,
                    "data_version": data_version,
                    "election_slug": election_slug,
                    "expected_family_count": component["expected_family_count"],
                    "expected_family_digest": component["expected_family_digest"],
                    "input_artifact_hash": component["input_artifact_hash"],
                    "legal_status": item["provenance"]["legal_status"],
                    "metric": metric,
                    "source_layer": family_parts[2],
                    "source_type": item["provenance"]["source_type"],
                }
                encoded_cohort = json.dumps(
                    cohort_payload, sort_keys=True, separators=(",", ":")
                ).encode()
                if component["cohort_hash"] != hashlib.sha256(encoded_cohort).hexdigest():
                    raise SnapshotError(f"{label} peer cohort_hash is not canonical")
            if component["component_type"] == "spatial_cluster":
                spatial_values = {
                    field: component.get(field) for field in _SPATIAL_PROVENANCE_FIELDS
                }
                populated_spatial = {
                    field
                    for field, field_value in spatial_values.items()
                    if field_value is not None
                }
                if populated_spatial and populated_spatial != _SPATIAL_PROVENANCE_FIELDS:
                    raise SnapshotError(
                        f"{label} spatial analyzer provenance must be complete when supplied"
                    )
                if (
                    release_status in {"candidate", "published"}
                    and not release_synthetic
                    and populated_spatial != _SPATIAL_PROVENANCE_FIELDS
                ):
                    raise SnapshotError(
                        f"{label} needs complete spatial analyzer provenance for release"
                    )
                if populated_spatial == _SPATIAL_PROVENANCE_FIELDS:
                    analysis_unit_id = _nonempty_string(
                        spatial_values["analysis_unit_id"],
                        f"{label}.analysis_unit_id",
                    )
                    peer_residual_hash = _sha256(
                        spatial_values["peer_residual_artifact_hash"],
                        f"{label}.peer_residual_artifact_hash",
                    )
                    peer_methodology = _nonempty_string(
                        spatial_values["peer_methodology_version"],
                        f"{label}.peer_methodology_version",
                    )
                    coordinate_url = _https_url(
                        spatial_values["coordinate_source_url"],
                        f"{label}.coordinate_source_url",
                    )
                    coordinate_hash = _sha256(
                        spatial_values["coordinate_source_hash"],
                        f"{label}.coordinate_source_hash",
                    )
                    coordinate_accuracy = _finite_number(
                        spatial_values["coordinate_accuracy_m"],
                        f"{label}.coordinate_accuracy_m",
                        minimum=0,
                        maximum=math.inf,
                    )
                    if coordinate_accuracy <= 0:
                        raise SnapshotError(f"{label}.coordinate_accuracy_m must be positive")
                    coordinate_grain = spatial_values["coordinate_grain"]
                    if coordinate_grain not in {"mesa", "polling_place"}:
                        raise SnapshotError(f"{label}.coordinate_grain is invalid")
                    if peer_methodology != "peer-beta-binomial-eb-v3":
                        raise SnapshotError(f"{label}.peer_methodology_version is not frozen")
                    expected_mesa_count = _nonnegative_int(
                        spatial_values["expected_mesa_count"],
                        f"{label}.expected_mesa_count",
                    )
                    expected_mesa_digest = _sha256(
                        spatial_values["expected_mesa_digest"],
                        f"{label}.expected_mesa_digest",
                    )
                    membership_digest = _sha256(
                        spatial_values["expected_mesa_membership_digest"],
                        f"{label}.expected_mesa_membership_digest",
                    )
                    if expected_mesa_count != len(mesas):
                        raise SnapshotError(f"{label} spatial mesa declaration is incomplete")
                    if peer_residual_hash not in artifact_hashes:
                        raise SnapshotError(
                            f"{label}.peer_residual_artifact_hash is not declared by the release"
                        )
                    if (coordinate_url, coordinate_hash) not in artifact_locations:
                        raise SnapshotError(
                            f"{label} coordinate provenance is not declared by the release"
                        )
                    if coordinate_url not in component["source_links"]:
                        raise SnapshotError(f"{label}.source_links omits its coordinate provenance")
                    expected_units = (
                        set(mesas)
                        if coordinate_grain == "mesa"
                        else {str(mesa["polling_place_id"]) for mesa in mesas.values()}
                    )
                    expected_digest = hashlib.sha256(
                        json.dumps(sorted(expected_units), separators=(",", ":")).encode()
                    ).hexdigest()
                    if (
                        component["expected_family_count"] != len(expected_units)
                        or component["expected_family_digest"] != expected_digest
                    ):
                        raise SnapshotError(
                            f"{label} spatial family does not cover the exact release units"
                        )
                    if expected_mesa_digest != mesa_family_digest or not membership_digest:
                        raise SnapshotError(f"{label} spatial mesa membership is not authenticated")
                    expected_unit_id = (
                        item["mesa_id"]
                        if coordinate_grain == "mesa"
                        else mesas[str(item["mesa_id"])]["polling_place_id"]
                    )
                    if analysis_unit_id != expected_unit_id:
                        raise SnapshotError(
                            f"{label}.analysis_unit_id does not match its release unit"
                        )
                    input_payload = {
                        "analysis_unit_digest": expected_digest,
                        "coordinate_source_hash": coordinate_hash,
                        "mesa_membership_digest": membership_digest,
                        "peer_residual_artifact_hash": peer_residual_hash,
                    }
                    expected_input_hash = hashlib.sha256(
                        json.dumps(input_payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    if component["input_artifact_hash"] != expected_input_hash:
                        raise SnapshotError(f"{label} spatial input_artifact_hash is not canonical")
                    cohort_payload = {
                        "candidate_id": None if candidate_id == "none" else candidate_id,
                        "coordinate_accuracy_m": coordinate_accuracy,
                        "coordinate_grain": coordinate_grain,
                        "coordinate_source_hash": coordinate_hash,
                        "coordinate_source_url": coordinate_url,
                        "data_version": data_version,
                        "election_slug": election_slug,
                        "expected_family_count": component["expected_family_count"],
                        "expected_family_digest": component["expected_family_digest"],
                        "expected_mesa_count": expected_mesa_count,
                        "expected_mesa_digest": expected_mesa_digest,
                        "expected_mesa_membership_digest": membership_digest,
                        "legal_status": item["provenance"]["legal_status"],
                        "metric": metric,
                        "peer_methodology_version": peer_methodology,
                        "peer_residual_artifact_hash": peer_residual_hash,
                        "source_layer": family_parts[2],
                        "source_type": item["provenance"]["source_type"],
                    }
                    expected_cohort_hash = hashlib.sha256(
                        json.dumps(cohort_payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    if component["cohort_hash"] != expected_cohort_hash:
                        raise SnapshotError(f"{label} spatial cohort_hash is not canonical")
        if item["provenance"]["methodology_version"] != methodology_version:
            raise SnapshotError(f"{label}.provenance lacks the release methodology version")
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("review_signals contains duplicate ids")
    return sorted(items, key=lambda item: (-int(item["score"]), str(item["id"])))


def _validate_datasets(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotError("manifest.datasets must be a list")
    fields = {
        "id",
        "title",
        "format",
        "url",
        "schema_url",
        "record_count",
        "byte_size",
        "content_hash",
        "filters",
    }
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"manifest.datasets[{index}]"
        item = _object(raw, label=label, fields=fields)
        _nonempty_string(item["id"], f"{label}.id")
        item["title"] = _localized(item["title"], f"{label}.title")
        if item["format"] not in {"csv", "parquet", "json"}:
            raise SnapshotError(f"{label}.format is invalid")
        _https_url(item["url"], f"{label}.url")
        _https_url(item["schema_url"], f"{label}.schema_url")
        _nonnegative_int(item["record_count"], f"{label}.record_count")
        _nonnegative_int(item["byte_size"], f"{label}.byte_size")
        _sha256(item["content_hash"], f"{label}.content_hash")
        if not isinstance(item["filters"], Mapping) or any(
            not isinstance(key, str) or not isinstance(filter_value, str)
            for key, filter_value in item["filters"].items()
        ):
            raise SnapshotError(f"{label}.filters must be string pairs")
        item["filters"] = dict(sorted(item["filters"].items()))
        items.append(item)
    if len({item["id"] for item in items}) != len(items):
        raise SnapshotError("manifest.datasets contains duplicate ids")
    return sorted(items, key=lambda item: str(item["id"]))


def _totals_record(value: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for item in value["candidates"]:
        if kind == "summary":
            candidates.append({"candidate_id": item["candidate"]["id"], "votes": item["votes"]})
        else:
            candidates.append({"candidate_id": item["candidate_id"], "votes": item["votes"]})
    identity = (
        {"kind": "summary", "election_slug": value["election_slug"]}
        if kind == "summary"
        else {
            "kind": "result",
            "id": value["id"],
            "geography_id": value["geography_id"],
            "geography_level": value["geography_level"],
            "mesa_id": value["mesa_id"],
        }
    )
    return (
        identity
        | {field: value[field] for field in _METRIC_FIELDS}
        | {"candidates": sorted(candidates, key=lambda item: str(item["candidate_id"]))}
    )


def _has_observed_totals(value: Mapping[str, Any], *, kind: str) -> bool:
    if any(value[field]["status"] == "observed" for field in _METRIC_FIELDS):
        return True
    for item in value["candidates"]:
        votes = item["votes"]
        if votes["status"] == "observed":
            return True
    return False


def documentary_totals_digest(
    *,
    source_content_hash: str,
    summary: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> str:
    """Digest the exact public totals attributed to one documentary source.

    Computing this digest is mechanical; it is *not* an attestation.  Two humans
    must independently verify the values and explicitly supply the matching
    :class:`DocumentaryTotalsAttestation` to the materializer.
    """
    _sha256(source_content_hash, "source_content_hash")
    records: list[dict[str, Any]] = []
    if (
        isinstance(summary.get("provenance"), Mapping)
        and summary["provenance"].get("content_hash") == source_content_hash
        and _has_observed_totals(summary, kind="summary")
    ):
        records.append(_totals_record(summary, kind="summary"))
    for result in results:
        if (
            isinstance(result.get("provenance"), Mapping)
            and result["provenance"].get("content_hash") == source_content_hash
            and _has_observed_totals(result, kind="result")
        ):
            records.append(_totals_record(result, kind="result"))
    if not records:
        raise SnapshotError("the documentary source has no observed totals to attest")
    payload = {
        "source_content_hash": source_content_hash,
        "records": sorted(records, key=lambda item: canonical_snapshot_bytes(item)),
    }
    return hashlib.sha256(canonical_snapshot_bytes(payload)).hexdigest()


def _required_documentary_attestations(
    *,
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    attestations: Sequence[DocumentaryTotalsAttestation],
) -> None:
    declared_sources: dict[tuple[str, str], Mapping[str, Any]] = {}
    for source in manifest["sources"]:
        key = str(source["source_type"]), str(source["content_hash"])
        previous = declared_sources.get(key)
        if previous is not None and previous != source:
            raise SnapshotError("manifest has ambiguous documentary source declarations")
        declared_sources[key] = source
    observed_hashes: set[str] = set()
    for value, kind in [(summary, "summary"), *((result, "result") for result in results)]:
        provenance = value["provenance"]
        source_type = str(provenance["source_type"])
        if source_type not in _DOCUMENTARY_SOURCE_TYPES or not _has_observed_totals(
            value, kind=kind
        ):
            continue
        source_hash = str(provenance["content_hash"])
        source = declared_sources.get((source_type, source_hash))
        if source is None:
            raise SnapshotError(
                "observed documentary totals must reference an immutable manifest source"
            )
        media_type = str(source["media_type"])
        if (
            source_type == "final_declaration"
            or media_type == "application/pdf"
            or media_type.startswith("image/")
        ):
            observed_hashes.add(source_hash)
    supplied: dict[str, DocumentaryTotalsAttestation] = {}
    for attestation in attestations:
        if not isinstance(attestation, DocumentaryTotalsAttestation):
            raise SnapshotError("documentary_totals_attestations must contain typed attestations")
        if attestation.source_content_hash in supplied:
            raise SnapshotError("duplicate documentary totals attestation")
        supplied[attestation.source_content_hash] = attestation
    if set(supplied) != observed_hashes:
        missing = sorted(observed_hashes - set(supplied))
        unexpected = sorted(set(supplied) - observed_hashes)
        detail = []
        if missing:
            detail.append(f"missing={missing!r}")
        if unexpected:
            detail.append(f"unexpected={unexpected!r}")
        raise SnapshotError(
            "documentary totals require exactly one explicit human double-entry attestation ("
            + ", ".join(detail)
            + ")"
        )
    for source_hash, attestation in supplied.items():
        expected = documentary_totals_digest(
            source_content_hash=source_hash,
            summary=summary,
            results=results,
        )
        if attestation.values_digest != expected:
            raise SnapshotError(
                "documentary totals attestation does not match the values in api_snapshot"
            )


def _validate_release_state(
    manifest: Mapping[str, Any], summary: Mapping[str, Any], review_signals: Sequence[object]
) -> None:
    status = manifest["status"]
    synthetic = manifest["synthetic"]
    context_only = manifest.get("release_class") == "context_only"
    if synthetic is not (status == "fixture"):
        raise SnapshotError("synthetic must be true exactly when release status is fixture")
    has_statistical_signals = any(
        isinstance(signal, Mapping)
        and any(
            isinstance(component, Mapping)
            and component.get("component_type") in _STATISTICAL_COMPONENTS
            for component in signal.get("components", ())
        )
        for signal in review_signals
    )
    if context_only:
        if status != "published" or synthetic:
            raise SnapshotError("context_only snapshots must be non-synthetic published releases")
        if (
            manifest["aggregate_reconciled"] is not True
            or manifest["wording_validation_passed"] is not True
        ):
            raise SnapshotError("a context_only snapshot requires reconciliation and wording gates")
        if manifest["statistical_validation_passed"] is not False:
            raise SnapshotError("a context_only snapshot must disable statistical validation")
        if summary["provenance"]["source_type"] != "contextual_baseline":
            raise SnapshotError("a context_only snapshot must use contextual baseline provenance")
        if review_signals:
            raise SnapshotError("a context_only snapshot cannot contain review signals")
    elif status == "published":
        gates = (
            "aggregate_reconciled",
            "statistical_validation_passed",
            "wording_validation_passed",
        )
        if any(manifest[field] is not True for field in gates):
            raise SnapshotError("a published snapshot requires every manifest release gate")
        if (
            summary["reconciliation"]["status"] != "passed"
            or summary["reconciliation"]["exceptions"] != 0
        ):
            raise SnapshotError("a published snapshot requires passed aggregate reconciliation")
        if summary["provenance"]["source_type"] != "final_declaration":
            raise SnapshotError("a published summary must use the controlling final declaration")
    if status in {"candidate", "published"} and has_statistical_signals:
        raise SnapshotError(
            "candidate/published statistical signals remain blocked pending independent pass B"
        )


def materialize_api_snapshot(
    *,
    manifest: Mapping[str, Any],
    election: Mapping[str, Any],
    summary: Mapping[str, Any],
    geographies: Sequence[Mapping[str, Any]],
    mesas: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]] = (),
    evidence_handling: Mapping[str, Any] | None = None,
    comparisons: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    comparison_authorization: Mapping[str, Any] | None = None,
    bulletins: Sequence[Mapping[str, Any]] = (),
    review_signals: Sequence[Mapping[str, Any]] = (),
    statistical_authorization: Mapping[str, Any] | None = None,
    evidence_authorization: Mapping[str, Any] | None = None,
    documentary_totals_attestations: Sequence[DocumentaryTotalsAttestation] = (),
) -> ApiSnapshotArtifact:
    """Validate and materialize the exact release shape consumed by the API.

    Dataset records come directly from ``manifest.datasets`` so their immutable
    URLs, sizes, and hashes cannot drift between the public manifest and the API.
    Input ordering is intentionally discarded; semantically identical inputs
    therefore produce identical canonical bytes and SHA-256 digests.
    """
    manifest_copy = cast(dict[str, Any], _json_clone(dict(manifest), "manifest"))
    findings = validate_manifest(manifest_copy)
    if findings:
        raise SnapshotError("; ".join(f"{finding.code}: {finding.detail}" for finding in findings))
    data_version = str(manifest_copy["data_version"])
    parser_versions = frozenset(
        [str(value) for value in manifest_copy["parser_versions"].values()]
        + [str(source["parser_version"]) for source in manifest_copy["sources"]]
    )
    declared_artifacts = [*manifest_copy["sources"], *manifest_copy["datasets"]]
    artifact_hashes = frozenset(str(artifact["content_hash"]) for artifact in declared_artifacts)
    artifact_locations = frozenset(
        (str(artifact.get("source_url", artifact.get("url"))), str(artifact["content_hash"]))
        for artifact in declared_artifacts
    )
    source_artifacts: dict[str, list[Mapping[str, Any]]] = {}
    for source in manifest_copy["sources"]:
        source_artifacts.setdefault(str(source["content_hash"]), []).append(source)
    legacy_fixture_accounting = manifest_copy["synthetic"] is True
    election_item = _validate_election(election, manifest_copy)
    candidate_ids = frozenset(str(candidate["id"]) for candidate in election_item["candidates"])
    summary_item = _validate_summary(
        summary,
        manifest=manifest_copy,
        election=election_item,
        parser_versions=parser_versions,
        legacy_fixture_accounting=legacy_fixture_accounting,
    )
    geography_items = _validate_geographies(_json_clone(list(geographies), "geographies"))
    geography_by_id = {str(item["id"]): item for item in geography_items}
    mesa_items = _validate_mesas(_json_clone(list(mesas), "mesas"), geography_by_id)
    mesa_by_id = {str(item["id"]): item for item in mesa_items}
    result_items = _validate_results(
        _json_clone(list(results), "results"),
        election_slug=str(election_item["slug"]),
        data_version=data_version,
        candidate_ids=candidate_ids,
        geographies=geography_by_id,
        mesas=mesa_by_id,
        parser_versions=parser_versions,
        legacy_fixture_accounting=legacy_fixture_accounting,
    )
    _validate_exact_summary_rollup(summary_item, result_items)
    evidence_items = _validate_evidence(
        _json_clone(list(evidence), "evidence"),
        data_version=data_version,
        mesas=mesa_by_id,
        parser_versions=parser_versions,
    )
    raw_evidence_has_legacy_projection = any(
        isinstance(item, Mapping) and "source_index_url" not in item for item in evidence
    )
    handling = (
        {}
        if raw_evidence_has_legacy_projection
        else _validate_evidence_handling(evidence_handling or {}, evidence_items)
    )
    comparison_items = _validate_comparisons(
        comparisons or {},
        mesa_by_id,
        artifact_hashes=artifact_hashes,
        source_artifacts=source_artifacts,
        comparison_authorization=comparison_authorization,
    )
    bulletin_items = _validate_bulletins(
        _json_clone(list(bulletins), "bulletins"),
        data_version=data_version,
        candidate_ids=candidate_ids,
    )
    signal_items = _validate_review_signals(
        _json_clone(list(review_signals), "review_signals"),
        methodology_version=str(manifest_copy["methodology_version"]),
        data_version=data_version,
        election_slug=str(election_item["slug"]),
        candidate_ids=candidate_ids,
        mesas=mesa_by_id,
        parser_versions=parser_versions,
        release_status=str(manifest_copy["status"]),
        release_synthetic=bool(manifest_copy["synthetic"]),
        artifact_hashes=artifact_hashes,
        artifact_locations=artifact_locations,
        statistical_authorization=statistical_authorization,
        evidence_authorization=evidence_authorization,
    )
    provenance_item = _validate_provenance(
        provenance,
        label="provenance",
        data_version=data_version,
        parser_versions=parser_versions,
    )
    dataset_items = _validate_datasets(manifest_copy["datasets"])
    _required_documentary_attestations(
        manifest=manifest_copy,
        summary=summary_item,
        results=result_items,
        attestations=documentary_totals_attestations,
    )
    _validate_release_state(manifest_copy, summary_item, signal_items)
    release = {
        field: manifest_copy[field]
        for field in (
            "release_id",
            "data_version",
            "status",
            "synthetic",
            "created_at",
            "methodology_version",
        )
    }
    snapshot: dict[str, Any] = {
        "release": release,
        "election": election_item,
        "summary": summary_item,
        "geographies": geography_items,
        "mesas": mesa_items,
        "results": result_items,
        "evidence": evidence_items,
        "evidence_handling": handling,
        "comparisons": comparison_items,
        "bulletins": bulletin_items,
        "review_signals": signal_items,
        "datasets": dataset_items,
        "provenance": provenance_item,
    }
    if set(snapshot) != _ROOT_FIELDS:  # defensive check if this module evolves
        raise SnapshotError("internal api_snapshot root shape drifted")
    encoded = canonical_snapshot_bytes(snapshot)
    return ApiSnapshotArtifact(
        snapshot=snapshot,
        canonical_bytes=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )
