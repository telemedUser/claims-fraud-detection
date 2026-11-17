"""require_roles: 401 without a valid token, 403 + access_denied audit for the wrong role, public routes open.
Requirements 7.1, 7.4, 7.5, 7.6, 6.3, 17.4."""
import pytest
from sqlalchemy import select

from app.db import audit, models as m
from app.db.session import SessionLocal, get_session

INTERNAL_GETS = ["/api/internal/overview", "/api/internal/claims", "/api/internal/claims/CLM-X"]


def _denied():
    with get_session() as s:
        return [e for e in s.scalars(select(m.AuditEvent)) if e.event_type == "access_denied"]


@pytest.mark.parametrize("path", INTERNAL_GETS)
def test_internal_gets_401_without_or_with_bad_token(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get(path, headers={"Authorization": "Basic abc"}).status_code == 401


def test_reset_401_without_token(client):
    assert client.post("/api/internal/reset").status_code == 401


@pytest.mark.parametrize("role", ["Investigator", "Ops_Manager", "Fraud_Team", "Administrator"])
def test_all_roles_read_internal_overview(client, auth_headers, role):
    assert client.get("/api/internal/overview", headers=auth_headers(role)).status_code == 200
    assert _denied() == []


@pytest.mark.parametrize("role", ["Investigator", "Ops_Manager", "Fraud_Team"])
def test_reset_forbidden_for_non_admin_and_audited(client, auth_headers, role):
    r = client.post("/api/internal/reset", headers=auth_headers(role))
    assert r.status_code == 403
    events = _denied()
    assert len(events) == 1
    assert events[0].detail == {"permission": "Administrator"}
    assert events[0].entity_id == "POST /api/internal/reset"
    assert audit.verify(SessionLocal()) is None


def test_denied_event_names_the_actor(client, auth_headers):
    client.post("/api/internal/reset", headers=auth_headers("Investigator"))
    with get_session() as s:
        uid = str(s.scalars(select(m.User).where(m.User.role == "Investigator")).one().id)
    assert _denied()[0].actor_id == uid


def test_unauthenticated_requests_write_no_denied_event(client):
    client.post("/api/internal/reset")
    assert _denied() == []


def test_public_routes_need_no_token(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/demo/clean").status_code == 200
    assert client.post("/api/policies/lookup", json={"policy_number": "POL-1001", "date_of_birth": "1992-04-18"}
                       ).status_code == 200
    assert client.get("/api/claims/CLM-NOPE/status").status_code == 404
    assert client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code == 401
