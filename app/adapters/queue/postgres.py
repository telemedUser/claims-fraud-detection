"""Database-backed job queue. Leasing uses ``FOR UPDATE SKIP LOCKED`` on PostgreSQL (ignored by
SQLite) and always finishes with a conditional UPDATE whose rowcount decides who won."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update

from app.db.models import Job
from app.db.session import get_session

ACTIVE = ("queued", "leased")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class PostgresQueue:
    def __init__(self, clock: Callable[[], datetime] = _utcnow, max_attempts: int = 3) -> None:
        self._clock = clock
        self._max_attempts = max_attempts

    def enqueue(self, kind: str, payload: dict[str, Any], dedupe_key: str | None = None) -> uuid.UUID:
        with get_session() as s:
            if dedupe_key is not None:
                existing = s.scalars(
                    select(Job.id).where(Job.dedupe_key == dedupe_key, Job.status.in_(ACTIVE)).limit(1)
                ).first()
                if existing is not None:
                    return existing
            job = Job(kind=kind, payload=payload, status="queued", attempts=0,
                      max_attempts=self._max_attempts, run_after=self._clock(), dedupe_key=dedupe_key)
            s.add(job)
            s.flush()
            return job.id

    def lease(self, worker_id: str, lease_seconds: int) -> Job | None:
        now = self._clock()
        for _ in range(5):
            with get_session() as s:
                stmt = (select(Job).where(Job.status == "queued", Job.run_after <= now)
                        .order_by(Job.run_after, Job.id).limit(1).with_for_update(skip_locked=True))
                job = s.scalars(stmt).first()
                if job is None:
                    return None
                res = s.execute(
                    update(Job).where(Job.id == job.id, Job.status == "queued").values(
                        status="leased", leased_by=worker_id, attempts=Job.attempts + 1,
                        lease_expires_at=now + timedelta(seconds=lease_seconds)))
                if res.rowcount == 1:
                    s.flush()
                    s.refresh(job)
                    return job
        return None

    def complete(self, job_id: uuid.UUID) -> None:
        with get_session() as s:
            s.execute(update(Job).where(Job.id == job_id).values(
                status="done", leased_by=None, lease_expires_at=None))

    def fail(self, job_id: uuid.UUID, error: str, retry_in: float | None = None) -> str:
        with get_session() as s:
            job = s.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            job.last_error = error
            job.leased_by = None
            job.lease_expires_at = None
            if job.attempts >= job.max_attempts:
                job.status = "dead"
            else:
                job.status = "queued"
                job.run_after = self._clock() + timedelta(seconds=retry_in or 0)
            return job.status

    def reap(self, now: datetime | None = None) -> int:
        now = now or self._clock()
        count = 0
        with get_session() as s:
            jobs = s.scalars(select(Job).where(Job.status == "leased").with_for_update(skip_locked=True)).all()
            for job in jobs:
                if job.lease_expires_at is None or _aware(job.lease_expires_at) > _aware(now):
                    continue
                job.leased_by = None
                job.lease_expires_at = None
                job.last_error = "lease expired"
                if job.attempts >= job.max_attempts:
                    job.status = "dead"
                else:
                    job.status = "queued"
                    job.run_after = now
                count += 1
        return count
