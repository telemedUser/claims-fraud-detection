from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]


class LineItem(BaseModel):
    description: str
    amount: float


class Invoice(BaseModel):
    invoice_number: str
    invoice_date: date
    line_items: list[LineItem]
    total: float
    tax_id: Optional[str] = None  # GST / registration number printed on invoice


class Claim(BaseModel):
    claim_id: str
    claimant_id: str
    claimant_name: str
    hospital_id: str
    doctor_id: str
    diagnosis: str
    admission_date: date
    discharge_date: date
    claimed_amount: float
    submitted_on: date = Field(default_factory=date.today)
    invoice: Invoice
    policy_number: Optional[str] = None
    disease_id: Optional[str] = None


DocType = Literal["medical_bill", "prescription", "medical_report", "lab_report", "payment_receipt", "other"]


class DocumentInfo(BaseModel):
    filename: str
    content_type: str
    size: int
    sha256: str
    data: bytes = b""
    doc_type: DocType = "other"


class ClaimSubmission(BaseModel):
    """What the customer journey sends. Claimant identity comes from the policy, not the client."""
    policy_number: str = Field(max_length=40)
    date_of_birth: date
    hospital_id: str = Field(max_length=20)
    doctor_id: str = Field(max_length=20)
    disease_id: str = Field(max_length=40)
    admission_date: date
    discharge_date: date
    claimed_amount: float = Field(gt=0, le=10_000_000)
    invoice: Invoice


class Finding(BaseModel):
    code: str
    severity: Severity
    detail: str
    source: Literal["rule", "llm"] = "rule"


class AgentResult(BaseModel):
    agent: str
    score: float  # 0 (clean) .. 100 (very suspicious)
    findings: list[Finding] = []
    rule_score: Optional[float] = None  # score before any LLM contribution
    llm_used: bool = False
    llm_points: float = 0
    reasoning: str = ""
    tool_calls: list[str] = []
    llm_model: Optional[str] = None


class AgentTrace(BaseModel):
    agent: str
    weight: float
    score: float
    weighted_contribution: float
    started_at_ms: float  # offset from orchestration start
    duration_ms: float
    finding_count: int


class Orchestration(BaseModel):
    agents_run_in_parallel: bool
    total_duration_ms: float
    sum_of_agent_durations_ms: float
    traces: list[AgentTrace]
    weighted_score: float
    peak_agent: str
    peak_score: float
    peak_floor: float  # 0.8 x peak score
    final_score: float
    score_rule: str
    thresholds: dict[str, int]
    decision_reason: str


class FraudAssessment(BaseModel):
    claim_id: str
    risk_score: float
    decision: Literal["auto_approve", "manual_review", "investigate"]
    agent_results: list[AgentResult]
    orchestration: Orchestration
    summary: str
    # Routing recommendation only; `decision` is kept for the frontend (auto_approve = low-risk queue).
    recommended_queue: Literal["low", "manual_review", "investigate"] = "low"
    needs_human_review: bool = False
    score_label: str = ""
    claim_status: str = "ASSESSED"
