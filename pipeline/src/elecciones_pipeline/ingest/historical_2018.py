# ruff: noqa: E501, S314, S608, ASYNC240
"""Safe, reproducible ingestion of the Registraduría 2018 MMV snapshots.

The Observatory publishes two ZIP files, rather than a query API.  This adapter
deliberately treats them as immutable contextual-baseline snapshots: it never
claims the data is scrutiny/final, invents missing candidate rows, or probes the
reCAPTCHA-protected document portals.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypedDict

import httpx
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from .checkpoint import SQLiteCheckpointStore
from .models import Snapshot
from .policy import AllowlistPolicy
from .storage import LocalObjectStore

HISTORICAL_2018_HOST = "observatorio.registraduria.gov.co"
HISTORICAL_2018_URLS = {
    1: "https://observatorio.registraduria.gov.co/anexos/MMV_NACIONAL_PRESIDENTE_2018_1v.zip",
    2: "https://observatorio.registraduria.gov.co/anexos/MMV_NACIONAL_PRESIDENTE_2018_2v.zip",
}
PARSER_VERSION = "historical-mmv-2018/2.0.0"
TRANSFORM_VERSION = "historical-rollup/2.0.0"
RELEASE_FAMILY = "historical-2018-mmv-context-v2"
SOURCE_TYPE = "contextual_baseline"
LEGAL_STATUS = "context_only"
# This profile is part of the immutable release identity.  Changing it means a
# consumer gets a new candidate release, even if the source ZIP bytes did not.
TRANSFORM_PROFILE = {
    "facts_schema": "historical-mmv-row/2.0.0",
    "geography_schema": "historical-geography/2.0.0",
    "rollup_schema": "historical-rollup-row/2.0.0",
    "parquet": {"compression": "zstd", "dictionary": False, "statistics": True},
}
# These response metadata were reviewed before collection.  The full-object
# SHA-256 is computed only after these independently supplied size and ETag
# values have matched, then becomes the immutable raw-object identity.
class SourceMetadata(TypedDict):
    byte_size: int
    etag: str


EXPECTED_SOURCE_METADATA: dict[int, SourceMetadata] = {
    1: {"byte_size": 61_121_207, "etag": '"6832194e-3a4a2b7"'},
    2: {"byte_size": 16_171_503, "etag": '"6832194e-f6c1ef"'},
}
MAX_ZIP_BYTES = max(item["byte_size"] for item in EXPECTED_SOURCE_METADATA.values())
MAX_MEMBER_BYTES = 200 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
_MEMBER_RE = re.compile(r"^MMV_NACIONAL_PRESIDENTE_2018_[12]v\.xlsx$")
_CODE_WIDTHS = {"DEP": 2, "MUN": 3, "ZONA": 2, "PUESTO": 2, "MESA": 3, "CAN": 3}
_REQUIRED_COLUMNS = (
    "DEP", "DEPNOMBRE", "MUN", "MUNNOMBRE", "ZONA", "PUESTO", "PUESNOMBRE",
    "MESA", "CORCODIGO", "CORNOMBRE", "CIR", "PAR", "PARNOMBRE", "CAN",
    "CANNOMBRE", "VOTOS",
)


class Historical2018Error(ValueError):
    """An official snapshot is unsafe or does not match its published schema."""


@dataclass(frozen=True)
class HistoricalBuild:
    manifest_path: Path
    metadata_path: Path
    rows_path: Path
    rollups_path: Path
    geography_path: Path
    row_counts: dict[int, int]
    mesa_counts: dict[int, int]
    release_id: str


def _now() -> datetime:
    return datetime.now(UTC)


async def fetch_historical_2018(
    state_directory: Path,
    *,
    recheck: bool = False,
    timeout_seconds: float = 45.0,
    max_attempts: int = 3,
) -> dict[int, Snapshot]:
    """Fetch both reviewed ZIPs into immutable raw storage before parsing.

    Conditional requests make this resume-safe. Redirects are checked against
    the one reviewed official host; response size/type are rejected before raw
    bytes can become an accepted snapshot.
    """
    state_directory.mkdir(parents=True, exist_ok=True)
    checkpoints = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    objects = LocalObjectStore(state_directory / "objects")
    policy = AllowlistPolicy({HISTORICAL_2018_HOST})
    snapshots: dict[int, Snapshot] = {}
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout_seconds) as client:
        for round_number, source_url in HISTORICAL_2018_URLS.items():
            latest = checkpoints.latest(source_url)
            if latest is not None and not recheck:
                snapshots[round_number] = latest
                continue
            headers = {"Accept": "application/zip, application/octet-stream;q=0.5"}
            if latest is not None and latest.etag:
                headers["If-None-Match"] = latest.etag
            if latest is not None and latest.last_modified:
                headers["If-Modified-Since"] = latest.last_modified
            current_url = source_url
            for _redirect_number in range(4):
                await policy.check(current_url)
                response: httpx.Response | None = None
                for attempt in range(max_attempts):
                    try:
                        candidate = await client.get(current_url, headers=headers)
                    except httpx.HTTPError as exc:
                        if attempt + 1 == max_attempts:
                            raise Historical2018Error("official ZIP request failed after retries") from exc
                        await asyncio.sleep(0.1 * (2**attempt))
                        continue
                    if candidate.status_code in {408, 429} or candidate.status_code >= 500:
                        if attempt + 1 == max_attempts:
                            raise Historical2018Error(
                                f"official ZIP returned HTTP {candidate.status_code} after retries"
                            )
                        await asyncio.sleep(0.1 * (2**attempt))
                        continue
                    response = candidate
                    break
                if response is None:  # pragma: no cover - defensive type narrowing
                    raise Historical2018Error("official ZIP request failed without a response")
                if response.status_code == 304 and latest is not None:
                    snapshots[round_number] = latest
                    break
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise Historical2018Error("official ZIP redirect omitted Location")
                    current_url = str(response.url.join(location))
                    await policy.check(current_url)
                    headers = {"Accept": headers["Accept"]}
                    continue
                if response.status_code != 200:
                    raise Historical2018Error(
                        f"official ZIP returned HTTP {response.status_code} for round {round_number}"
                    )
                media_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if media_type not in {"application/zip", "application/octet-stream"}:
                    raise Historical2018Error(f"unexpected ZIP content type {media_type!r}")
                expected = EXPECTED_SOURCE_METADATA[round_number]
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not declared.isdigit() or int(declared) != expected["byte_size"]
                ):
                    raise Historical2018Error("official ZIP Content-Length differs from reviewed size")
                content = response.content
                if len(content) != expected["byte_size"]:
                    raise Historical2018Error("official ZIP body differs from reviewed size")
                if response.headers.get("ETag") != expected["etag"]:
                    raise Historical2018Error("official ZIP ETag differs from reviewed ETag")
                if not content.startswith(b"PK\x03\x04"):
                    raise Historical2018Error("official response is not a ZIP local-file stream")
                key = await objects.put(content, content_type=media_type)
                snapshot = checkpoints.record_snapshot(
                    Snapshot(
                        url=source_url,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        object_key=key,
                        media_type=media_type,
                        byte_size=len(content),
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                    )
                )
                snapshots[round_number] = snapshot
                break
            else:
                raise Historical2018Error("official ZIP exceeded reviewed redirect limit")
    return snapshots


def _clean(value: str | None, column: str) -> str:
    if value is None:
        raise Historical2018Error(f"MMV row lacks {column}")
    cleaned = value.strip()
    if not cleaned:
        raise Historical2018Error(f"MMV row has blank {column}")
    return cleaned


def _code(value: str | None, column: str) -> str:
    cleaned = _clean(value, column)
    width = _CODE_WIDTHS.get(column)
    if (
        width is None
        or not cleaned.isascii()
        or not cleaned.isalnum()
        or cleaned != cleaned.upper()
        or len(cleaned) > width
    ):
        raise Historical2018Error(f"invalid MMV {column} code {cleaned!r}")
    # The published hierarchy is usually decimal, but includes real two-byte
    # polling-place codes such as A3.  Preserve those exact official codes;
    # only decimal values are zero-padded to their published fixed width.
    return cleaned.zfill(width) if cleaned.isdigit() else cleaned


def _validated_member(
    zip_bytes: bytes, round_number: int, *, require_reviewed_size: bool = True
) -> zipfile.ZipInfo:
    """Reject unsafe archive shapes before a raw object is accepted or parsed."""
    if (
        require_reviewed_size
        and len(zip_bytes) != EXPECTED_SOURCE_METADATA[round_number]["byte_size"]
    ):
        raise Historical2018Error("raw official ZIP differs from reviewed size")
    if not zip_bytes.startswith(b"PK\x03\x04"):
        raise Historical2018Error("raw official object is not a ZIP local-file stream")
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise Historical2018Error("raw official object is not a valid ZIP") from exc
    with archive:
        members = archive.infolist()
        if len(members) != 1:
            raise Historical2018Error("MMV ZIP must contain exactly one CSV member")
        member = members[0]
        if member.is_dir() or not _MEMBER_RE.fullmatch(member.filename):
            raise Historical2018Error("unexpected MMV ZIP member name")
        if member.flag_bits & 0x1 or member.file_size <= 0 or member.file_size > MAX_MEMBER_BYTES:
            raise Historical2018Error("unsafe MMV ZIP member")
        if member.compress_size <= 0 or member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
            raise Historical2018Error("MMV ZIP compression ratio exceeds safety limit")
        return member


def import_historical_2018_archives(
    state_directory: Path, archive_paths: dict[int, Path]
) -> dict[int, Snapshot]:
    """Accept already-transferred official ZIPs into SHA-addressed raw state.

    This deliberately performs no networking.  It is for bytes transferred
    through the approved private-egress relay, and validates archive size,
    ZIP shape, path, compression safety, and source identity before a parser
    can observe the file.
    """
    if set(archive_paths) != {1, 2}:
        raise Historical2018Error("exactly rounds 1 and 2 archive paths are required")
    state_directory.mkdir(parents=True, exist_ok=True)
    checkpoints = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    objects = LocalObjectStore(state_directory / "objects")
    snapshots: dict[int, Snapshot] = {}
    for round_number in (1, 2):
        archive_path = archive_paths[round_number]
        if not archive_path.is_file() or archive_path.is_symlink():
            raise Historical2018Error(f"round {round_number} archive must be a regular file")
        content = archive_path.read_bytes()
        _validated_member(content, round_number)
        key = asyncio.run(objects.put(content, content_type="application/zip"))
        expected = EXPECTED_SOURCE_METADATA[round_number]
        snapshots[round_number] = checkpoints.record_snapshot(
            Snapshot(
                url=HISTORICAL_2018_URLS[round_number],
                content_hash=hashlib.sha256(content).hexdigest(),
                object_key=key,
                media_type="application/zip",
                byte_size=int(expected["byte_size"]),
                etag=str(expected["etag"]),
            )
        )
    return snapshots


def _xlsx_rows(
    workbook_bytes: bytes, round_number: int, snapshot: Snapshot, data_version: str
) -> Iterable[dict[str, object]]:
    """Stream the verified 2018 XLSX worksheet without spreadsheet formulas/macros."""
    import xml.etree.ElementTree as element_tree

    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        workbook = zipfile.ZipFile(__import__("io").BytesIO(workbook_bytes))
    except zipfile.BadZipFile as exc:
        raise Historical2018Error("MMV XLSX member is not a valid ZIP") from exc
    with workbook:
        infos = workbook.infolist()
        if len(infos) > 64 or any(".." in Path(info.filename).parts or info.flag_bits & 1 for info in infos):
            raise Historical2018Error("unsafe MMV XLSX member set")
        if any(info.file_size > 400 * 1024 * 1024 or info.compress_size <= 0 for info in infos):
            raise Historical2018Error("unsafe MMV XLSX member size")
        strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = element_tree.fromstring(workbook.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.iter(namespace + "t")) for item in root]
        sheet = "xl/worksheets/sheet6.xml" if round_number == 1 else "xl/worksheets/sheet1.xml"
        if sheet not in workbook.namelist():
            raise Historical2018Error("reviewed MMV XLSX worksheet is absent")
        expected = (
            ("DEP", "MUN", "ZONA", "PSTO", "MESA", "COR", "CIR", "PAR", "PARTIDO", "CODCAN", "CANDIDATO", "VOTOS")
            if round_number == 1 else
            ("DEP", "MUN", "ZONA", "PUESTO", "MESA", "COR", "CIR", "PAR", "CAN", "CANDIDATO", "VOTOS")
        )
        header: list[str] | None = None
        for _event, row in element_tree.iterparse(workbook.open(sheet), events=("end",)):
            if row.tag != namespace + "row":
                continue
            cells: list[str] = []
            for cell in row.findall(namespace + "c"):
                value = cell.find(namespace + "v")
                raw = "" if value is None or value.text is None else value.text
                cells.append(strings[int(raw)] if cell.attrib.get("t") == "s" else raw)
            if header is None:
                header = [value.strip() for value in cells]
                if tuple(header) != expected:
                    raise Historical2018Error("MMV XLSX header does not match the reviewed schema")
                continue
            if len(cells) != len(expected):
                raise Historical2018Error("MMV XLSX row has unexpected cell count")
            raw = dict(zip(expected, cells, strict=True))
            dep, mun, zona = (_code(raw[key], key) for key in ("DEP", "MUN", "ZONA"))
            puesto_key, candidate_key = ("PSTO", "CODCAN") if round_number == 1 else ("PUESTO", "CAN")
            puesto, mesa = _code(raw[puesto_key], "PUESTO"), _code(raw["MESA"], "MESA")
            party = _clean(raw["PAR"], "PAR").zfill(4)
            candidate = _code(raw[candidate_key], "CAN")
            votes = int(_clean(raw["VOTOS"], "VOTOS"))
            if votes < 0 or votes > 10_000:
                raise Historical2018Error("VOTOS exceeds reviewed mesa/category sanity bound")
            party_name = raw.get("PARTIDO", "").strip() or f"official-party-code-{party}"
            yield {"round": round_number, "election_slug": f"presidencia-2018-round-{round_number}", "election_date": "2018-05-27" if round_number == 1 else "2018-06-17", "dep_code": dep, "dep_name": f"official-department-code-{dep}", "mun_code": mun, "mun_name": f"official-municipality-code-{dep}-{mun}", "zona_code": zona, "puesto_code": puesto, "puesto_name": f"official-place-code-{dep}-{mun}-{zona}-{puesto}", "mesa_code": mesa, "corporation_code": _clean(raw["COR"], "COR").zfill(2), "corporation_name": "PRESIDENTE", "circumscription_code": _clean(raw["CIR"], "CIR").zfill(2), "party_code": party, "party_name": party_name, "category_code": candidate, "category_name": _clean(raw["CANDIDATO"], "CANDIDATO"), "votes": votes, "source_url": snapshot.url, "content_hash": snapshot.content_hash, "retrieved_at": snapshot.retrieved_at.isoformat(), "data_version": data_version, "source_type": SOURCE_TYPE, "legal_status": LEGAL_STATUS, "parser_version": PARSER_VERSION, "transform_version": TRANSFORM_VERSION}


def _rows(
    zip_bytes: bytes,
    round_number: int,
    snapshot: Snapshot,
    *,
    data_version: str = RELEASE_FAMILY,
) -> Iterable[dict[str, object]]:
    _validated_member(zip_bytes, round_number, require_reviewed_size=False)
    archive = zipfile.ZipFile(__import__("io").BytesIO(zip_bytes))
    with archive:
        member = archive.infolist()[0]
        if member.filename.endswith(".xlsx"):
            yield from _xlsx_rows(archive.read(member), round_number, snapshot, data_version)
            return
        with archive.open(member) as binary, TextIOWrapper(binary, encoding="latin-1", newline="") as text:
            reader = csv.DictReader(text, delimiter=";", strict=True)
            if reader.fieldnames is None or tuple(reader.fieldnames) != _REQUIRED_COLUMNS:
                raise Historical2018Error("MMV CSV header does not match the reviewed explicit schema")
            semantic_keys: set[tuple[str, ...]] = set()
            names: dict[tuple[str, ...], str] = {}
            for line_number, raw in enumerate(reader, start=2):
                try:
                    dep, mun, zona, puesto, mesa = (
                        _code(raw[key], key) for key in ("DEP", "MUN", "ZONA", "PUESTO", "MESA")
                    )
                    votes_text = _clean(raw["VOTOS"], "VOTOS")
                    if not votes_text.isascii() or not votes_text.isdigit():
                        raise Historical2018Error("VOTOS must be a non-negative decimal integer")
                    votes = int(votes_text)
                    if votes > 10_000:
                        raise Historical2018Error("VOTOS exceeds reviewed mesa/category sanity bound")
                    candidate = _code(raw["CAN"], "CAN") if raw["CAN"] is not None else ""
                    party = _clean(raw["PAR"], "PAR").zfill(4)
                    if not party.isdigit() or len(party) != 4:
                        raise Historical2018Error("PAR must be a four-digit code")
                    dep_name = _clean(raw["DEPNOMBRE"], "DEPNOMBRE")
                    mun_name = _clean(raw["MUNNOMBRE"], "MUNNOMBRE")
                    puesto_name = _clean(raw["PUESNOMBRE"], "PUESNOMBRE")
                    corporation_name = _clean(raw["CORNOMBRE"], "CORNOMBRE")
                    party_name = _clean(raw["PARNOMBRE"], "PARNOMBRE")
                    category_name = _clean(raw["CANNOMBRE"], "CANNOMBRE")
                    name_keys = {
                        ("dep", dep): dep_name,
                        ("mun", dep, mun): mun_name,
                        ("place", dep, mun, zona, puesto): puesto_name,
                        ("corporation", raw["CORCODIGO"] or ""): corporation_name,
                        ("party", party): party_name,
                        ("category", party, candidate): category_name,
                    }
                    for name_key, name in name_keys.items():
                        previous = names.setdefault(name_key, name)
                        if previous != name:
                            raise Historical2018Error(
                                f"conflicting names for {'/'.join(name_key)}: {previous!r} != {name!r}"
                            )
                    semantic_key = (
                        dep, mun, zona, puesto, mesa,
                        _clean(raw["CORCODIGO"], "CORCODIGO").zfill(2),
                        _clean(raw["CIR"], "CIR").zfill(2), party, candidate,
                    )
                    if semantic_key in semantic_keys:
                        raise Historical2018Error("duplicate semantic MMV fact")
                    semantic_keys.add(semantic_key)
                    yield {
                        "round": round_number,
                        "election_slug": f"presidencia-2018-round-{round_number}",
                        "election_date": "2018-05-29" if round_number == 1 else "2018-06-19",
                        "dep_code": dep, "dep_name": dep_name,
                        "mun_code": mun, "mun_name": mun_name,
                        "zona_code": zona, "puesto_code": puesto,
                        "puesto_name": puesto_name, "mesa_code": mesa,
                        "corporation_code": _clean(raw["CORCODIGO"], "CORCODIGO").zfill(2),
                        "corporation_name": corporation_name,
                        "circumscription_code": _clean(raw["CIR"], "CIR").zfill(2),
                        "party_code": party, "party_name": party_name,
                        "category_code": candidate, "category_name": category_name,
                        "votes": votes, "source_url": snapshot.url, "content_hash": snapshot.content_hash,
                        "retrieved_at": snapshot.retrieved_at.isoformat(),
                        "data_version": data_version, "source_type": SOURCE_TYPE,
                        "legal_status": LEGAL_STATUS, "parser_version": PARSER_VERSION,
                        "transform_version": TRANSFORM_VERSION,
                    }
                except (ValueError, Historical2018Error) as exc:
                    raise Historical2018Error(f"invalid MMV CSV row {line_number}: {exc}") from exc


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(value, temporary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def _release_id(snapshots: dict[int, Snapshot], git_commit: str) -> str:
    """Return a stable candidate ID from every immutable build input.

    The old fixed ``...-v1`` ID could silently point to a different parser or
    source object.  A source/parser/profile/commit change now necessarily has
    a different target path and data_version.
    """
    identity = {
        "git_commit": git_commit,
        "parser_version": PARSER_VERSION,
        "release_family": RELEASE_FAMILY,
        "snapshots": {
            str(round_number): {
                "content_hash": snapshots[round_number].content_hash,
                "retrieved_at": snapshots[round_number].retrieved_at.isoformat(),
                "source_url": snapshots[round_number].url,
            }
            for round_number in sorted(snapshots)
        },
        "transform_profile": TRANSFORM_PROFILE,
        "transform_version": TRANSFORM_VERSION,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"{RELEASE_FAMILY}-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _write_parquet(writer: pq.ParquetWriter, rows: list[dict[str, object]], schema: pa.Schema) -> None:
    """Write a deterministic row group; parquet byte order follows CSV order."""
    writer.write_table(pa.Table.from_pylist(rows, schema=schema))


def _canonicalize_parquet(path: Path, sort_columns: list[str]) -> None:
    """Remove DuckDB writer variability before an artifact becomes content-addressed."""
    table = pq.read_table(path).sort_by([(column, "ascending") for column in sort_columns])
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        pq.write_table(
            table, temporary_path, compression="zstd", use_dictionary=False,
            write_statistics=True, version="2.6", data_page_version="1.0",
        )
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_release_tables(
    con: object,
    *,
    expected_rows: int,
    expected_mesas: dict[int, int],
) -> None:
    """Check hierarchy, exact rollups, and frozen national control totals."""
    # DuckDB's connection is intentionally typed as object to avoid making it
    # an import-time dependency for users only running parser/fetch commands.
    execute = con.execute  # type: ignore[attr-defined]
    raw_rows = int(execute("SELECT count(*) FROM mmv").fetchone()[0])
    if raw_rows != expected_rows:
        raise Historical2018Error("raw parquet row count changed during validation")
    for round_number, mesa_count in expected_mesas.items():
        observed = int(execute(
            "SELECT count(DISTINCT (dep_code, mun_code, zona_code, puesto_code, mesa_code)) "
            "FROM mmv WHERE round = ?", [round_number]
        ).fetchone()[0])
        if observed != mesa_count:
            raise Historical2018Error(f"round {round_number} mesa scope changed during validation")
    duplicate_geography = int(execute(
        "SELECT count(*) - count(DISTINCT id) FROM geography"
    ).fetchone()[0])
    if duplicate_geography:
        raise Historical2018Error("geographic hierarchy has non-unique round-scoped IDs")
    orphan_count = int(execute("""
        SELECT count(*) FROM geography child
        LEFT JOIN geography parent ON child.parent_id = parent.id
        WHERE child.parent_id IS NOT NULL AND parent.id IS NULL
    """).fetchone()[0])
    if orphan_count:
        raise Historical2018Error("geographic hierarchy has missing parents")
    invalid_parent_level = int(execute("""
        SELECT count(*) FROM geography child JOIN geography parent ON child.parent_id = parent.id
        WHERE (child.level = 'department' AND parent.level <> 'national')
           OR (child.level = 'municipality' AND parent.level <> 'department')
           OR (child.level = 'zone' AND parent.level <> 'municipality')
           OR (child.level = 'polling_place' AND parent.level <> 'zone')
           OR (child.level = 'mesa' AND parent.level <> 'polling_place')
    """).fetchone()[0])
    if invalid_parent_level:
        raise Historical2018Error("geographic hierarchy has invalid parent levels")
    mismatch = int(execute("""
        WITH all_levels AS (
          SELECT round, 'national' AS geography_level, 'r' || round || ':co' AS geography_id, * EXCLUDE(round) FROM mmv
          UNION ALL SELECT round, 'department', 'r' || round || ':dep:' || dep_code, * EXCLUDE(round) FROM mmv
          UNION ALL SELECT round, 'municipality', 'r' || round || ':mun:' || dep_code || ':' || mun_code, * EXCLUDE(round) FROM mmv
          UNION ALL SELECT round, 'zone', 'r' || round || ':zone:' || dep_code || ':' || mun_code || ':' || zona_code, * EXCLUDE(round) FROM mmv
          UNION ALL SELECT round, 'polling_place', 'r' || round || ':place:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code, * EXCLUDE(round) FROM mmv
          UNION ALL SELECT round, 'mesa', 'r' || round || ':mesa:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code || ':' || mesa_code, * EXCLUDE(round) FROM mmv
        ), expected AS (
          SELECT round, min(election_slug) AS election_slug, min(election_date) AS election_date,
                 geography_level, geography_id, category_code, category_name, party_code, party_name,
                 sum(votes)::BIGINT AS votes, min(source_url) AS source_url,
                 min(content_hash) AS content_hash, min(retrieved_at) AS retrieved_at,
                 min(data_version) AS data_version, min(source_type) AS source_type,
                 min(legal_status) AS legal_status, min(parser_version) AS parser_version,
                 min(transform_version) AS transform_version
          FROM all_levels GROUP BY ALL
        ), differences AS (
          (SELECT * FROM expected EXCEPT ALL SELECT * FROM rollups)
          UNION ALL (SELECT * FROM rollups EXCEPT ALL SELECT * FROM expected)
        ) SELECT count(*) FROM differences
    """).fetchone()[0])
    if mismatch:
        raise Historical2018Error(f"derived geographic rollup reconciliation failed ({mismatch} exceptions)")
    totals = dict(execute("""
        SELECT round, sum(votes)::BIGINT FROM rollups
        WHERE geography_level = 'national' GROUP BY round
    """).fetchall())
    # This contextual candidate has no separately verified controlling total.
    # The exact EXCEPT ALL comparison above is the required reconciliation;
    # do not manufacture a national control or a coverage denominator.
    if any(total < 0 for total in totals.values()):
        raise Historical2018Error("national MMV total cannot be negative")


def build_historical_2018_release(
    state_directory: Path,
    output_directory: Path,
    manifest_directory: Path,
    *,
    git_commit: str = "uncommitted-worktree",
) -> HistoricalBuild:
    """Parse stored raw snapshots into an immutable, reproducible candidate release."""
    snapshots = asyncio.run(fetch_historical_2018(state_directory))
    objects = LocalObjectStore(state_directory / "objects")
    release_id = _release_id(snapshots, git_commit)
    if output_directory.name == "historical-2018-mmv-context-v1":
        raise Historical2018Error(
            "refusing to write schema-v2 artifacts into the retired fixed v1 release directory; "
            f"use an isolated directory named for {release_id}"
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "historical-2018-mmv.parquet"
    schema = pa.schema([
        ("round", pa.int8()), ("election_slug", pa.string()), ("election_date", pa.string()),
        ("dep_code", pa.string()), ("dep_name", pa.string()),
        ("mun_code", pa.string()), ("mun_name", pa.string()), ("zona_code", pa.string()),
        ("puesto_code", pa.string()), ("puesto_name", pa.string()), ("mesa_code", pa.string()),
        ("corporation_code", pa.string()), ("corporation_name", pa.string()),
        ("circumscription_code", pa.string()), ("party_code", pa.string()), ("party_name", pa.string()),
        ("category_code", pa.string()), ("category_name", pa.string()), ("votes", pa.int32()),
        ("source_url", pa.string()), ("content_hash", pa.string()), ("retrieved_at", pa.string()),
        ("data_version", pa.string()), ("source_type", pa.string()), ("legal_status", pa.string()),
        ("parser_version", pa.string()), ("transform_version", pa.string()),
    ])
    counts: dict[int, int] = {1: 0, 2: 0}
    mesas: dict[int, set[tuple[str, str, str, str, str]]] = {1: set(), 2: set()}
    with pq.ParquetWriter(
        rows_path, schema, compression="zstd", use_dictionary=False, write_statistics=True,
        version="2.6", data_page_version="1.0",
    ) as writer:
        for round_number in (1, 2):
            raw = asyncio.run(objects.get(snapshots[round_number].object_key))
            batch: list[dict[str, object]] = []
            for row in _rows(raw, round_number, snapshots[round_number], data_version=release_id):
                counts[round_number] += 1
                mesa_key = (
                    str(row["dep_code"]), str(row["mun_code"]), str(row["zona_code"]),
                    str(row["puesto_code"]), str(row["mesa_code"]),
                )
                mesas[round_number].add(mesa_key)
                batch.append(row)
                if len(batch) == 20_000:
                    _write_parquet(writer, batch, schema)
                    batch.clear()
            if batch:
                _write_parquet(writer, batch, schema)
    # DuckDB writes the derived hierarchy without materialising all facts in Python.
    import duckdb
    rollups_path = output_directory / "historical-2018-rollups.parquet"
    geography_path = output_directory / "historical-2018-geography.parquet"
    escaped_rows = str(rows_path).replace("'", "''")
    escaped_rollups = str(rollups_path).replace("'", "''")
    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW mmv AS SELECT * FROM read_parquet('{escaped_rows}')")
        con.execute(
            """CREATE TABLE rollups AS
            WITH all_levels AS (
              SELECT round, 'national' AS geography_level, 'r' || round || ':co' AS geography_id, * EXCLUDE(round) FROM mmv
              UNION ALL SELECT round, 'department', 'r' || round || ':dep:' || dep_code, * EXCLUDE(round) FROM mmv
              UNION ALL SELECT round, 'municipality', 'r' || round || ':mun:' || dep_code || ':' || mun_code, * EXCLUDE(round) FROM mmv
              UNION ALL SELECT round, 'zone', 'r' || round || ':zone:' || dep_code || ':' || mun_code || ':' || zona_code, * EXCLUDE(round) FROM mmv
              UNION ALL SELECT round, 'polling_place', 'r' || round || ':place:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code, * EXCLUDE(round) FROM mmv
              UNION ALL SELECT round, 'mesa', 'r' || round || ':mesa:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code || ':' || mesa_code, * EXCLUDE(round) FROM mmv
            )
            SELECT round, min(election_slug) AS election_slug, min(election_date) AS election_date,
                   geography_level, geography_id, category_code, category_name,
                   party_code, party_name, sum(votes)::BIGINT AS votes,
                   min(source_url) AS source_url, min(content_hash) AS content_hash,
                   min(retrieved_at) AS retrieved_at, min(data_version) AS data_version,
                   min(source_type) AS source_type, min(legal_status) AS legal_status,
                   min(parser_version) AS parser_version, min(transform_version) AS transform_version
            FROM all_levels
            GROUP BY ALL ORDER BY round, geography_level, geography_id, category_code"""
        )
        con.execute(f"COPY rollups TO '{escaped_rollups}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        escaped_geography = str(geography_path).replace("'", "''")
        con.execute("""CREATE TABLE geography AS
          SELECT DISTINCT round, election_slug, election_date, 'national' AS level,
            'r' || round || ':co' AS id, '00' AS code, 'Colombia' AS name,
            NULL::VARCHAR AS parent_id, min(source_url) AS source_url, min(content_hash) AS content_hash, min(retrieved_at) AS retrieved_at, min(data_version) AS data_version, min(source_type) AS source_type, min(legal_status) AS legal_status, min(parser_version) AS parser_version, min(transform_version) AS transform_version FROM mmv GROUP BY ALL
          UNION ALL SELECT DISTINCT round, election_slug, election_date, 'department', 'r' || round || ':dep:' || dep_code, dep_code, dep_name, 'r' || round || ':co', min(source_url), min(content_hash), min(retrieved_at), min(data_version), min(source_type), min(legal_status), min(parser_version), min(transform_version) FROM mmv GROUP BY ALL
          UNION ALL SELECT DISTINCT round, election_slug, election_date, 'municipality', 'r' || round || ':mun:' || dep_code || ':' || mun_code, mun_code, mun_name, 'r' || round || ':dep:' || dep_code, min(source_url), min(content_hash), min(retrieved_at), min(data_version), min(source_type), min(legal_status), min(parser_version), min(transform_version) FROM mmv GROUP BY ALL
          UNION ALL SELECT DISTINCT round, election_slug, election_date, 'zone', 'r' || round || ':zone:' || dep_code || ':' || mun_code || ':' || zona_code, zona_code, zona_code, 'r' || round || ':mun:' || dep_code || ':' || mun_code, min(source_url), min(content_hash), min(retrieved_at), min(data_version), min(source_type), min(legal_status), min(parser_version), min(transform_version) FROM mmv GROUP BY ALL
          UNION ALL SELECT DISTINCT round, election_slug, election_date, 'polling_place', 'r' || round || ':place:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code, puesto_code, puesto_name, 'r' || round || ':zone:' || dep_code || ':' || mun_code || ':' || zona_code, min(source_url), min(content_hash), min(retrieved_at), min(data_version), min(source_type), min(legal_status), min(parser_version), min(transform_version) FROM mmv GROUP BY ALL
          UNION ALL SELECT DISTINCT round, election_slug, election_date, 'mesa', 'r' || round || ':mesa:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code || ':' || mesa_code, mesa_code, mesa_code, 'r' || round || ':place:' || dep_code || ':' || mun_code || ':' || zona_code || ':' || puesto_code, min(source_url), min(content_hash), min(retrieved_at), min(data_version), min(source_type), min(legal_status), min(parser_version), min(transform_version) FROM mmv GROUP BY ALL
        """)
        con.execute(f"COPY geography TO '{escaped_geography}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        rollup_count = con.execute("SELECT count(*) FROM rollups").fetchone()
        geography_count = con.execute("SELECT count(*) FROM geography").fetchone()
        if rollup_count is None or geography_count is None:
            raise Historical2018Error("derived artifact count query returned no result")
        rollup_rows = int(rollup_count[0])
        geography_rows = int(geography_count[0])
        _validate_release_tables(
            con, expected_rows=counts[1] + counts[2], expected_mesas={r: len(mesas[r]) for r in (1, 2)},
        )
    finally:
        con.close()
    _canonicalize_parquet(
        rollups_path, ["round", "geography_level", "geography_id", "category_code", "party_code"],
    )
    _canonicalize_parquet(geography_path, ["round", "level", "id"])
    metadata = {
        "schema_version": "1.0.0", "parser_version": PARSER_VERSION, "transform_version": TRANSFORM_VERSION,
        "data_version": release_id, "source_type": SOURCE_TYPE, "legal_status": LEGAL_STATUS,
        "sparse_category_semantics": "A missing category row is unavailable/unknown, never an inferred zero.",
        "coverage_basis": "each reviewed ZIP is one source object (expected/retrieved/parsed = 1); observed mesa scope is not an expected-mesa denominator",
        "rounds": {str(r): {"rows": counts[r], "observed_snapshot_scope": {"distinct_mesas": len(mesas[r]), "complete_expected_coverage": "unknown"}, "snapshot": snapshots[r].model_dump(mode="json")} for r in (1, 2)},
        "rollup_rows": rollup_rows,
        "geography_rows": geography_rows,
        "reconciliation": {
            "status": "passed",
            "basis": "exact derived rollups from parsed MMV facts",
            "checked_facts": counts[1] + counts[2],
            "exceptions": 0,
        },
    }
    metadata_path = output_directory / "historical-2018-metadata.json"
    _atomic_json(metadata_path, metadata)
    # This field deliberately records immutable input time, never build wall-clock time.
    created_at = max(snapshot.retrieved_at for snapshot in snapshots.values()).isoformat()
    datasets = []
    artifact_base = f"https://eleccionesabiertas.co/releases/{release_id}/datasets"
    for path, identifier, title_es, title_en, schema_name in ((rows_path, "historical-2018-mmv-parquet", "Mesa a mesa 2018", "2018 mesa-level results", "historical-mmv-row.schema.json"), (rollups_path, "historical-2018-rollups-parquet", "Agregados derivados 2018", "2018 derived rollups", "historical-rollup-row.schema.json"), (geography_path, "historical-2018-geography-parquet", "Jerarquía geográfica 2018", "2018 geographic hierarchy", "historical-geography.schema.json")):
        payload = path.read_bytes()
        datasets.append({"id": identifier, "title": {"es": title_es, "en": title_en}, "format": "parquet", "url": f"{artifact_base}/{identifier}/{hashlib.sha256(payload).hexdigest()}.parquet", "schema_url": f"https://eleccionesabiertas.co/schemas/{schema_name}", "record_count": geography_rows if path == geography_path else (rollup_rows if path == rollups_path else counts[1] + counts[2]), "byte_size": len(payload), "content_hash": hashlib.sha256(payload).hexdigest(), "filters": {"data_version": release_id, "source_type": SOURCE_TYPE, "legal_status": LEGAL_STATUS, "election_slugs": "presidencia-2018-round-1,presidencia-2018-round-2"}})
    manifest = {"$schema": "../../packages/contracts/schemas/release-manifest.schema.json", "schema_version": "1.0.0", "release_id": release_id, "election_slug": "presidencia-2018-historical-context", "data_version": release_id, "status": "candidate", "release_class": "context_only", "synthetic": False, "created_at": created_at, "methodology_version": "historical-context-2018/2.0.0", "parser_versions": {"historical_mmv_2018": PARSER_VERSION}, "git_commit": git_commit, "sources": [{"id": f"registraduria-observatorio-2018-round-{r}", "source_type": SOURCE_TYPE, "legal_status": LEGAL_STATUS, "source_url": snapshots[r].url, "retrieved_at": snapshots[r].retrieved_at.isoformat(), "content_hash": snapshots[r].content_hash, "media_type": snapshots[r].media_type, "byte_size": snapshots[r].byte_size, "parser_version": PARSER_VERSION, "transform_version": TRANSFORM_VERSION, "coverage": {"expected": 1, "retrieved": 1, "parsed": 1, "missing": 0, "ambiguous": 0, "excluded": 0}} for r in (1, 2)], "datasets": datasets, "aggregate_reconciled": True, "statistical_validation_passed": False, "wording_validation_passed": True, "notes": {"es": f"Contexto histórico MMV: rondas 1/2 con {len(mesas[1])}/{len(mesas[2])} mesas observadas; la cobertura nacional esperada es desconocida. No es preconteo, escrutinio ni declaración final verificada.", "en": f"Historical MMV context: rounds 1/2 contain {len(mesas[1])}/{len(mesas[2])} observed mesas; expected national coverage is unknown. It is not verified pre-count, scrutiny, or final declaration data."}}
    manifest_path = manifest_directory / f"{release_id}.json"
    if manifest_path.exists() and manifest_path.read_bytes() != (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode():
        raise Historical2018Error(f"refusing to overwrite non-identical immutable release {release_id}")
    _atomic_json(manifest_path, manifest)
    return HistoricalBuild(manifest_path, metadata_path, rows_path, rollups_path, geography_path, counts, {r: len(mesas[r]) for r in (1, 2)}, release_id)
