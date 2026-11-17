from app.agents.base import Agent
from app.data import store
from app.models import Claim, DocumentInfo, Finding


class InvoiceCheckAgent(Agent):
    """Validates invoice arithmetic, identity, duplicates and consistency with the claim."""
    name = "invoice_check"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        f: list[Finding] = []
        inv = claim.invoice

        line_sum = round(sum(i.amount for i in inv.line_items), 2)
        if abs(line_sum - inv.total) > 1:
            f.append(Finding(code="INVOICE_TOTAL_MISMATCH", severity="high",
                             detail=f"Line items sum to {line_sum} but invoice total is {inv.total}."))
        if abs(inv.total - claim.claimed_amount) > 1:
            f.append(Finding(code="CLAIM_VS_INVOICE_MISMATCH", severity="high",
                             detail=f"Claimed {claim.claimed_amount} but invoice total is {inv.total}."))
        if store.invoice_seen(claim.hospital_id, inv.invoice_number):
            f.append(Finding(code="DUPLICATE_INVOICE", severity="high",
                             detail=f"Invoice {inv.invoice_number} was already submitted for this hospital."))
        if not (claim.admission_date <= inv.invoice_date <= claim.submitted_on):
            f.append(Finding(code="INVOICE_DATE_OUT_OF_RANGE", severity="medium",
                             detail=f"Invoice date {inv.invoice_date} is outside admission to submission window."))
        if not inv.tax_id:
            f.append(Finding(code="TAX_ID_MISSING", severity="medium", detail="Invoice has no tax / registration ID."))
        if inv.total >= 10000 and inv.total % 1000 == 0:
            f.append(Finding(code="ROUND_TOTAL", severity="low", detail="Invoice total is a suspiciously round number."))
        descs = [i.description.strip().lower() for i in inv.line_items]
        if len(descs) != len(set(descs)):
            f.append(Finding(code="DUPLICATE_LINE_ITEMS", severity="medium", detail="Same line item billed more than once."))
        if any(i.amount <= 0 for i in inv.line_items):
            f.append(Finding(code="NON_POSITIVE_LINE_ITEM", severity="medium", detail="Line item has zero or negative amount."))
        if not inv.line_items:
            f.append(Finding(code="NO_LINE_ITEMS", severity="high", detail="Invoice has no itemisation."))

        dz = store.disease(claim.disease_id) if claim.disease_id else None
        if dz:
            lo, hi = dz["typical_cost"]
            if claim.claimed_amount > 1.5 * hi:
                f.append(Finding(code="AMOUNT_ABOVE_TYPICAL_FOR_DIAGNOSIS", severity="medium",
                                 detail=f"Claimed {claim.claimed_amount:,.0f} is over 1.5x the typical maximum "
                                        f"({hi:,.0f}) for {dz['name']}."))
            stay = (claim.discharge_date - claim.admission_date).days
            if stay > dz["typical_stay_days"][1] + 3:
                f.append(Finding(code="STAY_LONGER_THAN_TYPICAL", severity="low",
                                 detail=f"Stay of {stay} days exceeds the typical {dz['typical_stay_days'][1]} days for {dz['name']}."))
        return self.result(f)
