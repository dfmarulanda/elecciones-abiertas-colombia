"""Fail-closed health snapshot tests for the rate-ramp supervisor."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from elecciones_pipeline.ops.rate_ramp import CrawlSnapshot, _delta, snapshot


def test_snapshot_and_circuit_breaker_delta(tmp_path: Path) -> None:
    crawl = sqlite3.connect(tmp_path / "crawl.sqlite3")
    checkpoints = sqlite3.connect(tmp_path / "checkpoints.sqlite3")
    try:
        crawl.execute(
            "CREATE TABLE items(network_status TEXT,parse_status TEXT,error TEXT,updated_at TEXT)"
        )
        crawl.executemany(
            "INSERT INTO items VALUES(?,?,?,?)",
            [
                ("fetched", "parsed", None, "2026-08-04T00:00:00Z"),
                ("reused", "parsed", None, "2026-08-04T00:00:01Z"),
                ("failed", "missing", "retry exhausted after HTTP 429", "2026-08-04T00:00:02Z"),
                ("failed", "missing", "transport failure: ConnectTimeout", "2026-08-04T00:00:03Z"),
            ],
        )
        checkpoints.execute("CREATE TABLE snapshots(url TEXT,content_hash TEXT)")
        checkpoints.execute("CREATE TABLE quarantine(url TEXT)")
        checkpoints.executemany(
            "INSERT INTO snapshots VALUES(?,?)", [("one", "a"), ("two", "b"), ("two", "c")]
        )
        checkpoints.execute("INSERT INTO quarantine VALUES('bad')")
        crawl.commit()
        checkpoints.commit()
    finally:
        crawl.close()
        checkpoints.close()
    captured = snapshot(tmp_path)
    assert captured.parsed == 2
    assert captured.fetched == 1
    assert captured.reused == 1
    assert captured.http_429 == 1
    assert captured.raw_http_5xx == 0
    assert captured.timeouts == 1
    assert captured.quarantine == 1
    assert captured.changed_source_urls == 1
    stable = CrawlSnapshot(2, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1, None)
    assert _delta(stable, captured) == ("http_429", "timeouts", "failed_or_missing")


def test_snapshot_observes_recovered_raw_5xx(tmp_path: Path) -> None:
    crawl = sqlite3.connect(tmp_path / "crawl.sqlite3")
    checkpoints = sqlite3.connect(tmp_path / "checkpoints.sqlite3")
    try:
        crawl.execute(
            "CREATE TABLE items(network_status TEXT,parse_status TEXT,error TEXT,updated_at TEXT)"
        )
        crawl.execute("INSERT INTO items VALUES('fetched', 'parsed', NULL, '2026-08-04T00:00:00Z')")
        crawl.execute(
            """CREATE TABLE retryable_responses(
                source_url TEXT, status_code INTEGER, attempt INTEGER, observed_at TEXT)"""
        )
        crawl.execute(
            """INSERT INTO retryable_responses VALUES(
                'https://official.example/mesa', 500, 1, '2026-08-04T00:00:00Z'
            )"""
        )
        checkpoints.execute("CREATE TABLE snapshots(url TEXT,content_hash TEXT)")
        checkpoints.execute("CREATE TABLE quarantine(url TEXT)")
        crawl.commit()
        checkpoints.commit()
    finally:
        crawl.close()
        checkpoints.close()
    before = snapshot(tmp_path)
    assert before.http_5xx == 0
    assert before.raw_http_5xx == 1
    stable = CrawlSnapshot(1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None)
    assert _delta(stable, before) == ("raw_http_5xx",)
