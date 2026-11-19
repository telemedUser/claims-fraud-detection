"""Describes the agents and workflow for the internal console. Keep in sync with app/agents/*."""
from app import llm
from app.llm_review import DECLARATIONS, FOCUS
from app.core.risk_config import load_risk_config

AGENTS = [
    {"name": "provider_profile", "title": "Provider Profile Agent",
     "purpose": "Builds hospital and doctor profiles from the registry and claims data, and cross-checks the claim "
                "and its documents against them (docs/agents/provider_profile.md).",
     "checks": ["HOSPITAL_UNKNOWN", "HOSPITAL_UNREGISTERED", "HOSPITAL_NEW", "TAX_ID_MISMATCH", "REGISTRY_GSTIN_INVALID",
                "GSTIN_STATE_MISMATCH", "HOSPITAL_NOT_EMPANELLED_ON_DATE", "DOCTOR_UNKNOWN", "DOCTOR_LICENSE_INVALID",
                "DOCTOR_LICENCE_EXPIRED", "DOCTOR_REGISTRATION_MISSING", "DOCTOR_NOT_AFFILIATED",
                "DOCTOR_AFFILIATION_INACTIVE", "DOCTOR_MANY_HOSPITALS",
                "HOSPITAL_HIGH_FRAUD_RATE", "AMOUNT_OUTLIER_FOR_HOSPITAL", "HOSPITAL_VOLUME_SURGE", "PEER_COST_OUTLIER",
                "HOSPITAL_OVER_CAPACITY", "DOCTOR_HIGH_FRAUD_RATE", "DOCTOR_HIGH_VOLUME", "DOCTOR_VOLUME_SURGE",
                "DOCTOR_SIMILAR_BILLS", "DOCTOR_SAME_DAY_OTHER_CITY",
                "DOCTOR_SPECIALTY_MISMATCH", "HOSPITAL_SPECIALTY_NOT_OFFERED",
                "DOC_GSTIN_MISMATCH", "DOC_HOSPITAL_NAME_MISMATCH", "DOC_DOCTOR_NAME_MISSING", "DOC_DOCTOR_REG_MISMATCH",
                "PROVIDER_DOCS_NOT_CHECKED"]},
    {"name": "claimant_profile", "title": "User Profile Agent",
     "purpose": "Builds the policyholder's profile from earlier claims, decisions and policy terms, and checks this "
                "claim against it: frequency, amounts, re-claiming, timing around the policy term and earlier fraud "
                "outcomes (docs/agents/user_profile.md).",
     "checks": ["CLAIM_FREQUENCY", "CLAIM_FREQUENCY_EXTREME", "AMOUNT_SPIKE", "AMOUNT_ESCALATION", "HOSPITAL_HOPPING",
                "REPEATED_SIMILAR_AMOUNTS", "HIGH_AMOUNT_SHORT_STAY", "DATES_INVALID", "LATE_SUBMISSION",
                "CLAIM_SOON_AFTER_POLICY_START", "CLAIM_NEAR_POLICY_END", "POLICY_END_PATTERN", "SUM_INSURED_NEAR_LIMIT",
                "RESUBMITTED_STAY", "OVERLAPPING_STAYS_ELSEWHERE", "PRIOR_FRAUD_DECISION"]},
    {"name": "document_scan", "title": "Document Forensics Agent",
     "purpose": "Document forensics: completeness, reuse, metadata, edits after generation, AI-generation markers, and "
                "what is printed on the documents against the claim (docs/agents/document_scan.md).",
     "checks": ["NO_DOCUMENTS", "MISSING_MEDICAL_BILL", "MISSING_MEDICAL_REPORT", "UNEXPECTED_FILE_TYPE",
                "DOCUMENT_REUSED", "EDITING_SOFTWARE", "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION",
                "METADATA_STRIPPED", "PDF_UNREADABLE", "IMAGE_UNREADABLE", "DOC_EDITED_AFTER_GENERATION",
                "DOC_MODIFIED_AFTER_BILL_DATE", "AI_GENERATION_MARKER", "DOC_PATIENT_MISMATCH", "DOC_POLICY_MISMATCH",
                "DOC_DATES_MISMATCH", "DOC_DIAGNOSIS_MISMATCH", "DOC_BILL_NUMBER_MISMATCH", "DOC_BILL_TOTAL_MISMATCH",
                "DOC_BILL_DATE_MISMATCH"]},
    {"name": "invoice_check", "title": "Invoice Validation Agent",
     "purpose": "Bill arithmetic and plausibility, GST verification, duplicate bills and payment status "
                "(docs/agents/invoice_check.md).",
     "checks": ["INVOICE_TOTAL_MISMATCH", "CLAIM_VS_INVOICE_MISMATCH", "DUPLICATE_INVOICE", "DUPLICATE_INVOICE_VARIANT",
                "INVOICE_NUMBER_AT_OTHER_HOSPITAL", "DUPLICATE_BILL_NEW_NUMBER", "INVOICE_DATE_OUT_OF_RANGE",
                "ROUND_TOTAL", "DUPLICATE_LINE_ITEMS", "NON_POSITIVE_LINE_ITEM", "NO_LINE_ITEMS",
                "AMOUNT_ABOVE_TYPICAL_FOR_DIAGNOSIS", "STAY_LONGER_THAN_TYPICAL", "GSTIN_INVALID",
                "GST_CHARGED_WITHOUT_GSTIN", "GST_SPLIT_MISMATCH", "GST_MIXED_IGST", "GST_ON_EXEMPT_SERVICES",
                "CASHLESS_BILL_CLAIMED", "BILL_PAYMENT_PENDING", "CLAIM_EXCEEDS_AMOUNT_PAID", "PAYMENT_NOT_EVIDENCED",
                "PAYMENT_DATE_OUT_OF_RANGE"]},
    {"name": "medical_review", "title": "Medical Review Agent",
     "purpose": "Reads the medical report, prescription and lab report: ICD-10 codes against the diagnosis, medicines "
                "against the condition, lab reports verified by report number (SIMULATED lab registry), and treatment "
                "against the diagnosis (docs/agents/medical_review.md).",
     "checks": ["ICD_CODE_NOT_STATED", "ICD_CODE_INVALID", "ICD_DIAGNOSIS_MISMATCH", "ICD_CODES_INCONSISTENT",
                "MEDICINE_NOT_INDICATED", "MEDICINE_UNRELATED", "EXPECTED_MEDICINE_MISSING", "LAB_REPORT_UNVERIFIABLE",
                "LAB_REPORT_UNKNOWN_LAB", "LAB_REPORT_PATIENT_MISMATCH", "LAB_REPORT_TAMPERED",
                "LAB_REPORT_DATE_OUT_OF_RANGE", "TREATMENT_DIAGNOSIS_MISMATCH", "EXPECTED_TREATMENT_MISSING",
                "TREATMENT_NOT_TYPICAL", "MEDICAL_DOCS_NOT_READABLE"]},
]


