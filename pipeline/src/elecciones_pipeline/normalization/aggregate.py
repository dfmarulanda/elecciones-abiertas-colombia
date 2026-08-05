"""Conservative aggregation of normalized long facts."""
# ruff: noqa: E501

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


class AggregationError(ValueError):
    """Facts cannot be aggregated without losing a source qualification."""


_PROVENANCE = (
    "source_id",
    "source_type",
    "legal_status",
    "parser_version",
    "transform_version",
    "data_version",
    "source_layer",
)

_RAW_PROVENANCE = ("source_url", "content_hash", "retrieved_at")


def _hierarchy(identity: Mapping[str, Any], *, label: str) -> tuple[str, str, str]:
    values = tuple(identity.get(key) for key in ("department", "municipality", "place"))
    if not all(isinstance(part, str) and part for part in values):
        raise AggregationError(f"{label} hierarchy is incomplete")
    department, municipality, place = values
    # ``all`` above narrows only imprecisely for mypy; make the trusted boundary explicit.
    assert isinstance(department, str)
    assert isinstance(municipality, str)
    assert isinstance(place, str)
    return department, municipality, place


def aggregate_complete_mesa_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    level: str,
    expected_mesa_hierarchy: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, Any], ...]:
    """Roll up only observed mesa facts with identical source and metric semantics.

    ``expected_mesa_hierarchy`` is the verified release inventory keyed by
    canonical mesa ID, with each value containing its official ``department``,
    ``municipality``, and ``place`` codes. A numeric aggregate is emitted only
    when every mesa expected *at that aggregate's geography* supplies exactly one
    observed fact for that metric. Unknown/unavailable and missing facts make the
    group ineligible. Source-layer fields remain in the key, so pre-count and
    scrutiny data cannot merge. Raw-object provenance is retained as an ordered
    collection because a roll-up generally spans more than one source object.
    """
    positions = {"place": 3, "municipality": 2, "department": 1, "national": 0}
    if level not in positions:
        raise AggregationError("level must be place, municipality, department, or national")
    expected_by_hierarchy: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for mesa_id, identity in expected_mesa_hierarchy.items():
        if not isinstance(mesa_id, str) or not mesa_id:
            raise AggregationError("expected mesa ID must be a canonical non-empty string")
        if not isinstance(identity, Mapping):
            raise AggregationError("expected mesa hierarchy must be an object")
        hierarchy = _hierarchy(identity, label="expected mesa")
        expected_by_hierarchy[hierarchy].add(mesa_id)
    if not expected_by_hierarchy:
        raise AggregationError("expected_mesa_hierarchy must be a non-empty verified inventory")
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact.get("grain") != "mesa":
            raise AggregationError("only mesa facts can be rolled up")
        fact_mesa_id = fact.get("mesa_id")
        if not isinstance(fact_mesa_id, str):
            raise AggregationError("mesa fact lacks a canonical mesa ID")
        fact_identity = fact.get("identity")
        if not isinstance(fact_identity, Mapping):
            raise AggregationError("mesa fact lacks identity")
        hierarchy = _hierarchy(fact_identity, label="mesa")
        if fact_mesa_id not in expected_by_hierarchy.get(hierarchy, set()):
            raise AggregationError("mesa fact is not in the verified expected mesa hierarchy")
        if any(
            not isinstance(fact.get(name), str) or not fact[name]
            for name in _PROVENANCE + _RAW_PROVENANCE
        ):
            raise AggregationError("mesa fact has incomplete provenance")
        key = tuple(fact.get(name) for name in _PROVENANCE) + (
            fact.get("metric"),
            fact.get("record_type"),
            fact.get("party_id"),
            hierarchy[: positions[level]],
        )
        groups[key].append(fact)
    rows: list[dict[str, Any]] = []
    for key, items in sorted(groups.items(), key=lambda item: repr(item[0])):
        mesa_items: dict[str, Mapping[str, Any]] = {}
        duplicate = False
        for item in items:
            mesa_id = item["mesa_id"]
            if mesa_id in mesa_items:
                duplicate = True
            mesa_items[mesa_id] = item
        group_hierarchy = key[-1]
        expected = {
            mesa_id
            for hierarchy, mesa_ids in expected_by_hierarchy.items()
            if hierarchy[: positions[level]] == group_hierarchy
            for mesa_id in mesa_ids
        }
        if duplicate or set(mesa_items) != expected:
            continue
        if any(item.get("value_state") != "observed" for item in items):
            continue
        values = [item.get("value") for item in items]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values
        ):
            raise AggregationError("observed value must be a non-negative integer")
        first = items[0]
        raw_objects = tuple(
            {name: item[name] for name in _RAW_PROVENANCE}
            for item in sorted(
                items,
                key=lambda item: (item["mesa_id"], item["source_url"], item["content_hash"]),
            )
        )
        rows.append(
            {
                **{name: first[name] for name in _PROVENANCE},
                "grain": level,
                "identity_key": key[-1],
                "metric": first.get("metric"),
                "record_type": first.get("record_type"),
                "party_id": first.get("party_id"),
                "value_state": "observed",
                "value": sum(values),
                "source_fact_count": len(items),
                "raw_provenance": raw_objects,
            }
        )
    return tuple(rows)
