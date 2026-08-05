"""Resumable official pre-count collection with immutable raw provenance.

The crawl is deliberately split into explicit stages.  A mesa stage first
collects every selected polling-place ACT and enumerates child mesa identities
from its published ``mapagan`` list; mesa identifiers are never generated from
the nomenclator's count field.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from elecciones_pipeline.catalog import SourceCatalog

from .checkpoint import SQLiteCheckpointStore
from .http import AsyncOfficialClient, FetchError
from .models import CollectionConfig, Snapshot
from .policy import AllowlistPolicy, PolicyDenied
from .precount import (
    ParsedPrecountAct,
    PrecountPlanEntry,
    PrecountSchemaError,
    enumerate_mesa_act_urls,
    parse_nomenclator,
    parse_precount_act,
    plan_aggregate_act_urls,
)
from .storage import LocalObjectStore

PrecountStage = Literal["national", "aggregates", "places", "mesas"]
Progress = Callable[[str], None]


class PrecountCrawlError(RuntimeError):
    """The reviewed crawl cannot continue without guessing or losing provenance."""


@dataclass(frozen=True)
class StoredJson:
    snapshot: Snapshot
    payload: object
    network_status: str


@dataclass(frozen=True)
class EnumeratedMesa:
    entry: PrecountPlanEntry
    discovered_from_url: str
    discovered_from_hash: str
    discovery_plan_hash: str


@dataclass(frozen=True)
class PrecountCrawlReport:
    schema_version: str
    election_slug: str
    catalog_version: str
    stage: PrecountStage
    plan_id: str
    started_at: str
    completed_at: str
    sample_limited: bool
    expected: int
    planned: int
    retrieved: int
    parsed: int
    missing: int
    ambiguous: int
    excluded: int
    fetched: int
    reused: int
    nomenclator_hash: str
    root_sources: tuple[dict[str, object], ...]
    state_database: str

    @property
    def complete(self) -> bool:
        return self.parsed == self.expected and not self.missing and not self.ambiguous

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported normalized value: {type(value).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PrecountCrawlError("pre-count result entrypoint must be absolute HTTPS")
    return urlunsplit(("https", parsed.hostname, "", "", ""))


_NATIONAL_ACT_PATH = re.compile(r"^/json/ACT/([^/]+)/00\.json$")


def _legacy_election_sigla(national_url: str) -> str:
    """Read a legacy catalog's sigla from its explicit national ACT URL."""
    match = _NATIONAL_ACT_PATH.fullmatch(urlsplit(national_url).path)
    if match is None:
        raise PrecountCrawlError("national_results must be the explicit national ACT URL")
    return match.group(1)


