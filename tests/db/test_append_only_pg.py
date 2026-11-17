"""PostgreSQL append-only triggers on findings and audit_events (task 8.5).

Requires TEST_POSTGRES_URL (e.g. postgresql+psycopg://user:pw@host/db). The
migrations run inside a throwaway schema that is dropped afterwards.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("TEST_POSTGRES_URL")

if not BASE_URL:
    pytest.skip("TEST_POSTGRES_URL not set", allow_module_level=True)


def _reachable(url: str) -> bool:
    try:
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return True
    except Exception:
        return False


if not _reachable(BASE_URL):
    pytest.skip("TEST_POSTGRES_URL is unreachable", allow_module_level=True)


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "app" / "db" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="module")
def engine():
    schema = f"t_append_only_{uuid.uuid4().hex[:8]}"
    admin = create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(BASE_URL).update_query_dict({"options": f"-csearch_path={schema}"})
    cfg = _config(url)
    eng = create_engine(url)
    try:
        command.upgrade(cfg, "head")
        yield eng
    finally:
        try:
            command.downgrade(cfg, "base")
        finally:
            eng.dispose()
            with admin.connect() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            admin.dispose()


@pytest.fixture(scope="module")
def ids(engine):
    claim_id, run_id, finding_id, audit_id = (uuid.uuid4() for _ in range(4))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO claims (id, channel, status, is_test, created_at) "
                          "VALUES (:id, 'investigator', 'RECEIVED', false, now())"), {"id": claim_id})
        conn.execute(text("INSERT INTO processing_runs (id, claim_id, idempotency_key, status) "
                          "VALUES (:id, :c, :k, 'QUEUED')"),
                     {"id": run_id, "c": claim_id, "k": f"k-{run_id}"})
        _insert_finding(conn, finding_id, claim_id, run_id)
        _insert_audit(conn, audit_id, 1)
    return {"claim": claim_id, "run": run_id, "finding": finding_id, "audit": audit_id}


def _insert_finding(conn, finding_id, claim_id, run_id):
    conn.execute(text("INSERT INTO findings (id, claim_id, run_id, check_id, severity, status, created_at) "
                      "VALUES (:id, :c, :r, 'chk', 'LOW', 'PASS', now())"),
                 {"id": finding_id, "c": claim_id, "r": run_id})


def _insert_audit(conn, audit_id, seq):
    conn.execute(text("INSERT INTO audit_events (id, seq, ts, event_type, prev_hash, hash) "
                      "VALUES (:id, :seq, now(), 'test.event', :p, :h)"),
                 {"id": audit_id, "seq": seq, "p": "0" * 64, "h": "1" * 64})


def test_finding_update_is_rejected(engine, ids):
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE findings SET severity = 'HIGH' WHERE id = :id"), {"id": ids["finding"]})


def test_finding_delete_is_rejected(engine, ids):
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM findings WHERE id = :id"), {"id": ids["finding"]})


def test_audit_event_update_is_rejected(engine, ids):
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_events SET event_type = 'x' WHERE id = :id"), {"id": ids["audit"]})


def test_audit_event_delete_is_rejected(engine, ids):
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": ids["audit"]})


def test_insert_still_works_and_rows_unchanged(engine, ids):
    with engine.begin() as conn:
        _insert_finding(conn, uuid.uuid4(), ids["claim"], ids["run"])
        _insert_audit(conn, uuid.uuid4(), 2)
    with engine.connect() as conn:
        sev = conn.execute(text("SELECT severity FROM findings WHERE id = :id"), {"id": ids["finding"]}).scalar_one()
        evt = conn.execute(text("SELECT event_type FROM audit_events WHERE id = :id"), {"id": ids["audit"]}).scalar_one()
    assert sev == "LOW"
    assert evt == "test.event"
