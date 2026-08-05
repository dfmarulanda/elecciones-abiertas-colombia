"""Async HTTP collection with bounded per-host rate/concurrency and retries."""

from __future__ import annotations

import asyncio
import hashlib
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .checkpoint import CheckpointStore, SQLiteCheckpointStore
from .models import CollectionConfig, FetchResult, QuarantineRecord, Snapshot
from .policy import AllowlistPolicy, PolicyDenied
from .storage import ObjectStore

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
ResponseObserver = Callable[[str, int, int], None]


class FetchError(RuntimeError):
    """A permanent or exhausted fetch failure."""


class _HostLimit:
    def __init__(self, requests_per_second: float, concurrency: int, clock: Clock, sleep: Sleep):
        self.interval = 1 / requests_per_second
        self.semaphore = asyncio.Semaphore(concurrency)
        self.clock = clock
        self.sleep = sleep
        self.next_request_at = 0.0
        self.lock = asyncio.Lock()

    async def wait_turn(self) -> None:
        async with self.lock:
            now = self.clock()
            delay = max(0.0, self.next_request_at - now)
            self.next_request_at = max(now, self.next_request_at) + self.interval
        if delay:
            await self.sleep(delay)


class AsyncOfficialClient:
    """One request interface that makes collection policy hard to bypass."""

    retryable_statuses = frozenset({408, 429})

    def __init__(
        self,
        store: ObjectStore,
        checkpoints: CheckpointStore | SQLiteCheckpointStore,
        policy: AllowlistPolicy,
        config: CollectionConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock | None = None,
        random_float: Callable[[], float] = random.random,
        on_response: ResponseObserver | None = None,
    ):
        self.store = store
        self.checkpoints = checkpoints
        self.policy = policy
        self.config = config or CollectionConfig()
        self.client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.config.timeout_seconds,
            # The official endpoint has returned a partial JSON body followed by
            # a new HTTP status line on a reused connection.  Do not return a
            # connection to the pool after a response: a fresh connection is
            # safer than risking response framing from a prior request.
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self._owns_client = client is None
        self.sleep = sleep
        self.clock = clock or __import__("time").monotonic
        self.random_float = random_float
        # This hook records every response before retry logic hides a recovered
        # upstream failure from the terminal crawl ledger.
        self.on_response = on_response
        self._limits: dict[str, _HostLimit] = {}

    async def __aenter__(self) -> AsyncOfficialClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _limit_for(self, url: str) -> _HostLimit:
        host = urlsplit(url).hostname or ""
        if host not in self._limits:
            self._limits[host] = _HostLimit(
                self.config.requests_per_second,
                self.config.per_host_concurrency,
                self.clock,
                self.sleep,
            )
        return self._limits[host]

    @staticmethod
    def _retry_after(headers: httpx.Headers) -> float | None:
        value = headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=UTC)
                return max(0.0, (date - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError):
                return None

    def _backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = self._retry_after(response.headers)
            if retry_after is not None:
                return retry_after
        ceiling = min(
            self.config.retry_max_seconds, self.config.retry_base_seconds * (2 ** (attempt - 1))
        )
        return float(ceiling * (0.5 + self.random_float() * 0.5))

    async def fetch(self, url: str, *, conditional: bool = True) -> FetchResult:
        """Fetch and atomically checkpoint an immutable raw snapshot.

        Redirect targets receive a separate allowlist/policy check and are never
        followed automatically.
        """
        try:
            await self.policy.check(url)
        except PolicyDenied as exc:
            # A policy failure is an operator/configuration error, never a
            # transient upstream condition.  Keep the rejected URL as durable
            # evidence and fail closed before a network request is possible.
            self._quarantine(url, f"policy denied: {exc}", None, 1)
            raise
        quarantine = self.checkpoints.quarantined(url)
        if quarantine and not self._retryable_quarantine(quarantine):
            raise FetchError(f"URL remains quarantined: {url}")
        latest = self.checkpoints.latest(url)
        headers = {"Accept": "application/json, application/octet-stream;q=0.8, */*;q=0.1"}
        if conditional and latest and latest.etag:
            headers["If-None-Match"] = latest.etag
        if conditional and latest and latest.last_modified:
            headers["If-Modified-Since"] = latest.last_modified

        current_url = url
        last_status: int | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            response: httpx.Response | None = None
            try:
                limit = self._limit_for(current_url)
                async with limit.semaphore:
                    await limit.wait_turn()
                    response = await self.client.get(current_url, headers=headers)
                last_status = response.status_code
                if self.on_response is not None:
                    self.on_response(url, response.status_code, attempt)
                if response.status_code == 304 and latest:
                    return FetchResult(status="not_modified", url=url, snapshot=latest)
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        self._quarantine(
                            url, "redirect without Location", response.status_code, attempt
                        )
                        raise FetchError(f"redirect without Location: {current_url}")
                    target = str(response.url.join(location))
                    try:
                        await self.policy.check(target)
                    except PolicyDenied as exc:
                        self._quarantine(
                            url, f"policy denied redirect target: {exc}", None, attempt
                        )
                        raise
                    current_url = target
                    # Validators identify the original resource, not a redirect target.
                    headers = {"Accept": headers["Accept"]}
                    continue
                if 200 <= response.status_code < 300:
                    content = response.content
                    # The raw bytes reach the object store before Snapshot/parser consumers do.
                    object_key = await self.store.put(
                        content, content_type=response.headers.get("Content-Type")
                    )
                    snapshot = Snapshot(
                        url=url,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        object_key=object_key,
                        media_type=response.headers.get(
                            "Content-Type", "application/octet-stream"
                        ).split(";", 1)[0],
                        byte_size=len(content),
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                    )
                    return FetchResult(
                        status="fetched",
                        url=url,
                        snapshot=self.checkpoints.record_snapshot(snapshot),
                    )
                retryable = (
                    response.status_code in self.retryable_statuses
                    or 500 <= response.status_code < 600
                )
                if not retryable:
                    self._quarantine(
                        url, f"HTTP {response.status_code}", response.status_code, attempt
                    )
                    raise FetchError(f"permanent HTTP {response.status_code} for {url}")
                if attempt < self.config.max_attempts:
                    await self.sleep(self._backoff(attempt, response))
                    continue
                # Retain the failed attempt in the crawl ledger, but do not
                # quarantine a retryable upstream status.  A resumed reviewed
                # crawl must be able to retry after an outage or rate limit.
                raise FetchError(f"retry exhausted for {url}")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
                if attempt < self.config.max_attempts:
                    await self.sleep(self._backoff(attempt))
                    continue
                # Network failures are inherently non-terminal.  They remain
                # durable ``missing`` rows in the caller's crawl ledger and
                # are eligible for a later explicit resume.
                raise FetchError(f"transport failure for {url}") from exc
            except PolicyDenied:
                raise
        self._quarantine(url, "redirect limit exhausted", last_status, self.config.max_attempts)
        raise FetchError(f"redirect limit exhausted for {url}")

    def _quarantine(self, url: str, reason: str, status: int | None, attempts: int) -> None:
        self.checkpoints.quarantine(
            QuarantineRecord(url=url, reason=reason, status_code=status, attempts=attempts)
        )

    @classmethod
    def _retryable_quarantine(cls, record: QuarantineRecord) -> bool:
        """Permit a reviewed resume of legacy transient quarantine records.

        Earlier collector versions recorded exhausted transport and retryable
        HTTP failures in the same permanent quarantine store as terminal 4xx
        and policy failures.  Do not erase that evidence, but do not let it
        permanently suppress a later, explicit resume either.
        """
        return record.reason.startswith("transport failure:") or (
            record.reason.startswith("retry exhausted after HTTP ")
            and (
                record.status_code in cls.retryable_statuses
                or (record.status_code is not None and 500 <= record.status_code < 600)
            )
        )