def _legacy_nomenclator_election_id(payload: object) -> str:
    """Safely select the sole published election for older reviewed catalogs."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("amb"), list):
        raise PrecountCrawlError("nomenclator cannot supply a legacy election identifier")
    values = {
        str(item["elec"])
        for item in payload["amb"]
        if isinstance(item, Mapping) and isinstance(item.get("elec"), (str, int))
    }
    if len(values) != 1:
        raise PrecountCrawlError(
            "legacy catalog must publish exactly one nomenclator election identifier"
        )
    return values.pop()


class _CrawlLedger:
    """Incremental normalized crawl state keyed by a deterministic plan id."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL,
                    election_slug TEXT NOT NULL,
                    nomenclator_hash TEXT NOT NULL,
                    expected INTEGER NOT NULL,
                    planned INTEGER NOT NULL,
                    sample_limited INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    plan_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    scope_code TEXT NOT NULL,
                    grain TEXT NOT NULL,
                    parent_scope_code TEXT,
                    discovered_from_url TEXT,
                    discovered_from_hash TEXT,
                    source_hash TEXT,
                    object_key TEXT,
                    retrieved_at TEXT,
                    network_status TEXT NOT NULL,
                    parse_status TEXT NOT NULL,
                    normalized_json TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (plan_id, source_url),
                    FOREIGN KEY (plan_id) REFERENCES plans(id)
                );
                CREATE INDEX IF NOT EXISTS items_plan_status
                    ON items (plan_id, parse_status);
                CREATE TABLE IF NOT EXISTS retryable_responses (
                    source_url TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (source_url, status_code, attempt, observed_at)
                );
                CREATE INDEX IF NOT EXISTS retryable_responses_status
                    ON retryable_responses (status_code, observed_at);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        # The sqlite context manager handles transaction completion only; it
        # leaves the descriptor open.  This ledger is queried and updated per
        # official response, so close each connection deterministically.
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def prepare_plan(
        self,
        *,
        plan_id: str,
        stage: str,
        election_slug: str,
        nomenclator_hash: str,
        expected: int,
        planned: int,
        sample_limited: bool,
    ) -> None:
        values = (
            plan_id,
            stage,
            election_slug,
            nomenclator_hash,
            expected,
            planned,
            int(sample_limited),
            _utc_now(),
        )
        with self._connect() as connection:
            existing = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if existing is not None:
                immutable = (
                    existing["stage"],
                    existing["election_slug"],
                    existing["nomenclator_hash"],
                    existing["expected"],
                    existing["planned"],
                    existing["sample_limited"],
                )
                if immutable != values[1:7]:
                    raise PrecountCrawlError("an existing crawl plan id has different content")
                return
            connection.execute(
                """
                INSERT INTO plans (
                    id, stage, election_slug, nomenclator_hash, expected,
                    planned, sample_limited, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def record(
        self,
        *,
        plan_id: str,
        entry: PrecountPlanEntry,
        network_status: str,
        parse_status: str,
        snapshot: Snapshot | None,
        normalized: Mapping[str, object] | None,
        error: str | None,
        discovered_from_url: str | None,
        discovered_from_hash: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO items (
                    plan_id, source_url, scope_code, grain, parent_scope_code,
                    discovered_from_url, discovered_from_hash, source_hash,
                    object_key, retrieved_at, network_status, parse_status,
                    normalized_json, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id, source_url) DO UPDATE SET
                    scope_code = excluded.scope_code,
                    grain = excluded.grain,
                    parent_scope_code = excluded.parent_scope_code,
                    discovered_from_url = excluded.discovered_from_url,
                    discovered_from_hash = excluded.discovered_from_hash,
                    source_hash = excluded.source_hash,
                    object_key = excluded.object_key,
                    retrieved_at = excluded.retrieved_at,
                    network_status = excluded.network_status,
                    parse_status = excluded.parse_status,
                    normalized_json = excluded.normalized_json,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    plan_id,
                    entry.source_url,
                    entry.scope_code,
                    entry.grain,
                    entry.parent_scope_code,
                    discovered_from_url,
                    discovered_from_hash,
                    snapshot.content_hash if snapshot else None,
                    snapshot.object_key if snapshot else None,
                    snapshot.retrieved_at.isoformat() if snapshot else None,
                    network_status,
                    parse_status,
                    _canonical_json(normalized) if normalized is not None else None,
                    error,
                    _utc_now(),
                ),
            )

    def require_plan(
        self,
        *,
        plan_id: str,
        stage: str,
        election_slug: str,
        nomenclator_hash: str,
        expected: int,
        planned: int,
        sample_limited: bool,
    ) -> None:
        """Fail closed unless this exact immutable plan was previously recorded."""
        with self._connect() as connection:
            existing = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if existing is None:
            raise PrecountCrawlError(
                "retry-nonparsed-only requires an existing matching crawl plan"
            )
        immutable = (
            existing["stage"], existing["election_slug"], existing["nomenclator_hash"],
            existing["expected"], existing["planned"], existing["sample_limited"],
        )
        requested = (stage, election_slug, nomenclator_hash, expected, planned, int(sample_limited))
        if immutable != requested:
            raise PrecountCrawlError("retry-nonparsed-only plan identity differs from stored plan")

    def is_parsed(self, plan_id: str, source_url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT parse_status FROM items WHERE plan_id = ? AND source_url = ?",
                (plan_id, source_url),
            ).fetchone()
        return row is not None and row["parse_status"] == "parsed"

    def record_retryable_response(self, source_url: str, status_code: int, attempt: int) -> None:
        """Persist a raw retryable response even if a later retry succeeds.

        The terminal ``items`` row intentionally represents coverage, so it
        cannot expose a transient 5xx that was recovered.  This small
        append-only audit table supplies the rate-ramp circuit breaker with
        that missing observation without storing successful responses.
        """
        if status_code not in {408, 429} and not 500 <= status_code < 600:
            return
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO retryable_responses (
                    source_url, status_code, attempt, observed_at
                ) VALUES (?, ?, ?, ?)""",
                (source_url, status_code, attempt, _utc_now()),
            )

    def counts(self, plan_id: str, *, expected: int) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT parse_status, network_status, COUNT(*) AS count
                FROM items
                WHERE plan_id = ?
                GROUP BY parse_status, network_status
                """,
                (plan_id,),
            ).fetchall()
        parsed = sum(row["count"] for row in rows if row["parse_status"] == "parsed")
        ambiguous = sum(row["count"] for row in rows if row["parse_status"] == "ambiguous")
        retrieved = sum(
            row["count"] for row in rows if row["parse_status"] in {"parsed", "ambiguous"}
        )
        fetched = sum(row["count"] for row in rows if row["network_status"] == "fetched")
        reused = sum(row["count"] for row in rows if row["network_status"] == "reused")
        missing = expected - parsed - ambiguous
        if missing < 0:
            raise PrecountCrawlError("crawl terminal counts exceed the expected source count")
        return {
            "retrieved": retrieved,
            "parsed": parsed,
            "missing": missing,
            "ambiguous": ambiguous,
            "excluded": 0,
            "fetched": fetched,
            "reused": reused,
        }

    def requires_refetch(self, plan_id: str, source_url: str) -> bool:
        """Retry only raw-backed rows that did not reach a parsed terminal state."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT parse_status FROM items WHERE plan_id = ? AND source_url = ?",
                (plan_id, source_url),
            ).fetchone()
        return row is not None and row["parse_status"] != "parsed"


