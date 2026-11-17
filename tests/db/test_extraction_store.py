import io

from pypdf import PdfWriter
from sqlalchemy import select

from app.adapters.extraction.pypdf_ext import PypdfExtraction
from app.db import models
from app.db.extraction import store_extraction
from app.db.session import get_session
from app.seed import docgen


def _claim_and_doc(s):
    claim = models.Claim()
    s.add(claim)
    s.flush()
    doc = models.Document(claim_id=claim.id, doc_type="medical_bill", storage_key="k", sha256="a" * 64)
    s.add(doc)
    s.flush()
    return claim, doc


def test_store_bill_rows_and_replacement():
    case = docgen.build_case("clean")
    out = PypdfExtraction().extract(docgen.render(case, "medical_bill"))
    with get_session() as s:
        claim, doc = _claim_and_doc(s)
        results, facts = store_extraction(s, claim_id=claim.id, document_id=doc.id, adapter="pypdf", output=out)
        assert len(results) == len(out.pages)
        assert results[0].metadata_["producer"] == "CGH Hospital Information System v4.2"
        by = {f.field: f for f in facts}
        assert by["invoice_number"].original_value == case["invoice_number"]
        assert by["invoice_date"].normalised_value == case["bill_date"].isoformat()
        assert by["invoice_date"].original_value == case["bill_date"].strftime("%d-%b-%Y")
        assert by["invoice_date"].page == 1
        # storing again replaces rather than duplicates
        store_extraction(s, claim_id=claim.id, document_id=doc.id, adapter="pypdf", output=out)
        n = len(s.scalars(select(models.ExtractionResult).where(models.ExtractionResult.document_id == doc.id)).all())
        m = len(s.scalars(select(models.NormalisedFact).where(models.NormalisedFact.document_id == doc.id)).all())
        assert n == len(out.pages) and m == len(out.fields)


def test_store_blank_pdf_has_empty_text_and_no_facts():
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    w.write(buf)
    out = PypdfExtraction().extract(buf.getvalue())
    with get_session() as s:
        claim, doc = _claim_and_doc(s)
        results, facts = store_extraction(s, claim_id=claim.id, document_id=doc.id, adapter="pypdf", output=out)
        assert [r.text.strip() for r in results] == [""] and facts == []
