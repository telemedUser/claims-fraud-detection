"""Regression tests for the known defects listed in the requirements introduction (defects 1-3, 6-9).

Each defect has an explicit test here. Deeper coverage lives in test_customer_wording, test_assess_gate,
test_ratelimit and test_forensics_properties.
"""
import asyncio
import hashlib
import io
import json
from datetime import date, datetime, timedelta

import pytest
from pypdf import PdfWriter

from app import jobs, ratelimit
from app.api import customer_view
from app.agents.claimant_profile import ClaimantProfileAgent
from app.agents.document_scan import DocumentScanAgent
from app.agents.invoice_check import InvoiceCheckAgent
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Invoice, LineItem
from tests.db_state import db_snapshot

ADMISSION = date(2026, 3, 1)
LOOKUP = {"policy_number": "POL-1001", "date_of_birth": "1992-04-18"}


def _claim(tax_id=None, invoice_number="INV-REG-1") -> Claim:
    return Claim(claim_id="CLM-REG-1", claimant_id="U001", claimant_name="A. Kumar", hospital_id="H001",
                 doctor_id="D001", diagnosis="Acute appendicitis", admission_date=ADMISSION,
                 discharge_date=ADMISSION + timedelta(days=4), claimed_amount=45000, policy_number="POL-1001",
                 disease_id="appendicitis",
                 invoice=Invoice(invoice_number=invoice_number, invoice_date=ADMISSION + timedelta(days=4),
                                 total=45000, tax_id=tax_id,
                                 line_items=[LineItem(description="Room", amount=15000),
                                             LineItem(description="Surgery", amount=30000)]))


def _run(agent, claim, docs=()):
    return asyncio.run(agent.analyze(claim, list(docs)))


# ---- defect 1: "Verified" wording -------------------------------------------------------------
def test_defect1_customer_report_never_says_verified():
    for score in (0, 5, 29, 30, 80):
        for agent in ("provider_profile", "claimant_profile", "document_scan", "invoice_check"):
            assert "verified" not in customer_view.check_outcome(agent, score).lower()
    assert "verified" not in json.dumps(customer_view.OUTCOMES).lower()
    assert "verified" not in json.dumps(customer_view.CUSTOMER_LABELS).lower()
    assert not hasattr(customer_view, "VERIFIED_BELOW")
    # simulated registries are always labelled as such, even for a clean score
    assert customer_view.check_outcome("provider_profile", 0) == "simulated"


# ---- defect 2: TAX_ID_MISSING ----------------------------------------------------------------
@pytest.mark.parametrize("tax_id", [None, "27AAACC1111A1ZQ"])
def test_defect2_missing_tax_id_is_not_a_finding(tax_id):
    from app.agents.provider_profile import ProviderProfileAgent
    claim = _claim(tax_id=tax_id)
    for agent in (InvoiceCheckAgent(), ClaimantProfileAgent(), ProviderProfileAgent()):
        assert "TAX_ID_MISSING" not in {f.code for f in _run(agent, claim).findings}


def test_defect2_wrong_tax_id_still_flagged_by_one_agent():
    from app.agents.provider_profile import ProviderProfileAgent
    codes = [f.code for f in _run(ProviderProfileAgent(), _claim(tax_id="29ZZZZZ9999Z9Z9")).findings]
    assert codes.count("TAX_ID_MISMATCH") == 1
    assert "TAX_ID_MISMATCH" not in {f.code for f in _run(InvoiceCheckAgent(), _claim(tax_id="29ZZZZZ9999Z9Z9")).findings}


# ---- defect 3: duplicate invoice counted once -------------------------------------------------
def test_defect3_duplicate_invoice_yields_one_finding_across_agents():
    earlier = _claim(invoice_number="INV-REG-DUP")
    earlier.claim_id = "CLM-EARLIER"
    with open_repos() as repos:
        repos.register_claim(earlier, [])
    later = _claim(invoice_number="INV-REG-DUP")
    findings = _run(InvoiceCheckAgent(), later).findings + _run(ClaimantProfileAgent(), later).findings
    dupes = [f for f in findings if f.code in ("DUPLICATE_INVOICE", "REPEATED_INVOICE_NUMBER")]
    assert [f.code for f in dupes] == ["DUPLICATE_INVOICE"]


def test_defect3_new_invoice_number_has_no_duplicate_finding():
    findings = _run(InvoiceCheckAgent(), _claim(invoice_number="INV-REG-FRESH")).findings
    assert not [f for f in findings if "DUPLICATE_INVOICE" in f.code or "REPEATED_INVOICE" in f.code]


# ---- defect 6: LLM flag is server controlled --------------------------------------------------
def _submission() -> dict:
    return {"policy_number": "POL-1001", "date_of_birth": "1992-04-18", "hospital_id": "H001", "doctor_id": "D001",
            "disease_id": "appendicitis", "admission_date": "2026-03-01", "discharge_date": "2026-03-05",
            "claimed_amount": 45000,
            "invoice": {"invoice_number": "INV-REG-LLM", "invoice_date": "2026-03-05", "total": 45000,
                        "line_items": [{"description": "Room", "amount": 15000},
                                       {"description": "Surgery", "amount": 30000}]}}


def _submit_and_get_use_llm(client, monkeypatch, client_flag: str) -> bool:
    async def _noop(*a, **k):  # keep the background task from calling any LLM
        return None
    monkeypatch.setattr(jobs, "_process", _noop)
    r = client.post("/api/claims", data={"payload": json.dumps(_submission()), "use_llm": client_flag,
                                         "document_types": '["medical_bill"]'},
                    files=[("documents", ("bill.txt", b"bill", "text/plain"))])
    assert r.status_code == 202, r.text
    return jobs.JOBS[r.json()["claim_id"]]["use_llm"]


