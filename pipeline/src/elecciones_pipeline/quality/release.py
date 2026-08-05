"""Release gates kept independent of ingestion and analytical implementations.

The functions in this module deliberately accept plain mappings.  That makes the
gate usable before a release is materialised, and prevents a parser or an
analytics convenience model from silently defining what is safe to publish.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any, cast
from urllib.parse import urlsplit

from scipy.stats import beta as beta_distribution  # type: ignore[import-untyped]

from elecciones_pipeline.analytics.peer_signals import cohort_digest as peer_cohort_digest
from elecciones_pipeline.analytics.priority import DISCLOSURE_EN, DISCLOSURE_ES
from elecciones_pipeline.analytics.simulations import (
    METHODOLOGY_VERSION as SIMULATION_METHODOLOGY_VERSION,
)
from elecciones_pipeline.analytics.simulations import (
    TrustedSimulationInputs,
    canonical_input_hashes,
    decode_signal_key,
    detector_binding_hash,
    detector_bindings,
    run_end_to_end_validation,
    simulation_methodology_hash,
)
from elecciones_pipeline.analytics.simulations import (
    lower_binomial_bound as _lower_binomial_bound,
)
from elecciones_pipeline.analytics.spatial import (
    input_artifact_hash as spatial_input_artifact_hash,
)
from elecciones_pipeline.analytics.spatial import spatial_cohort_digest


class QualityError(ValueError):
    """A release invariant has been violated."""


PERMANENT_DISCLOSURE_ES = DISCLOSURE_ES
PERMANENT_DISCLOSURE_EN = DISCLOSURE_EN


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    detail: str


@dataclass(frozen=True)
class ReleaseReport:
    errors: tuple[Finding, ...]
    warnings: tuple[Finding, ...]
    digest: str

    @property
    def passed(self) -> bool:
        return not self.errors

    def require_passed(self) -> None:
        if self.errors:
            raise QualityError("; ".join(f"{item.code}: {item.detail}" for item in self.errors))


_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?57[ .-]?)?(?:3\d{2}|[1-8]\d)[ .-]?\d{3}[ .-]?\d{4}(?!\d)")
_DOCUMENT = re.compile(r"\b(?:CC|CE|TI|NIT)\s*[:#-]?\s*\d{6,12}\b", re.I)
_LEVELS = ("mesa", "place", "municipality", "department", "national")
_SOURCE_LEGAL_STATUS = {
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
    "pre_count": "preliminary",
    "contextual_baseline": "context_only",
}
_MANIFEST_FIELDS = {
    "$schema",
    "schema_version",
    "release_id",
    "election_slug",
    "data_version",
    "status",
    "release_class",
    "synthetic",
    "created_at",
    "methodology_version",
    "parser_versions",
    "git_commit",
    "sources",
    "datasets",
    "aggregate_reconciled",
    "statistical_validation_passed",
    "wording_validation_passed",
    "notes",
}
_SOURCE_FIELDS = {
    "id",
    "source_type",
    "legal_status",
    "source_url",
    "retrieved_at",
    "content_hash",
    "media_type",
    "byte_size",
    "parser_version",
    "transform_version",
    "coverage",
    "published_grain",
}
_DATASET_FIELDS = {
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
_FACT_PROVENANCE = (
    "data_version",
    "source_type",
    "legal_status",
    "source_url",
    "retrieved_at",
    "content_hash",
    "parser_version",
    "transform_version",
)


def canonical_hash(value: Any) -> str:
    """Hash JSON independent of input mapping or row order supplied by callers."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finding(code: str, detail: str) -> Finding:
    return Finding(code, detail)


def _require_mapping(value: object, label: str, errors: list[Finding]) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    errors.append(_finding("schema", f"{label} must be an object"))
    return {}


def validate_manifest(manifest: Mapping[str, Any]) -> tuple[Finding, ...]:
    """Check active manifest shape, source provenance, and coverage arithmetic."""
    errors: list[Finding] = []
    unexpected = set(manifest) - _MANIFEST_FIELDS
    if unexpected:
        errors.append(_finding("schema", f"manifest has unexpected fields: {sorted(unexpected)!r}"))
    required = (
        "schema_version",
        "release_id",
        "election_slug",
        "data_version",
        "status",
        "created_at",
        "methodology_version",
        "git_commit",
    )
    for field in required:
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            errors.append(_finding("schema", f"manifest.{field} is required"))
    if manifest.get("release_id") != manifest.get("data_version"):
        errors.append(_finding("release_identity", "release_id must equal data_version"))
    if manifest.get("status") not in {"fixture", "candidate", "published", "withdrawn"}:
        errors.append(_finding("schema", "manifest.status is invalid"))
    if manifest.get("release_class", "standard") not in {"standard", "context_only"}:
        errors.append(_finding("schema", "manifest.release_class is invalid"))
    if manifest.get("schema_version") != "1.0.0":
        errors.append(_finding("schema", "manifest.schema_version must be 1.0.0"))
    _validate_timestamp(manifest.get("created_at"), "manifest", errors, field="created_at")
    for field in (
        "synthetic",
        "aggregate_reconciled",
        "statistical_validation_passed",
        "wording_validation_passed",
    ):
        if not isinstance(manifest.get(field), bool):
            errors.append(_finding("schema", f"manifest.{field} must be boolean"))
    parser_versions = manifest.get("parser_versions")
    if (
        not isinstance(parser_versions, Mapping)
        or not parser_versions
        or any(
            not isinstance(key, str) or not key or not isinstance(value, str) or not value
            for key, value in parser_versions.items()
        )
    ):
        errors.append(_finding("schema", "manifest.parser_versions must be non-empty strings"))
    notes = manifest.get("notes")
    if not isinstance(notes, Mapping) or any(
        not isinstance(notes.get(locale), str) or not notes[locale] for locale in ("es", "en")
    ):
        errors.append(_finding("schema", "manifest.notes requires non-empty es and en text"))
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        return tuple(errors + [_finding("schema", "manifest.sources must be a non-empty list")])
    source_ids: set[str] = set()
    for index, raw in enumerate(sources):
        source = _require_mapping(raw, f"sources[{index}]", errors)
        unexpected_source = set(source) - _SOURCE_FIELDS
        if unexpected_source:
            errors.append(
                _finding(
                    "schema",
                    f"sources[{index}] has unexpected fields: {sorted(unexpected_source)!r}",
                )
            )
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(_finding("provenance", f"sources[{index}].id is required"))
        elif source_id in source_ids:
            errors.append(_finding("provenance", f"duplicate source id {source_id}"))
        else:
            source_ids.add(source_id)
        digest = source.get("content_hash")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(
                _finding("provenance", f"source {source_id!r} needs a SHA-256 content_hash")
            )
        if not isinstance(source.get("source_url"), str) or not source["source_url"].startswith(
            "https://"
        ):
            errors.append(_finding("provenance", f"source {source_id!r} needs an HTTPS source_url"))
        for field in (
            "source_type",
            "legal_status",
            "retrieved_at",
            "media_type",
            "parser_version",
            "transform_version",
        ):
            if not isinstance(source.get(field), str) or not source[field]:
                errors.append(_finding("provenance", f"source {source_id!r} needs {field}"))
        source_type = source.get("source_type")
        legal_status = source.get("legal_status")
        if source_type not in _SOURCE_LEGAL_STATUS:
            errors.append(_finding("provenance", f"source {source_id!r} has invalid source_type"))
        elif legal_status != _SOURCE_LEGAL_STATUS[source_type]:
            errors.append(
                _finding(
                    "provenance",
                    f"source {source_id!r} has incompatible source_type/legal_status",
                )
            )
        published_grain = source.get("published_grain")
        if published_grain is not None and published_grain not in _LEVELS:
            errors.append(
                _finding("source_grain", f"source {source_id!r} has invalid published_grain")
            )
        if (
            isinstance(source.get("byte_size"), bool)
            or not isinstance(source.get("byte_size"), int)
            or source["byte_size"] < 0
        ):
            errors.append(_finding("provenance", f"source {source_id!r} needs byte_size"))
        _validate_timestamp(source.get("retrieved_at"), f"source {source_id!r}", errors)
        coverage = _require_mapping(
            source.get("coverage"), f"source {source_id!r}.coverage", errors
        )
        _validate_coverage(coverage, str(source_id), errors)
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        errors.append(_finding("schema", "manifest.datasets must be a non-empty list"))
    else:
        dataset_ids: set[str] = set()
        for index, raw in enumerate(datasets):
            dataset = _require_mapping(raw, f"datasets[{index}]", errors)
            _validate_dataset(dataset, index, dataset_ids, errors)
    if manifest.get("release_class") == "context_only":
        if manifest.get("synthetic") is not False:
            errors.append(_finding("context_only", "context_only releases must be non-synthetic"))
        if any(
            not isinstance(source, Mapping)
            or source.get("source_type") != "contextual_baseline"
            or source.get("legal_status") != "context_only"
            for source in sources
        ):
            errors.append(
                _finding(
                    "context_only",
                    "context_only releases may contain only "
                    "contextual_baseline/context_only sources",
                )
            )
        if isinstance(datasets, list) and any(
            not isinstance(dataset, Mapping)
            or not isinstance(dataset.get("filters"), Mapping)
            or dataset["filters"].get("source_type") != "contextual_baseline"
            or dataset["filters"].get("legal_status") != "context_only"
            for dataset in datasets
        ):
            errors.append(
                _finding(
                    "context_only",
                    "context_only datasets must declare contextual_baseline/context_only filters",
                )
            )
        if manifest.get("statistical_validation_passed") is not False:
            errors.append(
                _finding(
                    "context_only",
                    "context_only releases must explicitly disable statistical validation",
                )
            )
    return tuple(sorted(errors))


