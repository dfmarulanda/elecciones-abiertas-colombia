from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path

import httpx
import pytest
from elecciones_pipeline.ingest import (
    AllowlistPolicy,
    AsyncOfficialClient,
    CheckpointStore,
    CollectionConfig,
    DiscoveryError,
    ElectionCollector,
    FetchError,
    LocalObjectStore,
    OfficialEntryPoints,
    PolicyDenied,
    QuarantineRecord,
    Snapshot,
    SQLiteCheckpointStore,
    discover_mesa_ids,
    discover_official_sources,
)
from pydantic import ValidationError


def run(coro):
    return asyncio.run(coro)


def make_client(tmp_path: Path, handler, **kwargs):
    return AsyncOfficialClient(
        LocalObjectStore(tmp_path / "objects"),
        CheckpointStore(tmp_path / "checkpoint.json"),
        AllowlistPolicy({"official.gov.co"}, resolver=lambda _host: ["8.8.8.8"]),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def test_collection_configuration_is_conservative_and_bounded():
    assert CollectionConfig().requests_per_second == 2
    assert CollectionConfig(requests_per_second=5).per_host_concurrency == 2
    # Generic raw-only crawls may deliberately use one request per second;
    # the pre-count CLI and its catalog policy enforce their separate 2–5 RPS
    # range.
    with pytest.raises(ValidationError):
        CollectionConfig(requests_per_second=0.9)
    with pytest.raises(ValidationError):
        CollectionConfig(per_host_concurrency=3)


@pytest.mark.parametrize(
    "url",
    [
        "https://sub.official.gov.co/data.json",
        "https://official.gov.co:444/data.json",
        "https://official.gov.co@127.0.0.1/data.json",
        "https://127.0.0.1/data.json",
    ],
)
def test_generic_policy_requires_exact_public_default_https_host(url: str):
    policy = AllowlistPolicy({"official.gov.co"}, resolver=lambda _host: ["8.8.8.8"])
    with pytest.raises(PolicyDenied):
        run(policy.check(url))


def test_generic_policy_rejects_private_dns_answer():
    policy = AllowlistPolicy({"official.gov.co"}, resolver=lambda _host: ["127.0.0.1"])
    with pytest.raises(PolicyDenied, match="non-public"):
        run(policy.check("https://official.gov.co/data.json"))


def test_retry_after_and_jittered_retry(tmp_path: Path):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, content=b"ok", headers={"Content-Type": "application/json"})

    async def sleep(seconds):
        sleeps.append(seconds)

    client = make_client(tmp_path, handler, sleep=sleep, random_float=lambda: 0)
    result = run(client.fetch("https://official.gov.co/a.json"))
    assert result.status == "fetched"
    assert len(calls) == 2
    assert sleeps[0] == 3.0
    assert len(sleeps) == 2  # Retry-After is honoured; host throttle still applies.


def test_protocol_failure_retries_and_keeps_successful_snapshot(tmp_path: Path):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("illegal status line")
        return httpx.Response(200, content=b'{"mesa":"M1"}')

    async def sleep(seconds):
        sleeps.append(seconds)

    client = make_client(
        tmp_path,
        handler,
        config=CollectionConfig(retry_base_seconds=1),
        sleep=sleep,
        random_float=lambda: 0,
    )
    result = run(client.fetch("https://official.gov.co/mesa.json"))

    assert result.status == "fetched"
    assert len(calls) == 2
    assert 0.5 in sleeps
    assert client.checkpoints.latest("https://official.gov.co/mesa.json") == result.snapshot
    assert client.checkpoints.quarantined("https://official.gov.co/mesa.json") is None


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_retryable_http_exhaustion_is_resumable_and_not_quarantined(tmp_path: Path, status: int):
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        headers = {"Retry-After": "3"} if status == 429 else {}
        return httpx.Response(status, headers=headers)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    url = "https://official.gov.co/retryable.json"
    client = make_client(
        tmp_path,
        unavailable,
        config=CollectionConfig(max_attempts=2, retry_base_seconds=1),
        sleep=sleep,
        random_float=lambda: 0,
    )
    with pytest.raises(FetchError, match="retry exhausted"):
        run(client.fetch(url))
    assert len(calls) == 2
    assert client.checkpoints.quarantined(url) is None
    if status == 429:
        assert 3.0 in sleeps

    resumed = make_client(
        tmp_path, lambda request: httpx.Response(200, content=b'{"recovered":true}')
    )
    assert run(resumed.fetch(url)).status == "fetched"


