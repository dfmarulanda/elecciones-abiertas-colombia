"""Plan scrutiny downloads from one official index snapshot.

The scrutiny service publishes an object whose keys are directory prefixes and
whose values are the corresponding filenames.  This module deliberately does
not discover, fetch, or guess any additional URLs: every plan entry is the
concatenation of exactly one published key/value pair.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class ScrutinyManifestError(ValueError):
    """The official index cannot safely be converted into a download plan."""


@dataclass(frozen=True)
class ScrutinyPlanEntry:
    """One explicitly published scrutiny resource."""

    source_url: str
    source_path: str
    category: str


_SCRUTINY_PREFIX = ("data", "esc", "v1")


def _require_https_base(base_url: str) -> tuple[str, str]:
    if not isinstance(base_url, str) or not base_url:
        raise ScrutinyManifestError("scrutiny base URL must be a non-empty HTTPS URL")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ScrutinyManifestError(
            "scrutiny base URL must be an HTTPS URL without credentials, query, or fragment"
        )
    if parsed.path and not parsed.path.endswith("/"):
        raise ScrutinyManifestError("scrutiny base URL path must end with a slash")
    base_path = parsed.path or "/"
    _path_parts(
        base_path.strip("/") if base_path != "/" else "",
        "scrutiny base URL path",
        allow_empty=True,
    )
    return parsed.netloc, base_path


def _path_parts(value: str, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    """Accept only an already-normalised relative URL path."""
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ScrutinyManifestError(f"{label} must be a non-empty relative path")
    if value != value.strip() or "\\" in value or "%" in value:
        raise ScrutinyManifestError(f"{label} is not a normalised relative path")
    parsed = urlsplit(value)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path != value
        or value.startswith("/")
    ):
        raise ScrutinyManifestError(f"{label} must be a relative path without query or fragment")
    if not value:
        return ()
    parts = tuple(value.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise ScrutinyManifestError(f"{label} is not a normalised relative path")
    if any(any(ord(character) < 32 or character.isspace() for character in part) for part in parts):
        raise ScrutinyManifestError(f"{label} contains whitespace or control characters")
    return parts


def _entry_path(prefix: object, filename: object) -> tuple[str, str]:
    if not isinstance(prefix, str) or not prefix.endswith("/"):
        raise ScrutinyManifestError("scrutiny index keys must be directory prefixes ending in '/'")
    prefix_parts = _path_parts(prefix[:-1], "scrutiny index key")
    if prefix_parts[: len(_SCRUTINY_PREFIX)] != _SCRUTINY_PREFIX or len(prefix_parts) == len(
        _SCRUTINY_PREFIX
    ):
        raise ScrutinyManifestError("scrutiny index key must begin with data/esc/v1/<category>/")
    if not isinstance(filename, str) or "/" in filename:
        raise ScrutinyManifestError("scrutiny index values must be single filenames")
    filename_parts = _path_parts(filename, "scrutiny index filename")
    if len(filename_parts) != 1:
        raise ScrutinyManifestError("scrutiny index values must be single filenames")
    return f"{prefix}{filename}", prefix_parts[len(_SCRUTINY_PREFIX)]


def plan_scrutiny_manifest(
    base_url: str, index: Mapping[str, object]
) -> tuple[ScrutinyPlanEntry, ...]:
    """Create a deterministic, exact-pair-only plan from an official index.

    ``base_url`` is the HTTPS directory under which the manifest's relative
    paths live (normally the service origin).  The planner makes no requests.
    Invalid, duplicate, or conflicting published paths fail closed.
    """
    netloc, base_path = _require_https_base(base_url)
    if not isinstance(index, Mapping):
        raise ScrutinyManifestError(
            "scrutiny index must be an object mapping prefixes to filenames"
        )

    entries_by_path: dict[str, ScrutinyPlanEntry] = {}
    filenames_by_prefix: dict[str, object] = {}
    for prefix, filename in index.items():
        previous_filename = filenames_by_prefix.get(prefix)
        if previous_filename is not None:
            if previous_filename == filename:
                raise ScrutinyManifestError(f"duplicate scrutiny index entry: {prefix!r}")
            raise ScrutinyManifestError(f"conflicting scrutiny index entry: {prefix!r}")
        filenames_by_prefix[prefix] = filename
        source_path, category = _entry_path(prefix, filename)
        source_url = urlunsplit(("https", netloc, f"{base_path}{source_path}", "", ""))
        entry = ScrutinyPlanEntry(
            source_url=source_url,
            source_path=source_path,
            category=category,
        )
        previous = entries_by_path.get(source_path)
        if previous is not None:
            if previous == entry:
                raise ScrutinyManifestError(f"duplicate scrutiny index entry: {source_path}")
            raise ScrutinyManifestError(f"conflicting scrutiny index entry: {source_path}")
        entries_by_path[source_path] = entry

    return tuple(
        sorted(
            entries_by_path.values(),
            key=lambda entry: (entry.source_path, entry.source_url, entry.category),
        )
    )
