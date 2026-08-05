"""High-level fetch/decode orchestration retaining raw provenance."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from .http import AsyncOfficialClient
from .models import Coverage, FetchResult

Parser = Callable[[bytes], Any | Awaitable[Any]]


class ElectionCollector:
    def __init__(self, client: AsyncOfficialClient):
        self.client = client

    async def collect_json(self, url: str) -> tuple[FetchResult, Any | None]:
        result = await self.client.fetch(url)
        if result.status == "not_modified":
            return result, None
        assert result.snapshot is not None
        # Object storage is the parser's sole input: it cannot read an unpersisted response.
        raw = await self.client.store.get(result.snapshot.object_key)
        return result, json.loads(raw)

    async def collect(self, url: str, parser: Parser) -> tuple[FetchResult, Any | None]:
        result = await self.client.fetch(url)
        if result.status == "not_modified":
            return result, None
        assert result.snapshot is not None
        raw = await self.client.store.get(result.snapshot.object_key)
        parsed = parser(raw)
        if hasattr(parsed, "__await__"):
            parsed = await parsed
        return result, parsed

    @staticmethod
    def coverage(
        expected: int,
        results: list[FetchResult],
        parsed_count: int,
        *,
        ambiguous: int = 0,
        excluded: int = 0,
    ) -> Coverage:
        return Coverage.from_outcomes(
            expected,
            sum(result.status == "fetched" for result in results),
            parsed_count,
            ambiguous=ambiguous,
            excluded=excluded,
        )
