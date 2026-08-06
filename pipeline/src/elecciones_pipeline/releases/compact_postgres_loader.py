"""Compact PostgreSQL loader for immutable historical context releases.

The public identifiers and provenance remain verbatim. Repeated relational
keys, category labels, and all-unavailable metric JSON are dictionary encoded
inside PostgreSQL so a compressed release does not expand into gigabytes of
duplicated text and indexes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import pyarrow.compute as pc  # type: ignore[import-untyped]
from sqlalchemy import Engine, text

from ._bulk import (
    _PAIR,
    ReleaseLoadError,
    _artifact,
    _batches,
    _copy_rows,
    _digest,
    _parquet,
    _require_int,
    _require_string,
    _timestamp,
)
from .postgres_loader import _ROW_PROVENANCE_COLUMNS

_LEVELS = {
    "national": 0,
    "department": 1,
    "municipality": 2,
    "zone": 3,
    "polling_place": 4,
    "mesa": 5,
}
_METRIC_STATUS_UNAVAILABLE = sum(2 << (offset * 2) for offset in range(6))
_PROFILES = {
    2018: {
        1: (
            "presidencia-2018-round-1",
            "2018-05-27",
            "Primera vuelta presidencial 2018",
            "2018 presidential first round",
        ),
        2: (
            "presidencia-2018-round-2",
            "2018-06-17",
            "Segunda vuelta presidencial 2018",
            "2018 presidential second round",
        ),
    },
    2022: {
        1: (
            "presidencia-2022-round-1",
            "2022-05-29",
            "Primera vuelta presidencial 2022",
            "2022 presidential first round",
        ),
        2: (
            "presidencia-2022-round-2",
            "2022-06-19",
            "Segunda vuelta presidencial 2022",
            "2022 presidential second round",
        ),
    },
}


@dataclass(frozen=True)
class _Geography:
    external_id: str
    level: str
    code: str
    name: str
    parent_external_id: str | None


@dataclass(frozen=True)
class _Category:
    key: str
    code: str
    name: str
    kind: str = "published_mmv_category"


def _hash_fields(hasher: Any, fields: tuple[object, ...]) -> None:
    """Feed a length-prefixed semantic tuple into a reproducible SHA-256."""
    for field in fields:
        encoded = str(field).encode("utf-8")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)


def _source_map(
    sources: object, year: int, rounds: dict[int, tuple[str, str, str, str]]
) -> dict[int, dict[str, Any]]:
    if not isinstance(sources, list) or not all(isinstance(row, dict) for row in sources):
        raise ReleaseLoadError("manifest sources must be objects")
    by_round: dict[int, dict[str, Any]] = {}
    for source in sources:
        if _PAIR.get(str(source.get("source_type"))) != source.get("legal_status"):
            raise ReleaseLoadError("invalid source type/legal-status role")
        if (
            source.get("source_type") != "contextual_baseline"
            or source.get("legal_status") != "context_only"
        ):
            raise ReleaseLoadError("compact loader accepts context-only sources")
        identifier = _require_string(source.get("id"), "source id")
        expected_prefix = f"registraduria-observatorio-{year}-round-"
        if not identifier.startswith(expected_prefix):
            raise ReleaseLoadError("source id does not match the historical year")
        try:
            number = int(identifier.removeprefix(expected_prefix))
        except ValueError as exc:
            raise ReleaseLoadError("source id has an invalid round") from exc
        if number not in rounds or number in by_round:
            raise ReleaseLoadError("sources must identify each historical round once")
        for field in (
            "source_url",
            "content_hash",
            "parser_version",
            "transform_version",
        ):
            _require_string(source.get(field), f"source {field}")
        if len(str(source["content_hash"])) != 64:
            raise ReleaseLoadError("source content_hash must be SHA-256")
        _timestamp(source.get("retrieved_at"), "source retrieved_at")
        by_round[number] = source
    if set(by_round) != set(rounds):
        raise ReleaseLoadError("manifest must have one source for each round")
    return by_round


def _validate_manifest(manifest: dict[str, Any], year: int) -> tuple[str, str]:
    release_id = manifest.get("release_id")
    if (
        not isinstance(release_id, str)
        or not release_id
        or manifest.get("data_version") != release_id
    ):
        raise ReleaseLoadError("release_id and data_version must be identical")
    if manifest.get("synthetic") or manifest.get("status") not in {
        "candidate",
        "published",
    }:
        raise ReleaseLoadError("only real immutable candidate/published releases can load")
    if manifest.get("release_class") != "context_only":
        raise ReleaseLoadError("compact historical releases must be context_only")
    if manifest.get("statistical_validation_passed") is not False:
        raise ReleaseLoadError("context-only releases cannot claim statistical validation")
    expected_family = f"historical-{year}-mmv-context-"
    if not release_id.startswith(expected_family):
        raise ReleaseLoadError("release id does not match the requested historical year")
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or any(
        any(word in str(item.get("id", "")).lower() for word in ("review", "signal", "fraud"))
        for item in datasets
        if isinstance(item, dict)
    ):
        raise ReleaseLoadError("context-only releases cannot contain review/signal datasets")
    methodology_version = _require_string(
        manifest.get("methodology_version"), "methodology_version"
    )
    return release_id, methodology_version


def _validate_row_provenance(
    row: dict[str, Any],
    *,
    source_by_round: dict[int, dict[str, Any]],
    rounds: dict[int, tuple[str, str, str, str]],
    data_version: str,
) -> tuple[int, str]:
    number = _require_int(row.get("round"), "artifact round")
    if number not in rounds:
        raise ReleaseLoadError("artifact has an unsupported round")
    slug, election_date, _, _ = rounds[number]
    source = source_by_round[number]
    expected = {
        "election_slug": slug,
        "election_date": election_date,
        "data_version": data_version,
        **{
            field: source[field]
            for field in (
                "source_url",
                "content_hash",
                "retrieved_at",
                "source_type",
                "legal_status",
                "parser_version",
                "transform_version",
            )
        },
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ReleaseLoadError(f"artifact {field} does not match manifest provenance")
    return number, slug


def _validate_parquet_provenance(
    path: Path,
    *,
    source_by_round: dict[int, dict[str, Any]],
    rounds: dict[int, tuple[str, str, str, str]],
    data_version: str,
    batch_size: int,
) -> None:
    artifact = _parquet(path, _ROW_PROVENANCE_COLUMNS)
    columns = sorted(_ROW_PROVENANCE_COLUMNS)
    for batch in artifact.iter_batches(batch_size=batch_size, columns=columns):
        combined: Any = None
        for number, source in source_by_round.items():
            slug, election_date, _, _ = rounds[number]
            expected = {
                "round": number,
                "election_slug": slug,
                "election_date": election_date,
                "data_version": data_version,
                **{
                    field: source[field]
                    for field in (
                        "source_url",
                        "content_hash",
                        "retrieved_at",
                        "source_type",
                        "legal_status",
                        "parser_version",
                        "transform_version",
                    )
                },
            }
            valid: Any = None
            for field, value in expected.items():
                column = batch.column(batch.schema.get_field_index(field))
                equal = pc.fill_null(pc.equal(column, value), False)
                valid = equal if valid is None else pc.and_(valid, equal)
            combined = valid if combined is None else pc.or_(combined, valid)
        if combined is None or pc.all(combined).as_py() is not True:
            raise ReleaseLoadError(f"{path.name} contains invalid row provenance")


def _geography(
    row: dict[str, Any],
    *,
    source_by_round: dict[int, dict[str, Any]],
    rounds: dict[int, tuple[str, str, str, str]],
    data_version: str,
) -> tuple[int, _Geography]:
    number, _slug = _validate_row_provenance(
        row,
        source_by_round=source_by_round,
        rounds=rounds,
        data_version=data_version,
    )
    level = _require_string(row.get("level"), "geography level")
    if level not in _LEVELS:
        raise ReleaseLoadError("unknown geography level")
    external_id = _require_string(row.get("id"), "geography id")
    code = _require_string(row.get("code"), "geography code")
    name = _require_string(row.get("name"), "geography name")
    parent = row.get("parent_id")
    if parent is not None:
        parent = _require_string(parent, "geography parent_id")
    root = f"r{number}"
    parts = external_id.split(":")
    expected_parent: str | None
    if level == "national":
        expected_id, expected_parent = f"{root}:co", None
    elif level == "department":
        expected_id, expected_parent = f"{root}:dep:{code}", f"{root}:co"
    elif level == "municipality":
        if len(parts) != 4 or parts[:2] != [root, "mun"] or parts[-1] != code:
            raise ReleaseLoadError("malformed municipality geography id")
        expected_id, expected_parent = external_id, f"{root}:dep:{parts[2]}"
    elif level == "zone":
        if len(parts) != 5 or parts[:2] != [root, "zone"] or parts[-1] != code:
            raise ReleaseLoadError("malformed zone geography id")
        expected_id = external_id
        expected_parent = f"{root}:mun:{parts[2]}:{parts[3]}"
    elif level == "polling_place":
        if len(parts) != 6 or parts[:2] != [root, "place"] or parts[-1] != code:
            raise ReleaseLoadError("malformed polling-place geography id")
        expected_id = external_id
        expected_parent = f"{root}:zone:{parts[2]}:{parts[3]}:{parts[4]}"
    else:
        if len(parts) != 7 or parts[:2] != [root, "mesa"] or parts[-1] != code:
            raise ReleaseLoadError("malformed mesa geography id")
        expected_id = external_id
        expected_parent = f"{root}:place:{parts[2]}:{parts[3]}:{parts[4]}:{parts[5]}"
    if external_id != expected_id or parent != expected_parent:
        raise ReleaseLoadError("geography id/parent hierarchy is inconsistent")
    return number, _Geography(external_id, level, code, name, parent)


def _tree_rows(
    geographies: list[_Geography], scope_id: int
) -> tuple[list[tuple[object, ...]], dict[str, int]]:
    by_external = {item.external_id: item for item in geographies}
    if len(by_external) != len(geographies):
        raise ReleaseLoadError("geography artifact contains duplicate ids")
    roots = [item for item in geographies if item.parent_external_id is None]
    if len(roots) != 1 or roots[0].level != "national":
        raise ReleaseLoadError("geography scope must contain exactly one national root")
    children: dict[str, list[str]] = defaultdict(list)
    for item in geographies:
        if item.parent_external_id is None:
            continue
        parent = by_external.get(item.parent_external_id)
        if parent is None or _LEVELS[parent.level] + 1 != _LEVELS[item.level]:
            raise ReleaseLoadError("geography hierarchy contains an invalid parent")
        children[parent.external_id].append(item.external_id)
    local_ids = {
        external_id: offset
        for offset, external_id in enumerate(sorted(by_external), start=1)
    }
    bounds: dict[str, tuple[int, int]] = {}
    counter = 0

    def visit(external_id: str) -> None:
        nonlocal counter
        counter += 1
        left = counter
        for child in sorted(children.get(external_id, ())):
            visit(child)
        counter += 1
        bounds[external_id] = (left, counter)

    visit(roots[0].external_id)
    if len(bounds) != len(geographies):
        raise ReleaseLoadError("geography hierarchy is disconnected")
    rows: list[tuple[object, ...]] = []
    for external_id in sorted(by_external):
        item = by_external[external_id]
        parent_id = (
            None
            if item.parent_external_id is None
            else local_ids[item.parent_external_id]
        )
        rows.append(
            (
                scope_id,
                local_ids[external_id],
                external_id,
                _LEVELS[item.level],
                item.code,
                item.name,
                parent_id,
                *bounds[external_id],
            )
        )
    return rows, local_ids


def _iter_rollups(
    path: Path,
    *,
    source_by_round: dict[int, dict[str, Any]],
    rounds: dict[int, tuple[str, str, str, str]],
    data_version: str,
    batch_size: int,
) -> Iterator[tuple[int, str, str, _Category, int]]:
    required = {
        "geography_id",
        "geography_level",
        "category_code",
        "category_name",
        "party_code",
        "party_name",
        "votes",
    } | _ROW_PROVENANCE_COLUMNS
    for batch in _batches(path, required, batch_size):
        for row in batch:
            number, _slug = _validate_row_provenance(
                row,
                source_by_round=source_by_round,
                rounds=rounds,
                data_version=data_version,
            )
            geography_id = _require_string(row.get("geography_id"), "rollup geography_id")
            geography_level = _require_string(
                row.get("geography_level"), "rollup geography_level"
            )
            if geography_level not in _LEVELS:
                raise ReleaseLoadError("rollup has an unknown geography level")
            category_code = _require_string(row.get("category_code"), "category_code")
            party_code = _require_string(row.get("party_code"), "party_code")
            votes = _require_int(row.get("votes"), "votes")
            if votes < 0:
                raise ReleaseLoadError("votes cannot be negative")
            yield (
                number,
                geography_id,
                geography_level,
                _Category(
                    key=f"{party_code}:{category_code}",
                    code=category_code,
                    name=_require_string(row.get("category_name"), "category_name"),
                ),
                votes,
            )


def load_historical_context_release(
    engine: Engine,
    manifest_path: Path,
    release_directory: Path,
    *,
    year: int,
    batch_size: int = 10_000,
) -> str:
    """Load one 2018/2022 context-only release into compact internal tables."""
    if batch_size < 1:
        raise ReleaseLoadError("batch_size must be positive")
    if engine.dialect.name != "postgresql":
        raise ReleaseLoadError("historical loader requires PostgreSQL")
    rounds = _PROFILES.get(year)
    if rounds is None:
        raise ReleaseLoadError("compact historical loader supports only 2018 and 2022")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ReleaseLoadError("manifest must be an object")
    release_id, methodology_version = _validate_manifest(manifest, year)
    source_by_round = _source_map(manifest.get("sources"), year, rounds)
    raw, raw_rows = _artifact(manifest, release_directory, "mmv-parquet")
    rollups, rollup_rows = _artifact(manifest, release_directory, "rollups-parquet")
    geography, geography_rows = _artifact(
        manifest, release_directory, "geography-parquet"
    )
    if _parquet(raw, _ROW_PROVENANCE_COLUMNS).metadata.num_rows != raw_rows:
        raise ReleaseLoadError("raw Parquet record count differs from manifest")
    if (
        _parquet(rollups, {"geography_id", "geography_level", "votes"}).metadata.num_rows
        != rollup_rows
    ):
        raise ReleaseLoadError("rollups Parquet record count differs from manifest")
    if (
        _parquet(geography, {"level", "id", "parent_id"}).metadata.num_rows
        != geography_rows
    ):
        raise ReleaseLoadError("geography Parquet record count differs from manifest")
    _validate_parquet_provenance(
        raw,
        source_by_round=source_by_round,
        rounds=rounds,
        data_version=release_id,
        batch_size=batch_size,
    )
    manifest_hash = _digest(manifest)

    geographies_by_round: dict[int, list[_Geography]] = defaultdict(list)
    for batch in _batches(
        geography,
        {"level", "id", "code", "name", "parent_id"} | _ROW_PROVENANCE_COLUMNS,
        batch_size,
    ):
        for row in batch:
            number, parsed = _geography(
                row,
                source_by_round=source_by_round,
                rounds=rounds,
                data_version=release_id,
            )
            geographies_by_round[number].append(parsed)
    if sum(map(len, geographies_by_round.values())) != geography_rows:
        raise ReleaseLoadError("geography streamed row count differs from manifest")

    categories_by_round: dict[int, dict[str, _Category]] = defaultdict(dict)
    scanned_rollups = 0
    for number, _geography_id, _level, category, _votes in _iter_rollups(
        rollups,
        source_by_round=source_by_round,
        rounds=rounds,
        data_version=release_id,
        batch_size=batch_size,
    ):
        previous = categories_by_round[number].setdefault(category.key, category)
        if previous != category:
            raise ReleaseLoadError("category code has conflicting immutable definitions")
        scanned_rollups += 1
    if scanned_rollups != rollup_rows:
        raise ReleaseLoadError("rollup streamed row count differs from manifest")

    with engine.begin() as connection:
        existing_hashes = list(
            connection.execute(
                text(
                    "SELECT manifest_hash FROM release_exposures WHERE release_id=:release"
                ),
                {"release": release_id},
            ).scalars()
        )
        if existing_hashes:
            if len(existing_hashes) == len(rounds) and all(
                value == manifest_hash for value in existing_hashes
            ):
                return "noop"
            raise ReleaseLoadError("release id already loaded with a different manifest hash")
        if connection.execute(
            text("SELECT 1 FROM releases WHERE id=:release"), {"release": release_id}
        ).scalar():
            raise ReleaseLoadError(
                "release id is already reserved without matching immutable exposure"
            )
        connection.execute(
            text(
                "INSERT INTO releases "
                "(id,status,synthetic,created_at,methodology_version,manifest) "
                "VALUES (:id,:status,false,:created,:method,CAST(:manifest AS jsonb))"
            ),
            {
                "id": release_id,
                "status": manifest["status"],
                "created": _timestamp(manifest.get("created_at"), "created_at"),
                "method": methodology_version,
                "manifest": json.dumps(manifest, separators=(",", ":")),
            },
        )
        scope_ids: dict[int, int] = {}
        geography_ids: dict[int, dict[str, int]] = {}
        category_ids: dict[int, dict[str, int]] = {}
        for number, (slug, day, name_es, name_en) in rounds.items():
            source = source_by_round[number]
            connection.execute(
                text(
                    "INSERT INTO release_elections "
                    "(release_id,election_slug,name_es,name_en,round,election_date) "
                    "VALUES (:release,:slug,:es,:en,:round,:day)"
                ),
                {
                    "release": release_id,
                    "slug": slug,
                    "es": name_es,
                    "en": name_en,
                    "round": number,
                    "day": day,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO release_sources "
                    "(release_id,election_slug,id,source_type,legal_status,source_url,"
                    "retrieved_at,content_hash,parser_version,transform_version) "
                    "VALUES (:release,:slug,:id,:type,:legal,:url,:at,:hash,:parser,:transform)"
                ),
                {
                    "release": release_id,
                    "slug": slug,
                    "id": source["id"],
                    "type": source["source_type"],
                    "legal": source["legal_status"],
                    "url": source["source_url"],
                    "at": _timestamp(source["retrieved_at"], "source retrieved_at"),
                    "hash": source["content_hash"],
                    "parser": source["parser_version"],
                    "transform": source["transform_version"],
                },
            )
            scope_id = int(
                connection.execute(
                    text(
                        "INSERT INTO context_release_scopes(release_id,election_slug) "
                        "VALUES (:release,:slug) RETURNING id"
                    ),
                    {"release": release_id, "slug": slug},
                ).scalar_one()
            )
            scope_ids[number] = scope_id
            _copy_rows(
                connection,
                "COPY context_sources(scope_id,ordinal,source_id) FROM STDIN",
                [(scope_id, 1, source["id"])],
            )
            geography_rows_for_scope, local_geography_ids = _tree_rows(
                geographies_by_round[number], scope_id
            )
            geography_ids[number] = local_geography_ids
            _copy_rows(
                connection,
                "COPY context_geographies"
                "(scope_id,id,external_id,level,code,name,parent_id,tree_left,tree_right) "
                "FROM STDIN",
                geography_rows_for_scope,
            )
            definitions = categories_by_round[number]
            local_category_ids = {
                key: offset for offset, key in enumerate(sorted(definitions), start=1)
            }
            if len(local_category_ids) > 32_767:
                raise ReleaseLoadError("category dictionary exceeds compact identifier range")
            category_ids[number] = local_category_ids
            _copy_rows(
                connection,
                "COPY context_categories"
                "(scope_id,id,category_key,category_code,category_name,category_kind) "
                "FROM STDIN",
                (
                    (
                        scope_id,
                        local_category_ids[key],
                        key,
                        definitions[key].code,
                        definitions[key].name,
                        definitions[key].kind,
                    )
                    for key in sorted(definitions)
                ),
            )

        fact_buffer: list[tuple[object, ...]] = []
        category_buffer: list[tuple[object, ...]] = []
        current: tuple[int, str, str] | None = None
        current_categories: set[str] = set()
        loaded_rollups = 0
        loaded_facts = 0
        loaded_rollups_by_round: dict[int, int] = defaultdict(int)
        loaded_facts_by_round: dict[int, int] = defaultdict(int)
        semantic_hashes = {number: sha256() for number in rounds}
        content_hashes = {number: sha256() for number in rounds}
        semantic_order: dict[int, tuple[str, str, str, str]] = {}

        def flush() -> None:
            nonlocal fact_buffer, category_buffer
            if fact_buffer:
                _copy_rows(
                    connection,
                    "COPY context_result_facts"
                    "(scope_id,geography_id,source_ordinal,metrics_status,"
                    "registered_electors,voters,valid_votes,blank_votes,null_votes,"
                    "unmarked_votes) FROM STDIN",
                    fact_buffer,
                )
                fact_buffer = []
            if category_buffer:
                _copy_rows(
                    connection,
                    "COPY context_category_facts"
                    "(scope_id,geography_id,source_ordinal,category_id,votes,status) "
                    "FROM STDIN",
                    category_buffer,
                )
                category_buffer = []

        for number, geography_id, level, category, votes in _iter_rollups(
            rollups,
            source_by_round=source_by_round,
            rounds=rounds,
            data_version=release_id,
            batch_size=batch_size,
        ):
            key = (number, level, geography_id)
            if current is not None and key < current:
                raise ReleaseLoadError("rollup facts are not in canonical key order")
            local_geography_id = geography_ids[number].get(geography_id)
            if local_geography_id is None:
                raise ReleaseLoadError("rollup fact references an unknown geography")
            if current != key:
                current = key
                current_categories = set()
                fact_buffer.append(
                    (
                        scope_ids[number],
                        local_geography_id,
                        1,
                        _METRIC_STATUS_UNAVAILABLE,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                )
                loaded_facts += 1
                loaded_facts_by_round[number] += 1
            if category.key in current_categories:
                raise ReleaseLoadError("rollup fact contains a duplicate category")
            current_categories.add(category.key)
            ordered_key = (level, geography_id, category.code, category.key)
            previous_key = semantic_order.get(number)
            if previous_key is not None and ordered_key <= previous_key:
                raise ReleaseLoadError(
                    "rollup category semantic keys are not in strict canonical order"
                )
            semantic_order[number] = ordered_key
            source_id = str(source_by_round[number]["id"])
            _hash_fields(
                semantic_hashes[number],
                (geography_id, source_id, category.key),
            )
            _hash_fields(
                content_hashes[number],
                (geography_id, source_id, category.key, votes, 0),
            )
            category_buffer.append(
                (
                    scope_ids[number],
                    local_geography_id,
                    1,
                    category_ids[number][category.key],
                    votes,
                    0,
                )
            )
            loaded_rollups += 1
            loaded_rollups_by_round[number] += 1
            if len(fact_buffer) >= batch_size:
                flush()
        flush()
        if loaded_rollups != rollup_rows or loaded_facts != geography_rows:
            raise ReleaseLoadError("compact fact/category counts differ from artifacts")
        # The one-time post-COPY digest sort is deliberately memory-bounded so
        # it cannot create a large temporary file on a small deployment volume.
        connection.execute(text("SET LOCAL work_mem='192MB'"))
        connection.execute(text("SET LOCAL max_parallel_workers_per_gather=0"))
        for number, (slug, *_rest) in rounds.items():
            scope_id = scope_ids[number]
            expected = {
                "geographies": len(geographies_by_round[number]),
                "facts": loaded_facts_by_round[number],
                "categories": loaded_rollups_by_round[number],
            }
            observed = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM context_geographies WHERE scope_id=:scope) "
                    "AS geographies,"
                    "(SELECT count(*) FROM context_result_facts WHERE scope_id=:scope) "
                    "AS facts,"
                    "(SELECT count(*) FROM context_category_facts WHERE scope_id=:scope) "
                    "AS categories"
                ),
                {"scope": scope_id},
            ).mappings().one()
            if any(int(observed[key]) != value for key, value in expected.items()):
                raise ReleaseLoadError("compact database row counts differ after COPY")

            database_semantic_hash = sha256()
            database_content_hash = sha256()
            rows = connection.execute(
                text(
                    "SELECT g.external_id,s.source_id,c.category_key,cf.votes,cf.status "
                    "FROM context_category_facts cf "
                    "JOIN context_geographies g ON "
                    "(g.scope_id=cf.scope_id AND g.id=cf.geography_id) "
                    "JOIN context_sources s ON "
                    "(s.scope_id=cf.scope_id AND s.ordinal=cf.source_ordinal) "
                    "JOIN context_categories c ON "
                    "(c.scope_id=cf.scope_id AND c.id=cf.category_id) "
                    "WHERE cf.scope_id=:scope ORDER BY "
                    "CASE g.level WHEN 0 THEN 'national' WHEN 1 THEN 'department' "
                    "WHEN 2 THEN 'municipality' WHEN 3 THEN 'zone' "
                    "WHEN 4 THEN 'polling_place' ELSE 'mesa' END,"
                    "g.external_id,c.category_code,c.category_key"
                ),
                {"scope": scope_id},
            ).mappings().yield_per(batch_size)
            database_count = 0
            for database_row in rows:
                identity = (
                    database_row["external_id"],
                    database_row["source_id"],
                    database_row["category_key"],
                )
                _hash_fields(database_semantic_hash, identity)
                _hash_fields(
                    database_content_hash,
                    (*identity, database_row["votes"], database_row["status"]),
                )
                database_count += 1
            if (
                database_count != expected["categories"]
                or database_semantic_hash.digest()
                != semantic_hashes[number].digest()
                or database_content_hash.digest() != content_hashes[number].digest()
            ):
                raise ReleaseLoadError("compact database semantic digest differs after COPY")
            connection.execute(
                text(
                    "UPDATE context_release_scopes SET geography_count=:geographies,"
                    "result_fact_count=:facts,category_fact_count=:categories,"
                    "semantic_key_hash=:semantic_hash,content_row_hash=:content_hash "
                    "WHERE id=:scope"
                ),
                {
                    "scope": scope_id,
                    **expected,
                    "semantic_hash": semantic_hashes[number].hexdigest(),
                    "content_hash": content_hashes[number].hexdigest(),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO release_exposures"
                    "(release_id,election_slug,access_scope,approved_at,manifest_hash) "
                    "VALUES (:release,:slug,'internal',NULL,:hash)"
                ),
                {"release": release_id, "slug": slug, "hash": manifest_hash},
            )
        if connection.execute(
            text(
                "SELECT count(*) FROM release_exposures "
                "WHERE release_id=:release AND access_scope='public'"
            ),
            {"release": release_id},
        ).scalar_one():
            raise ReleaseLoadError("loader may not grant public exposure")
    return "loaded"
