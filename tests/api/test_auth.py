"""Login, token and /api/me. Requirements 7.2, 7.3, 7.4, 17.4."""
import json
import time

import jwt
import pytest
from sqlalchemy import select

from app.api import auth
from app.db import audit, models as m
from app.db.session import get_session
from app.seed import run as seed_run

PW = {"investigator": "pw-inv-1", "ops_manager": "pw-ops-2", "fraud_team": "pw-fraud-3", "admin": "pw-admin-4"}


@pytest.fixture(autouse=True)
def _users(monkeypatch):
    for key, pw in PW.items():
        monkeypatch.setenv(f"SEED_PASSWORD_{key.upper()}", pw)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
    auth.reset_login_limiter()
    with get_session() as s:
        seed_run.seed_users(s)
    yield
    auth.reset_login_limiter()


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_success_token_claims(client):
    r = _login(client, "investigator", PW["investigator"])
    assert r.status_code == 200
    body = r.json()
    claims = jwt.decode(body["access_token"], "test-jwt-secret-that-is-long-enough-32b", algorithms=["HS256"])
    assert claims["role"] == "Investigator" and claims["jti"] and claims["sub"]
    assert abs(claims["exp"] - time.time() - 1800) < 30
    assert body["expires_in"] == 1800
    with get_session() as s:
        assert any(e.event_type == "login" and e.actor_id == claims["sub"]
                   for e in s.scalars(select(m.AuditEvent)))


def test_seed_one_user_per_role_idempotent_and_hashed():
    with get_session() as s:
        assert seed_run.seed_users(s) == []
        users = s.scalars(select(m.User)).all()
        assert sorted(u.role for u in users) == sorted(auth.ROLES)
        assert all(u.password_hash.startswith("$argon2id$") for u in users)
        assert len({u.password_hash for u in users}) == 4


def test_seed_skips_users_without_password(monkeypatch):
    for key in PW:
        monkeypatch.delenv(f"SEED_PASSWORD_{key.upper()}")
    monkeypatch.setenv("SEED_PASSWORD_INVESTIGATOR", "")
    with get_session() as s:
        s.query(m.User).delete()
        assert seed_run.seed_users(s) == []


def test_wrong_password_401_audited_without_password(client):
    r = _login(client, "admin", "not-the-password")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == auth.GENERIC_LOGIN_ERROR
    with get_session() as s:
        failed = [e for e in s.scalars(select(m.AuditEvent)) if e.event_type == "login_failed"]
        assert len(failed) == 1
        assert "not-the-password" not in json.dumps([e.detail for e in s.scalars(select(m.AuditEvent))])


def test_unknown_user_same_response_as_wrong_password(client):
    a = _login(client, "nobody", "x")
    b = _login(client, "admin", "x")
    def same(r):  # request_id differs per request by design
        e = r.json()["error"]
        return r.status_code, e["code"], e["message"], e["fields"]

    assert same(a) == same(b) == (401, "unauthenticated", auth.GENERIC_LOGIN_ERROR, [])


def test_inactive_user_401(client):
    with get_session() as s:
        s.scalars(select(m.User).where(m.User.username == "ops_manager")).one().is_active = False
    r = _login(client, "ops_manager", PW["ops_manager"])
    assert r.status_code == 401 and r.json()["error"]["message"] == auth.GENERIC_LOGIN_ERROR


def test_me_with_token(client):
    token = _login(client, "fraud_team", PW["fraud_team"]).json()["access_token"]
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "fraud_team" and r.json()["role"] == "Fraud_Team"


def test_me_missing_or_invalid_token_401(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    forged = jwt.encode({"sub": "x", "role": "Administrator", "jti": "j", "exp": int(time.time()) + 60},
                        "some-other-secret-that-is-32-bytes-long!", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_me_expired_token_401(client):
    with get_session() as s:
        uid = str(s.scalars(select(m.User)).first().id)
    old = jwt.encode({"sub": uid, "role": "Investigator", "jti": "j", "exp": int(time.time()) - 5},
                     "test-jwt-secret-that-is-long-enough-32b", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_me_rejects_token_of_deactivated_user(client):
    token = _login(client, "investigator", PW["investigator"]).json()["access_token"]
    with get_session() as s:
        s.scalars(select(m.User).where(m.User.username == "investigator")).one().is_active = False
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_login_503_without_jwt_secret(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "")
    r = _login(client, "admin", PW["admin"])
    assert r.status_code == 503 and "JWT_SECRET" in r.json()["error"]["message"]


def test_login_rate_limited(client, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE", "3/minute")
    auth.reset_login_limiter()
    codes = [_login(client, "admin", "bad").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    assert audit.verify(_session_for_verify()) is None


def _session_for_verify():
    from app.db.session import SessionLocal
    return SessionLocal()
