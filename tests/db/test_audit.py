"""Audit service on in-memory SQLite (Req 17.4, 17.7, 17.8)."""
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import audit
from app.db.session import create_all, make_engine


@pytest.fixture()
def engine():
    eng = make_engine("sqlite://")
    create_all(eng)
    yield eng
    eng.dispose()


def _seed(s):
    audit.log_login(s, "u1", True, request_id="req-00000001")
    audit.log_claim_access(s, "u1", "c1")
    audit.log_document_access(s, "u1", "d1", "c1")
    audit.log_processing(s, "c1", "done")
    audit.log_config_change(s, "admin", "risk", 1, 2)
    audit.log_decision(s, "u1", "c1", "approve")
    audit.log_denied(s, "u2", "claims:decide", "claim", "c1")
    s.commit()


def test_chain_verifies(engine):
    with Session(engine) as s:
        _seed(s)
        assert audit.verify(s) is None


def test_tamper_detected(engine):
    with Session(engine) as s:
        _seed(s)
        s.execute(text("UPDATE audit_events SET actor_id='evil' WHERE seq=3"))
        s.commit()
        assert audit.verify(s) == 3


def test_deleted_event_detected(engine):
    with Session(engine) as s:
        _seed(s)
        s.execute(text("DELETE FROM audit_events WHERE seq=2"))
        s.commit()
        assert audit.verify(s) == 3


def test_sanitiser_drops_pii_and_content():
    out = audit.sanitise_detail({
        "claim_id": "c1", "claimant_name": "Jane Doe", "email": "a@b.c",
        "document_text": "secret", "count": 3, "status": "ok", "reason_code": "x" * 500,
        "finding_id": {"nested": "Jane"},
    })
    assert out == {"claim_id": "c1", "count": 3, "status": "ok"}


def test_record_ignores_pii_in_detail(engine):
    with Session(engine) as s:
        row = audit.record(s, "processing", detail={"patient_name": "Jane Doe", "status": "ok"})
        s.commit()
        assert row.detail == {"status": "ok"}
