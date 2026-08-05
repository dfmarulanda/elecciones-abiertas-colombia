"""Atomic current-release pointer operations; manifests are never rewritten."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class PointerError(ValueError):
    pass


@dataclass(frozen=True)
class CurrentReleasePointer:
    release_id: str
    manifest_path: str
    activated_at: str
    synthetic: bool

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        manifest_path: str,
        synthetic: bool,
        activated_at: datetime | None = None,
    ) -> CurrentReleasePointer:
        timestamp = activated_at or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise PointerError("activated_at must be timezone-aware")
        return cls(
            release_id=release_id,
            manifest_path=manifest_path,
            activated_at=timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            synthetic=synthetic,
        )


def _validate(pointer: CurrentReleasePointer) -> None:
    if not pointer.release_id or not pointer.manifest_path or not pointer.activated_at:
        raise PointerError("release_id, manifest_path, and activated_at are required")
    if pointer.manifest_path.startswith("/") or ".." in Path(pointer.manifest_path).parts:
        raise PointerError("manifest_path must be a relative immutable path")


def _swap(path: Path, pointer: CurrentReleasePointer) -> None:
    _validate(pointer)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(asdict(pointer), sort_keys=True, separators=(",", ":")),
            "utf-8",
        )
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def activate_current_release(path: Path, pointer: CurrentReleasePointer) -> None:
    """Atomically expose a validated immutable manifest as current."""
    _swap(path, pointer)


def rollback_current_release(path: Path, previous: CurrentReleasePointer) -> None:
    """Atomically repoint current to a previously verified immutable release."""
    _swap(path, previous)
