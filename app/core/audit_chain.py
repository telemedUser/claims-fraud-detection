"""Tamper-evident audit hash chain. Pure: no I/O. Requirements 17.5, 17.6.

hash = sha256(prev_hash || canonical_json(ts, actor_id, event_type, entity_type,
entity_id, request_id, detail))
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.core.finding import canonical_json

GENESIS_PREV_HASH = "0" * 64

HASHED_FIELDS = (
    "ts",
    "actor_id",
    "event_type",
    "entity_type",
    "entity_id",
    "request_id",
    "detail",
)


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    ts: datetime
    actor_id: str
    event_type: str
    entity_type: str
    entity_id: str
    request_id: str
    detail: Any
    prev_hash: str
    hash: str

    def fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in HASHED_FIELDS}


def compute_hash(prev_hash: str, fields: Mapping[str, Any]) -> str:
    payload = canonical_json({name: fields[name] for name in HASHED_FIELDS})
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def append(tail: Optional[AuditEvent], fields: Mapping[str, Any]) -> AuditEvent:
    """Build the next event after `tail` (None starts a new chain at seq 1)."""
    prev_hash = tail.hash if tail is not None else GENESIS_PREV_HASH
    seq = tail.seq + 1 if tail is not None else 1
    return AuditEvent(
        seq=seq,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, fields),
        **{name: fields[name] for name in HASHED_FIELDS},
    )


def verify_chain(events: Iterable[AuditEvent] | Sequence[AuditEvent]) -> Optional[int]:
    """Return the seq of the first bad event, or None if the chain is intact.

    Checks, in order per event: contiguous seq (starting at the first event's
    seq), prev_hash link, and recomputed hash. The first event must link to
    GENESIS_PREV_HASH when its seq is 1; otherwise its prev_hash is trusted
    as the anchor of a partial chain.
    """
    prev: Optional[AuditEvent] = None
    for ev in events:
        if prev is None:
            if ev.seq == 1 and ev.prev_hash != GENESIS_PREV_HASH:
                return ev.seq
        else:
            if ev.seq != prev.seq + 1 or ev.prev_hash != prev.hash:
                return ev.seq
        if ev.hash != compute_hash(ev.prev_hash, ev.fields()):
            return ev.seq
        prev = ev
    return None
