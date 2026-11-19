"""Writes the demo scenarios as files for manual entry: one folder per scenario under "test scenario data/".

Usage:  python scripts/generate_test_scenarios.py
Output: test scenario data/<NN Scenario title>/  with the four PDFs and claim_form.txt (every value to type into
        the customer journey, step by step, and which file to upload where).

Each folder holds the same case the one-click buttons on /?demo=1 generate. The PDFs are signed for this server
(app/core/demo_mark.py, using JWT_SECRET from .env), so a claim submitted by hand with them is a demo claim: it
appears in the console as usual but never becomes history for later claims, and every scenario can be submitted
again with the same result. Dates are relative to the day you run this; re-run it before a demo if the files are
more than about two weeks old (policy POL-1001 ends on 31-Dec-2026).
"""
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import demo_mark  # noqa: E402
from app.seed import docgen  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "test scenario data"

# kind, title, agent expected to react, its rule score, what to look for (matches the demo panel on /?demo=1)
SCENARIOS = [
    ("small_claim", "Small claim auto-approved", "None (every agent passes)", 0,
     "Same-day fever visit for 1,830. Low risk and below the 2,000 auto-approval limit, so it is auto-approved."),
    ("clean", "Genuine claim", "None (every agent passes)", 0,
     "Appendectomy at City General for 41,850. Every agent passes with no findings, but only claims below 2,000 "
     "are auto-approved, so it goes to manual review."),
    ("suspicious", "Suspicious claim", "All agents", 100,
     "Many red flags at once: bill number already used, claimed 1,20,000 against a 1,00,000 bill, cashless bill "
     "with nothing paid, antibiotic for viral fever, altered lab report, files saved by Photoshop."),
    ("bill_overclaim", "Claimed more than billed", "Invoice Validation", 90,
     "The claim form says 48,500. The bill total and the amount paid on the bill are 41,850."),
    ("bill_duplicate", "Bill number already used", "Invoice Validation", 56,
     "Bill INV-1001 was already claimed at City General in January (claim C-100)."),
    ("bill_unpaid", "Bill not fully paid", "Invoice Validation", 53,
     "The bill shows 30,000 paid and 11,850 balance due (Payment pending), but the full 41,850 is claimed."),
    ("docs_mismatch", "Details differ across documents", "Document Forensics", 38,
     "The discharge summary names the patient 'S. Verma' and a discharge date 2 days later than the claim and the bill."),
    ("docs_edited", "Files saved by Photoshop", "Document Forensics", 75,
     "Not visible on the page: open the PDF properties (File > Properties) to see Producer 'Adobe Photoshop 25.0'."),
    ("medical_mismatch", "Treatment does not fit the diagnosis", "Medical Review", 30,
     "Viral fever, yet the prescription has an antibiotic (Azithromycin) and the bill and discharge summary an ICU day."),
    ("medical_lab_altered", "Lab report altered, wrong ICD code", "Medical Review", 42,
     "The lab report shows platelets 85,000 but the lab issued 2,10,000 (its verification code no longer matches); "
     "the discharge summary codes viral fever as ICD-10 A97.0 (dengue)."),
    ("provider_mismatch", "Wrong GSTIN, doctor outside specialty", "Provider Profile", 45,
     "The bill header shows Lakeview's GSTIN 27AAACL4444D1ZT instead of City General's 27AAACC1111A1ZQ, and the "
     "appendectomy is under Dr. Vikram Shah, an orthopaedic surgeon."),
    ("history_flags", "Earlier denied claim, frequent claims", "User Profile", 32,
     "R. Singh (POL-2002) had an earlier claim denied by an investigator and made 3 claims in the last 90 days. "
     "The claim and documents themselves are clean."),
]

DOC_LABEL = {"medical_bill": "Medical bill (itemised)", "medical_report": "Medical report / discharge summary",
             "prescription": "Prescription", "lab_report": "Lab report"}


