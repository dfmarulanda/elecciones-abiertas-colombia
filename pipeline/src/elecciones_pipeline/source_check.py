"""Non-publishing checks for the official crawl entry manifests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .catalog import SourceCatalog
from .ingest import (
    AllowlistPolicy,
    AsyncOfficialClient,
    CheckpointStore,
    CollectionConfig,
    ElectionCollector,
    LocalObjectStore,
)


@dataclass(frozen=True)
class SourceCheckItem:
    id: str
    url: str
    status: str
    content_hash: str
    snapshot_number: int
    changed: bool
    byte_size: int
    media_type: str


@dataclass(frozen=True)
class SourceCheckReport:
    catalog_version: str
    election_slug: str
    publication_requested: bool
    publication_performed: bool
    manifest_only: bool
    changed: bool
    items: tuple[SourceCheckItem, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def _validate_manifest_shape(identifier: str, payload: object) -> None:
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"{identifier} returned a scalar JSON value")
    if isinstance(payload, dict) and not payload:
        raise ValueError(f"{identifier} returned an empty JSON object")
    if isinstance(payload, list) and not payload:
        raise ValueError(f"{identifier} returned an empty JSON list")


async def check_official_manifests(
    catalog: SourceCatalog,
    state_directory: Path,
    *,
    manifest_only: bool = True,
) -> SourceCheckReport:
    """Fetch reviewed roots and report changes without creating or activating a release."""
    if not manifest_only:
        raise ValueError("full crawls require an explicit, separately reviewed crawl plan")
    await asyncio.to_thread(state_directory.mkdir, parents=True, exist_ok=True)
    store = LocalObjectStore(state_directory / "objects")
    checkpoints = CheckpointStore(state_directory / "checkpoints.json")
    policy = AllowlistPolicy(set(catalog.allowed_hosts))
    config = CollectionConfig(
        requests_per_second=catalog.collection_policy.requests_per_second_minimum,
        per_host_concurrency=catalog.collection_policy.maximum_concurrency_per_host,
    )
    items: list[SourceCheckItem] = []
    async with AsyncOfficialClient(store, checkpoints, policy, config) as client:
        collector = ElectionCollector(client)
        for identifier, url in catalog.manifest_entrypoints().items():
            result, parsed = await collector.collect_json(url)
            snapshot = result.snapshot
            if snapshot is None:
                raise RuntimeError(f"{identifier} did not retain its prior snapshot")
            if parsed is not None:
                _validate_manifest_shape(identifier, parsed)
            items.append(
                SourceCheckItem(
                    id=identifier,
                    url=url,
                    status=result.status,
                    content_hash=snapshot.content_hash,
                    snapshot_number=snapshot.snapshot_number,
                    changed=result.status == "fetched" and snapshot.snapshot_number > 1,
                    byte_size=snapshot.byte_size,
                    media_type=snapshot.media_type,
                )
            )
    if catalog.scrutiny_source() is None:
        # Do not present the absence of a reviewed structured scrutiny manifest
        # as either a fetched document or a legal-final result.
        items.append(
            SourceCheckItem(
                id="scrutiny_manifest",
                url="",
                status="not_declared",
                content_hash="",
                snapshot_number=0,
                changed=False,
                byte_size=0,
                media_type="",
            )
        )
    return SourceCheckReport(
        catalog_version=catalog.catalog_version,
        election_slug=catalog.election_slug,
        publication_requested=False,
        publication_performed=False,
        manifest_only=True,
        changed=any(item.changed for item in items),
        items=tuple(items),
    )
