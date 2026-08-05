"""Explicit adapter for the verified Registraduría pre-count ACT response shape.

The adapter deliberately has no URL logic.  An ACT is accepted only when it was
already fetched from an official, immutable snapshot and identified by verified
official geography/mesa components (or a verified mesa identifier).
"""
# ruff: noqa: E501

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .values import LocalizedValueError, parse_localized_integer


class ActSchemaError(ValueError):
    """The source does not match the reviewed ACT contract; quarantine it."""


_CODE = re.compile(r"^[A-Za-z0-9_-]+$")
_ACT_REQUIRED = frozenset({"act"})


@dataclass(frozen=True)
class SourceSnapshot:
    """Provenance copied into every normalized fact, never inferred downstream."""

    source_id: str
    source_type: str
    legal_status: str
    source_url: str
    retrieved_at: datetime
    content_hash: str
    parser_version: str
    transform_version: str
    data_version: str
    source_layer: str = "pre_count"

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.source_id,
                self.source_type,
                self.legal_status,
                self.source_url,
                self.content_hash,
                self.parser_version,
                self.transform_version,
                self.data_version,
                self.source_layer,
            )
        ):
            raise ActSchemaError("source provenance is incomplete")
        if not self.source_url.startswith("https://"):
            raise ActSchemaError("source_url must be HTTPS")
        if not re.fullmatch(r"[a-f0-9]{64}", self.content_hash):
            raise ActSchemaError("content_hash must be SHA-256")
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.tzinfo is None:
            raise ActSchemaError("retrieved_at must be timezone-aware")
        if self.retrieved_at.utcoffset() is None:
            raise ActSchemaError("retrieved_at must be timezone-aware")


def _component(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ActSchemaError(f"official {name} code is missing")
    code = str(value).strip()
    if not code or not _CODE.fullmatch(code):
        raise ActSchemaError(f"official {name} code is invalid")
    return code


def canonical_mesa_id(
    *,
    department: object | None = None,
    municipality: object | None = None,
    place: object | None = None,
    mesa: object | None = None,
    verified_mesa_id: object | None = None,
    verified_ids: frozenset[str] | set[str] | None = None,
) -> str:
    """Return an official identity, never an ID guessed from an endpoint pattern."""
    if verified_mesa_id is not None:
        identifier = _component(verified_mesa_id, "mesa")
        if verified_ids is None or identifier not in verified_ids:
            raise ActSchemaError("mesa ID was not declared by a verified manifest")
        return identifier
    if None in (department, municipality, place, mesa):
        raise ActSchemaError("all four official code components are required")
    identifier = ":".join(
        (
            _component(department, "department"),
            _component(municipality, "municipality"),
            _component(place, "place"),
            _component(mesa, "mesa"),
        )
    )
    if verified_ids is None or identifier not in verified_ids:
        raise ActSchemaError("mesa components were not declared by a verified manifest")
    return identifier


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ActSchemaError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ActSchemaError(f"{label} must be a list")
    return value


def _state(value: object) -> tuple[str, int | None]:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "n/a", "na"}):
        return "unavailable", None
    if isinstance(value, str) and value.strip().lower() in {"desconocido", "unknown", "pendiente"}:
        return "unknown", None
    try:
        return "observed", parse_localized_integer(value)
    except LocalizedValueError as exc:
        raise ActSchemaError(str(exc)) from exc


def _metric_rows(
    values: Mapping[str, Any], *, field_map: Mapping[str, str], base: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for output_name, source_name in sorted(field_map.items()):
        if source_name not in values:
            raise ActSchemaError(f"ACT object lacks required field {source_name!r}")
        state, value = _state(values[source_name])
        rows.append({**base, "metric": output_name, "value_state": state, "value": value})
    return rows


def parse_precount_act(
    payload: object,
    *,
    snapshot: SourceSnapshot,
    identity: Mapping[str, object],
    total_fields: Mapping[str, str],
    party_fields: Mapping[str, str],
    verified_mesa_ids: frozenset[str] | set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Normalize one ACT response using explicit field adapters.

    ``total_fields`` and ``party_fields`` map canonical metric names to reviewed
    ACT keys.  The function requires ``totales.act`` and every
    ``camaras[].partotabla[].act`` object; missing keys are schema drift, rather
    than an opportunity to silently coerce a changed source.
    """
    root = _mapping(payload, "ACT payload")
    if (
        snapshot.source_type != "pre_count"
        or snapshot.legal_status != "preliminary"
        or snapshot.source_layer != "pre_count"
    ):
        raise ActSchemaError(
            "pre-count ACT facts require source_type=pre_count, "
            "legal_status=preliminary, and source_layer=pre_count"
        )
    totals = _mapping(root.get("totales"), "totales")
    total_act = _mapping(totals.get("act"), "totales.act")
    cameras = _list(root.get("camaras"), "camaras")
    canonical = canonical_mesa_id(
        department=identity.get("department"),
        municipality=identity.get("municipality"),
        place=identity.get("place"),
        mesa=identity.get("mesa"),
        verified_mesa_id=identity.get("verified_mesa_id"),
        verified_ids=verified_mesa_ids,
    )
    base: dict[str, Any] = {
        "source_id": snapshot.source_id,
        "source_type": snapshot.source_type,
        "legal_status": snapshot.legal_status,
        "source_url": snapshot.source_url,
        "retrieved_at": snapshot.retrieved_at.astimezone(UTC).isoformat(),
        "content_hash": snapshot.content_hash,
        "parser_version": snapshot.parser_version,
        "transform_version": snapshot.transform_version,
        "data_version": snapshot.data_version,
        "source_layer": snapshot.source_layer,
        "grain": "mesa",
        "mesa_id": canonical,
        "identity": {
            key: _component(identity.get(key), key)
            for key in ("department", "municipality", "place", "mesa")
        },
    }
    rows = _metric_rows(total_act, field_map=total_fields, base={**base, "record_type": "total"})
    for camera_index, camera_raw in enumerate(cameras):
        camera = _mapping(camera_raw, f"camaras[{camera_index}]")
        party_table = _list(camera.get("partotabla"), f"camaras[{camera_index}].partotabla")
        for party_index, party_raw in enumerate(party_table):
            party = _mapping(party_raw, f"camaras[{camera_index}].partotabla[{party_index}]")
            act = _mapping(
                party.get("act"), f"camaras[{camera_index}].partotabla[{party_index}].act"
            )
            party_label = party.get("id") or party.get("codigo") or party.get("nombre")
            if not isinstance(party_label, (str, int)) or not str(party_label).strip():
                raise ActSchemaError("partotabla entry needs an explicit party identifier")
            rows.extend(
                _metric_rows(
                    act,
                    field_map=party_fields,
                    base={
                        **base,
                        "record_type": "party",
                        "camera_index": camera_index,
                        "party_id": str(party_label),
                    },
                )
            )
    return tuple(rows)


__all__ = ["ActSchemaError", "SourceSnapshot", "canonical_mesa_id", "parse_precount_act"]
