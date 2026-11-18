"""Medical Review agent (spec: Medical_Consistency). Reads the medical report, prescription and lab report and
checks them against the claimed diagnosis. Documented in docs/agents/medical_review.md.

  1. ICD codes      : stated, well formed, matching the diagnosis, consistent across documents
  2. Medicines      : not indicated for the diagnosis, unrelated, or the expected class missing
  3. Lab reports    : verified by report number against the SIMULATED lab registry (tampering, other patient,
                      sample date outside the stay)
  4. Treatment      : procedure for another condition, expected procedure missing, intensive services that are
                      unusual for the condition

Reference data: app/rules/medical_reference.v1.yaml (illustrative, not medical advice). Findings are potential
anomalies for a clinician to check. Deterministic; the optional LLM review runs afterwards in the pipeline.
"""
from datetime import timedelta

from app.agents.base import Agent
from app.core import lab_registry
from app.core import medical_reference as ref
from app.core.text_match import normalise_id
from app.models import Claim, DocumentInfo, Finding

CLINICAL_TYPES = ("medical_report", "prescription", "lab_report")
LAB_DAYS_BEFORE_ADMISSION = 7


class MedicalReviewAgent(Agent):
    """Clinical consistency of the medical documents with the claimed diagnosis and treatment."""
    name = "medical_review"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        from app.core.doc_text import document_texts

        clinical = [d for d in documents if d.doc_type in CLINICAL_TYPES] or [d for d in documents if d.doc_type == "other"]
        texts = document_texts(clinical)
        f: list[Finding] = []
        if clinical and not texts:
            f.append(Finding(code="MEDICAL_DOCS_NOT_READABLE", severity="low",
                             detail="The medical documents have no machine-readable text, so diagnosis, medicines, lab "
                                    "results and treatment were not checked."))
            return self.result(f)
        dz = ref.disease(claim.disease_id)
        by_type: dict[str, list[tuple[DocumentInfo, str]]] = {}
        for d, t in texts:
            by_type.setdefault(d.doc_type, []).append((d, t))
        clinical_text = "\n".join(t for d, t in texts if d.doc_type != "lab_report")
        bill_text = " ".join(li.description for li in claim.invoice.line_items)

        f += _icd_checks(claim, texts, dz)
        f += _medicine_checks(claim, [t for d, t in texts if d.doc_type in ("prescription", "medical_report", "other")], dz)
        f += _lab_checks(claim, by_type.get("lab_report", []))
        f += _treatment_checks(claim, clinical_text, bill_text, dz, has_report=bool(by_type.get("medical_report")))
        return self.result(f)


# ---------------------------------------------------------------- 1. ICD codes

def _icd_checks(claim: Claim, texts, dz) -> list[Finding]:
    f: list[Finding] = []
    per_doc = [(d, ref.icd_codes(t)) for d, t in texts if d.doc_type != "lab_report"]
    codes = [c for _, cs in per_doc for c in cs]
    reports = [d for d, _ in per_doc if d.doc_type == "medical_report"]
    if reports and not codes:
        f.append(Finding(code="ICD_CODE_NOT_STATED", severity="low",
                         detail="The medical report gives no ICD-10 code for the diagnosis."))
        return f
    bad = sorted({c for c in codes if not ref.icd_valid_shape(c)})
    if bad:
        f.append(Finding(code="ICD_CODE_INVALID", severity="medium",
                         detail=f"ICD code(s) {', '.join(bad)} are not valid ICD-10 codes (letter, two digits, optional decimals)."))
    valid = [c for c in codes if ref.icd_valid_shape(c)]
    if dz and valid:
        wrong = sorted({c for c in valid if not ref.icd_matches(c, claim.disease_id)})
        if wrong:
            other = {c: ref.icd_disease(c) for c in wrong}
            named = "; ".join(f"{c} is a code for {o.replace('_', ' ')}" if o else f"{c} is outside the expected range"
                              for c, o in other.items())
            f.append(Finding(code="ICD_DIAGNOSIS_MISMATCH", severity="medium",
                             detail=f"ICD code(s) on the documents do not match the claimed diagnosis {claim.diagnosis} "
                                    f"(expected {', '.join(dz['icd10'])}): {named}."))
    if len({c[:3] for c in valid}) > 1:
        f.append(Finding(code="ICD_CODES_INCONSISTENT", severity="medium",
                         detail=f"The documents give different ICD-10 categories: {', '.join(sorted(set(valid)))}."))
    return f


# ---------------------------------------------------------------- 2. medicines

