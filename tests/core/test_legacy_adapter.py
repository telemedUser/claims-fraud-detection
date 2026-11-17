"""Unit tests for app.core.legacy_adapter. Requirements 3.1, 3.2, 4.5."""
import re
from pathlib import Path

import pytest

from app.core.finding import (
    DetectionMethod,
    FindingDraft,
    FindingStatus,
    correlation_key,
)
from app.core.legacy_adapter import CODE_MAP, LegacyContext, adapt_finding, adapt_findings
from app.models import Finding as Legacy

AGENTS_DIR = Path(__file__).resolve().parents[2] / "app" / "agents"
AGENT_FILES = ("provider_profile", "claimant_profile", "document_scan", "invoice_check")
CODE_RE = re.compile(r'code="([A-Z_]+)"')


def _agent_codes() -> set[str]:
    codes: set[str] = set()
    for name in AGENT_FILES:
        codes |= set(CODE_RE.findall((AGENTS_DIR / f"{name}.py").read_text(encoding="utf-8")))
    codes.add("AGENT_ERROR")
    return codes


CTX = LegacyContext(invoice_number="INV-1", hospital_id="H1", doctor_id="D1", claim_id="C1")


def test_discovered_codes_are_non_trivial():
    assert len(_agent_codes()) >= 35


@pytest.mark.parametrize("code", sorted(_agent_codes()))
def test_every_agent_code_maps(code):
    assert code in CODE_MAP
    d = adapt_finding(Legacy(code=code, severity="high", detail="f.pdf: something"), CTX)
    assert isinstance(d, FindingDraft)
    assert d.method is DetectionMethod.RULE
    assert d.limitations and d.next_action
    assert d.extracted_values["legacy_code"] == code
    assert d.fact_key.fact_type != "legacy_unmapped"


def test_duplicate_invoice_and_document_reuse():
    d = adapt_finding(Legacy(code="DUPLICATE_INVOICE", severity="high", detail="x"), CTX)
    assert d.agent == "Duplicate_Detection" and d.fact_key.fact_type == "invoice_duplicate"
    r = adapt_finding(Legacy(code="DOCUMENT_REUSED", severity="high", detail="bill.pdf: identical"),
                      LegacyContext(document_hashes={"bill.pdf": "abc"}))
    assert r.agent == "Duplicate_Detection" and r.fact_key.fact_type == "document_reuse"
    assert r.fact_key.subject == ["document", "abc"]


def test_statuses():
    def st(code):
        return adapt_finding(Legacy(code=code, severity="medium", detail="a.pdf: x"), CTX).status

    for c in ("INVOICE_TOTAL_MISMATCH", "CLAIM_VS_INVOICE_MISMATCH", "DATES_INVALID"):
        assert st(c) is FindingStatus.CONFIRMED_RULE_VIOLATION
    for c in ("EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION", "METADATA_STRIPPED"):
        assert st(c) is FindingStatus.POTENTIAL_ANOMALY
    assert st("ROUND_TOTAL") is FindingStatus.INFORMATIONAL
    assert st("AGENT_ERROR") is FindingStatus.INCONCLUSIVE


def test_metadata_severity_capped_at_medium():
    d = adapt_finding(Legacy(code="EDITING_SOFTWARE", severity="high", detail="a.pdf: x"), CTX)
    assert d.severity == "medium"


def test_llm_source_is_ai_and_capped():
    d = adapt_finding(Legacy(code="INVOICE_TOTAL_MISMATCH", severity="high", detail="x", source="llm"), CTX)
    assert d.method is DetectionMethod.AI
    assert d.status is FindingStatus.POTENTIAL_ANOMALY
    assert d.severity == "medium"


def test_unknown_code_generic_mapping():
    d = adapt_finding(Legacy(code="LLM_WEIRD", severity="low", detail="Odd thing", source="llm"),
                      LegacyContext(agent_name="invoice_check"))
    assert d.status is FindingStatus.POTENTIAL_ANOMALY
    assert d.agent == "Billing_Intelligence"
    d2 = adapt_finding(Legacy(code="NEW_THING", severity="low", detail="x"))
    assert d2.agent == "Operational_Intelligence" and d2.status is FindingStatus.POTENTIAL_ANOMALY


def test_same_fact_from_two_agents_correlates():
    a = adapt_finding(Legacy(code="INVOICE_TOTAL_MISMATCH", severity="high", detail="one"), CTX)
    b = adapt_finding(Legacy(code="INVOICE_TOTAL_MISMATCH", severity="medium", detail="two", source="llm"), CTX)
    assert correlation_key(a.fact_key) == correlation_key(b.fact_key)
    other = adapt_finding(Legacy(code="INVOICE_TOTAL_MISMATCH", severity="high", detail="one"),
                          LegacyContext(invoice_number="INV-2", hospital_id="H1"))
    assert correlation_key(a.fact_key) != correlation_key(other.fact_key)


def test_adapt_findings_list():
    out = adapt_findings([Legacy(code="ROUND_TOTAL", severity="low", detail="x")], CTX)
    assert len(out) == 1
