"""Adapter from legacy agent findings (app.models.Finding) to FindingDraft.

Pure Python: no I/O. Lets the existing four agents (provider_profile, claimant_profile,
document_scan, invoice_check) keep working while the new core model is adopted.
Requirements 3.1, 3.2, 4.5.

Use case ids are best effort (design: Policy 1-12, Duplicates 13-22, Documents 23-38,
Billing 51-65). 0 means "no matching numbered Use_Case".
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from app.core.finding import (
    AgentName,
    DetectionMethod,
    FactKey,
    FindingDraft,
    FindingStatus,
)
from app.models import Finding as LegacyFinding

CONF = FindingStatus.CONFIRMED_RULE_VIOLATION
POT = FindingStatus.POTENTIAL_ANOMALY
INFO = FindingStatus.INFORMATIONAL
INC = FindingStatus.INCONCLUSIVE

# Subject kinds used to build the fact_key subject.
_INVOICE = "invoice"          # (hospital_id, invoice_number)
_DOCUMENT = "document"        # document sha256 or filename
_CLAIM = "claim"              # claim level, no extra identifiers
_PROVIDER = "provider"        # hospital/doctor, resolved from context


class Mapping_(NamedTuple):
    agent: AgentName
    category: str
    use_case_id: int
    fact_type: str
    status: FindingStatus
    subject: str
    limitations: str
    next_action: str


def _m(agent, category, uc, fact_type, status, subject, limitations, next_action) -> Mapping_:
    return Mapping_(agent, category, uc, fact_type, status, subject, limitations, next_action)


_DOC_ALT = "Metadata can change legitimately when a file is re-saved, converted or reissued."
_DOC_ACT = "Ask the provider for the original document and compare."
_REG_LIM = "Based on the simulated provider registry; not confirmed with the hospital."
_REG_ACT = "Verify the provider details with the hospital or registry."

# code -> mapping. Covers every code produced by the four legacy agents plus AGENT_ERROR.
CODE_MAP: dict[str, Mapping_] = {
    # provider_profile -> Provider_Intelligence
    "HOSPITAL_UNKNOWN": _m("Provider_Intelligence", "provider_registry", 0, "hospital_unknown", POT, _PROVIDER, _REG_LIM, _REG_ACT),
    "HOSPITAL_UNREGISTERED": _m("Provider_Intelligence", "provider_registry", 0, "hospital_unregistered", CONF, _PROVIDER, _REG_LIM, _REG_ACT),
    "HOSPITAL_HIGH_FRAUD_RATE": _m("Provider_Intelligence", "provider_risk", 0, "hospital_high_flag_rate", POT, _PROVIDER, "Historical flag ratio is a statistical indicator only.", "Review the provider's prior flagged claims."),
    "HOSPITAL_NEW": _m("Provider_Intelligence", "provider_risk", 0, "hospital_new", INFO, _PROVIDER, "A new provider is not evidence of fraud.", "No action unless other findings exist."),
    "AMOUNT_OUTLIER_FOR_HOSPITAL": _m("Provider_Intelligence", "provider_risk", 65, "amount_outlier_hospital", POT, _PROVIDER, "Compared with a simple hospital average.", "Compare the claim with the provider's similar claims."),
    "TAX_ID_MISMATCH": _m("Provider_Intelligence", "provider_registry", 0, "tax_id_mismatch", CONF, _PROVIDER, _REG_LIM, "Verify the tax ID with the hospital."),
    "DOCTOR_UNKNOWN": _m("Provider_Intelligence", "provider_registry", 0, "doctor_unknown", POT, _PROVIDER, _REG_LIM, _REG_ACT),
    "DOCTOR_LICENSE_INVALID": _m("Provider_Intelligence", "provider_registry", 0, "doctor_license_invalid", CONF, _PROVIDER, _REG_LIM, "Verify the licence with the medical council."),
    "DOCTOR_NOT_AFFILIATED": _m("Provider_Intelligence", "provider_registry", 0, "doctor_not_affiliated", POT, _PROVIDER, _REG_LIM, "Confirm the doctor's affiliation with the hospital."),
    "DOCTOR_MANY_HOSPITALS": _m("Provider_Intelligence", "provider_risk", 0, "doctor_many_hospitals", INFO, _PROVIDER, "Multiple affiliations are common for consultants.", "No action unless other findings exist."),
    "DOCTOR_HIGH_VOLUME": _m("Provider_Intelligence", "provider_risk", 65, "doctor_high_volume", POT, _PROVIDER, "Volume is compared with a fixed threshold.", "Review the doctor's claim volume against peers."),
    "DOCTOR_HIGH_FRAUD_RATE": _m("Provider_Intelligence", "provider_risk", 0, "doctor_high_flag_rate", POT, _PROVIDER, "Historical flag ratio is a statistical indicator only.", "Review the doctor's prior flagged claims."),
    # claimant_profile -> Customer_Behaviour / Policy_Eligibility
    "CLAIM_FREQUENCY": _m("Customer_Behaviour", "claim_pattern", 0, "claim_frequency", POT, _CLAIM, "Frequent claims can be legitimate.", "Review the claimant's recent claims."),
    "CLAIM_FREQUENCY_EXTREME": _m("Customer_Behaviour", "claim_pattern", 0, "claim_frequency_extreme", POT, _CLAIM, "Frequent claims can be legitimate.", "Review the claimant's recent claims."),
    "AMOUNT_SPIKE": _m("Customer_Behaviour", "claim_pattern", 0, "amount_spike", POT, _CLAIM, "Compared with the claimant's own history only.", "Check whether the treatment explains the higher amount."),
    "HOSPITAL_HOPPING": _m("Customer_Behaviour", "claim_pattern", 0, "hospital_hopping", POT, _CLAIM, "Multiple hospitals can reflect referrals or relocation.", "Review the claimant's hospital history."),
    "REPEATED_SIMILAR_AMOUNTS": _m("Customer_Behaviour", "claim_pattern", 0, "repeated_similar_amounts", POT, _CLAIM, "Similar amounts can result from fixed-price treatments.", "Compare the claims for repeated charges."),
    "HIGH_AMOUNT_SHORT_STAY": _m("Customer_Behaviour", "claim_pattern", 0, "high_amount_short_stay", POT, _CLAIM, "Some day-care procedures are costly.", "Check that the treatment justifies the amount."),
    "DATES_INVALID": _m("Policy_Eligibility", "claim_dates", 1, "dates_invalid", CONF, _CLAIM, "Compares claim dates only.", "Ask the claimant to correct the dates."),
    "LATE_SUBMISSION": _m("Policy_Eligibility", "claim_dates", 2, "late_submission", POT, _CLAIM, "Policy filing deadlines are not loaded.", "Check the policy's filing deadline."),
    # document_scan -> Document_Forensics / Duplicate_Detection
    "NO_DOCUMENTS": _m("Document_Forensics", "document_completeness", 29, "no_documents", CONF, _CLAIM, "No file was available to inspect.", "Request the supporting documents."),
    "MISSING_MEDICAL_BILL": _m("Document_Forensics", "document_completeness", 29, "missing_medical_bill", POT, _CLAIM, "Depends on the document type labels.", "Request the itemised medical bill."),
    "MISSING_MEDICAL_REPORT": _m("Document_Forensics", "document_completeness", 29, "missing_medical_report", POT, _CLAIM, "Depends on the document type labels.", "Request the medical report or discharge summary."),
    "UNEXPECTED_FILE_TYPE": _m("Document_Forensics", "document_integrity", 28, "unexpected_file_type", CONF, _DOCUMENT, "Only PDF, JPEG and PNG are accepted.", "Ask for the document in an accepted format."),
    "PDF_UNREADABLE": _m("Document_Forensics", "document_integrity", 27, "pdf_unreadable", INC, _DOCUMENT, "The file could not be parsed, so it was not inspected.", "Review the file manually or request a new copy."),
    "IMAGE_UNREADABLE": _m("Document_Forensics", "document_integrity", 27, "image_unreadable", INC, _DOCUMENT, "The file could not be parsed, so it was not inspected.", "Review the file manually or request a new copy."),
    "EDITING_SOFTWARE": _m("Document_Forensics", "document_metadata", 23, "doc_editing_software", POT, _DOCUMENT, _DOC_ALT, _DOC_ACT),
    "MODIFIED_AFTER_CREATION": _m("Document_Forensics", "document_metadata", 24, "doc_modified_after_creation", POT, _DOCUMENT, _DOC_ALT, _DOC_ACT),
    "DOC_CREATED_BEFORE_ADMISSION": _m("Document_Forensics", "document_metadata", 25, "doc_created_before_admission", POT, _DOCUMENT, _DOC_ALT, _DOC_ACT),
    "METADATA_STRIPPED": _m("Document_Forensics", "document_metadata", 26, "doc_metadata_stripped", POT, _DOCUMENT, "Many tools remove metadata when exporting or sharing.", _DOC_ACT),
    "DOCUMENT_REUSED": _m("Duplicate_Detection", "duplicate_document", 14, "document_reuse", CONF, _DOCUMENT, "Exact file hash match against earlier claims only.", "Compare with the earlier claim that used this file."),
    # invoice_check -> Billing_Intelligence / Duplicate_Detection
    "INVOICE_TOTAL_MISMATCH": _m("Billing_Intelligence", "invoice_arithmetic", 51, "invoice_total_mismatch", CONF, _INVOICE, "Uses extracted or entered line items.", "Ask the provider to correct the invoice."),
    "CLAIM_VS_INVOICE_MISMATCH": _m("Billing_Intelligence", "invoice_arithmetic", 52, "claim_vs_invoice_mismatch", CONF, _INVOICE, "Compares the claimed amount with the invoice total.", "Ask the claimant to explain the difference."),
    "DUPLICATE_INVOICE": _m("Duplicate_Detection", "duplicate_invoice", 13, "invoice_duplicate", CONF, _INVOICE, "Exact match on hospital and invoice number only.", "Compare with the earlier claim that used this invoice."),
    "INVOICE_DATE_OUT_OF_RANGE": _m("Billing_Intelligence", "invoice_dates", 53, "invoice_date_out_of_range", CONF, _INVOICE, "Compares dates entered on the claim.", "Ask the provider to confirm the invoice date."),
    "ROUND_TOTAL": _m("Billing_Intelligence", "invoice_pattern", 54, "round_total", INFO, _INVOICE, "Round totals are common for package pricing.", "No action unless other findings exist."),
    "DUPLICATE_LINE_ITEMS": _m("Billing_Intelligence", "invoice_line_items", 55, "duplicate_line_items", POT, _INVOICE, "Repeated items can be legitimate (for example daily charges).", "Check the line items against the treatment record."),
    "NON_POSITIVE_LINE_ITEM": _m("Billing_Intelligence", "invoice_line_items", 56, "non_positive_line_item", CONF, _INVOICE, "Uses extracted or entered line items.", "Ask the provider to correct the invoice."),
    "NO_LINE_ITEMS": _m("Billing_Intelligence", "invoice_line_items", 57, "no_line_items", CONF, _INVOICE, "Uses extracted or entered line items.", "Request an itemised invoice."),
    "AMOUNT_ABOVE_TYPICAL_FOR_DIAGNOSIS": _m("Billing_Intelligence", "cost_reasonableness", 58, "amount_above_typical", POT, _CLAIM, "Typical costs come from a small reference table.", "Compare the charges with the treatment record."),
    "STAY_LONGER_THAN_TYPICAL": _m("Medical_Consistency", "stay_reasonableness", 0, "stay_longer_than_typical", POT, _CLAIM, "Typical stay comes from a small reference table.", "Check the clinical notes for reasons for the longer stay."),
    # orchestrator
    "AGENT_ERROR": _m("Operational_Intelligence", "agent_failure", 0, "agent_error", INC, _CLAIM, "An analysis module failed, so its checks did not complete.", "Re-run the analysis or review the claim manually."),
}

# Fallback agent for unknown codes, by legacy agent name.
_AGENT_BY_LEGACY: dict[str, AgentName] = {
    "provider_profile": "Provider_Intelligence",
    "claimant_profile": "Customer_Behaviour",
    "document_scan": "Document_Forensics",
    "invoice_check": "Billing_Intelligence",
}

# Codes whose detail starts with "<filename>: ".
_FILENAME_PREFIXED = frozenset({
    "UNEXPECTED_FILE_TYPE", "PDF_UNREADABLE", "IMAGE_UNREADABLE", "EDITING_SOFTWARE",
    "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION", "METADATA_STRIPPED", "DOCUMENT_REUSED",
})
_PREFIX_RE = re.compile(r"^(?P<name>[^:]+?): ")
_SEVERITY_ORDER = ("low", "medium", "high")
_DOC_MAX_SEVERITY = "medium"  # Req 13.2: metadata indicators are low or medium.


@dataclass(frozen=True)
class LegacyContext:
    """Claim-level identifiers used to build fact keys. All optional."""

    invoice_number: str | None = None
    hospital_id: str | None = None
    doctor_id: str | None = None
    claim_id: str | None = None
    agent_name: str | None = None  # legacy agent name, e.g. "invoice_check"
    document_hashes: Mapping[str, str] = field(default_factory=dict)  # filename -> sha256


def context_from_claim(claim: Any, documents: list[Any] | None = None, agent_name: str | None = None) -> LegacyContext:
    """Build a LegacyContext from a legacy Claim and DocumentInfo list (duck-typed)."""
    inv = getattr(claim, "invoice", None)
    return LegacyContext(
        invoice_number=getattr(inv, "invoice_number", None),
        hospital_id=getattr(claim, "hospital_id", None),
        doctor_id=getattr(claim, "doctor_id", None),
        claim_id=getattr(claim, "claim_id", None),
        agent_name=agent_name,
        document_hashes={d.filename: d.sha256 for d in (documents or []) if getattr(d, "sha256", None)},
    )


def _norm_text(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def _document_ref(code: str, detail: str, ctx: LegacyContext) -> str:
    m = _PREFIX_RE.match(detail or "") if code in _FILENAME_PREFIXED else None
    if not m:
        return ""
    name = m.group("name").strip()
    return ctx.document_hashes.get(name) or name


def _subject(kind: str, code: str, detail: str, ctx: LegacyContext) -> list[Any]:
    if kind == _INVOICE:
        return [_INVOICE, ctx.hospital_id or "", _norm_text(ctx.invoice_number or "")]
    if kind == _DOCUMENT:
        return [_DOCUMENT, _document_ref(code, detail, ctx)]
    if kind == _PROVIDER:
        if code.startswith("DOCTOR"):
            return [_PROVIDER, "doctor", ctx.doctor_id or ""]
        return [_PROVIDER, "hospital", ctx.hospital_id or ""]
    return [_CLAIM, ctx.claim_id or ""]


def _cap_severity(severity: str, cap: str) -> str:
    s = severity if severity in _SEVERITY_ORDER else "low"
    return _SEVERITY_ORDER[min(_SEVERITY_ORDER.index(s), _SEVERITY_ORDER.index(cap))]


def adapt_finding(legacy: LegacyFinding, ctx: LegacyContext | None = None) -> FindingDraft:
    """Convert one legacy Finding into a FindingDraft. Never raises for unknown codes."""
    ctx = ctx or LegacyContext()
    code = str(legacy.code or "").upper()
    detail = str(legacy.detail or "")
    is_llm = getattr(legacy, "source", "rule") == "llm"
    mapping = CODE_MAP.get(code)

    if mapping is None:
        agent: AgentName = _AGENT_BY_LEGACY.get(ctx.agent_name or "", "Operational_Intelligence")
        mapping = _m(agent, "legacy_unmapped", 0, f"legacy_{code.lower() or 'unknown'}", POT, _CLAIM,
                     "Raised by a legacy rule without a structured mapping.",
                     "Review the finding manually.")
        # Include the detail so unrelated unknown findings do not collapse together.
        values: Any = [_norm_text(detail)]
    else:
        values = []

    severity = legacy.severity
    if mapping.agent == "Document_Forensics" and mapping.status is POT:
        severity = _cap_severity(severity, _DOC_MAX_SEVERITY)
    if is_llm:
        severity = _cap_severity(severity, "medium")  # legacy LLM cap
        method = DetectionMethod.AI
        explanation = detail
        confidence_def = "AI-assisted observation; not a measured probability."
        limitations = [mapping.limitations, "Produced by an AI model; requires human review."]
    else:
        method = DetectionMethod.RULE
        explanation = detail
        confidence_def = ""
        limitations = [mapping.limitations]

    subject = _subject(mapping.subject, code, detail, ctx)
    if code in _FILENAME_PREFIXED:
        source_field = subject[1] if len(subject) > 1 and subject[1] else None
    else:
        source_field = None

    return FindingDraft(
        use_case_id=mapping.use_case_id,
        check_id=f"legacy.{code.lower() or 'unknown'}",
        agent=mapping.agent,
        category=mapping.category,
        severity=severity,
        status=mapping.status,  # AI cap is applied by FindingDraft
        explanation=explanation or code,
        source_field=source_field,
        extracted_values={"legacy_code": code},
        method=method,
        confidence_definition=confidence_def,
        limitations=[x for x in limitations if x],
        next_action=mapping.next_action,
        fact_key=FactKey(mapping.fact_type, subject, values),
    )


def adapt_findings(legacy: list[LegacyFinding], ctx: LegacyContext | None = None) -> list[FindingDraft]:
    return [adapt_finding(f, ctx) for f in legacy]