async def _stored_json(
    client: AsyncOfficialClient,
    url: str,
    *,
    refresh: bool,
    unconditional: bool = False,
) -> StoredJson:
    latest = client.checkpoints.latest(url)
    if latest is not None and not refresh and await client.store.exists(latest.object_key):
        snapshot = latest
        status = "reused"
    else:
        result = await client.fetch(url, conditional=not unconditional)
        if result.snapshot is None:
            raise PrecountCrawlError(f"fetch retained no snapshot for {url}")
        snapshot = result.snapshot
        status = result.status

    # A malformed response is immutable evidence, not an input to repair.
    # Keep it, then make bounded fresh unconditional attempts: a validator or
    # 304 must never lock a framing-corrupted response into crawl coverage.
    last_decode_error: UnicodeDecodeError | json.JSONDecodeError | None = None
    for attempt in range(client.config.max_attempts):
        raw = await client.store.get(snapshot.object_key)
        try:
            payload = json.loads(raw)
            return StoredJson(snapshot=snapshot, payload=payload, network_status=status)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_decode_error = exc
        if attempt + 1 == client.config.max_attempts:
            break
        result = await client.fetch(url, conditional=False)
        if result.snapshot is None:
            raise PrecountCrawlError(f"fetch retained no snapshot for {url}")
        snapshot = result.snapshot
        status = result.status
    assert last_decode_error is not None
    raise PrecountCrawlError(f"official JSON could not be decoded for {url}") from last_decode_error


