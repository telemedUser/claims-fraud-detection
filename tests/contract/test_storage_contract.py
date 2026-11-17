"""Contract tests every Storage implementation must satisfy. Add a factory to FACTORIES to cover a new one."""
from __future__ import annotations

import pytest

from app.adapters.errors import StorageNotFound
from app.adapters.storage.base import Storage
from app.adapters.storage.local_fs import LocalFsStorage

FACTORIES = {
    "local_fs": lambda tmp_path: LocalFsStorage(tmp_path / "store"),
}


@pytest.fixture(params=list(FACTORIES))
def storage(request, tmp_path):
    return FACTORIES[request.param](tmp_path)


def test_implements_protocol(storage):
    assert isinstance(storage, Storage)


def test_round_trip(storage):
    data = b"%PDF-1.4 hello \x00\xff bytes"
    key = storage.put(data, "application/pdf")
    assert isinstance(key, str) and key
    assert storage.get(key) == data


def test_empty_payload_round_trip(storage):
    assert storage.get(storage.put(b"", "application/octet-stream")) == b""


def test_keys_are_distinct_for_identical_content(storage):
    k1 = storage.put(b"same", "text/plain")
    k2 = storage.put(b"same", "text/plain")
    assert k1 != k2
    assert storage.get(k1) == storage.get(k2) == b"same"


def test_get_after_delete_raises_not_found(storage):
    key = storage.put(b"gone", "text/plain")
    storage.delete(key)
    with pytest.raises(StorageNotFound):
        storage.get(key)


def test_delete_is_idempotent(storage):
    key = storage.put(b"x", "text/plain")
    storage.delete(key)
    storage.delete(key)  # second delete is a no-op


def test_delete_leaves_other_objects(storage):
    k1 = storage.put(b"one", "text/plain")
    k2 = storage.put(b"two", "text/plain")
    storage.delete(k1)
    assert storage.get(k2) == b"two"


def test_keys_do_not_embed_client_supplied_names(storage):
    # content type and payload are the only inputs; neither may leak into the generated key
    key = storage.put(b"patient_john_doe.pdf", "application/x-john-doe-report")
    assert "john" not in key.lower() and "doe" not in key.lower()
    assert ".pdf" not in key.lower()
