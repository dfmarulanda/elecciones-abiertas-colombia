"""Write-once, content-addressed blob store.

Every object is stored at ``objects/<sha256[0:2]>/<sha256>`` and its digest is
recomputed from the bytes on the way in and on the way out.  The filename is
never trusted: it is the one part of the layout that anything with write access
to the directory controls for free.

There is deliberately no delete, no overwrite and no rename in this module's
API.  That is not an oversight and it is not "we simply never call it": a
registry whose API can unsay something is a registry whose absence of an object
proves nothing, and the point of storing an artifact here is that a later
verifier can tell the difference between "was never declared" and "was declared
and then withdrawn".  Retiring an object is expressed by appending a superseding
statement to the log, not by removing bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

DIGEST_ALGORITHM = "sha256"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FANOUT = 2


class RegistryError(ValueError):
    """A registry invariant has been violated."""


def digest_bytes(data: bytes) -> str:
    """Content address for exact bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Encode a value the one way the whole registry agrees to hash it."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_digest(value: object) -> str:
    return digest_bytes(canonical_json_bytes(value))


def require_digest(value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RegistryError(f"not a lowercase sha256 digest: {value!r}")
    return value


class ContentAddressedStore:
    """An append-only object store addressed by the sha256 of its contents."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._objects = self._root / "objects"
        self._objects.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, digest: str) -> Path:
        checked = require_digest(digest)
        return self._objects / checked[:_FANOUT] / checked

    def contains(self, digest: str) -> bool:
        return self.path_for(digest).is_file()

    def put(self, data: bytes) -> str:
        """Store exact bytes and return their digest.

        Idempotent: storing identical bytes twice is a no-op that returns the
        same digest.  Storing different bytes under an existing digest cannot
        happen by construction, but if the file on disk no longer hashes to its
        own name, that is reported rather than silently repaired.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise RegistryError("only bytes can be stored")
        payload = bytes(data)
        digest = digest_bytes(payload)
        path = self.path_for(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError:
            # Already stored.  ``get`` re-hashes what is on disk, so an
            # idempotent re-put still refuses to succeed over a corrupt object.
            self.get(digest)
            return digest
        try:
            written = 0
            while written < len(payload):
                written += os.write(handle, payload[written:])
            os.fsync(handle)
        finally:
            os.close(handle)
        self._fsync_directory(path.parent)
        # Re-read rather than trust the write: the digest is the only thing
        # that makes this store meaningful, so it is confirmed against the
        # bytes that actually landed on disk.
        if self.get(digest) != payload:
            raise RegistryError(f"object {digest} did not survive the write intact")
        return digest

    def put_json(self, value: object) -> str:
        return self.put(canonical_json_bytes(value))

    def get(self, digest: str) -> bytes:
        path = self.path_for(digest)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise RegistryError(f"object {digest} is not in the store") from None
        actual = digest_bytes(data)
        if actual != digest:
            raise RegistryError(f"object {digest} hashes to {actual}: the store is corrupt")
        return data

    def get_json(self, digest: str) -> object:
        try:
            return json.loads(self.get(digest).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RegistryError(f"object {digest} is not canonical JSON: {exc}") from exc

    def digests(self) -> tuple[str, ...]:
        return tuple(sorted(self._walk()))

    def verify(self) -> tuple[str, ...]:
        """Re-hash every object; return findings for anything that disagrees."""
        findings: list[str] = []
        for name in sorted(self._walk()):
            path = self.path_for(name)
            actual = digest_bytes(path.read_bytes())
            if actual != name:
                findings.append(f"object {name} hashes to {actual}")
            if path.parent.name != name[:_FANOUT]:
                findings.append(f"object {name} is filed under {path.parent.name}")
        return tuple(findings)

    def _walk(self) -> Iterator[str]:
        for prefix in self._objects.iterdir():
            if not prefix.is_dir():
                continue
            for path in prefix.iterdir():
                if path.is_file() and _SHA256.fullmatch(path.name):
                    yield path.name

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        handle = os.open(path, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
