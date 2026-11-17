"""Finding feedback. Requirements 6.7, 3.6.

``POST /api/findings/{id}/feedback`` records an investigator verdict (false_positive | confirmed) in
``finding_feedback``, linked to the finding and the finding's Rule_Version. Findings are immutable:
the finding row is only read, never updated.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import CurrentUser
from app.api.deps import require_roles
from app.db import audit
from app.db.models import FindingFeedback, FindingRow
from app.db.session import get_session

router = APIRouter(tags=["feedback"])

FEEDBACK_ROLES = ("Investigator", "Fraud_Team")


class FeedbackIn(BaseModel):
    verdict: Literal["false_positive", "confirmed"]


class FeedbackOut(BaseModel):
    id: str
    finding_id: str
    verdict: str
    rule_version: str | None
    user_id: str
    created_at: str


@router.post("/api/findings/{finding_id}/feedback", status_code=201, response_model=FeedbackOut)
def submit_feedback(finding_id: str, body: FeedbackIn,
                    user: CurrentUser = Depends(require_roles(*FEEDBACK_ROLES))) -> FeedbackOut:
    try:
        fid = uuid.UUID(finding_id)
    except ValueError:
        raise HTTPException(404, "Finding not found.")
    with get_session() as session:
        finding = session.get(FindingRow, fid)
        if finding is None:
            raise HTTPException(404, "Finding not found.")
        row = FindingFeedback(finding_id=fid, user_id=uuid.UUID(user.id), verdict=body.verdict,
                              rule_version=finding.rule_version)
        session.add(row)
        session.flush()
        audit.record(session, "finding_feedback", actor_id=user.id, entity_type="finding",
                     entity_id=str(fid), detail={"finding_id": str(fid), "claim_id": str(finding.claim_id),
                                                 "decision": body.verdict})
        session.refresh(row)
        return FeedbackOut(id=str(row.id), finding_id=str(fid), verdict=row.verdict,
                           rule_version=row.rule_version, user_id=str(row.user_id),
                           created_at=row.created_at.isoformat())
