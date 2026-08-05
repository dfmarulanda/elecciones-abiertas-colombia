"""Immutable Parquet/DuckDB read model for historical context releases."""
# ruff: noqa: E501, S608

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from .repository import ResourceNotFoundError

_LEVELS = ("national", "department", "municipality", "zone", "polling_place", "mesa")
_READ_MODEL_NAME = "historical-geography.duckdb"
_MANIFESTS = {
    "historical-2018-mmv-context-v2-c456aeb032917d5c": (
        4507,
        "ef5daf8fbfebe4cc8d62006cd17801ee7255b15db8bbca8bd01731e261834710",
    ),
    "historical-2022-mmv-context-v2-288e9b41c14730e9": (
        4510,
        "3e26a526b25d359c051e92490fdf9abae75547384a84e9b135cc03c22a55e14c",
    ),
}
# Canonical digests computed from the hash-allowlisted rollup Parquet files.
# They bind the derived category index to an independent value that cannot be
# changed by editing the DuckDB file and its metadata together.
_SOURCE_CATEGORY_DIGESTS = {
    "historical-2018-mmv-context-v2-c456aeb032917d5c": (
        "288fb1ceddd2264e0ea4e2cfb236d146c68e1d16ffbd0517483b92f3b4af0204"
    ),
    "historical-2022-mmv-context-v2-288e9b41c14730e9": (
        "9e85309a9e8837c369b537c366423241c0144e0ba0d8c9d9d142a576ff84f56e"
    ),
}
_EXPECTED_COLUMNS = {
    "geography": {
        "round",
        "election_slug",
        "election_date",
        "level",
        "id",
        "code",
        "name",
        "parent_id",
        "source_url",
        "content_hash",
        "retrieved_at",
        "data_version",
        "source_type",
        "legal_status",
        "parser_version",
        "transform_version",
    },
    "rollups": {
        "round",
        "election_slug",
        "election_date",
        "geography_level",
        "geography_id",
        "category_code",
        "category_name",
        "party_code",
        "party_name",
        "votes",
        "source_url",
        "content_hash",
        "retrieved_at",
        "data_version",
        "source_type",
        "legal_status",
        "parser_version",
        "transform_version",
    },
    "mmv": {
        "round",
        "election_slug",
        "election_date",
        "dep_code",
        "dep_name",
        "mun_code",
        "mun_name",
        "zona_code",
        "puesto_code",
        "puesto_name",
        "mesa_code",
        "corporation_code",
        "corporation_name",
        "circumscription_code",
        "party_code",
        "party_name",
        "category_code",
        "category_name",
        "votes",
        "source_url",
        "content_hash",
        "retrieved_at",
        "data_version",
        "source_type",
        "legal_status",
        "parser_version",
        "transform_version",
    },
}


