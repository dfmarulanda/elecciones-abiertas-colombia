from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest
from elecciones_pipeline.registry import store as store_module
from elecciones_pipeline.registry.store import (
    ContentAddressedStore,
    RegistryError,
    canonical_json_bytes,
    digest_bytes,
)


def test_put_is_content_addressed_idempotent_and_verified_on_both_paths(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    payload = b"acta 050010204000009"
    digest = store.put(payload)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert store.path_for(digest) == tmp_path / "objects" / digest[:2] / digest
    assert store.contains(digest)
    assert store.get(digest) == payload
    # Storing the identical bytes again is a no-op, not a second object.
    assert store.put(payload) == digest
    assert store.digests() == (digest,)
    assert not store.verify()


def test_reads_and_sweeps_refuse_an_object_that_no_longer_hashes_to_its_name(
    tmp_path: Path,
) -> None:
    """The filename is the attacker-controlled part of the layout."""
    store = ContentAddressedStore(tmp_path)
    digest = store.put(b"original")
    path = store.path_for(digest)
    path.chmod(0o644)
    path.write_bytes(b"substituted")

    with pytest.raises(RegistryError, match="the store is corrupt"):
        store.get(digest)
    findings = store.verify()
    assert len(findings) == 1 and digest in findings[0]
    # An idempotent re-put of the true bytes must not paper over the damage.
    with pytest.raises(RegistryError, match="the store is corrupt"):
        store.put(b"original")


def test_the_api_surface_has_no_way_to_unsay_a_stored_object() -> None:
    """Absence of deletion is the property, not absence of calls to deletion.

    A store whose API can remove or rewrite an object cannot distinguish "never
    declared" from "declared, then withdrawn", which is the only question a
    later verifier is asking it.
    """
    forbidden = ("delete", "remove", "unlink", "overwrite", "replace", "prune", "rmtree", "purge")
    public = {
        name
        for name, _member in inspect.getmembers(ContentAddressedStore)
        if not name.startswith("_")
    }
    public |= {name for name in vars(store_module) if not name.startswith("_")}
    assert not [name for name in public if any(word in name.lower() for word in forbidden)]

    source = inspect.getsource(store_module)
    assert "os.unlink" not in source and "shutil.rmtree" not in source
    # O_EXCL is what makes a write refuse to clobber an existing object.
    assert "O_EXCL" in source


def test_json_objects_round_trip_through_one_canonical_encoding(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    value = {"b": 2, "a": [1, {"d": 4, "c": 3}]}
    digest = store.put_json(value)

    assert store.get_json(digest) == value
    # Key order in the caller's dict must not change the content address.
    assert store.put_json({"a": [1, {"c": 3, "d": 4}], "b": 2}) == digest
    assert digest == digest_bytes(canonical_json_bytes(value))

    raw = store.put(b"not json")
    with pytest.raises(RegistryError, match="not canonical JSON"):
        store.get_json(raw)


def test_missing_objects_and_malformed_digests_are_rejected(tmp_path: Path) -> None:
    store = ContentAddressedStore(tmp_path)
    with pytest.raises(RegistryError, match="not a lowercase sha256 digest"):
        store.path_for("A" * 64)
    with pytest.raises(RegistryError, match="not a lowercase sha256 digest"):
        store.path_for("abc")
    with pytest.raises(RegistryError, match="not in the store"):
        store.get("e" * 64)
    with pytest.raises(RegistryError, match="only bytes"):
        store.put("a string")  # type: ignore[arg-type]
