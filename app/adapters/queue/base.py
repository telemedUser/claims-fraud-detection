"""Queue port. Implementations: PostgresQueue (also runs on SQLite for local dev and tests)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class QueueAdapter(Protocol):
    def enqueue(self, kind: str, payload: dict[str, Any], dedupe_key: str | None = None) -> uuid.UUID:
        """Add a job; return the id of an existing unfinished job with the same dedupe key."""

    def lease(self, worker_id: str, lease_seconds: int) -> Any | None:
        """Atomically claim the oldest runnable job, or return None."""

    def complete(self, job_id: uuid.UUID) -> None: ...

    def fail(self, job_id: uuid.UUID, error: str, retry_in: float | None = None) -> str:
        """Requeue (returns 'queued') or, when attempts are exhausted, mark dead ('dead')."""

    def reap(self, now: datetime | None = None) -> int:
        """Requeue (or kill) jobs whose lease expired; return how many were touched."""
