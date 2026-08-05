"""Safe, restartable collection of reviewed official election sources."""

from .checkpoint import CheckpointStore, SQLiteCheckpointStore
from .collector import ElectionCollector
from .discovery import DiscoveryError, discover_mesa_ids, discover_official_sources
from .http import AsyncOfficialClient, FetchError
from .models import (
    CollectionConfig,
    Coverage,
    FetchResult,
    OfficialEntryPoints,
    QuarantineRecord,
    Snapshot,
)
from .policy import AllowlistPolicy, PolicyDenied
from .precount_crawl import (
    PrecountCrawlError,
    PrecountCrawlReport,
    PrecountStage,
    crawl_precount,
)
from .storage import LocalObjectStore, ObjectStore, R2ObjectStore

__all__ = [
    "AllowlistPolicy",
    "AsyncOfficialClient",
    "CheckpointStore",
    "CollectionConfig",
    "Coverage",
    "DiscoveryError",
    "ElectionCollector",
    "FetchError",
    "FetchResult",
    "LocalObjectStore",
    "ObjectStore",
    "OfficialEntryPoints",
    "PolicyDenied",
    "PrecountCrawlError",
    "PrecountCrawlReport",
    "PrecountStage",
    "QuarantineRecord",
    "R2ObjectStore",
    "SQLiteCheckpointStore",
    "Snapshot",
    "discover_mesa_ids",
    "discover_official_sources",
    "crawl_precount",
]