def _d(x: date) -> str:
    return f"{x:%d-%b-%Y}   (date picker: {x:%m/%d/%Y})"


def _money(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def claim_form(case: dict, title: str, agent: str, score: int, look: str, today: date) -> str:
    p, h, doc, dz = case["policy"], case["hospital"], case["doctor"], case["disease"]
    items = [(d, q * r) for d, q, r in case["items"]]
    lines = [
        f"SCENARIO: {title}",
        f"Agent expected to react: {agent}",
        f"Expected score: about {score}/100 from the weighted rules (with LLM analysis on, the LLM can add up to 25 points)",
        f"What to look for: {look}",
        f"Generated on {today:%d-%b-%Y}. Dates are relative to that day.",
        "",
        "Open http://localhost:5173/ (no ?demo=1 needed) and fill in the form as below.",
        "",
        "STEP 1 - POLICY",
        f"  Policy number ............... {case['policy_number']}",
        f"  Policyholder date of birth .. {_d(date.fromisoformat(p['date_of_birth']))}",
        f"  Click 'Find policy'. It shows policyholder {p['holder_name']}, plan {p['plan']}.",
        "",
        "STEP 2 - HOSPITAL & TREATMENT",
        f"  Network hospital ............ {h['name']} ({h['city']})",
        f"  Treating doctor ............. {doc['name']} ({doc['specialty']})",
        f"  Condition treated ........... {dz['name']}",
        f"  Admission date .............. {_d(case['admission'])}",
        f"  Discharge date .............. {_d(case['discharge'])}",
        "",
        "STEP 3 - BILL DETAILS",
        f"  Bill / invoice number ....... {case['invoice_number']}",
        f"  Bill date ................... {_d(case['bill_date'])}",
        f"  Hospital GSTIN (optional) ... {case['bill_tax_id'] or '(leave empty)'}",
        "  Line items (description  ->  amount):",
        *[f"    {i}. {d}  ->  {_money(a)}" for i, (d, a) in enumerate(items, 1)],
        f"  Bill total (the form adds it up) .. {_money(case['bill_total'])}",
        f"  Amount you are claiming ........... {_money(case['claimed_amount'])}",
        "",
        "STEP 4 - DOCUMENTS (upload these files from this folder)",
        *[f"  {DOC_LABEL[t]:<36} ->  {t}.pdf" for t in docgen.DOC_TYPES],
        "",
        "STEP 5 - REVIEW & SUBMIT",
        "  Tick the declaration and submit. The claim appears in the internal console (/internal) within a few seconds.",
        "",
        "Note: these files are signed as demo data for this server, so this claim does not become history for later",
        "claims and the scenario can be submitted again with the same result. Do not change the bill number.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    if not demo_mark.signature("x"):
        sys.exit("JWT_SECRET is not set in .env, so the files cannot be signed as demo data.")
    today = date.today()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    index = ["TEST SCENARIO DATA", f"Generated on {today:%d-%b-%Y}. Re-run: python scripts/generate_test_scenarios.py", "",
             "Each folder has claim_form.txt (what to type, step by step) and the four documents to upload.", "",
             f"{'Folder':<46} {'Agent':<28} Expected score (weighted rules)"]
    for n, (kind, title, agent, score, look) in enumerate(SCENARIOS, 1):
        case = docgen.build_case(kind, today)
        folder = OUT / f"{n:02d} {title}"
        folder.mkdir()
        for t in docgen.DOC_TYPES:
            (folder / f"{t}.pdf").write_bytes(docgen.render(case, t))
        (folder / "claim_form.txt").write_text(claim_form(case, title, agent, score, look, today), encoding="utf-8")
        index.append(f"{folder.name:<46} {agent:<28} ~{score}")
        print(f"{folder.name}: bill {case['invoice_number']}, claimed {_money(case['claimed_amount'])}")
    (OUT / "README.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"Wrote {len(SCENARIOS)} scenarios to {OUT}")


if __name__ == "__main__":
    main()
