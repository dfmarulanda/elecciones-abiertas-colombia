"""Raw-only, resumable crawl of a catalog-declared Registraduría scrutiny manifest.

This module deliberately stores and classifies JSON transport objects.  It has
no vote parser and never discovers links from a payload.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from elecciones_pipeline.catalog import SourceCatalog, load_source_catalog

from .checkpoint import SQLiteCheckpointStore
from .models import CollectionConfig, QuarantineRecord, Snapshot
from .scrutiny import ScrutinyPlanEntry, plan_scrutiny_manifest
from .storage import LocalObjectStore

MAX_JSON_BYTES = 10_000_000
PARSER_VERSION = "none@1"  # A raw crawl must never become an implicit vote parser.


class ScrutinyCrawlError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScrutinyCrawlReport:
    plan_id: str
    expected: int
    retrieved: int
    parsed: int
    unclassified: int
    missing: int
    quarantined: int
    categories: dict[str, dict[str, int]]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _plan_id(index_hash: str, entries: tuple[ScrutinyPlanEntry, ...]) -> str:
    material = "\n".join(f"{e.category}\t{e.source_path}\t{e.source_url}" for e in entries)
    return "scrutiny-" + hashlib.sha256((index_hash + "\n" + material).encode()).hexdigest()[:16]


class _Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.executescript("""PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, index_hash TEXT NOT NULL,
                entries_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                plan_id TEXT NOT NULL, source_url TEXT NOT NULL,
                source_path TEXT NOT NULL, category TEXT NOT NULL,
                state TEXT NOT NULL, json_state TEXT, snapshot_hash TEXT,
                reason TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(plan_id,source_url)
            );""")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        # sqlite's context manager finalizes the transaction but deliberately
        # keeps the connection open.  Raw crawls issue one ledger operation per
        # item, so do not defer those descriptors to cyclic GC.
        try:
            with c:
                yield c
        finally:
            c.close()

    def prepare(
        self, plan_id: str, index_hash: str, entries: tuple[ScrutinyPlanEntry, ...]
    ) -> None:
        immutable = json.dumps([asdict(x) for x in entries], sort_keys=True, separators=(",", ":"))
        with self._connect() as c:
            existing = c.execute(
                "SELECT index_hash,entries_json FROM plans WHERE id=?", (plan_id,)
            ).fetchone()
            if existing and (
                existing["index_hash"] != index_hash or existing["entries_json"] != immutable
            ):
                raise ScrutinyCrawlError("existing plan is not immutable")
            if not existing:
                c.execute(
                    "INSERT INTO plans VALUES (?,?,?,?)", (plan_id, index_hash, immutable, _now())
                )
            for e in entries:
                c.execute(
                    "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        plan_id,
                        e.source_url,
                        e.source_path,
                        e.category,
                        "pending",
                        None,
                        None,
                        None,
                        _now(),
                    ),
                )

    def pending(self, plan_id: str) -> tuple[sqlite3.Row, ...]:
        with self._connect() as c:
            return tuple(
                c.execute(
                    "SELECT * FROM items WHERE plan_id=? "
                    "AND state NOT IN ('retrieved','unclassified') ORDER BY source_path",
                    (plan_id,),
                )
            )

    def record(
        self,
        plan_id: str,
        entry: ScrutinyPlanEntry,
        state: str,
        json_state: str | None = None,
        snapshot_hash: str | None = None,
        reason: str | None = None,
    ) -> None:
        with self._connect() as c:
            c.execute(
                "UPDATE items SET state=?,json_state=?,snapshot_hash=?,reason=?,updated_at=? "
                "WHERE plan_id=? AND source_url=?",
                (state, json_state, snapshot_hash, reason, _now(), plan_id, entry.source_url),
            )

    def report(self, plan_id: str) -> ScrutinyCrawlReport:
        with self._connect() as c:
            rows = c.execute(
                "SELECT category,state,json_state FROM items WHERE plan_id=?", (plan_id,)
            ).fetchall()
        cats: dict[str, dict[str, int]] = {}
        for r in rows:
            d = cats.setdefault(
                r["category"],
                {
                    "expected": 0,
                    "retrieved": 0,
                    "parsed": 0,
                    "unclassified": 0,
                    "missing": 0,
                    "quarantined": 0,
                },
            )
            d["expected"] += 1
            if r["state"] in {"retrieved", "unclassified"}:
                d["retrieved"] += 1
            if r["state"] == "unclassified":
                d["unclassified"] += 1
            if r["state"] == "quarantined":
                d["quarantined"] += 1
            if r["state"] == "pending":
                d["missing"] += 1
        total = {
            k: sum(x[k] for x in cats.values())
            for k in ("expected", "retrieved", "parsed", "unclassified", "missing", "quarantined")
        }
        return ScrutinyCrawlReport(plan_id=plan_id, categories=cats, **total)


class _RawClient:
    """Strict one-at-a-time JSON GET; no redirects and no payload URL following."""

    def __init__(
        self,
        store: LocalObjectStore,
        checkpoints: SQLiteCheckpointStore,
        host: str,
        config: CollectionConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.store, self.checkpoints, self.host, self.config = store, checkpoints, host, config
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=config.timeout_seconds,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self.owns = client is None
        self.next_at = 0.0

    async def close(self) -> None:
        if self.owns:
            await self.client.aclose()

    async def fetch(self, url: str) -> tuple[str, Snapshot | None, str | None]:
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname != self.host or p.query or p.fragment:
            raise ScrutinyCrawlError("planned URL violates exact official host/path policy")
        latest = self.checkpoints.latest(url)
        headers = {"Accept": "application/json"}
        if latest and latest.etag:
            headers["If-None-Match"] = latest.etag
        if latest and latest.last_modified:
            headers["If-Modified-Since"] = latest.last_modified
        for attempt in range(1, self.config.max_attempts + 1):
            delay = max(0, self.next_at - asyncio.get_running_loop().time())
            if delay:
                await asyncio.sleep(delay)
            self.next_at = asyncio.get_running_loop().time() + 1 / self.config.requests_per_second
            try:
                r = await self.client.get(url, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                if attempt == self.config.max_attempts:
                    raise ScrutinyCrawlError(type(exc).__name__) from exc
                await asyncio.sleep(
                    min(
                        self.config.retry_max_seconds,
                        self.config.retry_base_seconds * 2 ** (attempt - 1),
                    )
                    * (0.5 + secrets.SystemRandom().random() / 2)
                )
                continue
            if r.status_code == 304 and latest:
                return "not_modified", latest, None
            if r.is_redirect:
                raise ScrutinyCrawlError("redirect rejected")
            if r.status_code in {408, 429} or r.status_code >= 500:
                if attempt < self.config.max_attempts:
                    retry = (
                        float(r.headers.get("Retry-After", "0") or 0)
                        if r.headers.get("Retry-After", "").isdigit()
                        else 0
                    )
                    await asyncio.sleep(
                        max(
                            retry,
                            min(
                                self.config.retry_max_seconds,
                                self.config.retry_base_seconds * 2 ** (attempt - 1),
                            ),
                        )
                        * (0.5 + secrets.SystemRandom().random() / 2)
                    )
                    continue
                raise ScrutinyCrawlError(f"HTTP {r.status_code}")
            if not 200 <= r.status_code < 300:
                raise ScrutinyCrawlError(f"HTTP {r.status_code}")
            media = r.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if media not in {"application/json", "application/problem+json"}:
                raise ScrutinyCrawlError("non-JSON Content-Type")
            if len(r.content) > MAX_JSON_BYTES:
                raise ScrutinyCrawlError("JSON exceeds size limit")
            key = await self.store.put(r.content, content_type=media)
            snapshot = Snapshot(
                url=url,
                content_hash=hashlib.sha256(r.content).hexdigest(),
                object_key=key,
                media_type=media,
                byte_size=len(r.content),
                etag=r.headers.get("ETag"),
                last_modified=r.headers.get("Last-Modified"),
            )
            return "fetched", self.checkpoints.record_snapshot(snapshot), None
        raise AssertionError("unreachable")


async def crawl_scrutiny(
    catalog: SourceCatalog,
    state_directory: Path,
    *,
    refresh_existing: bool = False,
    http_client: httpx.AsyncClient | None = None,
) -> ScrutinyCrawlReport:
    """Fetch index first, then only exact manifest entries. Valid JSON is unclassified."""
    await asyncio.to_thread(state_directory.mkdir, parents=True, exist_ok=True)
    # Resolve through the reviewed role, never through a round-specific source
    # identifier. This keeps the same strict raw-only behavior for each catalog
    # that explicitly declares a structured scrutiny manifest.
    url = catalog.manifest_entrypoints().get("scrutiny_manifest")
    if url is None:
        raise ScrutinyCrawlError("catalog does not declare a structured scrutiny manifest")
    host = urlsplit(url).hostname
    assert host
    store = LocalObjectStore(state_directory / "objects")
    checkpoints = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    config = CollectionConfig(
        requests_per_second=catalog.collection_policy.requests_per_second_minimum,
        per_host_concurrency=1,
    )
    raw = _RawClient(store, checkpoints, host, config, http_client)
    try:
        # Always conditionally fetch the index before trusting any persisted plan.
        _, index_snapshot, _ = await raw.fetch(url)
        assert index_snapshot
        index = json.loads(await store.get(index_snapshot.object_key))
        entries = plan_scrutiny_manifest(f"https://{host}/", index)
        plan_id = _plan_id(index_snapshot.content_hash, entries)
        ledger = _Ledger(state_directory / "scrutiny.sqlite3")
        ledger.prepare(plan_id, index_snapshot.content_hash, entries)
        known = {e.source_url: e for e in entries}
        for row in ledger.pending(plan_id):
            entry = known[row["source_url"]]
            try:
                status, snapshot, _ = await raw.fetch(entry.source_url)
                assert snapshot
                try:
                    json.loads(await store.get(snapshot.object_key))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    ledger.record(
                        plan_id,
                        entry,
                        "quarantined",
                        "invalid_json",
                        snapshot.content_hash,
                        type(exc).__name__,
                    )
                else:
                    ledger.record(
                        plan_id, entry, "unclassified", "valid_json", snapshot.content_hash
                    )
            except (ScrutinyCrawlError, httpx.HTTPError) as exc:
                checkpoints.quarantine(
                    QuarantineRecord(url=entry.source_url, reason=str(exc), attempts=1)
                )
                ledger.record(plan_id, entry, "quarantined", reason=str(exc))
        return ledger.report(plan_id)
    finally:
        await raw.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog", type=Path, default=Path("config/sources/presidencia-2026-segunda-vuelta.json")
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asdict(asyncio.run(crawl_scrutiny(load_source_catalog(args.catalog), args.state_dir))),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
