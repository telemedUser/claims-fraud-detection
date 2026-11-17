"""Generates fictional test documents (medical bill, prescription, medical report) for demo cases.

Every page carries a "SAMPLE - TEST DATA ONLY" watermark. All people, hospitals and IDs are fictional
and come from the seeded data in app/data/store.py. Dates are relative to `today` so cases always fall
inside the demo policies' validity windows.
"""
import io
import uuid
from datetime import date, timedelta

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from app.data import store

DOC_TYPES = ("medical_bill", "prescription", "medical_report")

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
            "invoice_number": f"INV-{uid}", "bill_tax_id": store.hospital("H001")["tax_id"],
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
            "advice": "Avoid lifting heavy weights for 4 weeks. Keep wound dry. Review in OPD after 7 days for suture removal.",
            # produced by the hospital billing system on the bill date
            "meta": {"/Producer": "CGH Hospital Information System v4.2", "/Creator": "CGH HIS Billing",
                     "/CreationDate": _pdfdate(dis), "/ModDate": _pdfdate(dis)},
        }
        case["claimed_amount"] = sum(q * r for _, q, r in case["items"])
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
                     ("CRP", "3 mg/L", "< 5")],
            "procedure": "None.",
            "course": "Observed overnight. Fever settled with paracetamol.",
            "condition": "Stable.",
            "rx": [("Tab. Paracetamol 500 mg", "1 tablet", "Three times daily if fever", "3 days")],
            "advice": "Oral fluids. Review if fever persists.",
            # edited in Photoshop, created long before admission, modified after discharge
            "meta": {"/Producer": "Adobe Photoshop 25.0", "/Creator": "Adobe Photoshop 25.0",
                     "/CreationDate": _pdfdate(today - timedelta(days=320), "100000"),
                     "/ModDate": _pdfdate(today - timedelta(days=6), "223000")},
        }
    else:
        raise ValueError(f"unknown case {kind}")

    pol = store.policy(case["policy_number"])
    case["policy"] = pol
    case["hospital"] = store.hospital(case["hospital_id"])
    case["doctor"] = store.doctor(case["doctor_id"])
    case["disease"] = store.disease(case["disease_id"])
    case["bill_total"] = sum(q * r for _, q, r in case["items"])
    return case


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


def _build(story, meta: dict, title: str) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=18 * mm).build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    # Rewrite metadata so the document_scan agent sees the intended producer and dates.
    reader = PdfReader(io.BytesIO(buf.getvalue()))
    w = PdfWriter()
    for p in reader.pages:
        w.add_page(p)
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
        Spacer(1, 6), Paragraph(f"<b>Amount payable: INR {_money(c['bill_total'])}</b>", N),
        Paragraph("Payment mode: Cashless / Insurance claim", SMALL)]
    story += _sign("Authorised signatory", c["hospital"]["name"])
    return _build(story, c["meta"], "Medical Bill")


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
    story += [_kv([
        ("Patient", _patient(c), "Policy No.", c["policy_number"]),
        ("Admitted", _fmt(c["admission"]), "Discharged", _fmt(c["discharge"])),
        ("Consultant", f"{d['name']} ({d['registration_no'] or 'reg. not stated'})", "Department", d["specialty"]),
    ])]
    for title, text in [("Final diagnosis", c["disease"]["name"]), ("Presenting complaints", c["complaints"]),
                        ("Clinical findings", c["findings"])]:
        story += [Paragraph(title, H2), Paragraph(text, N)]
    story += [Paragraph("Investigations", H2), _grid(labs, [70 * mm, 50 * mm, 60 * mm])]
    for title, text in [("Procedure", c["procedure"]), ("Hospital course", c["course"]),
                        ("Condition at discharge", c["condition"]),
                        ("Discharge medication and advice", "; ".join(r[0] for r in c["rx"]) + ". " + c["advice"])]:
        story += [Paragraph(title, H2), Paragraph(text, N)]
    story += _sign(d["name"], d["qualification"])
    return _build(story, c["meta"], "Medical Report")


RENDERERS = {"medical_bill": medical_bill, "prescription": prescription, "medical_report": medical_report}


def render(case: dict, doc_type: str) -> bytes:
    return RENDERERS[doc_type](case)
