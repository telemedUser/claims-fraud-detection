"""Describes the agents and workflow for the internal console. Keep in sync with app/agents/*."""
from app import llm
from app.llm_review import DECLARATIONS, FOCUS, MAX_LLM_POINTS
from app.core.risk_config import load_risk_config

AGENTS = [
    {"name": "provider_profile", "title": "Provider Profile Agent",
     "purpose": "Builds hospital and doctor risk profiles and checks the claim against them.",
     "checks": ["HOSPITAL_UNKNOWN", "HOSPITAL_UNREGISTERED", "HOSPITAL_HIGH_FRAUD_RATE", "HOSPITAL_NEW",
                "AMOUNT_OUTLIER_FOR_HOSPITAL", "TAX_ID_MISMATCH", "DOCTOR_UNKNOWN", "DOCTOR_LICENSE_INVALID",
                "DOCTOR_NOT_AFFILIATED", "DOCTOR_MANY_HOSPITALS", "DOCTOR_HIGH_VOLUME", "DOCTOR_HIGH_FRAUD_RATE"]},
    {"name": "claimant_profile", "title": "Claimant Profile Agent",
     "purpose": "Builds the policyholder's behaviour profile from claim history.",
     "checks": ["CLAIM_FREQUENCY", "CLAIM_FREQUENCY_EXTREME", "AMOUNT_SPIKE", "HOSPITAL_HOPPING",
                "REPEATED_SIMILAR_AMOUNTS", "DATES_INVALID", "LATE_SUBMISSION",
                "HIGH_AMOUNT_SHORT_STAY"]},
    {"name": "document_scan", "title": "Document Forensics Agent",
     "purpose": "Inspects uploaded files: required documents, type, reuse, and PDF/image metadata.",
     "checks": ["NO_DOCUMENTS", "MISSING_MEDICAL_BILL", "MISSING_MEDICAL_REPORT", "UNEXPECTED_FILE_TYPE",
                "DOCUMENT_REUSED", "EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION",
                "METADATA_STRIPPED", "PDF_UNREADABLE", "IMAGE_UNREADABLE"]},
    {"name": "invoice_check", "title": "Invoice Validation Agent",
     "purpose": "Validates bill arithmetic, identity, duplicates, and plausibility for the diagnosis.",
     "checks": ["INVOICE_TOTAL_MISMATCH", "CLAIM_VS_INVOICE_MISMATCH", "DUPLICATE_INVOICE", "INVOICE_DATE_OUT_OF_RANGE",
                "ROUND_TOTAL", "DUPLICATE_LINE_ITEMS", "NON_POSITIVE_LINE_ITEM", "NO_LINE_ITEMS",
                "AMOUNT_ABOVE_TYPICAL_FOR_DIAGNOSIS", "STAY_LONGER_THAN_TYPICAL"]},
]


def overview() -> dict:
    cfg = load_risk_config()
    sp = cfg.severity_points
    return {
        "agents": [{**a, "weight": 1.0, "llm_focus": FOCUS[a["name"]]} for a in AGENTS],
        "tools": [{"name": d["name"], "description": d["description"]} for d in DECLARATIONS],
        "scoring": {"rule": "final = min(100, sum of severity points x status multiplier over de-duplicated findings)",
                    "severity_points": {"low": sp.low, "medium": sp.medium, "high": sp.high}, "max_llm_points_per_agent": MAX_LLM_POINTS,
                    "llm_max_severity": "medium",
                    "thresholds": {"manual_review_at": cfg.bands.review_at, "investigate_at": cfg.bands.investigate_at}},
        "llm": {"enabled": llm.enabled(), "provider": "Google Gemini" if llm.enabled() else None,
                "models": llm.gemini_models() if llm.enabled() else []},
    }
