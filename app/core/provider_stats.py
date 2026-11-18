"""Statistics for provider profiles computed from claims data. Pure, no I/O."""
from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Baseline:
    """Amount baseline used for an outlier test, with where it came from (shown in the finding)."""

    mean: float
    std: float
    n: int
    basis: str  # "same-diagnosis claims at this hospital" | "all claims at this hospital" | "registry figures"


def mean_std(values: list[float]) -> tuple[float, float]:
    """Mean and sample standard deviation. Needs at least two values."""
    if len(values) < 2:
        raise ValueError("need at least two values")
    return statistics.fmean(values), statistics.stdev(values)


MIN_RELATIVE_SPREAD = 0.10  # computed spread is at least 10% of the mean


def _spread(mean: float, std: float) -> float:
    """Near-identical amounts (package prices) give a tiny standard deviation, which would make any modest
    difference look extreme. The spread is floored at ``MIN_RELATIVE_SPREAD`` of the mean."""
    return max(std, MIN_RELATIVE_SPREAD * abs(mean))


def choose_baseline(disease_amounts: list[float], hospital_amounts: list[float], registry_mean: float,
                    registry_std: float, min_disease: int, min_hospital: int) -> Baseline:
    """Most specific baseline with enough data: same diagnosis, then whole hospital, then registry figures."""
    if len(disease_amounts) >= min_disease:
        m, s = mean_std(disease_amounts)
        return Baseline(m, _spread(m, s), len(disease_amounts), "same-diagnosis claims at this hospital")
    if len(hospital_amounts) >= min_hospital:
        m, s = mean_std(hospital_amounts)
        return Baseline(m, _spread(m, s), len(hospital_amounts), "all claims at this hospital")
    return Baseline(float(registry_mean), float(registry_std), 0, "registry figures")


def zscore(x: float, mean: float, std: float) -> float:
    """Standard score; a zero or tiny spread is treated as 1 so a flat baseline cannot divide by zero."""
    return (x - mean) / max(std, 1.0)


def smoothed_rate(prior_rate: float, prior_weight: float, flagged: int, decided: int) -> float:
    """Registry rate blended with observed investigator outcomes.

    The prior counts as ``prior_weight`` decided claims, so a handful of decisions moves the rate a little
    and many decisions dominate it: (prior * w + flagged) / (w + decided).
    """
    total = prior_weight + decided
    if total <= 0:
        return 0.0
    return (prior_rate * prior_weight + flagged) / total


def volume_surge(count: int, baseline: float | None, multiple: float, min_claims: int) -> bool:
    """True when the window count is at least ``min_claims`` and above ``multiple`` x baseline."""
    if baseline is None or baseline <= 0:
        return False
    return count >= min_claims and count > multiple * baseline
