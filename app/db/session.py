"""Engine and session factory. The URL comes from ``get_settings().database_url``."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.settings import get_settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


def make_engine(url: str | None = None) -> Engine:
    """Build an engine. SQLite gets ``foreign_keys=ON``; in-memory SQLite shares one
    connection (StaticPool) so every session sees the same database."""
    url = url or get_settings().database_url
    kwargs: dict = {}
    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_memory(url):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if _is_sqlite(url):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def SessionLocal() -> Session:
    """Open a new session on the process-wide engine (created lazily)."""
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _factory()


def reset_engine() -> None:
    """Dispose the cached engine and factory (tests, settings changes)."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


def set_engine(engine: Engine) -> None:
    """Make ``engine`` the process-wide engine (tests inject an in-memory database)."""
    global _engine, _factory
    _engine = engine
    _factory = None


# A StaticPool engine hands every session the same DBAPI connection. Agents run in worker threads,
# so sessions on such an engine are serialised. Other engines use one connection per session.
_SHARED_CONNECTION_LOCK = threading.RLock()


@contextmanager
def get_session() -> Iterator[Session]:
    """Commit on success, roll back on error, always close."""
    shared = isinstance(get_engine().pool, StaticPool)
    lock = _SHARED_CONNECTION_LOCK if shared else nullcontext()
    with lock:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def create_all(engine: Engine | None = None) -> Engine:
    """Create every table (tests and local dev; production uses Alembic)."""
    from app.db.models import Base

    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine
