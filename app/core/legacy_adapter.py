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
    # provider_profile: registry cross-checks dated to the admission (docs/agents/provider_profile.md)
    "REGISTRY_GSTIN_INVALID": _m("Provider_Intelligence", "provider_registry", 0, "registry_gstin_invalid", POT, _PROVIDER, "Checks the format and check digit only; GSTN status is not queried.", "Correct the hospital's GSTIN in the provider registry."),
    "GSTIN_STATE_MISMATCH": _m("Provider_Intelligence", "provider_registry", 0, "gstin_state_mismatch", POT, _PROVIDER, "A hospital group can bill from a GSTIN registered in another state.", "Confirm the billing entity and its GSTIN with the hospital."),
    "HOSPITAL_NOT_EMPANELLED_ON_DATE": _m("Provider_Intelligence", "provider_registry", 0, "hospital_not_empanelled_on_date", CONF, _PROVIDER, _REG_LIM, "Check the hospital's network agreement dates."),
    "DOCTOR_LICENCE_EXPIRED": _m("Provider_Intelligence", "provider_registry", 0, "doctor_licence_expired", CONF, _PROVIDER, "Licence expiry from the simulated registry; renewals may not be recorded.", "Check the licence status with the medical council."),
    "DOCTOR_REGISTRATION_MISSING": _m("Provider_Intelligence", "provider_registry", 0, "doctor_registration_missing", POT, _PROVIDER, "The registry may be incomplete.", "Obtain the doctor's council registration number."),
    "DOCTOR_AFFILIATION_INACTIVE": _m("Provider_Intelligence", "provider_registry", 0, "doctor_affiliation_inactive", POT, _PROVIDER, "Affiliation dates from the simulated registry; visiting consultants may not be recorded.", "Confirm the doctor's affiliation on the admission date with the hospital."),
    # provider_profile: behaviour computed from claims data
    "HOSPITAL_VOLUME_SURGE": _m("Provider_Intelligence", "provider_risk", 65, "hospital_volume_surge", POT, _PROVIDER, "A surge can follow a new network agreement, an outbreak or seasonal demand.", "Review the hospital's recent claims for common patterns."),
    "DOCTOR_VOLUME_SURGE": _m("Provider_Intelligence", "provider_risk", 65, "doctor_volume_surge", POT, _PROVIDER, "Volume can rise legitimately, for example after joining a new hospital.", "Review the doctor's recent claims for common patterns."),
    "PEER_COST_OUTLIER": _m("Provider_Intelligence", "provider_risk", 0, "peer_cost_outlier", POT, _PROVIDER, "Peer claims differ in case mix and severity.", "Compare the itemised charges with peer hospitals' claims for the diagnosis."),
    "DOCTOR_SIMILAR_BILLS": _m("Provider_Intelligence", "provider_risk", 0, "doctor_similar_bills", POT, _PROVIDER, "Package pricing can produce similar amounts for different patients.", "Compare the bills for repeated line items and wording."),
    "HOSPITAL_OVER_CAPACITY": _m("Provider_Intelligence", "provider_risk", 0, "hospital_over_capacity", POT, _PROVIDER, "Counts claims with this insurer only and the bed count on record.", "Check the hospital's admissions register for the date."),
    "DOCTOR_SAME_DAY_OTHER_CITY": _m("Provider_Intelligence", "provider_risk", 0, "doctor_same_day_other_city", POT, _PROVIDER, "Admission can be recorded under a consultant who is not physically present.", "Ask both hospitals who treated the patients on that date."),
    # provider_profile: specialty fit
    "DOCTOR_SPECIALTY_MISMATCH": _m("Provider_Intelligence", "provider_fit", 0, "doctor_specialty_mismatch", POT, _PROVIDER, "Doctors can treat outside their specialty, for example in emergencies.", "Check the treatment record for who performed the treatment."),
    "HOSPITAL_SPECIALTY_NOT_OFFERED": _m("Provider_Intelligence", "provider_fit", 0, "hospital_specialty_not_offered", POT, _PROVIDER, "The department list on record may be incomplete.", "Confirm with the hospital that it provides this treatment."),
    # provider_profile: documents against the registry (text extraction, no OCR)
    "DOC_GSTIN_MISMATCH": _m("Provider_Intelligence", "provider_registry", 0, "tax_id_mismatch", CONF, _PROVIDER, "GSTIN read from document text; compared with the simulated registry.", "Verify the tax ID with the hospital."),
    "DOC_HOSPITAL_NAME_MISMATCH": _m("Provider_Intelligence", "provider_documents", 0, "doc_hospital_name_mismatch", POT, _PROVIDER, "Fuzzy name match on extracted text; letterheads can use a trade name.", "Confirm which hospital issued the documents."),
    "DOC_DOCTOR_NAME_MISSING": _m("Provider_Intelligence", "provider_documents", 0, "doc_doctor_name_missing", POT, _PROVIDER, "Handwritten or image-only text is not read.", "Check who signed the prescription and report."),
    "DOC_DOCTOR_REG_MISMATCH": _m("Provider_Intelligence", "provider_documents", 0, "doc_doctor_reg_mismatch", POT, _PROVIDER, "Registration numbers read from document text with a pattern match.", "Check the registration number with the medical council."),
    "PROVIDER_DOCS_NOT_CHECKED": _m("Provider_Intelligence", "provider_documents", 0, "provider_docs_not_checked", INC, _PROVIDER, "Image-only or scanned files need OCR, which is not configured.", "Compare the hospital and doctor details on the documents manually."),
    # claimant_profile -> Customer_Behaviour / Policy_Eligibility
    "CLAIM_FREQUENCY": _m("Customer_Behaviour", "claim_pattern", 0, "claim_frequency", POT, _CLAIM, "Frequent claims can be legitimate.", "Review the claimant's recent claims."),
    "CLAIM_FREQUENCY_EXTREME": _m("Customer_Behaviour", "claim_pattern", 0, "claim_frequency_extreme", POT, _CLAIM, "Frequent claims can be legitimate.", "Review the claimant's recent claims."),
    "AMOUNT_SPIKE": _m("Customer_Behaviour", "claim_pattern", 0, "amount_spike", POT, _CLAIM, "Compared with the claimant's own history only.", "Check whether the treatment explains the higher amount."),
    "HOSPITAL_HOPPING": _m("Customer_Behaviour", "claim_pattern", 0, "hospital_hopping", POT, _CLAIM, "Multiple hospitals can reflect referrals or relocation.", "Review the claimant's hospital history."),
    "REPEATED_SIMILAR_AMOUNTS": _m("Customer_Behaviour", "claim_pattern", 0, "repeated_similar_amounts", POT, _CLAIM, "Similar amounts can result from fixed-price treatments.", "Compare the claims for repeated charges."),
    "HIGH_AMOUNT_SHORT_STAY": _m("Customer_Behaviour", "claim_pattern", 0, "high_amount_short_stay", POT, _CLAIM, "Some day-care procedures are costly.", "Check that the treatment justifies the amount."),
    # claimant_profile (User Profile agent): docs/agents/user_profile.md
    "AMOUNT_ESCALATION": _m("Customer_Behaviour", "claim_pattern", 0, "amount_escalation", POT, _CLAIM, "Treatment costs can rise legitimately, for example for a worsening condition.", "Compare the claims' diagnoses and treatments."),
    "PRIOR_FRAUD_DECISION": _m("Customer_Behaviour", "claimant_history", 0, "prior_fraud_decision", POT, _CLAIM, "An earlier outcome does not prove this claim is fraudulent.", "Review the earlier denied or referred claims before deciding."),
    "RESUBMITTED_STAY": _m("Duplicate_Detection", "duplicate_claim", 15, "resubmitted_stay", POT, _CLAIM, "A corrected resubmission can legitimately repeat a stay.", "Compare with the earlier claim for the same stay."),
    "OVERLAPPING_STAYS_ELSEWHERE": _m("Customer_Behaviour", "claim_pattern", 0, "overlapping_stays", POT, _CLAIM, "Transfers between hospitals can produce overlapping dates.", "Check both hospitals' admission records."),
    "CLAIM_SOON_AFTER_POLICY_START": _m("Customer_Behaviour", "policy_timing", 0, "claim_soon_after_start", POT, _CLAIM, "Accidents and acute illness can happen at any time.", "Check for symptoms or treatment before the policy started."),
    "CLAIM_NEAR_POLICY_END": _m("Customer_Behaviour", "policy_timing", 0, "claim_near_policy_end", POT, _CLAIM, "Many genuine claims fall near a term end.", "No action unless other findings exist."),
    "POLICY_END_PATTERN": _m("Customer_Behaviour", "policy_timing", 0, "policy_end_pattern", POT, _CLAIM, "A pattern across a few claims can be coincidence.", "Review the timing and necessity of the claims near term ends."),
    "SUM_INSURED_NEAR_LIMIT": _m("Customer_Behaviour", "policy_timing", 0, "sum_insured_near_limit", POT, _CLAIM, "High utilisation is common for serious illness.", "Check the term's claims for duplicated treatment."),
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
    # document_scan: manipulation after generation, AI markers, content consistency (docs/agents/document_scan.md)
    "DOC_EDITED_AFTER_GENERATION": _m("Document_Forensics", "document_integrity", 24, "doc_extra_revision", POT, _DOCUMENT, "Digital signatures and form filling also add PDF revisions.", _DOC_ACT),
    "DOC_MODIFIED_AFTER_BILL_DATE": _m("Document_Forensics", "document_metadata", 24, "bill_modified_after_bill_date", POT, _DOCUMENT, _DOC_ALT, _DOC_ACT),
    "AI_GENERATION_MARKER": _m("Document_Forensics", "document_integrity", 32, "ai_generation_marker", POT, _DOCUMENT, "Markers are easy to add or strip; a marker is not proof and no marker is not proof of authenticity.", "Ask the hospital to confirm it issued the document."),
    "DOC_PATIENT_MISMATCH": _m("Document_Forensics", "cross_document", 33, "doc_patient_mismatch", POT, _CLAIM, "Name formats differ (initials, spelling) and extraction can misread names.", "Check the patient details on the original documents."),
    "DOC_POLICY_MISMATCH": _m("Document_Forensics", "cross_document", 33, "doc_policy_mismatch", POT, _CLAIM, "The hospital may print an old or group policy number.", "Confirm the policy number with the hospital's records."),
    "DOC_DATES_MISMATCH": _m("Document_Forensics", "cross_document", 34, "doc_dates_mismatch", POT, _CLAIM, "Dates read from document text; a typing error on the claim form is possible.", "Compare the stay dates with the hospital's admission register."),
    "DOC_DIAGNOSIS_MISMATCH": _m("Document_Forensics", "cross_document", 35, "doc_diagnosis_mismatch", POT, _CLAIM, "Documents can name the same condition differently.", "Check the diagnosis on the discharge summary."),
    "DOC_BILL_NUMBER_MISMATCH": _m("Document_Forensics", "cross_document", 36, "doc_bill_number_mismatch", POT, _CLAIM, "The claimant may have typed the bill number wrongly.", "Ask for the original bill."),
    "DOC_BILL_TOTAL_MISMATCH": _m("Document_Forensics", "cross_document", 36, "doc_bill_total_mismatch", POT, _CLAIM, "Totals read from document text; partial bills or discounts can differ.", "Compare the itemised bill with the claimed amounts."),
    "DOC_BILL_DATE_MISMATCH": _m("Document_Forensics", "cross_document", 36, "doc_bill_date_mismatch", POT, _CLAIM, "Interim and final bills carry different dates.", "Ask for the final bill."),
    # invoice_check: GST, duplicates, payment (docs/agents/invoice_check.md)
    "GSTIN_INVALID": _m("Billing_Intelligence", "gst", 59, "gstin_invalid", CONF, _INVOICE, "Format and check digit only; GSTN registration status is not queried.", "Ask the hospital for its GST registration certificate."),
    "GST_CHARGED_WITHOUT_GSTIN": _m("Billing_Intelligence", "gst", 59, "gst_without_gstin", POT, _INVOICE, "The GSTIN may be printed where it was not read.", "Check the GST details on the original bill."),
    "GST_SPLIT_MISMATCH": _m("Billing_Intelligence", "gst", 59, "gst_split_mismatch", POT, _INVOICE, "Rounding can make halves differ slightly.", "Ask the hospital to explain the GST lines."),
    "GST_MIXED_IGST": _m("Billing_Intelligence", "gst", 59, "gst_mixed_igst", POT, _INVOICE, "Separate supplies on one bill can legitimately mix tax types.", "Ask the hospital to explain the GST lines."),
    "GST_ON_EXEMPT_SERVICES": _m("Billing_Intelligence", "gst", 59, "gst_on_exempt", POT, _INVOICE, "Some items (costly room rent, cosmetics) are taxable.", "Check which items GST was charged on."),
    "DUPLICATE_INVOICE_VARIANT": _m("Duplicate_Detection", "duplicate_invoice", 13, "invoice_duplicate", POT, _INVOICE, "Hospitals rarely reuse a number with different formatting.", "Compare with the earlier claim that used this bill."),
    "INVOICE_NUMBER_AT_OTHER_HOSPITAL": _m("Duplicate_Detection", "duplicate_invoice", 13, "invoice_number_other_hospital", POT, _INVOICE, "Different hospitals can use the same numbering scheme.", "No action unless other findings exist."),
    "DUPLICATE_BILL_NEW_NUMBER": _m("Duplicate_Detection", "duplicate_invoice", 16, "bill_same_amount_date", POT, _INVOICE, "Two genuine bills can share a date and total.", "Compare the line items of both bills."),
    "CASHLESS_BILL_CLAIMED": _m("Billing_Intelligence", "payment", 60, "cashless_bill_claimed", POT, _INVOICE, "Read from the bill's payment line; a cashless request can be refused and later paid by the patient.", "Check with the hospital or TPA whether the bill was settled cashless."),
    "BILL_PAYMENT_PENDING": _m("Billing_Intelligence", "payment", 60, "bill_payment_pending", POT, _INVOICE, "The patient may have paid after the bill was printed.", "Ask for the payment receipt."),
    "CLAIM_EXCEEDS_AMOUNT_PAID": _m("Billing_Intelligence", "payment", 60, "claim_exceeds_paid", POT, _INVOICE, "Not every payment may be on the uploaded documents.", "Ask for receipts covering the full claimed amount."),
    "PAYMENT_NOT_EVIDENCED": _m("Billing_Intelligence", "payment", 60, "payment_not_evidenced", POT, _INVOICE, "Some hospitals print payment details on a separate receipt.", "Ask for the payment receipt."),
    "PAYMENT_DATE_OUT_OF_RANGE": _m("Billing_Intelligence", "payment", 60, "payment_date_out_of_range", POT, _INVOICE, "Advance deposits are paid before admission.", "Check the receipt against the stay dates."),
    # medical_review -> Medical_Consistency (docs/agents/medical_review.md). Clinical reference is illustrative.
    "MEDICAL_DOCS_NOT_READABLE": _m("Medical_Consistency", "clinical_documents", 0, "medical_docs_not_readable", INC, _CLAIM, "Image-only documents need OCR, which is not configured.", "Review the medical documents manually."),
    "ICD_CODE_NOT_STATED": _m("Medical_Consistency", "icd_coding", 0, "icd_not_stated", INFO, _CLAIM, "Many hospitals do not print ICD codes.", "No action unless other findings exist."),
    "ICD_CODE_INVALID": _m("Medical_Consistency", "icd_coding", 0, "icd_invalid", POT, _CLAIM, "Codes are read from text; a typing error is possible.", "Ask the hospital for the coded diagnosis."),
    "ICD_DIAGNOSIS_MISMATCH": _m("Medical_Consistency", "icd_coding", 0, "icd_diagnosis_mismatch", POT, _CLAIM, "Secondary diagnoses can carry other codes.", "Check the coded diagnosis against the clinical notes."),
    "ICD_CODES_INCONSISTENT": _m("Medical_Consistency", "icd_coding", 0, "icd_inconsistent", POT, _CLAIM, "Documents may list secondary diagnoses.", "Check which diagnosis was treated."),
    "MEDICINE_NOT_INDICATED": _m("Medical_Consistency", "medication", 0, "medicine_not_indicated", POT, _CLAIM, "Illustrative reference; a clinician may have a documented reason.", "Ask a medical reviewer to check the prescription."),
    "MEDICINE_UNRELATED": _m("Medical_Consistency", "medication", 0, "medicine_unrelated", POT, _CLAIM, "The medicine may treat a co-existing condition.", "Check for other diagnoses in the notes."),
    "EXPECTED_MEDICINE_MISSING": _m("Medical_Consistency", "medication", 0, "expected_medicine_missing", POT, _CLAIM, "Medicines may be listed on documents that were not uploaded.", "Ask for the full prescription."),
    "LAB_REPORT_UNVERIFIABLE": _m("Medical_Consistency", "lab_report", 0, "lab_report_unverifiable", POT, _CLAIM, "Some labs do not print a verification code.", "Ask the lab to confirm the report."),
    "LAB_REPORT_UNKNOWN_LAB": _m("Medical_Consistency", "lab_report", 0, "lab_report_unknown_lab", POT, _CLAIM, "The simulated lab registry lists only a few labs.", "Confirm the laboratory and report with the hospital."),
    "LAB_REPORT_PATIENT_MISMATCH": _m("Medical_Consistency", "lab_report", 0, "lab_report_other_patient", POT, _CLAIM, "The lab may have recorded an old policy number.", "Ask the lab to confirm whom the report belongs to."),
    "LAB_REPORT_TAMPERED": _m("Medical_Consistency", "lab_report", 0, "lab_report_tampered", POT, _CLAIM, "Verified against a SIMULATED lab registry; a re-typed copy also fails.", "Request the report directly from the laboratory."),
    "LAB_REPORT_DATE_OUT_OF_RANGE": _m("Medical_Consistency", "lab_report", 0, "lab_report_date_out_of_range", POT, _CLAIM, "Tests before admission can be part of the work-up.", "Check why the test date falls outside the stay."),
    "TREATMENT_DIAGNOSIS_MISMATCH": _m("Medical_Consistency", "treatment", 0, "treatment_diagnosis_mismatch", POT, _CLAIM, "A patient can have more than one condition treated.", "Ask a medical reviewer to compare the treatment with the diagnosis."),
    "EXPECTED_TREATMENT_MISSING": _m("Medical_Consistency", "treatment", 0, "expected_treatment_missing", POT, _CLAIM, "Conservative treatment is sometimes chosen.", "Check the operation notes."),
    "TREATMENT_NOT_TYPICAL": _m("Medical_Consistency", "treatment", 0, "treatment_not_typical", POT, _CLAIM, "Complications can justify intensive care or imaging.", "Check the clinical notes for the reason."),
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
    "medical_review": "Medical_Consistency",
}

# Codes whose detail starts with "<filename>: ".
_FILENAME_PREFIXED = frozenset({
    "UNEXPECTED_FILE_TYPE", "PDF_UNREADABLE", "IMAGE_UNREADABLE", "EDITING_SOFTWARE",
    "MODIFIED_AFTER_CREATION", "DOC_CREATED_BEFORE_ADMISSION", "METADATA_STRIPPED", "DOCUMENT_REUSED",
    "DOC_EDITED_AFTER_GENERATION", "DOC_MODIFIED_AFTER_BILL_DATE", "AI_GENERATION_MARKER",
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
