"""Invoice Check agent: bill arithmetic and plausibility, GST verification, duplicate bills and payment status.
Documented in docs/agents/invoice_check.md."""
import re

from app.agents.base import Agent
from app.db.repos import ReferenceRepo, open_repos
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
        with open_repos() as repos:
            seen = repos.invoice_seen(claim.hospital_id, inv.invoice_number)
        if seen:
            f.append(Finding(code="DUPLICATE_INVOICE", severity="high",
                             detail=f"Invoice {inv.invoice_number} was already submitted for this hospital."))
        if not (claim.admission_date <= inv.invoice_date <= claim.submitted_on):
            f.append(Finding(code="INVOICE_DATE_OUT_OF_RANGE", severity="medium",
                             detail=f"Invoice date {inv.invoice_date} is outside admission to submission window."))
        if inv.total >= 10000 and inv.total % 1000 == 0:
            f.append(Finding(code="ROUND_TOTAL", severity="low", detail="Invoice total is a suspiciously round number."))
        descs = [i.description.strip().lower() for i in inv.line_items]
        if len(descs) != len(set(descs)):
            f.append(Finding(code="DUPLICATE_LINE_ITEMS", severity="medium", detail="Same line item billed more than once."))
        if any(i.amount <= 0 for i in inv.line_items):
            f.append(Finding(code="NON_POSITIVE_LINE_ITEM", severity="medium", detail="Line item has zero or negative amount."))
        if not inv.line_items:
            f.append(Finding(code="NO_LINE_ITEMS", severity="high", detail="Invoice has no itemisation."))

        dz = ReferenceRepo().disease(claim.disease_id)
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

        bill_texts = _bill_texts(documents)
        f += _gst_checks(claim, bill_texts, dz)
        f += _duplicate_checks(claim)
        f += _payment_checks(claim, documents, bill_texts)
        return self.result(f)


# ---------------------------------------------------------------- GST, duplicates, payment (docs/agents/invoice_check.md)

_GST_LINE = re.compile(r"\b(CGST|SGST|UTGST|IGST|GST)\b", re.I)


def _bill_texts(documents: list[DocumentInfo]) -> list[str]:
    """Text of the bill documents (or of every document when none is labelled as a bill)."""
    from app.core.doc_text import document_texts

    texts = document_texts([d for d in documents if d.doc_type == "medical_bill"] or
                           [d for d in documents if d.doc_type == "other"])
    return [t for _, t in texts]


def _gst_checks(claim: Claim, bill_texts: list[str], dz: dict | None) -> list[Finding]:
    """GSTIN validity and GST charged on the bill. A missing GSTIN or no GST is not a finding: most
    hospital services are GST-exempt (non-negotiable rule 5)."""
    from app.core.doc_text import fields
    from app.core.text_match import find_gstins, normalise_id
    from app.core.validators import gstin as gstin_validator

    f: list[Finding] = []
    gstins = {normalise_id(g) for t in bill_texts for g in find_gstins(t)}
    if claim.invoice.tax_id:
        gstins.add(normalise_id(claim.invoice.tax_id))
    bad = sorted(g for g in gstins if g and not gstin_validator.is_valid(g))
    if bad:
        f.append(Finding(code="GSTIN_INVALID", severity="high",
                         detail=f"GSTIN {', '.join(bad)} on the bill fails the GSTIN format or check-digit test."))

    tax: dict[str, float] = {"CGST": 0.0, "SGST": 0.0, "UTGST": 0.0, "IGST": 0.0, "GST": 0.0}
    for li in claim.invoice.line_items:
        m = _GST_LINE.search(li.description or "")
        if m:
            tax[m.group(1).upper()] += li.amount
    for t in bill_texts:
        for k, values in fields(t)["gst"].items():
            tax[k] = max(tax[k], sum(values))
    charged = sum(tax.values())
    if charged <= 0:
        return f
    valid = [g for g in gstins if gstin_validator.is_valid(g)]
    if not valid:
        f.append(Finding(code="GST_CHARGED_WITHOUT_GSTIN", severity="medium",
                         detail=f"The bill charges {charged:,.2f} GST but shows no valid GSTIN; GST can only be collected "
                                f"by a GST-registered supplier."))
    local = tax["CGST"], tax["SGST"] + tax["UTGST"]
    if (local[0] > 0) != (local[1] > 0) or (all(local) and abs(local[0] - local[1]) > 1):
        f.append(Finding(code="GST_SPLIT_MISMATCH", severity="medium",
                         detail=f"CGST ({local[0]:,.2f}) and SGST/UTGST ({local[1]:,.2f}) should be charged in equal halves."))
    if tax["IGST"] > 0 and any(local):
        f.append(Finding(code="GST_MIXED_IGST", severity="medium",
                         detail="The bill charges both IGST and CGST/SGST on the same supply."))
    if dz and dz.get("category") in ("Medical", "Surgical", "Orthopaedic", "Ophthalmic", "Urology"):
        f.append(Finding(code="GST_ON_EXEMPT_SERVICES", severity="low",
                         detail=f"The bill charges {charged:,.2f} GST on {dz['name']} treatment, which is generally "
                                f"GST-exempt; GST applies only to some items (for example costly room rent or cosmetics)."))
    return f