def _normalized(parsed: ParsedPrecountAct, snapshot: Snapshot) -> dict[str, object]:
    return {
        **asdict(parsed),
        "provenance": {
            "source_type": "pre_count",
            "legal_status": "preliminary",
            "source_url": snapshot.url,
            "retrieved_at": snapshot.retrieved_at.astimezone(UTC).isoformat(),
            "content_hash": snapshot.content_hash,
            "object_key": snapshot.object_key,
            "parser_version": "registraduria-precount-act@1.0.0",
            "transform_version": "precount-normalized@1.0.0",
        },
    }


def _plan_id(
    *,
    stage: str,
    nomenclator_hash: str,
    expected: int,
    entries: Sequence[EnumeratedMesa | PrecountPlanEntry],
) -> str:
    plan_rows = []
    for item in entries:
        if isinstance(item, EnumeratedMesa):
            plan_rows.append(
                {
                    **asdict(item.entry),
                    "discovered_from_url": item.discovered_from_url,
                    # Preserve the original plan identity across a recovered
                    # place response. The ledger provenance below continues to
                    # record the exact hash that supplied this enumeration.
                    "discovered_from_hash": item.discovery_plan_hash,
                }
            )
        else:
            plan_rows.append(asdict(item))
    digest = hashlib.sha256(
        _canonical_json(
            {
                "stage": stage,
                "nomenclator_hash": nomenclator_hash,
                "expected": expected,
                "entries": plan_rows,
            }
        ).encode()
    ).hexdigest()
    return f"precount-{stage}-{digest[:16]}"


async def _collect(
    *,
    client: AsyncOfficialClient,
    ledger: _CrawlLedger,
    plan_id: str,
    entries: Sequence[EnumeratedMesa | PrecountPlanEntry],
    refresh_existing: bool,
    retry_nonparsed_only: bool,
    reviewed_origin: str,
    progress: Progress | None,
) -> None:
    queue: asyncio.Queue[EnumeratedMesa | PrecountPlanEntry | None] = asyncio.Queue(maxsize=64)
    completed = 0
    selected_entries = tuple(
        item
        for item in entries
        if not retry_nonparsed_only
        or not ledger.is_parsed(
            plan_id, item.entry.source_url if isinstance(item, EnumeratedMesa) else item.source_url
        )
    )
    total = len(selected_entries)

    async def worker() -> None:
        nonlocal completed
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                return
            entry = item.entry if isinstance(item, EnumeratedMesa) else item
            discovery_url = item.discovered_from_url if isinstance(item, EnumeratedMesa) else None
            discovery_hash = item.discovered_from_hash if isinstance(item, EnumeratedMesa) else None
            try:
                stored = await _stored_json(
                    client,
                    entry.source_url,
                    refresh=refresh_existing
                    or ledger.requires_refetch(plan_id, entry.source_url),
                    unconditional=ledger.requires_refetch(plan_id, entry.source_url),
                )
                parsed = parse_precount_act(
                    stored.payload,
                    expected=entry,
                    reviewed_origin=reviewed_origin,
                )
                ledger.record(
                    plan_id=plan_id,
                    entry=entry,
                    network_status=stored.network_status,
                    parse_status="parsed",
                    snapshot=stored.snapshot,
                    normalized=_normalized(parsed, stored.snapshot),
                    error=None,
                    discovered_from_url=discovery_url,
                    discovered_from_hash=discovery_hash,
                )
            except (FetchError, PolicyDenied) as exc:
                ledger.record(
                    plan_id=plan_id,
                    entry=entry,
                    network_status="failed",
                    parse_status="missing",
                    snapshot=None,
                    normalized=None,
                    error=str(exc),
                    discovered_from_url=discovery_url,
                    discovered_from_hash=discovery_hash,
                )
            except (PrecountCrawlError, PrecountSchemaError) as exc:
                latest = client.checkpoints.latest(entry.source_url)
                ledger.record(
                    plan_id=plan_id,
                    entry=entry,
                    network_status="reused" if latest is not None else "failed",
                    parse_status="ambiguous" if latest is not None else "missing",
                    snapshot=latest,
                    normalized=None,
                    error=str(exc),
                    discovered_from_url=discovery_url,
                    discovered_from_hash=discovery_hash,
                )
            finally:
                completed += 1
                if progress is not None and (completed == total or completed % 250 == 0):
                    progress(f"{plan_id}: {completed}/{total}")
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(2)]
    for entry in selected_entries:
        await queue.put(entry)
    for _ in workers:
        await queue.put(None)
    await queue.join()
    await asyncio.gather(*workers)


