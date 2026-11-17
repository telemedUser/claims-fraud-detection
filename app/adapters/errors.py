"""Adapter error types. Messages never contain secret values."""
from __future__ import annotations


class AdapterError(Exception):
    """Base class for adapter failures."""


class AdapterUnavailable(AdapterError):
    """Requested adapter is unknown or not implemented yet."""


class StorageKeyError(AdapterError):
    """Storage key is malformed or unsafe."""


class StorageNotFound(AdapterError):
    """No object exists for the storage key."""
