"""Test harness: the LLM is always off; every test gets a seeded in-memory SQLite database and empty jobs."""
import os

# Must happen before `app` is imported. Real environment variables take precedence over the
# git-ignored .env in app.settings, so an existing (empty) value stops the real key being re-added.
for _k in ("GEMINI_API_KEY", "BEDROCK_MODEL_ID"):
    os.environ[_k] = ""
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough-32b"
# A developer .env may enable dev seed passwords; tests configure seed passwords explicitly.
os.environ["DEV_SEED_DEFAULT_PASSWORDS"] = "false"

TEST_PASSWORD = "test-password-123"

import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "check_id(id): ties a test to a design check identifier")
    config.addinivalue_line("markers", "postgres: requires a reachable PostgreSQL instance")
    config.addinivalue_line("markers", "live_llm: calls the real Gemini API (never run by default)")


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    # Guard against a test or a later load_env() call re-enabling the LLM.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")
    from app import llm
    assert not llm.enabled()


@pytest.fixture(scope="session")
def _seeded_template():
    """One seeded in-memory SQLite database per test session; each test gets a copy."""
    from sqlalchemy.orm import Session
    from app.db import models
    from app.db.session import make_engine
    from app.seed.run import seed

    engine = make_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _fresh_state(_seeded_template):
    """Each test runs on its own in-memory database (a copy of the seeded template) and empty jobs."""
    from app import jobs
    from app.db import session as db_session

    engine = db_session.make_engine("sqlite://")
    src, dst = _seeded_template.raw_connection(), engine.raw_connection()
    try:
        src.driver_connection.backup(dst.driver_connection)
    finally:
        src.close()
        dst.close()
    db_session.set_engine(engine)
    jobs.reset()
    yield
    db_session.reset_engine()
    jobs.reset()


@pytest.fixture(autouse=True)
def _fresh_ratelimit(monkeypatch):
    from app import ratelimit
    monkeypatch.delenv("LOOKUP_RATE", raising=False)
    ratelimit.reset_lookup_limiter()
    yield
    ratelimit.reset_lookup_limiter()


@pytest.fixture
def auth_headers(monkeypatch):
    """Seeds the four role users (password TEST_PASSWORD) and returns ``auth_headers(role)``,
    which gives ``{"Authorization": "Bearer <token>"}`` for the user holding that role."""
    from sqlalchemy import select
    from app.api.auth import issue_token
    from app.db import models
    from app.db.session import get_session
    from app.seed.run import seed_users

    monkeypatch.setenv("SEED_USER_PASSWORD", TEST_PASSWORD)
    with get_session() as s:
        seed_users(s)

    def _headers(role: str) -> dict:
        with get_session() as s:
            user = s.scalars(select(models.User).where(models.User.role == role)).one()
            token, _ = issue_token(str(user.id), user.role)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    # Context manager keeps one event loop alive so background claim tasks can finish.
    with TestClient(app) as c:
        yield c
