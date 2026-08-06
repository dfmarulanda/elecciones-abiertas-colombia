from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from elecciones_pipeline.registry.log import (
    GENESIS_PREV_HASH,
    LOG_SCHEMA,
    AppendOnlyLog,
    RegistryError,
    merkle_root,
    verify_log_file,
)
from elecciones_pipeline.registry.store import canonical_json_bytes, canonical_json_digest

DIGESTS = tuple(hashlib.sha256(str(index).encode()).hexdigest() for index in range(8))


def _log(tmp_path: Path) -> AppendOnlyLog:
    return AppendOnlyLog(tmp_path / "declarations.jsonl", log_id="presidencia-2026-r2")


def _append(log: AppendOnlyLog, index: int, kind: str = "analyzer_artifact") -> None:
    log.append(
        kind=kind,
        content_hash=DIGESTS[index],
        declared_by="pipeline",
        statement=f"declaration {index}",
        recorded_at=f"2026-08-0{index + 1}T00:00:00+00:00",
    )


def test_entries_chain_from_genesis_and_bind_their_own_hash(tmp_path: Path) -> None:
    log = _log(tmp_path)
    assert log.entries() == ()
    assert log.head_hash() == GENESIS_PREV_HASH

    _append(log, 0, kind="input_bundle")
    _append(log, 1, kind="family_roster")
    _append(log, 2)

    entries = log.entries()
    assert [entry.seq for entry in entries] == [0, 1, 2]
    assert entries[0].prev_entry_hash == GENESIS_PREV_HASH
    assert entries[1].prev_entry_hash == entries[0].entry_hash
    assert entries[2].prev_entry_hash == entries[1].entry_hash
    assert log.head_hash() == entries[2].entry_hash
    # entry_hash is over the entry, never over itself.
    assert "entry_hash" not in entries[0].payload()
    assert entries[0].entry_hash == canonical_json_digest(entries[0].payload())
    assert not verify_log_file(log.path)


def test_editing_any_past_entry_breaks_every_entry_after_it(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for index in range(4):
        _append(log, index)
    original = log.entries()

    lines = log.path.read_bytes().splitlines()
    tampered = json.loads(lines[1])
    tampered["content_hash"] = DIGESTS[7]
    lines[1] = canonical_json_bytes(tampered)
    log.path.write_bytes(b"\n".join(lines) + b"\n")

    # The rewritten line's own hash no longer binds its fields.
    findings = verify_log_file(log.path)
    assert findings and "entry_hash does not bind its fields" in findings[0]

    # A forger who also recomputes that hash still breaks the forward chain.
    tampered["entry_hash"] = canonical_json_digest(
        {key: value for key, value in tampered.items() if key != "entry_hash"}
    )
    lines[1] = canonical_json_bytes(tampered)
    log.path.write_bytes(b"\n".join(lines) + b"\n")
    findings = verify_log_file(log.path)
    assert [finding for finding in findings if "does not chain to its predecessor" in finding]
    assert original[1].content_hash == DIGESTS[1]


def test_appending_never_rewrites_what_is_already_there(tmp_path: Path) -> None:
    log = _log(tmp_path)
    _append(log, 0)
    first_bytes = log.path.read_bytes()
    _append(log, 1)
    grown = log.path.read_bytes()

    assert grown.startswith(first_bytes)
    assert len(grown) > len(first_bytes)


def test_merkle_root_is_domain_separated_and_covers_a_prefix(tmp_path: Path) -> None:
    assert merkle_root([]) == hashlib.sha256(b"").hexdigest()
    # A single leaf is not its own entry hash: leaves are prefixed, so an
    # interior node can never be replayed as a leaf.
    assert merkle_root([DIGESTS[0]]) != DIGESTS[0]
    assert merkle_root([DIGESTS[0]]) == hashlib.sha256(
        b"\x00" + bytes.fromhex(DIGESTS[0])
    ).hexdigest()
    assert merkle_root(DIGESTS[:4]) != merkle_root(DIGESTS[:3])
    assert merkle_root(DIGESTS[:3]) != merkle_root(tuple(reversed(DIGESTS[:3])))

    log = _log(tmp_path)
    for index in range(5):
        _append(log, index)
    entries = log.entries()
    checkpoint = log.checkpoint(computed_at="2026-08-06T00:00:00+00:00")
    prefix = log.checkpoint(computed_at="2026-08-06T00:00:00+00:00", tree_size=3)

    assert checkpoint.tree_size == 5
    assert checkpoint.root_hash == merkle_root([entry.entry_hash for entry in entries])
    assert checkpoint.head_entry_hash == entries[-1].entry_hash
    assert prefix.root_hash == merkle_root([entry.entry_hash for entry in entries[:3]])
    assert prefix.root_hash != checkpoint.root_hash
    assert checkpoint.anchor_line().split(" ") == [
        LOG_SCHEMA,
        "presidencia-2026-r2",
        "5",
        checkpoint.root_hash,
    ]
    with pytest.raises(RegistryError, match="cannot checkpoint"):
        log.checkpoint(computed_at="2026-08-06T00:00:00+00:00", tree_size=6)


def test_a_recorded_checkpoint_is_recomputed_from_the_bytes_before_it(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for index in range(3):
        _append(log, index)
    checkpoint, entry = log.append_checkpoint(
        declared_by="release-governance", recorded_at="2026-08-06T00:00:00+00:00"
    )

    assert entry.kind == "checkpoint"
    assert entry.seq == 3
    assert entry.content_hash == checkpoint.checkpoint_hash
    assert entry.statement == checkpoint.anchor_line()
    assert not verify_log_file(log.path)

    # Deleting an entry the checkpoint already committed to is detectable by
    # anyone holding the anchored root, even without the removed line.
    lines = log.path.read_bytes().splitlines()
    log.path.write_bytes(b"\n".join(lines[:1] + lines[2:]) + b"\n")
    findings = verify_log_file(log.path)
    assert any("does not chain to its predecessor" in finding for finding in findings)
    assert any("does not commit to entries before it" in finding for finding in findings)


def test_malformed_entries_are_refused_at_the_boundary(tmp_path: Path) -> None:
    log = _log(tmp_path)
    with pytest.raises(RegistryError, match="unknown log entry kind"):
        log.append(
            kind="invented_kind",
            content_hash=DIGESTS[0],
            declared_by="pipeline",
            statement="x",
            recorded_at="2026-08-06T00:00:00+00:00",
        )
    with pytest.raises(RegistryError, match="not a lowercase sha256 digest"):
        log.append(
            kind="predeclaration",
            content_hash="nope",
            declared_by="pipeline",
            statement="x",
            recorded_at="2026-08-06T00:00:00+00:00",
        )
    with pytest.raises(RegistryError, match="need a declarer"):
        log.append(
            kind="predeclaration",
            content_hash=DIGESTS[0],
            declared_by="",
            statement="x",
            recorded_at="2026-08-06T00:00:00+00:00",
        )
    assert log.entries() == ()
    assert verify_log_file(tmp_path / "absent.jsonl") == (
        f"log {tmp_path / 'absent.jsonl'} does not exist",
    )
