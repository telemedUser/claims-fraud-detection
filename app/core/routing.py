"""Route a risk score to a queue band. Requirements 5.4-5.6.

The score is an ordering signal, not a probability (see ``SCORE_LABEL``).
"""
from __future__ import annotations

from typing import Literal

from app.core.risk_config import Bands

SCORE_LABEL = "Ordering signal, not a probability"

Route = Literal["low", "manual_review", "investigate"]


def route(score: float, bands: Bands) -> Route:
    """score < review_at -> low; < investigate_at -> manual_review; else investigate."""
    if score < bands.review_at:
        return "low"
    if score < bands.investigate_at:
        return "manual_review"
    return "investigate"
