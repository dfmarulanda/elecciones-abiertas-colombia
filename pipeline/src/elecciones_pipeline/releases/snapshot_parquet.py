"""Stage A: stream a standard 2026 API snapshot into bounded Parquet artifacts.

The snapshot is a 172 MB JSON document.  Nothing here ever holds it in memory:
``ijson`` yields one record at a time and each artifact is written in batches.
Only the geography graph (18,675 rows) and the mesa -> polling-place index
(122,020 rows) are retained, because both are needed to check the invariants
that the id strings themselves do not encode.

The one invariant this stage exists to protect
----------------------------------------------
A mesa id is *not* fixed width -- 62,821 are 15 characters and 59,199 are 17 --
and a polling-place code is 9 or 11 characters.  Deriving a mesa's polling place
by slicing its id therefore misassigns 59,199 of 122,020 mesas, silently.  The
polling place is read from ``mesas[].polling_place_id`` and never from the id,
and the concatenation identity ``mesa.id == place.code + mesa.display_number``
is asserted on every row.

Mesa result facts arrive with ``geography_id`` set to the *polling place* and a
separate ``mesa_id``.  They are rewritten to ``geography_id = mesa_id`` after
asserting the original equals that mesa's recorded polling place; the original
survives in ``source_geography_id`` so the rewrite stays auditable in the
artifact and re-checkable in SQL at load time.  Without the rewrite the
``geography_level = geography.level`` invariant breaks and a mesa lookup, which
filters on ``geography_id = mesa_id``, returns nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import ijson  # type: ignore[import-untyped]
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from ._bulk import _LEVEL_RANK, _PAIR, ReleaseLoadError, _require_int, _require_string, _timestamp

ELECTION_SLUG = "presidencia-2026-segunda-vuelta"
METRICS = (
    "registered_electors",
    "voters",
    "valid_votes",
    "blank_votes",
    "null_votes",
    "unmarked_votes",
)
# ``valid_votes`` already includes blanks (valid = sum(candidates) + blank, and
# voters = valid + null + unmarked, verified at every level).  The six metrics
# are therefore carried through independently and never reconstructed.
CATEGORY_KIND = "candidate"
SOURCE_NATIONAL = "registraduria-precount-national-2026-r2"
SOURCE_PLACE = "registraduria-precount-places-2026-r2"
SOURCE_MESA = "registraduria-precount-mesas-2026-r2"
SOURCE_ROLLUP = "derived-mesa-rollup-2026-r2"
ROLLUP_TRANSFORM = "mesa-rollup@1.0.0"
ROLLUP_URL = "https://eleccionesabiertas.co/derivations/mesa-rollup"
_LEVEL_SOURCE = {
    "national": SOURCE_NATIONAL,
    "polling_place": SOURCE_PLACE,
    "mesa": SOURCE_MESA,
}

GEOGRAPHY_ARTIFACT = "geography.parquet"
MESA_ARTIFACT = "mesas.parquet"
FACT_ARTIFACT = "facts.parquet"
CATEGORY_ARTIFACT = "categories.parquet"
LOAD_MANIFEST = "load-manifest.json"

_GEOGRAPHY_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("level", pa.string()),
        ("code", pa.string()),
        ("name", pa.string()),
        ("parent_id", pa.string()),
        ("canonical_path", pa.string()),
    ]
)
_MESA_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("display_number", pa.string()),
        ("polling_place_id", pa.string()),
        ("municipality_id", pa.string()),
        ("department_id", pa.string()),
    ]
)
_FACT_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("geography_id", pa.string()),
        # The pre-rewrite geography_id, kept so the rewrite is auditable.
        ("source_geography_id", pa.string()),
        ("geography_level", pa.string()),
        ("mesa_id", pa.string()),
        ("source_id", pa.string()),
        *[
            field
            for metric in METRICS
            for field in ((f"{metric}_value", pa.int64()), (f"{metric}_status", pa.string()))
        ],
        ("content_hash", pa.string()),
        ("retrieved_at", pa.string()),
    ]
)
_CATEGORY_SCHEMA = pa.schema(
    [
        ("result_fact_id", pa.string()),
        ("category_key", pa.string()),
        ("category_code", pa.string()),
        ("category_name", pa.string()),
        ("category_kind", pa.string()),
        ("votes", pa.int64()),
        ("status", pa.string()),
    ]
)


class _Writer:
    """A batched Parquet writer that never accumulates a whole artifact."""

    def __init__(self, path: Path, schema: pa.Schema, batch_size: int) -> None:
        self._path = path
        self._schema = schema
        self._batch_size = batch_size
        self._columns: dict[str, list[Any]] = {name: [] for name in schema.names}
        self._writer = pq.ParquetWriter(path, schema, compression="zstd")
        self.rows = 0

    def write(self, row: dict[str, Any]) -> None:
        for name, column in self._columns.items():
            column.append(row[name])
        self.rows += 1
        if len(self._columns[self._schema.names[0]]) >= self._batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._columns[self._schema.names[0]]:
            return
        self._writer.write_table(pa.table(self._columns, schema=self._schema))
        for column in self._columns.values():
            column.clear()

    def close(self) -> None:
        self._flush()
        self._writer.close()


def _hex_digest(value: object, label: str) -> str:
    digest = _require_string(value, label)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ReleaseLoadError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _metric(payload: object, label: str) -> tuple[int | None, str]:
    if not isinstance(payload, dict) or set(payload) != {"value", "status"}:
        raise ReleaseLoadError(f"{label} must be a value/status object")
    status = _require_string(payload.get("status"), f"{label} status")
    value = payload.get("value")
    if status == "observed":
        number = _require_int(value, f"{label} value")
        if number < 0:
            raise ReleaseLoadError(f"{label} cannot be negative")
        return number, status
    if value is not None:
        raise ReleaseLoadError(f"{label} must be null unless observed")
    return None, status


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _set_digest(pairs: list[tuple[str, str]]) -> str:
    """Order-independent digest of a (fact id, content hash) set.

    A grain covered by a single document keeps that document's own hash, so the
    national source stays byte-identical to its release-manifest entry.  A grain
    standing for many documents cannot have a document hash, so it gets a
    reproducible digest over the set it covers; each fact's own hash survives in
    ``release_result_facts.fact_content_hash``.
    """
    if len(pairs) == 1:
        return pairs[0][1]
    digest = hashlib.sha256()
    for identifier, content_hash in sorted(pairs):
        digest.update(f"{identifier}\x1f{content_hash}\x1e".encode())
    return digest.hexdigest()


def _geographies(snapshot_path: Path, writer: _Writer) -> dict[str, tuple[str, str]]:
    """Write the geography artifact and return ``id -> (level, code)``."""
    rows: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    with snapshot_path.open("rb") as handle:
        for record in ijson.items(handle, "geographies.item"):
            identifier = _require_string(record.get("id"), "geography id")
            level = _require_string(record.get("level"), "geography level")
            if level not in _LEVEL_RANK:
                raise ReleaseLoadError(f"unknown geography level {level!r}")
            if level == "mesa":
                raise ReleaseLoadError("snapshot geographies must not contain mesa rows")
            parent = record.get("parent_id")
            if parent is not None:
                parent = _require_string(parent, "geography parent_id")
            if (level == "national") != (parent is None):
                raise ReleaseLoadError("only the national geography may be parentless")
            if identifier in index:
                raise ReleaseLoadError(f"duplicate geography id {identifier!r}")
            row = {
                "id": identifier,
                "level": level,
                "code": _require_string(record.get("code"), "geography code"),
                "name": _require_string(record.get("name"), "geography name"),
                "parent_id": parent,
                "canonical_path": None,
            }
            index[identifier] = row
            rows.append(row)

    expected_parent = {
        "department": "national",
        "municipality": "department",
        "zone": "municipality",
        "polling_place": "zone",
    }
    paths: dict[str, str] = {}

    def canonical_path(identifier: str) -> str:
        if identifier in paths:
            return paths[identifier]
        row = index.get(identifier)
        if row is None:
            raise ReleaseLoadError(f"geography {identifier!r} has no parent record")
        parent = row["parent_id"]
        if parent is None:
            resolved = identifier
        else:
            parent_row = index.get(parent)
            if parent_row is None:
                raise ReleaseLoadError(f"geography {identifier!r} references a missing parent")
            if parent_row["level"] != expected_parent.get(row["level"]):
                raise ReleaseLoadError(f"geography {identifier!r} has a wrong-level parent")
            resolved = f"{canonical_path(parent)}/{identifier}"
        paths[identifier] = resolved
        return resolved

    for row in rows:
        row["canonical_path"] = canonical_path(row["id"])
        writer.write(row)
    return {row["id"]: (row["level"], row["code"]) for row in rows}


def _mesas(
    snapshot_path: Path, writer: _Writer, geographies: dict[str, tuple[str, str]]
) -> dict[str, str]:
    """Write the mesa artifact and return ``mesa id -> polling place id``."""
    places: dict[str, str] = {}
    with snapshot_path.open("rb") as handle:
        for record in ijson.items(handle, "mesas.item"):
            identifier = _require_string(record.get("id"), "mesa id")
            display_number = _require_string(record.get("display_number"), "mesa display_number")
            place_id = _require_string(record.get("polling_place_id"), "mesa polling_place_id")
            place = geographies.get(place_id)
            if place is None or place[0] != "polling_place":
                raise ReleaseLoadError(f"mesa {identifier!r} names a non-polling-place parent")
            # The identity that actually holds.  Never slice the id: mesa ids are
            # 15 or 17 characters and place codes are 9 or 11.
            if place[1] + display_number != identifier:
                raise ReleaseLoadError(
                    f"mesa {identifier!r} is not its polling-place code plus display number"
                )
            for field, level in (
                ("municipality_id", "municipality"),
                ("department_id", "department"),
            ):
                value = _require_string(record.get(field), f"mesa {field}")
                if geographies.get(value, ("", ""))[0] != level:
                    raise ReleaseLoadError(f"mesa {identifier!r} has an invalid {field}")
            if identifier in places:
                raise ReleaseLoadError(f"duplicate mesa id {identifier!r}")
            places[identifier] = place_id
            writer.write(
                {
                    "id": identifier,
                    "display_number": display_number,
                    "polling_place_id": place_id,
                    "municipality_id": record["municipality_id"],
                    "department_id": record["department_id"],
                }
            )
    return places


def _results(
    snapshot_path: Path,
    facts: _Writer,
    categories: _Writer,
    geographies: dict[str, tuple[str, str]],
    mesa_places: dict[str, str],
    candidate_names: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Write the fact/category artifacts and return per-source aggregates."""
    seen: set[str] = set()
    groups: dict[str, dict[str, Any]] = {}
    hashes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with snapshot_path.open("rb") as handle:
        for record in ijson.items(handle, "results.item"):
            identifier = _require_string(record.get("id"), "result fact id")
            if identifier in seen:
                raise ReleaseLoadError(f"duplicate result fact id {identifier!r}")
            seen.add(identifier)
            if record.get("election_slug") != ELECTION_SLUG:
                raise ReleaseLoadError(f"result fact {identifier!r} has a foreign election slug")
            level = _require_string(record.get("geography_level"), "geography_level")
            source_id = _LEVEL_SOURCE.get(level)
            if source_id is None:
                raise ReleaseLoadError(f"result fact {identifier!r} has an unloadable level")
            source_geography_id = _require_string(record.get("geography_id"), "geography_id")
            mesa_id = record.get("mesa_id")
            if level == "mesa":
                mesa_id = _require_string(mesa_id, "mesa_id")
                place_id = mesa_places.get(mesa_id)
                if place_id is None:
                    raise ReleaseLoadError(f"result fact {identifier!r} names an unknown mesa")
                # The rewrite is only legitimate if the fact really was filed
                # against that mesa's own polling place.
                if place_id != source_geography_id:
                    raise ReleaseLoadError(
                        f"result fact {identifier!r} is filed against a foreign polling place"
                    )
                geography_id = mesa_id
            else:
                if mesa_id is not None:
                    raise ReleaseLoadError(f"result fact {identifier!r} has a stray mesa_id")
                if geographies.get(source_geography_id, ("", ""))[0] != level:
                    raise ReleaseLoadError(
                        f"result fact {identifier!r} does not match its geography level"
                    )
                geography_id = source_geography_id

            provenance = record.get("provenance")
            if not isinstance(provenance, dict):
                raise ReleaseLoadError(f"result fact {identifier!r} has no provenance")
            source_type = _require_string(provenance.get("source_type"), "source_type")
            if _PAIR.get(source_type) != provenance.get("legal_status"):
                raise ReleaseLoadError(f"result fact {identifier!r} has an invalid legal status")
            content_hash = _hex_digest(provenance.get("content_hash"), "provenance content_hash")
            retrieved_at = _timestamp(provenance.get("retrieved_at"), "provenance retrieved_at")

            row: dict[str, Any] = {
                "id": identifier,
                "geography_id": geography_id,
                "source_geography_id": source_geography_id,
                "geography_level": level,
                "mesa_id": mesa_id,
                "source_id": source_id,
                "content_hash": content_hash,
                "retrieved_at": retrieved_at.isoformat(),
            }
            for metric in METRICS:
                value, status = _metric(record.get(metric), f"{identifier} {metric}")
                row[f"{metric}_value"] = value
                row[f"{metric}_status"] = status
            facts.write(row)

            slate = record.get("candidates")
            if not isinstance(slate, list) or not slate:
                raise ReleaseLoadError(f"result fact {identifier!r} has no candidate categories")
            local: set[str] = set()
            for entry in slate:
                if not isinstance(entry, dict):
                    raise ReleaseLoadError(f"result fact {identifier!r} has a malformed category")
                candidate_id = _require_string(entry.get("candidate_id"), "candidate_id")
                if candidate_id not in candidate_names:
                    raise ReleaseLoadError(f"result fact {identifier!r} names an unknown candidate")
                if candidate_id in local:
                    raise ReleaseLoadError(f"result fact {identifier!r} repeats a candidate")
                local.add(candidate_id)
                votes, status = _metric(entry.get("votes"), f"{identifier} {candidate_id}")
                categories.write(
                    {
                        "result_fact_id": identifier,
                        "category_key": f"candidate:{candidate_id}",
                        "category_code": candidate_id,
                        "category_name": candidate_names[candidate_id],
                        "category_kind": CATEGORY_KIND,
                        "votes": votes,
                        "status": status,
                    }
                )
            if local != set(candidate_names):
                raise ReleaseLoadError(f"result fact {identifier!r} has an incomplete slate")

            hashes[source_id].append((identifier, content_hash))
            group = groups.setdefault(
                source_id,
                {
                    "id": source_id,
                    "source_type": source_type,
                    "legal_status": provenance["legal_status"],
                    "parser_version": _require_string(
                        provenance.get("parser_version"), "parser_version"
                    ),
                    "transform_version": _require_string(
                        provenance.get("transform_version"), "transform_version"
                    ),
                    "source_url": _require_string(provenance.get("source_url"), "source_url"),
                    "retrieved_at": retrieved_at,
                    "fact_count": 0,
                },
            )
            for field in ("source_type", "legal_status", "parser_version", "transform_version"):
                if group[field] != provenance.get(field):
                    raise ReleaseLoadError(f"source {source_id!r} mixes incompatible provenance")
            # One source row stands for a whole grain, so its URL is the common
            # prefix of the documents it covers and its retrieval time is the
            # moment the last of them arrived.
            group["source_url"] = _common_prefix(group["source_url"], provenance["source_url"])
            group["retrieved_at"] = max(group["retrieved_at"], retrieved_at)
            group["fact_count"] += 1

    for source_id, group in groups.items():
        group["content_hash"] = _set_digest(hashes[source_id])
        group["retrieved_at"] = group["retrieved_at"].isoformat()
    if set(groups) != set(_LEVEL_SOURCE.values()):
        raise ReleaseLoadError("snapshot does not carry all three published fact grains")
    # The rollup is a pure function of the mesa facts, so its content hash is
    # exactly the digest of the mesa fact set it is computed from.  It is a
    # number this project derived, never a document the Registraduria published.
    mesa_group = groups[SOURCE_MESA]
    groups[SOURCE_ROLLUP] = {
        "id": SOURCE_ROLLUP,
        "source_type": mesa_group["source_type"],
        "legal_status": mesa_group["legal_status"],
        "parser_version": mesa_group["parser_version"],
        "transform_version": ROLLUP_TRANSFORM,
        "source_url": ROLLUP_URL,
        "retrieved_at": mesa_group["retrieved_at"],
        "content_hash": mesa_group["content_hash"],
        "fact_count": 0,
    }
    return groups


