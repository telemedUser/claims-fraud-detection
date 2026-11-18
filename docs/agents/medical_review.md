# Medical Review agent

Code: `app/agents/medical_review.py`. Findings map to **Medical_Consistency** in `app/core/legacy_adapter.py`. Reference data: `app/rules/medical_reference.v1.yaml` (loaded by `app/core/medical_reference.py`). Lab verification: `app/core/lab_registry.py`.

The reference file is illustrative demo data, not medical advice.

## What it checks

| Group | Code | Severity | Fires when |
|---|---|---|---|
| ICD-10 | `ICD_CODE_NOT_STATED` | info | the medical documents state no ICD-10 code |
| | `ICD_CODE_INVALID` | medium | a stated code is not a valid or known ICD-10 code |
| | `ICD_DIAGNOSIS_MISMATCH` | high | the code does not belong to the diagnosis on the claim |
| | `ICD_CODES_INCONSISTENT` | medium | different documents carry different codes |
| Medicines | `MEDICINE_NOT_INDICATED` | high | a prescribed medicine is not indicated for the diagnosis |
| | `MEDICINE_UNRELATED` | medium | a medicine has no relation to the diagnosis |
| | `EXPECTED_MEDICINE_MISSING` | low | none of the usual medicines for the diagnosis is prescribed |
| Lab report | `LAB_REPORT_UNVERIFIABLE` | low | the report has no number or verification code |
| | `LAB_REPORT_UNKNOWN_LAB` | medium | the report number prefix matches no registered lab |
| | `LAB_REPORT_PATIENT_MISMATCH` | high | the patient on the report differs from the claim |
| | `LAB_REPORT_TAMPERED` | high | the printed code does not match the registry code for the number, sample date, policy and results |
| | `LAB_REPORT_DATE_OUT_OF_RANGE` | medium | the sample date is outside the treatment window |
| Treatment | `TREATMENT_DIAGNOSIS_MISMATCH` | high, or medium when the correct procedure is also billed | the billed procedure does not fit the diagnosis |
| | `EXPECTED_TREATMENT_MISSING` | low | the usual treatment is absent |
| | `TREATMENT_NOT_TYPICAL` | low | the treatment is unusual for the diagnosis |
| Readability | `MEDICAL_DOCS_NOT_READABLE` | inconclusive | the medical documents have no readable text |

## Lab registry (simulated)

- The report number prefix identifies the lab (`PCL`, `NDL`, `LVL`, `GVL`, defined in `seed_data.LABS`).
- The verification code printed on the report is the first 16 hex characters, upper case, of HMAC-SHA256 over `number | sample date | policy | results`.
- Changing any result, the date or the policy changes the expected code, so an edited report no longer verifies.
- A real deployment would call the lab's verification API. The registry is a stand-in for the demo.

## LLM usage (switch on)

- **Tools:** `get_document_text` (personal data redacted), `get_clinical_reference` (expected medicines and procedures for the diagnosis), `get_lab_verification` (lab, code match, no personal data).
- **Looks for:** doses or combinations that look wrong, treatment out of proportion to the diagnosis, results that contradict the diagnosis.
- **Effect:** observations are shown and scored as potential anomalies (capped at 15 points for this agent and 25 per claim).

## Demo data

- **Suspicious and high-risk:** azithromycin for an ICD code `A97.0` diagnosis, and a lab report signed with CRP 3 that prints CRP 48. ICD mismatch, medicine not indicated and lab tampering fire.
- **Fabricated:** an unrelated medicine and a procedure that does not fit the diagnosis.
- **Clean and borderline:** no findings.

## Limitations

- **Small reference set:** only the diagnoses in the YAML file are covered. Unknown diagnoses produce no medicine or treatment findings.
- **Text-based:** scanned images without text give `MEDICAL_DOCS_NOT_READABLE`.
- **Simulated lab registry:** no real lab is queried.
