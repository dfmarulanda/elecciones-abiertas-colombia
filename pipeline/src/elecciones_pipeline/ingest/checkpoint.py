"""Durable, idempotent URL state and quarantine records."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from .models import QuarantineRecord, Snapshot


class CheckpointStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._snapshots: dict[str, list[Snapshot]] = {}
        self._quarantine: dict[str, QuarantineRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        self._snapshots = {
            url: [Snapshot.model_validate(item) for item in snapshots]
            for url, snapshots in data.get("snapshots", {}).items()
        }
        self._quarantine = {
            url: QuarantineRecord.model_validate(item)
            for url, item in data.get("quarantine", {}).items()
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "snapshots": {
                url: [s.model_dump(mode="json") for s in values]
                for url, values in self._snapshots.items()
            },
            "quarantine": {url: q.model_dump(mode="json") for url, q in self._quarantine.items()},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        # Replacement on one filesystem makes a complete checkpoint visible at once.
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def latest(self, url: str) -> Snapshot | None:
        values = self._snapshots.get(url, [])
        return values[-1] if values else None

    def snapshots(self, url: str) -> tuple[Snapshot, ...]:
        return tuple(self._snapshots.get(url, []))

    def record_snapshot(self, snapshot: Snapshot) -> Snapshot:
        values = self._snapshots.setdefault(snapshot.url, [])
        if values and values[-1].content_hash == snapshot.content_hash:
            return values[-1]
        saved = snapshot.model_copy(update={"snapshot_number": len(values) + 1})
        values.append(saved)
        # Quarantine records are operational provenance.  A later successful
        # snapshot proves recovery but must not erase the earlier rejected or
        # unavailable response from the durable checkpoint.
        self._save()
        return saved

    def quarantine(self, record: QuarantineRecord) -> None:
        self._quarantine[record.url] = record
        self._save()

    def quarantined(self, url: str) -> QuarantineRecord | None:
        return self._quarantine.get(url)


class SQLiteCheckpointStore:
    """Incremental checkpoint storage for national crawls.

    The JSON checkpoint remains useful for small source checks. Rewriting that
    complete document after each of more than 100,000 mesa responses would be
    quadratic work, so long-running crawls use this append-oriented store with
    the same interface consumed by :class:`AsyncOfficialClient`.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    url TEXT NOT NULL,
                    snapshot_number INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    etag TEXT,
                    last_modified TEXT,
                    PRIMARY KEY (url, snapshot_number)
                );
                CREATE INDEX IF NOT EXISTS snapshots_latest
                    ON snapshots (url, snapshot_number DESC);
                CREATE TABLE IF NOT EXISTS quarantine (
                    url TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    status_code INTEGER,
                    attempts INTEGER NOT NULL,
                    quarantined_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            # sqlite3.Connection's context manager commits or rolls back, but
            # intentionally does not close the database.  These stores open a
            # connection for every durable operation, so explicitly close it
            # once that transaction finishes rather than deferring hundreds of
            # file handles and statement caches to cyclic GC.
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _snapshot(row: sqlite3.Row | None) -> Snapshot | None:
        if row is None:
            return None
        return Snapshot.model_validate(dict(row))

    def latest(self, url: str) -> Snapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT url, content_hash, object_key, media_type, byte_size,
                       retrieved_at, etag, last_modified, snapshot_number
                FROM snapshots
                WHERE url = ?
                ORDER BY snapshot_number DESC
                LIMIT 1
                """,
                (url,),
            ).fetchone()
        return self._snapshot(row)

    def snapshots(self, url: str) -> tuple[Snapshot, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT url, content_hash, object_key, media_type, byte_size,
                       retrieved_at, etag, last_modified, snapshot_number
                FROM snapshots
                WHERE url = ?
                ORDER BY snapshot_number
                """,
                (url,),
            ).fetchall()
        return tuple(Snapshot.model_validate(dict(row)) for row in rows)

    def record_snapshot(self, snapshot: Snapshot) -> Snapshot:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT url, content_hash, object_key, media_type, byte_size,
                       retrieved_at, etag, last_modified, snapshot_number
                FROM snapshots
                WHERE url = ?
                ORDER BY snapshot_number DESC
                LIMIT 1
                """,
                (snapshot.url,),
            ).fetchone()
            latest = self._snapshot(row)
            if latest is not None and latest.content_hash == snapshot.content_hash:
                return latest
            saved = snapshot.model_copy(
                update={"snapshot_number": 1 if latest is None else latest.snapshot_number + 1}
            )
            connection.execute(
                """
                INSERT INTO snapshots (
                    url, snapshot_number, content_hash, object_key, media_type,
                    byte_size, retrieved_at, etag, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saved.url,
                    saved.snapshot_number,
                    saved.content_hash,
                    saved.object_key,
                    saved.media_type,
                    saved.byte_size,
                    saved.retrieved_at.isoformat(),
                    saved.etag,
                    saved.last_modified,
                ),
            )
        return saved

    def quarantine(self, record: QuarantineRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO quarantine (
                    url, reason, status_code, attempts, quarantined_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    reason = excluded.reason,
                    status_code = excluded.status_code,
                    attempts = excluded.attempts,
                    quarantined_at = excluded.quarantined_at
                """,
                (
                    record.url,
                    record.reason,
                    record.status_code,
                    record.attempts,
                    record.quarantined_at.isoformat(),
                ),
            )

    def quarantined(self, url: str) -> QuarantineRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT url, reason, status_code, attempts, quarantined_at
                FROM quarantine
                WHERE url = ?
                """,
                (url,),
            ).fetchone()
        return QuarantineRecord.model_validate(dict(row)) if row is not None else None
