"""Shows which Provider Profile checks fire for the demo scenarios and for one targeted case per new check.

Runs on its own seeded in-memory database (never touches claims_fraud.db) with the LLM off.
Usage: python scripts/provider_profile_demo.py
"""
import asyncio
import hashlib
import io
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(GEMINI_API_KEY="", BEDROCK_MODEL_ID="", JWT_SECRET="demo-secret-demo-secret-demo-secret-1",
                  DEV_SEED_DEFAULT_PASSWORDS="false")

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.agents.provider_profile import ProviderProfileAgent  # noqa: E402
from app.db import models as m  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.models import Claim, DocumentInfo, Invoice, LineItem  # noqa: E402
from app.pipeline import assess_claim  # noqa: E402
from app.seed import docgen, seed_data as sd  # noqa: E402
from app.seed.run import seed  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
AGENT = ProviderProfileAgent()


def fresh_db():
    engine = db_session.make_engine("sqlite://")
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)
    db_session.set_engine(engine)


def run(claim, docs=()):
    return asyncio.run(AGENT.analyze(claim, list(docs)))


def claim(hospital="H001", doctor="D001", disease="appendicitis", amount=41850, adm=None, days=4, claimant="U001",
          tax_id=None, cid=None):
    adm = adm or TODAY - timedelta(days=10)
    return Claim(claim_id=cid or f"CLM-DEMO-{uuid.uuid4().hex[:6]}", claimant_id=claimant, claimant_name="Demo",
                 hospital_id=hospital, doctor_id=doctor, diagnosis=sd.DISEASES[disease]["name"], disease_id=disease,
                 admission_date=adm, discharge_date=adm + timedelta(days=days), claimed_amount=amount,
                 policy_number="POL-1001",
                 invoice=Invoice(invoice_number=f"INV-{uuid.uuid4().hex[:6]}", invoice_date=adm + timedelta(days=days),
                                 total=amount, tax_id=tax_id, line_items=[LineItem(description="Treatment", amount=amount)]))


def ids(s, hospital=None, doctor=None):
    pid = s.scalars(select(m.Provider.id).where(m.Provider.code == hospital)).first() if hospital else None
    did = s.scalars(select(m.Doctor.id).where(m.Doctor.code == doctor)).first() if doctor else None
    return pid, did


def add_claim(s, hospital, doctor, disease, amount, adm, claimant, days=2, submitted=None):
    pid, did = ids(s, hospital, doctor)
    row = m.Claim(claim_ref=f"PRIOR-{uuid.uuid4().hex[:8]}", claimant_ref=claimant, provider_id=pid, doctor_id=did,
                  disease_code=disease, admission_date=adm, discharge_date=adm + timedelta(days=days),
                  claimed_amount=Decimal(str(amount)), submitted_on=submitted or NOW - timedelta(days=5),
                  status="ASSESSED", is_test=True)
    s.add(row)
    s.flush()
    return row


def pdfs(case, doc_types=docgen.DOC_TYPES):
    out = []
    for t in doc_types:
        data = docgen.render(case, t)
        out.append(DocumentInfo(filename=f"{t}.pdf", content_type="application/pdf", size=len(data),
                                sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=t))
    return out


def png_doc():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    data = buf.getvalue()
    return DocumentInfo(filename="bill_photo.png", content_type="image/png", size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type="medical_bill")


def show(title, result, expect):
    codes = [f.code for f in result.findings]
    ok = all(e in codes for e in expect) if expect else not codes
    print(f"\n[{'PASS' if ok else 'FAIL'}] {title}")
    for f in result.findings:
        mark = "*" if f.code in expect else " "
        print(f"   {mark} {f.severity:<6} {f.code}: {f.detail}")
    if not result.findings:
        print("     (no findings)")
    return ok


