"""Provider Profile thresholds: pydantic model loaded from app/rules/provider_profile.v1.yaml. Pure, no I/O
beyond reading the YAML file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "rules" / "provider_profile.v1.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Volume(_Strict):
    window_days: int = Field(gt=0)
    min_claims: int = Field(ge=1)


class DoctorVolume(_Strict):
    high_per_month: float = Field(gt=0)


class AmountOutlier(_Strict):
    z_threshold: float = Field(gt=0)
    min_samples_disease: int = Field(ge=2)
    min_samples_hospital: int = Field(ge=2)


class PeerCost(_Strict):
    min_peer_samples: int = Field(ge=2)
    multiple_of_peer_median: float = Field(gt=1)


class FraudRate(_Strict):
    threshold: float = Field(gt=0, lt=1)
    prior_weight: float = Field(ge=0)
    flagged_decisions: list[str]
    window_days: int = Field(gt=0)


class SimilarBills(_Strict):
    window_days: int = Field(gt=0)
    tolerance_pct: float = Field(gt=0)
    min_other_claimants: int = Field(ge=1)


class Documents(_Strict):
    name_match_threshold: float = Field(gt=0, le=1)


class ProviderConfig(_Strict):
    version: str = Field(min_length=1)
    volume: Volume
    doctor_volume: DoctorVolume
    amount_outlier: AmountOutlier
    peer_cost: PeerCost
    fraud_rate: FraudRate
    similar_bills: SimilarBills
    documents: Documents
    many_hospitals: int = Field(ge=2)
    new_hospital_years: float = Field(ge=0)


def parse_provider_config(text: str) -> ProviderConfig:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("provider config YAML must be a mapping")
    return ProviderConfig.model_validate(data)


@lru_cache(maxsize=4)
def load_provider_config(path: str | None = None) -> ProviderConfig:
    p = Path(path) if path is not None else DEFAULT_PATH
    return parse_provider_config(p.read_text(encoding="utf-8"))
