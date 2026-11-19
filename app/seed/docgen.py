"""Generates fictional test documents (medical bill, prescription, medical report) for demo cases.

Every page carries a "SAMPLE - TEST DATA ONLY" watermark. All people, hospitals and IDs are fictional
and come from the seeded data in app/seed/seed_data.py. Dates are relative to `today` so cases always fall
inside the demo policies' validity windows.
"""
import copy
import io
import uuid
from datetime import date, timedelta

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from app.seed import seed_data as sd

DOC_TYPES = ("medical_bill", "prescription", "medical_report", "lab_report")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Title"], fontSize=16, spaceAfter=2)
SUB = ParagraphStyle("sub", parent=_ss["Normal"], fontSize=8.5, alignment=1, textColor=colors.HexColor("#475569"))
H2 = ParagraphStyle("h2", parent=_ss["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=4)
N = ParagraphStyle("n", parent=_ss["Normal"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("s", parent=_ss["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))


def _pdfdate(d: date, hhmmss: str = "091500") -> str:
    return f"D:{d:%Y%m%d}{hhmmss}"


# ---------------------------------------------------------------- cases

def build_case(kind: str, today: date | None = None) -> dict:
    today = today or date.today()
    uid = uuid.uuid4().hex[:6].upper()
    if kind == "clean":
        adm = today - timedelta(days=16)
        dis = adm + timedelta(days=4)
        case = {
            "policy_number": "POL-1001", "hospital_id": "H001", "doctor_id": "D001", "disease_id": "appendicitis",
            "admission": adm, "discharge": dis, "bill_date": dis, "rx_date": dis,
            "invoice_number": f"INV-{uid}", "bill_tax_id": sd.HOSPITALS["H001"]["tax_id"],
            "items": [(f"Room charges - semi-private ({(dis - adm).days} days x 3,000)", (dis - adm).days, 3000),
                      ("Laparoscopic appendectomy (surgeon + OT)", 1, 22000),
                      ("Anaesthesia charges", 1, 4500),
                      ("Laboratory and imaging (CBC, CRP, USG abdomen)", 1, 2350),
                      ("Pharmacy - inpatient medicines", 1, 1000)],
            "complaints": "Pain in right lower abdomen for 2 days, nausea, low-grade fever.",
            "findings": "Tenderness at McBurney's point, positive Rovsing's sign. USG: inflamed, non-perforated appendix (9 mm).",
            "labs": [("Haemoglobin", "13.8 g/dL", "13.0 - 17.0"), ("WBC count", "14,200 /uL", "4,000 - 11,000"),
                     ("CRP", "38 mg/L", "< 5"), ("Serum creatinine", "0.9 mg/dL", "0.7 - 1.3")],
            "procedure": f"Laparoscopic appendectomy under general anaesthesia on {adm:%d-%b-%Y}. Uneventful.",
            "course": "Post-operative recovery uneventful. Afebrile from day 2. Tolerating oral diet. Wound healthy.",
            "condition": "Stable, ambulatory.",
            "rx": [("Tab. Amoxicillin-Clavulanate 625 mg", "1 tablet", "Twice daily after food", "5 days"),
                   ("Tab. Paracetamol 650 mg", "1 tablet", "Three times daily if pain/fever", "5 days"),
                   ("Tab. Pantoprazole 40 mg", "1 tablet", "Once daily before breakfast", "5 days")],
            "advice": "Avoid lifting heavy weights for 4 weeks. Keep the port-site dressings dry. Review in OPD after 7 days for a wound check.",
            # produced by the hospital billing system on the bill date
            "meta": {"/Producer": "CGH Hospital Information System v4.2", "/Creator": "CGH HIS Billing",
                     "/CreationDate": _pdfdate(dis), "/ModDate": _pdfdate(dis)},
        }
        case["claimed_amount"] = sum(q * r for _, q, r in case["items"])
        case["payment"] = {"mode": "UPI", "receipt": f"RCPT-{uid}", "paid": case["claimed_amount"], "date": dis}
    elif kind == "suspicious":
        adm = today - timedelta(days=9)
        dis = adm + timedelta(days=1)
        case = {
            "policy_number": "POL-2002", "hospital_id": "H002", "doctor_id": "D002", "disease_id": "viral_fever",
            "admission": adm, "discharge": dis, "bill_date": adm - timedelta(days=38), "rx_date": dis,
            "invoice_number": "INV-2002",  # already used in a past claim at this hospital
            "bill_tax_id": None,
            "items": [("Consultation", 1, 50000), ("Consultation", 1, 50000)],
            "claimed_amount": 120000,  # does not match bill total of 100,000
            "complaints": "Fever for 1 day.",
            "findings": "Temperature 99.4 F. No other abnormality detected.",
            "labs": [("Haemoglobin", "14.1 g/dL", "13.0 - 17.0"), ("WBC count", "7,800 /uL", "4,000 - 11,000"),
                     ("CRP", "48 mg/L", "< 5")],
            "procedure": "None.",
            "course": "Observed overnight. Fever settled with paracetamol.",
            "condition": "Stable.",
            "rx": [("Tab. Paracetamol 500 mg", "1 tablet", "Three times daily if fever", "3 days"),
                   ("Tab. Azithromycin 500 mg", "1 tablet", "Once daily", "5 days")],  # antibiotic for a viral fever
            "advice": "Oral fluids. Review if fever persists.",
            "icd": "A97.0",  # dengue code on a viral-fever claim
            # the lab issued CRP 3 mg/L (signed); the uploaded copy was altered to 48 mg/L
            "labs_signed": [("Haemoglobin", "14.1 g/dL", "13.0 - 17.0"), ("WBC count", "7,800 /uL", "4,000 - 11,000"),
                            ("CRP", "3 mg/L", "< 5")],
            # edited in Photoshop, created long before admission, modified after discharge
            "meta": {"/Producer": "Adobe Photoshop 25.0", "/Creator": "Adobe Photoshop 25.0",
                     "/CreationDate": _pdfdate(today - timedelta(days=320), "100000"),
                     "/ModDate": _pdfdate(today - timedelta(days=6), "223000")},
            # marked cashless with the full amount still due, yet claimed as a reimbursement
            "payment": {"mode": "Cashless (insurer / TPA)", "receipt": None, "paid": 0, "date": None},
            # the saved bill was edited again later (second PDF revision)
            "incremental_edit": _pdfdate(today - timedelta(days=5), "231500"),
        }
    elif kind in DEMO_KINDS:
        return _demo_case(kind, today)
    elif kind in SCENARIO_KINDS:
        return _scenario(kind, today)
    else:
        raise ValueError(f"unknown case {kind}")
    return _finish(case)


def _finish(case: dict) -> dict:
    """Attach the reference records and totals derived from the case ids."""
    case["policy"] = copy.deepcopy(sd.POLICIES.get(case["policy_number"]))
    case["hospital"] = copy.deepcopy(sd.HOSPITALS.get(case["hospital_id"]))
    case["doctor"] = copy.deepcopy(sd.DOCTORS.get(case["doctor_id"]))
    case["disease"] = copy.deepcopy(sd.DISEASES.get(case["disease_id"]))
    case["bill_total"] = sum(q * r for _, q, r in case["items"])
    case.setdefault("doc_types", DOC_TYPES)
    case.setdefault("preauth_amount", None)
    # Lab report issued by the hospital's lab, with a verification code over what the lab issued (labs_signed);
    # what is printed is case["labs"], so a difference simulates a tampered copy.
    from app.core import lab_registry
    from app.core.medical_reference import primary_icd

    prefix = sd.HOSPITAL_LAB.get(case["hospital_id"], "PCL")
    case["lab_number"] = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
    signed = case.get("labs_signed") or case["labs"]
    case["lab_code"] = lab_registry.sign(case["lab_number"], case["admission"].isoformat(), case["policy_number"],
                                         [(n, r) for n, r, _ in signed])
    case["icd"] = case.get("icd") or primary_icd(case["disease_id"])
    # Mark the PDFs as this generator's demo files for this bill number (app/core/demo_mark.py).
    from app.core import demo_mark

    sig = demo_mark.signature(case["invoice_number"])
    case["meta"] = {k: v for k, v in case["meta"].items() if k != demo_mark.META_KEY}
    if sig:
        case["meta"][demo_mark.META_KEY] = sig
    return case


# Demo scenarios of Requirement 1.4 (besides "clean"). Invoice numbers are fixed so seeding is repeatable.
DEMO_KINDS = ("high_risk", "fabricated", "borderline")
INVALID_DEMO_GSTIN = "27AAACS2222B1Z9"  # right shape, wrong check character


def _demo_case(kind: str, today: date) -> dict:
    if kind == "high_risk":
        # duplicate invoice (INV-2002 already used at H002) + invalid GSTIN + 14-day stay for viral fever;
        # Dr. Mehta at H002 carries the provider volume surge.
        case = build_case("suspicious", today)
        adm = today - timedelta(days=25)
        case.update(admission=adm, discharge=adm + timedelta(days=14), rx_date=adm + timedelta(days=14),
                    bill_tax_id=INVALID_DEMO_GSTIN)
        case["bill_date"] = case["discharge"]
        return _finish(case)
    case = build_case("clean", today)
    case.pop("icd", None)  # recomputed for the new diagnosis in _finish
    if kind == "fabricated":
        # AI/editor-looking bill: round total, editor producer metadata created and modified the same minute,
        # and a doctor who is not in any register.
        adm = today - timedelta(days=12)
        dis = adm + timedelta(days=2)
        case.update(
            policy_number="POL-1001", hospital_id="H004", doctor_id="D008", disease_id="kidney_stone",
            admission=adm, discharge=dis, bill_date=dis, rx_date=dis, invoice_number="INV-DEMO-FAB",
            bill_tax_id=sd.HOSPITALS["H004"]["tax_id"],
            items=[("Lithotripsy treatment package (all inclusive)", 1, 100000)], claimed_amount=100000,
            meta={"/Producer": "Canva", "/Creator": "Canva Magic Design",
                  "/CreationDate": _pdfdate(dis, "101000"), "/ModDate": _pdfdate(dis, "101100")})
        case["payment"] = {"mode": "UPI", "receipt": f"RCPT-FAB-{uuid.uuid4().hex[:4].upper()}", "paid": 100000, "date": dis}
        return _finish(case)
    # borderline: no discharge summary and the claim exceeds the pre-authorised amount
    # TODO(19.2): the pre-auth overrun is only stored (claims.preauth_amount); Billing_Intelligence will check it
    # later. Until then the routing comes from MISSING_MEDICAL_REPORT, AMOUNT_SPIKE and AMOUNT_OUTLIER_FOR_HOSPITAL.
    adm = today - timedelta(days=20)
    dis = adm + timedelta(days=5)
    items = [("Room charges - semi-private (5 days x 4,000)", 5, 4000), ("Pneumonia treatment and monitoring", 1, 26000),
             ("Laboratory and imaging (CBC, chest X-ray, CT)", 1, 9400), ("Pharmacy - inpatient medicines", 1, 13000)]
    case.update(
        policy_number="POL-1001", hospital_id="H005", doctor_id="D006", disease_id="pneumonia",
        admission=adm, discharge=dis, bill_date=dis, rx_date=dis, invoice_number="INV-DEMO-BORDER",
        bill_tax_id=sd.HOSPITALS["H005"]["tax_id"], items=items, claimed_amount=68400,
        payment={"mode": "Card", "receipt": "RCPT-BORDER-01", "paid": 68400, "date": dis},
        preauth_amount=50000, doc_types=("medical_bill", "prescription"),
        complaints="Cough with fever for 4 days and breathlessness.",
        findings="Right lower zone crepitations. Chest X-ray: consolidation.",
        rx=[("Tab. Azithromycin 500 mg", "1 tablet", "Once daily", "5 days"),
            ("Tab. Paracetamol 650 mg", "1 tablet", "Three times daily if fever", "5 days")],
        meta={"/Producer": "GVMC Hospital Information System v2.1", "/Creator": "GVMC HIS Billing",
              "/CreationDate": _pdfdate(dis), "/ModDate": _pdfdate(dis)})
    return _finish(case)


# ---------------------------------------------------------------- one-click demo scenarios
# Each scenario starts from a claim that passes every check and changes one thing, so a single agent reacts
# (except "suspicious", which combines many). The comments give the intended rule score of that agent
# (points: low/medium/high = 6/15/27 for a potential anomaly, 10/25/45 for a confirmed rule violation).
# Everything except "docs_edited" is visible on the generated PDFs. Demo submissions are kept out of the
# claim history (channel "demo"), so clicking a scenario again gives the same result.
SCENARIO_KINDS = (
    "small_claim",
    "bill_overclaim", "bill_duplicate", "bill_unpaid",
    "docs_mismatch", "docs_edited",
    "medical_mismatch", "medical_lab_altered",
    "provider_mismatch",
    "history_flags",
)


def _clean_fever(today: date) -> dict:
    """Viral fever at Lakeview (H004) with Dr. Priya Nair (General Medicine): passes every check."""
    uid = uuid.uuid4().hex[:6].upper()
    adm = today - timedelta(days=10)
    dis = adm + timedelta(days=2)
    items = [("Room charges - general ward (2 days x 2,500)", 2, 2500), ("Physician consultation and monitoring", 1, 4200),
             ("Laboratory (CBC, dengue NS1, malaria antigen)", 1, 2850), ("Pharmacy - inpatient medicines", 1, 1180)]
    case = {
        "policy_number": "POL-1001", "hospital_id": "H004", "doctor_id": "D004", "disease_id": "viral_fever",
        "admission": adm, "discharge": dis, "bill_date": dis, "rx_date": dis,
        "invoice_number": f"INV-{uid}", "bill_tax_id": sd.HOSPITALS["H004"]["tax_id"], "items": items,
        "complaints": "High fever with body ache for 3 days.",
        "findings": "Temperature 101.8 F. No localising signs. Dengue NS1 and malaria antigen negative.",
        "labs": [("Haemoglobin", "13.9 g/dL", "13.0 - 17.0"), ("WBC count", "5,600 /uL", "4,000 - 11,000"),
                 ("Platelet count", "2,10,000 /uL", "1,50,000 - 4,50,000")],
        "procedure": "None.",
        "course": "Treated with oral fluids and antipyretics. Afebrile from day 2.",
        "condition": "Stable, afebrile.",
        "rx": [("Tab. Paracetamol 650 mg", "1 tablet", "Three times daily if fever", "3 days"),
               ("ORS sachets", "1 sachet in 1 L water", "Through the day", "3 days"),
               ("Tab. Pantoprazole 40 mg", "1 tablet", "Once daily before breakfast", "3 days")],
        "advice": "Plenty of oral fluids and rest. Review if fever returns.",
        "meta": {"/Producer": "LMH Hospital Information System v3.0", "/Creator": "LMH HIS",
                 "/CreationDate": _pdfdate(dis), "/ModDate": _pdfdate(dis)},
    }
    total = sum(q * r for _, q, r in items)
    case["claimed_amount"] = total
    case["payment"] = {"mode": "UPI", "receipt": f"RCPT-{uid}", "paid": total, "date": dis}
    return case


def _small_fever(today: date) -> dict:
    """Same-day day-care visit for viral fever, 1,830 in total: low risk and below the auto-approval limit (2,000)."""
    case = _clean_fever(today)
    day = today - timedelta(days=6)
    items = [("Day-care consultation (General Medicine)", 1, 600), ("Laboratory (CBC, dengue NS1)", 1, 750),
             ("Pharmacy - medicines dispensed", 1, 480)]
    total = sum(q * r for _, q, r in items)
    case.update(
        admission=day, discharge=day, bill_date=day, rx_date=day, items=items, claimed_amount=total,
        findings="Temperature 100.6 F. No localising signs. Dengue NS1 negative.",
        labs=[("Haemoglobin", "14.2 g/dL", "13.0 - 17.0"), ("WBC count", "6,100 /uL", "4,000 - 11,000"),
              ("Platelet count", "2,40,000 /uL", "1,50,000 - 4,50,000")],
        course="Seen in day care. Treated with oral fluids and antipyretics and sent home the same day.",
        condition="Stable.",
        rx=[("Tab. Paracetamol 650 mg", "1 tablet", "Three times daily if fever", "3 days"),
            ("ORS sachets", "1 sachet in 1 L water", "Through the day", "3 days")],
        meta={**case["meta"], "/CreationDate": _pdfdate(day), "/ModDate": _pdfdate(day)},
        payment={**case["payment"], "paid": total, "date": day})
    return case


def _scenario(kind: str, today: date) -> dict:
    if kind == "small_claim":
        # Every agent passes and the claim is below the auto-approval limit, so it is auto-approved.
        return _finish(_small_fever(today))
    if kind.startswith("medical_"):
        case = _clean_fever(today)
    else:
        case = build_case("clean", today)  # appendicitis at City General, 41,850, every check passes
        case.pop("icd", None)

    if kind == "bill_overclaim":
        # Bill agent ~72: claimed 48,500 against a bill of 41,850 (CLAIM_VS_INVOICE_MISMATCH, confirmed high 45)
        # and more than the 41,850 the receipt shows as paid (CLAIM_EXCEEDS_AMOUNT_PAID, high 27).
        case["claimed_amount"] = 48500
    elif kind == "bill_duplicate":
        # Bill agent ~45: bill number INV-1001 was already claimed at City General (claim C-100).
        case["invoice_number"] = "INV-1001"
    elif kind == "bill_unpaid":
        # Bill agent ~42: the bill shows 30,000 paid and 11,850 still due (BILL_PAYMENT_PENDING 15), yet the
        # full 41,850 is claimed (CLAIM_EXCEEDS_AMOUNT_PAID 27).
        case["payment"] = {**case["payment"], "paid": 30000}
    elif kind == "docs_mismatch":
        # Document agent ~30: the discharge summary names another patient (DOC_PATIENT_MISMATCH 15) and a
        # discharge date 2 days later than the claim and the bill (DOC_DATES_MISMATCH 15).
        case["report_patient"] = "S. Verma"
        case["report_discharge"] = case["discharge"] + timedelta(days=2)
    elif kind == "docs_edited":
        # Document agent ~60: all four PDFs were saved by Adobe Photoshop (EDITING_SOFTWARE 15 each). Visible only
        # in the files' properties (Producer / Creator), not on the page.
        case["meta"] = {**case["meta"], "/Producer": "Adobe Photoshop 25.0", "/Creator": "Adobe Photoshop 25.0"}
    elif kind == "medical_mismatch":
        # Medical agent ~30: an antibiotic prescribed for a viral fever (MEDICINE_NOT_INDICATED 15) and an ICU day
        # on the bill and in the discharge summary (TREATMENT_NOT_TYPICAL 15).
        case["rx"] = case["rx"] + [("Tab. Azithromycin 500 mg", "1 tablet", "Once daily", "5 days")]
        case["items"] = case["items"] + [("ICU observation (1 day)", 1, 6500)]
        case["course"] = "Moved to the ICU for observation on day 1. Treated with oral fluids and antipyretics. Afebrile from day 2."
        total = sum(q * r for _, q, r in case["items"])
        case["claimed_amount"] = total
        case["payment"] = {**case["payment"], "paid": total}
    elif kind == "medical_lab_altered":
        # Medical agent ~42: the lab issued a platelet count of 2,10,000 but the uploaded copy shows 85,000, so the
        # lab's verification code no longer matches (LAB_REPORT_TAMPERED 27); the discharge summary codes the viral
        # fever as dengue, ICD-10 A97.0 (ICD_DIAGNOSIS_MISMATCH 15).
        case["labs_signed"] = list(case["labs"])
        case["labs"] = case["labs"][:2] + [("Platelet count", "85,000 /uL", "1,50,000 - 4,50,000")]
        case["icd"] = "A97.0"
    elif kind == "provider_mismatch":
        # Hospital and doctor agent ~60: the bill carries Lakeview's GSTIN instead of City General's
        # (TAX_ID_MISMATCH, confirmed high 45) and the appendectomy is under Dr. Vikram Shah, an orthopaedic
        # surgeon (DOCTOR_SPECIALTY_MISMATCH 15).
        case["bill_tax_id"] = sd.HOSPITALS["H004"]["tax_id"]
        case["doctor_id"] = "D005"
    elif kind == "history_flags":
        # Policyholder agent ~42: R. Singh (POL-2002) had a claim denied by an investigator (PRIOR_FRAUD_DECISION 27)
        # and made 3 claims in the last 90 days (CLAIM_FREQUENCY 15). The claim and documents themselves are clean.
        case["policy_number"] = "POL-2002"
    return _finish(case)


def form_payload(case: dict) -> dict:
    """The customer-journey form values for a case."""
    return {
        "policy_number": case["policy_number"], "date_of_birth": case["policy"]["date_of_birth"],
        "hospital_id": case["hospital_id"], "doctor_id": case["doctor_id"], "disease_id": case["disease_id"],
        "admission_date": case["admission"].isoformat(), "discharge_date": case["discharge"].isoformat(),
        "claimed_amount": case["claimed_amount"],
        "invoice": {"invoice_number": case["invoice_number"], "invoice_date": case["bill_date"].isoformat(),
                    "line_items": [{"description": d, "amount": q * r} for d, q, r in case["items"]],
                    "total": case["bill_total"], "tax_id": case["bill_tax_id"]},
    }


def claim_json(case: dict, claim_id: str) -> dict:
    """Full Claim model JSON (for the direct /api/assess endpoint and scripts)."""
    f = form_payload(case)
    return {"claim_id": claim_id, "claimant_id": case["policy"]["claimant_id"],
            "claimant_name": case["policy"]["holder_name"], "hospital_id": f["hospital_id"],
            "doctor_id": f["doctor_id"], "diagnosis": case["disease"]["name"],
            "admission_date": f["admission_date"], "discharge_date": f["discharge_date"],
            "claimed_amount": f["claimed_amount"], "invoice": {k: v for k, v in f["invoice"].items() if v is not None},
            "policy_number": f["policy_number"], "disease_id": f["disease_id"]}


# ---------------------------------------------------------------- rendering helpers

def _fmt(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def _money(v: float) -> str:
    return f"{v:,.2f}"


def _watermark(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 42)
    canvas.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.12))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, "SAMPLE - TEST DATA ONLY")
    canvas.restoreState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawString(15 * mm, 10 * mm, "Fictional document generated for fraud-detection testing. Not a real medical record.")


def _header(c, title):
    h = c["hospital"]
    tax = f" | GSTIN: {c['bill_tax_id']}" if c["bill_tax_id"] else ""
    return [Paragraph(h["name"], H1),
            Paragraph(f"{h['address']} | Tel: {h['phone']}{tax}", SUB),
            Spacer(1, 6),
            Table([[Paragraph(f"<b>{title}</b>", ParagraphStyle("t", parent=N, fontSize=12, alignment=1, textColor=colors.white))]],
                  colWidths=[180 * mm], style=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1e3a5f")),
                                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]),
            Spacer(1, 8)]


def _kv(rows):
    data = [[Paragraph(f"<b>{a}</b>", N), Paragraph(str(b), N), Paragraph(f"<b>{c_}</b>", N), Paragraph(str(d), N)]
            for a, b, c_, d in rows]
    return Table(data, colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm],
                 style=[("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f1f5f9")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP")])


def _grid(data, widths, right_cols=()):
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    style += [("ALIGN", (col, 0), (col, -1), "RIGHT") for col in right_cols]
    return Table(data, colWidths=widths, style=style, repeatRows=1)


def _sign(name, line2):
    return [Spacer(1, 24), Table([["", Paragraph(f"______________________<br/><b>{name}</b><br/>{line2}", N)]],
                                 colWidths=[110 * mm, 70 * mm])]


def _patient(c):
    return c["policy"]["holder_name"]


# Time of day (HHMMSS) each document type is saved by the hospital system on the document date.
_SAVED_AT = {"Medical Bill": "091500", "Prescription": "084010", "Medical Report": "085530", "Lab Report": "071245"}


def _build(story, meta: dict, title: str) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=18 * mm).build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    # Rewrite metadata so the document_scan agent sees the intended producer and dates.
    reader = PdfReader(io.BytesIO(buf.getvalue()))
    w = PdfWriter()
    for p in reader.pages:
        w.add_page(p)
    meta = dict(meta)
    if meta.get("/CreationDate") and meta.get("/CreationDate") == meta.get("/ModDate") and title in _SAVED_AT:
        # An untouched system file: each document is saved at its own time of day, as a hospital system would.
        stamp = str(meta["/CreationDate"])[:10] + _SAVED_AT[title]
        meta["/CreationDate"] = meta["/ModDate"] = stamp
    w.add_metadata({**meta, "/Title": title, "/Nonce": uuid.uuid4().hex})  # nonce: unique hash per render
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


# ---------------------------------------------------------------- documents

def medical_bill(c) -> bytes:
    rows = [["#", "Description", "Qty", "Rate", "Amount"]]
    rows += [[str(i), Paragraph(d, N), str(q), _money(r), _money(q * r)] for i, (d, q, r) in enumerate(c["items"], 1)]
    rows += [["", Paragraph("<b>Total</b>", N), "", "", _money(c["bill_total"])]]
    story = _header(c, "INPATIENT FINAL BILL")
    story += [_kv([
        ("Bill No.", c["invoice_number"], "Bill Date", _fmt(c["bill_date"])),
        ("Patient", _patient(c), "Policy No.", c["policy_number"]),
        ("Admitted", _fmt(c["admission"]), "Discharged", _fmt(c["discharge"])),
        ("Consultant", c["doctor"]["name"], "Department", c["doctor"]["specialty"]),
        ("Diagnosis", c["disease"]["name"], "Hospital ID", c["hospital_id"]),
    ]), Spacer(1, 10), _grid(rows, [10 * mm, 100 * mm, 15 * mm, 27 * mm, 28 * mm], right_cols=(2, 3, 4)),
        Spacer(1, 6), Paragraph(f"<b>Amount payable: INR {_money(c['bill_total'])}</b>", N)]
    pay = c.get("payment") or {}
    paid = pay.get("paid", c["bill_total"])
    story += [Spacer(1, 4), _kv([
        ("Payment mode", pay.get("mode", "UPI"), "Receipt No.", pay.get("receipt") or "-"),
        ("Amount paid", f"INR {_money(paid)}", "Balance due", f"INR {_money(c['bill_total'] - paid)}"),
        ("Paid on", _fmt(pay["date"]) if pay.get("date") else "-", "Status", "Paid in full" if paid >= c["bill_total"] else "Payment pending"),
    ])]
    story += _sign("Authorised signatory", c["hospital"]["name"])
    data = _build(story, c["meta"], "Medical Bill")
    if c.get("incremental_edit"):
        data = _incremental_edit(data, c["incremental_edit"])
    return data


def _incremental_edit(data: bytes, mod_date: str) -> bytes:
    """Append a second revision (as an editor does when a saved PDF is changed and saved again)."""
    w = PdfWriter(io.BytesIO(data), incremental=True)
    w.add_metadata({"/ModDate": mod_date})
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def prescription(c) -> bytes:
    d = c["doctor"]
    rows = [["Medicine", "Dose", "Frequency", "Duration"]]
    rows += [[Paragraph(m, N), ds, Paragraph(f, N), du] for m, ds, f, du in c["rx"]]
    story = _header(c, "PRESCRIPTION")
    story += [Paragraph(f"<b>{d['name']}</b>, {d['qualification']} | Reg. No: {d['registration_no'] or '(not stated)'} | "
                        f"Dept: {d['specialty']}", N), Spacer(1, 6),
              _kv([("Patient", _patient(c), "Date", _fmt(c["rx_date"])),
                   ("Policy No.", c["policy_number"], "Diagnosis", c["disease"]["name"])]),
              Spacer(1, 10), Paragraph("<font size=18><b>Rx</b></font>", N), Spacer(1, 4),
              _grid(rows, [70 * mm, 25 * mm, 55 * mm, 30 * mm]),
              Paragraph("Advice", H2), Paragraph(c["advice"], N)]
    story += _sign(d["name"], d["qualification"])
    return _build(story, c["meta"], "Prescription")


def medical_report(c) -> bytes:
    d = c["doctor"]
    labs = [["Test", "Result", "Reference range"]] + [list(x) for x in c["labs"]]
    story = _header(c, "DISCHARGE SUMMARY / MEDICAL REPORT")
    # report_patient / report_discharge: what this document prints when a scenario makes it disagree with the claim
    story += [_kv([
        ("Patient", c.get("report_patient") or _patient(c), "Policy No.", c["policy_number"]),
        ("Admitted", _fmt(c["admission"]), "Discharged", _fmt(c.get("report_discharge") or c["discharge"])),
        ("Consultant", f"{d['name']} ({d['registration_no'] or 'reg. not stated'})", "Department", d["specialty"]),
    ])]
    final = f"{c['disease']['name']} (ICD-10: {c['icd']})" if c.get("icd") else c["disease"]["name"]
    for title, text in [("Final diagnosis", final), ("Presenting complaints", c["complaints"]),
                        ("Clinical findings", c["findings"])]:
        story += [Paragraph(title, H2), Paragraph(text, N)]
    story += [Paragraph("Investigations", H2), _grid(labs, [70 * mm, 50 * mm, 60 * mm])]
    for title, text in [("Procedure", c["procedure"]), ("Hospital course", c["course"]),
                        ("Condition at discharge", c["condition"]),
                        ("Discharge medication and advice", "; ".join(r[0] for r in c["rx"]) + ". " + c["advice"])]:
        story += [Paragraph(title, H2), Paragraph(text, N)]
    story += _sign(d["name"], d["qualification"])
    return _build(story, c["meta"], "Medical Report")


def lab_report(c) -> bytes:
    """Report from the hospital's laboratory. No GSTIN (the lab bills separately); names the referring hospital."""
    lab = sd.LABS[c["lab_number"].split("-", 1)[0]]
    labs = [["Test", "Result", "Reference range"]] + [list(x) for x in c["labs"]]
    story = [Paragraph(lab["name"], H1),
             Paragraph(f"{lab['city']} | NABL accredited (simulated) | Referred by: {c['hospital']['name']}", SUB),
             Spacer(1, 6),
             Table([[Paragraph("<b>LABORATORY REPORT</b>", ParagraphStyle("t", parent=N, fontSize=12, alignment=1, textColor=colors.white))]],
                   colWidths=[180 * mm], style=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#14532d")),
                                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]),
             Spacer(1, 8),
             _kv([("Lab report No.", c["lab_number"], "Sample date", _fmt(c["admission"])),
                  ("Patient", _patient(c), "Policy No.", c["policy_number"]),
                  ("Referred by", c["doctor"]["name"], "Hospital", c["hospital"]["name"])]),
             Spacer(1, 10), _grid(labs, [70 * mm, 50 * mm, 60 * mm]), Spacer(1, 10),
             Paragraph(f"Verification code: {c['lab_code']}", N),
             Paragraph("Verify this report on the laboratory portal with the report number (SIMULATED).", SMALL)]
    story += _sign("Pathologist", lab["name"])
    return _build(story, c["meta"], "Lab Report")


RENDERERS = {"medical_bill": medical_bill, "prescription": prescription, "medical_report": medical_report,
             "lab_report": lab_report}


def render(case: dict, doc_type: str) -> bytes:
    return RENDERERS[doc_type](case)
