"""Provider Profile agent: hospital and doctor risk profile and cross-checks.

Documented in docs/agents/provider_profile.md (checks, data sources, workflow, limitations).

Four groups of deterministic checks, all in this module:
  1. Registry checks      - the claim against the stored hospital and doctor records, dated to the admission.
  2. Behaviour checks     - a profile computed from claims data and investigator decisions (volume, amounts,
                            peers, flag rate, near-identical bills, capacity, same-day presence elsewhere).
  3. Specialty fit        - doctor and hospital specialties against the diagnosis.
  4. Document checks      - hospital name, GSTIN, doctor name and registration number printed on the uploaded
                            documents against the registry (text from the extraction adapter; no OCR).

No LLM is called here. Thresholds come from app/rules/provider_profile.v1.yaml. The registry is simulated
seed data, so findings say "on record" and never "verified".
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, time, timedelta, timezone

from app.agents.base import Agent
from app.core.provider_config import ProviderConfig, load_provider_config
from app.core.provider_stats import choose_baseline, smoothed_rate, volume_surge, zscore
from app.core.risk_config import load_risk_config
from app.core.text_match import find_gstins, find_registration_numbers, name_match_score, normalise_id
from app.core.validators import gstin as gstin_validator
from app.db.repos import open_repos
from app.models import Claim, DocumentInfo, Finding

DOCTOR_DOC_TYPES = ("prescription", "medical_report")


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _active_on(day: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= day) and (end is None or day <= end)


class ProviderProfileAgent(Agent):
    """Builds hospital and doctor risk profiles and checks the claim against them."""
    name = "provider_profile"

    async def analyze(self, claim: Claim, documents: list[DocumentInfo]):
        cfg = load_provider_config()
        volume_multiple = load_risk_config().thresholds.provider_volume_multiple
        with open_repos() as repos:
            h = repos.hospital(claim.hospital_id)
            d = repos.doctor(claim.doctor_id)
            dz = repos.disease(claim.disease_id)
            act = _activity(repos, claim, h, d, cfg)
            names = repos.providers.provider_names() if documents else {}

        f: list[Finding] = []
        f += _registry_checks(claim, h, d, cfg)
        f += _behaviour_checks(claim, h, d, act, cfg, volume_multiple)
        f += _fit_checks(h, d, dz)
        f += _document_checks(claim, h, d, documents, names, cfg)
        return self.result(f)


# ---------------------------------------------------------------- computed profile (claims data)

def _activity(repos, claim: Claim, h: dict | None, d: dict | None, cfg: ProviderConfig) -> dict:
    """Everything the behaviour checks need from the claims tables, in one session."""
    ref = claim.submitted_on or date.today()
    until = datetime.combine(ref + timedelta(days=1), time.min, tzinfo=timezone.utc)
    vol_since = until - timedelta(days=cfg.volume.window_days)
    dec_since = until - timedelta(days=cfg.fraud_rate.window_days)
    sim_since = until - timedelta(days=cfg.similar_bills.window_days)
    a = repos.activity
    cid = claim.claim_id
    out: dict = {}
    if h:
        code = claim.hospital_id
        out["hospital_count"] = a.provider_claim_count(code, vol_since, until, cid)
        out["disease_amounts"] = a.provider_amounts(code, claim.disease_id, cid) if claim.disease_id else []
        out["hospital_amounts"] = a.provider_amounts(code, None, cid)
        out["peer_amounts"] = a.peer_amounts(claim.disease_id, code, cid) if claim.disease_id else []
        out["hospital_decisions"] = a.decision_counts(cfg.fraud_rate.flagged_decisions, dec_since, hospital=code)
        out["overlapping_stays"] = a.overlapping_stays(code, claim.admission_date, cid)
    if d:
        did = claim.doctor_id
        out["doctor_count"] = a.doctor_claim_count(did, vol_since, until, cid)
        out["doctor_decisions"] = a.decision_counts(cfg.fraud_rate.flagged_decisions, dec_since, doctor=did)
        out["doctor_same_day"] = a.doctor_admissions_on(did, claim.admission_date, cid)
        out["similar_claimants"] = a.doctor_similar_amount_claimants(
            did, claim.claimed_amount, cfg.similar_bills.tolerance_pct, sim_since, claim.claimant_id, cid)
    return out


# ---------------------------------------------------------------- 1. registry checks

def _registry_checks(claim: Claim, h: dict | None, d: dict | None, cfg: ProviderConfig) -> list[Finding]:
    f: list[Finding] = []
    adm = claim.admission_date

    if not h:
        f.append(Finding(code="HOSPITAL_UNKNOWN", severity="high", detail="Hospital not found in registry."))
    else:
        if not h["registered"]:
            f.append(Finding(code="HOSPITAL_UNREGISTERED", severity="high", detail=f"{h['name']} is not a registered facility."))
        if h["years_active"] < cfg.new_hospital_years:
            f.append(Finding(code="HOSPITAL_NEW", severity="low",
                             detail=f"Hospital has under {cfg.new_hospital_years:g} years of claim history."))
        reg_gstin = normalise_id(h["tax_id"])
        entered = normalise_id(claim.invoice.tax_id)
        if reg_gstin and entered and entered != reg_gstin:
            f.append(Finding(code="TAX_ID_MISMATCH", severity="high",
                             detail="Tax ID on invoice does not match the hospital registry."))
        if reg_gstin:
            if not gstin_validator.is_valid(reg_gstin):
                f.append(Finding(code="REGISTRY_GSTIN_INVALID", severity="low",
                                 detail=f"The GSTIN on record for {h['name']} fails the GSTIN format or check-digit test."))
            elif h.get("state_code") and reg_gstin[:2] != h["state_code"]:
                f.append(Finding(code="GSTIN_STATE_MISMATCH", severity="medium",
                                 detail=f"The GSTIN on record has state code {reg_gstin[:2]}, but the hospital's address is in "
                                        f"state {h['state_code']}."))
        start, end = _d(h.get("empanelled_from")), _d(h.get("empanelled_to"))
        if start and not _active_on(adm, start, end):
            period = f"{start.isoformat()} to {end.isoformat() if end else 'open'}"
            f.append(Finding(code="HOSPITAL_NOT_EMPANELLED_ON_DATE", severity="medium",
                             detail=f"Admission on {adm.isoformat()} is outside the hospital's network period ({period})."))

    if not d:
        f.append(Finding(code="DOCTOR_UNKNOWN", severity="high", detail="Doctor not found in registry."))
        return f
    if not d["license_valid"]:
        f.append(Finding(code="DOCTOR_LICENSE_INVALID", severity="high", detail=f"{d['name']} has no valid license on record."))
    else:
        expiry = _d(d.get("licence_valid_to"))
        if expiry and adm > expiry:
            f.append(Finding(code="DOCTOR_LICENCE_EXPIRED", severity="high",
                             detail=f"{d['name']}'s licence on record expired on {expiry.isoformat()}, before the admission "
                                    f"on {adm.isoformat()}."))
    if not d.get("registration_no"):
        f.append(Finding(code="DOCTOR_REGISTRATION_MISSING", severity="low",
                         detail=f"No medical council registration number is on record for {d['name']}."))

    affs = d.get("affiliation_dates") or {}  # hospital id -> (start, end) ISO dates

    def on_date(code: str) -> bool:
        start, end = affs.get(code, (None, None))
        return _active_on(adm, _d(start), _d(end))

    if claim.hospital_id not in d["hospital_ids"]:
        f.append(Finding(code="DOCTOR_NOT_AFFILIATED", severity="high",
                         detail="Doctor is not affiliated with the claimed hospital."))
    elif not on_date(claim.hospital_id):
        start, end = affs[claim.hospital_id]
        f.append(Finding(code="DOCTOR_AFFILIATION_INACTIVE", severity="high",
                         detail=f"{d['name']}'s affiliation with the hospital ran {start or '?'} to {end or 'open'}, "
                                f"which does not cover the admission on {adm.isoformat()}."))
    active = [code for code in d["hospital_ids"] if on_date(code)]
    if len(active) >= cfg.many_hospitals:
        f.append(Finding(code="DOCTOR_MANY_HOSPITALS", severity="low",
                         detail=f"Doctor is attached to {len(active)} hospitals on the admission date."))
    return f


# ---------------------------------------------------------------- 2. behaviour checks

def _rate_detail(prior: float, decided: int, rate: float) -> str:
    if decided == 0:
        return f"registry figure {_pct(prior)}; no investigator decisions yet"
    return f"registry figure {_pct(prior)} blended with {decided} investigator decision(s), estimate {_pct(rate)}"


def _behaviour_checks(claim: Claim, h: dict | None, d: dict | None, act: dict, cfg: ProviderConfig,
                      volume_multiple: float) -> list[Finding]:
    f: list[Finding] = []
    window = cfg.volume.window_days
    fr = cfg.fraud_rate

    if h:
        decided, flagged = act["hospital_decisions"]
        rate = smoothed_rate(h["flagged_claims_ratio"], fr.prior_weight, flagged, decided)
        if rate > fr.threshold:
            f.append(Finding(code="HOSPITAL_HIGH_FRAUD_RATE", severity="medium",
                             detail=f"About {_pct(rate)} of this hospital's past claims were flagged "
                                    f"({_rate_detail(h['flagged_claims_ratio'], decided, rate)})."))

        base = choose_baseline(act["disease_amounts"], act["hospital_amounts"], h["avg_claim"], h["std_claim"],
                               cfg.amount_outlier.min_samples_disease, cfg.amount_outlier.min_samples_hospital)
        z = zscore(claim.claimed_amount, base.mean, base.std)
        if z > cfg.amount_outlier.z_threshold:
            n = f", {base.n} claims" if base.n else ""
            f.append(Finding(code="AMOUNT_OUTLIER_FOR_HOSPITAL", severity="medium",
                             detail=f"Claim is {z:.1f} standard deviations above the hospital average "
                                    f"({base.mean:,.0f}; {base.basis}{n})."))

        baseline = h.get("baseline_monthly_claims")
        expected = baseline * window / 30 if baseline else None
        if volume_surge(act["hospital_count"], expected, volume_multiple, cfg.volume.min_claims):
            f.append(Finding(code="HOSPITAL_VOLUME_SURGE", severity="medium",
                             detail=f"{act['hospital_count']} claims at this hospital in the last {window} days against a "
                                    f"baseline of about {expected:.0f} (over {volume_multiple:g}x)."))

        peers = act["peer_amounts"]
        if len(peers) >= cfg.peer_cost.min_peer_samples:
            median = statistics.median(peers)
            if median > 0 and claim.claimed_amount > cfg.peer_cost.multiple_of_peer_median * median:
                f.append(Finding(code="PEER_COST_OUTLIER", severity="medium",
                                 detail=f"Claim is {claim.claimed_amount / median:.1f}x the median ({median:,.0f}) of "
                                        f"{len(peers)} claims for the same diagnosis at other hospitals."))

        beds = h.get("bed_count")
        if beds and act["overlapping_stays"] + 1 > beds:
            f.append(Finding(code="HOSPITAL_OVER_CAPACITY", severity="medium",
                             detail=f"{act['overlapping_stays'] + 1} admissions overlap {claim.admission_date.isoformat()} "
                                    f"at a hospital with {beds} beds on record."))

    if d:
        decided, flagged = act["doctor_decisions"]
        rate = smoothed_rate(d["flagged_claims_ratio"], fr.prior_weight, flagged, decided)
        if rate > fr.threshold:
            f.append(Finding(code="DOCTOR_HIGH_FRAUD_RATE", severity="medium",
                             detail=f"About {_pct(rate)} of this doctor's claims were flagged "
                                    f"({_rate_detail(d['flagged_claims_ratio'], decided, rate)})."))

        observed = act["doctor_count"] * 30 / window
        volume = max(d["claims_per_month"], observed)
        if volume > cfg.doctor_volume.high_per_month:
            f.append(Finding(code="DOCTOR_HIGH_VOLUME", severity="medium",
                             detail=f"Doctor appears on about {volume:.0f} claims per month (registry figure "
                                    f"{d['claims_per_month']:g}, observed {observed:.0f})."))
        expected = d["claims_per_month"] * window / 30 if d["claims_per_month"] else None
        if volume_surge(act["doctor_count"], expected, volume_multiple, cfg.volume.min_claims):
            f.append(Finding(code="DOCTOR_VOLUME_SURGE", severity="medium",
                             detail=f"{act['doctor_count']} claims by this doctor in the last {window} days against a "
                                    f"baseline of about {expected:.0f} (over {volume_multiple:g}x)."))

        if act["similar_claimants"] >= cfg.similar_bills.min_other_claimants:
            f.append(Finding(code="DOCTOR_SIMILAR_BILLS", severity="medium",
                             detail=f"{act['similar_claimants']} other patients of this doctor claimed within "
                                    f"{cfg.similar_bills.tolerance_pct:g}% of {claim.claimed_amount:,.0f} in the last "
                                    f"{cfg.similar_bills.window_days} days."))

        city = (h or {}).get("city")
        elsewhere = [x for x in act["doctor_same_day"] if city and x["city"] and x["city"] != city]
        if elsewhere:
            where = "; ".join(f"{x['hospital']} ({x['city']})" for x in elsewhere[:3])
            f.append(Finding(code="DOCTOR_SAME_DAY_OTHER_CITY", severity="medium",
                             detail=f"The same doctor admitted other patients on {claim.admission_date.isoformat()} "
                                    f"in another city: {where}."))
    return f


# ---------------------------------------------------------------- 3. specialty fit

def _fit_checks(h: dict | None, d: dict | None, dz: dict | None) -> list[Finding]:
    f: list[Finding] = []
    wanted = set((dz or {}).get("specialties") or [])
    if not wanted:
        return f
    if d and d.get("specialty") and d["specialty"] not in wanted:
        f.append(Finding(code="DOCTOR_SPECIALTY_MISMATCH", severity="medium",
                         detail=f"{d['name']} ({d['specialty']}) is not in a specialty that usually treats "
                                f"{dz['name']} ({', '.join(sorted(wanted))})."))
    if h and h.get("specialties") and not wanted & set(h["specialties"]):
        f.append(Finding(code="HOSPITAL_SPECIALTY_NOT_OFFERED", severity="medium",
                         detail=f"{h['name']} has no department on record for {dz['name']} "
                                f"(needs {', '.join(sorted(wanted))})."))
    return f


# ---------------------------------------------------------------- 4. document checks

def _document_texts(documents: list[DocumentInfo]) -> list[tuple[DocumentInfo, str]]:
    """Text of each document from the extraction adapter (shared helper in app/core/doc_text.py)."""
    from app.core.doc_text import document_texts

    return document_texts(documents)


def _document_checks(claim: Claim, h: dict | None, d: dict | None, documents: list[DocumentInfo],
                     names: dict[str, str], cfg: ProviderConfig) -> list[Finding]:
    f: list[Finding] = []
    if not documents:
        return f
    texts = _document_texts(documents)
    if not texts:
        f.append(Finding(code="PROVIDER_DOCS_NOT_CHECKED", severity="low",
                         detail="The uploaded documents have no machine-readable text, so the hospital and doctor "
                                "details on them were not compared with the registry."))
        return f
    threshold = cfg.documents.name_match_threshold
    all_text = "\n".join(t for _, t in texts)

    if h:
        printed = find_gstins(all_text)
        reg_gstin = normalise_id(h["tax_id"])
        if reg_gstin and printed and reg_gstin not in printed:
            f.append(Finding(code="DOC_GSTIN_MISMATCH", severity="high",
                             detail=f"The documents show GSTIN {', '.join(printed)}; the hospital's GSTIN on record is "
                                    f"{reg_gstin}."))
        off = [(doc, text) for doc, text in texts if name_match_score(h["name"], text) < threshold]
        if off:
            others = [n for code, n in names.items() if code != claim.hospital_id]
            named = sorted({n for _, text in off for n in others if name_match_score(n, text) >= threshold})
            files = ", ".join(doc.filename for doc, _ in off)
            extra = f"; they name {', '.join(named)} instead" if named else ""
            f.append(Finding(code="DOC_HOSPITAL_NAME_MISMATCH", severity="high" if named else "medium",
                             detail=f"{files}: the claimed hospital's name ({h['name']}) was not found{extra}."))

    if d:
        typed = [(doc, t) for doc, t in texts if doc.doc_type in DOCTOR_DOC_TYPES]
        targets = typed or texts
        if all(name_match_score(d["name"], t) < threshold for _, t in targets):
            files = ", ".join(doc.filename for doc, _ in targets)
            f.append(Finding(code="DOC_DOCTOR_NAME_MISSING", severity="low",
                             detail=f"{files}: the treating doctor's name ({d['name']}) does not appear."))
        reg = normalise_id(d.get("registration_no"))
        shown = find_registration_numbers(all_text)
        if reg and shown and reg not in {normalise_id(x) for x in shown}:
            f.append(Finding(code="DOC_DOCTOR_REG_MISMATCH", severity="high",
                             detail=f"The documents show registration number(s) {', '.join(shown)}; {d['name']}'s number "
                                    f"on record is {d['registration_no']}."))
    return f
