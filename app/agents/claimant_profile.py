"""User Profile agent (agent id ``claimant_profile``): the policyholder's claim history and behaviour.

Documented in docs/agents/user_profile.md. The profile logic is shared with the investigator profile page
(``app/core/user_profile.py``). Deterministic; the optional LLM review runs afterwards in the pipeline and
never sees names, dates of birth or real claimant/policy ids.

Signals for the claim being assessed (codes, see app/core/user_profile.py):
  frequency and amounts : CLAIM_FREQUENCY, CLAIM_FREQUENCY_EXTREME, AMOUNT_SPIKE, AMOUNT_ESCALATION,
                          REPEATED_SIMILAR_AMOUNTS, HOSPITAL_HOPPING, HIGH_AMOUNT_SHORT_STAY
  submission behaviour  : DATES_INVALID, LATE_SUBMISSION, CLAIM_SOON_AFTER_POLICY_START,
                          CLAIM_NEAR_POLICY_END, POLICY_END_PATTERN, SUM_INSURED_NEAR_LIMIT
  re-claiming           : RESUBMITTED_STAY, OVERLAPPING_STAYS_ELSEWHERE
  earlier fraud         : PRIOR_FRAUD_DECISION
"""
from app.agents.base import Agent
from app.core.user_profile import build_profile
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Finding


def current_row(claim: Claim) -> dict:
    return {"claim_id": claim.claim_id, "submitted": claim.submitted_on, "admission": claim.admission_date,
            "discharge": claim.discharge_date, "amount": claim.claimed_amount, "hospital_id": claim.hospital_id,
            "doctor_id": claim.doctor_id, "disease": claim.disease_id, "invoice_number": claim.invoice.invoice_number,
            "decision": None}


class ClaimantProfileAgent(Agent):
    """Builds the user (claimant) profile from claim history and checks this claim against it."""
    name = "claimant_profile"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        with open_repos() as repos:
            prior = repos.claimant_records(claim.claimant_id, exclude_ref=claim.claim_id)
            policy = repos.policy(claim.policy_number) if claim.policy_number else None
        profile = build_profile(current_row(claim), prior, policy)
        findings = [Finding(code=s["code"], severity=s["severity"], detail=s["detail"]) for s in profile["signals"]]
        return self.result(findings)
