# Every interpolated SQL fragment below is built from module constants -- metric
# names, level names, table names -- and never from release data.  All values
# travel as bound parameters.
# ruff: noqa: S608
"""Stage B: load a standard 2026 release into PostgreSQL, internally only.

One transaction, all-or-nothing, a manifest-hash idempotency check, and an
exposure that can only be ``internal``.  Promotion to ``preliminary`` or
``public`` is a separate reviewed step and is rejected here.

Why there are no staging copies of the release
----------------------------------------------
This loader used to COPY every artifact into ``ON COMMIT DROP`` temp tables,
validate there, and only then INSERT into the live tables.  Inside one
transaction nothing is ever reclaimed -- ``ON COMMIT DROP`` unlinks the temp
files at commit, not when the loader is done with them -- so staging and live
coexisted for the whole load and the peak was roughly the release twice over,
plus the sort/hash spill of a 366,060-row rollup-membership join.  On a capped
volume that peak is what fails, with ``DiskFull`` on ``base/pgsql_tmp``, while
the same load succeeds anywhere the disk is merely large.

The staging tier bought nothing that survives inspection.  Every per-row rule
is checked in Python before the row is written, and every set-wise rule is a
query that reads exactly as well against the live tables, which are scoped by
``release_id`` and therefore hold this release's rows and nobody else's.  The
one rule staging carried on its own -- "no duplicate scoped primary keys" -- is
a real primary key on each live table, so it is now enforced by the database
rather than asserted after the fact; the driver error is translated back into
``ReleaseLoadError`` so callers still read the sentence, not a traceback.

Nothing about the all-or-nothing guarantee changes.  It is still one
transaction, every assertion still aborts it, and the exposure row -- the gate
every read path joins through -- is still the last write, so a load that fails
anywhere leaves nothing readable.

What is specific to this release
--------------------------------
*Mesa geographies are derived, not shipped.*  The snapshot has 18,675
geographies and no mesa level, so the 122,020 mesa geographies are materialised
in SQL from ``release_mesas``, whose ``polling_place_id`` came straight from
``mesas[].polling_place_id`` -- never from slicing a mesa id.  The
``mesa.id = place.code || mesa.display_number`` identity is asserted set-wise
on all 122,020 and the transaction aborts on any violation.

*Aggregates are derived, not published.*  The Registraduria publishes nothing
between polling place and nation: there are zero department, municipality and
zone facts.  The 4,236 aggregate facts are summed from the mesa facts inside the
transaction and attributed to a fourth, structurally separate source
(``derived-mesa-rollup-2026-r2``, transform ``mesa-rollup@1.0.0``).  A
department total is a number this project computed; it must never be readable as
a document the Registraduria published.

The three aggregate levels are summed in one ``GROUPING SETS`` pass over the
mesa facts instead of through a materialised (level, geography, mesa) membership
table.  Same three sums, same three groupings, one scan, no 366,060-row
intermediate and no hash spill.

*Turnout below the nation is impossible.*  ``registered_electors`` is
``unavailable`` on 122,008 of 122,020 mesas, so every derived aggregate records
it as unavailable.  Summing the handful of observed values would fabricate a
denominator that does not exist.

*Reconciliation is asserted, and separately reported.*  In-transaction, the sum
of the mesas in each of the 14,438 polling places must equal that place's own
published fact, and the sum of the 34 departments must equal the national fact,
for all five vote metrics and both candidates.  Independently of that, the
pipeline's own ``reconciliation`` verdict is ``blocked`` with three exceptions
and is stored verbatim in ``release_summaries``: a passing load assertion does
not turn a blocked release into a reconciled one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from ._bulk import (
    _LEVEL_RANK,
    _PAIR,
    ReleaseLoadError,
    _batches,
    _copy_rows,
    _digest,
    _require_int,
    _require_string,
    _timestamp,
)
from .snapshot_parquet import (
    CATEGORY_ARTIFACT,
    ELECTION_SLUG,
    FACT_ARTIFACT,
    GEOGRAPHY_ARTIFACT,
    LOAD_MANIFEST,
    MESA_ARTIFACT,
    METRICS,
    ROLLUP_TRANSFORM,
    SOURCE_MESA,
    SOURCE_NATIONAL,
    SOURCE_PLACE,
    SOURCE_ROLLUP,
)

RELEASE_CLASS = "standard"
# Levels the Registraduria never published a fact for; every one is derived.
_DERIVED_LEVELS = ("zone", "municipality", "department")
_DERIVED_LEVEL_COLUMN = {
    "zone": "zone_id",
    "municipality": "municipality_id",
    "department": "department_id",
}
_VOTE_METRICS = ("voters", "valid_votes", "blank_votes", "null_votes", "unmarked_votes")
_EXPECTED_SOURCES = (SOURCE_NATIONAL, SOURCE_PLACE, SOURCE_MESA, SOURCE_ROLLUP)
_GEOGRAPHY_COLUMNS = {"id", "level", "code", "name", "parent_id", "canonical_path"}
_MESA_COLUMNS = {"id", "display_number", "polling_place_id", "municipality_id", "department_id"}
_FACT_COLUMNS = {
    "id",
    "geography_id",
    "source_geography_id",
    "geography_level",
    "mesa_id",
    "source_id",
    "content_hash",
    "retrieved_at",
    *[f"{metric}_{suffix}" for metric in METRICS for suffix in ("value", "status")],
}
_CATEGORY_COLUMNS = {
    "result_fact_id",
    "category_key",
    "category_code",
    "category_name",
    "category_kind",
    "votes",
    "status",
}
_GEOGRAPHY_TARGET = (
    "release_geographies (release_id,election_slug,id,level,code,name,parent_id,canonical_path)"
)
_MESA_TARGET = (
    "release_mesas "
    "(release_id,election_slug,id,display_number,polling_place_id,municipality_id,department_id)"
)
_FACT_TARGET = (
    "release_result_facts (release_id,election_slug,id,geography_id,geography_level,mesa_id,"
    "source_id,metrics,fact_content_hash,fact_retrieved_at)"
)
_CATEGORY_TARGET = (
    "release_category_facts (release_id,election_slug,result_fact_id,category_key,category_code,"
    "category_name,category_kind,votes,status)"
)
# `metrics` is a json column, so the derived facts are built with
# json_build_object rather than jsonb_build_object: json preserves the key order
# it is given, which keeps every row in a release -- streamed or derived --
# serialised the same way.
_DERIVED_METRICS_JSON = (
    "json_build_object("
    + ",".join(
        f"'{metric}',json_build_object('value',NULL::bigint,'status','unavailable')"
        if metric not in _VOTE_METRICS
        else f"'{metric}',json_build_object('value',r.{metric},'status','observed')"
        for metric in METRICS
    )
    + ")"
)


def _metric_value(alias: str, metric: str) -> str:
    return f"({alias}.metrics->'{metric}'->>'value')::bigint"


def _metric_status(alias: str, metric: str) -> str:
    return f"{alias}.metrics->'{metric}'->>'status'"


def _grouping_case(expression: dict[str, str]) -> str:
    """Pick the value belonging to whichever GROUPING SET produced the row."""
    return (
        "CASE"
        + "".join(
            f" WHEN GROUPING(l.{_DERIVED_LEVEL_COLUMN[level]})=0 THEN {expression[level]}"
            for level in _DERIVED_LEVELS[:-1]
        )
        + f" ELSE {expression[_DERIVED_LEVELS[-1]]} END"
    )


_ROLLUP_LEVEL = _grouping_case({level: f"'{level}'" for level in _DERIVED_LEVELS})
_ROLLUP_GEOGRAPHY = _grouping_case(
    {level: f"l.{_DERIVED_LEVEL_COLUMN[level]}" for level in _DERIVED_LEVELS}
)
_ROLLUP_GROUPING_SETS = (
    "GROUPING SETS ("
    + ",".join(f"(l.{_DERIVED_LEVEL_COLUMN[level]})" for level in _DERIVED_LEVELS)
    + ")"
)


def _advisory_key(release_id: str) -> int:
    """A stable signed bigint lock key for a release id.

    Derived in Python rather than with ``hashtext`` so the key does not depend
    on an undocumented server function whose hash could change between major
    PostgreSQL versions and silently stop serialising two loaders.
    """
    return int.from_bytes(hashlib.sha256(release_id.encode()).digest()[:8], "big", signed=True)


def _artifact_path(directory: Path, load_manifest: dict[str, Any], filename: str) -> Path:
    """Resolve one Stage A artifact and verify its recorded hash and size."""
    entries = [
        entry
        for entry in load_manifest.get("artifacts", [])
        if isinstance(entry, dict) and entry.get("filename") == filename
    ]
    if len(entries) != 1:
        raise ReleaseLoadError(f"load manifest must describe exactly one {filename}")
    entry = entries[0]
    expected_hash = _require_string(entry.get("content_hash"), f"{filename} content_hash")
    expected_size = _require_int(entry.get("byte_size"), f"{filename} byte_size")
    expected_rows = _require_int(entry.get("record_count"), f"{filename} record_count")
    if len(expected_hash) != 64 or expected_size < 0 or expected_rows < 0:
        raise ReleaseLoadError(f"invalid {filename} artifact metadata")
    path = directory / filename
    if not path.is_file():
        raise ReleaseLoadError(f"missing artifact {filename}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_hash:
        raise ReleaseLoadError(f"artifact hash/size mismatch: {filename}")
    return path


def _validate_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ReleaseLoadError("manifest must be an object")
    # A 172 MB api_snapshot in releases.manifest would be deserialised into
    # every API worker on every read.  It must never reach the table.
    if "api_snapshot" in manifest:
        raise ReleaseLoadError("manifest must not embed an api_snapshot")
    if manifest.get("release_class") != RELEASE_CLASS:
        raise ReleaseLoadError("standard loader requires release_class 'standard'")
    if manifest.get("synthetic") is not False:
        raise ReleaseLoadError("synthetic releases cannot be loaded")
    if manifest.get("election_slug") != ELECTION_SLUG:
        raise ReleaseLoadError(f"manifest election_slug must be {ELECTION_SLUG!r}")
    if manifest.get("status") not in {"candidate", "published"}:
        raise ReleaseLoadError("only candidate/published releases can load")
    release_id = _require_string(manifest.get("release_id"), "release_id")
    if manifest.get("data_version") != release_id:
        raise ReleaseLoadError("release_id and data_version must be identical")
    _require_string(manifest.get("methodology_version"), "methodology_version")
    return manifest, release_id


def _validate_load_manifest(
    load_manifest: dict[str, Any], release_id: str, manifest: dict[str, Any]
) -> None:
    if load_manifest.get("release_id") != release_id:
        raise ReleaseLoadError("load manifest describes a different release")
    if load_manifest.get("election_slug") != ELECTION_SLUG:
        raise ReleaseLoadError("load manifest describes a different election")
    sources = load_manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != len(_EXPECTED_SOURCES):
        raise ReleaseLoadError("load manifest must describe exactly four sources")
    by_id = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ReleaseLoadError("load manifest sources must be objects")
        identifier = _require_string(source.get("id"), "source id")
        if _PAIR.get(str(source.get("source_type"))) != source.get("legal_status"):
            raise ReleaseLoadError(f"source {identifier!r} has an invalid legal status")
        for field in ("source_url", "parser_version", "transform_version"):
            _require_string(source.get(field), f"source {field}")
        if len(_require_string(source.get("content_hash"), "source content_hash")) != 64:
            raise ReleaseLoadError(f"source {identifier!r} content_hash must be SHA-256")
        _timestamp(source.get("retrieved_at"), "source retrieved_at")
        by_id[identifier] = source
    if set(by_id) != set(_EXPECTED_SOURCES):
        raise ReleaseLoadError("load manifest sources do not match the expected grains")
    # The derived rollup must stay structurally distinguishable from the three
    # grains that correspond to published documents.
    if by_id[SOURCE_ROLLUP]["transform_version"] != ROLLUP_TRANSFORM:
        raise ReleaseLoadError(f"the rollup source must use transform {ROLLUP_TRANSFORM}")
    for identifier in (SOURCE_NATIONAL, SOURCE_PLACE, SOURCE_MESA):
        if by_id[identifier]["transform_version"] == ROLLUP_TRANSFORM:
            raise ReleaseLoadError("a published grain must not claim the rollup transform")
    # The national grain is a single published document, so its hash must match
    # the release manifest's own entry for it byte for byte.
    declared = [
        entry
        for entry in manifest.get("sources", [])
        if isinstance(entry, dict) and entry.get("id") == SOURCE_NATIONAL
    ]
    if len(declared) != 1:
        raise ReleaseLoadError(f"manifest must declare the {SOURCE_NATIONAL} source")
    for field in ("content_hash", "source_url", "parser_version", "transform_version"):
        if declared[0].get(field) != by_id[SOURCE_NATIONAL][field]:
            raise ReleaseLoadError(f"national source {field} does not match the release manifest")
    summary = load_manifest.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("reconciliation"), dict):
        raise ReleaseLoadError("load manifest has no usable summary block")


def _reject_foreign_id_scheme(value: str, label: str) -> None:
    # ``r1:``/``r2:`` is the historical 2022/2018 scheme.  A 2026 standard
    # release uses ``CO``/``scope:<code>``; mixing them would silently load a
    # context release through a path that asserts none of its invariants.
    if value.startswith(("r1:", "r2:")):
        raise ReleaseLoadError(f"{label} uses the historical r1:/r2: id scheme")


def _copy(connection: Connection, target: str, rows: list[tuple[Any, ...]]) -> None:
    """COPY one bounded batch, translating a key collision into our own error.

    The scoped primary keys the staging tier used to re-derive with a GROUP BY
    are real constraints on these tables.  A duplicate now aborts the
    transaction at the row that caused it; the caller still gets the sentence.
    """
    try:
        _copy_rows(connection, f"COPY {target} FROM STDIN", rows)
    except Exception as exc:  # noqa: BLE001 - re-raised below unless it is class 23
        # COPY runs on the driver connection, so a constraint violation arrives
        # as a psycopg error rather than a SQLAlchemy one.  SQLSTATE class 23 is
        # "integrity constraint violation"; anything else is not ours to reword.
        if not str(getattr(exc, "sqlstate", "") or "").startswith("23"):
            raise
        raise ReleaseLoadError("artifacts contain duplicate scoped primary keys") from exc


def _copy_geography_rows(connection: Connection, release_id: str, path: Path, limit: int) -> int:
    loaded = 0
    for batch in _batches(path, _GEOGRAPHY_COLUMNS, limit):
        buffer: list[tuple[Any, ...]] = []
        for row in batch:
            identifier = _require_string(row.get("id"), "geography id")
            _reject_foreign_id_scheme(identifier, "geography id")
            level = _require_string(row.get("level"), "geography level")
            if level not in _LEVEL_RANK or level == "mesa":
                raise ReleaseLoadError("staged geography has an unloadable level")
            parent = row.get("parent_id")
            if parent is not None:
                parent = _require_string(parent, "geography parent_id")
            buffer.append(
                (
                    release_id,
                    ELECTION_SLUG,
                    identifier,
                    level,
                    _require_string(row.get("code"), "geography code"),
                    _require_string(row.get("name"), "geography name"),
                    parent,
                    _require_string(row.get("canonical_path"), "geography canonical_path"),
                )
            )
            loaded += 1
        _copy(connection, _GEOGRAPHY_TARGET, buffer)
    return loaded


def _copy_mesa_rows(connection: Connection, release_id: str, path: Path, limit: int) -> int:
    loaded = 0
    for batch in _batches(path, _MESA_COLUMNS, limit):
        buffer: list[tuple[Any, ...]] = []
        for row in batch:
            identifier = _require_string(row.get("id"), "mesa id")
            _reject_foreign_id_scheme(identifier, "mesa id")
            buffer.append(
                (
                    release_id,
                    ELECTION_SLUG,
                    identifier,
                    _require_string(row.get("display_number"), "mesa display_number"),
                    _require_string(row.get("polling_place_id"), "mesa polling_place_id"),
                    _require_string(row.get("municipality_id"), "mesa municipality_id"),
                    _require_string(row.get("department_id"), "mesa department_id"),
                )
            )
            loaded += 1
        _copy(connection, _MESA_TARGET, buffer)
    return loaded


def _copy_fact_rows(connection: Connection, release_id: str, path: Path, limit: int) -> int:
    """Stream the published facts straight into ``release_result_facts``.

    ``source_geography_id`` is not a column of the read model -- it is the
    polling place the Registraduria filed the mesa under, and it exists only to
    be checked against the mesa index.  The mesa rows keep it in a two-column
    temp table (about 8 MB) so the set-wise assertion is unchanged; nothing else
    is duplicated.
    """
    loaded = 0
    for batch in _batches(path, _FACT_COLUMNS, limit):
        facts: list[tuple[Any, ...]] = []
        places: list[tuple[Any, ...]] = []
        for row in batch:
            identifier = _require_string(row.get("id"), "fact id")
            level = _require_string(row.get("geography_level"), "fact geography_level")
            if level not in _LEVEL_RANK:
                raise ReleaseLoadError(f"fact {identifier!r} has an unknown level")
            geography_id = _require_string(row.get("geography_id"), "fact geography_id")
            _reject_foreign_id_scheme(geography_id, "fact geography_id")
            mesa_id = row.get("mesa_id")
            # The rewrite must already have happened, and must be exactly this.
            if (level == "mesa") != (mesa_id is not None):
                raise ReleaseLoadError(f"fact {identifier!r} mismatches mesa level and mesa_id")
            if mesa_id is not None and mesa_id != geography_id:
                raise ReleaseLoadError(f"mesa fact {identifier!r} was not rewritten to its mesa")
            if _require_string(row.get("source_id"), "fact source_id") not in _EXPECTED_SOURCES:
                raise ReleaseLoadError(f"fact {identifier!r} names an unknown source")
            metrics: dict[str, Any] = {}
            for metric in METRICS:
                status = _require_string(row.get(f"{metric}_status"), f"{metric} status")
                value = row.get(f"{metric}_value")
                if (status == "observed") != (value is not None):
                    raise ReleaseLoadError(f"fact {identifier!r} has an incoherent {metric}")
                if value is not None and _require_int(value, f"{metric} value") < 0:
                    raise ReleaseLoadError(f"fact {identifier!r} has a negative {metric}")
                metrics[metric] = {"value": value, "status": status}
            facts.append(
                (
                    release_id,
                    ELECTION_SLUG,
                    identifier,
                    geography_id,
                    level,
                    mesa_id,
                    row["source_id"],
                    json.dumps(metrics, separators=(",", ":")),
                    _require_string(row.get("content_hash"), "fact content_hash"),
                    _timestamp(row.get("retrieved_at"), "fact retrieved_at"),
                )
            )
            if mesa_id is not None:
                places.append(
                    (
                        mesa_id,
                        _require_string(row.get("source_geography_id"), "fact source_geography_id"),
                    )
                )
            loaded += 1
        _copy(connection, _FACT_TARGET, facts)
        if places:
            _copy_rows(
                connection,
                "COPY stage_mesa_fact_place (mesa_id,source_geography_id) FROM STDIN",
                places,
            )
    return loaded


def _copy_category_rows(connection: Connection, release_id: str, path: Path, limit: int) -> int:
    loaded = 0
    for batch in _batches(path, _CATEGORY_COLUMNS, limit):
        buffer: list[tuple[Any, ...]] = []
        for row in batch:
            status = _require_string(row.get("status"), "category status")
            votes = row.get("votes")
            if (status == "observed") != (votes is not None):
                raise ReleaseLoadError("category votes and status are incoherent")
            if votes is not None and _require_int(votes, "category votes") < 0:
                raise ReleaseLoadError("category votes cannot be negative")
            for field in ("result_fact_id", "category_key", "category_code", "category_name"):
                _require_string(row.get(field), f"category {field}")
            buffer.append(
                (
                    release_id,
                    ELECTION_SLUG,
                    row["result_fact_id"],
                    row["category_key"],
                    row["category_code"],
                    row["category_name"],
                    _require_string(row.get("category_kind"), "category category_kind"),
                    votes,
                    status,
                )
            )
            loaded += 1
        _copy(connection, _CATEGORY_TARGET, buffer)
    return loaded


def _analyze(connection: Connection, tables: tuple[str, ...]) -> None:
    for table in tables:
        connection.execute(text(f"ANALYZE {table}"))


def _assert(connection: Connection, sql: str, parameters: dict[str, Any], message: str) -> None:
    if connection.execute(text(sql), parameters).scalar_one():
        raise ReleaseLoadError(message)


def _scope(release_id: str) -> dict[str, Any]:
    return {"r": release_id, "e": ELECTION_SLUG}


def _derive_mesa_geographies(connection: Connection, release_id: str) -> None:
    """Materialise the 122,020 mesa geographies the snapshot does not ship."""
    connection.execute(
        text(
            f"INSERT INTO {_GEOGRAPHY_TARGET} "
            "SELECT m.release_id,m.election_slug,m.id,'mesa',m.display_number,"
            " 'Mesa ' || m.display_number,m.polling_place_id,"
            " p.canonical_path || '/' || m.id "
            "FROM release_mesas m "
            "JOIN release_geographies p ON (p.release_id,p.election_slug,p.id)="
            " (m.release_id,m.election_slug,m.polling_place_id) AND p.level='polling_place' "
            "WHERE m.release_id=:r AND m.election_slug=:e"
        ),
        _scope(release_id),
    )
    # THE assertion.  A mesa id is 15 or 17 characters and a polling-place code
    # is 9 or 11, so slicing an id to find its place misassigns 48.5% of mesas.
    # The concatenation identity is what actually holds; if it ever does not,
    # the polling place is wrong and nothing downstream can be trusted.
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_mesas m "
        "LEFT JOIN release_geographies p ON (p.release_id,p.election_slug,p.id)="
        " (m.release_id,m.election_slug,m.polling_place_id) AND p.level='polling_place' "
        "WHERE m.release_id=:r AND m.election_slug=:e "
        " AND (p.id IS NULL OR m.id <> p.code || m.display_number)",
        _scope(release_id),
        "a mesa id is not its polling-place code plus its display number",
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM stage_mesa_fact_place s "
        "JOIN release_mesas m ON m.id=s.mesa_id AND m.release_id=:r AND m.election_slug=:e "
        "WHERE s.source_geography_id <> m.polling_place_id",
        _scope(release_id),
        "a mesa fact was rewritten away from its own polling place",
    )


def _build_mesa_lineage(connection: Connection, release_id: str) -> None:
    """The (mesa -> place, zone, municipality, department) map, once.

    122,020 narrow rows.  This is the only working set the load materialises:
    the zone is the polling place's parent and is not on ``release_mesas``, and
    the rollup and both reconciliation queries all need it.
    """
    connection.execute(
        text(
            "CREATE TEMP TABLE stage_mesa_lineage ON COMMIT DROP AS "
            "SELECT m.id AS mesa_id,m.polling_place_id,place.parent_id AS zone_id,"
            " m.municipality_id,m.department_id "
            "FROM release_mesas m "
            "JOIN release_geographies place ON (place.release_id,place.election_slug,"
            " place.id)=(m.release_id,m.election_slug,m.polling_place_id) "
            "WHERE m.release_id=:r AND m.election_slug=:e AND place.level='polling_place'"
        ),
        _scope(release_id),
    )
    _analyze(connection, ("stage_mesa_lineage",))
    _assert(
        connection,
        "SELECT COUNT(*) FROM stage_mesa_lineage l "
        "LEFT JOIN release_geographies z ON z.release_id=:r AND z.election_slug=:e "
        " AND z.id=l.zone_id AND z.level='zone' "
        "LEFT JOIN release_geographies mu ON mu.release_id=:r AND mu.election_slug=:e "
        " AND mu.id=l.municipality_id AND mu.level='municipality' "
        "WHERE z.id IS NULL OR mu.id IS NULL OR z.parent_id <> l.municipality_id "
        " OR mu.parent_id <> l.department_id",
        _scope(release_id),
        "the mesa lineage disagrees with the geography hierarchy",
    )


def _derive_aggregate_facts(connection: Connection, release_id: str) -> int:
    """Sum the mesa facts into the zone/municipality/department levels.

    One pass, three groupings.  The old shape built a (level, geography, mesa)
    membership table -- 366,060 rows plus two indexes -- and joined the facts
    and the categories back through it; that join is what spilled into
    ``base/pgsql_tmp`` and filled the volume.  ``GROUPING SETS`` asks the
    planner for the same three aggregations over a single scan instead.
    """
    # ``registered_electors`` is deliberately absent from this sum: it is
    # unavailable on 122,008 of 122,020 mesas, so a total would be a fabricated
    # denominator rather than a smaller one.
    sums = ",".join(f"SUM({_metric_value('f', metric)}) AS {metric}" for metric in _VOTE_METRICS)
    observed = " AND ".join(
        f"bool_and({_metric_status('f', metric)}='observed')" for metric in _VOTE_METRICS
    )
    connection.execute(
        text(
            "CREATE TEMP TABLE stage_rollup ON COMMIT DROP AS "
            f"SELECT {_ROLLUP_LEVEL} AS level,{_ROLLUP_GEOGRAPHY} AS geography_id,"
            f"{sums},({observed}) AS all_observed "
            "FROM release_result_facts f "
            "JOIN stage_mesa_lineage l ON l.mesa_id=f.mesa_id "
            "WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='mesa' "
            f"GROUP BY {_ROLLUP_GROUPING_SETS}"
        ),
        _scope(release_id),
    )
    _analyze(connection, ("stage_rollup",))
    _assert(
        connection,
        "SELECT COUNT(*) FROM stage_rollup WHERE NOT all_observed",
        {},
        "an aggregate would hide a non-observed mesa metric",
    )
    connection.execute(
        text(
            f"INSERT INTO {_FACT_TARGET} "
            "SELECT :r,:e,'rollup-' || r.level || '-' || g.code,r.geography_id,r.level,"
            f" NULL,:source,{_DERIVED_METRICS_JSON},:hash,:retrieved "
            "FROM stage_rollup r "
            "JOIN release_geographies g ON (g.release_id,g.election_slug,g.id)="
            " (:r,:e,r.geography_id) AND g.level=r.level"
        ),
        {
            **_scope(release_id),
            "source": SOURCE_ROLLUP,
            "hash": _rollup_hash(connection, release_id),
            # An aggregate is only as fresh as the newest mesa it contains.
            "retrieved": connection.execute(
                text(
                    "SELECT MAX(fact_retrieved_at) FROM release_result_facts "
                    "WHERE release_id=:r AND election_slug=:e AND geography_level='mesa'"
                ),
                _scope(release_id),
            ).scalar_one(),
        },
    )
    connection.execute(
        text(
            f"INSERT INTO {_CATEGORY_TARGET} "
            "SELECT :r,:e,'rollup-' || a.level || '-' || g.code,a.category_key,a.category_code,"
            " a.category_name,a.category_kind,a.votes,a.status FROM ("
            f" SELECT {_ROLLUP_LEVEL} AS level,{_ROLLUP_GEOGRAPHY} AS geography_id,"
            "  c.category_key,c.category_code,MIN(c.category_name) AS category_name,"
            "  MIN(c.category_kind) AS category_kind,SUM(c.votes) AS votes,"
            "  CASE WHEN bool_and(c.status='observed') THEN 'observed'"
            "   ELSE 'unavailable' END AS status"
            "  FROM release_category_facts c"
            "  JOIN release_result_facts f ON (f.release_id,f.election_slug,f.id)="
            "   (c.release_id,c.election_slug,c.result_fact_id)"
            "  JOIN stage_mesa_lineage l ON l.mesa_id=f.mesa_id"
            "  WHERE c.release_id=:r AND c.election_slug=:e AND f.geography_level='mesa'"
            f"  GROUP BY {_ROLLUP_GROUPING_SETS},c.category_key,c.category_code"
            ") a "
            "JOIN release_geographies g ON (g.release_id,g.election_slug,g.id)="
            " (:r,:e,a.geography_id) AND g.level=a.level"
        ),
        _scope(release_id),
    )
    derived = int(
        connection.execute(
            text(
                "SELECT COUNT(*) FROM release_result_facts "
                "WHERE release_id=:r AND election_slug=:e AND source_id=:s"
            ),
            {**_scope(release_id), "s": SOURCE_ROLLUP},
        ).scalar_one()
    )
    aggregate_geographies = int(
        connection.execute(
            text(
                "SELECT COUNT(*) FROM release_geographies "
                "WHERE release_id=:r AND election_slug=:e AND level = ANY(:levels)"
            ),
            {**_scope(release_id), "levels": list(_DERIVED_LEVELS)},
        ).scalar_one()
    )
    # Every zone, municipality and department must get exactly one derived fact:
    # a missing one is a hole in the read model, an extra one is a phantom.
    if derived != aggregate_geographies:
        raise ReleaseLoadError("derived aggregates do not cover every aggregate geography exactly")
    return derived


def _rollup_hash(connection: Connection, release_id: str) -> str:
    """Digest the mesa fact set the rollup is computed from."""
    return str(
        connection.execute(
            text(
                "SELECT encode(sha256(string_agg(id || ':' || fact_content_hash,E'\\x1e' "
                "ORDER BY id)::bytea),'hex') FROM release_result_facts "
                "WHERE release_id=:r AND election_slug=:e AND geography_level='mesa'"
            ),
            _scope(release_id),
        ).scalar_one()
    )


def _reconcile(connection: Connection, release_id: str) -> None:
    """Assert the derived numbers add up, or abort the whole transaction."""
    metric_equal = " OR ".join(
        f"{_metric_value('p', metric)} <> s.{metric}" for metric in _VOTE_METRICS
    )
    sums = ",".join(f"SUM({_metric_value('f', metric)}) AS {metric}" for metric in _VOTE_METRICS)
    mesa_facts = (
        "FROM release_result_facts f "
        "JOIN stage_mesa_lineage l ON l.mesa_id=f.mesa_id "
        "WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='mesa'"
    )
    # Every one of the 14,438 published polling-place facts must equal the sum
    # of the mesas the mesa index assigns to it.  This is what would fail loudly
    # if a mesa were ever attached to the wrong place.
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_result_facts p LEFT JOIN ("
        f" SELECT l.polling_place_id AS geography_id,{sums} {mesa_facts}"
        "  GROUP BY l.polling_place_id"
        ") s ON s.geography_id=p.geography_id "
        "WHERE p.release_id=:r AND p.election_slug=:e AND p.geography_level='polling_place' "
        f"AND (s.geography_id IS NULL OR {metric_equal})",
        _scope(release_id),
        "a polling-place total does not equal the sum of its mesas",
    )
    category_sums = (
        "SELECT l.polling_place_id AS geography_id,c.category_key,SUM(c.votes) AS votes "
        "FROM release_result_facts f "
        "JOIN stage_mesa_lineage l ON l.mesa_id=f.mesa_id "
        "JOIN release_category_facts c ON (c.release_id,c.election_slug,c.result_fact_id)="
        " (f.release_id,f.election_slug,f.id) "
        "WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='mesa' "
        "GROUP BY l.polling_place_id,c.category_key"
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_result_facts p "
        "JOIN release_category_facts pc ON (pc.release_id,pc.election_slug,pc.result_fact_id)="
        " (p.release_id,p.election_slug,p.id) "
        f"LEFT JOIN ({category_sums}) s ON s.geography_id=p.geography_id "
        " AND s.category_key=pc.category_key "
        "WHERE p.release_id=:r AND p.election_slug=:e AND p.geography_level='polling_place' "
        "AND (s.votes IS NULL OR pc.votes <> s.votes)",
        _scope(release_id),
        "a polling-place candidate total does not equal the sum of its mesas",
    )
    # And the 34 derived department totals must reproduce the published nation.
    national_equal = " OR ".join(
        f"{_metric_value('n', metric)} <> d.{metric}" for metric in _VOTE_METRICS
    )
    department_sums = ",".join(
        f"SUM({_metric_value('f', metric)}) AS {metric}" for metric in _VOTE_METRICS
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_result_facts n CROSS JOIN ("
        f" SELECT {department_sums} FROM release_result_facts f"
        "  WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='department'"
        ") d WHERE n.release_id=:r AND n.election_slug=:e AND n.geography_level='national' "
        f"AND ({national_equal})",
        _scope(release_id),
        "the department totals do not reproduce the national fact",
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_result_facts n "
        "JOIN release_category_facts nc ON (nc.release_id,nc.election_slug,nc.result_fact_id)="
        " (n.release_id,n.election_slug,n.id) "
        "LEFT JOIN ("
        " SELECT c.category_key,SUM(c.votes) AS votes FROM release_result_facts f"
        "  JOIN release_category_facts c ON (c.release_id,c.election_slug,c.result_fact_id)="
        "   (f.release_id,f.election_slug,f.id)"
        "  WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='department'"
        "  GROUP BY c.category_key"
        ") d ON d.category_key=nc.category_key "
        "WHERE n.release_id=:r AND n.election_slug=:e AND n.geography_level='national' "
        "AND (d.votes IS NULL OR nc.votes <> d.votes)",
        _scope(release_id),
        "the department candidate totals do not reproduce the national fact",
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_result_facts f "
        "WHERE f.release_id=:r AND f.election_slug=:e AND f.source_id=:s AND "
        f"({_metric_value('f', 'registered_electors')} IS NOT NULL OR "
        f"{_metric_status('f', 'registered_electors')} <> 'unavailable')",
        {**_scope(release_id), "s": SOURCE_ROLLUP},
        "a derived aggregate fabricated a registered-electors denominator",
    )


def _validate_relations(connection: Connection, release_id: str) -> None:
    _assert(
        connection,
        "SELECT COUNT(*) FROM release_geographies g "
        "LEFT JOIN release_geographies p ON p.release_id=g.release_id "
        " AND p.election_slug=g.election_slug AND p.id=g.parent_id "
        "WHERE g.release_id=:r AND g.election_slug=:e AND g.parent_id IS NOT NULL "
        " AND p.id IS NULL",
        _scope(release_id),
        "geography hierarchy contains an orphan",
    )
    _assert(
        connection,
        "SELECT COUNT(*) FROM ("
        " SELECT f.id FROM release_result_facts f"
        " LEFT JOIN release_geographies g ON g.release_id=:r AND g.election_slug=:e"
        "  AND g.id=f.geography_id"
        " LEFT JOIN release_mesas m ON m.release_id=:r AND m.election_slug=:e AND m.id=f.mesa_id"
        " WHERE f.release_id=:r AND f.election_slug=:e"
        "  AND (g.id IS NULL OR f.geography_level<>g.level"
        "   OR (g.level='mesa')<>(f.mesa_id IS NOT NULL)"
        "   OR (f.mesa_id IS NOT NULL AND m.id IS NULL))"
        " UNION ALL"
        " SELECT c.result_fact_id FROM release_category_facts c"
        " LEFT JOIN release_result_facts f ON (f.release_id,f.election_slug,f.id)="
        "  (c.release_id,c.election_slug,c.result_fact_id)"
        " WHERE c.release_id=:r AND c.election_slug=:e AND f.id IS NULL"
        ") invalid",
        _scope(release_id),
        "loaded rows violate a scoped relational invariant",
    )


def load_standard_2026_release(
    engine: Engine,
    manifest_path: Path,
    artifact_directory: Path,
    *,
    batch_size: int = 20_000,
) -> str:
    """Load the 2026 standard release in one transaction, internal-only."""
    if batch_size < 1:
        raise ReleaseLoadError("batch_size must be positive")
    if engine.dialect.name != "postgresql":
        raise ReleaseLoadError("standard loader requires PostgreSQL")
    manifest, release_id = _validate_manifest(manifest_path)
    _reject_foreign_id_scheme(release_id, "release_id")
    load_manifest_path = artifact_directory / LOAD_MANIFEST
    if not load_manifest_path.is_file():
        raise ReleaseLoadError(f"artifact directory has no {LOAD_MANIFEST}")
    load_manifest = json.loads(load_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(load_manifest, dict):
        raise ReleaseLoadError("load manifest must be an object")
    _validate_load_manifest(load_manifest, release_id, manifest)
    paths = {
        name: _artifact_path(artifact_directory, load_manifest, name)
        for name in (GEOGRAPHY_ARTIFACT, MESA_ARTIFACT, FACT_ARTIFACT, CATEGORY_ARTIFACT)
    }
    expected = {entry["filename"]: entry["record_count"] for entry in load_manifest["artifacts"]}
    manifest_hash = _digest(manifest)
    summary = load_manifest["summary"]
    election = load_manifest["election"]

    with engine.begin() as connection:
        # Claim the release id before reading its state.  Without this the
        # check and the INSERT are two steps: a second loader reads "absent",
        # both insert, and the loser surfaces a raw duplicate-key IntegrityError
        # instead of the documented noop.  The lock is transaction scoped, so a
        # concurrent loader waits here and then reads the committed rows below.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _advisory_key(release_id)}
        )
        existing = list(
            connection.execute(
                text("SELECT manifest_hash FROM release_exposures WHERE release_id=:r"),
                {"r": release_id},
            ).scalars()
        )
        if existing:
            if len(existing) == 1 and existing[0] == manifest_hash:
                return "noop"
            raise ReleaseLoadError("release id already loaded with a different manifest hash")
        if connection.execute(
            text("SELECT 1 FROM releases WHERE id=:r"), {"r": release_id}
        ).scalar():
            raise ReleaseLoadError(
                "release id is already reserved without a matching immutable exposure"
            )
        connection.execute(
            text(
                "CREATE TEMP TABLE stage_mesa_fact_place "
                "(mesa_id text NOT NULL, source_geography_id text NOT NULL) ON COMMIT DROP"
            )
        )

        try:
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
                    "method": manifest["methodology_version"],
                    "manifest": json.dumps(manifest, separators=(",", ":")),
                },
            )
        except IntegrityError as exc:
            # Unreachable while the advisory lock holds, and kept anyway: a
            # caller must never have to read a driver traceback to learn that
            # another loader owns this release id.
            raise ReleaseLoadError(
                "release id was claimed by a concurrent loader during this transaction"
            ) from exc
        connection.execute(
            text(
                "INSERT INTO release_elections "
                "(release_id,election_slug,name_es,name_en,round,election_date) "
                "VALUES (:r,:e,:es,:en,:n,:d)"
            ),
            {
                **_scope(release_id),
                "es": election["name_es"],
                "en": election["name_en"],
                "n": election["round"],
                "d": election["election_date"],
            },
        )
        for source in load_manifest["sources"]:
            connection.execute(
                text(
                    "INSERT INTO release_sources "
                    "(release_id,election_slug,id,source_type,legal_status,source_url,"
                    "retrieved_at,content_hash,parser_version,transform_version) "
                    "VALUES (:r,:e,:id,:type,:legal,:url,:at,:hash,:parser,:transform)"
                ),
                {
                    **_scope(release_id),
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

        loaded_geographies = _copy_geography_rows(
            connection, release_id, paths[GEOGRAPHY_ARTIFACT], batch_size
        )
        loaded_mesas = _copy_mesa_rows(connection, release_id, paths[MESA_ARTIFACT], batch_size)
        loaded_facts = _copy_fact_rows(connection, release_id, paths[FACT_ARTIFACT], batch_size)
        loaded_categories = _copy_category_rows(
            connection, release_id, paths[CATEGORY_ARTIFACT], batch_size
        )
        for name, loaded in (
            (GEOGRAPHY_ARTIFACT, loaded_geographies),
            (MESA_ARTIFACT, loaded_mesas),
            (FACT_ARTIFACT, loaded_facts),
            (CATEGORY_ARTIFACT, loaded_categories),
        ):
            if loaded != expected[name]:
                raise ReleaseLoadError(f"{name} streamed row count differs from the load manifest")

        # A freshly COPYed table has no statistics, and the planner then
        # nested-loops 122,020 mesas against 18,675 geographies.  Analyse before
        # the derivations, not after them.
        _analyze(
            connection,
            (
                "release_geographies",
                "release_mesas",
                "release_result_facts",
                "release_category_facts",
                "stage_mesa_fact_place",
            ),
        )
        _derive_mesa_geographies(connection, release_id)
        _analyze(connection, ("release_geographies",))
        _build_mesa_lineage(connection, release_id)
        _derive_aggregate_facts(connection, release_id)
        _analyze(connection, ("release_result_facts", "release_category_facts"))
        _reconcile(connection, release_id)
        _validate_relations(connection, release_id)

        connection.execute(
            text(
                "INSERT INTO release_summaries "
                "(release_id,election_slug,release_class,completion,coverage,"
                "geographic_collection_coverage,reconciliation,turnout) "
                "VALUES (:r,:e,:c,CAST(:completion AS jsonb),CAST(:coverage AS jsonb),"
                "CAST(:geographic AS jsonb),CAST(:reconciliation AS jsonb),:turnout)"
            ),
            {
                **_scope(release_id),
                "c": RELEASE_CLASS,
                "completion": json.dumps(summary["completion"], separators=(",", ":")),
                "coverage": json.dumps(summary["coverage"], separators=(",", ":")),
                "geographic": json.dumps(
                    summary["geographic_collection_coverage"], separators=(",", ":")
                ),
                "reconciliation": json.dumps(summary["reconciliation"], separators=(",", ":")),
                "turnout": summary["turnout"],
            },
        )
        # The exposure insert fires validate_release_exposure, which re-checks
        # every relationship with EXCEPT queries over the 140,695 loaded rows.
        # Without statistics the planner nested-loops them.
        _analyze(connection, ("release_sources",))
        connection.execute(
            text(
                "INSERT INTO release_exposures "
                "(release_id,election_slug,access_scope,approved_at,manifest_hash) "
                "VALUES (:r,:e,'internal',NULL,:h)"
            ),
            {**_scope(release_id), "h": manifest_hash},
        )
        # Loading is not publication, and it is not a preview grant either.
        # Both wider scopes are separate reviewed steps.
        exposed = connection.execute(
            text(
                "SELECT COUNT(*) FROM release_exposures "
                "WHERE release_id=:r AND access_scope<>'internal'"
            ),
            {"r": release_id},
        ).scalar_one()
        if exposed:
            raise ReleaseLoadError("loader may not grant public or preliminary exposure")
    return "loaded"