def test_defect6_client_cannot_enable_llm_when_server_disabled(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")
    assert _submit_and_get_use_llm(client, monkeypatch, "true") is False


def test_defect6_client_cannot_disable_llm_when_server_enabled(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-not-used")
    monkeypatch.delenv("LLM_REVIEW_ENABLED", raising=False)
    assert _submit_and_get_use_llm(client, monkeypatch, "false") is True


def test_defect6_server_flag_turns_llm_off(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-not-used")
    monkeypatch.setenv("LLM_REVIEW_ENABLED", "false")
    assert _submit_and_get_use_llm(client, monkeypatch, "true") is False


# ---- defect 7: /api/assess gate ---------------------------------------------------------------
def _assess(client, headers=None):
    claim = _claim().model_dump(mode="json")
    return client.post("/api/assess", headers=headers or {},
                       data={"claim": json.dumps(claim), "use_llm": "false", "document_types": '["medical_bill"]'},
                       files=[("documents", ("bill.txt", b"Hospital bill", "text/plain"))])


def test_defect7_assess_rejects_anonymous_and_writes_no_history():
    from fastapi.testclient import TestClient
    from app.main import app
    before = db_snapshot()
    with TestClient(app) as c:
        assert _assess(c).status_code == 401
        assert _assess(c, {"Authorization": "Bearer wrong"}).status_code == 401
    assert db_snapshot() == before


def test_defect7_assess_with_token_skips_history(client, auth_headers):
    before = db_snapshot()
    assert _assess(client, auth_headers("Investigator")).status_code == 200
    assert db_snapshot() == before


# ---- defect 8: lookup rate limit --------------------------------------------------------------
def test_defect8_lookup_returns_429_over_rate_and_not_under(client, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATE", "3/minute")
    ratelimit.reset_lookup_limiter()
    for _ in range(3):
        assert client.post("/api/policies/lookup", json=LOOKUP).status_code == 200
    r = client.post("/api/policies/lookup", json=LOOKUP)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


# ---- defect 9: forensics rules ----------------------------------------------------------------
def _pdf(meta: dict) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    w.add_metadata(meta)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _pdf_date(dt: datetime) -> str:
    return dt.strftime("D:%Y%m%d%H%M%S")


def _scan_codes(meta: dict, doc_type: str) -> set[str]:
    data = _pdf(meta)
    doc = DocumentInfo(filename="f.pdf", content_type="application/pdf", size=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=doc_type)
    return {f.code for f in _run(DocumentScanAgent(), _claim(), [doc]).findings}


@pytest.mark.parametrize("producer,expected", [
    ("Adobe Photoshop 25.0", True),
    ("Microsoft Word", True),
    ("Password Manager Export", False),      # contains "word" as a substring
    ("Libreoffice Exporter Plugin", False),  # contains an editor name as a substring
    ("Hospital Billing System 4.2", False),
])
def test_defect9_editor_software_is_exact_match(producer, expected):
    assert ("EDITING_SOFTWARE" in _scan_codes({"/Producer": producer}, "medical_bill")) is expected


@pytest.mark.parametrize("doc_type,expected", [
    ("medical_bill", True), ("other", True), ("prescription", False), ("medical_report", False),
])
def test_defect9_created_before_admission_depends_on_document_type(doc_type, expected):
    meta = {"/CreationDate": _pdf_date(datetime(2026, 2, 1, 9, 0))}
    assert ("DOC_CREATED_BEFORE_ADMISSION" in _scan_codes(meta, doc_type)) is expected


def test_defect9_created_on_or_after_admission_does_not_trigger():
    meta = {"/CreationDate": _pdf_date(datetime(2026, 3, 2, 9, 0))}
    assert "DOC_CREATED_BEFORE_ADMISSION" not in _scan_codes(meta, "medical_bill")


def test_defect9_modification_gap_thresholds():
    created = datetime(2026, 3, 2, 9, 0)

    def meta(hours):
        return {"/CreationDate": _pdf_date(created), "/ModDate": _pdf_date(created + timedelta(hours=hours))}
    # bills: 1h threshold; 90 minutes triggers, 30 minutes does not
    assert "MODIFIED_AFTER_CREATION" in _scan_codes(meta(1.5), "medical_bill")
    assert "MODIFIED_AFTER_CREATION" not in _scan_codes(meta(0.5), "medical_bill")
    # prescriptions: 24h threshold; 2h does not trigger, 48h does
    assert "MODIFIED_AFTER_CREATION" not in _scan_codes(meta(2), "prescription")
    assert "MODIFIED_AFTER_CREATION" in _scan_codes(meta(48), "prescription")


def test_defect9_metadata_findings_are_low_or_medium_with_alternative_explanations():
    created = datetime(2026, 2, 1, 9, 0)
    meta = {"/Producer": "Adobe Photoshop", "/CreationDate": _pdf_date(created),
            "/ModDate": _pdf_date(created + timedelta(days=3))}
    data = _pdf(meta)
    doc = DocumentInfo(filename="f.pdf", content_type="application/pdf", size=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type="medical_bill")
    found = [f for f in _run(DocumentScanAgent(), _claim(), [doc]).findings
             if f.code in {"EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION"}]
    assert {f.code for f in found} == {"EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION"}
    assert all(f.severity in ("low", "medium") for f in found)
    assert all("alternative explanations" in f.detail for f in found)
