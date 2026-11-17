"""Additive, saturating risk score over a list of findings. Requirements 5.1-5.6.

Pure Python. Scores exactly the list it receives; deduplication is the caller's job.
"""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.finding import Finding, FindingDraft, FindingStatus
from app.core.risk_config import RiskConfig


class Contribution(BaseModel):
    """Points one finding adds to the score.

    ``index`` is the position of the finding in the input list and is always set.
    ``finding_id`` is set only when the input was a persisted ``Finding``; drafts
    are identified by ``index`` alone.
    """

    model_config = ConfigDict(frozen=True)

    index: int
    finding_id: UUID | None
    check_id: str
    severity: str
    status: FindingStatus
    points: float


class NotScored(BaseModel):
    """A finding that contributes 0 (NOT_CHECKED, INFORMATIONAL, INCONCLUSIVE)."""

    model_config = ConfigDict(frozen=True)

    index: int
    finding_id: UUID | None
    check_id: str
    status: FindingStatus


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float
    contributions: tuple[Contribution, ...]
    not_scored: tuple[NotScored, ...]
    config_version: str
    label: str


def score(findings: Sequence[Finding | FindingDraft], config: RiskConfig) -> ScoreResult:
    """contribution = severity_points[severity] * status_multiplier[status] for scored statuses.

    score = min(100, round(sum, 1)). Other statuses are listed in ``not_scored``.
    """
    scored = set(config.scored_statuses)
    points_by_severity = config.severity_points.model_dump()
    multipliers = config.status_multiplier.model_dump()

    contributions: list[Contribution] = []
    not_scored: list[NotScored] = []
    for i, f in enumerate(findings):
        fid = getattr(f, "finding_id", None)
        status = FindingStatus(f.status)
        if status.value in scored:
            contributions.append(
                Contribution(
                    index=i,
                    finding_id=fid,
                    check_id=f.check_id,
                    severity=f.severity,
                    status=status,
                    points=points_by_severity[f.severity] * multipliers[status.value],
                )
            )
        else:
            not_scored.append(NotScored(index=i, finding_id=fid, check_id=f.check_id, status=status))

    total = min(100.0, round(sum(c.points for c in contributions), 1))
    return ScoreResult(
        score=total,
        contributions=tuple(contributions),
        not_scored=tuple(not_scored),
        config_version=config.version,
        label=config.label,
    )