def main():
    results = []

    # ---- demo scenarios through the full pipeline (provider findings only, plus the claim score)
    print("=" * 100 + "\nDEMO SCENARIOS (full pipeline, LLM off)")
    for name, sc in sd.SCENARIOS.items():
        fresh_db()
        case = docgen.build_case(sc["case"])
        case["invoice_number"] = sc["invoice_number"]
        c = Claim(**docgen.claim_json(case, f"SC-{name}"))
        res = asyncio.run(assess_claim(c, pdfs(case, case["doc_types"]), use_llm=False, register=None))
        prov = next(a for a in res.agent_results if a.agent == "provider_profile")
        print(f"\n{name}: score {res.risk_score} -> {res.recommended_queue} (expected {sc['expected']})")
        for f in prov.findings:
            print(f"     {f.severity:<6} {f.code}: {f.detail}")

    print("\n" + "=" * 100 + "\nTARGETED CASES (Provider Profile agent only)")

    # ---- C: registry checks dated to the admission
    fresh_db()
    with db_session.get_session() as s:
        s.scalars(select(m.Doctor).where(m.Doctor.code == "D001")).one().licence_valid_to = TODAY - timedelta(days=30)
    results.append(show("Licence expired before admission", run(claim()), ["DOCTOR_LICENCE_EXPIRED"]))

    fresh_db()
    results.append(show("Affiliation ended before admission (D002 left H003 on 2026-06-30)",
                        run(claim(hospital="H003", doctor="D002", disease="viral_fever", amount=15000, adm=date(2026, 8, 1))),
                        ["DOCTOR_AFFILIATION_INACTIVE"]))

    fresh_db()
    results.append(show("Admission before the hospital joined the network (H002 from 2025-06-01)",
                        run(claim(hospital="H002", doctor="D002", disease="viral_fever", amount=15000, adm=date(2025, 3, 1))),
                        ["HOSPITAL_NOT_EMPANELLED_ON_DATE"]))

    fresh_db()
    with db_session.get_session() as s:
        s.scalars(select(m.Provider).where(m.Provider.code == "H005")).one().state_code = "27"
    results.append(show("Registry GSTIN state differs from the hospital's state",
                        run(claim(hospital="H005", doctor="D006", disease="pneumonia", amount=40000)),
                        ["GSTIN_STATE_MISMATCH"]))

    fresh_db()
    results.append(show("Doctor with no registration number on record (D008)",
                        run(claim(hospital="H004", doctor="D008", disease="kidney_stone", amount=50000)),
                        ["DOCTOR_REGISTRATION_MISSING"]))

    # ---- C: specialty fit
    fresh_db()
    results.append(show("Orthopaedic surgeon billing an appendectomy",
                        run(claim(doctor="D005")), ["DOCTOR_SPECIALTY_MISMATCH"]))
    fresh_db()
    results.append(show("Fracture surgery at a general-medicine clinic",
                        run(claim(hospital="H002", doctor="D002", disease="fracture", amount=60000)),
                        ["HOSPITAL_SPECIALTY_NOT_OFFERED", "DOCTOR_SPECIALTY_MISMATCH"]))

    # ---- C: same doctor, same day, another city; hospital over capacity
    fresh_db()
    adm = TODAY - timedelta(days=8)
    with db_session.get_session() as s:
        add_claim(s, "H004", "D005", "fracture", 70000, adm, "U900")
    results.append(show("Same doctor admitted a patient in Mumbai on the same day",
                        run(claim(doctor="D005", disease="fracture", amount=60000, adm=adm)), ["DOCTOR_SAME_DAY_OTHER_CITY"]))

    fresh_db()
    with db_session.get_session() as s:
        s.scalars(select(m.Provider).where(m.Provider.code == "H002")).one().bed_count = 2
        for i in range(2):
            add_claim(s, "H002", "D002", "viral_fever", 12000, adm - timedelta(days=1), f"U9{i}", days=3)
    results.append(show("More overlapping admissions than beds (H002 set to 2 beds)",
                        run(claim(hospital="H002", doctor="D002", disease="viral_fever", amount=12000, adm=adm)),
                        ["HOSPITAL_OVER_CAPACITY"]))

    # ---- B: computed profile
    fresh_db()
    results.append(show("Hospital volume surge (H002: 30 recent claims vs baseline 6)",
                        run(claim(hospital="H002", doctor="D002", disease="viral_fever", amount=15000)),
                        ["HOSPITAL_VOLUME_SURGE"]))

    fresh_db()
    with db_session.get_session() as s:
        for i in range(3):
            add_claim(s, "H004", "D004", "pneumonia", 52000 + i * 300, TODAY - timedelta(days=20 + i), f"U8{i}")
    results.append(show("Doctor's other patients claimed near-identical amounts",
                        run(claim(hospital="H004", doctor="D004", disease="pneumonia", amount=52400)), ["DOCTOR_SIMILAR_BILLS"]))

    fresh_db()
    with db_session.get_session() as s:
        for amt in (29000, 31000, 30500, 28500, 30000):
            add_claim(s, "H005", "D007", "cataract", amt, TODAY - timedelta(days=40), "U70")
    r = run(claim(hospital="H005", doctor="D007", disease="cataract", amount=45000, days=1))
    results.append(show("Outlier against the hospital's own cataract claims (registry average would not flag it)",
                        r, ["AMOUNT_OUTLIER_FOR_HOSPITAL"]))

    fresh_db()
    with db_session.get_session() as s:
        for i, amt in enumerate((38000, 40000, 41000, 39000, 42000, 40500, 39500, 41500)):
            add_claim(s, "H004" if i % 2 else "H005", "D004" if i % 2 else "D006", "appendicitis", amt,
                      TODAY - timedelta(days=60), f"U6{i}")
    results.append(show("Claim far above peer hospitals for the same diagnosis",
                        run(claim(amount=95000)), ["PEER_COST_OUTLIER"]))

    fresh_db()
    with db_session.get_session() as s:
        user = m.User(username="demo_inv", password_hash="x", role="Investigator", is_active=True)
        s.add(user)
        s.flush()
        for i in range(10):
            row = add_claim(s, "H004", "D004", "pneumonia", 50000, TODAY - timedelta(days=90), f"U5{i}")
            s.add(m.InvestigatorDecision(claim_id=row.id, user_id=user.id, decision="deny" if i < 8 else "approve",
                                         reason="demo"))
    results.append(show("Flag rate learned from investigator decisions (H004 registry 3%, 8 of 10 denied)",
                        run(claim(hospital="H004", doctor="D004", disease="pneumonia", amount=50000)),
                        ["HOSPITAL_HIGH_FRAUD_RATE"]))

    # ---- C: documents against the registry
    fresh_db()
    case = docgen.build_case("clean")
    case["hospital"] = sd.HOSPITALS["H004"] | {}
    case["bill_tax_id"] = sd.HOSPITALS["H004"]["tax_id"]
    results.append(show("Documents printed by a different hospital (Lakeview) for a City General claim",
                        run(claim(), pdfs(case)), ["DOC_HOSPITAL_NAME_MISMATCH", "DOC_GSTIN_MISMATCH"]))

    fresh_db()
    case = docgen.build_case("clean")
    case["doctor"] = sd.DOCTORS["D004"] | {}
    results.append(show("Prescription and report signed by another doctor (Dr. Priya Nair)",
                        run(claim(), pdfs(case)), ["DOC_DOCTOR_NAME_MISSING", "DOC_DOCTOR_REG_MISMATCH"]))

    fresh_db()
    case = docgen.build_case("clean")
    case["doctor"] = sd.DOCTORS["D001"] | {"registration_no": "MMC-2010-99999"}
    results.append(show("Correct doctor name but a different registration number on the documents",
                        run(claim(), pdfs(case)), ["DOC_DOCTOR_REG_MISMATCH"]))

    fresh_db()
    results.append(show("Photo of a bill (no machine-readable text)", run(claim(), [png_doc()]), ["PROVIDER_DOCS_NOT_CHECKED"]))

    fresh_db()
    case = docgen.build_case("clean")
    results.append(show("Clean claim with matching documents (expect no provider findings)",
                        run(claim(), pdfs(case)), []))

    print(f"\n{sum(results)}/{len(results)} targeted cases behaved as expected")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
