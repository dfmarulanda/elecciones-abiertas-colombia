"""Bounded, immutable PostgreSQL loader for historical release artifacts.

Loading only creates ``internal`` exposure rows.  It is deliberately not an
activation operation: a separate, reviewed publication workflow is required
before public readers can see a release.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from sqlalchemy import Connection, Engine, text


class ReleaseLoadError(ValueError):
    pass


_PAIR = {
    "contextual_baseline": "context_only",
    "final_declaration": "controlling_final",
    "scrutiny": "official_scrutiny",
    "pre_count": "preliminary",
    "e14_delegate": "documentary_evidence",
    "e14_transmission": "documentary_evidence",
}
_METRICS_JSON = json.dumps(
    {
        name: {"value": None, "status": "unavailable"}
        for name in (
            "registered_electors",
            "voters",
            "valid_votes",
            "blank_votes",
            "null_votes",
            "unmarked_votes",
        )
    },
    separators=(",", ":"),
)
_LEVEL_RANK = {
    "national": 0,
    "department": 1,
    "municipality": 2,
    "zone": 3,
    "polling_place": 4,
    "mesa": 5,
}
_ROUNDS = {
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
}
_ROW_PROVENANCE_COLUMNS = {
    "round",
    "election_slug",
    "election_date",
    "source_url",
    "content_hash",
    "retrieved_at",
    "data_version",
    "source_type",
    "legal_status",
    "parser_version",
    "transform_version",
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _parquet(path: Path, required: set[str]) -> pq.ParquetFile:
    """Open and schema-check an artifact without decoding its rows."""
    try:
        artifact = pq.ParquetFile(path)
    except (OSError, ValueError, pq.ArrowException) as exc:
        raise ReleaseLoadError(f"cannot read {path.name} as Parquet") from exc
    if not required.issubset(set(artifact.schema_arrow.names)):
        raise ReleaseLoadError(f"{path.name} lacks required columns")
    if artifact.metadata is None or artifact.metadata.num_rows < 0:
        raise ReleaseLoadError(f"{path.name} has no valid Parquet row metadata")
    return artifact


def _batches(path: Path, required: set[str], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    artifact = _parquet(path, required)
    for batch in artifact.iter_batches(batch_size=batch_size):
        # Bounded conversion: never read a complete artifact into Python.
        yield batch.to_pylist()


def _artifact(manifest: dict[str, Any], release_directory: Path, needle: str) -> tuple[Path, int]:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        raise ReleaseLoadError("manifest datasets must be a list")
    matches = [
        item for item in datasets if isinstance(item, dict) and needle in str(item.get("id"))
    ]
    if len(matches) != 1:
        raise ReleaseLoadError(f"manifest must contain exactly one {needle} artifact")
    entry = matches[0]
    expected_rows = entry.get("record_count")
    expected_size = entry.get("byte_size")
    expected_hash = entry.get("content_hash")
    if (
        not isinstance(expected_rows, int)
        or expected_rows < 0
        or not isinstance(expected_size, int)
        or expected_size < 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        raise ReleaseLoadError(f"invalid {needle} artifact metadata")
    paths = list(release_directory.glob(f"*{needle.replace('-parquet', '')}*.parquet"))
    if len(paths) != 1:
        raise ReleaseLoadError(f"expected exactly one local {needle} artifact")
    digest = hashlib.sha256()
    size = 0
    with paths[0].open("rb") as artifact:
        while chunk := artifact.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ReleaseLoadError(f"artifact hash/size mismatch: {paths[0].name}")
    return paths[0], expected_rows


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseLoadError(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    # bool is an int subclass and must not silently become a vote/round.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReleaseLoadError(f"{label} must be an integer")
    return value


def _timestamp(value: object, label: str) -> datetime:
    raw = _require_string(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseLoadError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ReleaseLoadError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _source_map(sources: object) -> dict[int, dict[str, Any]]:
    if not isinstance(sources, list) or not all(isinstance(row, dict) for row in sources):
        raise ReleaseLoadError("manifest sources must be objects")
    by_round: dict[int, dict[str, Any]] = {}
    for source in sources:
        source_type = source.get("source_type")
        if _PAIR.get(str(source_type)) != source.get("legal_status"):
            raise ReleaseLoadError("invalid source type/legal-status role")
        identifier = _require_string(source.get("id"), "source id")
        matching_rounds = [number for number in _ROUNDS if identifier.endswith(f"round-{number}")]
        if len(matching_rounds) != 1 or matching_rounds[0] in by_round:
            raise ReleaseLoadError("sources must identify exactly one distinct 2022 round")
        for field in ("source_url", "content_hash", "parser_version", "transform_version"):
            _require_string(source.get(field), f"source {field}")
        if len(str(source["content_hash"])) != 64:
            raise ReleaseLoadError("source content_hash must be SHA-256")
        _timestamp(source.get("retrieved_at"), "source retrieved_at")
        by_round[matching_rounds[0]] = source
    if set(by_round) != set(_ROUNDS):
        raise ReleaseLoadError("manifest must have one source for each 2022 round")
    return by_round


def _validate_parquet_provenance(
    path: Path,
    source_by_round: dict[int, dict[str, Any]],
    data_version: str,
    batch_size: int,
) -> None:
    """Vector-check every artifact row without materializing Python dictionaries."""
    artifact = _parquet(path, _ROW_PROVENANCE_COLUMNS)
    columns = sorted(_ROW_PROVENANCE_COLUMNS)
    for batch in artifact.iter_batches(batch_size=batch_size, columns=columns):
        combined: Any = None
        for number, source in source_by_round.items():
            slug, election_date, _, _ = _ROUNDS[number]
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


def _validate_provenance(
    row: dict[str, Any], source: dict[str, Any], data_version: str
) -> tuple[int, str]:
    number = _require_int(row.get("round"), "artifact round")
    if number not in _ROUNDS:
        raise ReleaseLoadError("artifact has an unsupported round")
    slug, election_date, _, _ = _ROUNDS[number]
    if row.get("election_slug") != slug or row.get("election_date") != election_date:
        raise ReleaseLoadError("artifact election identity does not match its round")
    if row.get("data_version") != data_version:
        raise ReleaseLoadError("artifact row data_version does not match manifest")
    for field in (
        "source_url",
        "content_hash",
        "retrieved_at",
        "source_type",
        "legal_status",
        "parser_version",
        "transform_version",
    ):
        if row.get(field) != source[field]:
            raise ReleaseLoadError(f"artifact {field} does not match manifest provenance")
    return number, slug


def _validate_geography(
    row: dict[str, Any], source: dict[str, Any], data_version: str
) -> tuple[int, str, tuple[Any, ...], tuple[Any, ...] | None]:
    number, slug = _validate_provenance(row, source, data_version)
    level = _require_string(row.get("level"), "geography level")
    if level not in _LEVEL_RANK:
        raise ReleaseLoadError("unknown geography level")
    identifier = _require_string(row.get("id"), "geography id")
    code = _require_string(row.get("code"), "geography code")
    name = _require_string(row.get("name"), "geography name")
    parent = row.get("parent_id")
    if parent is not None:
        parent = _require_string(parent, "geography parent_id")
    root = f"r{number}"
    expected_parent: str | None
    if level == "national":
        expected_id, expected_parent = f"{root}:co", None
    elif level == "department":
        expected_id, expected_parent = f"{root}:dep:{code}", f"{root}:co"
    elif level == "municipality":
        parts = identifier.split(":")
        if len(parts) != 4 or parts[:2] != [root, "mun"] or parts[-1] != code:
            raise ReleaseLoadError("malformed municipality geography id")
        expected_id, expected_parent = identifier, f"{root}:dep:{parts[2]}"
    elif level == "zone":
        parts = identifier.split(":")
        if len(parts) != 5 or parts[:2] != [root, "zone"] or parts[-1] != code:
            raise ReleaseLoadError("malformed zone geography id")
        expected_id, expected_parent = identifier, f"{root}:mun:{parts[2]}:{parts[3]}"
    elif level == "polling_place":
        parts = identifier.split(":")
        if len(parts) != 6 or parts[:2] != [root, "place"] or parts[-1] != code:
            raise ReleaseLoadError("malformed polling-place geography id")
        expected_id, expected_parent = identifier, f"{root}:zone:{parts[2]}:{parts[3]}:{parts[4]}"
    else:
        parts = identifier.split(":")
        if len(parts) != 7 or parts[:2] != [root, "mesa"] or parts[-1] != code:
            raise ReleaseLoadError("malformed mesa geography id")
        expected_id = identifier
        expected_parent = f"{root}:place:{parts[2]}:{parts[3]}:{parts[4]}:{parts[5]}"
    if identifier != expected_id or parent != expected_parent:
        raise ReleaseLoadError("geography id/parent hierarchy is inconsistent")
    if level == "national":
        canonical_path = identifier
    elif level == "department":
        canonical_path = f"{root}:co/{identifier}"
    elif level == "municipality":
        canonical_path = f"{root}:co/{root}:dep:{parts[2]}/{identifier}"
    elif level == "zone":
        canonical_path = (
            f"{root}:co/{root}:dep:{parts[2]}/{root}:mun:{parts[2]}:{parts[3]}/{identifier}"
        )
    elif level == "polling_place":
        canonical_path = (
            f"{root}:co/{root}:dep:{parts[2]}/{root}:mun:{parts[2]}:{parts[3]}/"
            f"{root}:zone:{parts[2]}:{parts[3]}:{parts[4]}/{identifier}"
        )
    else:
        canonical_path = (
            f"{root}:co/{root}:dep:{parts[2]}/{root}:mun:{parts[2]}:{parts[3]}/"
            f"{root}:zone:{parts[2]}:{parts[3]}:{parts[4]}/"
            f"{root}:place:{parts[2]}:{parts[3]}:{parts[4]}:{parts[5]}/{identifier}"
        )
    geo_row = (slug, identifier, level, code, name, parent, canonical_path)
    mesa_row: tuple[Any, ...] | None = None
    if level == "mesa":
        parts = identifier.split(":")
        mesa_row = (
            slug,
            identifier,
            code,
            f"{root}:place:{parts[2]}:{parts[3]}:{parts[4]}:{parts[5]}",
            f"{root}:mun:{parts[2]}:{parts[3]}",
            f"{root}:dep:{parts[2]}",
        )
    return number, level, geo_row, mesa_row


def _copy_rows(connection: Connection, copy_sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    """COPY a bounded row iterable through SQLAlchemy's active psycopg transaction."""
    driver_connection: Any = connection.connection.driver_connection
    try:
        cursor: Any = driver_connection.cursor()
        with cursor.copy(copy_sql) as copy:
            for row in rows:
                copy.write_row(row)
        cursor.close()
    except AttributeError as exc:
        raise ReleaseLoadError(
            "historical PostgreSQL loader requires a psycopg COPY connection"
        ) from exc


