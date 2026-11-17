import pytest

from app.adapters.errors import StorageKeyError, StorageNotFound
from app.adapters.storage.base import Storage
from app.adapters.storage.local_fs import LocalFsStorage


def test_put_get_delete_roundtrip(tmp_path):
    s = LocalFsStorage(tmp_path)
    assert isinstance(s, Storage)
    key = s.put(b"hello", "application/pdf")
    parts = key.split("/")
    assert [len(p) for p in parts] == [2, 2, 32]
    assert parts[2].startswith(parts[0] + parts[1])
    assert s.get(key) == b"hello"
    s.delete(key)
    with pytest.raises(StorageNotFound):
        s.get(key)
    s.delete(key)  # no-op


def test_keys_unique_and_no_temp_leftovers(tmp_path):
    s = LocalFsStorage(tmp_path)
    assert s.put(b"a", "x/y") != s.put(b"a", "x/y")
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("key", ["../evil", "ab/cd/../../x", "/etc/passwd", "ab/cd/report.pdf", "", "..\\x", "ab/cd/" + "g" * 32])
def test_rejects_unsafe_keys(tmp_path, key):
    s = LocalFsStorage(tmp_path)
    for op in (s.get, s.delete):
        with pytest.raises(StorageKeyError):
            op(key)


def test_uses_storage_dir_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "root"))
    key = LocalFsStorage().put(b"z", "text/plain")
    assert (tmp_path / "root" / key).read_bytes() == b"z"
