"""Risk scoring configuration: pydantic model with YAML load and dump."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "rules" / "risk_scoring.v1.yaml"

ScoredStatus = Literal["CONFIRMED_RULE_VIOLATION", "POTENTIAL_ANOMALY"]


class Bands(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_at: float
    investigate_at: float

    @model_validator(mode="after")
    def _check_order(self) -> "Bands":
        if not (0 < self.review_at < self.investigate_at <= 100):
            raise ValueError("bands must satisfy 0 < review_at < investigate_at <= 100")
        return self


class SeverityPoints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float = Field(ge=0)
    medium: float = Field(ge=0)
    high: float = Field(ge=0)


class StatusMultiplier(BaseModel):
    """Only these two statuses are scored; all others contribute 0."""

    model_config = ConfigDict(extra="forbid")

    CONFIRMED_RULE_VIOLATION: float = Field(ge=0)
    POTENTIAL_ANOMALY: float = Field(ge=0)


class DocModificationGapHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice: float = Field(gt=0)
    discharge_summary: float = Field(gt=0)
    default: float = Field(gt=0)


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_purchase_gap_days: int = Field(ge=0)
    preauth_overrun_pct: float = Field(ge=0)
    invoice_total_tolerance: float = Field(ge=0)
    doc_modification_gap_hours: DocModificationGapHours
    provider_volume_multiple: float = Field(gt=0)


class LlmScoring(BaseModel):
    """How LLM observations add to the score. LLM findings count as POTENTIAL_ANOMALY, so they use that status
    multiplier, and they are capped per agent and in total so the rules stay the main signal."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_points_per_agent: float = Field(default=20.0, ge=0)
    max_points_total: float = Field(default=30.0, ge=0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    label: str
    severity_points: SeverityPoints
    status_multiplier: StatusMultiplier
    bands: Bands
    thresholds: Thresholds
    gst_exempt_categories: list[str] = Field(default_factory=list)
    llm: LlmScoring = Field(default_factory=LlmScoring)

    @property
    def scored_statuses(self) -> tuple[str, ...]:
        return tuple(StatusMultiplier.model_fields)


def parse_risk_config(text: str) -> RiskConfig:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("risk config YAML must be a mapping")
    return RiskConfig.model_validate(data)


def load_risk_config(path: str | Path | None = None) -> RiskConfig:
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return parse_risk_config(p.read_text(encoding="utf-8"))


def dump_risk_config(config: RiskConfig) -> str:
    return yaml.safe_dump(config.model_dump(mode="python"), sort_keys=False, allow_unicode=False)
