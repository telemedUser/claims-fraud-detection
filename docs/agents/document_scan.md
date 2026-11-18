# Document Scan agent (document forensics)

Code: `app/agents/document_scan.py`. Helpers: `app/core/doc_text.py` (text and printed fields), `app/core/pdf_forensics.py` (revisions, AI markers), `app/core/redact.py` (personal data removed before the LLM). Findings map to **Document_Forensics** in `app/core/legacy_adapter.py`. Every indicator is a potential anomaly with at most medium severity, and its detail gives alternative explanations.

## What it detects

| Group | Code | Severity | Fires when | |
|---|---|---|---|---|
| Completeness | `NO_DOCUMENTS`, `MISSING_MEDICAL_BILL`, `MISSING_MEDICAL_REPORT` | high / medium / low | required documents are missing | |
| File | `UNEXPECTED_FILE_TYPE`, `PDF_UNREADABLE`, `IMAGE_UNREADABLE` | medium | wrong type or unreadable | |
| Reuse | `DOCUMENT_REUSED` | high | identical file (SHA-256) used in an earlier claim | |
| Metadata | `EDITING_SOFTWARE` | medium | producer or creator is an editor (Photoshop, Canva, Word…) | |
| | `MODIFIED_AFTER_CREATION` | low | modified long after creation (per-type threshold) | |
| | `DOC_CREATED_BEFORE_ADMISSION` | medium | a bill file created before the admission | |
| | `METADATA_STRIPPED` | low | no metadata | |
| **Changed after generation** | `DOC_EDITED_AFTER_GENERATION` | medium | the PDF has more than one saved revision (edited and saved again) | new |
| | `DOC_MODIFIED_AFTER_BILL_DATE` | medium | the bill file was modified more than 2 days after its bill date | new |
| **AI-generated** | `AI_GENERATION_MARKER` | medium | metadata names an AI tool or label (ChatGPT, DALL·E, Midjourney, Firefly, Canva Magic Design, IPTC `trainedAlgorithmicMedia`…) | new |
| **Content vs claim** | `DOC_PATIENT_MISMATCH` | medium | the patient name printed on a document is not the policyholder | new |
| | `DOC_POLICY_MISMATCH` | medium | a different policy number is printed | new |
| | `DOC_DATES_MISMATCH` | medium | printed admission or discharge dates differ from the claim | new |
| | `DOC_DIAGNOSIS_MISMATCH` | medium | the printed diagnosis differs from the claim | new |
| | `DOC_BILL_NUMBER_MISMATCH` / `DOC_BILL_TOTAL_MISMATCH` / `DOC_BILL_DATE_MISMATCH` | medium / medium / low | the bill's printed number, total or date differ from what was claimed | new |

The hospital, doctor and GSTIN on documents are compared with the registry by the Provider Profile agent (`DOC_HOSPITAL_NAME_MISMATCH` and related codes).

Names and policy numbers are compared locally and **never written into finding text**, because rule findings are sent to the LLM.

## LLM usage (switch on)

- **Tool `get_document_text`:** each document's text, at most 3,000 characters, **with personal data redacted** by `app/core/redact.py`:
  - removed: the patient name and each part of it, policy number, claimant ID, values after Patient, Policy No, Name and Address labels, dates of birth, phone numbers, e-mails, Aadhaar-like and PAN-like numbers
  - included alongside: PDF metadata and the revision count
- **Kept for analysis:** provider details (hospital, doctor, GSTIN).
- **Untrusted text:** document text is marked as untrusted data, and the model is told to ignore instructions inside it.
- **What it looks for:** what the rules can't express, such as text that reads as AI-generated or templated, a discharge summary that doesn't support the billed treatment, documents that contradict each other, or details unusual for a hospital document.
- **Live example:** `BILL_DATE_PRE_DATES_ADMISSION` and `UNUSUAL_BILL_LINE_ITEMS`.
- **Effect:** observations are shown and scored as potential anomalies (capped at 15 points for this agent and 25 per claim).

## Demo data

- **Suspicious and high-risk bills:** Photoshop metadata, plus a **second PDF revision** written after generation, so `DOC_EDITED_AFTER_GENERATION` and `DOC_MODIFIED_AFTER_BILL_DATE` fire.
- **Fabricated bill:** created in "Canva Magic Design", so `AI_GENERATION_MARKER` fires.
- **Clean bill:** no document findings.

## Limitations

- No OCR: image-only scans give no text, so the content checks don't run on them.
- AI markers are easy to strip, so having no marker proves nothing.
- Visual tampering (fonts, stamps, signatures) isn't analysed yet. Use cases 30 and 31 are NOT_CHECKED.
