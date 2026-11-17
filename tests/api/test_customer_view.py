"""Customer view wording and intake rules (task 13.4; Requirements 8.2 to 8.6)."""
import json
import re
import time

import pytest
from sqlalchemy import select

from app import jobs
from app.api import customer_view as cv
from app.db import models as m
from app.db.session import get_session

FORBIDDEN_WORDS = re.compile(r"verified|genuine|authentic|score|band|risk|fraud|anomal|finding", re.I)
AGENT_NAMES = ("provider_profile", "claimant_profile", "document_scan", "invoice_check")


def _submission(**over) -> dict:
    body = {
        "policy_number": "POL-1001", "date_of_birth": "1992-04-18", "hospital_id": "H001", "doctor_id": "D001",
        "disease_id": "appendicitis", "admission_date": "2026-03-01", "discharge_date": "2026-03-05",
        "claimed_amount": 45000,
        "invoice": {"invoice_number": "INV-CV-1", "invoice_date": "2026-03-05", "total": 45000,
                    "tax_id": "27AAACC1111A1ZQ",
                    "line_items": [{"description": "Room", "amount": 15000}, {"description": "Surgery", "amount": 30000}]},
    }
    body.update(over)
    return body


def _post(client, body, **form):
    return client.post("/api/claims", data={"payload": json.dumps(body), "document_types": '["medical_bill"]', **form},
                       files=[("documents", ("bill.txt", b"Hospital bill INV-CV-1", "text/plain"))])


def test_static_wording_has_no_forbidden_text():
    text = json.dumps([cv.OUTCOMES, list(cv.CUSTOMER_LABELS.values()), list(cv.CUSTOMER_CHECKS.values()),
                       cv.FAILED_MESSAGE])
    assert not FORBIDDEN_WORDS.search(text), FORBIDDEN_WORDS.search(text)
    assert not any(a in text for a in AGENT_NAMES)
    for o in cv.OUTCOMES.values():
        # "code" is an opaque identifier the frontend switches on; only the displayed text is checked
        assert "approved" not in json.dumps([o["title"], o["message"], o["next_steps"]]).lower()


def test_check_outcome_labels():
    assert {cv.check_outcome(a, s) for a in AGENT_NAMES for s in (0, 29, 30, 99)} <= {"no_issues", "unavailable", "simulated"}
    assert cv.check_outcome("provider_profile", 0) == "simulated"
    assert cv.check_outcome("invoice_check", 29.9) == "no_issues"
    assert cv.check_outcome("invoice_check", 30) == "unavailable"


def test_jobs_reexports_customer_view():
    assert jobs.customer_view is cv.customer_view and jobs.OUTCOMES is cv.OUTCOMES


def test_status_response_discloses_nothing_internal(client):
    r = _post(client, _submission())
    assert r.status_code == 202, r.text
    cid = r.json()["claim_id"]
    status = {}
    for _ in range(100):
        status = client.get(f"/api/claims/{cid}/status").json()
        if status["status"] != "processing":
            break
        time.sleep(0.1)
    text = json.dumps(status)
    assert not any(a in text for a in AGENT_NAMES)
    assert not FORBIDDEN_WORDS.search(text.replace(status["claim"]["claim_id"] if "claim" in status else "", ""))
    if status["status"] == "completed":
        report = status["report"]
        assert {c["outcome"] for c in report["checks"]} <= {"no_issues", "unavailable", "simulated"}
        assert not {"score", "risk_score", "findings", "decision", "recommended_queue"} & set(report)


@pytest.mark.parametrize("flag", ["true", "false"])
def test_client_analysis_flags_are_ignored(client, monkeypatch, flag):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(jobs, "_process", _noop)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")
    r = _post(client, _submission(), use_llm=flag)
    assert r.status_code == 202
    assert jobs.JOBS[r.json()["claim_id"]]["use_llm"] is False  # server config: no LLM key


@pytest.mark.parametrize("over,rule,text", [
    ({"hospital_id": "H002"}, "HOSPITAL_NOT_IN_NETWORK", "network"),
    ({"disease_id": "cosmetic"}, "CONDITION_NOT_COVERED", "not covered"),
    ({"admission_date": "2024-01-01", "discharge_date": "2024-01-05"}, "ADMISSION_OUTSIDE_POLICY_PERIOD", "policy period"),
    ({"claimed_amount": 600000}, "AMOUNT_EXCEEDS_SUM_INSURED", "sum insured"),
])
def test_eligibility_violation_returns_422_and_stores_claim_with_finding(client, over, rule, text):
    with get_session() as s:
        before = s.query(m.Claim).count()
    r = _post(client, _submission(**over))
    assert r.status_code == 422, r.text
    assert text in json.dumps(r.json())
    with get_session() as s:
        assert s.query(m.Claim).count() == before + 1
        claim = s.scalars(select(m.Claim).where(m.Claim.status == "POLICY_VIOLATION")).one()
        assert claim.channel == "customer"
        run = s.scalars(select(m.ProcessingRun).where(m.ProcessingRun.claim_id == claim.id)).one()
        assert run.status == "INTAKE_REJECTED"
        f = s.scalars(select(m.FindingRow).where(m.FindingRow.claim_id == claim.id)).one()
        assert (f.agent, f.status, f.run_id) == ("Policy_Eligibility", "CONFIRMED_RULE_VIOLATION", run.id)
        assert rule in f.explanation
    assert claim.claim_ref not in jobs.JOBS  # nothing is processed


def test_rejected_claim_is_not_a_prior_submission(client):
    assert _post(client, _submission(hospital_id="H002")).status_code == 422
    from app.db.repos import open_repos
    with open_repos() as repos:
        assert not repos.invoice_seen("H002", "INV-CV-1")
        assert repos.history("U001") == [] or all(h["invoice_number"] != "INV-CV-1" for h in repos.history("U001"))


def test_malformed_data_is_422_and_not_stored(client):
    r = _post(client, _submission(discharge_date="2026-02-01"))
    assert r.status_code == 422
    with get_session() as s:
        assert s.query(m.Claim).filter(m.Claim.status == "POLICY_VIOLATION").count() == 0