def _medicine_checks(claim: Claim, texts: list[str], dz) -> list[Finding]:
    if not dz:
        return []
    names = []
    for t in texts:
        for n in ref.medicines(t):
            if n.lower() not in [x.lower() for x in names]:
                names.append(n)
    classified = [(n, ref.medicine_class(n)) for n in names]
    known = [(n, c) for n, c in classified if c]
    if not known:
        return []
    f: list[Finding] = []
    bad = [(n, c) for n, c in known if c in dz["not_indicated_classes"]]
    if bad:
        f.append(Finding(code="MEDICINE_NOT_INDICATED", severity="medium",
                         detail=f"{', '.join(f'{n} ({c})' for n, c in bad)} is not usually indicated for {claim.diagnosis}."))
    support = set(ref.reference()["supportive_classes"])
    unrelated = [(n, c) for n, c in known if c not in support and c not in dz["not_indicated_classes"]
                 and not any(ref.satisfies(c, e) for e in dz["expected_classes"])]
    if unrelated:
        f.append(Finding(code="MEDICINE_UNRELATED", severity="low",
                         detail=f"{', '.join(f'{n} ({c})' for n, c in unrelated)} is not related to {claim.diagnosis}; "
                                f"it may treat another condition."))
    missing = [e for e in dz["expected_classes"] if not any(ref.satisfies(c, e) for _, c in known)]
    if missing:
        f.append(Finding(code="EXPECTED_MEDICINE_MISSING", severity="low",
                         detail=f"No {' or '.join(missing)} medicine is prescribed, which is usual for {claim.diagnosis}."))
    return f


# ---------------------------------------------------------------- 3. lab reports

def _lab_checks(claim: Claim, labs) -> list[Finding]:
    f: list[Finding] = []
    for d, text in labs:
        lab = lab_registry.parse(text)
        tag = d.filename
        if not lab["number"] or not lab["code"]:
            f.append(Finding(code="LAB_REPORT_UNVERIFIABLE", severity="low",
                             detail=f"{tag}: no lab report number or verification code, so the report cannot be checked "
                                    f"with the issuing laboratory."))
            continue
        found = lab_registry.lab_for(lab["number"])
        if not found:
            f.append(Finding(code="LAB_REPORT_UNKNOWN_LAB", severity="medium",
                             detail=f"{tag}: report number {lab['number']} does not belong to a laboratory in the "
                                    f"registry (SIMULATED)."))
            continue
        if claim.policy_number and lab["policy_number"] and normalise_id(lab["policy_number"]) != normalise_id(claim.policy_number):
            f.append(Finding(code="LAB_REPORT_PATIENT_MISMATCH", severity="high",
                             detail=f"{tag}: lab report {lab['number']} was issued for a different policy, so it belongs "
                                    f"to another patient."))
        sample = lab["sample_date"]
        ok = lab_registry.verify(lab["number"], sample.isoformat() if sample else "", lab["policy_number"] or "",
                                 lab["results"], lab["code"])
        if not ok:
            f.append(Finding(code="LAB_REPORT_TAMPERED", severity="high",
                             detail=f"{tag}: the verification code for lab report {lab['number']} does not match the "
                                    f"printed results, date or policy, so the report was changed after "
                                    f"{found[1]['name']} issued it (SIMULATED lab registry)."))
        if sample and not (claim.admission_date - timedelta(days=LAB_DAYS_BEFORE_ADMISSION) <= sample <= claim.discharge_date):
            f.append(Finding(code="LAB_REPORT_DATE_OUT_OF_RANGE", severity="medium",
                             detail=f"{tag}: sample date {sample} is outside the stay ({claim.admission_date} to "
                                    f"{claim.discharge_date})."))
    return f


# ---------------------------------------------------------------- 4. treatment

def _treatment_checks(claim: Claim, clinical_text: str, bill_text: str, dz, has_report: bool) -> list[Finding]:
    if not dz:
        return []
    f: list[Finding] = []
    text = f"{clinical_text}\n{bill_text}"
    found = ref.procedures_in(text)
    other = {k: v for k, v in found.items() if k != claim.disease_id}
    if other:
        what = "; ".join(f"{', '.join(v)} ({k.replace('_', ' ')})" for k, v in other.items())
        also = claim.disease_id in found
        f.append(Finding(code="TREATMENT_DIAGNOSIS_MISMATCH", severity="medium" if also else "high",
                         detail=f"The documents or bill describe treatment for another condition: {what}"
                                f"{', alongside the expected treatment' if also else ''}; the claim is for {claim.diagnosis}."))
    if dz["surgical"] and claim.disease_id not in found and (has_report or bill_text):
        f.append(Finding(code="EXPECTED_TREATMENT_MISSING", severity="medium",
                         detail=f"{claim.diagnosis} is usually treated with a procedure ({', '.join(dz['procedures'][:3])}), "
                                f"but none is recorded in the report or the bill."))
    unusual = ref.intensive_in(text, dz["atypical_services"])
    if unusual:
        f.append(Finding(code="TREATMENT_NOT_TYPICAL", severity="medium",
                         detail=f"{', '.join(unusual)} is unusual for {claim.diagnosis}; check that the clinical notes "
                                f"justify it."))
    return f
