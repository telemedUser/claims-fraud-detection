"""Helpers shared by the customer and internal claim-intake routes (not a router)."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app import jobs
from app.db.repos import DISEASES, open_repos
from app.models import Claim, ClaimSubmission, DocumentInfo

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 10
ALLOWED_DOC_TYPES = {"medical_bill", "prescription", "medical_report", "lab_report", "payment_receipt", "other"}


async def read_documents(documents: list[UploadFile], types: list[str]) -> list[DocumentInfo]:
    if len(documents) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} documents allowed")
    docs = []
    for i, up in enumerate(documents):
        data = await up.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"{up.filename} exceeds 10 MB")
        doc_type = types[i] if i < len(types) and types[i] in ALLOWED_DOC_TYPES else "other"
        docs.append(DocumentInfo(filename=(up.filename or "unnamed")[:200], content_type=up.content_type or "",
                                 size=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=doc_type))
    return docs


def verified_policy(policy_number: str, dob: date) -> dict:
    with open_repos() as repos:
        p = repos.policy(policy_number.strip().upper())
    if not p or p["date_of_birth"] != dob.isoformat():
        raise HTTPException(404, "We couldn't find a policy with that number and date of birth.")
    return p


ELIGIBILITY = "eligibility"  # rule kinds: eligibility violations are stored for review, "invalid" ones are not
INVALID = "invalid"


def policy_rule_violations(p: dict, c) -> list[tuple[str, str, str]]:
    """Every policy rule `c` breaks, in precedence order, as ``(kind, rule, message)``.

    ``kind`` is ELIGIBILITY (hospital not in network, condition not covered, admission outside the policy period,
    amount over the sum insured) or INVALID (malformed data such as an unknown doctor or impossible dates).
    `c` needs hospital_id, doctor_id, disease_id, admission_date, discharge_date and claimed_amount
    (ClaimSubmission or Claim)."""
    out: list[tuple[str, str, str]] = []
    if c.hospital_id not in p["network_hospital_ids"]:
        out.append((ELIGIBILITY, "HOSPITAL_NOT_IN_NETWORK", "The selected hospital is not in your policy's network."))
    if c.disease_id not in p["covered_disease_ids"]:
        out.append((ELIGIBILITY, "CONDITION_NOT_COVERED", "The selected condition is not covered by your policy."))
    with open_repos() as repos:
        doctor_known = repos.doctor(c.doctor_id) is not None
    if not doctor_known:
        out.append((INVALID, "UNKNOWN_DOCTOR", "Unknown doctor."))
    if c.discharge_date < c.admission_date:
        out.append((INVALID, "DISCHARGE_BEFORE_ADMISSION", "Discharge date cannot be before admission date."))
    if c.discharge_date > date.today():
        out.append((INVALID, "DISCHARGE_IN_FUTURE", "Discharge date cannot be in the future."))
    if not (date.fromisoformat(p["valid_from"]) <= c.admission_date <= date.fromisoformat(p["valid_to"])):
        out.append((ELIGIBILITY, "ADMISSION_OUTSIDE_POLICY_PERIOD", "Admission date is outside your policy period."))
    if c.claimed_amount > p["sum_insured"]:
        out.append((ELIGIBILITY, "AMOUNT_EXCEEDS_SUM_INSURED", "Claimed amount exceeds your sum insured."))
    return out


def enforce_policy_rules(p: dict, c) -> None:
    """Policy rules shared by claim submission and /api/assess: raise 422 for the first rule broken."""
    violations = policy_rule_violations(p, c)
    if violations:
        raise HTTPException(422, violations[0][2])


# Run status for a claim rejected at intake. Findings need a processing run (findings.run_id is NOT NULL), so a
# minimal run is created with this status and a fixed idempotency key; no agents run and no risk assessment exists.
INTAKE_REJECTED = "INTAKE_REJECTED"
INTAKE_RULE_VERSION = "intake-policy-rules-1"


def store_rejected_claim(claim: Claim, docs: list[DocumentInfo], rule: str, message: str) -> None:
    """Persist a claim that failed a policy eligibility rule, with a CONFIRMED_RULE_VIOLATION Finding from the
    Policy_Eligibility agent, so an Investigator can review it (Requirement 8.6). The claim gets status
    POLICY_VIOLATION and is not counted as an earlier submission by duplicate or history lookups."""
    from app.db import models as m
    from app.db.repos import POLICY_VIOLATION

    now = datetime.now(timezone.utc)
    with open_repos() as repos:
        row = repos.register_claim(claim, [d.sha256 for d in docs])
        row.status = POLICY_VIOLATION
        row.channel = "customer"
        run = m.ProcessingRun(claim_id=row.id, idempotency_key="intake-rejected", status=INTAKE_REJECTED,
                              rule_version=INTAKE_RULE_VERSION, started_at=now, finished_at=now)
        repos.session.add(run)
        repos.session.flush()
        repos.session.add(m.FindingRow(
            claim_id=row.id, run_id=run.id, use_case_id="1-12", check_id=f"intake.{rule.lower()}",
            category="policy_eligibility", agent="Policy_Eligibility", severity="high",
            status="CONFIRMED_RULE_VIOLATION", explanation=f"{rule}: {message}", method="RULE", confidence=1.0,
            confidence_definition="Deterministic rule comparison; the result is exact.",
            next_action="Review the claim and contact the policyholder if the rule was applied in error.",
            correlation_key=f"policy_eligibility:{rule}", rule_version=INTAKE_RULE_VERSION))


async def accept_submission(payload: str, documents: list[UploadFile], document_types: str) -> str:
    """Validate a ClaimSubmission JSON + documents, apply policy rules, store and start processing.
    Returns the new claim id. Shared by ``POST /api/claims`` and ``POST /api/internal/claims``.

    Analysis settings come from server configuration only; any extra client field (for example ``use_llm``) is
    never read (Requirement 8.2). A policy eligibility violation is returned as 422 and the claim is stored with
    a Finding for review (Requirement 8.6)."""
    try:
        sub = ClaimSubmission.model_validate(json.loads(payload))
        types = json.loads(document_types)
        if not isinstance(types, list):
            raise ValueError("document_types must be a list")
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise HTTPException(422, f"Invalid claim: {e}")

    p = verified_policy(sub.policy_number, sub.date_of_birth)
    violations = policy_rule_violations(p, sub)
    first = violations[0] if violations else None
    if any(v[0] == INVALID for v in violations):  # malformed data: plain 422, nothing stored
        raise HTTPException(422, first[2])
    if not first and not documents:
        raise HTTPException(422, "Please upload at least one document.")

    docs = await read_documents(documents, types)
    claim = Claim(claim_id=f"CLM-{uuid.uuid4().hex[:10].upper()}", claimant_id=p["claimant_id"],
                  claimant_name=p["holder_name"], hospital_id=sub.hospital_id, doctor_id=sub.doctor_id,
                  diagnosis=DISEASES[sub.disease_id]["name"], admission_date=sub.admission_date,
                  discharge_date=sub.discharge_date, claimed_amount=sub.claimed_amount, invoice=sub.invoice,
                  policy_number=sub.policy_number.strip().upper(), disease_id=sub.disease_id)
    if first:
        store_rejected_claim(claim, docs, first[1], first[2])
        raise HTTPException(422, first[2])
    # The console's LLM analysis switch (server-side, Administrator-controlled) decides; read once per claim.
    from app import runtime_settings

    jobs.start(claim, docs, runtime_settings.llm_effective())
    return claim.claim_id
