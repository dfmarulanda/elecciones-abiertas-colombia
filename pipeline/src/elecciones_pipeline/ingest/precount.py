"""Strict adapters for the 2026 Registraduría presidential pre-count.

The public application exposes two reviewed contracts used here:

* ``nomenclator.json`` is an indexed geography graph.  Its published scope
  codes are the only inputs accepted by the aggregate ACT planner.
* ``/json/ACT/PR/{scope}.json`` is the ACT resource.  Mesa resources are
  planned only from identifiers observed in a fetched polling-place ACT's
  ``camaras[].mapagan[].amb`` entries.

This module plans and parses already-fetched public resources.  It performs no
network requests and deliberately contains no fallback URL discovery.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlsplit, urlunsplit


class PrecountSchemaError(ValueError):
    """A source object cannot be interpreted without guessing."""


type ValueState = Literal["observed", "unknown", "unavailable"]
type MetricKind = Literal["count", "percentage"]
type PlanKind = Literal["aggregate", "mesa"]

_REVIEWED_PRECOUNT_HOSTS = frozenset(
    {
        "resultadosprecpresidente2026-1v.registraduria.gov.co",
        "resultadosprecpresidente2026-2v.registraduria.gov.co",
    }
)
_SCOPE_CODE_LENGTHS = {
    1: frozenset({2}),
    2: frozenset({2}),
    3: frozenset({5}),
    4: frozenset({7}),
    # A comuna is an optional nomenclator node.  The service publishes its
    # exact code, rather than a code we can safely derive.  Current official
    # graphs use the same canonical decimal hierarchy widths as other
    # sub-municipal scopes; accepting these published widths keeps the parser
    # forward-compatible without synthesising an ACT path.
    5: frozenset({7, 8, 9}),
    # Domestic polling places use nine digits.  The same official graph also
    # publishes 11-digit places (for example ``28048999000``); mesa IDs append
    # six digits to whichever exact parent width was published.
    6: frozenset({9, 11}),
    7: frozenset({15, 17}),
}
_GRAIN_BY_LEVEL = {
    1: "national",
    2: "department",
    3: "municipality",
    4: "zone",
    5: "comuna",
    6: "polling_place",
    7: "mesa",
}
_ELECTION_SIGLAS = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")
_DIGITS = re.compile(r"^\d+$")
_SCOPE_CHARACTERS = re.compile(r"^[A-Z0-9]+$")
_PERCENTAGE = re.compile(r"^(?:0|[1-9]\d*)(?:,\d+)?%$")
_UNKNOWN_VALUES = frozenset({"DESCONOCIDO", "PENDIENTE", "UNKNOWN"})
_UNAVAILABLE_VALUES = frozenset({"", "N/A", "NA", "NO DISPONIBLE", "SIN DATO"})

_TOTAL_COUNT_FIELDS = (
    "metota",
    "mesesc",
    "meserr",
    "centota",
    "votant",
    "absten",
    "votnul",
    "votnma",
    "votblan",
    "votval",
)
_TOTAL_PERCENTAGE_FIELDS = (
    "pmesesc",
    "pvotant",
    "pabsten",
    "pvotnul",
    "pvotnma",
    "pvotblan",
    "pvotval",
)


@dataclass(frozen=True)
class PrecountScope:
    """One validated node from the official indexed geography graph."""

    election_id: str
    index: int
    code: str
    level: int
    grain: str
    name: str
    slug: str
    mesa_count: int
    parent_indices: tuple[int, ...]
    child_indices: tuple[int, ...]


@dataclass(frozen=True)
class PrecountNomenclator:
    """A deterministic, internally consistent election geography."""

    election_id: str
    scopes: tuple[PrecountScope, ...]

    def scope(self, code: str) -> PrecountScope:
        matches = [scope for scope in self.scopes if scope.code == code]
        if len(matches) != 1:
            raise PrecountSchemaError(f"scope code {code!r} is not unique in the nomenclator")
        return matches[0]


@dataclass(frozen=True)
class PrecountPlanEntry:
    """One ACT URL derived from an explicitly published official identity."""

    source_url: str
    election_id: str
    election_siglas: str
    scope_code: str
    scope_level: int
    grain: str
    kind: PlanKind
    department_code: str
    parent_scope_code: str | None = None


@dataclass(frozen=True)
class PublishedMetric:
    """A source number with its raw representation and semantic state."""

    name: str
    kind: MetricKind
    raw: str | None
    state: ValueState
    value: int | Decimal | None


@dataclass(frozen=True)
class PrecountCandidate:
    """One presidential candidate slate as published in ``partotabla``."""

    camera_code: str
    constituency_code: str
    party_code: str
    candidate_code: str
    ballot_position: str
    candidate_given_names: str
    candidate_surnames: str
    running_mate_given_names: str
    running_mate_surnames: str
    votes: PublishedMetric
    vote_share: PublishedMetric


@dataclass(frozen=True)
class ParsedPrecountAct:
    """Normalized official ACT content at one published geography grain."""

    source_url: str
    election_id: str
    scope_code: str
    grain: str
    department_code: str
    totals: tuple[PublishedMetric, ...]
    candidates: tuple[PrecountCandidate, ...]


@dataclass(frozen=True)
class _GraphNode:
    scope: PrecountScope
    parent_refs: tuple[tuple[int, int], ...]
    child_refs: tuple[tuple[int, int], ...]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PrecountSchemaError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise PrecountSchemaError(f"{label} must be a list")
    return value


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PrecountSchemaError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "nonnegative"
        raise PrecountSchemaError(f"{label} must be {qualifier}")
    return value


def _decimal_code(
    value: object,
    label: str,
    *,
    length: int | None = None,
    lengths: frozenset[int] | None = None,
) -> str:
    if not isinstance(value, str) or not _DIGITS.fullmatch(value):
        raise PrecountSchemaError(f"{label} must be a decimal string")
    if length is not None and len(value) != length:
        raise PrecountSchemaError(f"{label} must contain exactly {length} digits")
    if lengths is not None and len(value) not in lengths:
        options = " or ".join(str(item) for item in sorted(lengths))
        raise PrecountSchemaError(f"{label} must contain exactly {options} digits")
    return value


def _scope_code(
    value: object,
    label: str,
    *,
    lengths: frozenset[int],
    allow_letters: bool,
) -> str:
    if not isinstance(value, str) or not _SCOPE_CHARACTERS.fullmatch(value):
        qualifier = "uppercase alphanumeric" if allow_letters else "decimal"
        raise PrecountSchemaError(f"{label} must be a canonical {qualifier} scope code")
    if not allow_letters and not _DIGITS.fullmatch(value):
        raise PrecountSchemaError(f"{label} must be a canonical decimal scope code")
    if len(value) not in lengths:
        options = " or ".join(str(item) for item in sorted(lengths))
        raise PrecountSchemaError(f"{label} must contain exactly {options} characters")
    return value


def _source_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrecountSchemaError(f"{label} must be a non-empty string")
    if any(ord(character) < 32 for character in value):
        raise PrecountSchemaError(f"{label} contains a control character")
    return value


def _election_id(value: object, label: str = "election id") -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PrecountSchemaError(f"{label} must be a positive decimal identifier")
    text = str(value)
    if not _DIGITS.fullmatch(text) or int(text) < 1 or text != str(int(text)):
        raise PrecountSchemaError(f"{label} must be a positive decimal identifier")
    return text


def _reference_pairs(value: object, label: str) -> tuple[tuple[int, int], ...]:
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for group_index, raw_group in enumerate(_list(value, label)):
        group = _mapping(raw_group, f"{label}[{group_index}]")
        level = _integer(group.get("l"), f"{label}[{group_index}].l", positive=True)
        references = _list(group.get("p"), f"{label}[{group_index}].p")
        if not references:
            raise PrecountSchemaError(f"{label}[{group_index}].p must not be empty")
        for reference_index, raw_reference in enumerate(references):
            reference = _integer(
                raw_reference,
                f"{label}[{group_index}].p[{reference_index}]",
            )
            pair = (level, reference)
            if pair in seen:
                raise PrecountSchemaError(f"{label} contains a duplicate graph reference")
            seen.add(pair)
            pairs.append(pair)
    return tuple(sorted(pairs))


def _parse_scope(raw: object, election_id: str, position: int) -> _GraphNode:
    node = _mapping(raw, f"ambitos[{position}]")
    index = _integer(node.get("i"), f"ambitos[{position}].i")
    level = _integer(node.get("l"), f"ambitos[{position}].l", positive=True)
    expected_lengths = _SCOPE_CODE_LENGTHS.get(level)
    if expected_lengths is None:
        raise PrecountSchemaError(f"ambitos[{position}].l has an unsupported scope level")
    code = _scope_code(
        node.get("c"),
        f"ambitos[{position}].c",
        lengths=expected_lengths,
        allow_letters=level in {6, 7},
    )
    name = _source_text(node.get("n"), f"ambitos[{position}].n")
    slug = _source_text(node.get("s"), f"ambitos[{position}].s")
    mesa_count = _integer(node.get("m"), f"ambitos[{position}].m")
    parent_refs = _reference_pairs(node.get("p"), f"ambitos[{position}].p")
    child_refs = _reference_pairs(node.get("h"), f"ambitos[{position}].h")
    raw_related = _list(node.get("r"), f"ambitos[{position}].r")
    related = tuple(
        _integer(item, f"ambitos[{position}].r[{item_index}]")
        for item_index, item in enumerate(raw_related)
    )
    if len(related) != len(set(related)):
        raise PrecountSchemaError(f"ambitos[{position}].r contains duplicate indices")
    scope = PrecountScope(
        election_id=election_id,
        index=index,
        code=code,
        level=level,
        grain=_GRAIN_BY_LEVEL[level],
        name=name,
        slug=slug,
        mesa_count=mesa_count,
        parent_indices=tuple(reference for _, reference in parent_refs),
        child_indices=tuple(reference for _, reference in child_refs),
    )
    return _GraphNode(scope=scope, parent_refs=parent_refs, child_refs=child_refs)


def parse_nomenclator(payload: object, *, election_id: str | int) -> PrecountNomenclator:
    """Parse and validate one election's indexed ``nomenclator.json`` graph.

    Indices are resolved by each node's explicit ``i`` value, never by list
    position.  Parent/child references must agree in both directions and must
    name the referenced node's published level.
    """
    expected_election = _election_id(election_id)
    root = _mapping(payload, "nomenclator")
    election_entries = _list(root.get("amb"), "nomenclator.amb")
    matches: list[Mapping[str, object]] = []
    for position, raw_entry in enumerate(election_entries):
        entry = _mapping(raw_entry, f"nomenclator.amb[{position}]")
        actual_election = _election_id(entry.get("elec"), f"nomenclator.amb[{position}].elec")
        if actual_election == expected_election:
            matches.append(entry)
    if len(matches) != 1:
        raise PrecountSchemaError(
            f"nomenclator must contain exactly one election {expected_election!r}"
        )

    raw_scopes = _list(matches[0].get("ambitos"), "nomenclator election ambitos")
    if not raw_scopes:
        raise PrecountSchemaError("nomenclator election ambitos must not be empty")
    nodes = tuple(
        _parse_scope(raw_scope, expected_election, position)
        for position, raw_scope in enumerate(raw_scopes)
    )
    by_index: dict[int, _GraphNode] = {}
    by_code: dict[str, _GraphNode] = {}
    for node in nodes:
        if node.scope.index in by_index:
            raise PrecountSchemaError(f"duplicate nomenclator index {node.scope.index}")
        if node.scope.code in by_code:
            raise PrecountSchemaError(f"duplicate nomenclator scope code {node.scope.code!r}")
        by_index[node.scope.index] = node
        by_code[node.scope.code] = node

    roots: list[PrecountScope] = []
    for node in nodes:
        scope = node.scope
        if not node.parent_refs:
            roots.append(scope)
        elif len(node.parent_refs) != 1:
            raise PrecountSchemaError(f"scope {scope.code!r} has an ambiguous parent")
        for parent_level, parent_index in node.parent_refs:
            parent = by_index.get(parent_index)
            if parent is None:
                raise PrecountSchemaError(f"scope {scope.code!r} references a missing parent")
            if parent.scope.level != parent_level or parent.scope.level >= scope.level:
                raise PrecountSchemaError(f"scope {scope.code!r} has an inconsistent parent level")
            if (scope.level, scope.index) not in parent.child_refs:
                raise PrecountSchemaError(f"scope {scope.code!r} parent/child references disagree")
        for child_level, child_index in node.child_refs:
            child = by_index.get(child_index)
            if child is None:
                raise PrecountSchemaError(f"scope {scope.code!r} references a missing child")
            if child.scope.level != child_level or child.scope.level <= scope.level:
                raise PrecountSchemaError(f"scope {scope.code!r} has an inconsistent child level")
            if (scope.level, scope.index) not in child.parent_refs:
                raise PrecountSchemaError(f"scope {scope.code!r} parent/child references disagree")

    if len(roots) != 1 or roots[0].level != 1:
        raise PrecountSchemaError("nomenclator election must have one national root")
    if roots[0].code != "00":
        raise PrecountSchemaError("national nomenclator root must publish scope code '00'")

    scopes = tuple(sorted((node.scope for node in nodes), key=lambda item: item.index))
    return PrecountNomenclator(election_id=expected_election, scopes=scopes)


def _validated_origin(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url:
        raise PrecountSchemaError("pre-count base URL must be a non-empty HTTPS origin")
    parsed = urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PrecountSchemaError("pre-count base URL contains an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _REVIEWED_PRECOUNT_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise PrecountSchemaError(
            "pre-count base URL must be an HTTPS origin without credentials, port, path, query, "
            "or fragment"
        )
    if parsed.netloc != parsed.hostname:
        raise PrecountSchemaError("pre-count base URL host must be canonical")
    return urlunsplit(("https", parsed.hostname, "", "", ""))


def _validated_siglas(election_siglas: str) -> str:
    if not isinstance(election_siglas, str) or not _ELECTION_SIGLAS.fullmatch(election_siglas):
        raise PrecountSchemaError("election siglas must be a canonical uppercase path segment")
    return election_siglas


def _scope_department(scope: PrecountScope, by_index: Mapping[int, PrecountScope]) -> str:
    current = scope
    visited: set[int] = set()
    while current.level > 2:
        if current.index in visited or len(current.parent_indices) != 1:
            raise PrecountSchemaError(f"scope {scope.code!r} has an ambiguous ancestry")
        visited.add(current.index)
        parent = by_index.get(current.parent_indices[0])
        if parent is None:
            raise PrecountSchemaError(f"scope {scope.code!r} has a missing ancestor")
        current = parent
    return "00" if current.level == 1 else current.code


def _act_url(origin: str, election_siglas: str, scope_code: str) -> str:
    return f"{origin}/json/ACT/{election_siglas}/{scope_code}.json"


def _validate_plan_entry(
    expected: PrecountPlanEntry, *, reviewed_origin: str | None = None
) -> None:
    election_id = _election_id(expected.election_id, "plan election id")
    siglas = _validated_siglas(expected.election_siglas)
    department_code = _decimal_code(expected.department_code, "plan department code", length=2)
    if expected.grain == "mesa":
        if expected.kind != "mesa" or expected.scope_level != 7:
            raise PrecountSchemaError("mesa plan kind, grain, and level are inconsistent")
        parent = _scope_code(
            expected.parent_scope_code,
            "mesa plan parent scope",
            lengths=_SCOPE_CODE_LENGTHS[6],
            allow_letters=True,
        )
        scope_code = _scope_code(
            expected.scope_code,
            "mesa plan scope",
            lengths=frozenset({len(parent) + 6}),
            allow_letters=True,
        )
        if not scope_code.startswith(parent):
            raise PrecountSchemaError("mesa plan scope is outside its polling place")
        _decimal_code(scope_code[len(parent) :], "mesa plan suffix", length=6)
    else:
        if expected.kind != "aggregate" or expected.parent_scope_code is not None:
            raise PrecountSchemaError("aggregate plan kind and parent identity are inconsistent")
        expected_grain = _GRAIN_BY_LEVEL.get(expected.scope_level)
        lengths = _SCOPE_CODE_LENGTHS.get(expected.scope_level)
        if expected_grain is None or lengths is None or expected.grain != expected_grain:
            raise PrecountSchemaError("aggregate plan grain and level are inconsistent")
        scope_code = _scope_code(
            expected.scope_code,
            "aggregate plan scope",
            lengths=lengths,
            allow_letters=expected.scope_level == 6,
        )
    if expected.grain == "national":
        if scope_code != "00" or department_code != "00":
            raise PrecountSchemaError("national plan identity is inconsistent")
    elif not scope_code.startswith(department_code):
        raise PrecountSchemaError("plan scope and department identities are inconsistent")
    source = urlsplit(expected.source_url)
    try:
        source_origin = _validated_origin(
            urlunsplit((source.scheme, source.netloc, "", "", ""))
        )
    except PrecountSchemaError as exc:
        raise PrecountSchemaError("plan source URL has an unreviewed origin") from exc
    origin = _validated_origin(reviewed_origin) if reviewed_origin is not None else source_origin
    expected_url = _act_url(origin, siglas, scope_code)
    if expected.source_url != expected_url:
        raise PrecountSchemaError("plan source URL does not match its official identity")
    if election_id != expected.election_id:
        raise PrecountSchemaError("plan election id must be canonical")


def plan_aggregate_act_urls(
    base_url: str,
    election_siglas: str,
    nomenclator: PrecountNomenclator,
) -> tuple[PrecountPlanEntry, ...]:
    """Plan aggregate ACTs from the exact official scope codes in the graph."""
    origin = _validated_origin(base_url)
    siglas = _validated_siglas(election_siglas)
    if not isinstance(nomenclator, PrecountNomenclator):
        raise PrecountSchemaError("a validated PrecountNomenclator is required")
    by_index = {scope.index: scope for scope in nomenclator.scopes}
    if len(by_index) != len(nomenclator.scopes):
        raise PrecountSchemaError("nomenclator contains duplicate scope indices")
    if len({scope.code for scope in nomenclator.scopes}) != len(nomenclator.scopes):
        raise PrecountSchemaError("nomenclator contains duplicate scope codes")
    entries = (
        PrecountPlanEntry(
            source_url=_act_url(origin, siglas, scope.code),
            election_id=nomenclator.election_id,
            election_siglas=siglas,
            scope_code=scope.code,
            scope_level=scope.level,
            grain=scope.grain,
            kind="aggregate",
            department_code=_scope_department(scope, by_index),
        )
        for scope in nomenclator.scopes
        # Mesa ACTs are only planned from IDs published by the parent place
        # ACT's mapagan array. A level-7 nomenclator node proves hierarchy but
        # is not a permission to synthesize a mesa retrieval.
        if scope.level != 7
    )
    plan = tuple(sorted(entries, key=lambda entry: (entry.scope_level, entry.scope_code)))
    for entry in plan:
        _validate_plan_entry(entry, reviewed_origin=origin)
    return plan


def enumerate_mesa_act_urls(
    base_url: str,
    election_siglas: str,
    polling_place: PrecountScope,
    polling_place_act: object,
) -> tuple[PrecountPlanEntry, ...]:
    """Plan only mesa IDs explicitly returned by a polling-place ACT.

    ``polling_place.mesa_count`` is intentionally not used to fill gaps.  A
    partially reported source therefore produces a partial plan whose missing
    coverage can be reported by the caller without invented identifiers.
    """
    origin = _validated_origin(base_url)
    siglas = _validated_siglas(election_siglas)
    if not isinstance(polling_place, PrecountScope) or polling_place.level != 6:
        raise PrecountSchemaError("mesa enumeration requires a validated polling-place scope")
    root = _mapping(polling_place_act, "polling-place ACT")
    actual_election = _election_id(root.get("elec"), "polling-place ACT elec")
    if actual_election != polling_place.election_id:
        raise PrecountSchemaError("polling-place ACT election identity does not match nomenclator")
    actual_scope = _scope_code(
        root.get("amb"),
        "polling-place ACT amb",
        lengths=_SCOPE_CODE_LENGTHS[6],
        allow_letters=True,
    )
    if actual_scope != polling_place.code:
        raise PrecountSchemaError("polling-place ACT scope identity does not match nomenclator")
    department_code = _decimal_code(root.get("dept"), "polling-place ACT dept", length=2)
    if not actual_scope.startswith(department_code):
        raise PrecountSchemaError("polling-place ACT department identity is inconsistent")

    mesa_codes: set[str] = set()
    cameras = _list(root.get("camaras"), "polling-place ACT camaras")
    if not cameras:
        raise PrecountSchemaError("polling-place ACT camaras must not be empty")
    for camera_index, raw_camera in enumerate(cameras):
        camera = _mapping(raw_camera, f"polling-place ACT camaras[{camera_index}]")
        map_entries = _list(
            camera.get("mapagan"),
            f"polling-place ACT camaras[{camera_index}].mapagan",
        )
        for mesa_index, raw_mesa in enumerate(map_entries):
            mesa = _mapping(
                raw_mesa,
                f"polling-place ACT camaras[{camera_index}].mapagan[{mesa_index}]",
            )
            mesa_code = _scope_code(
                mesa.get("amb"),
                "mapagan mesa amb",
                lengths=frozenset({len(actual_scope) + 6}),
                allow_letters=True,
            )
            if not mesa_code.startswith(actual_scope):
                raise PrecountSchemaError("mapagan mesa identity is outside its polling place")
            _decimal_code(
                mesa_code[len(actual_scope) :],
                "mapagan mesa suffix",
                length=6,
            )
            if mesa_code in mesa_codes:
                raise PrecountSchemaError(f"duplicate mapagan mesa identity {mesa_code!r}")
            mesa_codes.add(mesa_code)
    if len(mesa_codes) > polling_place.mesa_count:
        raise PrecountSchemaError("polling-place ACT publishes more mesas than the nomenclator")

    plan = tuple(
        PrecountPlanEntry(
            source_url=_act_url(origin, siglas, mesa_code),
            election_id=polling_place.election_id,
            election_siglas=siglas,
            scope_code=mesa_code,
            scope_level=7,
            grain="mesa",
            kind="mesa",
            department_code=department_code,
            parent_scope_code=polling_place.code,
        )
        for mesa_code in sorted(mesa_codes)
    )
    for entry in plan:
        _validate_plan_entry(entry, reviewed_origin=origin)
    return plan


def _published_metric(value: object, name: str, kind: MetricKind) -> PublishedMetric:
    if value is None:
        return PublishedMetric(name=name, kind=kind, raw=None, state="unavailable", value=None)
    if not isinstance(value, str):
        raise PrecountSchemaError(f"{name} must be a source string or null")
    normalized_state = value.strip().upper()
    if normalized_state in _UNKNOWN_VALUES:
        return PublishedMetric(name=name, kind=kind, raw=value, state="unknown", value=None)
    if normalized_state in _UNAVAILABLE_VALUES:
        return PublishedMetric(name=name, kind=kind, raw=value, state="unavailable", value=None)
    if kind == "count":
        if not _DIGITS.fullmatch(value):
            raise PrecountSchemaError(f"{name} must be a nonnegative integer string")
        parsed: int | Decimal = int(value)
    else:
        if not _PERCENTAGE.fullmatch(value):
            raise PrecountSchemaError(f"{name} must be a Colombian percentage string")
        try:
            parsed = Decimal(value.removesuffix("%").replace(",", "."))
        except InvalidOperation as exc:  # pragma: no cover - regex is the primary guard
            raise PrecountSchemaError(f"{name} must be a Colombian percentage string") from exc
        if not Decimal(0) <= parsed <= Decimal(100):
            raise PrecountSchemaError(f"{name} percentage must be between 0 and 100")
    return PublishedMetric(name=name, kind=kind, raw=value, state="observed", value=parsed)


def _required_metric(
    source: Mapping[str, object], field: str, kind: MetricKind, label: str
) -> PublishedMetric:
    if field not in source:
        raise PrecountSchemaError(f"{label} lacks required field {field!r}")
    return _published_metric(source[field], field, kind)


def _candidate_text(source: Mapping[str, object], field: str, label: str) -> str:
    if field not in source:
        raise PrecountSchemaError(f"{label} lacks required field {field!r}")
    return _source_text(source[field], f"{label}.{field}")


def parse_precount_act(
    payload: object,
    *,
    expected: PrecountPlanEntry,
    reviewed_origin: str | None = None,
) -> ParsedPrecountAct:
    """Parse a reviewed presidential ACT at its validated planned grain.

    Aggregate ACTs remain aggregate observations: callers must not infer or
    materialize mesa facts from them.
    """
    if not isinstance(expected, PrecountPlanEntry):
        raise PrecountSchemaError("a validated PrecountPlanEntry is required")
    _validate_plan_entry(expected, reviewed_origin=reviewed_origin)
    if expected.grain not in {
        "national",
        "department",
        "municipality",
        "zone",
        "comuna",
        "polling_place",
        "mesa",
    }:
        raise PrecountSchemaError("ACT parser does not support the planned scope grain")
    root = _mapping(payload, "ACT payload")
    actual_election = _election_id(root.get("elec"), "ACT elec")
    if actual_election != expected.election_id:
        raise PrecountSchemaError("ACT election identity does not match its plan")
    expected_length = len(expected.scope_code)
    expected_lengths = (
        frozenset({len(expected.scope_code)})
        if expected.grain == "mesa"
        else _SCOPE_CODE_LENGTHS[expected.scope_level]
    )
    actual_scope = _scope_code(
        root.get("amb"),
        "ACT amb",
        lengths=expected_lengths,
        allow_letters=expected.scope_level == 6 or expected.grain == "mesa",
    )
    if actual_scope != expected.scope_code:
        raise PrecountSchemaError("ACT scope identity does not match its plan")
    department_code = _decimal_code(root.get("dept"), "ACT dept", length=2)
    if department_code != expected.department_code:
        raise PrecountSchemaError("ACT department identity does not match its plan")
    if expected.grain != "national" and not actual_scope.startswith(department_code):
        raise PrecountSchemaError("ACT scope and department identities are inconsistent")

    totals_wrapper = _mapping(root.get("totales"), "ACT totales")
    totals_act = _mapping(totals_wrapper.get("act"), "ACT totales.act")
    totals = tuple(
        [
            _required_metric(totals_act, field, "count", "ACT totales.act")
            for field in _TOTAL_COUNT_FIELDS
        ]
        + [
            _required_metric(totals_act, field, "percentage", "ACT totales.act")
            for field in _TOTAL_PERCENTAGE_FIELDS
        ]
    )

    candidates: list[PrecountCandidate] = []
    candidate_keys: set[tuple[str, str, str, str]] = set()
    cameras = _list(root.get("camaras"), "ACT camaras")
    if not cameras:
        raise PrecountSchemaError("ACT camaras must not be empty")
    for camera_index, raw_camera in enumerate(cameras):
        camera_label = f"ACT camaras[{camera_index}]"
        camera = _mapping(raw_camera, camera_label)
        camera_code = _decimal_code(camera.get("cam"), f"{camera_label}.cam")
        constituency_code = _decimal_code(camera.get("cir"), f"{camera_label}.cir")
        parties = _list(camera.get("partotabla"), f"{camera_label}.partotabla")
        for party_index, raw_party in enumerate(parties):
            party_label = f"{camera_label}.partotabla[{party_index}].act"
            party_wrapper = _mapping(
                raw_party,
                f"{camera_label}.partotabla[{party_index}]",
            )
            party = _mapping(party_wrapper.get("act"), party_label)
            party_code = _decimal_code(party.get("codpar"), f"{party_label}.codpar")
            party_votes = _required_metric(party, "vot", "count", party_label)
            party_share = _required_metric(party, "pvot", "percentage", party_label)
            raw_candidates = _list(party.get("cantotabla"), f"{party_label}.cantotabla")
            if len(raw_candidates) != 1:
                raise PrecountSchemaError(
                    f"{party_label}.cantotabla must contain one presidential slate"
                )
            candidate_label = f"{party_label}.cantotabla[0]"
            candidate = _mapping(raw_candidates[0], candidate_label)
            candidate_scope = _scope_code(
                candidate.get("amb"),
                f"{candidate_label}.amb",
                lengths=frozenset({expected_length}),
                allow_letters=expected.scope_level == 6 or expected.grain == "mesa",
            )
            if candidate_scope != actual_scope:
                raise PrecountSchemaError("candidate scope identity does not match ACT")
            candidate_code = _decimal_code(candidate.get("codcan"), f"{candidate_label}.codcan")
            ballot_position = _decimal_code(candidate.get("sorteo"), f"{candidate_label}.sorteo")
            candidate_votes = _required_metric(candidate, "vot", "count", candidate_label)
            candidate_share = _required_metric(candidate, "pvot", "percentage", candidate_label)
            if candidate_votes != party_votes or candidate_share != party_share:
                raise PrecountSchemaError("candidate and party presidential totals disagree")
            key = (camera_code, constituency_code, party_code, candidate_code)
            if key in candidate_keys:
                raise PrecountSchemaError("ACT contains a duplicate candidate identity")
            candidate_keys.add(key)
            candidates.append(
                PrecountCandidate(
                    camera_code=camera_code,
                    constituency_code=constituency_code,
                    party_code=party_code,
                    candidate_code=candidate_code,
                    ballot_position=ballot_position,
                    candidate_given_names=_candidate_text(candidate, "nomcan", candidate_label),
                    candidate_surnames=_candidate_text(candidate, "apecan", candidate_label),
                    running_mate_given_names=_candidate_text(candidate, "nomcan2", candidate_label),
                    running_mate_surnames=_candidate_text(candidate, "apecan2", candidate_label),
                    votes=candidate_votes,
                    vote_share=candidate_share,
                )
            )
    if not candidates:
        raise PrecountSchemaError("ACT contains no presidential candidates")

    return ParsedPrecountAct(
        source_url=expected.source_url,
        election_id=expected.election_id,
        scope_code=actual_scope,
        grain=expected.grain,
        department_code=department_code,
        totals=totals,
        candidates=tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.camera_code,
                    item.constituency_code,
                    item.party_code,
                    item.candidate_code,
                ),
            )
        ),
    )


__all__ = [
    "ParsedPrecountAct",
    "PrecountCandidate",
    "PrecountNomenclator",
    "PrecountPlanEntry",
    "PrecountSchemaError",
    "PrecountScope",
    "PublishedMetric",
    "enumerate_mesa_act_urls",
    "parse_nomenclator",
    "parse_precount_act",
    "plan_aggregate_act_urls",
]