def _validate_timestamp(
    value: object,
    label: str,
    errors: list[Finding],
    *,
    field: str = "retrieved_at",
) -> None:
    if not isinstance(value, str) or not value:
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(_finding("provenance", f"{label}.{field} must be ISO-8601"))
        return
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(_finding("provenance", f"{label}.{field} must include a timezone"))


def _validate_dataset(
    dataset: Mapping[str, Any],
    index: int,
    seen: set[str],
    errors: list[Finding],
) -> None:
    unexpected = set(dataset) - _DATASET_FIELDS
    if unexpected:
        errors.append(
            _finding(
                "schema",
                f"datasets[{index}] has unexpected fields: {sorted(unexpected)!r}",
            )
        )
    identifier = dataset.get("id")
    if not isinstance(identifier, str) or not identifier:
        errors.append(_finding("dataset", f"datasets[{index}].id is required"))
    elif identifier in seen:
        errors.append(_finding("dataset", f"duplicate dataset id {identifier}"))
    else:
        seen.add(identifier)
    if dataset.get("format") not in {"csv", "parquet", "json"}:
        errors.append(_finding("dataset", f"dataset {identifier!r} has invalid format"))
    for field in ("url", "schema_url"):
        value = dataset.get(field)
        if not isinstance(value, str) or not value.startswith("https://"):
            errors.append(_finding("dataset", f"dataset {identifier!r} needs HTTPS {field}"))
    if not isinstance(dataset.get("content_hash"), str) or not _SHA256.fullmatch(
        dataset["content_hash"]
    ):
        errors.append(_finding("dataset", f"dataset {identifier!r} needs a SHA-256 hash"))
    for field in ("record_count", "byte_size"):
        value = dataset.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(_finding("dataset", f"dataset {identifier!r} needs nonnegative {field}"))
    title = dataset.get("title")
    if not isinstance(title, Mapping) or any(
        not isinstance(title.get(locale), str) or not title[locale] for locale in ("es", "en")
    ):
        errors.append(_finding("dataset", f"dataset {identifier!r} needs bilingual title"))
    filters = dataset.get("filters")
    if not isinstance(filters, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in filters.items()
    ):
        errors.append(_finding("dataset", f"dataset {identifier!r} has invalid filters"))


def _validate_coverage(coverage: Mapping[str, Any], source_id: str, errors: list[Finding]) -> None:
    labels = ("expected", "retrieved", "parsed", "missing", "ambiguous", "excluded")
    raw_counts = {label: coverage.get(label) for label in labels}
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in raw_counts.values()
    ):
        errors.append(_finding("coverage", f"source {source_id!r} has invalid coverage counts"))
        return
    counts = {label: cast(int, raw_counts[label]) for label in labels}
    if not counts["parsed"] <= counts["retrieved"] <= counts["expected"]:
        errors.append(
            _finding("coverage", f"source {source_id!r} violates parsed <= retrieved <= expected")
        )
    if (
        counts["parsed"] + counts["missing"] + counts["ambiguous"] + counts["excluded"]
        != counts["expected"]
    ):
        errors.append(
            _finding("coverage", f"source {source_id!r} terminal coverage does not equal expected")
        )


def _identity(fact: Mapping[str, Any]) -> tuple[str, str, str, str]:
    identity = fact.get("identity", fact)
    if not isinstance(identity, Mapping):
        raise QualityError("fact identity must be an object")
    values = tuple(identity.get(name) for name in ("department", "municipality", "place", "mesa"))
    if not all(isinstance(value, str) and value for value in values):
        raise QualityError("fact identity needs department, municipality, place and mesa")
    return values  # type: ignore[return-value]


def _fact_values(fact: Mapping[str, Any]) -> Mapping[str, int]:
    values = fact.get("values")
    if not isinstance(values, Mapping):
        raise QualityError("fact values must be an object")
    typed: dict[str, int] = {}
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise QualityError(f"value {key!r} must be a nonnegative integer")
        typed[str(key)] = value
    return typed


def validate_value_states(facts: Iterable[Mapping[str, Any]]) -> tuple[Finding, ...]:
    """Zero is observed data; unavailable and unknown never become zero."""
    errors: list[Finding] = []
    for number, fact in enumerate(facts):
        state = fact.get("value_state", "observed")
        value = fact.get("value")
        if state == "observed":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(
                    _finding(
                        "value_state", f"fact {number}: observed value must be nonnegative integer"
                    )
                )
        elif state in {"unknown", "unavailable"}:
            if value is not None:
                errors.append(
                    _finding("value_state", f"fact {number}: {state} value must be null, not zero")
                )
        else:
            errors.append(_finding("value_state", f"fact {number}: invalid value_state {state!r}"))
    return tuple(sorted(errors))


def validate_arithmetic(
    facts: Iterable[Mapping[str, Any]], rules: Mapping[str, tuple[tuple[str, ...], str]]
) -> tuple[Finding, ...]:
    """Validate declared source-local identities without crossing source layers."""
    errors: list[Finding] = []
    for number, fact in enumerate(facts):
        source = fact.get("source_id")
        rule = rules.get(source) if isinstance(source, str) else None
        if rule is None:
            continue
        left, right = rule
        try:
            values = _fact_values(fact)
        except QualityError as exc:
            errors.append(_finding("arithmetic", f"fact {number}: {exc}"))
            continue
        if (
            set((*left, right)).issubset(values)
            and sum(values[name] for name in left) != values[right]
        ):
            errors.append(
                _finding("arithmetic", f"fact {number} violates {source} accounting identity")
            )
    return tuple(sorted(errors))