def _llm_state() -> dict:
    """``enabled`` is the effective switch: the console setting AND a configured provider key."""
    from app import runtime_settings

    s = runtime_settings.llm_switch()
    return {"enabled": s["effective"], "requested": s["requested"], "provider_configured": s["provider_configured"],
            "provider": s["provider"]}


def overview() -> dict:
    cfg = load_risk_config()
    sp = cfg.severity_points
    return {
        "agents": [{**a, "weight": cfg.agent_weights.get(a["name"], 100 / len(AGENTS)) / 100,
                    "llm_focus": FOCUS[a["name"]]} for a in AGENTS],
        "tools": [{"name": d["name"], "description": d["description"]} for d in DECLARATIONS],
        "scoring": {"rule": "final = min(100, sum over agents of agent rule points x (weight x agents) + capped LLM points); "
                            "points = severity points x status multiplier over de-duplicated findings",
                    "severity_points": {"low": sp.low, "medium": sp.medium, "high": sp.high}, "max_llm_points_per_agent": cfg.llm.max_points_per_agent, "max_llm_points_total": cfg.llm.max_points_total,
                    "llm_max_severity": "medium",
                    "thresholds": {"manual_review_at": cfg.bands.review_at, "investigate_at": cfg.bands.investigate_at}},
        "llm": {**_llm_state(), "models": llm.gemini_models() if llm.enabled() else []},
    }
