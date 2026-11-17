"""Schema tests for app.db.models on in-memory SQLite (Req 17.1, 16.5, 9.7, 4.9)."""
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import create_all, make_engine

EXPECTED_TABLES = {
    "users", "policies", "members", "providers", "doctors", "claims", "claim_changes", "documents",
    "extraction_results", "normalised_facts", "invoices", "invoice_line_items", "processing_runs",
    "jobs", "agent_executions", "findings", "risk_configs", "risk_assessments", "risk_contributions",
    "verification_requests", "verification_responses", "investigator_decisions", "finding_feedback",
    "llm_calls", "rule_versions", "audit_events",
}


@pytest.fixture()
def engine():
    eng = make_engine("sqlite://")
    create_all(eng)
    yield eng
    eng.dispose()


def test_all_design_tables_exist(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_primary_keys_are_uuid(engine):
    with Session(engine) as s:
        claim = models.Claim()
        s.add(claim)
        s.commit()
        assert isinstance(claim.id, uuid.UUID) and claim.id.version == 4


def test_documents_unique_claim_sha256(engine):
    with Session(engine) as s:
        claim = models.Claim()
        s.add(claim)
        s.flush()
        s.add(models.Document(claim_id=claim.id, storage_key="a", sha256="x" * 64))
        s.commit()
        s.add(models.Document(claim_id=claim.id, storage_key="b", sha256="x" * 64))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        other = models.Claim()
        s.add(other)
        s.flush()
        s.add(models.Document(claim_id=other.id, storage_key="c", sha256="x" * 64))
        s.commit()  # same hash on a different claim is allowed


def test_runs_unique_claim_idempotency_key(engine):
    with Session(engine) as s:
        claim = models.Claim()
        s.add(claim)
        s.flush()
        s.add(models.ProcessingRun(claim_id=claim.id, idempotency_key="k1"))
        s.commit()
        s.add(models.ProcessingRun(claim_id=claim.id, idempotency_key="k1"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_foreign_keys_enforced_on_sqlite(engine):
    with Session(engine) as s:
        s.add(models.Document(claim_id=uuid.uuid4(), storage_key="a", sha256="y" * 64))
        with pytest.raises(IntegrityError):
            s.commit()
