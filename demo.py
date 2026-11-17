"""Runs two sample claims through the agents without starting the API."""
import asyncio
import io
import json
from datetime import date

from pypdf import PdfWriter

from app.models import Claim, DocumentInfo
from app.orchestrator import assess_claim
import hashlib


def make_pdf(producer: str, created: str, modified: str) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_metadata({"/Producer": producer, "/CreationDate": created, "/ModDate": modified})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def doc(name, data):
    return DocumentInfo(filename=name, content_type="application/pdf", size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), data=data)


CLEAN = Claim(
    claim_id="CL-1", claimant_id="U003", claimant_name="A. Kumar", hospital_id="H001", doctor_id="D001",
    diagnosis="Appendicitis", admission_date=date(2026, 11, 1), discharge_date=date(2026, 11, 5),
    claimed_amount=41850, submitted_on=date(2026, 11, 10),
    invoice={"invoice_number": "INV-9001", "invoice_date": date(2026, 11, 5),
             "line_items": [{"description": "Surgery", "amount": 29850}, {"description": "Room", "amount": 12000}],
             "total": 41850, "tax_id": "27AAACC1111A1Z5"})

SUSPICIOUS = Claim(
    claim_id="CL-2", claimant_id="U002", claimant_name="R. Singh", hospital_id="H003", doctor_id="D002",
    diagnosis="Fever", admission_date=date(2026, 11, 8), discharge_date=date(2026, 11, 9),
    claimed_amount=120000, submitted_on=date(2026, 11, 12),
    invoice={"invoice_number": "INV-2003", "invoice_date": date(2026, 10, 1),
             "line_items": [{"description": "Consultation", "amount": 50000}, {"description": "Consultation", "amount": 50000}],
             "total": 100000})


async def main():
    for claim, d in [(CLEAN, doc("bill.pdf", make_pdf("Hospital Billing System v4", "D:20261105090000", "D:20261105090000"))),
                     (SUSPICIOUS, doc("bill_edited.pdf", make_pdf("Adobe Photoshop 25.0", "D:20260101000000", "D:20261110120000")))]:
        result = await assess_claim(claim, [d])
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        print("=" * 60)


asyncio.run(main())
