"""Strict discovery from configured manifest data, without endpoint synthesis."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from .models import OfficialEntryPoints


class DiscoveryError(ValueError):
    pass


_URL_KEYS = frozenset(
    {"url", "href", "source_url", "manifest_url", "results_url", "result_url", "index_url"}
)
_MESA_KEYS = frozenset({"mesa_id", "mesaId", "id_mesa", "codigo_mesa"})
_RESULT_MANIFEST_MARKERS = frozenset(
    {"polling_place_results", "polling-place-results", "verified_manifest", "verified-manifest"}
)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _absolute(base_url: str, candidate: str) -> str:
    if not isinstance(candidate, str) or not candidate.strip():
        raise DiscoveryError("manifest URL is missing or invalid")
    return urljoin(base_url, candidate)


def discover_official_sources(entries: OfficialEntryPoints, documents: dict[str, Any]) -> set[str]:
    """Return only URLs explicitly present in the three fetched root documents."""
    expected = set(entries.urls())
    if set(documents) != expected:
        raise DiscoveryError("discovery requires exactly the configured official entry documents")
    found = set(expected)
    for base_url, document in documents.items():
        for item in _walk(document):
            for key in _URL_KEYS:
                candidate = item.get(key)
                if isinstance(candidate, str):
                    found.add(_absolute(base_url, candidate))
    return found


def discover_mesa_ids(polling_place_results_or_manifest: dict[str, Any]) -> set[str]:
    """Enumerate mesa IDs only if a verified results/manifest type declares them."""
    marker = str(
        polling_place_results_or_manifest.get("kind")
        or polling_place_results_or_manifest.get("type")
        or polling_place_results_or_manifest.get("manifest_type")
        or ""
    ).lower()
    if marker not in _RESULT_MANIFEST_MARKERS or not polling_place_results_or_manifest.get(
        "verified", False
    ):
        raise DiscoveryError("mesa IDs may only come from a verified polling-place result manifest")
    mesas = polling_place_results_or_manifest.get("mesas")
    if not isinstance(mesas, list):
        raise DiscoveryError("verified result manifest must contain a mesas list")
    ids: set[str] = set()
    for mesa in mesas:
        if not isinstance(mesa, dict):
            raise DiscoveryError("mesa entry must be an object")
        mesa_id = next((mesa[key] for key in _MESA_KEYS if isinstance(mesa.get(key), str)), None)
        if not mesa_id:
            raise DiscoveryError("mesa entry does not declare an ID")
        ids.add(mesa_id)
    return ids