def test_transport_exhaustion_is_resumable_and_legacy_record_is_preserved(tmp_path: Path):
    calls: list[httpx.Request] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("source unavailable", request=request)

    url = "https://official.gov.co/transport.json"
    client = make_client(
        tmp_path,
        unavailable,
        config=CollectionConfig(max_attempts=2),
        sleep=lambda _seconds: asyncio.sleep(0),
    )
    with pytest.raises(FetchError, match="transport failure"):
        run(client.fetch(url))
    assert len(calls) == 2
    assert client.checkpoints.quarantined(url) is None

    # A pre-patch checkpoint records this condition as a quarantine.  The
    # patched client retries it, while retaining the original evidence.
    client.checkpoints.quarantine(
        QuarantineRecord(url=url, reason="transport failure: ConnectError", attempts=4)
    )
    resumed = make_client(
        tmp_path, lambda request: httpx.Response(200, content=b'{"recovered":true}')
    )
    assert run(resumed.fetch(url)).status == "fetched"
    assert resumed.checkpoints.quarantined(url) is not None


def test_permanent_failure_is_quarantined(tmp_path: Path):
    client = make_client(tmp_path, lambda request: httpx.Response(404))
    with pytest.raises(FetchError, match="permanent HTTP 404"):
        run(client.fetch("https://official.gov.co/missing.json"))
    assert client.checkpoints.quarantined("https://official.gov.co/missing.json").status_code == 404
    with pytest.raises(FetchError, match="remains quarantined"):
        run(client.fetch("https://official.gov.co/missing.json"))


def test_conditional_request_and_checkpoint_resume(tmp_path: Path):
    requests = []

    def first(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=b'{"one":1}',
            headers={"ETag": '"v1"', "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"},
        )

    client = make_client(tmp_path, first)
    first_result = run(client.fetch("https://official.gov.co/data.json"))
    assert first_result.snapshot.snapshot_number == 1

    def resumed(request):
        requests.append(request)
        assert request.headers["if-none-match"] == '"v1"'
        assert "if-modified-since" in request.headers
        return httpx.Response(304)

    resumed_client = make_client(tmp_path, resumed)
    second = run(resumed_client.fetch("https://official.gov.co/data.json"))
    assert second.status == "not_modified"
    assert second.snapshot.content_hash == first_result.snapshot.content_hash


def test_changed_content_records_a_new_snapshot(tmp_path: Path):
    payloads = iter([b'{"version":1}', b'{"version":2}'])
    client = make_client(tmp_path, lambda request: httpx.Response(200, content=next(payloads)))
    one = run(client.fetch("https://official.gov.co/data.json"))
    two = run(client.fetch("https://official.gov.co/data.json"))
    assert one.snapshot.content_hash != two.snapshot.content_hash
    assert two.snapshot.snapshot_number == 2
    assert len(client.checkpoints.snapshots(one.url)) == 2


def test_raw_object_is_stored_before_parser_runs(tmp_path: Path):
    client = make_client(tmp_path, lambda request: httpx.Response(200, content=b'{"mesa":"M1"}'))
    collector = ElectionCollector(client)

    async def parser(raw):
        snapshot = client.checkpoints.latest("https://official.gov.co/data.json")
        assert snapshot is not None
        assert await client.store.get(snapshot.object_key) == raw
        return json.loads(raw)

    _, parsed = run(collector.collect("https://official.gov.co/data.json", parser))
    assert parsed == {"mesa": "M1"}


def test_coverage_uses_release_manifest_vocabulary(tmp_path: Path):
    client = make_client(tmp_path, lambda request: httpx.Response(200, content=b"{}"))
    one = run(client.fetch("https://official.gov.co/one.json"))
    coverage = ElectionCollector.coverage(3, [one], parsed_count=1, ambiguous=1)
    assert coverage.model_dump() == {
        "expected": 3,
        "retrieved": 1,
        "parsed": 1,
        "missing": 1,
        "ambiguous": 1,
        "excluded": 0,
    }
    assert (
        coverage.parsed + coverage.missing + coverage.ambiguous + coverage.excluded
        == coverage.expected
    )
    with pytest.raises(ValidationError):
        coverage.model_validate({"expected": 1, "retrieved": 0, "parsed": 1})


def test_checkpoint_publish_is_atomic_in_its_own_directory(tmp_path: Path, monkeypatch):
    checkpoint_path = tmp_path / "state" / "checkpoint.json"
    checkpoint = CheckpointStore(checkpoint_path)
    replacements = []
    real_replace = os.replace

    def checked_replace(source, destination):
        source_path = Path(source)
        replacements.append(source_path)
        assert source_path.parent == checkpoint_path.parent
        assert json.loads(source_path.read_text())["snapshots"] == {}
        real_replace(source, destination)

    monkeypatch.setattr("elecciones_pipeline.ingest.checkpoint.os.replace", checked_replace)
    checkpoint.quarantine(
        QuarantineRecord(url="https://official.gov.co/a", reason="test", attempts=1)
    )
    assert replacements and checkpoint_path.exists()
    assert not list(checkpoint_path.parent.glob(f".{checkpoint_path.name}.*"))
    assert CheckpointStore(checkpoint_path).quarantined("https://official.gov.co/a") is not None


