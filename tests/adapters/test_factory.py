import sys

import pytest

from app import adapters
from app.adapters.errors import AdapterError, AdapterUnavailable
from app.adapters.storage.local_fs import LocalFsStorage


def test_default_storage_is_local(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("STORAGE_ADAPTER", raising=False)
    assert isinstance(adapters.get_storage(), LocalFsStorage)


def test_unknown_name_names_setting(monkeypatch):
    monkeypatch.setenv("STORAGE_ADAPTER", "s3cret-bucket")
    with pytest.raises(AdapterUnavailable) as ei:
        adapters.get_storage()
    assert "STORAGE_ADAPTER" in str(ei.value)
    assert isinstance(ei.value, AdapterError)


def test_default_extraction_is_pypdf(monkeypatch):
    from app.adapters.extraction.pypdf_ext import PypdfExtraction
    monkeypatch.delenv("EXTRACTION_ADAPTER", raising=False)
    assert isinstance(adapters.get_extraction(), PypdfExtraction)


def test_default_queue_is_postgres_queue(monkeypatch):
    from app.adapters.queue.postgres import PostgresQueue
    monkeypatch.setenv("QUEUE_ADAPTER", "local")
    assert isinstance(adapters.get_queue(), PostgresQueue)


@pytest.mark.parametrize("getter", ["get_llm", "get_hospital"])
def test_unimplemented_kinds_raise(getter, monkeypatch):
    for v in ("LLM", "HOSPITAL"):
        monkeypatch.setenv(f"{v}_ADAPTER", "local")
    with pytest.raises(AdapterUnavailable):
        getattr(adapters, getter)()


def test_lazy_import_does_not_load_other_adapters():
    assert "app.adapters.llm.local" not in sys.modules
