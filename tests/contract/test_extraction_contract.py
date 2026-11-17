"""Contract tests every extraction implementation must satisfy. Add a factory to FACTORIES to cover a new one."""
from __future__ import annotations

import io

import pytest

from app.adapters.extraction.base import ExtractionError, ExtractionOutput
from app.adapters.extraction.pypdf_ext import PypdfExtraction
from app.seed import docgen

FACTORIES = {
    "pypdf": PypdfExtraction,
}


@pytest.fixture(params=list(FACTORIES))
def extractor(request):
    return FACTORIES[request.param]()


@pytest.fixture(scope="module")
def bill_pdf() -> bytes:
    return docgen.render(docgen.build_case("clean"), "medical_bill")


def _blank_pdf() -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_port_shape(extractor):
    assert isinstance(extractor.name, str) and extractor.name
    assert callable(extractor.extract)


def test_text_pdf_pages_fields_metadata(extractor, bill_pdf):
    out = extractor.extract(bill_pdf, "application/pdf")
    assert isinstance(out, ExtractionOutput)
    assert out.pages
    assert [p["page"] for p in out.pages] == list(range(1, len(out.pages) + 1))
    assert all(isinstance(p["text"], str) for p in out.pages)
    assert any(p["text"].strip() for p in out.pages)
    assert isinstance(out.metadata, dict)
    for f in out.fields:
        assert set(f) >= {"name", "value", "page", "confidence"}
        assert isinstance(f["name"], str) and f["value"] is not None
        assert 1 <= f["page"] <= len(out.pages)
        assert 0.0 <= f["confidence"] <= 1.0


def test_blank_pdf_has_no_text(extractor):
    out = extractor.extract(_blank_pdf(), "application/pdf")
    assert len(out.pages) == 1
    assert out.pages[0]["page"] == 1
    assert out.pages[0]["text"].strip() == ""
    assert isinstance(out.metadata, dict)


def test_image_only_has_no_text(extractor):
    out = extractor.extract(_png(), "image/png")
    assert out.pages
    assert all(p["text"].strip() == "" for p in out.pages)
    assert isinstance(out.metadata, dict)


@pytest.mark.parametrize("data", [b"", b"not a document at all", b"%PDF-1.4 truncated garbage"])
def test_garbage_raises_extraction_error(extractor, data):
    with pytest.raises(ExtractionError):
        extractor.extract(data, "application/pdf")