class HistoricalReleaseError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HistoricalDuckDBRepository:
    """Parameterised SELECT-only access to verified packaged Parquet bytes."""

    is_fixture = False

    def __init__(self, data_path: Path, release_ids: Iterable[str], active_release_id: str) -> None:
        self._data_path = data_path.resolve()
        self._active_release_id = active_release_id
        self._releases: dict[str, dict[str, Any]] = {}
        self._files: dict[str, dict[str, Path]] = {}
        self._source_geography_digests: dict[str, str] = {}
        self._query_slots = threading.BoundedSemaphore(1)
        self._runtime_connection: duckdb.DuckDBPyConnection | None = None
        self._temp_directory = tempfile.TemporaryDirectory(
            prefix="elecciones-duckdb-"
        )
        read_model = self._data_path / _READ_MODEL_NAME
        self._read_model_path = read_model if read_model.is_file() else None
        for release_id in release_ids:
            self._load_release(release_id)
        if active_release_id not in self._releases:
            raise HistoricalReleaseError(
                "ACTIVE_RELEASE is not one of the verified packaged releases"
            )
        if self._read_model_path is not None:
            self._validate_read_model()
            self._open_runtime_connection()

    @property
    def active_release_id(self) -> str:
        return self._active_release_id

    @property
    def data_version(self) -> str:
        return self._active_release_id

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Serialize reads through one reusable connection when an index exists."""
        with self._query_slots:
            if self._runtime_connection is not None:
                yield self._runtime_connection
                return
            connection = self._new_connection()
            try:
                yield connection
            finally:
                connection.close()

    def _new_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(
            ":memory:" if self._read_model_path is None else str(self._read_model_path),
            read_only=self._read_model_path is not None,
            config={
                "threads": "1",
                "memory_limit": "48MB",
                "temp_directory": self._temp_directory.name,
                "max_temp_directory_size": "256MB",
            },
        )

    def _open_runtime_connection(self) -> None:
        if self._runtime_connection is None:
            self._runtime_connection = self._new_connection()

    def close(self) -> None:
        """Close the reusable read-only connection during application shutdown."""
        with self._query_slots:
            if self._runtime_connection is not None:
                self._runtime_connection.close()
                self._runtime_connection = None
            self._temp_directory.cleanup()

    def _geography_relation(self, release_id: str) -> tuple[str, list[object]]:
        if self._read_model_path is not None:
            return "geography", []
        geography, _ = self._paths(release_id)
        return "read_parquet(?)", [str(geography)]

    def _load_release(self, release_id: str) -> None:
        manifest_path = self._data_path / "manifests" / f"{release_id}.json"
        expected_manifest = _MANIFESTS.get(release_id)
        if (
            expected_manifest is None
            or (
                manifest_path.stat().st_size,
                _sha256(manifest_path),
            )
            != expected_manifest
        ):
            raise HistoricalReleaseError("manifest byte/hash allowlist verification failed")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("release_id") != release_id or manifest.get("data_version") != release_id:
            raise HistoricalReleaseError("manifest release identity mismatch")
        if (
            manifest.get("status") != "candidate"
            or manifest.get("git_commit") != "uncommitted-worktree"
            or manifest.get("release_class") != "context_only"
            or manifest.get("statistical_validation_passed") is not False
        ):
            raise HistoricalReleaseError("historical release is not fail-closed context_only")
        directory = self._data_path / "releases" / release_id
        files: dict[str, Path] = {}
        datasets = manifest.get("datasets")
        if not isinstance(datasets, list) or len(datasets) != 3:
            raise HistoricalReleaseError("release must declare exactly three datasets")
        identifiers = [item.get("id") for item in datasets if isinstance(item, dict)]
        year = release_id.split("-", 2)[1]
        expected_ids = {
            f"historical-{year}-mmv-parquet",
            f"historical-{year}-rollups-parquet",
            f"historical-{year}-geography-parquet",
        }
        if set(identifiers) != expected_ids:
            raise HistoricalReleaseError("release dataset ids are invalid or duplicated")
        sources = manifest.get("sources")
        if not isinstance(sources, list) or len(sources) != 2:
            raise HistoricalReleaseError("release must declare exactly two round sources")
        if any(
            source.get("source_type") != "contextual_baseline"
            or source.get("legal_status") != "context_only"
            for source in sources
        ):
            raise HistoricalReleaseError("release source roles are invalid")
        if {source.get("id") for source in sources} != {
            f"registraduria-observatorio-{year}-round-1",
            f"registraduria-observatorio-{year}-round-2",
        }:
            raise HistoricalReleaseError("release source ids are invalid")
        expected_slugs = {
            f"presidencia-{year}-round-1",
            f"presidencia-{year}-round-2",
        }
        if self._slugs(manifest) != expected_slugs:
            raise HistoricalReleaseError("release election slugs are invalid")
        with self._connect() as connection:
            for dataset in datasets:
                identifier = dataset["id"]
                kind = (
                    "geography"
                    if "geography" in identifier
                    else "rollups"
                    if "rollups" in identifier
                    else "mmv"
                )
                matches = sorted(directory.glob(f"*{kind}.parquet"))
                if len(matches) != 1:
                    raise HistoricalReleaseError(f"{identifier} has no unique packaged artifact")
                path = matches[0].resolve()
                if path.parent != directory.resolve():
                    raise HistoricalReleaseError("artifact escaped its immutable release directory")
                if (
                    path.stat().st_size != dataset["byte_size"]
                    or _sha256(path) != dataset["content_hash"]
                ):
                    raise HistoricalReleaseError(f"{identifier} byte/hash verification failed")
                quoted = str(path).replace("'", "''")
                count_row = connection.execute(
                    f"SELECT count(*) FROM read_parquet('{quoted}')"
                ).fetchone()
                assert count_row is not None
                row_count = count_row[0]
                columns = {
                    row[0]
                    for row in connection.execute(
                        f"DESCRIBE SELECT * FROM read_parquet('{quoted}')"
                    ).fetchall()
                }
                if row_count != dataset["record_count"] or columns != _EXPECTED_COLUMNS[kind]:
                    raise HistoricalReleaseError(f"{identifier} schema/row verification failed")
                files[identifier] = path
            geography = next(path for key, path in files.items() if "geography" in key)
            rollups = next(path for key, path in files.items() if "rollups" in key)
            for slug in sorted(expected_slugs):
                proof = connection.execute(
                    """WITH g AS (
                         SELECT id,level FROM read_parquet(?) WHERE election_slug=?
                       ), r AS (
                         SELECT DISTINCT geography_id,geography_level
                         FROM read_parquet(?) WHERE election_slug=?
                       )
                       SELECT
                         (SELECT count(*) FROM g),
                         (SELECT count(DISTINCT id) FROM g),
                         (SELECT count(DISTINCT geography_id) FROM r),
                         (SELECT count(*) FROM (SELECT id FROM g EXCEPT SELECT geography_id FROM r)),
                         (SELECT count(*) FROM (SELECT geography_id FROM r EXCEPT SELECT id FROM g)),
                         (SELECT count(*) FROM (
                            SELECT geography_id,geography_level FROM r
                            EXCEPT SELECT id,level FROM g
                         ))""",
                    [str(geography), slug, str(rollups), slug],
                ).fetchone()
                if (
                    proof is None
                    or proof[0] != proof[1]
                    or proof[0] != proof[2]
                    or tuple(proof[3:]) != (0, 0, 0)
                ):
                    raise HistoricalReleaseError(
                        f"{slug} geography/result keyset verification failed"
                    )
            self._source_geography_digests[release_id] = self._geography_digest(
                connection,
                "read_parquet(?)",
                [str(geography)],
                expected_slugs,
            )
        self._releases[release_id] = manifest
        self._files[release_id] = files

    @staticmethod
    def _geography_digest(
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        relation_params: list[object],
        slugs: Iterable[str],
    ) -> str:
        """Canonical digest of every field that can be served from the geo index."""
        selected_slugs = sorted(slugs)
        digest = hashlib.sha256()
        for slug in selected_slugs:
            cursor = connection.execute(
                f"""SELECT election_slug,round,CAST(election_date AS VARCHAR),
                           level,id,code,name,parent_id
                    FROM {relation}
                    WHERE election_slug=?
                    ORDER BY level,id""",
                [*relation_params, slug],
            )
            while rows := cursor.fetchmany(8192):
                for row in rows:
                    digest.update(
                        json.dumps(
                            row, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")
                    )
                    digest.update(b"\n")
        return digest.hexdigest()

    @staticmethod
    def _category_digest(
        connection: duckdb.DuckDBPyConnection,
        relation: str,
        relation_params: list[object],
        slugs: Iterable[str],
        *,
        grouped: bool,
    ) -> str:
        """Digest compact per-geography hashes without a global category sort."""
        digest = hashlib.sha256()
        for slug in sorted(slugs):
            if grouped:
                statement = f"""SELECT election_slug,geography_id,
                                          category_digest,category_count
                                   FROM {relation}
                                   WHERE election_slug=?
                                   ORDER BY geography_id"""
            else:
                statement = f"""WITH grouped AS (
                         SELECT election_slug,geography_id,
                                list(struct_pack(
                                  category_key := party_code||':'||category_code,
                                  category_code := category_code,
                                  category_name := category_name,
                                  votes := votes
                                ) ORDER BY party_code||':'||category_code) AS categories
                         FROM {relation} WHERE election_slug=?
                         GROUP BY election_slug,geography_id
                       )
                       SELECT election_slug,geography_id,
                              sha256(to_json(categories)),len(categories)
                       FROM grouped ORDER BY geography_id"""
            cursor = connection.execute(statement, [*relation_params, slug])
            while rows := cursor.fetchmany(8192):
                for row in rows:
                    digest.update(
                        json.dumps(
                            row, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")
                    )
                    digest.update(b"\n")
        return digest.hexdigest()

    def _manifest(self, release_id: str, election_slug: str) -> dict[str, Any]:
        manifest = self._releases.get(release_id)
        if manifest is None or election_slug not in self._slugs(manifest):
            raise ResourceNotFoundError("The requested historical release/election was not found.")
        return manifest

    @staticmethod
    def _slugs(manifest: Mapping[str, Any]) -> set[str]:
        return set(str(manifest["datasets"][0]["filters"]["election_slugs"]).split(","))

    def _paths(self, release_id: str) -> tuple[Path, Path]:
        values = self._files[release_id]
        geography = next(path for key, path in values.items() if "geography" in key)
        rollups = next(path for key, path in values.items() if "rollups" in key)
        return geography, rollups

    def build_geography_read_model(self, destination: Path) -> None:
        """Build compact geography/category indexes without changing release bytes."""
        destination = destination.resolve()
        if destination.parent != self._data_path or destination.exists():
            raise HistoricalReleaseError(
                "derived geography index destination must be a new file in the data directory"
            )
        connection = duckdb.connect(str(destination))
        try:
            connection.execute("SET threads=1")
            connection.execute(
                """CREATE TABLE geography (
                     round INTEGER NOT NULL,
                     election_slug VARCHAR NOT NULL,
                     election_date DATE NOT NULL,
                     level VARCHAR NOT NULL,
                     id VARCHAR NOT NULL,
                     code VARCHAR NOT NULL,
                     name VARCHAR NOT NULL,
                     parent_id VARCHAR
                   )"""
            )
            connection.execute(
                """CREATE TABLE read_model_metadata (
                     release_id VARCHAR PRIMARY KEY,
                     geography_dataset_id VARCHAR NOT NULL,
                     manifest_hash VARCHAR NOT NULL,
                     geography_content_hash VARCHAR NOT NULL,
                     geography_byte_size BIGINT NOT NULL,
                     geography_row_count BIGINT NOT NULL,
                     geography_served_digest VARCHAR NOT NULL,
                     category_dataset_id VARCHAR NOT NULL,
                     category_content_hash VARCHAR NOT NULL,
                     category_byte_size BIGINT NOT NULL,
                     category_row_count BIGINT NOT NULL,
                     category_served_digest VARCHAR NOT NULL
                   )"""
            )
            connection.execute(
                """CREATE TABLE category_groups AS
                   WITH grouped AS (
                     SELECT election_slug,geography_id,
                            list(struct_pack(
                              category_key := party_code||':'||category_code,
                              category_code := category_code,
                              category_name := category_name,
                              votes := votes
                            ) ORDER BY party_code||':'||category_code) AS categories
                     FROM read_parquet(?) WHERE false
                     GROUP BY election_slug,geography_id
                   )
                   SELECT election_slug,geography_id,categories,
                          sha256(to_json(categories)) AS category_digest,
                          len(categories) AS category_count
                   FROM grouped""",
                [str(self._paths(next(iter(self._releases)))[1])],
            )
            connection.execute(
                """CREATE TABLE election_stats (
                     election_slug VARCHAR PRIMARY KEY,
                     release_id VARCHAR NOT NULL,
                     round INTEGER NOT NULL,
                     election_date DATE NOT NULL,
                     geography_count BIGINT NOT NULL,
                     category_count BIGINT NOT NULL,
                     national_geography_id VARCHAR NOT NULL
                   )"""
            )
            for release_id, manifest in self._releases.items():
                geography, rollups = self._paths(release_id)
                geography_dataset = next(
                    item for item in manifest["datasets"] if "geography" in item["id"]
                )
                category_dataset = next(
                    item for item in manifest["datasets"] if "rollups" in item["id"]
                )
                connection.execute(
                    """INSERT INTO geography
                       SELECT round,election_slug,election_date,level,id,code,name,parent_id
                       FROM read_parquet(?)""",
                    [str(geography)],
                )
                connection.execute(
                    """INSERT INTO category_groups
                       WITH grouped AS (
                         SELECT election_slug,geography_id,
                                list(struct_pack(
                                  category_key := party_code||':'||category_code,
                                  category_code := category_code,
                                  category_name := category_name,
                                  votes := votes
                                ) ORDER BY party_code||':'||category_code) AS categories
                         FROM read_parquet(?) GROUP BY election_slug,geography_id
                       )
                       SELECT election_slug,geography_id,categories,
                              sha256(to_json(categories)),len(categories)
                       FROM grouped""",
                    [str(rollups)],
                )
                category_digest = self._category_digest(
                    connection,
                    "read_parquet(?)",
                    [str(rollups)],
                    self._slugs(manifest),
                    grouped=False,
                )
                pinned_category_digest = _SOURCE_CATEGORY_DIGESTS[release_id]
                if (
                    category_digest != pinned_category_digest
                    or pinned_category_digest
                    != self._category_digest(
                        connection,
                        "category_groups",
                        [],
                        self._slugs(manifest),
                        grouped=True,
                    )
                ):
                    raise HistoricalReleaseError(
                        f"{release_id} derived category content digest failed"
                    )
                slugs = sorted(self._slugs(manifest))
                placeholders = ",".join("?" for _ in slugs)
                duplicate_groups = connection.execute(
                    f"""SELECT count(*) FROM category_groups
                         WHERE election_slug IN ({placeholders})
                           AND category_count != len(list_distinct(list_transform(
                             categories,item -> item.category_key
                           )))""",
                    slugs,
                ).fetchone()
                if duplicate_groups != (0,):
                    raise HistoricalReleaseError(
                        f"{release_id} category identity uniqueness failed"
                    )
                connection.execute(
                    f"""INSERT INTO election_stats
                         SELECT g.election_slug,?,min(g.round),min(g.election_date),
                                count(*),sum(c.category_count),
                                max(CASE WHEN g.level='national' THEN g.id END)
                         FROM geography g
                         JOIN category_groups c
                           ON c.election_slug=g.election_slug
                          AND c.geography_id=g.id
                         WHERE g.election_slug IN ({placeholders})
                         GROUP BY g.election_slug""",
                    [release_id, *slugs],
                )
                connection.execute(
                    "INSERT INTO read_model_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        release_id,
                        geography_dataset["id"],
                        _sha256(
                            self._data_path / "manifests" / f"{release_id}.json"
                        ),
                        geography_dataset["content_hash"],
                        geography_dataset["byte_size"],
                        geography_dataset["record_count"],
                        self._source_geography_digests[release_id],
                        category_dataset["id"],
                        category_dataset["content_hash"],
                        category_dataset["byte_size"],
                        category_dataset["record_count"],
                        pinned_category_digest,
                    ],
                )
            connection.execute(
                "CREATE UNIQUE INDEX geography_identity ON geography(election_slug,id)"
            )
            connection.execute(
                """CREATE INDEX geography_children
                   ON geography(election_slug,parent_id,level,code,id)"""
            )
            connection.execute(
                """CREATE UNIQUE INDEX category_group_identity
                   ON category_groups(election_slug,geography_id)"""
            )
            connection.execute("CHECKPOINT")
        finally:
            connection.close()
        self._read_model_path = destination
        self._validate_read_model()
        self._open_runtime_connection()

    def _validate_read_model(self) -> None:
        path = self._read_model_path
        if path is None or path.resolve().parent != self._data_path:
            raise HistoricalReleaseError("derived geography index path is invalid")
        expected_metadata: dict[str, tuple[object, ...]] = {}
        for release_id, manifest in self._releases.items():
            geography_dataset = next(
                item for item in manifest["datasets"] if "geography" in item["id"]
            )
            category_dataset = next(
                item for item in manifest["datasets"] if "rollups" in item["id"]
            )
            expected_metadata[release_id] = (
                geography_dataset["id"],
                _sha256(self._data_path / "manifests" / f"{release_id}.json"),
                geography_dataset["content_hash"],
                geography_dataset["byte_size"],
                geography_dataset["record_count"],
                self._source_geography_digests[release_id],
                category_dataset["id"],
                category_dataset["content_hash"],
                category_dataset["byte_size"],
                category_dataset["record_count"],
                _SOURCE_CATEGORY_DIGESTS[release_id],
            )
        try:
            with self._connect() as connection:
                metadata_rows = connection.execute(
                    """SELECT release_id,geography_dataset_id,manifest_hash,
                              geography_content_hash,geography_byte_size,
                              geography_row_count,geography_served_digest,
                              category_dataset_id,category_content_hash,
                              category_byte_size,category_row_count,
                              category_served_digest
                       FROM read_model_metadata ORDER BY release_id"""
                ).fetchall()
                actual_metadata = {row[0]: tuple(row[1:]) for row in metadata_rows}
                if actual_metadata != expected_metadata:
                    raise HistoricalReleaseError(
                        "derived read index metadata does not match pinned artifacts"
                    )
                expected_total = 0
                expected_category_total = 0
                expected_slugs: set[str] = set()
                for release_id, manifest in self._releases.items():
                    geography_dataset = next(
                        item
                        for item in manifest["datasets"]
                        if "geography" in item["id"]
                    )
                    category_dataset = next(
                        item
                        for item in manifest["datasets"]
                        if "rollups" in item["id"]
                    )
                    slugs = self._slugs(manifest)
                    expected_slugs.update(slugs)
                    expected_total += geography_dataset["record_count"]
                    expected_category_total += category_dataset["record_count"]
                    placeholders = ",".join("?" for _ in slugs)
                    counts = connection.execute(
                        f"""SELECT count(*),count(DISTINCT election_slug || chr(0) || id)
                            FROM geography WHERE election_slug IN ({placeholders})""",
                        sorted(slugs),
                    ).fetchone()
                    if counts != (
                        geography_dataset["record_count"],
                        geography_dataset["record_count"],
                    ):
                        raise HistoricalReleaseError(
                            f"{release_id} derived geography row/identity check failed"
                        )
                    digest = self._geography_digest(
                        connection, "geography", [], slugs
                    )
                    if digest != self._source_geography_digests[release_id]:
                        raise HistoricalReleaseError(
                            f"{release_id} derived geography content digest failed"
                        )
                    category_counts = connection.execute(
                        f"""SELECT count(*),sum(len(categories)),
                                   count(DISTINCT election_slug || chr(0) || geography_id)
                            FROM category_groups
                            WHERE election_slug IN ({placeholders})""",
                        sorted(slugs),
                    ).fetchone()
                    if category_counts != (
                        geography_dataset["record_count"],
                        category_dataset["record_count"],
                        geography_dataset["record_count"],
                    ):
                        raise HistoricalReleaseError(
                            f"{release_id} derived category row/identity check failed"
                        )
                    invalid_category_groups = connection.execute(
                        f"""SELECT count(*) FROM category_groups
                             WHERE election_slug IN ({placeholders}) AND (
                               category_count != len(categories)
                               OR category_digest != sha256(to_json(categories))
                               OR category_count != len(list_distinct(list_transform(
                                 categories,item -> item.category_key
                               )))
                             )""",
                        sorted(slugs),
                    ).fetchone()
                    if invalid_category_groups != (0,):
                        raise HistoricalReleaseError(
                            f"{release_id} derived category group validation failed"
                        )
                    expected_category_digest = _SOURCE_CATEGORY_DIGESTS[release_id]
                    if self._category_digest(
                        connection,
                        "category_groups",
                        [],
                        slugs,
                        grouped=True,
                    ) != expected_category_digest:
                        raise HistoricalReleaseError(
                            f"{release_id} derived category content digest failed"
                        )
                    stats = connection.execute(
                        f"""SELECT s.election_slug,s.release_id,s.round,
                                   CAST(s.election_date AS VARCHAR),
                                   s.geography_count,s.category_count,
                                   s.national_geography_id,
                                   min(g.round),CAST(min(g.election_date) AS VARCHAR),
                                   count(*),sum(c.category_count),
                                   max(CASE WHEN g.level='national' THEN g.id END),
                                   count(*) FILTER (WHERE g.level='national')
                            FROM election_stats s
                            JOIN geography g ON g.election_slug=s.election_slug
                            JOIN category_groups c
                              ON c.election_slug=g.election_slug
                             AND c.geography_id=g.id
                            WHERE s.election_slug IN ({placeholders})
                            GROUP BY s.election_slug,s.release_id,s.round,s.election_date,
                                     s.geography_count,s.category_count,
                                     s.national_geography_id
                            ORDER BY s.election_slug""",
                        sorted(slugs),
                    ).fetchall()
                    if len(stats) != len(slugs) or any(
                        row[1] != release_id
                        or row[2] != row[7]
                        or row[3] != row[8]
                        or row[4] != row[9]
                        or row[5] != row[10]
                        or row[6] != row[11]
                        or row[12] != 1
                        for row in stats
                    ):
                        raise HistoricalReleaseError(
                            f"{release_id} derived election statistics validation failed"
                        )
                total = connection.execute(
                    "SELECT count(*),count(DISTINCT election_slug) FROM geography"
                ).fetchone()
                if total != (expected_total, len(expected_slugs)):
                    raise HistoricalReleaseError(
                        "derived geography index contains unexpected release rows"
                    )
                category_total = connection.execute(
                    "SELECT count(*),sum(len(categories)) FROM category_groups"
                ).fetchone()
                if category_total != (expected_total, expected_category_total):
                    raise HistoricalReleaseError(
                        "derived category index contains unexpected release rows"
                    )
                stats_slugs = {
                    row[0]
                    for row in connection.execute(
                        "SELECT election_slug FROM election_stats"
                    ).fetchall()
                }
                if stats_slugs != expected_slugs:
                    raise HistoricalReleaseError(
                        "derived election statistics contain unexpected release rows"
                    )
        except HistoricalReleaseError:
            raise
        except Exception as exc:
            raise HistoricalReleaseError(
                "derived geography index could not be opened read-only"
            ) from exc

    def public_elections(self) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for release_id, manifest in self._releases.items():
            relation, relation_params = self._geography_relation(release_id)
            with self._connect() as connection:
                rows = connection.execute(
                    f"""SELECT DISTINCT election_slug,round,election_date
                        FROM {relation} ORDER BY election_date""",
                    relation_params,
                ).fetchall()
            sources = {source["id"].rsplit("-", 1)[-1]: source for source in manifest["sources"]}
            for slug, round_number, election_date in rows:
                source = sources[str(round_number)]
                output.append(
                    {
                        "release_id": release_id,
                        "election_slug": slug,
                        "name_es": f"Elección presidencial {str(election_date)[:4]}",
                        "name_en": f"{str(election_date)[:4]} presidential election",
                        "round": round_number,
                        "election_date": election_date,
                        "status": manifest["status"],
                        "release_class": "context_only",
                        "methodology_version": manifest["methodology_version"],
                        "release_manifest_hash": _sha256(
                            self._data_path / "manifests" / f"{release_id}.json"
                        ),
                        "exposure_approved_at": None,
                        "sources": [source],
                    }
                )
        return output

    def _source(self, manifest: Mapping[str, Any], slug: str) -> Mapping[str, Any]:
        round_number = int(slug.rsplit("-", 1)[-1])
        return next(
            source for source in manifest["sources"] if source["id"].endswith(f"-{round_number}")
        )

    def normalized_results(
        self,
        release_id: str,
        election_slug: str,
        filters: dict[str, object],
        after: tuple[str, ...] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        manifest = self._manifest(release_id, election_slug)
        _, rollups = self._paths(release_id)
        geography_relation, geography_params = self._geography_relation(release_id)
        clauses = ["g.election_slug=?"]
        params: list[object] = [election_slug]
        for key, column in (("geography_id", "g.id"), ("geography_level", "g.level")):
            if filters.get(key) is not None:
                clauses.append(f"{column}=?")
                params.append(filters[key])
        if filters.get("source_type") not in (None, "contextual_baseline"):
            return []
        if filters.get("source_id") not in (None, self._source(manifest, election_slug)["id"]):
            return []
        if filters.get("category_key") is not None:
            category_key = str(filters["category_key"])
            if ":" not in category_key:
                return []
            if self._read_model_path is not None:
                clauses.append(
                    """EXISTS (
                         SELECT 1 FROM category_groups cg
                         WHERE cg.election_slug=g.election_slug
                           AND cg.geography_id=g.id
                           AND list_contains(list_transform(
                             cg.categories,item -> item.category_key
                           ),?)
                       )"""
                )
                params.append(category_key)
            else:
                party, code = category_key.split(":", 1)
                clauses.append(
                    "EXISTS (SELECT 1 FROM read_parquet(?) r WHERE r.election_slug=g.election_slug AND r.geography_id=g.id AND r.party_code=? AND r.category_code=?)"
                )
                params.extend([str(rollups), party, code])
        if filters.get("status") not in (None, "observed"):
            return []
        if filters.get("geography_path") is not None:
            leaf = str(filters["geography_path"]).rsplit("/", 1)[-1]
            if (
                self._path(release_id, election_slug, leaf) != str(filters["geography_path"])
                and leaf != filters["geography_path"]
            ):
                return []
            first_relation, first_params = self._geography_relation(release_id)
            child_relation, child_params = self._geography_relation(release_id)
            clauses.append(
                "g.id IN (WITH RECURSIVE descendants(id) AS ("
                f"SELECT id FROM {first_relation} WHERE election_slug=? AND id=? "
                f"UNION ALL SELECT child.id FROM {child_relation} child "
                "JOIN descendants d ON child.parent_id=d.id WHERE child.election_slug=?"
                ") SELECT id FROM descendants)"
            )
            params.extend(
                [
                    *first_params,
                    election_slug,
                    leaf,
                    *child_params,
                    election_slug,
                ]
            )
        rank = "CASE g.level WHEN 'national' THEN 0 WHEN 'department' THEN 1 WHEN 'municipality' THEN 2 WHEN 'zone' THEN 3 WHEN 'polling_place' THEN 4 ELSE 5 END"
        if after:
            clauses.append(f"({rank},g.id)>(?,?)")
            params.extend([_LEVELS.index(after[0]), after[1]])
        sql = f"SELECT g.id,g.level,g.code,g.name,g.parent_id FROM {geography_relation} g WHERE {' AND '.join(clauses)} ORDER BY {rank},g.id LIMIT ?"
        params = [*geography_params, *params, limit + 1]
        source = self._source(manifest, election_slug)
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._normalized_result_fact(row[0], row[1], source) for row in rows]

    @staticmethod
    def _normalized_result_fact(
        geography_id: str, geography_level: str, source: Mapping[str, Any]
    ) -> dict[str, object]:
        unavailable = {
            metric: {"value": None, "status": "unavailable"}
            for metric in (
                "registered_electors",
                "voters",
                "valid_votes",
                "blank_votes",
                "null_votes",
                "unmarked_votes",
            )
        }
        return {
            "id": f"{geography_id}:{source['id']}",
            "geography_id": geography_id,
            "geography_level": geography_level,
            "mesa_id": geography_id if geography_level == "mesa" else None,
            "source_id": source["id"],
            "metrics": unavailable,
            **{
                key: source[key]
                for key in (
                    "source_type",
                    "legal_status",
                    "source_url",
                    "retrieved_at",
                    "content_hash",
                    "parser_version",
                    "transform_version",
                )
            },
        }

    def iter_normalized_results(
        self, release_id: str, election_slug: str, filters: Mapping[str, object]
    ) -> Iterator[dict[str, object]]:
        yield from self.normalized_results(
            release_id, election_slug, dict(filters), None, 10_000_000
        )

    @staticmethod
    def _canonical_path_ids(geography_id: str) -> list[str]:
        """Enumerate candidate ancestors from the verified canonical ID grammar."""
        parts = geography_id.split(":")
        if len(parts) == 2 and parts[1] == "co":
            return [geography_id]
        component_count = {
            "dep": 1,
            "mun": 2,
            "zone": 3,
            "place": 4,
            "mesa": 5,
        }.get(parts[1] if len(parts) > 1 else "")
        if (
            component_count is None
            or len(parts) != component_count + 2
            or not parts[0].startswith("r")
            or not parts[0][1:].isdigit()
            or any(not component for component in parts[2:])
        ):
            return [geography_id]
        prefix = parts[0]
        components = parts[2:]
        identifiers = [f"{prefix}:co"]
        for index, token in enumerate(("dep", "mun", "zone", "place", "mesa"), 1):
            if index > component_count:
                break
            identifiers.append(
                f"{prefix}:{token}:{':'.join(components[:index])}"
            )
        return identifiers

    def _path_rows(
        self, release_id: str, election_slug: str, geography_id: str
    ) -> list[dict[str, object]]:
        relation, relation_params = self._geography_relation(release_id)
        current = geography_id.rsplit("/", 1)[-1]
        path_ids = self._canonical_path_ids(current)
        placeholders = ",".join("?" for _ in path_ids)
        with self._connect() as connection:
            found_rows = connection.execute(
                f"""SELECT id,level,code,name,parent_id FROM {relation}
                     WHERE election_slug=? AND id IN ({placeholders})""",
                [*relation_params, election_slug, *path_ids],
            ).fetchall()
        by_id = {row[0]: row for row in found_rows}
        if current not in by_id:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        if len(by_id) != len(path_ids):
            raise HistoricalReleaseError("derived geography path is incomplete or cyclic")
        found_rows = [by_id[identifier] for identifier in path_ids]
        rows = [
            dict(
                zip(
                    ("id", "level", "code", "name", "parent_id"),
                    found,
                    strict=True,
                )
            )
            for found in found_rows
        ]
        leaf_level = rows[-1]["level"]
        if not isinstance(leaf_level, str) or leaf_level not in _LEVELS:
            raise HistoricalReleaseError("derived geography path has an invalid level")
        expected_levels = list(_LEVELS[: _LEVELS.index(leaf_level) + 1])
        if [row["level"] for row in rows] != expected_levels or any(
            row["parent_id"] != (None if index == 0 else rows[index - 1]["id"])
            for index, row in enumerate(rows)
        ):
            raise HistoricalReleaseError("derived geography path is incomplete or cyclic")
        canonical = "/".join(str(row["id"]) for row in rows)
        if "/" in geography_id and geography_id != canonical:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        for index, path_row in enumerate(rows):
            path_row["canonical_path"] = "/".join(str(item["id"]) for item in rows[: index + 1])
        return rows

    def _path(self, release_id: str, election_slug: str, geography_id: str) -> str:
        return str(self._path_rows(release_id, election_slug, geography_id)[-1]["canonical_path"])

    def normalized_geography_path(
        self, release_id: str, election_slug: str, geography_id: str
    ) -> list[dict[str, object]]:
        self._manifest(release_id, election_slug)
        return self._path_rows(release_id, election_slug, geography_id)

    def normalized_geography(
        self, release_id: str, election_slug: str, geography_id: str
    ) -> dict[str, object]:
        row = dict(self._path_rows(release_id, election_slug, geography_id)[-1])
        row["authoritative_coordinates"] = None
        return row

    def normalized_geography_children(
        self,
        release_id: str,
        election_slug: str,
        geography_id: str,
        child_level: str | None,
        after: tuple[str, ...] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        relation, relation_params = self._geography_relation(release_id)
        parent_path = self._path(release_id, election_slug, geography_id)
        clauses = ["election_slug=?", "parent_id=?"]
        params: list[object] = [election_slug, geography_id]
        if child_level:
            clauses.append("level=?")
            params.append(child_level)
        if after:
            clauses.append("(level,code,id)>(?,?,?)")
            params.extend(after)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id,level,code,name,parent_id FROM {relation} WHERE {' AND '.join(clauses)} ORDER BY level,code,id LIMIT ?",
                [*relation_params, *params, limit + 1],
            ).fetchall()
        return [
            {
                "id": row[0],
                "level": row[1],
                "code": row[2],
                "name": row[3],
                "parent_id": row[4],
                "canonical_path": f"{parent_path}/{row[0]}",
                "has_published_facts": True,
            }
            for row in rows
        ]

    def normalized_mesa(
        self,
        release_id: str,
        election_slug: str,
        mesa_id: str,
        source_id: str | None,
        source_type: str | None,
    ) -> dict[str, object]:
        manifest = self._manifest(release_id, election_slug)
        path = self._path_rows(release_id, election_slug, mesa_id)
        if path[-1]["level"] != "mesa":
            raise ResourceNotFoundError(f"Mesa '{mesa_id}' was not found.")
        by_level = {row["level"]: row for row in path}
        source = self._source(manifest, election_slug)
        facts = (
            [self._normalized_result_fact(mesa_id, "mesa", source)]
            if source_id in (None, source["id"])
            and source_type in (None, "contextual_baseline")
            else []
        )
        return {
            "id": mesa_id,
            "display_number": path[-1]["code"],
            "polling_place_id": by_level["polling_place"]["id"],
            "municipality_id": by_level["municipality"]["id"],
            "department_id": by_level["department"]["id"],
            "geography_path": path,
            "results": facts,
        }

    def normalized_categories(
        self, release_id: str, election_slug: str, fact_id: str, after: str | None, limit: int
    ) -> list[dict[str, object]]:
        manifest = self._manifest(release_id, election_slug)
        source = self._source(manifest, election_slug)
        suffix = f":{source['id']}"
        if not fact_id.endswith(suffix):
            raise ResourceNotFoundError(f"Result fact '{fact_id}' was not found.")
        geography_id = fact_id[: -len(suffix)]
        if self._read_model_path is not None:
            with self._connect() as connection:
                grouped = connection.execute(
                    """SELECT categories FROM category_groups
                       WHERE election_slug=? AND geography_id=?""",
                    [election_slug, geography_id],
                ).fetchone()
            if grouped is None:
                raise ResourceNotFoundError(f"Result fact '{fact_id}' was not found.")
            rows = [
                (
                    item["category_key"],
                    item["category_code"],
                    item["category_name"],
                    "published_mmv_category",
                    item["votes"],
                )
                for item in grouped[0]
                if after is None or item["category_key"] > after
            ][: limit + 1]
        else:
            self._path_rows(release_id, election_slug, geography_id)
            _, rollups = self._paths(release_id)
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT party_code||':'||category_code,category_code,category_name,'published_mmv_category',votes FROM read_parquet(?) WHERE election_slug=? AND geography_id=? AND (? IS NULL OR party_code||':'||category_code>?) ORDER BY 1 LIMIT ?",
                    [str(rollups), election_slug, geography_id, after, after, limit + 1],
                ).fetchall()
        return [
            {
                "category_key": row[0],
                "category_code": row[1],
                "category_name": row[2],
                "category_kind": row[3],
                "votes": row[4],
                "status": "observed",
                **{
                    key: source[key]
                    for key in (
                        "source_type",
                        "legal_status",
                        "source_url",
                        "retrieved_at",
                        "content_hash",
                        "parser_version",
                        "transform_version",
                    )
                },
            }
            for row in rows
        ]

    def normalized_summary(self, release_id: str, election_slug: str) -> dict[str, object]:
        manifest = self._manifest(release_id, election_slug)
        source = self._source(manifest, election_slug)
        if self._read_model_path is not None:
            with self._connect() as connection:
                statistics = connection.execute(
                    """SELECT round,election_date,geography_count,category_count,
                              national_geography_id
                       FROM election_stats WHERE election_slug=? AND release_id=?""",
                    [election_slug, release_id],
                ).fetchone()
            if statistics is None:
                raise HistoricalReleaseError(
                    "derived election statistics do not contain the requested election"
                )
            round_number, election_date, geography_count, category_count, national_id = (
                statistics
            )
        else:
            geography, rollups = self._paths(release_id)
            with self._connect() as connection:
                statistics = connection.execute(
                    """SELECT min(round),min(election_date),count(*),
                              (SELECT count(*) FROM read_parquet(?) r
                               WHERE r.election_slug=?),
                              max(CASE WHEN level='national' THEN id END)
                       FROM read_parquet(?) g WHERE g.election_slug=?""",
                    [str(rollups), election_slug, str(geography), election_slug],
                ).fetchone()
            assert statistics is not None
            round_number, election_date, geography_count, category_count, national_id = (
                statistics
            )
        source = self._source(manifest, election_slug)
        national_fact_id = f"{national_id}:{source['id']}"
        national_categories = self.normalized_categories(
            release_id, election_slug, national_fact_id, None, 500
        )
        unavailable = {
            metric: {"value": None, "status": "unavailable"}
            for metric in (
                "registered_electors",
                "voters",
                "valid_votes",
                "blank_votes",
                "null_votes",
                "unmarked_votes",
            )
        }
        return {
            "election_slug": election_slug,
            "election_name": {
                "es": f"Elección presidencial {str(election_date)[:4]}",
                "en": f"{str(election_date)[:4]} presidential election",
            },
            "round": round_number,
            "election_date": election_date,
            "data_version": release_id,
            "release_status": manifest["status"],
            "release_class": "context_only",
            "synthetic": False,
            "completion": {
                "status": "unknown",
                "reason": "No expected reporting denominator is declared.",
            },
            **unavailable,
            "national_categories": national_categories,
            "coverage": {
                "status": "unknown",
                "observed_geographies": geography_count,
                "observed_result_facts": geography_count,
                "observed_category_facts": category_count,
                "reason": "Observed rows are not an expected coverage denominator.",
            },
            "reconciliation": {"status": "not_run", "checked_facts": 0, "exceptions": 0},
            "provenance": {
                "data_version": release_id,
                **{
                    key: source[key]
                    for key in (
                        "source_type",
                        "legal_status",
                        "source_url",
                        "retrieved_at",
                        "content_hash",
                        "parser_version",
                        "transform_version",
                    )
                },
                "methodology_version": None,
                "preview_caveat": "Candidate context-only preview from an uncommitted worktree; not an immutable published release.",
            },
        }

    def datasets(self, slug: str, version: str | None) -> list[dict[str, object]]:
        release_id = version or self._active_release_id
        manifest = self._manifest(release_id, slug)
        return [
            {
                **item,
                "url": f"/api/v1/releases/{release_id}/elections/{slug}/datasets/{item['id']}/download",
                "schema_url": None,
            }
            for item in manifest["datasets"]
        ]

    def dataset_file(
        self, release_id: str, election_slug: str, dataset_id: str
    ) -> tuple[Path, Mapping[str, Any]]:
        manifest = self._manifest(release_id, election_slug)
        dataset = next((item for item in manifest["datasets"] if item["id"] == dataset_id), None)
        path = self._files[release_id].get(dataset_id)
        if dataset is None or path is None:
            raise ResourceNotFoundError(f"Dataset '{dataset_id}' was not found.")
        return path, dataset

    def normalized_comparison(self, *args: Any, **kwargs: Any) -> dict[str, object]:
        return {
            "comparison_status": "descriptive_context_only",
            "reason": "no_approved_longitudinal_crosswalk",
            "eligible_for_integrity_analysis": False,
            "items": [],
        }

    def __getattr__(self, name: str) -> Any:
        if name.startswith(
            (
                "analysis",
                "anomal",
                "review",
                "outcome",
                "normalized_outcome",
                "evidence",
                "comparison",
                "bulletin",
                "signal",
            )
        ):

            def unavailable(*args: Any, **kwargs: Any) -> Any:
                raise ResourceNotFoundError(
                    "Analytical and review outputs are unavailable for context-only releases."
                )

            return unavailable
        raise AttributeError(name)
