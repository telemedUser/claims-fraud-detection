"""Local extraction with pypdf (text PDFs) and optional Pillow (image EXIF). No OCR: image-only
files yield empty text."""
from __future__ import annotations

import io
import re
from typing import Any

from app.adapters.extraction.base import ExtractionError, ExtractionOutput

_INVOICE_NO = re.compile(r"(?:Invoice|Bill)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-]{2,40})", re.I)
_DATE = r"(\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{2,4}|\d{4}-\d{2}-\d{2})"
_INVOICE_DATE = re.compile(r"(?:Invoice|Bill)\s*Date\s*[:\-]?\s*" + _DATE, re.I)
_TOTAL = re.compile(r"(?:Amount\s+payable|Grand\s+Total|Total\s+Amount|Total)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
_GSTIN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9])\b", re.I)
_GSTIN_LABELLED = re.compile(r"GSTIN\s*[:\-]?\s*([A-Za-z0-9]{6,20})", re.I)

_IMAGE_TYPES = ("image/jpeg", "image/png", "image/jpg")


def _is_pdf(data: bytes) -> bool:
    return data[:1024].lstrip().startswith(b"%PDF")


def _is_image(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"


def extract_fields(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Best-effort regex extraction; the first match per field name wins."""
    patterns = [("invoice_number", _INVOICE_NO, 0.8), ("invoice_date", _INVOICE_DATE, 0.8),
                ("total", _TOTAL, 0.7), ("gstin", _GSTIN, 0.9), ("gstin", _GSTIN_LABELLED, 0.6)]
    found: dict[str, dict[str, Any]] = {}
    for name, rx, conf in patterns:
        if name in found:
            continue
        for p in pages:
            m = rx.search(p["text"] or "")
            if m:
                found[name] = {"name": name, "value": m.group(1).strip(), "page": p["page"], "confidence": conf}
                break
    return list(found.values())


def _pdf_metadata(reader) -> dict[str, Any]:
    info = reader.metadata
    out: dict[str, Any] = {"format": "pdf", "page_count": len(reader.pages)}
    if info:
        for key, attr in (("producer", "/Producer"), ("creator", "/Creator"), ("creation_date", "/CreationDate"),
                          ("mod_date", "/ModDate"), ("title", "/Title")):
            v = info.get(attr)
            if v is not None:
                out[key] = str(v)
    return out


def _image_metadata(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {"format": "image"}
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow optional
        return out
    try:
        with Image.open(io.BytesIO(data)) as im:
            out["image_format"] = im.format
            out["size"] = list(im.size)
            exif = im.getexif()
            tags = {305: "software", 306: "datetime", 271: "make", 272: "model"}
            for tag, key in tags.items():
                if exif.get(tag) is not None:
                    out[key] = str(exif.get(tag))
    except Exception as exc:
        raise ExtractionError("unreadable image") from exc
    return out


class PypdfExtraction:
    name = "pypdf"

    def extract(self, data: bytes, content_type: str | None = None) -> ExtractionOutput:
        if not data:
            raise ExtractionError("empty document")
        if _is_pdf(data):
            return self._pdf(data)
        if _is_image(data) or (content_type or "").lower() in _IMAGE_TYPES:
            meta = _image_metadata(data)  # raises when not a decodable image
            return ExtractionOutput(pages=[{"page": 1, "text": ""}], fields=[], metadata=meta)
        raise ExtractionError("unsupported or unreadable document")

    def _pdf(self, data: bytes) -> ExtractionOutput:
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [{"page": i, "text": (p.extract_text() or "")} for i, p in enumerate(reader.pages, 1)]
            meta = _pdf_metadata(reader)
        except Exception as exc:
            raise ExtractionError("unreadable PDF") from exc
        return ExtractionOutput(pages=pages, fields=extract_fields(pages), metadata=meta)
