"""Characterisation smoke tests for the current API (health, policy lookup, claim submit, status)."""
import json
import time

LOOKUP = {"policy_number": "pol-1001", "date_of_birth": "1992-04-18"}


def _submission() -> dict:
    return {
        "policy_number": "POL-1001", "date_of_birth": "1992-04-18", "hospital_id": "H001", "doctor_id": "D001",
        "disease_id": "appendicitis", "admission_date": "2026-03-01", "discharge_date": "2026-03-05",
        "claimed_amount": 45000,
        "invoice": {"invoice_number": "INV-SMOKE-1", "invoice_date": "2026-03-05", "total": 45000,
                    "tax_id": "27AAACC1111A1ZQ",
                    "line_items": [{"description": "Room", "amount": 15000}, {"description": "Surgery", "amount": 30000}]},
    }


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_policy_lookup_ok(client):
    r = client.post("/api/policies/lookup", json=LOOKUP)
    assert r.status_code == 200
    body = r.json()
    assert body["policy_number"] == "POL-1001"
    assert body["holder_name"] == "A. Kumar"
    assert {h["id"] for h in body["network_hospitals"]} == {"H001", "H004", "H005"}
    assert body["covered_diseases"] and body["not_covered"]


def test_policy_lookup_wrong_dob(client):
    r = client.post("/api/policies/lookup", json={**LOOKUP, "date_of_birth": "1990-01-01"})
    assert r.status_code == 404


def test_claim_submit_and_status(client):
    r = client.post("/api/claims", data={"payload": json.dumps(_submission()), "document_types": '["medical_bill"]'},
                    files=[("documents", ("bill.txt", b"Hospital bill INV-SMOKE-1", "text/plain"))])
    assert r.status_code == 202, r.text
    claim_id = r.json()["claim_id"]
    assert claim_id.startswith("CLM-")

    status = None
    for _ in range(100):
        status = client.get(f"/api/claims/{claim_id}/status").json()
        if status["status"] != "processing":
            break
        time.sleep(0.1)
    assert status["status"] in ("completed", "failed")
    assert status["claim_id"] == claim_id
    assert [s["key"] for s in status["stages"]][0] == "intake"
    assert not any("_profile" in s["key"] or "_scan" in s["key"] or "_check" in s["key"] for s in status["stages"])
    if status["status"] == "completed":
        assert status["report"]["outcome"]["code"] in ("approved", "under_review", "verification")


def test_claim_without_documents_rejected(client):
    r = client.post("/api/claims", data={"payload": json.dumps(_submission())})
    assert r.status_code == 422


def test_status_unknown_claim(client):
    assert client.get("/api/claims/CLM-NOPE/status").status_code == 404
