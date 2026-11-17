"""Property test for forensics (document metadata) indicators.

Finding has no status field, so "never confirmed" is checked as: severity is never "high"
for metadata indicators (and is capped at MAX_SEVERITY).
"""
import asyncio
import hashlib
import io
from datetime import date, datetime, timedelta

from hypothesis import given, settings, strategies as st
from pypdf import PdfWriter

from app.agents.document_scan import (
    EDITOR_PRODUCERS, MOD_GAP_HOURS, PRE_ADMISSION_EXEMPT_TYPES, DocumentScanAgent,
    is_editor, normalise_producer,
)
from app.models import Claim, DocumentInfo, Invoice

METADATA_CODES = {"EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION", "METADATA_STRIPPED"}
DOC_TYPES = ["medical_bill", "prescription", "medical_report", "other"]
ADMISSION = date(2026, 3, 1)

# ---- strategies -----------------------------------------------------------------------------
_editor_names = st.sampled_from(sorted(EDITOR_PRODUCERS))


@st.composite
def exact_editor_producers(draw):
    """Allow-listed name with random case and an optional version suffix."""
    name = draw(_editor_names)
    name = "".join(c.upper() if draw(st.booleans()) else c for c in name)
    version = draw(st.sampled_from(["", " 25.0", " 2.10.1", " v3", " (Windows)"]))
    return name + version


@st.composite
def decoy_producers(draw):
    """Strings that merely contain an editor name (or are arbitrary text) but are not an exact match."""
    kind = draw(st.sampled_from(["prefix", "suffix", "embedded", "free"]))
    if kind == "free":
        s = draw(st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=30))
    else:
        name = draw(_editor_names)
        extra = draw(st.sampled_from(["password manager", "exporter", "my", "plugin", "pro suite", "x"]))
        s = {"prefix": f"{extra} {name}", "suffix": f"{name} {extra}", "embedded": f"{extra}{name}{extra}"}[kind]
    return s


def _pdf_date(dt: datetime) -> str:
    return dt.strftime("D:%Y%m%d%H%M%S")


@st.composite
def date_pairs(draw):
    created = datetime(2025, 1, 1) + timedelta(seconds=draw(st.integers(0, 3 * 365 * 86400)))
    modified = created + timedelta(seconds=draw(st.integers(0, 10 * 86400)))
    return created, modified


def _pdf_bytes(meta: dict) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    if meta:
        w.add_metadata(meta)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _scan(meta: dict, doc_type: str):
    data = _pdf_bytes(meta)
    doc = DocumentInfo(filename="f.pdf", content_type="application/pdf", size=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=doc_type)
    claim = Claim(claim_id="c", claimant_id="p", claimant_name="n", hospital_id="h", doctor_id="d",
                  diagnosis="x", admission_date=ADMISSION, discharge_date=ADMISSION + timedelta(days=2),
                  claimed_amount=1000, invoice=Invoice(invoice_number="1", invoice_date=ADMISSION,
                                                       line_items=[], total=1000))
    result = asyncio.run(DocumentScanAgent().analyze(claim, [doc]))
    return [f for f in result.findings if f.code in METADATA_CODES]


# ---- properties -----------------------------------------------------------------------------
# Feature: claims-fraud-detection-service, Property 19: Forensics indicators are exact, low severity and never confirmed
@settings(max_examples=100, deadline=None)
@given(producer=exact_editor_producers(), doc_type=st.sampled_from(DOC_TYPES))
def test_allow_listed_producer_fires(producer, doc_type):
    """**Validates: Requirements 13.2**"""
    assert is_editor(producer)
    codes = {f.code for f in _scan({"/Producer": producer}, doc_type)}
    assert "EDITING_SOFTWARE" in codes


# Feature: claims-fraud-detection-service, Property 19: Forensics indicators are exact, low severity and never confirmed
@settings(max_examples=100, deadline=None)
@given(producer=decoy_producers(), doc_type=st.sampled_from(DOC_TYPES))
def test_non_exact_producer_never_fires(producer, doc_type):
    """**Validates: Requirements 13.2**"""
    exact = normalise_producer(producer) in EDITOR_PRODUCERS
    codes = {f.code for f in _scan({"/Producer": producer}, doc_type)}
    assert ("EDITING_SOFTWARE" in codes) == exact


# Feature: claims-fraud-detection-service, Property 19: Forensics indicators are exact, low severity and never confirmed
@settings(max_examples=100, deadline=None)
@given(producer=st.one_of(exact_editor_producers(), decoy_producers()), dates=date_pairs(),
       doc_type=st.sampled_from(DOC_TYPES), with_dates=st.booleans())
def test_metadata_findings_low_severity_and_exemptions(producer, dates, doc_type, with_dates):
    """**Validates: Requirements 13.3, 13.4, 13.5, 20.4**"""
    created, modified = dates
    meta = {"/Producer": producer}
    if with_dates:
        meta["/CreationDate"] = _pdf_date(created)
        meta["/ModDate"] = _pdf_date(modified)
    findings = _scan(meta, doc_type)
    codes = {f.code for f in findings}

    # never confirmed: metadata indicators are at most medium, never high
    assert all(f.severity in ("low", "medium") for f in findings)
    # alternative explanations accompany every date/editor indicator
    for f in findings:
        if f.code != "METADATA_STRIPPED":
            assert "alternative explanations" in f.detail

    # prescriptions and medical reports never raise a before-admission finding
    if doc_type in PRE_ADMISSION_EXEMPT_TYPES:
        assert "DOC_CREATED_BEFORE_ADMISSION" not in codes
    elif with_dates:
        assert ("DOC_CREATED_BEFORE_ADMISSION" in codes) == (created.date() < ADMISSION)

    # modification gap uses the per-type threshold
    if with_dates:
        over = (modified - created).total_seconds() > MOD_GAP_HOURS[doc_type] * 3600
        assert ("MODIFIED_AFTER_CREATION" in codes) == over
    else:
        assert "MODIFIED_AFTER_CREATION" not in codes
