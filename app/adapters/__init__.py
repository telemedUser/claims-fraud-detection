"""Adapter factory. Selection comes from settings; implementations are imported lazily so
cloud SDKs load only when selected. Core packages depend on the ports, never on SDKs."""
from __future__ import annotations

import importlib
from typing import Any

from app.adapters.errors import AdapterError, AdapterUnavailable

# kind -> (setting attribute, env var, {name: "module:Class"})
REGISTRY: dict[str, tuple[str, str, dict[str, str]]] = {
    "storage": ("storage_adapter", "STORAGE_ADAPTER", {"local": "app.adapters.storage.local_fs:LocalFsStorage"}),
    "llm": ("llm_adapter", "LLM_ADAPTER", {"local": "app.adapters.llm.local:LocalLlm"}),
    "extraction": ("extraction_adapter", "EXTRACTION_ADAPTER", {"local": "app.adapters.extraction.pypdf_ext:PypdfExtraction"}),
    "queue": ("queue_adapter", "QUEUE_ADAPTER", {"local": "app.adapters.queue.postgres:PostgresQueue"}),
    "hospital": ("hospital_adapter", "HOSPITAL_ADAPTER", {"local": "app.adapters.hospital.local:LocalHospital"}),
}


def _build(kind: str) -> Any:
    from app.settings import get_settings

    attr, env, impls = REGISTRY[kind]
    name = str(getattr(get_settings(), attr)).strip().lower()
    target = impls.get(name)
    if target is None:
        raise AdapterUnavailable(f"Unknown {env} value {name!r}; supported: {', '.join(sorted(impls))}")
    module_name, _, cls_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and (module_name == exc.name or module_name.startswith(exc.name + ".")):
            raise AdapterUnavailable(f"{env}={name!r} is not implemented yet") from None
        raise AdapterUnavailable(f"{env}={name!r} requires a missing dependency: {exc.name}") from None
    return getattr(module, cls_name)()


def get_storage() -> Any:
    return _build("storage")


def get_llm() -> Any:
    return _build("llm")


def get_extraction() -> Any:
    return _build("extraction")


def get_queue() -> Any:
    return _build("queue")


def get_hospital() -> Any:
    return _build("hospital")


__all__ = [
    "AdapterError",
    "AdapterUnavailable",
    "get_storage",
    "get_llm",
    "get_extraction",
    "get_queue",
    "get_hospital",
]
