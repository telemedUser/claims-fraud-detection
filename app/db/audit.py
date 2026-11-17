"""Audit service: appends to the tamper-evident hash chain. Requirements 17.4, 17.7, 17.8.

Inserts run inside the caller's transaction. On PostgreSQL a transaction-scoped
advisory lock serialises writers so the chain stays linear; on SQLite the
single-writer lock gives the same guarantee. `detail` is sanitised against an
allow-list so PII and document content never reach the log.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import audit_chain
from app.db.models import AuditEvent as AuditRow

AUDIT_LOCK_KEY = 0x41554449  # "AUDI"

# Keys that may appear in `detail`: ids, codes, counts, statuses only.
ALLOWED_DETAIL_KEYS = frozenset({
    "claim_id", "document_id", "assessment_id", "job_id", "finding_id", "user_id",
    "role", "status", "decision", "outcome", "reason_code", "code", "error_code",
    "count", "document_count", "finding_count", "attempt", "attempts",
    "config_key", "config_version", "old_version", "new_version", "ruleset_version",
    "doc_type", "kind", "method", "path", "http_status", "score", "band", "route",
    "permission", "success",
})
MAX_STR_LEN = 64


def _clean_scalar(v: Any) -> tuple[bool, Any]:
    if v is None or isinstance(v, (bool, int, float)):
        return True, v
    if isinstance(v, str) and len(v) <= MAX_STR_LEN and "\n" not in v:
        return True, v
    if hasattr(v, "hex") and hasattr(v, "int"):  # uuid.UUID
        return True, str(v)
    return False, None


def sanitise_detail(detail: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep only allow-listed keys with short scalar (or list-of-scalar) values."""
    out: dict[str, Any] = {}
    for k, v in (detail or {}).items():
        if k not in ALLOWED_DETAIL_KEYS:
            continue
        if isinstance(v, (list, tuple)):
            items = [c for ok, c in (_clean_scalar(x) for x in v) if ok]
            if len(items) == len(v):
                out[k] = items
            continue
        ok, cleaned = _clean_scalar(v)
        if ok:
            out[k] = cleaned
    return out


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _to_chain(row: AuditRow) -> audit_chain.AuditEvent:
    return audit_chain.AuditEvent(
        seq=row.seq, ts=_utc(row.ts), actor_id=row.actor_id, event_type=row.event_type,
        entity_type=row.entity_type, entity_id=row.entity_id, request_id=row.request_id,
        detail=row.detail, prev_hash=row.prev_hash, hash=row.hash,
    )


def _lock(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})


def record(
    session: Session,
    event_type: str,
    *,
    actor_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    request_id: Optional[str] = None,
    detail: Optional[Mapping[str, Any]] = None,
) -> AuditRow:
    """Append one event in the caller's transaction (caller commits)."""
    _lock(session)
    tail_row = session.execute(select(AuditRow).order_by(AuditRow.seq.desc()).limit(1)).scalar_one_or_none()
    tail = _to_chain(tail_row) if tail_row is not None else None
    if request_id is None:
        from app.logging_setup import current_request_id
        request_id = current_request_id()
    fields = {
        "ts": datetime.now(timezone.utc).replace(microsecond=0),
        "actor_id": actor_id,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "request_id": request_id,
        "detail": sanitise_detail(detail),
    }
    ev = audit_chain.append(tail, fields)
    row = AuditRow(
        seq=ev.seq, ts=ev.ts, actor_id=ev.actor_id, event_type=ev.event_type,
        entity_type=ev.entity_type, entity_id=ev.entity_id, request_id=ev.request_id,
        detail=ev.detail, prev_hash=ev.prev_hash, hash=ev.hash,
    )
    session.add(row)
    session.flush()
    return row


def verify(session: Session) -> Optional[int]:
    """Seq of the first tampered event, or None if the chain is intact."""
    rows = session.execute(select(AuditRow).order_by(AuditRow.seq)).scalars().all()
    return audit_chain.verify_chain([_to_chain(r) for r in rows])


# ---- typed helpers -------------------------------------------------------

def log_login(session: Session, actor_id: Optional[str], success: bool, **kw: Any) -> AuditRow:
    return record(session, "login" if success else "login_failed", actor_id=actor_id,
                  entity_type="user", entity_id=actor_id, detail={"success": success}, **kw)


def log_claim_access(session: Session, actor_id: str, claim_id: str, **kw: Any) -> AuditRow:
    return record(session, "claim_access", actor_id=actor_id, entity_type="claim",
                  entity_id=claim_id, detail={"claim_id": claim_id}, **kw)


def log_document_access(session: Session, actor_id: str, document_id: str,
                        claim_id: Optional[str] = None, **kw: Any) -> AuditRow:
    return record(session, "document_access", actor_id=actor_id, entity_type="document",
                  entity_id=document_id, detail={"document_id": document_id, "claim_id": claim_id}, **kw)


def log_processing(session: Session, claim_id: str, status: str, actor_id: Optional[str] = None,
                   detail: Optional[Mapping[str, Any]] = None, **kw: Any) -> AuditRow:
    return record(session, "processing", actor_id=actor_id, entity_type="claim", entity_id=claim_id,
                  detail={**(detail or {}), "claim_id": claim_id, "status": status}, **kw)


def log_config_change(session: Session, actor_id: str, config_key: str,
                      old_version: Optional[int] = None, new_version: Optional[int] = None, **kw: Any) -> AuditRow:
    return record(session, "config_change", actor_id=actor_id, entity_type="config", entity_id=config_key,
                  detail={"config_key": config_key, "old_version": old_version, "new_version": new_version}, **kw)


def log_decision(session: Session, actor_id: str, claim_id: str, decision: str,
                 detail: Optional[Mapping[str, Any]] = None, **kw: Any) -> AuditRow:
    return record(session, "decision", actor_id=actor_id, entity_type="claim", entity_id=claim_id,
                  detail={**(detail or {}), "claim_id": claim_id, "decision": decision}, **kw)


def log_denied(session: Session, actor_id: Optional[str], permission: str,
               entity_type: Optional[str] = None, entity_id: Optional[str] = None, **kw: Any) -> AuditRow:
    return record(session, "access_denied", actor_id=actor_id, entity_type=entity_type, entity_id=entity_id,
                  detail={"permission": permission}, **kw)
