"""Finding model, status normalisation and correlation keys.

Pure Python: no I/O, no cloud SDK, no web framework. Requirements 3.1-3.6.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentName = Literal[
    "Policy_Eligibility",
    "Duplicate_Detection",
    "Document_Forensics",
    "Medical_Consistency",
    "Billing_Intelligence",
    "Provider_Intelligence",
    "Customer_Behaviour",
    "Identity_Verification",
    "Hospitalisation",
    "Predictive_Fraud",
    "Operational_Intelligence",
]

Severity = Literal["low", "medium", "high"]


class FindingStatus(StrEnum):
    CONFIRMED_RULE_VIOLATION = "CONFIRMED_RULE_VIOLATION"
    POTENTIAL_ANOMALY = "POTENTIAL_ANOMALY"
    INFORMATIONAL = "INFORMATIONAL"
    NOT_CHECKED = "NOT_CHECKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class DetectionMethod(StrEnum):
    RULE = "RULE"
    OCR = "OCR"
    AI = "AI"
    ML = "ML"
    EXTERNAL = "EXTERNAL"


class FactKey(NamedTuple):
    """(fact_type, subject, normalised values). Subject and values are JSON-like."""

    fact_type: str
    subject: Any = ()
    values: Any = ()


# Higher rank wins in dedup.
STATUS_RANK: dict[FindingStatus, int] = {
    FindingStatus.NOT_CHECKED: 0,
    FindingStatus.INFORMATIONAL: 1,
    FindingStatus.INCONCLUSIVE: 2,
    FindingStatus.POTENTIAL_ANOMALY: 3,
    FindingStatus.CONFIRMED_RULE_VIOLATION: 4,
}
SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

_CAPPED_METHODS = frozenset({DetectionMethod.AI, DetectionMethod.ML})


def normalise_status(status: FindingStatus, method: DetectionMethod) -> FindingStatus:
    """AI or ML findings never exceed POTENTIAL_ANOMALY (Req 3.3, 10.6)."""
    status = FindingStatus(status)
    if DetectionMethod(method) in _CAPPED_METHODS and status is FindingStatus.CONFIRMED_RULE_VIOLATION:
        return FindingStatus.POTENTIAL_ANOMALY
    return status


def not_checked_fact_key(check_id: str) -> FactKey:
    return FactKey("not_checked", check_id)


def _json_default(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, (Decimal, UUID)):
        return str(o)
    if isinstance(o, StrEnum):
        return o.value
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, non-ASCII kept."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default
    )


def correlation_key(fact_key: FactKey | tuple) -> str:
    """sha256(fact_type | canonical_json(subject) | canonical_json(values))."""
    fk = FactKey(*fact_key)
    payload = "|".join((fk.fact_type, canonical_json(fk.subject), canonical_json(fk.values)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FindingDraft(BaseModel):
    """Produced by checks, before persistence."""

    use_case_id: int
    check_id: str
    agent: AgentName
    category: str
    severity: Severity
    status: FindingStatus
    explanation: str
    source_document_id: UUID | None = None
    page: int | None = None
    source_field: str | None = None
    extracted_values: dict[str, Any] = Field(default_factory=dict)
    expected_value: dict[str, Any] | str | None = None
    method: DetectionMethod
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_definition: str = ""
    limitations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    next_action: str = ""
    fact_key: FactKey

    @model_validator(mode="after")
    def _normalise(self) -> "FindingDraft":
        normalised = normalise_status(self.status, self.method)
        if normalised is not self.status:
            object.__setattr__(self, "status", normalised)
        if self.status is FindingStatus.NOT_CHECKED:
            object.__setattr__(self, "fact_key", not_checked_fact_key(self.check_id))
        return self


class Finding(FindingDraft):
    """Persisted finding. Immutable after creation (Req 3.6)."""

    model_config = ConfigDict(frozen=True)

    finding_id: UUID
    claim_id: UUID
    run_id: UUID
    created_at: datetime
    rule_version: str
    correlation_key: str
    contributing_checks: list[str] = Field(default_factory=list)
    contributing_sources: list[str] = Field(default_factory=list)
    contributing_use_case_ids: list[int] = Field(default_factory=list)

    @classmethod
    def from_draft(
        cls,
        draft: FindingDraft,
        *,
        finding_id: UUID,
        claim_id: UUID,
        run_id: UUID,
        created_at: datetime,
        rule_version: str,
    ) -> "Finding":
        source = (
            str(draft.source_document_id)
            if draft.source_document_id is not None
            else (draft.source_field or "")
        )
        return cls(
            **draft.model_dump(),
            finding_id=finding_id,
            claim_id=claim_id,
            run_id=run_id,
            created_at=created_at,
            rule_version=rule_version,
            correlation_key=correlation_key(draft.fact_key),
            contributing_checks=[draft.check_id],
            contributing_sources=[source] if source else [],
            contributing_use_case_ids=[draft.use_case_id],
        )
