"""Append-only, tamper-evident declaration log.

Each entry names one artifact by content hash and says who declared it and
what they were claiming.  Entries are chained by ``prev_entry_hash``, so any
edit to a past entry invalidates every entry after it, and a Merkle checkpoint
over entries ``[0, n)`` produces a root that can be published somewhere the
project does not control.

That last part is what the log is actually for.  A hash chain kept only by the
party that writes it proves nothing against that party: they can rewrite the
whole file.  The chain makes tampering *detectable by anyone holding an earlier
checkpoint*, which is why :meth:`AppendOnlyLog.checkpoint` exists and why its
root is formatted for external anchoring.  Until a root is anchored somewhere
independent, this file is an audit convenience, not evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .store import RegistryError, canonical_json_bytes, canonical_json_digest, require_digest

LOG_SCHEMA = "elecciones-registry-log-v1"
GENESIS_PREV_HASH = "0" * 64

ENTRY_KINDS = (
    "input_bundle",
    "family_roster",
    "analyzer_artifact",
    "replay_attestation",
    "verifier_policy",
    "predeclaration",
    "checkpoint",
)
_KINDS = frozenset(ENTRY_KINDS)


@dataclass(frozen=True)
class LogEntry:
    """One declaration: an artifact, a declarer, and what is being claimed."""

    seq: int
    prev_entry_hash: str
    kind: str
    content_hash: str
    declared_by: str
    statement: str
    recorded_at: str

    def __post_init__(self) -> None:
        if type(self.seq) is not int or self.seq < 0:
            raise RegistryError("log entry seq must be a non-negative integer")
        if self.kind not in _KINDS:
            raise RegistryError(f"unknown log entry kind: {self.kind!r}")
        require_digest(self.prev_entry_hash)
        require_digest(self.content_hash)
        if not self.declared_by or not self.statement or not self.recorded_at:
            raise RegistryError("log entries need a declarer, a statement, and a timestamp")

    def payload(self) -> dict[str, object]:
        """The hashed body.  ``entry_hash`` is never part of its own preimage."""
        return {
            "content_hash": self.content_hash,
            "declared_by": self.declared_by,
            "kind": self.kind,
            "prev_entry_hash": self.prev_entry_hash,
            "recorded_at": self.recorded_at,
            "seq": self.seq,
            "statement": self.statement,
        }

    @property
    def entry_hash(self) -> str:
        return canonical_json_digest(self.payload())

    def record(self) -> dict[str, object]:
        return {**self.payload(), "entry_hash": self.entry_hash}


def _leaf_hash(entry_hash: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(require_digest(entry_hash))).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(entry_hashes: Sequence[str]) -> str:
    """RFC 6962 Merkle root over entry hashes ``[0, n)``.

    Domain-separated leaves and nodes: without the prefixes an interior node
    can be replayed as a leaf, and a log with n entries can be presented as a
    log with fewer.
    """
    if not entry_hashes:
        return hashlib.sha256(b"").hexdigest()
    level = [_leaf_hash(value) for value in entry_hashes]
    while len(level) > 1:
        pairs = zip(level[::2], level[1::2], strict=False)
        nodes = [_node_hash(left, right) for left, right in pairs]
        if len(level) % 2:
            nodes.append(level[-1])
        level = nodes
    return level[0].hex()


@dataclass(frozen=True)
class Checkpoint:
    """A signed-tree-head-shaped commitment to entries ``[0, tree_size)``."""

    log_id: str
    tree_size: int
    root_hash: str
    head_entry_hash: str
    computed_at: str

    def anchor_line(self) -> str:
        """A single line small enough to publish anywhere.

        Anchoring means putting this string somewhere the project cannot
        rewrite.  Storing it back in this repository anchors nothing.
        """
        return f"{LOG_SCHEMA} {self.log_id} {self.tree_size} {self.root_hash}"

    def payload(self) -> dict[str, object]:
        return {
            "computed_at": self.computed_at,
            "head_entry_hash": self.head_entry_hash,
            "log_id": self.log_id,
            "root_hash": self.root_hash,
            "schema": LOG_SCHEMA,
            "tree_size": self.tree_size,
        }

    @property
    def checkpoint_hash(self) -> str:
        return canonical_json_digest(self.payload())


class AppendOnlyLog:
    """A JSON-lines log that is only ever appended to."""

    def __init__(self, path: Path | str, *, log_id: str) -> None:
        if not log_id:
            raise RegistryError("a log needs an id")
        self._path = Path(path)
        self._log_id = log_id
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def log_id(self) -> str:
        return self._log_id

    def entries(self) -> tuple[LogEntry, ...]:
        """Parse every entry and re-verify its hash and its link."""
        entries = tuple(_parse_records(self._read_lines()))
        findings = verify_entries(entries)
        if findings:
            raise RegistryError(f"log {self._path} is not intact: {findings[0]}")
        return entries

    def tree_size(self) -> int:
        return len(self.entries())

    def head_hash(self) -> str:
        entries = self.entries()
        return entries[-1].entry_hash if entries else GENESIS_PREV_HASH

    def append(
        self,
        *,
        kind: str,
        content_hash: str,
        declared_by: str,
        statement: str,
        recorded_at: str,
    ) -> LogEntry:
        entries = self.entries()
        entry = LogEntry(
            seq=len(entries),
            prev_entry_hash=entries[-1].entry_hash if entries else GENESIS_PREV_HASH,
            kind=kind,
            content_hash=content_hash,
            declared_by=declared_by,
            statement=statement,
            recorded_at=recorded_at,
        )
        line = canonical_json_bytes(entry.record()) + b"\n"
        handle = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            written = 0
            while written < len(line):
                written += os.write(handle, line[written:])
            os.fsync(handle)
        finally:
            os.close(handle)
        return entry

    def checkpoint(self, *, computed_at: str, tree_size: int | None = None) -> Checkpoint:
        entries = self.entries()
        size = len(entries) if tree_size is None else tree_size
        if type(size) is not int or not 0 <= size <= len(entries):
            raise RegistryError(f"cannot checkpoint {size} of {len(entries)} entries")
        covered = entries[:size]
        return Checkpoint(
            log_id=self._log_id,
            tree_size=size,
            root_hash=merkle_root([entry.entry_hash for entry in covered]),
            head_entry_hash=covered[-1].entry_hash if covered else GENESIS_PREV_HASH,
            computed_at=computed_at,
        )

    def append_checkpoint(
        self, *, declared_by: str, recorded_at: str
    ) -> tuple[Checkpoint, LogEntry]:
        """Commit to everything so far, and record that commitment in the log.

        The entry's content hash is the checkpoint artifact's hash, and its
        statement is the anchor line, so a verifier holding only the log can
        recompute the root the checkpoint claimed.
        """
        checkpoint = self.checkpoint(computed_at=recorded_at)
        entry = self.append(
            kind="checkpoint",
            content_hash=checkpoint.checkpoint_hash,
            declared_by=declared_by,
            statement=checkpoint.anchor_line(),
            recorded_at=recorded_at,
        )
        return checkpoint, entry

    def _read_lines(self) -> list[bytes]:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return []
        return [line for line in raw.split(b"\n") if line]


def _parse_records(lines: Sequence[bytes]) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RegistryError(f"log line {index} is not JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise RegistryError(f"log line {index} is not an object")
        try:
            entry = LogEntry(
                seq=record["seq"],
                prev_entry_hash=record["prev_entry_hash"],
                kind=record["kind"],
                content_hash=record["content_hash"],
                declared_by=record["declared_by"],
                statement=record["statement"],
                recorded_at=record["recorded_at"],
            )
        except KeyError as exc:
            raise RegistryError(f"log line {index} is missing {exc}") from exc
        if record.get("entry_hash") != entry.entry_hash:
            raise RegistryError(f"log line {index} entry_hash does not bind its fields")
        entries.append(entry)
    return entries


def verify_entries(entries: Sequence[LogEntry]) -> tuple[str, ...]:
    """Recompute every hash and every link; return findings, not a boolean."""
    findings: list[str] = []
    previous = GENESIS_PREV_HASH
    for index, entry in enumerate(entries):
        if entry.seq != index:
            findings.append(f"entry {index} declares seq {entry.seq}")
        if entry.prev_entry_hash != previous:
            findings.append(f"entry {index} does not chain to its predecessor")
        previous = entry.entry_hash
    for entry in entries:
        if entry.kind != "checkpoint":
            continue
        covered = [item.entry_hash for item in entries[: entry.seq]]
        expected = Checkpoint(
            log_id=_log_id_from_statement(entry.statement),
            tree_size=entry.seq,
            root_hash=merkle_root(covered),
            head_entry_hash=covered[-1] if covered else GENESIS_PREV_HASH,
            computed_at=entry.recorded_at,
        )
        if entry.content_hash != expected.checkpoint_hash:
            findings.append(f"checkpoint at seq {entry.seq} does not commit to entries before it")
        if entry.statement != expected.anchor_line():
            findings.append(f"checkpoint at seq {entry.seq} anchors a different root")
    return tuple(findings)


def _log_id_from_statement(statement: str) -> str:
    parts = statement.split(" ")
    return parts[1] if len(parts) > 2 and parts[0] == LOG_SCHEMA else ""


def verify_log_file(path: Path | str) -> tuple[str, ...]:
    """Verify a log from bytes alone, without trusting any in-memory state."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return (f"log {path} does not exist",)
    lines = [line for line in raw.split(b"\n") if line]
    try:
        entries = _parse_records(lines)
    except RegistryError as exc:
        return (str(exc),)
    return verify_entries(entries)
