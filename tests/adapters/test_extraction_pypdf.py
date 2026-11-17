import io

import pytest
from pypdf import PdfWriter

from app.adapters import get_extraction
from app.adapters.errors import AdapterError
from app.adapters.extraction.base import ExtractionError
from app.adapters.extraction.pypdf_ext import PypdfExtraction, extract_fields
from app.seed import docgen


def _blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def clean_case():
    return docgen.build_case("clean")


def test_clean_bill_text_fields_and_metadata(clean_case):
    out = PypdfExtraction().extract(docgen.render(clean_case, "medical_bill"), "application/pdf")
    assert len(out.pages) >= 1 and out.pages[0]["page"] == 1
    assert clean_case["invoice_number"] in out.pages[0]["text"]
    by_name = {f["name"]: f for f in out.fields}
    assert by_name["invoice_number"]["value"] == clean_case["invoice_number"]
    assert by_name["invoice_date"]["value"] == clean_case["bill_date"].strftime("%d-%b-%Y")
    assert by_name["gstin"]["value"].upper() == clean_case["bill_tax_id"].upper()
    assert by_name["total"]["value"].replace(",", "").startswith(str(int(clean_case["bill_total"])))
    assert all(set(f) == {"name", "value", "page", "confidence"} for f in out.fields)
    assert out.metadata["producer"] == "CGH Hospital Information System v4.2"
    assert "creation_date" in out.metadata and "mod_date" in out.metadata


def test_blank_page_pdf_has_empty_text_and_no_fields():
    out = PypdfExtraction().extract(_blank_pdf())
    assert [p["text"].strip() for p in out.pages] == [""]
    assert out.fields == []
    assert out.metadata["page_count"] == 1


def test_image_only_file_returns_empty_text():
    pil = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    pil.new("RGB", (8, 8), "white").save(buf, format="PNG")
    out = PypdfExtraction().extract(buf.getvalue(), "image/png")
    assert out.pages == [{"page": 1, "text": ""}]
    assert out.fields == []


@pytest.mark.parametrize("data", [b"", b"not a document", b"%PDF-1.4 garbage"])
def test_unreadable_raises_adapter_error(data):
    with pytest.raises(ExtractionError) as ei:
        PypdfExtraction().extract(data)
    assert isinstance(ei.value, AdapterError)


def test_factory_returns_pypdf():
    assert isinstance(get_extraction(), PypdfExtraction)


def test_extract_fields_first_match_and_page():
    pages = [{"page": 1, "text": "nothing"}, {"page": 2, "text": "Invoice No: AB-12 Total: INR 1,500.50"}]
    got = {f["name"]: f for f in extract_fields(pages)}
    assert got["invoice_number"]["value"] == "AB-12" and got["invoice_number"]["page"] == 2
    assert got["total"]["value"] == "1,500.50"
