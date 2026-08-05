"""Index official document links without synthesising endpoints or fetching them."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from .models import DocumentIndexEntry, DocumentType
from .policy import DocumentURLPolicy

_MESA_KEYS = ("mesa_id", "mesaId", "id_mesa", "codigo_mesa")
_URL_KEYS = ("official_url", "document_url", "pdf_url", "image_url", "url", "href")
_TYPE_KEYS = ("document_type", "type", "kind")
_TYPE_MAP: dict[str, DocumentType] = {
    "e14_delegate": "e14_delegate",
    "e14-delegate": "e14_delegate",
    "e14_transmission": "e14_transmission",
    "e14-transmission": "e14_transmission",
}


class DocumentIndexError(ValueError):
    pass


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _document_type(item: dict[str, Any]) -> DocumentType | None:
    for key in _TYPE_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.lower() in _TYPE_MAP:
            return _TYPE_MAP[value.lower()]
    # A URL alone is not enough to label an arbitrary resource as E-14.
    return None


def index_official_documents(
    source_index_url: str,
    manifest: dict[str, Any],
    known_mesa_ids: set[str] | frozenset[str],
    *,
    policy: DocumentURLPolicy,
) -> tuple[DocumentIndexEntry, ...]:
    """Index explicitly published documents only for canonical, pre-verified mesas."""
    if not known_mesa_ids:
        raise DocumentIndexError("canonical mesa IDs are required before document indexing")
    index_hash = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    entries: dict[tuple[str, str, str], DocumentIndexEntry] = {}
    for item in _walk(manifest):
        mesa_id = next((item[key] for key in _MESA_KEYS if isinstance(item.get(key), str)), None)
        document_type = _document_type(item)
        url = next((item[key] for key in _URL_KEYS if isinstance(item.get(key), str)), None)
        if mesa_id is None and document_type is None and url is None:
            continue
        if not (mesa_id and document_type and url):
            continue
        if mesa_id not in known_mesa_ids:
            raise DocumentIndexError(
                f"document references unknown/non-canonical mesa ID: {mesa_id}"
            )
        # An index reference is link metadata, not a path template.  Never
        # manufacture a document endpoint from a relative reference.
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise DocumentIndexError(
                "official document reference must be an explicit absolute HTTPS URL"
            )
        official_url = url
        # A compromised index must not become a public outbound-link source.
        policy.check(official_url)
        key = (mesa_id, document_type, official_url)
        digest = hashlib.sha256("\x1f".join(key).encode()).hexdigest()[:24]
        entries[key] = DocumentIndexEntry(
            id=f"doc-{digest}",
            mesa_id=mesa_id,
            document_type=document_type,
            official_url=official_url,
            source_index_url=source_index_url,
            source_index_hash=index_hash,
        )
    return tuple(sorted(entries.values(), key=lambda entry: entry.id))