def _common_prefix(left: str, right: str) -> str:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    prefix = left[:index]
    if not prefix.startswith("https://"):
        raise ReleaseLoadError("source documents do not share an https origin")
    return prefix


def _scalar(snapshot_path: Path, prefix: str) -> Any:
    with snapshot_path.open("rb") as handle:
        for item in ijson.items(handle, prefix, use_float=True):
            return item
    raise ReleaseLoadError(f"snapshot has no {prefix} block")


def snapshot_to_parquet(
    snapshot_path: Path, output_directory: Path, *, batch_size: int = 20_000
) -> dict[str, Any]:
    """Stream ``api-snapshot.json`` into four Parquet artifacts and a load manifest."""
    if batch_size < 1:
        raise ReleaseLoadError("batch_size must be positive")
    output_directory.mkdir(parents=True, exist_ok=True)

    election = _scalar(snapshot_path, "election")
    if not isinstance(election, dict) or election.get("slug") != ELECTION_SLUG:
        raise ReleaseLoadError("snapshot is not the 2026 second-round election")
    slate = election.get("candidates")
    if not isinstance(slate, list) or len(slate) < 2:
        raise ReleaseLoadError("snapshot election has no candidate slate")
    candidates: list[dict[str, Any]] = []
    candidate_names: dict[str, str] = {}
    ballot_numbers: set[int] = set()
    for entry in slate:
        if not isinstance(entry, dict):
            raise ReleaseLoadError("snapshot election has a malformed candidate slate")
        identifier = _require_string(entry.get("id"), "candidate id")
        if identifier in candidate_names:
            raise ReleaseLoadError("snapshot election repeats a candidate id")
        ballot_number = _require_int(entry.get("ballot_number"), "candidate ballot_number")
        if ballot_number < 1 or ballot_number in ballot_numbers:
            raise ReleaseLoadError("candidate ballot numbers must be distinct positive integers")
        name = entry.get("name") or {}
        short_name = entry.get("short_name") or name
        name_es = _require_string(name.get("es"), "candidate name es")
        name_en = _require_string(name.get("en"), "candidate name en")
        candidate_names[identifier] = name_es
        ballot_numbers.add(ballot_number)
        candidates.append(
            {
                "id": identifier,
                "ballot_number": ballot_number,
                "name_es": name_es,
                "name_en": name_en,
                "short_name_es": _require_string(short_name.get("es"), "candidate short name es"),
                "short_name_en": _require_string(short_name.get("en"), "candidate short name en"),
            }
        )
    release = _scalar(snapshot_path, "release")
    summary = _scalar(snapshot_path, "summary")
    if not isinstance(release, dict) or not isinstance(summary, dict):
        raise ReleaseLoadError("snapshot release/summary blocks are malformed")
    data_version = _require_string(release.get("data_version"), "snapshot data_version")
    if summary.get("data_version") != data_version:
        raise ReleaseLoadError("snapshot summary does not match its release")

    writers = {
        GEOGRAPHY_ARTIFACT: _Writer(
            output_directory / GEOGRAPHY_ARTIFACT, _GEOGRAPHY_SCHEMA, batch_size
        ),
        MESA_ARTIFACT: _Writer(output_directory / MESA_ARTIFACT, _MESA_SCHEMA, batch_size),
        FACT_ARTIFACT: _Writer(output_directory / FACT_ARTIFACT, _FACT_SCHEMA, batch_size),
        CATEGORY_ARTIFACT: _Writer(
            output_directory / CATEGORY_ARTIFACT, _CATEGORY_SCHEMA, batch_size
        ),
    }
    try:
        geographies = _geographies(snapshot_path, writers[GEOGRAPHY_ARTIFACT])
        mesa_places = _mesas(snapshot_path, writers[MESA_ARTIFACT], geographies)
        sources = _results(
            snapshot_path,
            writers[FACT_ARTIFACT],
            writers[CATEGORY_ARTIFACT],
            geographies,
            mesa_places,
            candidate_names,
        )
    finally:
        for writer in writers.values():
            writer.close()

    artifacts = []
    for name, writer in writers.items():
        content_hash, byte_size = _file_digest(output_directory / name)
        artifacts.append(
            {
                "id": name.removesuffix(".parquet"),
                "filename": name,
                "content_hash": content_hash,
                "byte_size": byte_size,
                "record_count": writer.rows,
            }
        )
    snapshot_hash, snapshot_size = _file_digest(snapshot_path)
    if summary.get("completion") is None or summary.get("reconciliation") is None:
        raise ReleaseLoadError("snapshot summary lacks completion/reconciliation")
    load_manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "release_id": _require_string(release.get("release_id"), "snapshot release_id"),
        "data_version": data_version,
        "election_slug": ELECTION_SLUG,
        "election": {
            "name_es": _require_string((election.get("name") or {}).get("es"), "election name es"),
            "name_en": _require_string((election.get("name") or {}).get("en"), "election name en"),
            "round": _require_int(election.get("round"), "election round"),
            "election_date": _require_string(
                election.get("election_date"), "election election_date"
            ),
            "candidates": candidates,
        },
        # Copied verbatim.  ``reconciliation`` is ``blocked`` with three
        # exceptions and must be served as blocked; recomputing any of these
        # from the loaded rows would quietly turn that into a pass.
        "summary": {
            "completion": summary.get("completion"),
            "coverage": summary.get("coverage"),
            "geographic_collection_coverage": summary.get("geographic_collection_coverage"),
            "reconciliation": summary.get("reconciliation"),
            "turnout": summary.get("turnout"),
        },
        "sources": [sources[key] for key in sorted(sources)],
        "artifacts": artifacts,
        "snapshot": {
            "filename": snapshot_path.name,
            "content_hash": snapshot_hash,
            "byte_size": snapshot_size,
        },
    }
    (output_directory / LOAD_MANIFEST).write_text(
        json.dumps(load_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return load_manifest
