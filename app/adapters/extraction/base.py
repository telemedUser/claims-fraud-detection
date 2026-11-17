"""Extraction port: bytes of a document -> per-page text, fields and file metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.adapters.errors import AdapterError


class ExtractionError(AdapterError):
    """The document could not be read."""


@dataclass
class ExtractionOutput:
    pages: list[dict[str, Any]] = field(default_factory=list)  # [{page, text}], page is 1-based
    fields: list[dict[str, Any]] = field(default_factory=list)  # [{name, value, page, confidence}]
    metadata: dict[str, Any] = field(default_factory=dict)


class ExtractionPort(Protocol):
    name: str

    def extract(self, data: bytes, content_type: str | None = None) -> ExtractionOutput: ...