def validate_fact_layers(
    facts: Iterable[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    methodology_version: object = None,
    data_version: object = None,
) -> tuple[Finding, ...]:
    """Require complete fact provenance and prohibit inferred mesa finality.

    A final or scrutiny source may publish only the grain explicitly recorded
    on the fact. Inferred mesa claims are always prohibited.
    """
    errors: list[Finding] = []
    seen: set[tuple[object, ...]] = set()
    for number, fact in enumerate(facts):
        try:
            identity = _identity(fact)
        except QualityError as exc:
            errors.append(_finding("identity", f"fact {number}: {exc}"))
            continue
        source_id = fact.get("source_id")
        source = sources.get(source_id) if isinstance(source_id, str) else None
        grain = fact.get("grain")
        if source is None:
            errors.append(_finding("traceability", f"fact {number} references unknown source"))
        for field in _FACT_PROVENANCE:
            value = fact.get(field)
            if not isinstance(value, str) or not value:
                errors.append(_finding("provenance", f"fact {number} lacks {field}"))
                continue
            if field == "data_version":
                continue
            if source is not None and value != source.get(field):
                errors.append(_finding("provenance", f"fact {number} {field} differs from source"))
        _validate_timestamp(fact.get("retrieved_at"), f"fact {number}", errors)
        source_url = fact.get("source_url")
        if isinstance(source_url, str) and not source_url.startswith("https://"):
            errors.append(_finding("provenance", f"fact {number} source_url must be HTTPS"))
        content_hash = fact.get("content_hash")
        if isinstance(content_hash, str) and not _SHA256.fullmatch(content_hash):
            errors.append(_finding("provenance", f"fact {number} content_hash is not SHA-256"))
        if data_version is not None and fact.get("data_version") != data_version:
            errors.append(_finding("provenance", f"fact {number} has a different data_version"))
        if grain not in _LEVELS:
            errors.append(_finding("grain", f"fact {number} has invalid grain"))
        if grain == "mesa" and fact.get("inferred") is True:
            errors.append(_finding("mesa_inference", f"fact {number} is an inferred mesa fact"))
        if fact.get("source_type") in {"final_declaration", "scrutiny"} and (
            fact.get("published_grain") != grain or fact.get("inferred") is not False
        ):
            errors.append(
                _finding(
                    "source_grain",
                    f"fact {number} is not explicitly published at its claimed source grain",
                )
            )
        manifest_grain = source.get("published_grain") if source is not None else None
        if manifest_grain is not None and (
            grain != manifest_grain or fact.get("published_grain") != manifest_grain
        ):
            errors.append(
                _finding(
                    "source_grain",
                    f"fact {number} does not match its manifest-declared published grain",
                )
            )
        if grain == "mesa" and not isinstance(fact.get("source_layer"), str):
            errors.append(_finding("source_layer", f"fact {number} lacks source_layer"))
        if fact.get("join_status") == "ambiguous":
            errors.append(
                _finding("ambiguous_join", f"fact {number} has an ambiguous geography join")
            )
        if methodology_version is not None and fact.get("methodology_version") not in {
            None,
            methodology_version,
        }:
            errors.append(
                _finding("methodology", f"fact {number} has a different methodology version")
            )
        if fact.get("is_rollup") is True and source is not None and not _source_complete(source):
            errors.append(
                _finding("partial_rollup", f"fact {number} derives from incomplete source")
            )
        key = (
            source_id,
            identity,
            fact.get("metric"),
            fact.get("record_type"),
            fact.get("party_id"),
        )
        if grain == "mesa" and key in seen:
            errors.append(
                _finding("duplicate_identity", f"duplicate mesa identity for source {source_id!r}")
            )
        seen.add(key)
    return tuple(sorted(errors))


def _source_complete(source: Mapping[str, Any]) -> bool:
    coverage = source.get("coverage")
    return isinstance(coverage, Mapping) and (
        coverage.get("expected") == coverage.get("parsed")
        and coverage.get("missing") == 0
        and coverage.get("ambiguous") == 0
        and coverage.get("excluded") == 0
    )


def exact_rollup(facts: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Produce mesa through national totals, exactly and deterministically."""
    rows = tuple(
        fact
        for fact in facts
        if (
            fact.get("grain") == "mesa"
            and fact.get("published_grain") == "mesa"
            and fact.get("inferred") is not True
        )
    )
    if not rows:
        return ()
    if all(isinstance(fact.get("values"), Mapping) for fact in rows):
        return _exact_wide_rollup(rows)
    if all(isinstance(fact.get("metric"), str) for fact in rows):
        return _exact_long_rollup(rows)
    raise QualityError("mesa facts mix incompatible wide and long representations")


def _rollup_keys(identity: tuple[str, str, str, str]) -> dict[str, tuple[str, ...]]:
    return {
        "mesa": identity,
        "place": identity[:3],
        "municipality": identity[:2],
        "department": identity[:1],
        "national": ("CO",),
    }


def _exact_wide_rollup(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    seen: set[tuple[str, tuple[str, str, str, str]]] = set()
    field_sets: dict[str, frozenset[str]] = {}
    totals: dict[tuple[str, str, tuple[str, ...]], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for fact in rows:
        source = fact.get("source_id")
        if not isinstance(source, str) or not source:
            raise QualityError("fact source_id is required")
        identity = _identity(fact)
        key = (source, identity)
        if key in seen:
            raise QualityError("duplicate mesa identity cannot be rolled up")
        seen.add(key)
        values = _fact_values(fact)
        fields = frozenset(values)
        if source in field_sets and fields != field_sets[source]:
            raise QualityError(f"source {source!r} has a partial metric field set")
        field_sets[source] = fields
        for level, hierarchy_key in _rollup_keys(identity).items():
            for field, value in values.items():
                totals[(source, level, hierarchy_key)][field] += value
    return tuple(
        {"source_id": source, "level": level, "key": key, "values": dict(sorted(values.items()))}
        for (source, level, key), values in sorted(totals.items())
    )


def _exact_long_rollup(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    seen: set[tuple[object, ...]] = set()
    totals: dict[tuple[object, ...], int] = defaultdict(int)
    for fact in rows:
        source_layer = fact.get("source_layer")
        metric = fact.get("metric")
        if not isinstance(source_layer, str) or not source_layer:
            raise QualityError("long fact source_layer is required")
        if not isinstance(metric, str) or not metric:
            raise QualityError("long fact metric is required")
        identity = _identity(fact)
        semantic = (
            source_layer,
            identity,
            metric,
            fact.get("record_type"),
            fact.get("party_id"),
        )
        if semantic in seen:
            raise QualityError("duplicate semantic mesa fact cannot be rolled up")
        seen.add(semantic)
        if fact.get("value_state") != "observed":
            continue
        value = fact.get("value")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise QualityError("observed long fact value must be a nonnegative integer")
        for level, hierarchy_key in _rollup_keys(identity).items():
            totals[
                (
                    source_layer,
                    level,
                    hierarchy_key,
                    metric,
                    fact.get("record_type"),
                    fact.get("party_id"),
                )
            ] += value
    return tuple(
        {
            "source_layer": source_layer,
            "level": level,
            "key": key,
            "metric": metric,
            "record_type": record_type,
            "party_id": party_id,
            "value": value,
        }
        for (
            source_layer,
            level,
            key,
            metric,
            record_type,
            party_id,
        ), value in sorted(totals.items(), key=lambda item: repr(item[0]))
    )


def _declared_rollup_errors(facts: Sequence[Mapping[str, Any]]) -> tuple[Finding, ...]:
    declared = [
        fact for fact in facts if fact.get("grain") != "mesa" and fact.get("is_rollup") is True
    ]
    if not declared:
        return ()
    try:
        computed = exact_rollup(facts)
    except QualityError as exc:
        return (_finding("aggregate_reconciliation", str(exc)),)
    wide = {
        (row["source_id"], row["level"], row["key"]): row["values"]
        for row in computed
        if "source_id" in row
    }
    long = {
        (
            row["source_layer"],
            row["level"],
            row["key"],
            row["metric"],
            row["record_type"],
            row["party_id"],
        ): row["value"]
        for row in computed
        if "source_layer" in row
    }
    errors: list[Finding] = []
    for number, fact in enumerate(declared):
        try:
            identity = _identity(fact)
        except QualityError:
            continue
        level = str(fact["grain"])
        if level not in _LEVELS:
            continue
        key = _rollup_keys(identity)[level]
        expected: object
        observed: object
        if isinstance(fact.get("values"), Mapping):
            expected = wide.get((fact.get("source_id"), level, key))
            try:
                observed = _fact_values(fact)
            except QualityError:
                continue
        else:
            expected = long.get(
                (
                    fact.get("source_layer"),
                    level,
                    key,
                    fact.get("metric"),
                    fact.get("record_type"),
                    fact.get("party_id"),
                )
            )
            observed = fact.get("value")
        if expected is None or observed != expected:
            errors.append(
                _finding(
                    "aggregate_reconciliation",
                    f"declared rollup fact {number} does not equal its exact mesa rollup",
                )
            )
    return tuple(errors)


def _reconciliation_observations(
    facts: Sequence[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[tuple[object, ...], int]], tuple[Finding, ...]]:
    by_source: dict[str, dict[tuple[object, ...], int]] = defaultdict(dict)
    errors: list[Finding] = []
    for number, fact in enumerate(facts):
        source_id = fact.get("source_id")
        grain = fact.get("grain")
        if not isinstance(source_id, str) or grain not in _LEVELS:
            continue
        source = sources.get(source_id)
        # Do not let an identity-shaped aggregate become an observed mesa
        # operand.  A comparison can use aggregate facts only at their exact,
        # explicitly authenticated publication grain.
        if (
            source is None
            or source.get("published_grain") != grain
            or fact.get("published_grain") != grain
            or (grain == "mesa" and fact.get("inferred") is True)
            or any(
                fact.get(field) != source.get(field)
                for field in _FACT_PROVENANCE
                if field != "data_version"
            )
        ):
            continue
        try:
            identity = _identity(fact)
        except QualityError:
            continue
        observations: list[tuple[tuple[object, ...], int]] = []
        values = fact.get("values")
        if isinstance(values, Mapping):
            try:
                typed = _fact_values(fact)
            except QualityError:
                continue
            observations.extend(
                ((grain, identity, "wide", field), value) for field, value in sorted(typed.items())
            )
        elif fact.get("value_state") == "observed":
            value = fact.get("value")
            metric = fact.get("metric")
            if type(value) is int and value >= 0 and isinstance(metric, str) and metric:
                observations.append(
                    (
                        (
                            grain,
                            identity,
                            "long",
                            metric,
                            fact.get("record_type"),
                            fact.get("party_id"),
                        ),
                        value,
                    )
                )
        for key, observed in observations:
            if key in by_source[source_id]:
                errors.append(
                    _finding(
                        "aggregate_reconciliation",
                        f"source {source_id!r} repeats a reconciliation field at fact {number}",
                    )
                )
            by_source[source_id][key] = observed
    return dict(by_source), tuple(errors)


def _aggregate_reconciliation_errors(
    facts: Sequence[Mapping[str, Any]], sources: Mapping[str, Mapping[str, Any]]
) -> tuple[Finding, ...]:
    """Compare exact same-field, same-identity, same-grain controlling observations."""
    observations, observation_errors = _reconciliation_observations(facts, sources)
    errors = list(observation_errors)
    observed_ids = set(observations)
    controlling_ids = sorted(
        source_id
        for source_id in observed_ids
        if sources.get(source_id, {}).get("source_type") in {"final_declaration", "scrutiny"}
    )
    if not controlling_ids:
        errors.append(
            _finding(
                "aggregate_reconciliation",
                "aggregate reconciliation needs an observed scrutiny or final controlling source",
            )
        )
        return tuple(errors)
    comparison_ids = sorted(observed_ids - set(controlling_ids))
    if not comparison_ids and len(controlling_ids) < 2:
        errors.append(
            _finding(
                "aggregate_reconciliation",
                "aggregate reconciliation needs a distinct comparison source",
            )
        )
        return tuple(errors)
    pairs = {
        tuple(sorted((controlling_id, other_id)))
        for controlling_id in controlling_ids
        for other_id in observed_ids
        if other_id != controlling_id
    }
    for left_id, right_id in sorted(pairs):
        left = observations[left_id]
        right = observations[right_id]
        if set(left) != set(right):
            errors.append(
                _finding(
                    "aggregate_reconciliation",
                    f"sources {left_id!r} and {right_id!r} do not expose the same fields, "
                    "identities, and grains",
                )
            )
            continue
        unequal = sorted((key for key in left if left[key] != right[key]), key=repr)
        if unequal:
            errors.append(
                _finding(
                    "aggregate_reconciliation",
                    f"sources {left_id!r} and {right_id!r} disagree on "
                    f"{len(unequal)} same-field same-grain observations",
                )
            )
    return tuple(errors)


def scan_public_text(texts: Iterable[str]) -> tuple[Finding, ...]:
    """Flag common direct identifiers before public artifacts leave the pipeline."""
    errors: list[Finding] = []
    for index, text in enumerate(texts):
        if _EMAIL.search(text):
            errors.append(_finding("pii", f"public text {index} contains an email address"))
        if _PHONE.search(text):
            errors.append(_finding("pii", f"public text {index} contains a phone number"))
        if _DOCUMENT.search(text):
            errors.append(_finding("pii", f"public text {index} contains an identity document"))
    return tuple(sorted(errors))


def audit_allowed_hosts(urls: Iterable[str], allowed_hosts: set[str]) -> tuple[Finding, ...]:
    errors: list[Finding] = []
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            errors.append(_finding("allowlist", f"unapproved public URL {url!r}"))
    return tuple(sorted(errors))


def _statistical_errors(
    summary: Mapping[str, Any],
    *,
    release_id: object,
    replay_inputs: TrustedSimulationInputs | None = None,
    trusted_registry_artifact_hashes: frozenset[str] = frozenset(),
) -> tuple[Finding, ...]:
    errors: list[Finding] = []
    required = {
        "alternative_runs",
        "alternative_seeds",
        "alternative_simulations",
        "artifact_hash",
        "cohort_declarations",
        "release_id",
        "cohort_hash",
        "confusion_by_signal_key",
        "confusion_totals",
        "detector_bindings",
        "detector_validation",
        "detector_hash",
        "empirical_fdr",
        "family_sizes",
        "family_error_count",
        "family_error_upper_confidence",
        "false_discovery_probability",
        "false_discovery_target",
        "injected_discrepancy_detection_rate",
        "injection_spec",
        "input_data_hashes",
        "mean_false_discoveries",
        "methodology_hash",
        "methodology_version",
        "null_runs",
        "null_seeds",
        "null_simulations",
        "power_by_family",
        "run_spec",
        "seeds",
        "simulations",
    }
    missing = required - set(summary)
    if missing:
        return (_finding("statistics", f"validation artifact missing fields: {sorted(missing)!r}"),)
    artifact_hash = summary.get("artifact_hash")
    payload = dict(summary)
    payload.pop("artifact_hash", None)
    try:
        expected_artifact_hash = canonical_hash(payload)
    except (TypeError, ValueError):
        expected_artifact_hash = ""
    if not (
        isinstance(artifact_hash, str)
        and _SHA256.fullmatch(artifact_hash)
        and artifact_hash == expected_artifact_hash
    ):
        return (_finding("statistics", "validation artifact hash does not bind its fields"),)
    # A self-consistent summary is not evidence.  Require the exact original
    # typed rows and an external canonical-hash registry, then replay the real
    # analyzers with the declared configuration before accepting any field.
    if replay_inputs is None or replay_inputs.canonical_input_hash_registry is None:
        return (
            _finding(
                "statistics",
                "validation replay needs trusted original MesaMetrics/SpatialMesa rows "
                "and registry",
            ),
        )
    try:
        trusted_hashes = canonical_input_hashes(replay_inputs)
        registry = dict(replay_inputs.canonical_input_hash_registry)
    except (TypeError, ValueError):
        return (_finding("statistics", "trusted validation replay inputs are invalid"),)
    if registry != trusted_hashes:
        return (_finding("statistics", "trusted input-hash registry does not authenticate rows"),)
    expected_registry_hash = canonical_hash(
        {"schema": "canonical-input-hash-registry-v1", "hashes": registry}
    )
    if (
        replay_inputs.registry_artifact_hash != expected_registry_hash
        or expected_registry_hash not in trusted_registry_artifact_hashes
    ):
        return (
            _finding(
                "statistics",
                "trusted input-hash registry is not bound to immutable registry bytes",
            ),
        )
    if summary.get("input_data_hashes") != trusted_hashes:
        return (_finding("statistics", "artifact input hashes differ from trusted original rows"),)
    if summary.get("release_id") != release_id:
        errors.append(
            _finding("statistics", "validation artifact release_id does not match manifest")
        )

    input_hashes = summary.get("input_data_hashes")
    if (
        not isinstance(input_hashes, Mapping)
        or set(input_hashes)
        not in (
            {"peer"},
            {"peer", "spatial"},
        )
        or any(
            not isinstance(value, str) or not _SHA256.fullmatch(value)
            for value in input_hashes.values()
        )
    ):
        return (_finding("statistics", "validation artifact has invalid exact input data hashes"),)
    include_spatial = "spatial" in input_hashes
    expected_bindings = detector_bindings(include_spatial=include_spatial)
    bindings = summary.get("detector_bindings")
    if bindings != expected_bindings:
        errors.append(
            _finding("statistics", "validation artifact is not bound to the frozen detector code")
        )
    if summary.get("detector_hash") != detector_binding_hash(expected_bindings):
        errors.append(_finding("statistics", "validation artifact detector hash is stale"))
    if summary.get("methodology_version") != SIMULATION_METHODOLOGY_VERSION or summary.get(
        "methodology_hash"
    ) != simulation_methodology_hash(expected_bindings):
        errors.append(_finding("statistics", "validation artifact simulation methodology is stale"))

    declarations = summary.get("cohort_declarations")
    if (
        not isinstance(declarations, Mapping)
        or set(declarations) != set(input_hashes)
        or any(not isinstance(value, Mapping) for value in declarations.values())
    ):
        return (_finding("statistics", "validation artifact has invalid cohort declarations"),)
    cohort_material = {
        "cohort_declarations": declarations,
        "input_data_hashes": input_hashes,
    }
    if summary.get("cohort_hash") != canonical_hash(cohort_material):
        errors.append(
            _finding("statistics", "validation artifact cohort hash does not bind exact inputs")
        )
    peer_declaration = cast(Mapping[str, Any], declarations["peer"])
    try:
        original_peer_cohort = peer_cohort_digest(
            election_slug=peer_declaration["election_slug"],
            data_version=peer_declaration["data_version"],
            source_layer=peer_declaration["source_layer"],
            source_type=peer_declaration["source_type"],
            legal_status=peer_declaration["legal_status"],
            metric=peer_declaration["metric"],
            candidate_id=peer_declaration["candidate_id"],
            expected_family_count=peer_declaration["expected_family_count"],
            expected_family_digest=peer_declaration["expected_family_digest"],
            input_artifact_hash=peer_declaration["input_artifact_hash"],
        )
    except (KeyError, TypeError, ValueError):
        original_peer_cohort = ""
    if original_peer_cohort != peer_declaration.get("cohort_hash"):
        errors.append(_finding("statistics", "peer cohort declaration is not internally bound"))
    spatial_declaration: Mapping[str, Any] | None = None
    if include_spatial:
        spatial_declaration = cast(Mapping[str, Any], declarations["spatial"])
        try:
            original_spatial_cohort = spatial_cohort_digest(
                peer_residual_artifact_hash=spatial_declaration["peer_residual_artifact_hash"],
                election_slug=spatial_declaration["election_slug"],
                data_version=spatial_declaration["data_version"],
                source_layer=spatial_declaration["source_layer"],
                source_type=spatial_declaration["source_type"],
                legal_status=spatial_declaration["legal_status"],
                metric=spatial_declaration["metric"],
                candidate_id=spatial_declaration["candidate_id"],
                peer_methodology_version=spatial_declaration["peer_methodology_version"],
                coordinate_source_url=spatial_declaration["coordinate_source_url"],
                coordinate_source_hash=spatial_declaration["coordinate_source_hash"],
                coordinate_accuracy_m=spatial_declaration["coordinate_accuracy_m"],
                coordinate_grain=spatial_declaration["coordinate_grain"],
                expected_family_count=spatial_declaration["expected_family_count"],
                expected_family_digest=spatial_declaration["expected_family_digest"],
                expected_mesa_count=spatial_declaration["expected_mesa_count"],
                expected_mesa_digest=spatial_declaration["expected_mesa_digest"],
                expected_mesa_membership_digest=spatial_declaration[
                    "expected_mesa_membership_digest"
                ],
            )
        except (KeyError, TypeError, ValueError):
            original_spatial_cohort = ""
        if original_spatial_cohort != spatial_declaration.get("cohort_hash"):
            errors.append(
                _finding("statistics", "spatial cohort declaration is not internally bound")
            )

    family_sizes = summary.get("family_sizes")
    if (
        not isinstance(family_sizes, Mapping)
        or not family_sizes
        or any(
            not isinstance(key, str) or not key or type(value) is not int or value < 1
            for key, value in family_sizes.items()
        )
    ):
        return (_finding("statistics", "validation artifact needs non-empty family sizes"),)
    decoded_families: dict[str, str] = {}
    try:
        for key in family_sizes:
            analyzer, family_id, analysis_unit_id = decode_signal_key(key)
            if (
                analyzer not in expected_bindings
                or analyzer in decoded_families
                or analysis_unit_id != "__family__"
            ):
                raise ValueError
            decoded_families[analyzer] = family_id
    except ValueError:
        return (_finding("statistics", "validation artifact family keys are not canonical"),)
    if set(decoded_families) != set(expected_bindings):
        return (_finding("statistics", "validation artifact family sizes do not match detectors"),)

    null_count = summary.get("null_simulations")
    alternative_count = summary.get("alternative_simulations")
    simulations = summary.get("simulations")
    if (
        type(null_count) is not int
        or null_count < 100
        or type(alternative_count) is not int
        or alternative_count < 100
        or type(simulations) is not int
        or simulations != null_count + alternative_count
    ):
        return (
            _finding(
                "statistics",
                "at least 100 separate pure-null and alternative simulations are required",
            ),
        )
    seeds = summary.get("seeds")
    null_seeds = summary.get("null_seeds")
    alternative_seeds = summary.get("alternative_seeds")
    if not all(
        isinstance(value, (list, tuple)) for value in (seeds, null_seeds, alternative_seeds)
    ):
        return (_finding("statistics", "validation artifact seeds do not match runs"),)
    typed_seeds = cast(Sequence[object], seeds)
    typed_null_seeds = cast(Sequence[object], null_seeds)
    typed_alternative_seeds = cast(Sequence[object], alternative_seeds)
    if (
        len(typed_null_seeds) != null_count
        or len(typed_alternative_seeds) != alternative_count
        or tuple(typed_seeds) != tuple(typed_null_seeds) + tuple(typed_alternative_seeds)
        or len(set(typed_seeds)) != simulations
        or any(type(value) is not int or value < 0 for value in typed_seeds)
    ):
        errors.append(_finding("statistics", "validation artifact seeds do not match runs"))

    run_spec = summary.get("run_spec")
    injection_spec = summary.get("injection_spec")
    if (
        not isinstance(run_spec, Mapping)
        or run_spec.get("null_runs") != null_count
        or run_spec.get("alternative_runs") != alternative_count
        or run_spec.get("run_arms") != ["pure_null", "alternative"]
        or not isinstance(injection_spec, Mapping)
    ):
        errors.append(_finding("statistics", "validation artifact has invalid separated run specs"))
        injection_spec = {}
    injection_count = injection_spec.get("count_per_run")
    injection_effect = injection_spec.get("effect_fraction_of_denominator")
    if (
        type(injection_count) is not int
        or injection_count < 1
        or isinstance(injection_effect, bool)
        or not isinstance(injection_effect, (int, float))
        or not isfinite(float(injection_effect))
        or not 0 < float(injection_effect) <= 1
        or injection_spec.get("key_schema")
        != "canonical-json-[detector_id,family_id,analysis_unit_id]"
    ):
        errors.append(_finding("statistics", "validation artifact injection spec is invalid"))

    declared_seed = summary.get("seed")
    if type(declared_seed) is not int or declared_seed < 0:
        errors.append(_finding("statistics", "validation artifact master seed is invalid"))

    raw_null_runs = summary.get("null_runs")
    raw_alternative_runs = summary.get("alternative_runs")
    if (
        not isinstance(raw_null_runs, (list, tuple))
        or not isinstance(raw_alternative_runs, (list, tuple))
        or len(raw_null_runs) != null_count
        or len(raw_alternative_runs) != alternative_count
    ):
        return (_finding("statistics", "validation artifact run evidence is incomplete"),)

    def validate_run(
        raw: object,
        *,
        mode: str,
        index: int,
        expected_seed: object,
    ) -> tuple[set[str], set[str], float | None] | None:
        if not isinstance(raw, Mapping):
            return None
        if (
            raw.get("mode") != mode
            or raw.get("run_index") != index
            or raw.get("seed") != expected_seed
        ):
            return None
        for field in ("peer_input_artifact_hash", "peer_cohort_hash"):
            if not isinstance(raw.get(field), str) or not _SHA256.fullmatch(raw[field]):
                return None
        try:
            expected_peer_run_cohort = peer_cohort_digest(
                election_slug=peer_declaration["election_slug"],
                data_version=peer_declaration["data_version"],
                source_layer=peer_declaration["source_layer"],
                source_type=peer_declaration["source_type"],
                legal_status=peer_declaration["legal_status"],
                metric=peer_declaration["metric"],
                candidate_id=peer_declaration["candidate_id"],
                expected_family_count=peer_declaration["expected_family_count"],
                expected_family_digest=peer_declaration["expected_family_digest"],
                input_artifact_hash=raw["peer_input_artifact_hash"],
            )
        except (KeyError, TypeError, ValueError):
            return None
        if raw.get("peer_cohort_hash") != expected_peer_run_cohort:
            return None
        spatial_fields = (
            "spatial_residual_data_hash",
            "spatial_peer_residual_artifact_hash",
            "spatial_cohort_hash",
            "spatial_input_artifact_hash",
        )
        if include_spatial:
            if (
                any(
                    not isinstance(raw.get(field), str) or not _SHA256.fullmatch(raw[field])
                    for field in spatial_fields
                )
                or spatial_declaration is None
            ):
                return None
            try:
                expected_spatial_run_cohort = spatial_cohort_digest(
                    peer_residual_artifact_hash=raw["spatial_peer_residual_artifact_hash"],
                    election_slug=spatial_declaration["election_slug"],
                    data_version=spatial_declaration["data_version"],
                    source_layer=spatial_declaration["source_layer"],
                    source_type=spatial_declaration["source_type"],
                    legal_status=spatial_declaration["legal_status"],
                    metric=spatial_declaration["metric"],
                    candidate_id=spatial_declaration["candidate_id"],
                    peer_methodology_version=spatial_declaration["peer_methodology_version"],
                    coordinate_source_url=spatial_declaration["coordinate_source_url"],
                    coordinate_source_hash=spatial_declaration["coordinate_source_hash"],
                    coordinate_accuracy_m=spatial_declaration["coordinate_accuracy_m"],
                    coordinate_grain=spatial_declaration["coordinate_grain"],
                    expected_family_count=spatial_declaration["expected_family_count"],
                    expected_family_digest=spatial_declaration["expected_family_digest"],
                    expected_mesa_count=spatial_declaration["expected_mesa_count"],
                    expected_mesa_digest=spatial_declaration["expected_mesa_digest"],
                    expected_mesa_membership_digest=spatial_declaration[
                        "expected_mesa_membership_digest"
                    ],
                )
                expected_spatial_input = spatial_input_artifact_hash(
                    peer_residual_artifact_hash=raw["spatial_peer_residual_artifact_hash"],
                    coordinate_source_hash=spatial_declaration["coordinate_source_hash"],
                    analysis_unit_digest=spatial_declaration["expected_family_digest"],
                    mesa_membership_digest=spatial_declaration["expected_mesa_membership_digest"],
                )
            except (KeyError, TypeError, ValueError):
                return None
            if (
                raw.get("spatial_cohort_hash") != expected_spatial_run_cohort
                or raw.get("spatial_input_artifact_hash") != expected_spatial_input
            ):
                return None
        elif any(raw.get(field) is not None for field in spatial_fields):
            return None

        injected_raw = raw.get("injected_keys")
        flagged_raw = raw.get("flagged_keys")
        if not isinstance(injected_raw, (list, tuple)) or not isinstance(
            flagged_raw, (list, tuple)
        ):
            return None
        injected_values = tuple(injected_raw)
        flagged_values = tuple(flagged_raw)
        if (
            any(not isinstance(key, str) for key in (*injected_values, *flagged_values))
            or tuple(sorted(set(injected_values))) != injected_values
            or tuple(sorted(set(flagged_values))) != flagged_values
        ):
            return None
        try:
            decoded_injected = [decode_signal_key(cast(str, key)) for key in injected_values]
            decoded_flagged = [decode_signal_key(cast(str, key)) for key in flagged_values]
        except ValueError:
            return None
        allowed_family_ids = set(decoded_families.values())
        if any(
            detector_id not in expected_bindings or family_id not in allowed_family_ids
            for detector_id, family_id, _analysis_unit_id in (*decoded_injected, *decoded_flagged)
        ):
            return None
        injected = {cast(str, key) for key in injected_values}
        flagged = {cast(str, key) for key in flagged_values}
        if mode == "pure_null" and injected:
            return None
        if mode == "alternative" and (
            not injected
            or type(injection_count) is not int
            or len(injected) != injection_count
            or any(
                detector_id != "peer" or family_id != decoded_families.get("peer")
                for detector_id, family_id, _ in decoded_injected
            )
        ):
            return None
        true_positive = len(flagged & injected)
        false_positive = len(flagged - injected)
        false_negative = len(injected - flagged)
        if (
            raw.get("true_positive") != true_positive
            or raw.get("false_positive") != false_positive
            or raw.get("false_negative") != false_negative
            or raw.get("false_discoveries") != false_positive
        ):
            return None
        fdp = raw.get("fdp")
        if mode == "pure_null":
            if fdp is not None:
                return None
            return injected, flagged, None
        expected_fdp = false_positive / max(len(flagged), 1)
        if (
            isinstance(fdp, bool)
            or not isinstance(fdp, (int, float))
            or not isfinite(float(fdp))
            or abs(float(fdp) - expected_fdp) > 1e-12
        ):
            return None
        return injected, flagged, expected_fdp

    validated_null: list[tuple[set[str], set[str], float | None]] = []
    validated_alternative: list[tuple[set[str], set[str], float | None]] = []
    for index, raw in enumerate(raw_null_runs):
        validated = validate_run(
            raw,
            mode="pure_null",
            index=index,
            expected_seed=typed_null_seeds[index],
        )
        if validated is None:
            return (_finding("statistics", "pure-null run evidence is invalid"),)
        validated_null.append(validated)
    for index, raw in enumerate(raw_alternative_runs):
        validated = validate_run(
            raw,
            mode="alternative",
            index=index,
            expected_seed=typed_alternative_seeds[index],
        )
        if validated is None:
            return (_finding("statistics", "alternative run evidence is invalid"),)
        validated_alternative.append(validated)

    family_errors = sum(1 for _injected, flagged, _fdp in validated_null if flagged)
    null_false_discoveries = sum(len(flagged) for _injected, flagged, _fdp in validated_null)
    upper_bound = (
        1.0
        if family_errors == null_count
        else float(beta_distribution.ppf(0.95, family_errors + 1, null_count - family_errors))
    )
    false_discovery_probability = family_errors / null_count
    mean_false_discoveries = null_false_discoveries / null_count
    empirical_fdr = (
        sum(cast(float, fdp) for _injected, _flagged, fdp in validated_alternative)
        / alternative_count
    )

    computed_by_key: dict[str, dict[str, int]] = defaultdict(
        lambda: {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    )
    for injected, flagged, _fdp in validated_alternative:
        for key in injected & flagged:
            computed_by_key[key]["true_positive"] += 1
        for key in flagged - injected:
            computed_by_key[key]["false_positive"] += 1
        for key in injected - flagged:
            computed_by_key[key]["false_negative"] += 1
    expected_by_key = {key: computed_by_key[key] for key in sorted(computed_by_key)}
    if summary.get("confusion_by_signal_key") != expected_by_key:
        errors.append(
            _finding("statistics", "validation artifact keyed confusion matrix is invalid")
        )
    expected_confusion = {
        label: sum(counts[label] for counts in expected_by_key.values())
        for label in ("true_positive", "false_positive", "false_negative")
    }
    if summary.get("confusion_totals") != expected_confusion:
        errors.append(_finding("statistics", "validation artifact confusion totals are invalid"))
    injected_total = expected_confusion["true_positive"] + expected_confusion["false_negative"]
    power = expected_confusion["true_positive"] / injected_total if injected_total else 0.0
    family_power_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"detected": 0, "injected": 0}
    )
    for key, counts in expected_by_key.items():
        detector_id, family_id, _unit_id = decode_signal_key(key)
        detector_family = json.dumps(
            [detector_id, family_id, "__family__"],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        family_power_counts[detector_family]["detected"] += counts["true_positive"]
        family_power_counts[detector_family]["injected"] += (
            counts["true_positive"] + counts["false_negative"]
        )
    # Mirrors simulations.run_end_to_end_validation exactly, including the
    # unmeasured-power case: a family reached only by a false positive has no
    # injected alternatives, and null power is not zero power.
    expected_power: dict[str, dict[str, object]] = {}
    for family_id, counts in sorted(family_power_counts.items()):
        measured = counts["injected"] > 0
        expected_power[family_id] = {
            **counts,
            "power": counts["detected"] / counts["injected"] if measured else None,
            "lower_confidence_bound": _lower_binomial_bound(counts["detected"], counts["injected"]),
            "status": "measured" if measured else "no_injected_alternatives",
        }
    if summary.get("power_by_family") != expected_power:
        errors.append(_finding("statistics", "validation artifact keyed power is invalid"))

    numeric_expectations = {
        "family_error_upper_confidence": upper_bound,
        "false_discovery_probability": false_discovery_probability,
        "mean_false_discoveries": mean_false_discoveries,
        "empirical_fdr": empirical_fdr,
        "injected_discrepancy_detection_rate": power,
    }
    for field, expected in numeric_expectations.items():
        value = summary.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or abs(float(value) - expected) > 1e-12
        ):
            errors.append(_finding("statistics", f"validation artifact {field} is invalid"))
    if summary.get("family_error_count") != family_errors:
        errors.append(_finding("statistics", "validation artifact family error count is invalid"))
    target = summary.get("false_discovery_target")
    if target != 0.05:
        errors.append(_finding("statistics", "validation artifact false-discovery target changed"))
        target = 0.05
    false_discovery_gate = upper_bound <= target and empirical_fdr <= target
    # The artifact must also be byte-identical to a trusted replay of the
    # analyzer (below), so this cannot be literal equality against a
    # hand-written dict: the two conditions contradict each other and no
    # artifact, valid or forged, can satisfy both.  Assert instead the
    # production-eligibility contract the analyzer actually emits.  This still
    # fails closed today, because the analyzer hardcodes production_eligible
    # to False pending an independent full artifact.
    detector_validation = summary.get("detector_validation")
    peer_validation = (
        detector_validation.get("peer") if isinstance(detector_validation, Mapping) else None
    )
    if not isinstance(peer_validation, Mapping):
        errors.append(_finding("statistics", "detector validation is missing the peer detector"))
    else:
        if peer_validation.get("power_target") != 0.80 or peer_validation.get("confidence") != 0.95:
            errors.append(
                _finding("statistics", "detector validation power target or confidence changed")
            )
        if not (
            peer_validation.get("production_eligible") is True
            and peer_validation.get("trusted_input_registry_verified") is True
            and peer_validation.get("external_family_ledger_verified") is True
            and peer_validation.get("public_signal_forced_false") is False
        ):
            errors.append(
                _finding(
                    "statistics",
                    "peer detector is not production eligible: "
                    f"{peer_validation.get('status')}",
                )
            )
    if include_spatial:
        spatial_validation = (
            detector_validation.get("spatial") if isinstance(detector_validation, Mapping) else None
        )
        if spatial_validation != {
            "status": "unvalidated_ineligible",
            "reason": "no predeclared spatial alternative calibration design",
        }:
            errors.append(
                _finding("statistics", "spatial detector validation eligibility is invalid")
            )
    for family, item in expected_power.items():
        power_by_family = summary.get("power_by_family")
        observed = power_by_family.get(family) if isinstance(power_by_family, Mapping) else None
        if not isinstance(observed, Mapping):
            continue
        lower = _lower_binomial_bound(
            int(cast(int, item["detected"])), int(cast(int, item["injected"]))
        )
        if (
            isinstance(observed.get("lower_confidence_bound"), bool)
            or not isinstance(observed.get("lower_confidence_bound"), (int, float))
            or abs(float(observed["lower_confidence_bound"]) - lower) > 1e-12
        ):
            errors.append(
                _finding("statistics", "validation artifact power confidence bound is invalid")
            )
    # The analyzer derives this gate from per-stratum power.  Recomputing it
    # from per-family counts compares a different quantity and reports a valid
    # artifact as spoofed.  The bounds are still recomputed here rather than
    # trusted; the counts they are computed from are authenticated by the
    # trusted-analyzer replay below.
    stratum_power = summary.get("power_by_stratum")
    if not isinstance(stratum_power, Mapping) or not stratum_power:
        errors.append(_finding("statistics", "validation artifact has no per-stratum power"))
        power_gate = False
    else:
        power_gate = True
        for item in stratum_power.values():
            if not isinstance(item, Mapping):
                errors.append(
                    _finding("statistics", "validation artifact stratum power is invalid")
                )
                power_gate = False
                continue
            bound = _lower_binomial_bound(
                int(cast(int, item.get("detected", 0))), int(cast(int, item.get("injected", 0)))
            )
            observed_bound = item.get("lower_confidence_bound")
            if (
                isinstance(observed_bound, bool)
                or not isinstance(observed_bound, (int, float))
                or abs(float(observed_bound) - bound) > 1e-12
            ):
                errors.append(
                    _finding("statistics", "validation artifact stratum power bound is invalid")
                )
                power_gate = False
                continue
            if bound < 0.80:
                power_gate = False
    if (
        summary.get("false_discovery_gate_passed") is not false_discovery_gate
        or summary.get("injected_discrepancy_gate_passed") is not power_gate
        or summary.get("release_gate_passed") is not (false_discovery_gate and power_gate)
    ):
        errors.append(_finding("statistics", "validation artifact gate booleans are spoofed"))
    if not false_discovery_gate or not power_gate:
        errors.append(
            _finding("statistics", "the authenticated statistical validation gate did not pass")
        )
    # The comparison is intentionally complete, not a selection of convenient
    # summary figures.  Replay even when a derived gate is already red: that
    # keeps provenance diagnostics independent of an artifact's claimed score.
    try:
        replayed = run_end_to_end_validation(
            release_id=cast(str, release_id),
            peer_records=replay_inputs.peer_records,
            spatial_records=replay_inputs.spatial_records,
            simulations=null_count,
            seed=cast(int, declared_seed),
            injected_discrepancies=cast(int, injection_count),
            injection_size=float(cast(float, injection_effect)),
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        errors.append(_finding("statistics", f"trusted analyzer replay failed: {exc}"))
    else:
        if canonical_hash(summary) != canonical_hash(asdict(replayed)):
            errors.append(
                _finding(
                    "statistics",
                    "validation artifact does not exactly match trusted analyzer replay",
                )
            )
    return tuple(errors)


def _has_controlling_final_declaration(sources: Iterable[Mapping[str, Any]]) -> bool:
    return any(
        source.get("source_type") == "final_declaration"
        and source.get("legal_status") == "controlling_final"
        for source in sources
    )


def verify_release(
    manifest: Mapping[str, Any],
    *,
    facts: Sequence[Mapping[str, Any]] = (),
    public_text: Sequence[str] = (),
    public_urls: Sequence[str] = (),
    allowed_hosts: set[str] | None = None,
    statistical_summary: Mapping[str, Any] | None = None,
    statistical_replay_inputs: TrustedSimulationInputs | None = None,
    permanent_wording: str = "",
) -> ReleaseReport:
    """Run all release gates; callers must call :meth:`ReleaseReport.require_passed`."""
    errors = list(validate_manifest(manifest))
    sources = {
        item["id"]: item
        for item in manifest.get("sources", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    errors.extend(
        validate_fact_layers(
            facts, sources, manifest.get("methodology_version"), manifest.get("data_version")
        )
    )
    errors.extend(validate_value_states(facts))
    source_rules = {
        source_id: (("candidate", "blank"), "total")
        for source_id, source in sources.items()
        if source.get("source_type") in {"pre_count", "e14_delegate", "e14_transmission"}
    }
    errors.extend(validate_arithmetic(facts, source_rules))
    try:
        exact_rollup(facts)
    except QualityError as exc:
        errors.append(_finding("aggregate_reconciliation", str(exc)))
    errors.extend(_declared_rollup_errors(facts))
    status = manifest.get("status")
    context_only_release = manifest.get("release_class") == "context_only"
    contextual_source_declared = any(
        source.get("source_type") == "contextual_baseline"
        or source.get("legal_status") == "context_only"
        for source in sources.values()
    )
    contextual_fact_used = any(
        fact.get("source_layer") in {"context_only", "contextual_baseline"}
        or fact.get("source_type") == "contextual_baseline"
        or fact.get("legal_status") == "context_only"
        for fact in facts
    )
    if (contextual_source_declared or contextual_fact_used) and not context_only_release:
        errors.append(
            _finding(
                "analytics_context_only",
                "contextual_baseline/context_only facts cannot enter release analytics",
            )
        )
    if status in {"candidate", "published"} and manifest.get("synthetic") is True:
        errors.append(
            _finding("synthetic_release", "synthetic data may never be candidate or published")
        )
    if status in {"candidate", "published"} and manifest.get("aggregate_reconciled") is not True:
        errors.append(
            _finding(
                "aggregate_reconciliation", "candidate/published release must reconcile aggregates"
            )
        )
    if (
        status in {"candidate", "published"}
        and manifest.get("aggregate_reconciled") is True
        and not context_only_release
    ):
        observed_sources = {
            str(fact.get("source_id")) for fact in facts if isinstance(fact.get("source_id"), str)
        }
        complete_sources = all(
            isinstance(source.get("coverage"), Mapping)
            and source["coverage"].get("expected") == source["coverage"].get("parsed")
            and source["coverage"].get("missing") == 0
            and source["coverage"].get("ambiguous") == 0
            and source["coverage"].get("excluded") == 0
            for source_id, source in sources.items()
            if source_id in observed_sources
        )
        source_grains_declared = all(
            sources.get(source_id, {}).get("published_grain") in _LEVELS
            for source_id in observed_sources
        )
        if len(observed_sources) < 2 or not complete_sources or not source_grains_declared:
            errors.append(
                _finding(
                    "aggregate_reconciliation",
                    "aggregate reconciliation needs complete observations from distinct sources "
                    "with manifest-declared grain",
                )
            )
        errors.extend(_aggregate_reconciliation_errors(facts, sources))
        if status == "published" and not any(
            sources.get(source_id, {}).get("source_type") == "final_declaration"
            for source_id in observed_sources
        ):
            errors.append(
                _finding(
                    "aggregate_reconciliation",
                    "published aggregate reconciliation needs an observed controlling-source "
                    "comparison",
                )
            )
    if status in {"candidate", "published"} and not context_only_release:
        errors.append(
            _finding(
                "statistics_pass_b_pending",
                "candidate/published statistical analytics remain blocked pending "
                "independent pass B",
            )
        )
        errors.append(
            _finding(
                "outcome_pass_b_pending",
                "candidate/published outcome sensitivity remains blocked pending independent "
                "pass B",
            )
        )
        errors.extend(
            _statistical_errors(
                statistical_summary or {},
                release_id=manifest.get("data_version"),
                replay_inputs=statistical_replay_inputs,
                trusted_registry_artifact_hashes=frozenset(
                    str(item["content_hash"])
                    for collection in (manifest.get("sources", ()), manifest.get("datasets", ()))
                    for item in collection
                    if isinstance(item, Mapping) and isinstance(item.get("content_hash"), str)
                ),
            )
        )
        if manifest.get("statistical_validation_passed") is not True:
            errors.append(
                _finding("statistics", "manifest.statistical_validation_passed must be true")
            )
        if manifest.get("wording_validation_passed") is not True:
            errors.append(_finding("permanent_wording", "wording validation must pass"))
        if not facts:
            errors.append(_finding("facts", "candidate/published release needs result facts"))
    if status in {"candidate", "published"} and not (
        PERMANENT_DISCLOSURE_ES in permanent_wording
        and PERMANENT_DISCLOSURE_EN in permanent_wording
    ):
        errors.append(
            _finding(
                "permanent_wording", "permanent disclosure lacks the exact ES and EN audit wording"
            )
        )
    is_published_non_synthetic = (
        status == "published"
        and manifest.get("synthetic") is not True
        and not context_only_release
    )
    if is_published_non_synthetic and not _has_controlling_final_declaration(sources.values()):
        errors.append(
            _finding(
                "final_declaration",
                "published release needs a controlling final-declaration source",
            )
        )
    errors.extend(scan_public_text(public_text))
    if allowed_hosts is not None:
        manifest_urls = [
            str(source["source_url"])
            for source in sources.values()
            if isinstance(source.get("source_url"), str)
        ]
        manifest_urls.extend(
            str(dataset[field])
            for dataset in manifest.get("datasets", ())
            if isinstance(dataset, Mapping)
            for field in ("url", "schema_url")
            if isinstance(dataset.get(field), str)
        )
        errors.extend(audit_allowed_hosts((*manifest_urls, *public_urls), allowed_hosts))
    digest = canonical_hash({"manifest": manifest, "facts": sorted(facts, key=canonical_hash)})
    return ReleaseReport(tuple(sorted(set(errors))), (), digest)
