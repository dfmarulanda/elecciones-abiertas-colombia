"""Build a truthful local candidate release from the verified national crawl.

This first materialization exposes the official preliminary national ACT.  It
retains the CNE final-declaration link as catalogued metadata only; no election
document is downloaded, transcribed, or used as a numeric result.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from elecciones_pipeline.catalog import SourceCatalog
from elecciones_pipeline.ingest import LocalObjectStore, SQLiteCheckpointStore
from elecciones_pipeline.ingest.precount import PrecountSchemaError, parse_nomenclator

from .export import DatasetArtifact, export_dataset
from .manifest import build_candidate_manifest
from .snapshot import materialize_api_snapshot


class CandidateBuildError(ValueError):
    """The collected state is insufficient or inconsistent for a candidate."""


@dataclass(frozen=True)
class CandidateBuild:
    release_id: str
    manifest_path: Path
    snapshot_path: Path
    snapshot_hash: str
    dataset_artifacts: tuple[DatasetArtifact, ...]
    publication_blockers: tuple[str, ...]


_PARSER_VERSION = "registraduria-precount-act@1.0.0"
_TRANSFORM_VERSION = "precount-national-candidate@1.0.0"
_GEOGRAPHY_TRANSFORM_VERSION = "precount-geographic-candidate@1.0.4"
_ROUND2_CANDIDATES = {
    ("2", "1"): {
        "id": "ivan-cepeda-aida-quilcue",
        "name": {
            "es": "Iván Cepeda Castro / Aida Marina Quilcué Vivas",
            "en": "Iván Cepeda Castro / Aida Marina Quilcué Vivas",
        },
        "short_name": {"es": "Cepeda / Quilcué", "en": "Cepeda / Quilcué"},
    },
    ("3", "2"): {
        "id": "abelardo-de-la-espriella-jose-manuel-restrepo",
        "name": {
            "es": "Abelardo de la Espriella / José Manuel Restrepo",
            "en": "Abelardo de la Espriella / José Manuel Restrepo",
        },
        "short_name": {
            "es": "De la Espriella / Restrepo",
            "en": "De la Espriella / Restrepo",
        },
    },
}

_ROUND1_CANDIDATES = {
    ("10", "4"): (
        "abelardo-de-la-espriella-jose-manuel-restrepo",
        "Abelardo de la Espriella / José Manuel Restrepo",
        "De la Espriella / Restrepo",
    ),
    ("7", "1"): (
        "ivan-cepeda-aida-quilcue",
        "Iván Cepeda Castro / Aida Marina Quilcué Vivas",
        "Cepeda / Quilcué",
    ),
    ("2", "11"): (
        "paloma-valencia-juan-daniel-oviedo",
        "Paloma Valencia Laserna / Juan Daniel Oviedo Arango",
        "Valencia / Oviedo",
    ),
    ("3", "12"): (
        "sergio-fajardo-edna-bonilla",
        "Sergio Fajardo Valderrama / Edna Cristina del Socorro Bonilla Seba",
        "Fajardo / Bonilla",
    ),
    ("11", "2"): (
        "claudia-lopez-leonardo-huerta",
        "Claudia López / Leonardo Humberto Huerta Gutiérrez",
        "López / Huerta",
    ),
    ("8", "3"): (
        "raul-botero-carlos-cuevas",
        "Raúl Santiago Botero Jaramillo / Carlos Fernando Cuevas Romero",
        "Botero / Cuevas",
    ),
    ("14", "5"): (
        "oscar-lizcano-pedro-de-la-torre",
        "Óscar Mauricio Lizcano Arango / Pedro Luis de la Torre Márquez",
        "Lizcano / De la Torre",
    ),
    ("4", "6"): (
        "miguel-uribe-luisa-villegas",
        "Miguel Uribe Londoño / Luisa Fernanda Villegas Araque",
        "Uribe / Villegas",
    ),
    ("9", "7"): (
        "sondra-macollins-leonardo-karam",
        "Sondra Macollins Garvin Pinto / Leonardo Karam Helo",
        "Macollins / Karam",
    ),
    ("6", "8"): (
        "roy-barreras-martha-zamora",
        "Roy Leonardo Barreras Montealegre / Martha Lucía Zamora Ávila",
        "Barreras / Zamora",
    ),
    ("13", "9"): (
        "carlos-caicedo-nelson-alarcon",
        "Carlos Eduardo Caicedo Omar / Nelson Javier Alarcón Suárez",
        "Caicedo / Alarcón",
    ),
    ("5", "10"): (
        "gustavo-matamoros-mila-paz",
        "Gustavo Matamoros Camacho / Mila María Paz Campaz",
        "Matamoros / Paz",
    ),
    ("12", "13"): (
        "luis-murillo-luz-zapata",
        "Luis Gilberto Murillo Urrutia / Luz María Zapata Zapata",
        "Murillo / Zapata",
    ),
}


@dataclass(frozen=True)
class _ElectionProfile:
    round: int
    election_date: str
    release_prefix: str
    name_es: str
    name_en: str
    source_suffix: str
    candidates: Mapping[tuple[str, str], Mapping[str, Any] | tuple[str, str, str]]
    require_legal_material: bool


_PROFILES = {
    "presidencia-2026-primera-vuelta": _ElectionProfile(
        round=1,
        election_date="2026-05-31",
        release_prefix="candidate-2026-r1",
        name_es="Presidencia 2026 · primera vuelta",
        name_en="2026 presidential election · first round",
        source_suffix="2026-r1",
        candidates=_ROUND1_CANDIDATES,
        require_legal_material=False,
    ),
    "presidencia-2026-segunda-vuelta": _ElectionProfile(
        round=2,
        election_date="2026-06-21",
        release_prefix="candidate-2026-r2",
        name_es="Presidencia 2026 · segunda vuelta",
        name_en="2026 presidential election · second round",
        source_suffix="2026-r2",
        candidates=_ROUND2_CANDIDATES,
        require_legal_material=True,
    ),
}


def _profile(catalog: SourceCatalog) -> _ElectionProfile:
    try:
        return _PROFILES[catalog.election_slug]
    except KeyError as exc:
        raise CandidateBuildError(
            f"catalog slug has no reviewed candidate profile: {catalog.election_slug}"
        ) from exc


def _read_national_row(database: Path, plan_id: str) -> dict[str, Any]:
    if not database.is_file():
        raise CandidateBuildError(f"crawl ledger does not exist: {database}")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT normalized_json
            FROM items
            WHERE plan_id = ? AND grain = 'national' AND parse_status = 'parsed'
            """,
            (plan_id,),
        ).fetchall()
    if len(rows) != 1 or rows[0]["normalized_json"] is None:
        raise CandidateBuildError("candidate build requires exactly one parsed national ACT")
    value = json.loads(rows[0]["normalized_json"])
    if not isinstance(value, dict):
        raise CandidateBuildError("normalized national ACT is not an object")
    return value


