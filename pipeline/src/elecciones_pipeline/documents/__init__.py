"""Index-only E-14 documentary-reference handling.

This namespace deliberately has no document-retrieval or transcription module.
"""

from .index import DocumentIndexError, index_official_documents
from .models import (
    DocumentIndexEntry,
    DocumentProvenance,
    EvidenceDocument,
)
from .policy import DocumentURLPolicy

__all__ = [
    "DocumentIndexEntry",
    "DocumentIndexError",
    "DocumentProvenance",
    "DocumentURLPolicy",
    "EvidenceDocument",
    "index_official_documents",
]