def test_sqlite_checkpoint_is_incremental_resumable_and_tracks_changes(tmp_path: Path):
    path = tmp_path / "national-crawl.sqlite3"
    store = SQLiteCheckpointStore(path)
    first = store.record_snapshot(
        Snapshot(
            url="https://official.gov.co/a.json",
            content_hash="a" * 64,
            object_key=f"sha256/{'a' * 64}",
            media_type="application/json",
            byte_size=2,
        )
    )
    unchanged = store.record_snapshot(
        Snapshot(
            url=first.url,
            content_hash=first.content_hash,
            object_key=first.object_key,
            media_type=first.media_type,
            byte_size=first.byte_size,
        )
    )
    changed = store.record_snapshot(
        Snapshot(
            url=first.url,
            content_hash="b" * 64,
            object_key=f"sha256/{'b' * 64}",
            media_type="application/json",
            byte_size=3,
        )
    )
    store.quarantine(QuarantineRecord(url="https://official.gov.co/b", reason="test", attempts=1))

    resumed = SQLiteCheckpointStore(path)
    assert unchanged.snapshot_number == 1
    assert changed.snapshot_number == 2
    assert [item.content_hash for item in resumed.snapshots(first.url)] == ["a" * 64, "b" * 64]
    assert resumed.latest(first.url) == changed
    assert resumed.quarantined("https://official.gov.co/b") is not None


def test_sqlite_checkpoint_connections_close_after_each_operation(tmp_path: Path):
    store = SQLiteCheckpointStore(tmp_path / "national-crawl.sqlite3")
    with store._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_redirect_limit_is_quarantined_instead_of_falling_through(tmp_path: Path):
    client = make_client(
        tmp_path,
        lambda request: httpx.Response(302, headers={"Location": "/again"}),
        config=CollectionConfig(max_attempts=2),
    )
    with pytest.raises(FetchError, match="redirect limit exhausted"):
        run(client.fetch("https://official.gov.co/start"))
    record = client.checkpoints.quarantined("https://official.gov.co/start")
    assert record is not None
    assert record.reason == "redirect limit exhausted"


def test_allowlist_blocks_ssrf_forms_and_redirect_targets(tmp_path: Path):
    policy = AllowlistPolicy({"official.gov.co", "data.official.gov.co"})
    assert policy.permits("https://data.official.gov.co/a")
    assert not policy.permits("https://official.gov.co@127.0.0.1/a")
    assert not policy.permits("http://official.gov.co/a")

    client = make_client(
        tmp_path, lambda request: httpx.Response(302, headers={"Location": "https://127.0.0.1/"})
    )
    with pytest.raises(PolicyDenied):
        run(client.fetch("https://official.gov.co/a"))
    quarantine = client.checkpoints.quarantined("https://official.gov.co/a")
    assert quarantine is not None
    assert quarantine.reason.startswith("policy denied redirect target:")


def test_initial_policy_denial_is_quarantined(tmp_path: Path):
    client = make_client(tmp_path, lambda request: pytest.fail("network must not be reached"))
    url = "http://official.gov.co/not-https"
    with pytest.raises(PolicyDenied):
        run(client.fetch(url))
    quarantine = client.checkpoints.quarantined(url)
    assert quarantine is not None
    assert quarantine.reason.startswith("policy denied:")


def test_discovery_requires_roots_and_verified_polling_place_manifest_only():
    entries = OfficialEntryPoints(
        election_configuration="https://official.gov.co/election.json",
        nomenclator="https://official.gov.co/nomenclator.json",
        scrutiny_index="https://official.gov.co/data/index.json",
    )
    documents = {
        "https://official.gov.co/election.json": {"results_url": "/results/place-1.json"},
        "https://official.gov.co/nomenclator.json": {},
        "https://official.gov.co/data/index.json": {"manifest_url": "/verified.json"},
    }
    discovered = discover_official_sources(entries, documents)
    assert "https://official.gov.co/results/place-1.json" in discovered
    assert "https://official.gov.co/verified.json" in discovered
    with pytest.raises(DiscoveryError):
        discover_official_sources(entries, {})
    with pytest.raises(DiscoveryError):
        discover_mesa_ids(
            {"kind": "polling_place_results", "verified": False, "mesas": [{"mesa_id": "M1"}]}
        )
    assert discover_mesa_ids(
        {
            "kind": "verified_manifest",
            "verified": True,
            "mesas": [{"mesa_id": "M1"}, {"mesaId": "M2"}],
        }
    ) == {"M1", "M2"}


def test_schema_drift_does_not_synthesize_mesas_or_endpoints():
    with pytest.raises(DiscoveryError):
        discover_mesa_ids({"kind": "verified_manifest", "verified": True, "mesa_count": 999})
    with pytest.raises(ValidationError):
        OfficialEntryPoints(
            election_configuration="https://official.gov.co/election.json",
            nomenclator="https://official.gov.co/nomenclator-v2.json",
            scrutiny_index="https://official.gov.co/data/index.json",
        )
