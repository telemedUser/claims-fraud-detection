from app.agents.base import Agent
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Finding


class ClaimantProfileAgent(Agent):
    """Builds a claimant behaviour profile from claim history."""
    name = "claimant_profile"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        f: list[Finding] = []
        with open_repos() as repos:
            past = repos.history(claim.claimant_id)

        recent = [c for c in past if 0 <= (claim.submitted_on - c["date"]).days <= 90]
        if len(recent) >= 2:
            f.append(Finding(code="CLAIM_FREQUENCY", severity="medium",
                             detail=f"{len(recent)} other claims in the last 90 days."))
        if len(recent) >= 4:
            f.append(Finding(code="CLAIM_FREQUENCY_EXTREME", severity="high", detail="4 or more claims in 90 days."))

        if past:
            avg = sum(c["amount"] for c in past) / len(past)
            if claim.claimed_amount > 3 * avg:
                f.append(Finding(code="AMOUNT_SPIKE", severity="medium",
                                 detail=f"Claim is more than 3x the claimant's average ({avg:.0f})."))
            hospitals = {c["hospital_id"] for c in past}
            if len(hospitals) >= 3:
                f.append(Finding(code="HOSPITAL_HOPPING", severity="medium",
                                 detail=f"Claimant has used {len(hospitals)} different hospitals."))
            amounts = [c["amount"] for c in past] + [claim.claimed_amount]
            if len(amounts) >= 3 and max(amounts) - min(amounts) < 0.1 * max(amounts):
                f.append(Finding(code="REPEATED_SIMILAR_AMOUNTS", severity="medium",
                                 detail="Claim amounts are almost identical across claims."))

        stay = (claim.discharge_date - claim.admission_date).days
        if stay < 0:
            f.append(Finding(code="DATES_INVALID", severity="high", detail="Discharge date is before admission date."))
        if (claim.submitted_on - claim.discharge_date).days > 90:
            f.append(Finding(code="LATE_SUBMISSION", severity="low", detail="Claim submitted over 90 days after discharge."))
        if claim.claimed_amount > 100000 and stay <= 1:
            f.append(Finding(code="HIGH_AMOUNT_SHORT_STAY", severity="medium",
                             detail="High claim amount for a stay of one day or less."))
        return self.result(f)
