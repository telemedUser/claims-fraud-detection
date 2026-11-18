"""User (claimant) profile: claim history, submission behaviour and risk signals. Pure, no I/O.

``build_profile`` is shared by the User Profile agent (app/agents/claimant_profile.py), which turns the
signals for the claim being assessed into findings, and the investigator profile page, which shows the
whole history. Input rows come from ``ClaimRepo.claimant_records``; nothing here reads names or dates of
birth, so the same output can be given to the LLM.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "rules" / "user_profile.v1.yaml"


class UserProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    frequency_window_days: int
    frequency_claims: int
    frequency_claims_extreme: int
    amount_spike_multiple: float
    hospital_hopping: int
    similar_amount_spread: float
    late_submission_days: int
    high_amount_short_stay: float
    flagged_decisions: list[str]
    policy_start_days: int
    policy_end_days: int
    policy_end_pattern_claims: int
    escalation_ratio: float
    sum_insured_share: float


@lru_cache(maxsize=1)
def load_config() -> UserProfileConfig:
    return UserProfileConfig.model_validate(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- policy terms

def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


def _d(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def term_for(day: date, valid_from: date | None, valid_to: date | None) -> tuple[date, date] | None:
    """The yearly policy term containing ``day`` (terms repeat on the policy anniversary)."""
    if not valid_from or not valid_to or not day:
        return None
    years = 0
    start, end = valid_from, valid_to
    while day > end and years < 50:
        years += 1
        start, end = _shift_years(valid_from, years), _shift_years(valid_to, years)
    while day < start and years > -50:
        years -= 1
        start, end = _shift_years(valid_from, years), _shift_years(valid_to, years)
    return start, end


def days_to_term_end(day: date | None, policy: dict | None) -> int | None:
    t = term_for(day, _d((policy or {}).get("valid_from")), _d((policy or {}).get("valid_to"))) if day else None
    return (t[1] - day).days if t else None


# ---------------------------------------------------------------- profile

def _overlaps(a: dict, b: dict) -> bool:
    if not a.get("admission") or not b.get("admission"):
        return False
    a_end, b_end = a.get("discharge") or a["admission"], b.get("discharge") or b["admission"]
    return a["admission"] <= b_end and b["admission"] <= a_end


def _sig(code: str, severity: str, detail: str, claims: list[str] | None = None) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "claim_ids": claims or []}


def build_profile(current: dict | None, prior: list[dict], policy: dict | None,
                  cfg: UserProfileConfig | None = None) -> dict:
    """Metrics over all claims and the signals for ``current`` against ``prior`` (oldest first).

    ``current``/``prior`` rows: claim_id, submitted, admission, discharge, amount, hospital_id, doctor_id,
    disease, decision. ``policy``: valid_from, valid_to, sum_insured (or None).
    """
    cfg = cfg or load_config()
    rows = prior + ([current] if current else [])
    sig: list[dict] = []
    policy = policy or {}

    # ---- signals about the claim being assessed
    if current:
        ref = current.get("submitted") or date.today()
        window = [p for p in prior if p.get("submitted") and 0 <= (ref - p["submitted"]).days <= cfg.frequency_window_days]
        if len(window) >= cfg.frequency_claims:
            sig.append(_sig("CLAIM_FREQUENCY", "medium", f"{len(window)} other claims in the last {cfg.frequency_window_days} days.",
                            [p["claim_id"] for p in window]))
        if len(window) >= cfg.frequency_claims_extreme:
            sig.append(_sig("CLAIM_FREQUENCY_EXTREME", "high", f"{cfg.frequency_claims_extreme} or more claims in {cfg.frequency_window_days} days."))

        amounts = [p["amount"] for p in prior if p.get("amount") is not None]
        if amounts:
            avg = sum(amounts) / len(amounts)
            if current["amount"] > cfg.amount_spike_multiple * avg:
                sig.append(_sig("AMOUNT_SPIKE", "medium", f"Claim is more than {cfg.amount_spike_multiple:g}x the claimant's average ({avg:,.0f})."))
        hospitals = {p["hospital_id"] for p in prior if p.get("hospital_id")}
        if len(hospitals) >= cfg.hospital_hopping:
            sig.append(_sig("HOSPITAL_HOPPING", "medium", f"Claimant has used {len(hospitals)} different hospitals."))
        all_amounts = amounts + [current["amount"]]
        if len(all_amounts) >= 3 and max(all_amounts) - min(all_amounts) < cfg.similar_amount_spread * max(all_amounts):
            sig.append(_sig("REPEATED_SIMILAR_AMOUNTS", "medium", "Claim amounts are almost identical across claims."))
        last3 = all_amounts[-3:]
        if len(last3) == 3 and all(last3[i + 1] >= cfg.escalation_ratio * last3[i] for i in range(2)):
            sig.append(_sig("AMOUNT_ESCALATION", "medium",
                            f"Each of the last three claims is at least {cfg.escalation_ratio:g}x the one before "
                            f"({', '.join(f'{a:,.0f}' for a in last3)})."))

        adm, dis = current.get("admission"), current.get("discharge")
        if adm and dis:
            stay = (dis - adm).days
            if stay < 0:
                sig.append(_sig("DATES_INVALID", "high", "Discharge date is before admission date."))
            if (ref - dis).days > cfg.late_submission_days:
                sig.append(_sig("LATE_SUBMISSION", "low", f"Claim submitted over {cfg.late_submission_days} days after discharge."))
            if current["amount"] > cfg.high_amount_short_stay and stay <= 1:
                sig.append(_sig("HIGH_AMOUNT_SHORT_STAY", "medium", "High claim amount for a stay of one day or less."))

        flagged = [p for p in prior if p.get("decision") in cfg.flagged_decisions]
        if flagged:
            sig.append(_sig("PRIOR_FRAUD_DECISION", "high",
                            f"{len(flagged)} earlier claim(s) were denied or referred to the fraud unit by an investigator "
                            f"({', '.join(p['claim_id'] for p in flagged[:3])}).", [p["claim_id"] for p in flagged]))
        same = [p for p in prior if p.get("hospital_id") == current.get("hospital_id") and _overlaps(p, current)]
        if same:
            sig.append(_sig("RESUBMITTED_STAY", "high",
                            f"An earlier claim at the same hospital covers the same stay ({', '.join(p['claim_id'] for p in same[:3])}).",
                            [p["claim_id"] for p in same]))
        other = [p for p in prior if p.get("hospital_id") != current.get("hospital_id") and _overlaps(p, current)]
        if other:
            sig.append(_sig("OVERLAPPING_STAYS_ELSEWHERE", "medium",
                            f"The stay overlaps an earlier claim at another hospital ({', '.join(p['claim_id'] for p in other[:3])}).",
                            [p["claim_id"] for p in other]))

        start = _d(policy.get("valid_from"))
        if adm and start and 0 <= (adm - start).days < cfg.policy_start_days:
            sig.append(_sig("CLAIM_SOON_AFTER_POLICY_START", "medium",
                            f"Admission {(adm - start).days} days after the policy started ({start.isoformat()})."))
        to_end = days_to_term_end(adm, policy)
        if to_end is not None and 0 <= to_end <= cfg.policy_end_days:
            sig.append(_sig("CLAIM_NEAR_POLICY_END", "low", f"Admission {to_end} days before the policy term ends."))
        near_end = [r for r in rows if (lambda n: n is not None and 0 <= n <= cfg.policy_end_days)(days_to_term_end(r.get("admission"), policy))]
        if len(near_end) >= cfg.policy_end_pattern_claims and current in near_end:
            sig.append(_sig("POLICY_END_PATTERN", "medium",
                            f"{len(near_end)} claims were for admissions in the last {cfg.policy_end_days} days of a policy term.",
                            [r["claim_id"] for r in near_end]))

        sum_insured = policy.get("sum_insured")
        term = term_for(adm, start, _d(policy.get("valid_to"))) if adm else None
        if sum_insured and term:
            in_term = [r["amount"] for r in rows if r.get("admission") and term[0] <= r["admission"] <= term[1]]
            used = sum(in_term)
            if used >= cfg.sum_insured_share * sum_insured:
                sig.append(_sig("SUM_INSURED_NEAR_LIMIT", "low",
                                f"Claims in this policy term total {used:,.0f}, {used / sum_insured:.0%} of the sum insured."))

    # ---- metrics over the whole history (for the profile page and the LLM tool)
    lags = [(r["submitted"] - r["discharge"]).days for r in rows if r.get("submitted") and r.get("discharge")]
    decisions: dict[str, int] = {}
    for r in rows:
        key = r.get("decision") or "pending"
        decisions[key] = decisions.get(key, 0) + 1
    today = (current or {}).get("submitted") or date.today()
    total = sum(r["amount"] for r in rows if r.get("amount") is not None)
    metrics = {
        "claims": len(rows),
        "total_claimed": total,
        "average_claim": round(total / len(rows), 2) if rows else 0,
        "largest_claim": max((r["amount"] for r in rows if r.get("amount") is not None), default=0),
        "hospitals": len({r["hospital_id"] for r in rows if r.get("hospital_id")}),
        "doctors": len({r["doctor_id"] for r in rows if r.get("doctor_id")}),
        "claims_last_90_days": sum(1 for r in rows if r.get("submitted") and 0 <= (today - r["submitted"]).days <= 90),
        "claims_last_365_days": sum(1 for r in rows if r.get("submitted") and 0 <= (today - r["submitted"]).days <= 365),
        "average_submission_lag_days": round(sum(lags) / len(lags), 1) if lags else None,
        "decisions": decisions,
        "flagged_claims": sum(1 for r in rows if r.get("decision") in cfg.flagged_decisions),
        "claims_near_policy_end": sum(1 for r in rows if (lambda n: n is not None and 0 <= n <= cfg.policy_end_days)(
            days_to_term_end(r.get("admission"), policy))),
        "first_claim": min((r["submitted"] for r in rows if r.get("submitted")), default=None),
        "last_claim": max((r["submitted"] for r in rows if r.get("submitted")), default=None),
    }
    return {"metrics": metrics, "signals": sig, "config_version": cfg.version}
