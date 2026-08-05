"""Nondestructive gate for resuming a local crawl through the private relay."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .checkpoint import SQLiteCheckpointStore
from .http import AsyncOfficialClient
from .models import CollectionConfig, QuarantineRecord
from .policy import AllowlistPolicy
from .relay_transport import PrecountRelayTransport, load_relay_token
from .storage import LocalObjectStore

_HOSTS = {
    1: "resultadosprecpresidente2026-1v.registraduria.gov.co",
    2: "resultadosprecpresidente2026-2v.registraduria.gov.co",
}


class RelaySmokeError(RuntimeError):
    """The relay did not preserve local crawl invariants."""


@dataclass(frozen=True)
class RelaySmokeReport:
    round_number: int
    completed_checked: int
    completed_not_modified: int
    completed_same_hash: int
    retryable_source_url: str
    retryable_content_hash: str
    quarantine_unchanged: bool
    provenance_urls_official: bool
    crawl_started: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def _selected_urls(state_directory: Path, round_number: int, count: int) -> tuple[list[str], str]:
    if round_number not in _HOSTS:
        raise RelaySmokeError("round number must be 1 or 2")
    if count != 10:
        raise RelaySmokeError("the reviewed relay smoke requires exactly ten completed mesas")
    database = state_directory / "crawl.sqlite3"
    if not database.is_file():
        raise RelaySmokeError("crawl ledger does not exist")
    prefix = f"https://{_HOSTS[round_number]}/json/ACT/PR/"
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        completed = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT source_url
                FROM items
                WHERE grain = 'mesa'
                  AND parse_status = 'parsed'
                  AND source_url LIKE ?
                ORDER BY source_url
                LIMIT ?
                """,
                (f"{prefix}%", count),
            ).fetchall()
        ]
        retryable_row = connection.execute(
            """
            SELECT source_url
            FROM items
            WHERE grain = 'mesa'
              AND parse_status = 'missing'
              AND source_url LIKE ?
              AND (error LIKE 'transport failure%' OR error LIKE 'retry exhausted%')
            ORDER BY updated_at DESC, source_url
            LIMIT 1
            """,
            (f"{prefix}%",),
        ).fetchone()
    finally:
        connection.close()
    if len(completed) != count:
        raise RelaySmokeError("crawl ledger lacks ten parsed mesas for the smoke gate")
    if retryable_row is None:
        raise RelaySmokeError("crawl ledger lacks a retryable missing mesa for the smoke gate")
    retryable = str(retryable_row[0])
    if retryable in completed:
        raise RelaySmokeError("retryable smoke URL overlaps completed smoke URLs")
    return completed, retryable


def _quarantine_identity(record: QuarantineRecord | None) -> tuple[object, ...] | None:
    if record is None:
        return None
    return (
        record.url,
        record.reason,
        record.status_code,
        record.attempts,
        record.quarantined_at,
    )


async def smoke_relay_resume(
    state_directory: Path,
    *,
    round_number: int,
    relay_base_url: str,
    relay_token_file: Path,
    completed_count: int = 10,
) -> RelaySmokeReport:
    """Verify conditional idempotence plus one previously retryable mesa."""
    completed_urls, retryable_url = _selected_urls(state_directory, round_number, completed_count)
    host = _HOSTS[round_number]
    store = LocalObjectStore(state_directory / "objects")
    checkpoints = SQLiteCheckpointStore(state_directory / "checkpoints.sqlite3")
    before_quarantine = {
        url: _quarantine_identity(checkpoints.quarantined(url))
        for url in (*completed_urls, retryable_url)
    }
    transport = PrecountRelayTransport(
        relay_base_url,
        load_relay_token(relay_token_file),
    )
    completed_not_modified = 0
    completed_same_hash = 0
    official_provenance = True
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=90,
        trust_env=False,
    ) as relay_client:
        collector = AsyncOfficialClient(
            store,
            checkpoints,
            AllowlistPolicy({host}),
            CollectionConfig(
                requests_per_second=2,
                per_host_concurrency=2,
                max_attempts=2,
            ),
            client=relay_client,
        )
        for url in completed_urls:
            prior = checkpoints.latest(url)
            if prior is None:
                raise RelaySmokeError("parsed smoke mesa lacks a checkpoint snapshot")
            result = await collector.fetch(url, conditional=True)
            if result.snapshot is None:
                raise RelaySmokeError("completed smoke fetch returned no snapshot")
            raw = await store.get(result.snapshot.object_key)
            json.loads(raw)
            if result.snapshot.content_hash != prior.content_hash:
                raise RelaySmokeError("completed smoke mesa changed content hash")
            if result.snapshot.snapshot_number != prior.snapshot_number:
                raise RelaySmokeError("unchanged completed mesa created a new snapshot number")
            if result.status == "not_modified":
                completed_not_modified += 1
            else:
                completed_same_hash += 1
            official_provenance = official_provenance and result.snapshot.url == url

        retryable = await collector.fetch(retryable_url, conditional=False)
        if retryable.snapshot is None:
            raise RelaySmokeError("retryable smoke mesa returned no snapshot")
        retryable_raw = await store.get(retryable.snapshot.object_key)
        json.loads(retryable_raw)
        official_provenance = official_provenance and retryable.snapshot.url == retryable_url

    after_quarantine = {
        url: _quarantine_identity(checkpoints.quarantined(url))
        for url in (*completed_urls, retryable_url)
    }
    quarantine_unchanged = before_quarantine == after_quarantine
    if not quarantine_unchanged:
        raise RelaySmokeError("relay smoke changed quarantine state")
    if not official_provenance:
        raise RelaySmokeError("relay smoke replaced an official provenance URL")
    return RelaySmokeReport(
        round_number=round_number,
        completed_checked=len(completed_urls),
        completed_not_modified=completed_not_modified,
        completed_same_hash=completed_same_hash,
        retryable_source_url=retryable_url,
        retryable_content_hash=retryable.snapshot.content_hash,
        quarantine_unchanged=quarantine_unchanged,
        provenance_urls_official=official_provenance,
    )


__all__ = ["RelaySmokeError", "RelaySmokeReport", "smoke_relay_resume"]
