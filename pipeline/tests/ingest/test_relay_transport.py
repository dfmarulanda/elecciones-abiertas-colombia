from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest
from elecciones_pipeline.ingest.checkpoint import SQLiteCheckpointStore
from elecciones_pipeline.ingest.http import AsyncOfficialClient, FetchError
from elecciones_pipeline.ingest.models import CollectionConfig
from elecciones_pipeline.ingest.policy import AllowlistPolicy
from elecciones_pipeline.ingest.relay_transport import (
    PrecountRelayTransport,
    RelayTransportError,
    load_relay_token,
    relay_path_for_official_url,
    validate_relay_base_url,
)
from elecciones_pipeline.ingest.storage import LocalObjectStore

OFFICIAL_HOST = "resultadosprecpresidente2026-2v.registraduria.gov.co"
OFFICIAL_URL = f"https://{OFFICIAL_HOST}/json/ACT/PR/00123456789012345.json"
TOKEN = "a" * 64


def run(coro):
    return asyncio.run(coro)


def test_only_reviewed_official_urls_map_to_typed_relay_paths() -> None:
    assert (
        relay_path_for_official_url(
            "https://resultadosprecpresidente2026-1v.registraduria.gov.co/json/web/config.json"
        )
        == "/v1/precount/1/configuration"
    )
    assert (
        relay_path_for_official_url(
            "https://resultadosprecpresidente2026-2v.registraduria.gov.co/json/nomenclator.json"
        )
        == "/v1/precount/2/nomenclator"
    )
    assert relay_path_for_official_url(OFFICIAL_URL) == ("/v1/precount/2/act/00123456789012345")

    for forbidden in (
        "https://example.com/json/ACT/PR/00.json",
        f"https://{OFFICIAL_HOST}/documents/E14.pdf",
        f"https://{OFFICIAL_HOST}/json/ACT/PR/00.json?url=https://example.com",
        f"https://{OFFICIAL_HOST}@127.0.0.1/json/ACT/PR/00.json",
        f"http://{OFFICIAL_HOST}/json/ACT/PR/00.json",
    ):
        with pytest.raises(RelayTransportError):
            relay_path_for_official_url(forbidden)


def test_relay_base_and_token_file_are_local_and_owner_only(tmp_path: Path) -> None:
    assert validate_relay_base_url("http://127.0.0.1:18787") == "http://127.0.0.1:18787"
    for forbidden in (
        "https://127.0.0.1:18787",
        "http://localhost:18787",
        "http://0.0.0.0:18787",
        "http://127.0.0.1:18787/path",
        "http://127.0.0.1",
    ):
        with pytest.raises(RelayTransportError, match="loopback"):
            validate_relay_base_url(forbidden)

    token_path = tmp_path / "token"
    token_path.write_text(f"{TOKEN}\n", encoding="ascii")
    token_path.chmod(0o600)
    assert load_relay_token(token_path) == TOKEN
    token_path.chmod(0o644)
    with pytest.raises(RelayTransportError, match="group or other"):
        load_relay_token(token_path)


def test_transport_preserves_official_provenance_hash_and_conditional_headers(
    tmp_path: Path,
) -> None:
    payload = b'{"mesa":"00123456789012345","votes":0}'
    requests: list[httpx.Request] = []

    def relay_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "http://127.0.0.1:18787/v1/precount/2/act/00123456789012345"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert "cookie" not in request.headers
        if len(requests) == 1:
            return httpx.Response(
                200,
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "ETag": '"snapshot-one"',
                    "Last-Modified": "Mon, 04 Aug 2026 12:00:00 GMT",
                },
            )
        assert request.headers["if-none-match"] == '"snapshot-one"'
        assert request.headers["if-modified-since"] == "Mon, 04 Aug 2026 12:00:00 GMT"
        return httpx.Response(304)

    async def scenario() -> None:
        checkpoints = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite3")
        relay_transport = PrecountRelayTransport(
            "http://127.0.0.1:18787",
            TOKEN,
            inner=httpx.MockTransport(relay_handler),
        )
        async with httpx.AsyncClient(
            transport=relay_transport,
            follow_redirects=False,
            trust_env=False,
        ) as relay_client:
            collector = AsyncOfficialClient(
                LocalObjectStore(tmp_path / "objects"),
                checkpoints,
                AllowlistPolicy({OFFICIAL_HOST}, resolver=lambda _host: ("8.8.8.8",)),
                client=relay_client,
            )
            first = await collector.fetch(OFFICIAL_URL)
            assert first.snapshot is not None
            assert first.snapshot.url == OFFICIAL_URL
            assert first.snapshot.content_hash == hashlib.sha256(payload).hexdigest()
            assert await collector.store.get(first.snapshot.object_key) == payload

            second = await collector.fetch(OFFICIAL_URL)
            assert second.status == "not_modified"
            assert second.url == OFFICIAL_URL
            assert second.snapshot == first.snapshot

    run(scenario())
    assert len(requests) == 2


def test_retryable_relay_status_remains_resumable_and_unquarantined(tmp_path: Path) -> None:
    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def scenario() -> None:
        checkpoints = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite3")
        relay_transport = PrecountRelayTransport(
            "http://127.0.0.1:18787",
            TOKEN,
            inner=httpx.MockTransport(unavailable),
        )
        async with httpx.AsyncClient(transport=relay_transport, trust_env=False) as relay_client:
            collector = AsyncOfficialClient(
                LocalObjectStore(tmp_path / "objects"),
                checkpoints,
                AllowlistPolicy({OFFICIAL_HOST}, resolver=lambda _host: ("8.8.8.8",)),
                CollectionConfig(max_attempts=1),
                client=relay_client,
            )
            with pytest.raises(FetchError, match="retry exhausted"):
                await collector.fetch(OFFICIAL_URL)
            assert checkpoints.quarantined(OFFICIAL_URL) is None

    run(scenario())
