"""ORM models for every table in design.md "Data Models".

Primary keys are UUIDv4 (Req 16.5). JSON columns are ``JSON`` with a ``JSONB`` variant on
PostgreSQL. Append-only triggers on ``findings`` and ``audit_events`` are PostgreSQL-only and are
added by the Alembic migration (task 8.3). ``audit_events.seq`` is assigned by the audit
repository under the advisory lock so the chain stays linear on every backend.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")
Money = Numeric(14, 2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=_uuid)


def _fk(target: str, *, nullable: bool = False, index: bool = True) -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey(target), nullable=nullable, index=index)


def _ts(*, default: bool = False, nullable: bool = True) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_now if default else None,
                         nullable=False if default else nullable)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


# --------------------------------------------------------------------------- reference data
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30))  # Investigator, Ops_Manager, Fraud_Team, Administrator
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[uuid.UUID] = _pk()
    policy_number: Mapped[str] = mapped_column(String(64), unique=True)
    plan: Mapped[str | None] = mapped_column(String(100))
    inception_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    sum_insured: Mapped[Decimal | None] = mapped_column(Money)
    waiting_period_days: Mapped[int | None] = mapped_column(Integer)
    exclusions: Mapped[Any] = mapped_column(JSONType, default=list)
    dob: Mapped[date | None] = mapped_column(Date)  # lookup only
    holder_name: Mapped[str | None] = mapped_column(String(200))
    network_hospital_ids: Mapped[Any] = mapped_column(JSONType, nullable=True)  # provider codes
    covered_disease_ids: Mapped[Any] = mapped_column(JSONType, nullable=True)  # disease catalogue ids


class Member(Base):
    __tablename__ = "members"
    id: Mapped[uuid.UUID] = _pk()
    policy_id: Mapped[uuid.UUID] = _fk("policies.id")
    code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)  # short claimant id, e.g. "U001"
    name: Mapped[str | None] = mapped_column(String(200))
    relation: Mapped[str | None] = mapped_column(String(50))
    dob: Mapped[date | None] = mapped_column(Date)


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(300))
    phone: Mapped[str | None] = mapped_column(String(50))
    specialties: Mapped[Any] = mapped_column(JSONType, nullable=True)
    registered: Mapped[bool] = mapped_column(Boolean, default=True)
    years_active: Mapped[float | None] = mapped_column(Float)
    avg_claim: Mapped[Decimal | None] = mapped_column(Money)
    std_claim: Mapped[Decimal | None] = mapped_column(Money)
    flagged_claims_ratio: Mapped[float | None] = mapped_column(Float)
    baseline_monthly_claims: Mapped[float | None] = mapped_column(Float)
    gstin: Mapped[str | None] = mapped_column(String(15))
    reference_source: Mapped[str | None] = mapped_column(String(200))


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[uuid.UUID] = _pk()
    provider_id: Mapped[uuid.UUID] = _fk("providers.id")  # primary hospital; all hospitals are in doctor_affiliations
    code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)  # short doctor id, e.g. "D001"
    name: Mapped[str] = mapped_column(String(200))
    qualification: Mapped[str | None] = mapped_column(String(200))
    registration_no: Mapped[str | None] = mapped_column(String(64))
    licence_valid: Mapped[bool | None] = mapped_column(Boolean)
    specialities: Mapped[Any] = mapped_column(JSONType, default=list)
    claims_per_month: Mapped[float | None] = mapped_column(Float)
    flagged_claims_ratio: Mapped[float | None] = mapped_column(Float)


class DoctorAffiliation(Base):
    """A doctor can be attached to several hospitals; ``position`` keeps the listed order."""

    __tablename__ = "doctor_affiliations"
    doctor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("doctors.id"), primary_key=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("providers.id"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- claims
class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = _pk()
    claim_ref: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)  # external id, e.g. "CLM-..."
    claimant_ref: Mapped[str | None] = mapped_column(String(64), index=True)  # claimant id the history is keyed by
    policy_id: Mapped[uuid.UUID | None] = _fk("policies.id", nullable=True)
    member_id: Mapped[uuid.UUID | None] = _fk("members.id", nullable=True)
    provider_id: Mapped[uuid.UUID | None] = _fk("providers.id", nullable=True)
    doctor_id: Mapped[uuid.UUID | None] = _fk("doctors.id", nullable=True)
    disease_code: Mapped[str | None] = mapped_column(String(32))
    admission_date: Mapped[date | None] = mapped_column(Date)
    discharge_date: Mapped[date | None] = mapped_column(Date)
    claimed_amount: Mapped[Decimal | None] = mapped_column(Money)
    submitted_on: Mapped[datetime | None] = _ts()
    channel: Mapped[str] = mapped_column(String(20), default="investigator")  # investigator | customer
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    preauth_amount: Mapped[Decimal | None] = mapped_column(Money)
    retention_until: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = _ts(default=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="claim")


class ClaimChange(Base):
    __tablename__ = "claim_changes"
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    field: Mapped[str] = mapped_column(String(100))
    before: Mapped[Any] = mapped_column(JSONType, nullable=True)
    after: Mapped[Any] = mapped_column(JSONType, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    changed_at: Mapped[datetime] = _ts(default=True)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("claim_id", "sha256", name="uq_documents_claim_sha256"),)
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    doc_type: Mapped[str | None] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int | None] = mapped_column(Integer)
    original_name_ref: Mapped[str | None] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = _ts(default=True)

    claim: Mapped[Claim] = relationship(back_populates="documents")


class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    id: Mapped[uuid.UUID] = _pk()
    document_id: Mapped[uuid.UUID] = _fk("documents.id")
    adapter: Mapped[str] = mapped_column(String(50))
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    fields: Mapped[Any] = mapped_column(JSONType, default=dict)
    metadata_: Mapped[Any] = mapped_column("metadata", JSONType, default=dict)


class NormalisedFact(Base):
    __tablename__ = "normalised_facts"
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    field: Mapped[str] = mapped_column(String(100))
    original_value: Mapped[str | None] = mapped_column(Text)
    normalised_value: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    source_field: Mapped[str | None] = mapped_column(String(100))


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    gstin: Mapped[str | None] = mapped_column(String(15))
    stated_total: Mapped[Decimal | None] = mapped_column(Money)
    service_category: Mapped[str | None] = mapped_column(String(100))
    authenticity_state: Mapped[str | None] = mapped_column(String(60))


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    id: Mapped[uuid.UUID] = _pk()
    invoice_id: Mapped[uuid.UUID] = _fk("invoices.id")
    description: Mapped[str | None] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Money)
    category: Mapped[str | None] = mapped_column(String(100))


# --------------------------------------------------------------------------- processing
class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(String(20))  # rules | prompt | scoring
    version: Mapped[str] = mapped_column(String(50))
    checksum: Mapped[str | None] = mapped_column(String(64))


class RiskConfigRow(Base):
    __tablename__ = "risk_configs"
    id: Mapped[uuid.UUID] = _pk()
    version: Mapped[str] = mapped_column(String(50), unique=True)
    body: Mapped[Any] = mapped_column(JSONType)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = _ts(default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (UniqueConstraint("claim_id", "idempotency_key", name="uq_runs_claim_idempotency"),)
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    retry_of_run_id: Mapped[uuid.UUID | None] = _fk("processing_runs.id", nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    rule_version: Mapped[str | None] = mapped_column(String(50))
    config_version: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = _ts()
    finished_at: Mapped[datetime | None] = _ts()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[Any] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime | None] = _ts()
    lease_expires_at: Mapped[datetime | None] = _ts()
    leased_by: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), index=True)


class AgentExecution(Base):
    __tablename__ = "agent_executions"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = _fk("processing_runs.id")
    agent: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(20))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = _ts()
    ended_at: Mapped[datetime | None] = _ts()
    error: Mapped[str | None] = mapped_column(Text)


class FindingRow(Base):
    """Append-only (PostgreSQL trigger blocks UPDATE and DELETE)."""

    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    run_id: Mapped[uuid.UUID] = _fk("processing_runs.id")
    use_case_id: Mapped[str | None] = mapped_column(String(20))
    check_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(50))
    agent: Mapped[str | None] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = _fk("documents.id", nullable=True)
    page: Mapped[int | None] = mapped_column(Integer)
    source_field: Mapped[str | None] = mapped_column(String(100))
    extracted_values: Mapped[Any] = mapped_column(JSONType, nullable=True)
    expected_value: Mapped[Any] = mapped_column(JSONType, nullable=True)
    method: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    confidence_definition: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[Any] = mapped_column(JSONType, nullable=True)
    alternatives: Mapped[Any] = mapped_column(JSONType, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text)
    correlation_key: Mapped[str | None] = mapped_column(String(200), index=True)
    contributing_checks: Mapped[Any] = mapped_column(JSONType, nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = _ts(default=True)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("processing_runs.id"), unique=True)
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(20))
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    config_version: Mapped[str | None] = mapped_column(String(50))
    rule_version: Mapped[str | None] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(100))


class RiskContribution(Base):
    __tablename__ = "risk_contributions"
    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("risk_assessments.id"), primary_key=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("findings.id"), primary_key=True)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    scored: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- verification
class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    id: Mapped[uuid.UUID] = _pk()
    invoice_id: Mapped[uuid.UUID] = _fk("invoices.id")
    adapter: Mapped[str] = mapped_column(String(50))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    request: Mapped[Any] = mapped_column(JSONType, default=dict)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = _ts(default=True)


class VerificationResponse(Base):
    __tablename__ = "verification_responses"
    id: Mapped[uuid.UUID] = _pk()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("verification_requests.id"), unique=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    response: Mapped[Any] = mapped_column(JSONType, default=dict)
    state: Mapped[str | None] = mapped_column(String(20))
    received_at: Mapped[datetime] = _ts(default=True)


# --------------------------------------------------------------------------- decisions, feedback
class InvestigatorDecision(Base):
    __tablename__ = "investigator_decisions"
    id: Mapped[uuid.UUID] = _pk()
    claim_id: Mapped[uuid.UUID] = _fk("claims.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    risk_assessment_id: Mapped[uuid.UUID | None] = _fk("risk_assessments.id", nullable=True)
    created_at: Mapped[datetime] = _ts(default=True)


class FindingFeedback(Base):
    __tablename__ = "finding_feedback"
    id: Mapped[uuid.UUID] = _pk()
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    verdict: Mapped[str] = mapped_column(String(20))  # false_positive | confirmed
    rule_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = _ts(default=True)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID | None] = _fk("processing_runs.id", nullable=True)
    adapter: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    field_names: Mapped[Any] = mapped_column(JSONType, default=list)  # names only, never values
    outcome: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = _ts(default=True)


class AuditEvent(Base):
    """Append-only hash chain (PostgreSQL trigger blocks UPDATE and DELETE)."""

    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = _pk()
    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    ts: Mapped[datetime] = _ts(default=True)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[Any] = mapped_column(JSONType, default=dict)  # no PII
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