def _norm_invoice(number: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(number or "").upper()).lstrip("0")


def _duplicate_checks(claim: Claim) -> list[Finding]:
    """Duplicates beyond the exact (hospital, invoice number) match: number variants, the same number at another
    hospital, and the same bill under a new number (same hospital, date and total)."""
    inv = claim.invoice
    with open_repos() as repos:
        rows = repos.invoice_candidates(claim.hospital_id, inv.invoice_number, claim.claim_id)
    mine = _norm_invoice(inv.invoice_number)
    f: list[Finding] = []
    variants = [r for r in rows if r["hospital_id"] == claim.hospital_id and r["invoice_number"] != inv.invoice_number
                and _norm_invoice(r["invoice_number"]) == mine]
    if variants:
        f.append(Finding(code="DUPLICATE_INVOICE_VARIANT", severity="high",
                         detail=f"Bill {inv.invoice_number} matches earlier bill {variants[0]['invoice_number']} at the same "
                                f"hospital once spaces, dashes and leading zeros are ignored (claim {variants[0]['claim_id']})."))
    elsewhere = [r for r in rows if r["hospital_id"] != claim.hospital_id and _norm_invoice(r["invoice_number"]) == mine]
    if elsewhere:
        f.append(Finding(code="INVOICE_NUMBER_AT_OTHER_HOSPITAL", severity="low",
                         detail=f"Bill number {inv.invoice_number} was also used on a claim at hospital {elsewhere[0]['hospital_id']} "
                                f"(claim {elsewhere[0]['claim_id']})."))
    same_bill = [r for r in rows if r["hospital_id"] == claim.hospital_id and r["invoice_date"] == inv.invoice_date
                 and r["total"] is not None and abs(r["total"] - inv.total) <= 1 and _norm_invoice(r["invoice_number"]) != mine]
    if same_bill:
        f.append(Finding(code="DUPLICATE_BILL_NEW_NUMBER", severity="high",
                         detail=f"An earlier bill at the same hospital has the same date ({inv.invoice_date}) and total "
                                f"({inv.total:,.2f}) under a different number ({same_bill[0]['invoice_number']}, claim "
                                f"{same_bill[0]['claim_id']})."))
    return f


def _payment_checks(claim: Claim, documents: list[DocumentInfo], bill_texts: list[str]) -> list[Finding]:
    """Reimbursement needs a paid bill: payment status printed on the bill and on any uploaded payment receipt."""
    from app.core.doc_text import document_texts, fields

    if not bill_texts:
        return []  # no readable bill: Document Scan reports missing or unreadable bills
    bill = fields("\n".join(bill_texts))
    receipts = [fields(t) for _, t in document_texts([d for d in documents if d.doc_type == "payment_receipt"])]
    paid_values = [x for x in [bill["amount_paid"]] + [r["amount_paid"] for r in receipts] if x is not None]
    paid = max(paid_values) if paid_values else None
    mode = (bill["payment_mode"] or "").lower()
    f: list[Finding] = []
    if re.search(r"cashless|\btpa\b|insurer|insurance", mode):
        f.append(Finding(code="CASHLESS_BILL_CLAIMED", severity="high",
                         detail=f"The bill's payment mode is '{bill['payment_mode']}', so the hospital may already be paid "
                                f"by an insurer, yet the claim asks for reimbursement."))
    if bill["balance_due"] is not None and bill["balance_due"] > 1:
        f.append(Finding(code="BILL_PAYMENT_PENDING", severity="medium",
                         detail=f"The bill shows a balance due of {bill['balance_due']:,.2f}: it has not been paid in full."))
    if paid is not None and claim.claimed_amount > paid + 1:
        f.append(Finding(code="CLAIM_EXCEEDS_AMOUNT_PAID", severity="high",
                         detail=f"Claimed {claim.claimed_amount:,.2f} but the bill and receipts show {paid:,.2f} paid."))
    if paid is None and bill["balance_due"] is None and not receipts:
        f.append(Finding(code="PAYMENT_NOT_EVIDENCED", severity="low",
                         detail="Neither the bill nor an uploaded receipt shows that the bill was paid."))
    paid_on = [d for d in [bill["paid_on"]] + [r["paid_on"] for r in receipts] if d]
    late = [d for d in paid_on if d < claim.admission_date or d > claim.submitted_on]
    if late:
        f.append(Finding(code="PAYMENT_DATE_OUT_OF_RANGE", severity="medium",
                         detail=f"Payment dated {late[0]} is outside the admission-to-submission window "
                                f"({claim.admission_date} to {claim.submitted_on})."))
    return f
