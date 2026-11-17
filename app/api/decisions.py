"""Investigator decisions. Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 17.4.

``POST /api/claims/{claim_id}/decisions`` records a human decision for a claim (Investigator and
Fraud_Team only; other roles get 403 and an ``access_denied`` audit event from ``require_roles``).
Each decision is a new ``investigator_decisions`` row, so earlier decisions stay in history. This is
the only code path that moves a claim to ``DECIDED``; until then an investigate-band claim keeps its
``OPEN_INVESTIGATION`` status. ``deny`` is only ever set here, by a person.

``claim_id`` is the external claim reference (``claims.claim_ref``) or the claim's UUID.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import CurrentUser
from app.api.deps import require_roles
from app.db import audit
from app.db.models import Claim, InvestigatorDecision, ProcessingRun, RiskAssessment
from app.db.session import get_session

router = APIRouter(tags=["decisions"])

DECISION_ROLES = ("Investigator", "Fraud_Team")
DECIDED = "DECIDED"
DecisionValue = Literal["approve", "APPROVE_EXCEPTION", "REQUEST_DOCUMENTS", "REFER_TO_FIU", "deny"]


class DecisionIn(BaseModel):
    decision: DecisionValue
    reason: str = Field(..., max_length=4000, description="Why; at least one non-blank character")
    notes: str | None = Field(None, max_length=10000)
    risk_assessment_id: uuid.UUID | None = Field(
        None, description="Risk assessment the decider was looking at; defaults to the claim's latest")

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Reason must contain at least one non-blank character")
        return v


class DecisionOut(BaseModel):
    id: str
    claim_id: str
    decision: str
    reason: str
    notes: str | None
    risk_assessment_id: str | None
    user_id: str
    created_at: str
    claim_status: str
    previous_status: str
    decision_count: int


def _find_claim(session: Session, claim_id: str) -> Claim | None:
    row = session.scalars(select(Claim).where(Claim.claim_ref == claim_id)).first()
    if row is None:
        try:
            row = session.get(Claim, uuid.UUID(claim_id))
        except ValueError:
            return None
    return row


def _visible_assessment(session: Session, claim: Claim, requested: uuid.UUID | None) -> uuid.UUID | None:
    if requested is not None:
        ra = session.get(RiskAssessment, requested)
        if ra is None or ra.claim_id != claim.id:
            raise HTTPException(422, "risk_assessment_id does not belong to this claim.")
        return ra.id
    latest = session.execute(
        select(RiskAssessment.id).join(ProcessingRun, ProcessingRun.id == RiskAssessment.run_id)
        .where(RiskAssessment.claim_id == claim.id)
        .order_by(ProcessingRun.started_at.desc()).limit(1)).scalar_one_or_none()
    return latest


@router.post("/api/claims/{claim_id}/decisions", status_code=201, response_model=DecisionOut)
def record_decision(claim_id: str, body: DecisionIn,
                    user: CurrentUser = Depends(require_roles(*DECISION_ROLES))) -> DecisionOut:
    with get_session() as session:
        claim = _find_claim(session, claim_id)
        if claim is None:
            raise HTTPException(404, "Claim not found.")
        ra_id = _visible_assessment(session, claim, body.risk_assessment_id)
        row = InvestigatorDecision(claim_id=claim.id, user_id=uuid.UUID(user.id), decision=body.decision,
                                   reason=body.reason, notes=body.notes, risk_assessment_id=ra_id)
        session.add(row)
        previous = claim.status
        claim.status = DECIDED
        session.flush()
        count = len(session.scalars(select(InvestigatorDecision.id)
                                    .where(InvestigatorDecision.claim_id == claim.id)).all())
        audit.log_decision(session, user.id, str(claim.id), body.decision,
                           detail={"assessment_id": str(ra_id) if ra_id else None, "status": DECIDED,
                                   "count": count, "role": user.role})
        session.refresh(row)
        return DecisionOut(id=str(row.id), claim_id=claim.claim_ref or str(claim.id), decision=row.decision,
                           reason=row.reason, notes=row.notes,
                           risk_assessment_id=str(ra_id) if ra_id else None, user_id=str(row.user_id),
                           created_at=row.created_at.isoformat(), claim_status=claim.status,
                           previous_status=previous, decision_count=count)
