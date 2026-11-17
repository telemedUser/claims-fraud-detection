"""Finding feedback endpoint. Requirements 6.7, 3.6."""
import uuid

import pytest
from sqlalchemy import select

from app.db import audit, models
from app.db.session import get_session


def _insert_finding(rule_version="rv-7") -> str:
    with get_session() as s:
        claim = models.Claim()
        s.add(claim)
        s.flush()
        run = models.ProcessingRun(claim_id=claim.id, idempotency_key="k1")
        s.add(run)
        s.flush()
        f = models.FindingRow(claim_id=claim.id, run_id=run.id, check_id="C1", severity="high",
                              status="flagged", rule_version=rule_version)
        s.add(f)
        s.flush()
        return str(f.id)


@pytest.mark.parametrize("role", ["Investigator", "Fraud_Team"])
@pytest.mark.parametrize("verdict", ["false_positive", "confirmed"])
def test_feedback_stored_with_rule_version(client, auth_headers, role, verdict):
    fid = _insert_finding("rv-7")
    r = client.post(f"/api/findings/{fid}/feedback", json={"verdict": verdict}, headers=auth_headers(role))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verdict"] == verdict and body["rule_version"] == "rv-7" and body["finding_id"] == fid
    with get_session() as s:
        rows = s.scalars(select(models.FindingFeedback)).all()
        assert len(rows) == 1
        assert str(rows[0].finding_id) == fid and rows[0].rule_version == "rv-7"
        finding = s.get(models.FindingRow, uuid.UUID(fid))
        assert finding.status == "flagged" and finding.rule_version == "rv-7"  # finding untouched
        events = s.scalars(select(models.AuditEvent).where(models.AuditEvent.event_type == "finding_feedback")).all()
        assert len(events) == 1 and events[0].detail["finding_id"] == fid
        assert audit.verify(s) is None


def test_unknown_finding_is_404_envelope(client, auth_headers):
    r = client.post(f"/api/findings/{uuid.uuid4()}/feedback", json={"verdict": "confirmed"},
                    headers=auth_headers("Investigator"))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_invalid_verdict_is_422(client, auth_headers):
    fid = _insert_finding()
    r = client.post(f"/api/findings/{fid}/feedback", json={"verdict": "maybe"}, headers=auth_headers("Investigator"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    with get_session() as s:
        assert s.scalars(select(models.FindingFeedback)).all() == []


def test_ops_manager_forbidden(client, auth_headers):
    fid = _insert_finding()
    r = client.post(f"/api/findings/{fid}/feedback", json={"verdict": "confirmed"},
                    headers=auth_headers("Ops_Manager"))
    assert r.status_code == 403