def _observed_metrics(normalized: Mapping[str, Any]) -> dict[str, int]:
    totals = normalized.get("totals")
    if not isinstance(totals, list):
        raise CandidateBuildError("normalized national ACT has no totals")
    metrics: dict[str, int] = {}
    for item in totals:
        if not isinstance(item, Mapping):
            raise CandidateBuildError("normalized total is not an object")
        name, state, value = item.get("name"), item.get("state"), item.get("value")
        if not isinstance(name, str):
            raise CandidateBuildError("normalized total lacks a name")
        if state == "observed" and type(value) is int and value >= 0:
            metrics[name] = value
    required = {
        "metota",
        "mesesc",
        "centota",
        "votant",
        "absten",
        "votnul",
        "votnma",
        "votblan",
        "votval",
    }
    if missing := required - set(metrics):
        raise CandidateBuildError(f"national ACT lacks observed totals: {sorted(missing)!r}")
    return metrics


def _candidate_data(
    normalized: Mapping[str, Any],
    profile: _ElectionProfile,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = normalized.get("candidates")
    if not isinstance(source, list):
        raise CandidateBuildError("normalized national ACT has no candidates")
    candidates: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in source:
        if not isinstance(raw, Mapping):
            raise CandidateBuildError("normalized candidate is not an object")
        key = str(raw.get("party_code")), str(raw.get("candidate_code"))
        reviewed = profile.candidates.get(key)
        if reviewed is None:
            raise CandidateBuildError(f"unreviewed presidential slate identity: {key!r}")
        votes = raw.get("votes")
        ballot = raw.get("ballot_position")
        if (
            not isinstance(votes, Mapping)
            or votes.get("state") != "observed"
            or type(votes.get("value")) is not int
            or not isinstance(ballot, str)
            or not ballot.isdecimal()
        ):
            raise CandidateBuildError("candidate votes or ballot position are not observed")
        if isinstance(reviewed, tuple):
            identifier, name, short_name = reviewed
            candidate = {
                "id": identifier,
                "name": {"es": name, "en": name},
                "short_name": {"es": short_name, "en": short_name},
                "ballot_number": int(ballot),
            }
        else:
            candidate = {**reviewed, "ballot_number": int(ballot)}
        identifier = str(candidate["id"])
        if identifier in seen:
            raise CandidateBuildError("national ACT contains a duplicate reviewed slate")
        seen.add(identifier)
        candidates.append(candidate)
        results.append(
            {
                "candidate_id": identifier,
                "votes": {"value": int(votes["value"]), "status": "observed"},
            }
        )
    if len(candidates) != len(profile.candidates):
        raise CandidateBuildError("national ACT does not contain every reviewed slate")
    candidates.sort(key=lambda item: int(item["ballot_number"]))
    results.sort(key=lambda item: str(item["candidate_id"]))
    return candidates, results


def _metric(value: int) -> dict[str, object]:
    return {"value": value, "status": "observed"}


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateBuildError(f"{label} is required")
    return value


def _source_from_snapshot(
    *,
    identifier: str,
    source_type: str,
    legal_status: str,
    snapshot: Any,
    parser_version: str,
    transform_version: str,
    coverage: Mapping[str, int],
) -> dict[str, object]:
    return {
        "id": identifier,
        "source_type": source_type,
        "legal_status": legal_status,
        "source_url": snapshot.url,
        "retrieved_at": snapshot.retrieved_at.astimezone(UTC).isoformat(),
        "content_hash": snapshot.content_hash,
        "media_type": snapshot.media_type,
        "byte_size": snapshot.byte_size,
        "parser_version": parser_version,
        "transform_version": transform_version,
        "coverage": dict(coverage),
    }


def _flat_download_row(
    result: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": result["id"],
        "election_slug": result["election_slug"],
        "geography_id": result["geography_id"],
        "geography_level": result["geography_level"],
        "mesa_id": result["mesa_id"],
        "source_type": result["provenance"]["source_type"],
        "legal_status": result["provenance"]["legal_status"],
        "source_url": result["provenance"]["source_url"],
        "retrieved_at": result["provenance"]["retrieved_at"],
        "content_hash": result["provenance"]["content_hash"],
    }
    for field in (
        "registered_electors",
        "voters",
        "valid_votes",
        "blank_votes",
        "null_votes",
        "unmarked_votes",
    ):
        metric = result[field]
        row[f"{field}_value"] = metric["value"]
        row[f"{field}_status"] = metric["status"]
    votes = {item["candidate_id"]: item["votes"] for item in result["candidates"]}
    for candidate in candidates:
        identifier = str(candidate["id"])
        row[f"candidate_{identifier}_votes"] = votes[identifier]["value"]
    return row


def _completed_plan_rows(
    database: Path, plan_id: str, *, stage: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return only a fully parsed immutable crawl plan, never a best effort subset."""
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        plan = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        rows = connection.execute(
            "SELECT * FROM items WHERE plan_id = ? ORDER BY scope_code, source_url", (plan_id,)
        ).fetchall()
    if plan is None or plan["stage"] != stage:
        raise CandidateBuildError(f"{stage} plan is not a known {stage} crawl plan: {plan_id}")
    if (
        not rows
        or len(rows) != plan["expected"]
        or any(row["parse_status"] != "parsed" for row in rows)
    ):
        raise CandidateBuildError(
            f"{stage} plan is not completed with parsed official records: {plan_id}"
        )
    if any(row["normalized_json"] is None for row in rows):
        raise CandidateBuildError(f"{stage} plan has a parsed row without normalized content")
    return dict(plan), [dict(row) for row in rows]


def _result_metrics(
    normalized: Mapping[str, Any], *, geographic_endpoint: bool = False
) -> dict[str, dict[str, object]]:
    totals = normalized.get("totals")
    if not isinstance(totals, list):
        raise CandidateBuildError("normalized ACT has no totals")
    names = {
        "registered_electors": "centota",
        "voters": "votant",
        "valid_votes": "votval",
        "blank_votes": "votblan",
        "null_votes": "votnul",
        "unmarked_votes": "votnma",
    }
    values: dict[str, dict[str, object]] = {}
    by_name = {item.get("name"): item for item in totals if isinstance(item, Mapping)}
    for field, source_name in names.items():
        item = by_name.get(source_name)
        if not isinstance(item, Mapping) or item.get("state") not in {
            "observed",
            "unknown",
            "unavailable",
        }:
            raise CandidateBuildError(f"normalized ACT lacks a valid {source_name} metric")
        if item["state"] == "observed":
            if type(item.get("value")) is not int or item["value"] < 0:
                raise CandidateBuildError(f"normalized ACT has invalid observed {source_name}")
            voters_total = by_name.get("votant")
            voters_positive = (
                isinstance(voters_total, Mapping)
                and voters_total.get("state") == "observed"
                and type(voters_total.get("value")) is int
                and voters_total["value"] > 0
            )
            if (
                geographic_endpoint
                and field == "registered_electors"
                and item["value"] == 0
                and voters_positive
            ):
                # This geographic ACT endpoint uses a zero placeholder for the
                # census while publishing positive voters. Keep raw normalized
                # data/provenance intact, but never present it as an electorate
                # or derive turnout from it.
                values[field] = {"value": None, "status": "unavailable"}
            else:
                values[field] = {"value": item["value"], "status": "observed"}
        else:
            values[field] = {"value": None, "status": item["state"]}
    return values


def _result_candidates(
    normalized: Mapping[str, Any], profile: _ElectionProfile
) -> list[dict[str, Any]]:
    source = normalized.get("candidates")
    if not isinstance(source, list):
        raise CandidateBuildError("normalized ACT has no candidates")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in source:
        if not isinstance(raw, Mapping):
            raise CandidateBuildError("normalized ACT candidate is not an object")
        reviewed = profile.candidates.get(
            (str(raw.get("party_code")), str(raw.get("candidate_code")))
        )
        votes = raw.get("votes")
        if reviewed is None or not isinstance(votes, Mapping):
            raise CandidateBuildError("normalized ACT has an unreviewed candidate")
        status = votes.get("state")
        if status == "observed":
            if type(votes.get("value")) is not int or votes["value"] < 0:
                raise CandidateBuildError("normalized ACT has invalid observed candidate votes")
            metric: dict[str, object] = {"value": votes["value"], "status": "observed"}
        elif status in {"unknown", "unavailable"}:
            metric = {"value": None, "status": status}
        else:
            raise CandidateBuildError("normalized ACT has invalid candidate vote state")
        candidate_id = str(reviewed[0] if isinstance(reviewed, tuple) else reviewed["id"])
        if candidate_id in seen:
            raise CandidateBuildError("normalized ACT has duplicate reviewed candidates")
        seen.add(candidate_id)
        items.append({"candidate_id": candidate_id, "votes": metric})
    if seen != {
        str(candidate[0] if isinstance(candidate, tuple) else candidate["id"])
        for candidate in profile.candidates.values()
    }:
        raise CandidateBuildError("normalized ACT does not contain every reviewed slate")
    return sorted(items, key=lambda item: str(item["candidate_id"]))


def _act_provenance(normalized: Mapping[str, Any], *, data_version: str) -> dict[str, object]:
    raw = normalized.get("provenance")
    if not isinstance(raw, Mapping):
        raise CandidateBuildError("normalized ACT lacks provenance")
    return {
        "data_version": data_version,
        "source_type": raw.get("source_type"),
        "legal_status": raw.get("legal_status"),
        "source_url": raw.get("source_url"),
        "retrieved_at": raw.get("retrieved_at"),
        "content_hash": raw.get("content_hash"),
        "parser_version": raw.get("parser_version"),
        "transform_version": raw.get("transform_version"),
        "methodology_version": None,
    }


def _normalized_plan_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Bind normalized output to the ledger row that retained its raw source."""
    try:
        normalized = json.loads(str(row["normalized_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise CandidateBuildError("completed plan has invalid normalized JSON") from exc
    if not isinstance(normalized, dict):
        raise CandidateBuildError("completed plan normalized record is not an object")
    provenance = normalized.get("provenance")
    if (
        normalized.get("scope_code") != row.get("scope_code")
        or normalized.get("grain") != row.get("grain")
        or not isinstance(provenance, Mapping)
        or provenance.get("source_url") != row.get("source_url")
        or (
            row.get("source_hash") is not None
            and provenance.get("content_hash") != row.get("source_hash")
        )
    ):
        raise CandidateBuildError("normalized plan record is detached from its source ledger row")
    return normalized


def _geographic_snapshot_records(
    *,
    state_directory: Path,
    places_plan_id: str,
    mesas_plan_id: str,
    data_version: str,
    nomenclator_payload: object,
    nomenclator_hash: str,
    election_slug: str,
    profile: _ElectionProfile | None = None,
    expected_mesas: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[str, ...],
    dict[str, int | str],
]:
    """Materialize a verified sample geography; mismatched rollups remain blockers."""
    if profile is None:
        try:
            profile = _PROFILES[election_slug]
        except KeyError as exc:
            raise CandidateBuildError(
                "geographic records require a reviewed election profile"
            ) from exc
    database = state_directory / "crawl.sqlite3"
    places_plan, place_rows = _completed_plan_rows(database, places_plan_id, stage="places")
    mesas_plan, mesa_rows = _completed_plan_rows(database, mesas_plan_id, stage="mesas")
    if places_plan["nomenclator_hash"] != mesas_plan["nomenclator_hash"]:
        raise CandidateBuildError("place and mesa plans use different nomenclator snapshots")
    try:
        nomenclator = parse_nomenclator(nomenclator_payload, election_id="1")
    except PrecountSchemaError as exc:
        raise CandidateBuildError(f"cannot materialize geographic hierarchy: {exc}") from exc
    by_code = {scope.code: scope for scope in nomenclator.scopes}
    by_index = {scope.index: scope for scope in nomenclator.scopes}
    if places_plan["nomenclator_hash"] != nomenclator_hash:
        raise CandidateBuildError("place plan is detached from the exact nomenclator snapshot")

    places: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for row in place_rows:
        normalized = _normalized_plan_record(row)
        code = row["scope_code"]
        if row["grain"] != "polling_place" or code not in by_code:
            raise CandidateBuildError("place plan row is not a nomenclator polling place")
        places[code] = (row, normalized)
    mesa_by_place: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {
        code: [] for code in places
    }
    for row in mesa_rows:
        normalized = _normalized_plan_record(row)
        parent = row["parent_scope_code"]
        if (
            row["grain"] != "mesa"
            or parent not in mesa_by_place
            or not row["scope_code"].startswith(parent)
        ):
            raise CandidateBuildError(
                "mesa plan is not canonically bound to a selected polling place"
            )
        mesa_by_place[parent].append((row, normalized))

    selected_scopes: dict[str, Any] = {"00": by_code["00"]}
    for code in places:
        current = by_code[code]
        while current.code != "00":
            selected_scopes[current.code] = current
            current = by_index[current.parent_indices[0]]
    levels = {1: "national", 2: "department", 3: "municipality", 4: "zone", 6: "polling_place"}
    geographies: list[dict[str, Any]] = []
    for scope in selected_scopes.values():
        if scope.level == 1:
            geographies.append(
                {
                    "id": "CO",
                    "level": "national",
                    "code": scope.code,
                    "name": scope.name,
                    "parent_id": None,
                    "authoritative_coordinates": None,
                }
            )
        else:
            parent = by_index[scope.parent_indices[0]]
            geographies.append(
                {
                    "id": f"scope:{scope.code}",
                    "level": levels[scope.level],
                    "code": scope.code,
                    "name": scope.name,
                    "parent_id": "CO" if parent.level == 1 else f"scope:{parent.code}",
                    "authoritative_coordinates": None,
                }
            )

    mesas: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    for place_code, (_, place) in sorted(places.items()):
        place_id = f"scope:{place_code}"
        place_metrics = _result_metrics(place, geographic_endpoint=True)
        place_candidates = _result_candidates(place, profile)
        results.append(
            {
                "id": f"precount-place-{place_code}",
                "election_slug": election_slug,
                "geography_id": place_id,
                "geography_level": "polling_place",
                "mesa_id": None,
                **place_metrics,
                "candidates": place_candidates,
                "provenance": _act_provenance(place, data_version=data_version),
            }
        )
        children = sorted(mesa_by_place[place_code], key=lambda item: item[0]["scope_code"])
        for row, mesa in children:
            mesa_id = row["scope_code"]
            scope = by_code.get(place_code)
            assert scope is not None
            ancestry = []
            current = scope
            while current.level > 1:
                current = by_index[current.parent_indices[0]]
                ancestry.append(current)
            municipality = next(value for value in ancestry if value.level == 3)
            department = next(value for value in ancestry if value.level == 2)
            mesas.append(
                {
                    "id": mesa_id,
                    "display_number": mesa_id[len(place_code) :],
                    "polling_place_id": place_id,
                    "municipality_id": f"scope:{municipality.code}",
                    "department_id": f"scope:{department.code}",
                }
            )
            results.append(
                {
                    "id": f"precount-mesa-{mesa_id}",
                    "election_slug": election_slug,
                    "geography_id": place_id,
                    "geography_level": "mesa",
                    "mesa_id": mesa_id,
                    **_result_metrics(mesa, geographic_endpoint=True),
                    "candidates": _result_candidates(mesa, profile),
                    "provenance": _act_provenance(mesa, data_version=data_version),
                }
            )
        # A partial plan may contain a place with zero enumerated mesas; that is a blocker,
        # not an invitation to infer a missing child or a final total.
        if not children:
            blockers.append(
                f"No parsed canonical mesas were available for polling place {place_code}."
            )
            continue
        for field in (*_result_metrics(place, geographic_endpoint=True), "candidates"):
            if field == "candidates":
                expected = {item["candidate_id"]: item["votes"] for item in place_candidates}
                actual_rows = [
                    {
                        item["candidate_id"]: item["votes"]
                        for item in _result_candidates(item[1], profile)
                    }
                    for item in children
                ]
                for candidate_id, metric in expected.items():
                    child_metrics = [item[candidate_id] for item in actual_rows]
                    if (
                        metric["status"] != "observed"
                        or any(value["status"] != "observed" for value in child_metrics)
                        or sum(value["value"] for value in child_metrics) != metric["value"]
                    ):
                        blockers.append(
                            "Mesa sum does not exactly match official polling-place "
                            f"{place_code} candidate {candidate_id}."
                        )
            else:
                expected_metric = place_metrics[field]
                child_metrics = [
                    _result_metrics(item[1], geographic_endpoint=True)[field] for item in children
                ]
                if field == "registered_electors" and all(
                    metric["status"] == "unavailable" for metric in child_metrics
                ):
                    # Polling-place census is published, but this mesa endpoint does
                    # not publish the same metric. Do not infer or apportion it.
                    continue
                if (
                    expected_metric["status"] != "observed"
                    or any(value["status"] != "observed" for value in child_metrics)
                    or sum(value["value"] for value in child_metrics) != expected_metric["value"]
                ):
                    blockers.append(
                        "Mesa sum does not exactly match official polling-place "
                        f"{place_code} {field}."
                    )
    expected_polling_places = sum(1 for scope in nomenclator.scopes if scope.level == 6)
    coverage = {
        "status": (
            "sample_limited"
            if bool(places_plan["sample_limited"]) or bool(mesas_plan["sample_limited"])
            else "full_scope"
        ),
        "expected_polling_places": expected_polling_places,
        "retrieved_polling_places": len(place_rows),
        # The national ACT is the authoritative expected mesa count; the plan rows
        # are the observed collection count and must never be promoted to a total.
        "expected_mesas": expected_mesas,
        "retrieved_mesas": len(mesa_rows),
    }
    return geographies, mesas, results, tuple(sorted(set(blockers))), coverage


def build_national_precount_candidate(
    *,
    catalog: SourceCatalog,
    state_directory: Path,
    plan_id: str,
    output_directory: Path,
    manifest_directory: Path,
    git_commit: str = "uncommitted-worktree",
    places_plan_id: str | None = None,
    mesas_plan_id: str | None = None,
) -> CandidateBuild:
    """Build, but never activate, a real national candidate snapshot."""
    if (places_plan_id is None) != (mesas_plan_id is None):
        raise CandidateBuildError(
            "geographic materialization requires both a places and a mesas plan"
        )
    profile = _profile(catalog)
    precount_source = catalog.precount_source()
    normalized = _read_national_row(state_directory / "crawl.sqlite3", plan_id)
    if precount_source.election_id is not None and normalized.get("election_id") not in {
        None,
        precount_source.election_id,
    }:
        raise CandidateBuildError("national ACT election identifier differs from catalog")
    metrics = _observed_metrics(normalized)
    candidates, candidate_results = _candidate_data(normalized, profile)
    provenance_raw = normalized.get("provenance")
    if not isinstance(provenance_raw, Mapping):
        raise CandidateBuildError("normalized national ACT lacks provenance")
    source_hash = _required_text(provenance_raw.get("content_hash"), "content_hash")
    retrieved_at = _required_text(provenance_raw.get("retrieved_at"), "retrieved_at")
    source_url = _required_text(provenance_raw.get("source_url"), "source_url")

    final_declaration = catalog.final_declaration_source()
    final_reference: dict[str, object] | None = None
    if final_declaration is not None:
        final_url = final_declaration.entrypoints.get(
            "declaration"
        ) or final_declaration.entrypoints.get("declaration_resolution")
        if final_url is None:
            raise CandidateBuildError(
                "final-declaration catalog source has no official reference URL"
            )
        final_reference = {
            "id": final_declaration.id,
            "source_url": final_url,
            "catalog_version": catalog.catalog_version,
            "catalog_verified_at": catalog.verified_at,
        }
        final_reference_bytes = json.dumps(
            final_reference, sort_keys=True, separators=(",", ":")
        ).encode()
        final_reference["content_hash"] = hashlib.sha256(final_reference_bytes).hexdigest()
        final_reference["byte_size"] = len(final_reference_bytes)
    checkpoint = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    object_store = LocalObjectStore(state_directory / "objects")
    root_snapshots = {
        identifier: checkpoint.latest(url)
        for identifier, url in catalog.manifest_entrypoints().items()
    }
    if any(snapshot is None for snapshot in root_snapshots.values()):
        raise CandidateBuildError("candidate build requires every checked official root snapshot")
    national_snapshot = checkpoint.latest(source_url)
    if national_snapshot is None or national_snapshot.content_hash != source_hash:
        raise CandidateBuildError("national normalized fact is detached from its raw snapshot")
    scrutiny_snapshot = root_snapshots.get("scrutiny_manifest")
    scrutiny_manifest: Mapping[str, object] | None = None
    if profile.require_legal_material:
        if scrutiny_snapshot is None:
            raise CandidateBuildError("round two requires the declared scrutiny manifest snapshot")
        scrutiny_raw = (object_store.root / scrutiny_snapshot.object_key).read_bytes()
        decoded_scrutiny = json.loads(scrutiny_raw)
        if not isinstance(decoded_scrutiny, Mapping):
            raise CandidateBuildError("scrutiny root snapshot is not a manifest object")
        scrutiny_manifest = decoded_scrutiny

    version_material = {
        "catalog_version": catalog.catalog_version,
        "profile": {
            "slug": catalog.election_slug,
            "round": profile.round,
            "candidates": [
                {"party_code": key[0], "candidate_code": key[1], "identity": value}
                for key, value in sorted(profile.candidates.items())
            ],
        },
        "git_commit": git_commit,
        "parser_version": _PARSER_VERSION,
        "transform_version": _TRANSFORM_VERSION,
        "geography_transform_version": _GEOGRAPHY_TRANSFORM_VERSION,
        "geographic_plans": [places_plan_id, mesas_plan_id],
        "sources": sorted(
            [
                *(snapshot.content_hash for snapshot in root_snapshots.values() if snapshot),
                national_snapshot.content_hash,
                *([str(final_reference["content_hash"])] if final_reference is not None else []),
            ]
        ),
    }
    release_digest = hashlib.sha256(
        json.dumps(version_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    release_id = f"{profile.release_prefix}-{release_digest[:16]}"
    created_at = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    release_root = output_directory / release_id

    provenance = {
        "data_version": release_id,
        "source_type": "pre_count",
        "legal_status": "preliminary",
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_hash": source_hash,
        "parser_version": _PARSER_VERSION,
        "transform_version": _TRANSFORM_VERSION,
        "methodology_version": None,
    }
    election = {
        "slug": catalog.election_slug,
        "name": {
            "es": profile.name_es,
            "en": profile.name_en,
        },
        "round": profile.round,
        "election_date": profile.election_date,
        "candidates": candidates,
    }
    valid_votes = metrics["votval"]
    candidate_summaries = [
        {
            "candidate": candidate,
            "votes": next(
                item["votes"]
                for item in candidate_results
                if item["candidate_id"] == candidate["id"]
            ),
            "share": next(
                item["votes"]["value"]
                for item in candidate_results
                if item["candidate_id"] == candidate["id"]
            )
            / valid_votes,
        }
        for candidate in candidates
    ]
    summary = {
        "election_slug": catalog.election_slug,
        "election_name": election["name"],
        "round": profile.round,
        "election_date": profile.election_date,
        "data_version": release_id,
        "release_status": "candidate",
        "synthetic": False,
        "completion": {
            "expected": metrics["metota"],
            "reported": metrics["mesesc"],
            "percent": metrics["mesesc"] / metrics["metota"],
        },
        "registered_electors": _metric(metrics["centota"]),
        "voters": _metric(metrics["votant"]),
        "turnout": metrics["votant"] / metrics["centota"],
        "valid_votes": _metric(valid_votes),
        "blank_votes": _metric(metrics["votblan"]),
        "null_votes": _metric(metrics["votnul"]),
        "unmarked_votes": _metric(metrics["votnma"]),
        "candidates": candidate_summaries,
        "coverage": {
            "expected": 1,
            "retrieved": 1,
            "parsed": 1,
            "missing": 0,
            "ambiguous": 0,
            "excluded": 0,
        },
        "reconciliation": {"status": "blocked", "checked_facts": 1, "exceptions": 0},
        "provenance": provenance,
    }
    result = {
        "id": "precount-national-00",
        "election_slug": catalog.election_slug,
        "geography_id": "CO",
        "geography_level": "national",
        "mesa_id": None,
        "registered_electors": summary["registered_electors"],
        "voters": summary["voters"],
        "valid_votes": summary["valid_votes"],
        "blank_votes": summary["blank_votes"],
        "null_votes": summary["null_votes"],
        "unmarked_votes": summary["unmarked_votes"],
        "candidates": candidate_results,
        "provenance": provenance,
    }
    candidate_total = sum(item["votes"]["value"] for item in candidate_results)
    if candidate_total + metrics["votblan"] != valid_votes:
        raise CandidateBuildError("candidate plus blank vote arithmetic failed")
    if valid_votes + metrics["votnul"] + metrics["votnma"] != metrics["votant"]:
        raise CandidateBuildError("valid/null/unmarked voter arithmetic failed")
    if metrics["votant"] + metrics["absten"] != metrics["centota"]:
        raise CandidateBuildError("voter/abstention/elector arithmetic failed")

    geographies: list[dict[str, Any]] = [
        {
            "id": "CO",
            "level": "national",
            "code": "00",
            "name": "Colombia",
            "parent_id": None,
            "authoritative_coordinates": None,
        }
    ]
    mesas: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = [result]
    geographic_blockers: tuple[str, ...] = ()
    if places_plan_id is not None and mesas_plan_id is not None:
        nomenclator_snapshot = root_snapshots["precount_nomenclator"]
        assert nomenclator_snapshot is not None
        try:
            nomenclator_payload = json.loads(
                (object_store.root / nomenclator_snapshot.object_key).read_bytes()
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CandidateBuildError("nomenclator root snapshot cannot be decoded") from exc
        (
            geographic_geographies,
            mesas,
            geographic_results,
            geographic_blockers,
            geographic_coverage,
        ) = _geographic_snapshot_records(
            state_directory=state_directory,
            places_plan_id=places_plan_id,
            mesas_plan_id=mesas_plan_id,
            data_version=release_id,
            nomenclator_payload=nomenclator_payload,
            nomenclator_hash=nomenclator_snapshot.content_hash,
            election_slug=catalog.election_slug,
            profile=profile,
            expected_mesas=metrics["metota"],
        )
        geographies = geographic_geographies
        results.extend(geographic_results)
        summary["geographic_collection_coverage"] = geographic_coverage
        # A sample's exact place rollup is a useful partial check, never a
        # release-wide reconciliation. The controlling national source and
        # publication gates remain outstanding.
        summary["reconciliation"] = {
            "status": "blocked",
            "checked_facts": len(geographic_results),
            "exceptions": len(geographic_blockers),
        }

    nested_artifacts = tuple(
        export_dataset(
            [result],
            name="national-precount-results",
            directory=release_root,
            format=format_name,
        )
        for format_name in ("json", "parquet")
    )
    flat_artifact = export_dataset(
        [_flat_download_row(result, candidates)],
        name="national-precount-results-flat",
        directory=release_root,
        format="csv",
    )
    artifacts = (*nested_artifacts, flat_artifact)

    root_coverage = {
        "expected": 1,
        "retrieved": 1,
        "parsed": 1,
        "missing": 0,
        "ambiguous": 0,
        "excluded": 0,
    }
    configuration = root_snapshots["precount_configuration"]
    nomenclator = root_snapshots["precount_nomenclator"]
    assert configuration is not None and nomenclator is not None
    sources = [
        _source_from_snapshot(
            identifier=f"registraduria-precount-configuration-{profile.source_suffix}",
            source_type="pre_count",
            legal_status="preliminary",
            snapshot=configuration,
            parser_version="registraduria-config@1.0.0",
            transform_version="source-root@1.0.0",
            coverage=root_coverage,
        ),
        _source_from_snapshot(
            identifier=f"registraduria-precount-nomenclator-{profile.source_suffix}",
            source_type="pre_count",
            legal_status="preliminary",
            snapshot=nomenclator,
            parser_version="registraduria-nomenclator@1.0.0",
            transform_version="geography-graph@1.0.0",
            coverage=root_coverage,
        ),
        _source_from_snapshot(
            identifier=f"registraduria-precount-national-{profile.source_suffix}",
            source_type="pre_count",
            legal_status="preliminary",
            snapshot=national_snapshot,
            parser_version=_PARSER_VERSION,
            transform_version=_TRANSFORM_VERSION,
            coverage=root_coverage,
        ),
    ]
    if scrutiny_snapshot is not None and scrutiny_manifest is not None:
        sources.append(
            _source_from_snapshot(
                identifier=f"registraduria-scrutiny-manifest-{profile.source_suffix}",
                source_type="scrutiny",
                legal_status="official_scrutiny",
                snapshot=scrutiny_snapshot,
                parser_version="registraduria-scrutiny-index@1.0.0",
                transform_version="manifest-plan@1.0.0",
                coverage={
                    "expected": len(scrutiny_manifest),
                    "retrieved": 1,
                    "parsed": 1,
                    "missing": len(scrutiny_manifest) - 1,
                    "ambiguous": 0,
                    "excluded": 0,
                },
            )
        )
    if final_reference is not None:
        sources.append(
            {
                "id": f"cne-final-declaration-{profile.source_suffix}",
                "source_type": "final_declaration",
                "legal_status": "controlling_final",
                "source_url": str(final_reference["source_url"]),
                "retrieved_at": catalog.verified_at,
                "content_hash": str(final_reference["content_hash"]),
                "media_type": "application/vnd.election.source-reference+json",
                "byte_size": cast(int, final_reference["byte_size"]),
                "parser_version": "cne-reference-index@1.0.0",
                "transform_version": "catalog-reference-only@1.0.0",
                "coverage": {
                    "expected": 1,
                    "retrieved": 0,
                    "parsed": 0,
                    "missing": 0,
                    "ambiguous": 0,
                    "excluded": 1,
                },
            }
        )
    titles = {
        "national-precount-results": {
            "es": "Resultado nacional preliminar · JSON/Parquet",
            "en": "Preliminary national result · JSON/Parquet",
        },
        "national-precount-results-flat": {
            "es": "Resultado nacional preliminar · CSV plano",
            "en": "Preliminary national result · flat CSV",
        },
    }
    artifact_base = f"https://eleccionesabiertas.co/releases/{release_id}"
    manifest = build_candidate_manifest(
        release_id=release_id,
        election_slug=catalog.election_slug,
        methodology_version="audit-priority-v1.0.0",
        created_at=created_at,
        git_commit=git_commit,
        sources=sources,
        datasets=artifacts,
        artifact_base_url=artifact_base,
        dataset_schema_url="https://eleccionesabiertas.co/schemas/result-fact.schema.json",
        dataset_schema_urls={
            "national-precount-results-flat": (
                "https://eleccionesabiertas.co/schemas/result-fact-flat.schema.json"
            )
        },
        dataset_titles=titles,
        dataset_filters={
            name: {"source_type": "pre_count", "geography_level": "national"} for name in titles
        },
        notes=(
            {
                "es": (
                    "Candidato local: muestra el ACT nacional de preconteo. La declaración final "
                    "del CNE se conserva únicamente como enlace oficial y no se descarga ni "
                    "transcribe; "
                    "faltan la recolección por mesa y las validaciones estadísticas."
                ),
                "en": (
                    "Local candidate: shows the national pre-count ACT. The CNE final declaration "
                    "is retained only as an external official link and is neither downloaded nor "
                    "transcribed; the mesa crawl and "
                    "statistical validation are incomplete."
                ),
            }
            if profile.require_legal_material
            else {
                "es": (
                    "Candidato local: muestra únicamente el ACT nacional de preconteo de primera "
                    "vuelta. No se ha incorporado una fuente estructurada de escrutinio ni una "
                    "declaración final; faltan la recolección por mesa y las validaciones."
                ),
                "en": (
                    "Local candidate: shows only the first-round national pre-count ACT. No "
                    "structured scrutiny source or final declaration has been incorporated; mesa "
                    "collection and validation remain incomplete."
                ),
            }
        ),
        aggregate_reconciled=False,
        statistical_validation_passed=False,
        wording_validation_passed=False,
    )
    artifact = materialize_api_snapshot(
        manifest=manifest,
        election=election,
        summary=summary,
        geographies=geographies,
        mesas=mesas,
        results=results,
        provenance=provenance,
    )
    manifest_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_directory / f"{release_id}.json"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
        raise CandidateBuildError("candidate release id already has a different manifest")
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest_bytes)
    snapshot_path = release_root / "api-snapshot.json"
    if snapshot_path.exists() and snapshot_path.read_bytes() != artifact.canonical_bytes:
        raise CandidateBuildError("candidate release id already has a different API snapshot")
    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(artifact.canonical_bytes)
    return CandidateBuild(
        release_id=release_id,
        manifest_path=manifest_path,
        snapshot_path=snapshot_path,
        snapshot_hash=artifact.sha256,
        dataset_artifacts=tuple(artifacts),
        publication_blockers=(
            *(
                ("CNE E-26 totals await two matching independent human entries.",)
                if profile.require_legal_material
                else (
                    "No reviewed structured scrutiny source is incorporated for first round.",
                    "No reviewed controlling final declaration is incorporated for first round.",
                )
            ),
            "Mesa-level pre-count coverage and exact rollup reconciliation are incomplete.",
            *geographic_blockers,
            "Review-signal computation and synthetic false-discovery validation are incomplete.",
            "Wording, privacy, accessibility, performance, and end-to-end release gates remain.",
        ),
    )


__all__ = [
    "CandidateBuild",
    "CandidateBuildError",
    "build_national_precount_candidate",
]
