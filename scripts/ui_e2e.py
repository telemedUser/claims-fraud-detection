"""Browser end-to-end test of the customer journey and internal console (uses installed Microsoft Edge).
Usage: python scripts/ui_e2e.py            (server must be running on :8000)
Screenshots are written to ui_screens/.
"""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import load_env  # noqa: E402

load_env()
BASE = "http://127.0.0.1:8000"
OUT = ROOT / "ui_screens"
OUT.mkdir(exist_ok=True)
DOCS = ROOT / "test_documents" / "clean"
claim = json.loads((DOCS / "claim.json").read_text(encoding="utf-8"))


def shot(page, name, full=True):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("  screenshot", name)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))

    # ---------------- manual journey (genuine claim, typed by hand)
    print("journey: manual genuine claim")
    page.goto(BASE + "/")
    page.fill("#policy", "POL-1001")
    page.fill("#dob", "1992-04-18")
    page.get_by_role("button", name="Find policy").click()
    expect(page.get_by_text("Policy verified")).to_be_visible()
    shot(page, "01_policy")
    page.get_by_role("button", name="Continue").click()

    expect(page.get_by_role("radio", name=re.compile("City General Hospital"))).to_be_visible()
    hospitals = page.get_by_role("radiogroup", name="Network hospital").get_by_role("radio").count()
    print("  network hospitals shown:", hospitals)
    page.get_by_role("radio", name=re.compile("City General Hospital")).click()
    page.get_by_role("radio", name=re.compile("Dr. Asha Rao")).click()
    page.get_by_role("radio", name=re.compile("Acute appendicitis")).click()
    page.get_by_role("button", name=re.compile("Not covered by your plan")).click()
    page.fill("#adm", claim["admission_date"])
    page.fill("#dis", claim["discharge_date"])
    shot(page, "02_treatment")
    page.get_by_role("button", name="Continue").click()

    page.fill("#inv", claim["invoice"]["invoice_number"])
    page.fill("#billdate", claim["invoice"]["invoice_date"])
    page.fill("#gstin", claim["invoice"]["tax_id"])
    for i, li in enumerate(claim["invoice"]["line_items"], 1):
        if i > 1:
            page.get_by_role("button", name="Add item").click()
        page.get_by_label(f"Item {i} description").fill(li["description"])
        page.get_by_label(f"Item {i} amount").fill(str(li["amount"]))
    print("  claimed amount auto-filled:", page.input_value("#claimed"))
    shot(page, "03_bill")
    page.get_by_role("button", name="Continue").click()

    # validation: continue without required docs
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("The itemised hospital bill is required.")).to_be_visible()
    page.get_by_label("Final hospital bill", exact=True).set_input_files(str(DOCS / "medical_bill.pdf"))
    page.get_by_label("Medical report / discharge summary", exact=True).set_input_files(str(DOCS / "medical_report.pdf"))
    page.get_by_label("Prescription", exact=True).set_input_files(str(DOCS / "prescription.pdf"))
    shot(page, "04_documents")
    page.get_by_role("button", name="Continue").click()

    page.get_by_role("checkbox").check()
    shot(page, "05_review")
    page.get_by_role("button", name="Submit claim").click()
    page.wait_for_url(re.compile(r"/claims/CLM-[A-F0-9]+/processing"))
    page.wait_for_timeout(1200)
    shot(page, "06_processing", full=False)
    page.wait_for_url(re.compile(r"/claims/CLM-[A-F0-9]+$"), timeout=180_000)
    expect(page.get_by_text("Verification checks")).to_be_visible()
    page.wait_for_timeout(800)
    print("  outcome:", page.locator("h1").first.inner_text())
    shot(page, "07_report_genuine")

    # ---------------- demo-mode suspicious claim
    print("journey: demo suspicious claim")
    page.goto(BASE + "/?demo=1")
    page.get_by_role("button", name="Suspicious claim").click()
    expect(page.get_by_text("Review and submit")).to_be_visible(timeout=20_000)
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="Submit claim").click()
    page.wait_for_url(re.compile(r"/claims/CLM-[A-F0-9]+$"), timeout=180_000)
    expect(page.get_by_text("Verification checks")).to_be_visible()
    page.wait_for_timeout(800)
    print("  outcome:", page.locator("h1").first.inner_text())
    shot(page, "08_report_suspicious")

    # ---------------- internal console
    print("internal console")
    page.goto(BASE + "/internal")
    page.get_by_label("Internal key").fill("wrong-key")
    page.get_by_role("button", name="Unlock console").click()
    expect(page.get_by_text("Invalid internal key")).to_be_visible()
    page.get_by_label("Internal key").fill(os.environ["INTERNAL_API_KEY"])
    page.get_by_role("button", name="Unlock console").click()
    expect(page.get_by_text("End-to-end claim workflow")).to_be_visible()
    page.wait_for_timeout(1500)
    shot(page, "09_internal_workflow")
    page.get_by_role("button", name="Agents").click()
    page.wait_for_timeout(500)
    shot(page, "10_internal_agents")
    page.get_by_role("button", name=re.compile(r"Claims \(")).click()
    page.wait_for_timeout(500)
    shot(page, "11_internal_claims")
    page.locator("tbody tr").first.click()
    expect(page.get_by_text("Agent responses")).to_be_visible()
    page.wait_for_timeout(1200)
    shot(page, "12_internal_claim_detail")

    print("console errors:", errors or "none")
    browser.close()
