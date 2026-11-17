"""POST /api/assess is gated by role (Investigator, Fraud_Team, Administrator), applies policy checks, and writes history only in test mode."""
import hashlib
import json

import pytest

from app.db.repos import DISEASES, open_repos
from tests.db_state import db_snapshot

def _claim(**over) -> dict:
    c = {"claim_id": "CLM-ASSESS-1", "claimant_id": "U001", "claimant_name": "A. Kumar", "hospital_id": "H001",
         "doctor_id": "D001", "diagnosis": "Acute appendicitis", "admission_date": "2026-03-01",
         "discharge_date": "2026-03-05", "claimed_amount": 45000, "policy_number": "POL-1001",
         "disease_id": "appendicitis",
         "invoice": {"invoice_number": "INV-ASSESS-1", "invoice_date": "2026-03-05", "total": 45000,
                     "tax_id": "27AAACC1111A1ZQ",
                     "line_items": [{"description": "Room", "amount": 15000}, {"description": "Surgery", "amount": 30000}]}}
    c.update(over)
    return c


def _post(client, claim, headers=None, **params):
    return client.post("/api/assess", params=params, headers=headers or {},
                       data={"claim": json.dumps(claim), "use_llm": "false", "document_types": '["medical_bill"]'},
                       files=[("documents", ("bill.txt", b"Hospital bill INV-ASSESS-1", "text/plain"))])


def _snapshot():
    return db_snapshot()


def test_anonymous_rejected(client):
    assert _post(client, _claim()).status_code == 401


def test_invalid_token_rejected(client):
    assert _post(client, _claim(), headers={"Authorization": "Bearer nope"}).status_code == 401


def test_old_internal_key_header_no_longer_works(client):
    assert _post(client, _claim(), headers={"X-Internal-Key": "test-internal-key"}).status_code == 401


@pytest.mark.parametrize("role", ["Investigator", "Fraud_Team", "Administrator"])
def test_allowed_roles_do_not_write_history(client, auth_headers, role):
    before = _snapshot()
    r = _post(client, _claim(), headers=auth_headers(role))
    assert r.status_code == 200, r.text
    assert _snapshot() == before


def test_ops_manager_forbidden_and_audited(client, auth_headers):
    from sqlalchemy import select
    from app.db import models as m
    from app.db.session import get_session
    r = _post(client, _claim(), headers=auth_headers("Ops_Manager"))
    assert r.status_code == 403
    with get_session() as s:
        events = [e for e in s.scalars(select(m.AuditEvent)) if e.event_type == "access_denied"]
        assert len(events) == 1
        assert events[0].detail["permission"] == "Investigator|Fraud_Team|Administrator"
        assert events[0].entity_id == "POST /api/assess" and events[0].actor_id


@pytest.mark.parametrize("over", [
    {"hospital_id": "H002"},                      # not in network
    {"disease_id": "__uncovered__"},
    {"policy_number": "POL-NOPE"},
    {"claimed_amount": 99_000_000},
    {"admission_date": "2025-01-01", "discharge_date": "2025-01-05"},
])
def test_policy_checks_apply_outside_test_mode(client, auth_headers, over):
    if over.get("disease_id") == "__uncovered__":
        with open_repos() as repos:
            covered = set(repos.policy("POL-1001")["covered_disease_ids"])
        over = {"disease_id": next(k for k in DISEASES if k not in covered)}
    before = _snapshot()
    r = _post(client, _claim(**over), headers=auth_headers("Investigator"))
    assert r.status_code in (404, 422), r.text
    assert _snapshot() == before


def test_test_mode_skips_policy_checks_and_labels_record(client, auth_headers):
    r = _post(client, _claim(hospital_id="H002"), headers=auth_headers("Fraud_Team"), test_mode="true")
    assert r.status_code == 200, r.text
    with open_repos() as repos:
        records = [h for h in repos.history("U001") if h["claim_id"] == "CLM-ASSESS-1"]
        assert len(records) == 1 and records[0]["is_test"] is True
        assert repos.invoice_seen("H002", "INV-ASSESS-1")
        assert repos.seen_doc_hashes([hashlib.sha256(b"Hospital bill INV-ASSESS-1").hexdigest()])


def test_test_mode_still_requires_token(client):
    assert _post(client, _claim(), test_mode="true").status_code == 401


def test_customer_claim_records_are_not_test(client):
    from app.models import Claim
    claim = Claim.model_validate(_claim())
    with open_repos() as repos:
        repos.register_claim(claim, [])
        assert repos.history("U001")[-1]["is_test"] is False