def _limit_entries[T](entries: Sequence[T], limit: int | None) -> tuple[T, ...]:
    if limit is None:
        return tuple(entries)
    if limit < 1:
        raise PrecountCrawlError("limit must be a positive integer")
    return tuple(entries[:limit])


async def crawl_precount(
    catalog: SourceCatalog,
    state_directory: Path,
    *,
    stage: PrecountStage,
    requests_per_second: float = 5.0,
    refresh_existing: bool = False,
    retry_nonparsed_only: bool = False,
    limit: int | None = None,
    progress: Progress | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> PrecountCrawlReport:
    """Collect one explicit pre-count stage and persist normalized results.

    ``limit`` creates a clearly labelled sample plan for smoke testing.  It is
    never interpreted as full source coverage.
    """
    if stage not in {"national", "aggregates", "places", "mesas"}:
        raise PrecountCrawlError(f"unsupported pre-count stage: {stage}")
    if retry_nonparsed_only and refresh_existing:
        raise PrecountCrawlError("retry-nonparsed-only cannot be combined with refresh-existing")
    started_at = _utc_now()
    await asyncio.to_thread(state_directory.mkdir, parents=True, exist_ok=True)
    store = LocalObjectStore(state_directory / "objects")
    checkpoints = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    ledger = _CrawlLedger(state_directory / "crawl.sqlite3")
    policy = AllowlistPolicy(set(catalog.allowed_hosts))
    config = CollectionConfig(
        requests_per_second=requests_per_second,
        per_host_concurrency=catalog.collection_policy.maximum_concurrency_per_host,
    )
    source = catalog.precount_source()
    entrypoints = catalog.precount_entrypoints()
    election_id = source.election_id
    election_sigla = source.election_sigla
    root_sources: list[dict[str, object]] = []

    async with AsyncOfficialClient(
        store,
        checkpoints,
        policy,
        config,
        client=http_client,
        on_response=ledger.record_retryable_response,
    ) as client:
        roots: dict[str, StoredJson] = {}
        for identifier, url in entrypoints.items():
            stored = await _stored_json(client, url, refresh=True)
            roots[identifier] = stored
            root_sources.append(
                {
                    "id": identifier,
                    "source_url": url,
                    "content_hash": stored.snapshot.content_hash,
                    "retrieved_at": stored.snapshot.retrieved_at.astimezone(UTC).isoformat(),
                    "byte_size": stored.snapshot.byte_size,
                    "media_type": stored.snapshot.media_type,
                    "network_status": stored.network_status,
                }
            )
        try:
            config_payload = roots["precount_configuration"].payload
            if not isinstance(config_payload, Mapping) or not config_payload:
                raise PrecountCrawlError("pre-count configuration is empty or invalid")
            nomenclator_payload = roots["precount_nomenclator"].payload
            if election_id is None:
                election_id = _legacy_nomenclator_election_id(nomenclator_payload)
            nomenclator = parse_nomenclator(nomenclator_payload, election_id=election_id)
        except PrecountSchemaError as exc:
            raise PrecountCrawlError(f"a required official root failed validation: {exc}") from exc

        national_url = source.entrypoints.get("national_results")
        if national_url is None:
            raise PrecountCrawlError("catalog lacks the reviewed national-results entrypoint")
        if election_sigla is None:
            election_sigla = _legacy_election_sigla(national_url)
        assert election_sigla is not None
        aggregate_plan = plan_aggregate_act_urls(_origin(national_url), election_sigla, nomenclator)
        by_code = {scope.code: scope for scope in nomenclator.scopes}
        nomenclator_hash = roots["precount_nomenclator"].snapshot.content_hash

        if stage == "national":
            selected: tuple[PrecountPlanEntry, ...] = tuple(
                entry for entry in aggregate_plan if entry.grain == "national"
            )
            expected = len(selected)
            selected = _limit_entries(selected, limit)
            plan_entries: tuple[EnumeratedMesa | PrecountPlanEntry, ...] = selected
        elif stage == "aggregates":
            # These are direct ACT observations at the exact nomenclator
            # scopes.  Although a polling-place ACT is an aggregate relative
            # to mesas, this stage never turns any aggregate into mesa data.
            selected = _limit_entries(aggregate_plan, limit)
            expected = len(selected)
            plan_entries = selected
        elif stage == "places":
            selected = tuple(entry for entry in aggregate_plan if entry.grain == "polling_place")
            selected = _limit_entries(selected, limit)
            expected = len(selected)
            plan_entries = selected
        else:
            place_entries = tuple(
                entry for entry in aggregate_plan if entry.grain == "polling_place"
            )
            selected_places = _limit_entries(place_entries, limit)
            place_plan_id = _plan_id(
                stage="places",
                nomenclator_hash=nomenclator_hash,
                expected=len(selected_places),
                entries=selected_places,
            )
            if retry_nonparsed_only:
                ledger.require_plan(
                    plan_id=place_plan_id,
                    stage="places",
                    election_slug=catalog.election_slug,
                    nomenclator_hash=nomenclator_hash,
                    expected=len(selected_places),
                    planned=len(selected_places),
                    sample_limited=limit is not None,
                )
            else:
                ledger.prepare_plan(
                    plan_id=place_plan_id,
                    stage="places",
                    election_slug=catalog.election_slug,
                    nomenclator_hash=nomenclator_hash,
                    expected=len(selected_places),
                    planned=len(selected_places),
                    sample_limited=limit is not None,
                )
            enumerated: list[EnumeratedMesa] = []
            for position, entry in enumerate(selected_places, start=1):
                place_was_parsed = retry_nonparsed_only and ledger.is_parsed(
                    place_plan_id, entry.source_url
                )
                try:
                    stored = await _stored_json(
                        client,
                        entry.source_url,
                        refresh=refresh_existing
                        or ledger.requires_refetch(place_plan_id, entry.source_url),
                        unconditional=ledger.requires_refetch(place_plan_id, entry.source_url),
                    )
                    parsed = parse_precount_act(
                        stored.payload,
                        expected=entry,
                        reviewed_origin=_origin(national_url),
                    )
                    scope = by_code[entry.scope_code]
                    mesa_entries = enumerate_mesa_act_urls(
                        _origin(national_url), election_sigla, scope, stored.payload
                    )
                    enumerated.extend(
                        EnumeratedMesa(
                            child,
                            discovered_from_url=entry.source_url,
                            discovered_from_hash=stored.snapshot.content_hash,
                            discovery_plan_hash=client.checkpoints.snapshots(entry.source_url)[
                                0
                            ].content_hash,
                        )
                        for child in mesa_entries
                    )
                    if not place_was_parsed:
                        ledger.record(
                            plan_id=place_plan_id,
                            entry=entry,
                            network_status=stored.network_status,
                            parse_status="parsed",
                            snapshot=stored.snapshot,
                            normalized=_normalized(parsed, stored.snapshot),
                            error=None,
                            discovered_from_url=None,
                            discovered_from_hash=None,
                        )
                except (FetchError, PolicyDenied) as exc:
                    ledger.record(
                        plan_id=place_plan_id,
                        entry=entry,
                        network_status="failed",
                        parse_status="missing",
                        snapshot=None,
                        normalized=None,
                        error=str(exc),
                        discovered_from_url=None,
                        discovered_from_hash=None,
                    )
                except (PrecountCrawlError, PrecountSchemaError) as exc:
                    latest = client.checkpoints.latest(entry.source_url)
                    ledger.record(
                        plan_id=place_plan_id,
                        entry=entry,
                        network_status="reused" if latest else "failed",
                        parse_status="ambiguous" if latest else "missing",
                        snapshot=latest,
                        normalized=None,
                        error=str(exc),
                        discovered_from_url=None,
                        discovered_from_hash=None,
                    )
                if progress is not None and (
                    position == len(selected_places) or position % 250 == 0
                ):
                    progress(f"{place_plan_id}: {position}/{len(selected_places)}")

            seen: dict[str, EnumeratedMesa] = {}
            for item in enumerated:
                previous = seen.get(item.entry.scope_code)
                if previous is not None and previous != item:
                    raise PrecountCrawlError(
                        f"mesa {item.entry.scope_code} was enumerated by conflicting places"
                    )
                seen[item.entry.scope_code] = item
            mesa_plan_entries: tuple[EnumeratedMesa, ...] = tuple(
                sorted(seen.values(), key=lambda item: item.entry.scope_code)
            )
            plan_entries = mesa_plan_entries
            expected = sum(by_code[entry.scope_code].mesa_count for entry in selected_places)

        plan_id = _plan_id(
            stage=stage,
            nomenclator_hash=nomenclator_hash,
            expected=expected,
            entries=plan_entries,
        )
        if retry_nonparsed_only:
            ledger.require_plan(
                plan_id=plan_id,
                stage=stage,
                election_slug=catalog.election_slug,
                nomenclator_hash=nomenclator_hash,
                expected=expected,
                planned=len(plan_entries),
                sample_limited=limit is not None,
            )
        else:
            ledger.prepare_plan(
                plan_id=plan_id,
                stage=stage,
                election_slug=catalog.election_slug,
                nomenclator_hash=nomenclator_hash,
                expected=expected,
                planned=len(plan_entries),
                sample_limited=limit is not None,
            )
        await _collect(
            client=client,
            ledger=ledger,
            plan_id=plan_id,
            entries=plan_entries,
            refresh_existing=refresh_existing,
            retry_nonparsed_only=retry_nonparsed_only,
            reviewed_origin=_origin(national_url),
            progress=progress,
        )

    counts = ledger.counts(plan_id, expected=expected)
    report = PrecountCrawlReport(
        schema_version="1.0.0",
        election_slug=catalog.election_slug,
        catalog_version=catalog.catalog_version,
        stage=stage,
        plan_id=plan_id,
        started_at=started_at,
        completed_at=_utc_now(),
        sample_limited=limit is not None,
        expected=expected,
        planned=len(plan_entries),
        retrieved=counts["retrieved"],
        parsed=counts["parsed"],
        missing=counts["missing"],
        ambiguous=counts["ambiguous"],
        excluded=counts["excluded"],
        fetched=counts["fetched"],
        reused=counts["reused"],
        nomenclator_hash=nomenclator_hash,
        root_sources=tuple(root_sources),
        state_database=str(ledger.path),
    )
    reports = state_directory / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    encoded = f"{report.to_json()}\n"
    report_digest = hashlib.sha256(encoded.encode()).hexdigest()
    report_path = reports / f"{plan_id}-{report_digest[:16]}.json"
    if not report_path.exists():
        report_path.write_text(encoded, encoding="utf-8")
    return report


__all__ = [
    "PrecountCrawlError",
    "PrecountCrawlReport",
    "PrecountStage",
    "crawl_precount",
]