def _copy_geography(
    connection: Connection,
    release_id: str,
    rows: list[tuple[Any, ...]],
    mesas: list[tuple[Any, ...]],
    *,
    geography_table: str,
    mesa_table: str,
) -> None:
    if rows:
        _copy_rows(
            connection,
            f"COPY {geography_table} "
            "(release_id,election_slug,id,level,code,name,parent_id,canonical_path) FROM STDIN",
            ((release_id, *row) for row in rows),
        )
    if mesas:
        _copy_rows(
            connection,
            f"COPY {mesa_table} "
            "(release_id,election_slug,id,display_number,polling_place_id,municipality_id,"
            "department_id) FROM STDIN",
            ((release_id, *row) for row in mesas),
        )


def _copy_result_batch(
    connection: Connection,
    release_id: str,
    facts: list[tuple[Any, ...]],
    categories: list[tuple[Any, ...]],
    *,
    fact_table: str,
    category_table: str,
) -> None:
    if not facts:
        return
    _copy_rows(
        connection,
        f"COPY {fact_table} "
        "(release_id,election_slug,id,geography_id,geography_level,mesa_id,source_id,metrics) "
        "FROM STDIN",
        ((release_id, *row) for row in facts),
    )
    if categories:
        _copy_rows(
            connection,
            f"COPY {category_table} "
            "(release_id,election_slug,result_fact_id,category_key,category_code,category_name,"
            "category_kind,votes,status) "
            "FROM STDIN",
            ((release_id, *row) for row in categories),
        )


