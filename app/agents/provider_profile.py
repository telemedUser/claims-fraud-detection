from app.agents.base import Agent
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Finding


class ProviderProfileAgent(Agent):
    """Builds hospital and doctor risk profiles and checks the claim against them."""
    name = "provider_profile"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        f: list[Finding] = []
        with open_repos() as repos:
            h = repos.hospital(claim.hospital_id)
            d = repos.doctor(claim.doctor_id)

        if not h:
            f.append(Finding(code="HOSPITAL_UNKNOWN", severity="high", detail="Hospital not found in registry."))
        else:
            if not h["registered"]:
                f.append(Finding(code="HOSPITAL_UNREGISTERED", severity="high", detail=f"{h['name']} is not a registered facility."))
            if h["flagged_claims_ratio"] > 0.2:
                f.append(Finding(code="HOSPITAL_HIGH_FRAUD_RATE", severity="medium",
                                 detail=f"{h['flagged_claims_ratio']:.0%} of this hospital's past claims were flagged."))
            if h["years_active"] < 2:
                f.append(Finding(code="HOSPITAL_NEW", severity="low", detail="Hospital has under 2 years of claim history."))
            z = (claim.claimed_amount - h["avg_claim"]) / max(h["std_claim"], 1)
            if z > 2:
                f.append(Finding(code="AMOUNT_OUTLIER_FOR_HOSPITAL", severity="medium",
                                 detail=f"Claim is {z:.1f} standard deviations above the hospital average ({h['avg_claim']})."))
            if h["tax_id"] and claim.invoice.tax_id and claim.invoice.tax_id != h["tax_id"]:
                f.append(Finding(code="TAX_ID_MISMATCH", severity="high",
                                 detail="Tax ID on invoice does not match the hospital registry."))

        if not d:
            f.append(Finding(code="DOCTOR_UNKNOWN", severity="high", detail="Doctor not found in registry."))
        else:
            if not d["license_valid"]:
                f.append(Finding(code="DOCTOR_LICENSE_INVALID", severity="high", detail=f"{d['name']} has no valid license on record."))
            if claim.hospital_id not in d["hospital_ids"]:
                f.append(Finding(code="DOCTOR_NOT_AFFILIATED", severity="high",
                                 detail="Doctor is not affiliated with the claimed hospital."))
            if len(d["hospital_ids"]) >= 3:
                f.append(Finding(code="DOCTOR_MANY_HOSPITALS", severity="low",
                                 detail=f"Doctor is attached to {len(d['hospital_ids'])} hospitals."))
            if d["claims_per_month"] > 150:
                f.append(Finding(code="DOCTOR_HIGH_VOLUME", severity="medium",
                                 detail=f"Doctor appears on {d['claims_per_month']} claims per month."))
            if d["flagged_claims_ratio"] > 0.2:
                f.append(Finding(code="DOCTOR_HIGH_FRAUD_RATE", severity="medium",
                                 detail=f"{d['flagged_claims_ratio']:.0%} of this doctor's claims were flagged."))
        return self.result(f)
