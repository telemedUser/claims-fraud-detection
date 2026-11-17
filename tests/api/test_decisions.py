"""Investigator decisions endpoint. Requirements 6.1-6.6, 17.4."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select

from app.db import audit, models
from app.db.session import get_session

DECISIONS = ["approve", "APPROVE_EXCEPTION", "REQUEST_DOCUMENTS", "REFER_TO_FIU", "deny"]


def _insert_claim(ref="CLM-DEC-1", status="OPEN_INVESTIGATION", assessments=0) -> tuple[str, list[str]]:
    """A claim row plus ``assessments`` risk assessments (oldest first)."""
    with get_session() as s:
        claim = models.Claim(claim_ref=ref, status=status)
        s.add(claim)
        s.flush()
        ids = []
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(assessments):
            run = models.ProcessingRun(claim_id=claim.id, idempotency_key=f"k{i}", started_at=base + timedelta(hours=i))
            s.add(run)
            s.flush()
            ra = models.RiskAssessment(run_id=run.id, claim_id=claim.id, score=80.0, band="investigate")
            s.add(ra)
            s.flush()
            ids.append(str(ra.id))
        return ref, ids


def _decisions():
    with get_session() as s:
        return s.scalars(select(models.InvestigatorDecision).order_by(models.InvestigatorDecision.created_at)).all()


def _events(kind):
    with get_session() as s:
        return s.scalars(select(models.AuditEvent).where(models.AuditEvent.event_type == kind)).all()


def _status(ref):
    with get_session() as s:
        return s.scalars(select(models.Claim.status).where(models.Claim.claim_ref == ref)).one()


@pytest.mark.parametrize("role", ["Investigator", "Fraud_Team"])
@pytest.mark.parametrize("decision", DECISIONS)
def test_decision_recorded_with_user_reason_notes_and_assessment(client, auth_headers, role, decision):
    ref, ras = _insert_claim(assessments=2)
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers(role),
                    json={"decision": decision, "reason": "Hospital confirmed stay", "notes": "called desk",
                          "risk_assessment_id": ras[0]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["decision"] == decision and body["claim_status"] == "DECIDED"
    assert body["previous_status"] == "OPEN_INVESTIGATION" and body["risk_assessment_id"] == ras[0]
    [row] = _decisions()
    with get_session() as s:
        user = s.scalars(select(models.User).where(models.User.role == role)).one()
    assert row.user_id == user.id and row.reason == "Hospital confirmed stay" and row.notes == "called desk"
    assert str(row.risk_assessment_id) == ras[0] and row.created_at is not None
    assert _status(ref) == "DECIDED"
    [ev] = _events("decision")
    assert ev.actor_id == str(user.id) and ev.detail["decision"] == decision
    assert ev.detail["assessment_id"] == ras[0]
    with get_session() as s:
        assert audit.verify(s) is None


def test_defaults_to_latest_assessment_and_claim_uuid_works(client, auth_headers):
    ref, ras = _insert_claim(assessments=3)
    with get_session() as s:
        cid = str(s.scalars(select(models.Claim.id).where(models.Claim.claim_ref == ref)).one())
    r = client.post(f"/api/claims/{cid}/decisions", headers=auth_headers("Investigator"),
                    json={"decision": "approve", "reason": "ok"})
    assert r.status_code == 201, r.text
    assert r.json()["risk_assessment_id"] == ras[-1] and r.json()["notes"] is None


def test_no_assessment_records_null(client, auth_headers):
    ref, _ = _insert_claim(assessments=0)
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Fraud_Team"),
                    json={"decision": "REQUEST_DOCUMENTS", "reason": "need discharge summary"})
    assert r.status_code == 201 and r.json()["risk_assessment_id"] is None


def test_later_decisions_keep_history(client, auth_headers):
    ref, _ = _insert_claim()
    for i, d in enumerate(["REQUEST_DOCUMENTS", "REFER_TO_FIU", "deny"], start=1):
        r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Investigator"),
                        json={"decision": d, "reason": f"step {i}"})
        assert r.status_code == 201 and r.json()["decision_count"] == i
    rows = _decisions()
    assert [x.decision for x in rows] == ["REQUEST_DOCUMENTS", "REFER_TO_FIU", "deny"]
    assert [x.reason for x in rows] == ["step 1", "step 2", "step 3"]
    assert len(_events("decision")) == 3


@pytest.mark.parametrize("role", ["Ops_Manager", "Administrator"])
def test_other_roles_forbidden_and_audited(client, auth_headers, role):
    ref, _ = _insert_claim()
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers(role),
                    json={"decision": "approve", "reason": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert _decisions() == [] and _status(ref) == "OPEN_INVESTIGATION"
    denied = _events("access_denied")
    assert len(denied) == 1 and denied[0].entity_id.endswith(f"/api/claims/{ref}/decisions")


def test_anonymous_is_401(client):
    ref, _ = _insert_claim()
    r = client.post(f"/api/claims/{ref}/decisions", json={"decision": "approve", "reason": "x"})
    assert r.status_code == 401 and _decisions() == []


@pytest.mark.parametrize("payload,field", [
    ({"decision": "approve", "reason": "   "}, "reason"),
    ({"decision": "approve", "reason": ""}, "reason"),
    ({"decision": "approve"}, "reason"),
    ({"decision": "auto_approve", "reason": "x"}, "decision"),
    ({"decision": "APPROVE", "reason": "x"}, "decision"),
])
def test_invalid_payload_is_422_and_nothing_stored(client, auth_headers, payload, field):
    ref, _ = _insert_claim()
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Investigator"), json=payload)
    assert r.status_code == 422
    assert field in [f["field"] for f in r.json()["error"]["fields"]]
    assert _decisions() == [] and _status(ref) == "OPEN_INVESTIGATION"


def test_unknown_claim_is_404(client, auth_headers):
    r = client.post("/api/claims/CLM-NOPE/decisions", headers=auth_headers("Investigator"),
                    json={"decision": "approve", "reason": "x"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_assessment_of_another_claim_is_rejected(client, auth_headers):
    ref, _ = _insert_claim("CLM-A", assessments=1)
    _, other = _insert_claim("CLM-B", assessments=1)
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Investigator"),
                    json={"decision": "approve", "reason": "x", "risk_assessment_id": other[0]})
    assert r.status_code == 422 and _decisions() == [] and _status(ref) == "OPEN_INVESTIGATION"


def test_investigate_claim_stays_open_until_decided(client, auth_headers):
    """No route other than the decision endpoint sets DECIDED (Req 6.5)."""
    ref, _ = _insert_claim()
    assert client.get(f"/api/internal/claims", headers=auth_headers("Investigator")).status_code == 200
    assert _status(ref) == "OPEN_INVESTIGATION"
    client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Investigator"),
                json={"decision": "approve", "reason": "fine"})
    assert _status(ref) == "DECIDED"


_blank = st.text(alphabet=" \t\r\n\u00a0\u2003", max_size=8)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(decision=st.sampled_from(DECISIONS), reason=st.one_of(_blank, st.text(min_size=1, max_size=40)))
def test_reason_rule_property(client, auth_headers, decision, reason):
    """A decision is stored iff the reason has a non-blank character (Req 6.2)."""
    ref = f"CLM-P-{uuid.uuid4().hex[:8]}"
    _insert_claim(ref)
    before = len(_decisions())
    r = client.post(f"/api/claims/{ref}/decisions", headers=auth_headers("Investigator"),
                    json={"decision": decision, "reason": reason})
    if reason.strip():
        assert r.status_code == 201 and len(_decisions()) == before + 1 and _status(ref) == "DECIDED"
    else:
        assert r.status_code == 422 and len(_decisions()) == before and _status(ref) == "OPEN_INVESTIGATION"