def load_historical_2022_release(
    engine: Engine, manifest_path: Path, release_directory: Path, *, batch_size: int = 5_000
) -> str:
    """Load immutable historical-2022 artifacts in one internal-only transaction."""
    if batch_size < 1:
        raise ReleaseLoadError("batch_size must be positive")
    if engine.dialect.name != "postgresql":
        raise ReleaseLoadError("historical loader requires PostgreSQL")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ReleaseLoadError("manifest must be an object")
    release_id = manifest.get("release_id")
    if (
        not isinstance(release_id, str)
        or not release_id
        or manifest.get("data_version") != release_id
    ):
        raise ReleaseLoadError("release_id and data_version must be identical")
    if manifest.get("synthetic") or manifest.get("status") not in {"candidate", "published"}:
        raise ReleaseLoadError("only non-synthetic immutable candidate/published releases can load")
    methodology_version = _require_string(
        manifest.get("methodology_version"), "methodology_version"
    )
    source_by_round = _source_map(manifest.get("sources"))
    raw, raw_rows = _artifact(manifest, release_directory, "mmv-parquet")
    rollups, rollup_rows = _artifact(manifest, release_directory, "rollups-parquet")
    geography, geography_rows = _artifact(manifest, release_directory, "geography-parquet")
    # Footer counts avoid decoding 1.1M raw rows merely to count them.  SHA-256
    # above validates every byte; schema validation prevents a renamed/sparse file.
    if (
        _parquet(
            raw,
            {
                "dep_code",
                "mun_code",
                "zona_code",
                "puesto_code",
                "mesa_code",
            }
            | _ROW_PROVENANCE_COLUMNS,
        ).metadata.num_rows
        != raw_rows
    ):
        raise ReleaseLoadError("raw Parquet record count differs from manifest")
    if (
        _parquet(
            rollups,
            {
                "geography_id",
                "geography_level",
                "category_code",
                "party_code",
                "votes",
            }
            | _ROW_PROVENANCE_COLUMNS,
        ).metadata.num_rows
        != rollup_rows
    ):
        raise ReleaseLoadError("rollups Parquet record count differs from manifest")
    if (
        _parquet(
            geography,
            {
                "level",
                "id",
                "code",
                "name",
                "parent_id",
            }
            | _ROW_PROVENANCE_COLUMNS,
        ).metadata.num_rows
        != geography_rows
    ):
        raise ReleaseLoadError("geography Parquet record count differs from manifest")
    _validate_parquet_provenance(raw, source_by_round, release_id, batch_size)
    manifest_hash = _digest(manifest)

    with engine.begin() as connection:
        existing_hashes = list(
            connection.execute(
                text("SELECT manifest_hash FROM release_exposures WHERE release_id=:r"),
                {"r": release_id},
            ).scalars()
        )
        if existing_hashes:
            if len(existing_hashes) == len(_ROUNDS) and all(
                value == manifest_hash for value in existing_hashes
            ):
                return "noop"
            raise ReleaseLoadError("release id already loaded with a different manifest hash")
        if connection.execute(
            text("SELECT 1 FROM releases WHERE id=:r"), {"r": release_id}
        ).scalar():
            raise ReleaseLoadError(
                "release id is already reserved without a matching immutable exposure"
            )
        # COPY into transaction-local tables first.  This is portable to normal
        # managed PostgreSQL roles (unlike session_replication_role), preserves
        # bounded client memory, and lets us validate every relationship before
        # the constraint-enforced final inserts.
        for staging, live in (
            ("stage_release_geographies", "release_geographies"),
            ("stage_release_mesas", "release_mesas"),
            ("stage_release_result_facts", "release_result_facts"),
            ("stage_release_category_facts", "release_category_facts"),
        ):
            connection.execute(text(f"CREATE TEMP TABLE {staging} (LIKE {live}) ON COMMIT DROP"))

        connection.execute(
            text(
                "INSERT INTO releases "
                "(id,status,synthetic,created_at,methodology_version,manifest) "
                "VALUES (:id,:status,false,:created,:method,CAST(:manifest AS jsonb))"
            ),
            {
                "id": release_id,
                "status": manifest["status"],
                "created": datetime.now(UTC),
                "method": methodology_version,
                "manifest": json.dumps(manifest, separators=(",", ":")),
            },
        )
        for number, (slug, day, es, en) in _ROUNDS.items():
            source = source_by_round[number]
            connection.execute(
                text(
                    "INSERT INTO release_elections "
                    "(release_id,election_slug,name_es,name_en,round,election_date) "
                    "VALUES (:r,:s,:es,:en,:n,:d)"
                ),
                {"r": release_id, "s": slug, "es": es, "en": en, "n": number, "d": day},
            )
            connection.execute(
                text(
                    "INSERT INTO release_sources "
                    "(release_id,election_slug,id,source_type,legal_status,source_url,retrieved_at,"
                    "content_hash,parser_version,transform_version) "
                    "VALUES (:r,:e,:id,:type,:legal,:url,:at,:hash,:parser,:transform)"
                ),
                {
                    "r": release_id,
                    "e": slug,
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

        loaded_geographies = 0
        geography_copy_size = batch_size
        geography_buffer: list[tuple[Any, ...]] = []
        mesa_buffer: list[tuple[Any, ...]] = []
        for batch in _batches(
            geography,
            {
                "level",
                "id",
                "code",
                "name",
                "parent_id",
            }
            | _ROW_PROVENANCE_COLUMNS,
            batch_size,
        ):
            for row in batch:
                number = _require_int(row.get("round"), "geography round")
                geography_source = source_by_round.get(number)
                if geography_source is None:
                    raise ReleaseLoadError("geography has an unsupported round")
                _, _level, geo_row, mesa_row = _validate_geography(
                    row, geography_source, release_id
                )
                geography_buffer.append(geo_row)
                if mesa_row is not None:
                    mesa_buffer.append(mesa_row)
                loaded_geographies += 1
                if len(geography_buffer) >= geography_copy_size:
                    _copy_geography(
                        connection,
                        release_id,
                        geography_buffer,
                        mesa_buffer,
                        geography_table="stage_release_geographies",
                        mesa_table="stage_release_mesas",
                    )
                    geography_buffer = []
                    mesa_buffer = []
            _copy_geography(
                connection,
                release_id,
                geography_buffer,
                mesa_buffer,
                geography_table="stage_release_geographies",
                mesa_table="stage_release_mesas",
            )
            geography_buffer = []
            mesa_buffer = []
        if loaded_geographies != geography_rows:
            raise ReleaseLoadError("geography streamed row count differs from manifest")

        invalid_geography = connection.execute(
            text(
                "SELECT COUNT(*) FROM stage_release_geographies g "
                "LEFT JOIN stage_release_geographies p ON p.release_id=g.release_id "
                "AND p.election_slug=g.election_slug AND p.id=g.parent_id "
                "WHERE g.release_id=:r AND g.parent_id IS NOT NULL AND p.id IS NULL"
            ),
            {"r": release_id},
        ).scalar_one()
        if invalid_geography:
            raise ReleaseLoadError("geography hierarchy contains an orphan")
        facts: list[tuple[Any, ...]] = []
        categories: list[tuple[Any, ...]] = []
        current: tuple[str, str, str] | None = None
        current_level: str | None = None
        current_categories: list[tuple[Any, ...]] = []
        loaded_rollups = 0

        def flush_fact() -> None:
            nonlocal facts, categories, current_categories
            if current is None:
                return
            slug, geography_id, source_id = current
            if current_level is None or not current_categories:
                raise ReleaseLoadError("rollup fact is sparse")
            fact_id = f"{geography_id}:{source_id}"
            facts.append(
                (
                    slug,
                    fact_id,
                    geography_id,
                    current_level,
                    geography_id if current_level == "mesa" else None,
                    source_id,
                    _METRICS_JSON,
                )
            )
            categories.extend((slug, fact_id, *category) for category in current_categories)
            current_categories = []
            if len(facts) >= batch_size:
                _copy_result_batch(
                    connection,
                    release_id,
                    facts,
                    categories,
                    fact_table="stage_release_result_facts",
                    category_table="stage_release_category_facts",
                )
                facts = []
                categories = []

        for batch in _batches(
            rollups,
            {
                "geography_id",
                "geography_level",
                "category_code",
                "category_name",
                "party_code",
                "party_name",
                "votes",
            }
            | _ROW_PROVENANCE_COLUMNS,
            batch_size,
        ):
            for row in batch:
                number = _require_int(row.get("round"), "rollup round")
                rollup_source = source_by_round.get(number)
                if rollup_source is None:
                    raise ReleaseLoadError("rollup has an unsupported round")
                _, slug = _validate_provenance(row, rollup_source, release_id)
                geography_id = _require_string(row.get("geography_id"), "rollup geography_id")
                level = _require_string(row.get("geography_level"), "rollup geography_level")
                if level not in _LEVEL_RANK:
                    raise ReleaseLoadError("rollup has an unknown geography level")
                source_id = rollup_source["id"]
                key = (slug, geography_id, source_id)
                if current is not None and key != current:
                    flush_fact()
                current = key
                current_level = level
                category_code = _require_string(row.get("category_code"), "category_code")
                party_code = _require_string(row.get("party_code"), "party_code")
                current_categories.append(
                    (
                        f"{party_code}:{category_code}",
                        category_code,
                        _require_string(row.get("category_name"), "category_name"),
                        "published_mmv_category",
                        _require_int(row.get("votes"), "votes"),
                        "observed",
                    )
                )
                if current_categories[-1][4] < 0:
                    raise ReleaseLoadError("votes cannot be negative")
                loaded_rollups += 1
        flush_fact()
        _copy_result_batch(
            connection,
            release_id,
            facts,
            categories,
            fact_table="stage_release_result_facts",
            category_table="stage_release_category_facts",
        )
        if loaded_rollups != rollup_rows:
            raise ReleaseLoadError("rollup streamed row count differs from manifest")

        for name, columns in (
            ("stage_geo_identity", "release_id,election_slug,id"),
            ("stage_mesa_identity", "release_id,election_slug,id"),
            ("stage_fact_identity", "release_id,election_slug,id"),
        ):
            table = {
                "stage_geo_identity": "stage_release_geographies",
                "stage_mesa_identity": "stage_release_mesas",
                "stage_fact_identity": "stage_release_result_facts",
            }[name]
            connection.execute(text(f"CREATE INDEX {name} ON {table} ({columns})"))
        invalid_relations = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                " SELECT m.id FROM stage_release_mesas m"
                " LEFT JOIN stage_release_geographies mesa ON "
                " (mesa.release_id,mesa.election_slug,mesa.id)="
                " (m.release_id,m.election_slug,m.id)"
                " LEFT JOIN stage_release_geographies place ON "
                " (place.release_id,place.election_slug,place.id)="
                " (m.release_id,m.election_slug,m.polling_place_id)"
                " LEFT JOIN stage_release_geographies municipality ON "
                " (municipality.release_id,municipality.election_slug,municipality.id)="
                " (m.release_id,m.election_slug,m.municipality_id)"
                " LEFT JOIN stage_release_geographies department ON "
                " (department.release_id,department.election_slug,department.id)="
                " (m.release_id,m.election_slug,m.department_id)"
                " WHERE m.release_id=:r AND (mesa.id IS NULL OR mesa.level<>'mesa'"
                " OR place.id IS NULL OR place.level<>'polling_place'"
                " OR municipality.id IS NULL OR municipality.level<>'municipality'"
                " OR department.id IS NULL OR department.level<>'department')"
                " UNION ALL"
                " SELECT f.id FROM stage_release_result_facts f"
                " LEFT JOIN stage_release_geographies g ON (g.release_id,g.election_slug,g.id)="
                " (f.release_id,f.election_slug,f.geography_id)"
                " LEFT JOIN stage_release_mesas m ON (m.release_id,m.election_slug,m.id)="
                " (f.release_id,f.election_slug,f.mesa_id)"
                " LEFT JOIN release_sources s ON (s.release_id,s.election_slug,s.id)="
                " (f.release_id,f.election_slug,f.source_id)"
                " WHERE f.release_id=:r AND (g.id IS NULL OR s.id IS NULL"
                " OR f.geography_level<>g.level OR (g.level='mesa')<>(f.mesa_id IS NOT NULL)"
                " OR (f.mesa_id IS NOT NULL AND m.id IS NULL))"
                " UNION ALL"
                " SELECT c.result_fact_id FROM stage_release_category_facts c"
                " LEFT JOIN stage_release_result_facts f ON "
                " (f.release_id,f.election_slug,f.id)="
                " (c.release_id,c.election_slug,c.result_fact_id)"
                " WHERE c.release_id=:r AND f.id IS NULL"
                ") invalid"
            ),
            {"r": release_id},
        ).scalar_one()
        if invalid_relations:
            raise ReleaseLoadError("loaded rows violate a scoped relational invariant")
        duplicate_rows = connection.execute(
            text(
                "SELECT COUNT(*) FROM ("
                " SELECT release_id,election_slug,id FROM stage_release_geographies"
                " GROUP BY release_id,election_slug,id HAVING COUNT(*) > 1"
                " UNION ALL SELECT release_id,election_slug,id FROM stage_release_mesas"
                " GROUP BY release_id,election_slug,id HAVING COUNT(*) > 1"
                " UNION ALL SELECT release_id,election_slug,id FROM stage_release_result_facts"
                " GROUP BY release_id,election_slug,id HAVING COUNT(*) > 1"
                " UNION ALL SELECT release_id,election_slug,result_fact_id || ':' || category_key"
                " FROM stage_release_category_facts"
                " GROUP BY release_id,election_slug,result_fact_id,category_key HAVING COUNT(*) > 1"
                ") duplicates"
            )
        ).scalar_one()
        if duplicate_rows:
            raise ReleaseLoadError("artifacts contain duplicate scoped primary keys")
        # Retained release/election ownership FKs stay immediate.  All
        # high-volume relationships have already been checked set-wise above.
        for level in _LEVEL_RANK:
            connection.execute(
                text(
                    "INSERT INTO release_geographies "
                    "(release_id,election_slug,id,level,code,name,parent_id,canonical_path) "
                    "SELECT release_id,election_slug,id,level,code,name,parent_id,canonical_path "
                    "FROM stage_release_geographies WHERE level=:level"
                ),
                {"level": level},
            )
        connection.execute(
            text(
                "INSERT INTO release_mesas "
                "(release_id,election_slug,id,display_number,polling_place_id,municipality_id,"
                "department_id) SELECT release_id,election_slug,id,display_number,polling_place_id,"
                "municipality_id,department_id FROM stage_release_mesas"
            )
        )
        connection.execute(
            text(
                "INSERT INTO release_result_facts "
                "(release_id,election_slug,id,geography_id,geography_level,mesa_id,source_id,"
                "metrics) SELECT release_id,election_slug,id,geography_id,geography_level,mesa_id,"
                "source_id,metrics FROM stage_release_result_facts"
            )
        )
        connection.execute(
            text(
                "INSERT INTO release_category_facts "
                "(release_id,election_slug,result_fact_id,category_key,category_code,category_name,"
                "category_kind,votes,status) SELECT release_id,election_slug,result_fact_id,"
                "category_key,category_code,category_name,category_kind,votes,status "
                "FROM stage_release_category_facts"
            )
        )
        for slug, *_ in _ROUNDS.values():
            connection.execute(
                text(
                    "INSERT INTO release_exposures "
                    "(release_id,election_slug,access_scope,approved_at,manifest_hash) "
                    "VALUES (:r,:e,'internal',NULL,:h)"
                ),
                {"r": release_id, "e": slug, "h": manifest_hash},
            )
        public_exposures = connection.execute(
            text(
                "SELECT COUNT(*) FROM release_exposures "
                "WHERE release_id=:r AND access_scope='public'"
            ),
            {"r": release_id},
        ).scalar_one()
        if public_exposures:
            raise ReleaseLoadError("loader may not grant public exposure")
    return "loaded"
