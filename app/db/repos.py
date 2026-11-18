"""Repositories that replaced the in-memory accessors and ``SEEN_*`` sets of the old ``app/data/store.py``.

Each repository wraps a SQLAlchemy ``Session`` and returns the plain-dict shapes the agents use, so
callers changed very little. Repositories never commit; the caller owns the transaction
(``open_repos()`` and ``get_session()`` commit on success).

``Repos`` bundles the repositories behind the old function names (``hospital``, ``doctor``,
``policy``, ``history``, ``invoice_seen`` ...). Callers use::

    with open_repos() as repos:
        h = repos.hospital("H001")

Identifier mapping (the old store used short string ids; the schema uses UUID primary keys):
  * hospital id  -> ``providers.code``
  * doctor id    -> ``doctors.code`` (a UUID string is also accepted)
  * claimant id  -> ``members.code`` (falls back to ``str(members.id)``); claims keep the claimant id
    they were registered with in ``claims.claimant_ref``
  * claim id     -> ``claims.claim_ref`` (the primary key is a uuid5 of it when it is not a UUID)
  * disease id   -> static reference data (no diseases table), see ``ReferenceRepo``

Prior-claim lookups (``invoice_seen``, ``doc_hash_seen``, ``history``) only count claims that have
been processed. Claims with status ``RECEIVED`` (for example the seeded demo scenarios that are still
waiting to be run) are not earlier submissions.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Iterator

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.seed.seed_data import DISEASES  # static reference data: there is no diseases table

UNPROCESSED = "RECEIVED"
REGISTERED_STATUS = "ASSESSED"
POLICY_VIOLATION = "POLICY_VIOLATION"  # stored for review after a policy eligibility rejection (task 13.4)
NOT_PRIOR = (UNPROCESSED, POLICY_VIOLATION)  # statuses that are not earlier submissions


def _num(v: Decimal | float | int | None, default: float | int | None = None) -> float | int | None:
    """Numbers as the old store had them: whole values stay ints (45000, not 45000.0)."""
    if v is None:
        return default
    f = float(v)
    return int(f) if f.is_integer() else f


def _iso(d: date | datetime | None) -> str | None:
    return None if d is None else d.isoformat()


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def claim_uuid(claim_id: str) -> uuid.UUID:
    """UUID for an external claim id: itself when it is a UUID, else a stable uuid5."""
    return _as_uuid(claim_id) or uuid.uuid5(uuid.NAMESPACE_URL, f"claim:{claim_id}")


class ReferenceRepo:
    """Static reference data (disease catalogue)."""

    DISEASES = DISEASES

    def disease(self, disease_id: str | None) -> dict | None:
        return DISEASES.get(disease_id) if disease_id else None

    def diseases(self) -> dict[str, dict]:
        return dict(DISEASES)


class ProviderRepo:
    def __init__(self, session: Session):
        self.s = session

    def _provider(self, code: str) -> m.Provider | None:
        return self.s.scalars(select(m.Provider).where(m.Provider.code == code)).first()

    def _doctor(self, did: str | None) -> m.Doctor | None:
        if not did:
            return None
        d = self.s.scalars(select(m.Doctor).where(m.Doctor.code == did)).first()
        if d is None:
            key = _as_uuid(did)
            d = self.s.get(m.Doctor, key) if key else None
        return d

    def _hospital_codes(self, d: m.Doctor) -> list[str]:
        codes = list(self.s.scalars(
            select(m.Provider.code).join(m.DoctorAffiliation, m.DoctorAffiliation.provider_id == m.Provider.id)
            .where(m.DoctorAffiliation.doctor_id == d.id).order_by(m.DoctorAffiliation.position)))
        if codes:
            return codes
        p = self.s.get(m.Provider, d.provider_id)
        return [p.code] if p else []

    def _affiliation_dates(self, d: m.Doctor) -> dict[str, tuple[str | None, str | None]]:
        """hospital code -> (start, end) ISO dates, only for affiliations with dates on record."""
        rows = self.s.execute(
            select(m.Provider.code, m.DoctorAffiliation.start_date, m.DoctorAffiliation.end_date)
            .join(m.DoctorAffiliation, m.DoctorAffiliation.provider_id == m.Provider.id)
            .where(m.DoctorAffiliation.doctor_id == d.id).order_by(m.DoctorAffiliation.position)).all()
        return {code: (_iso(start), _iso(end)) for code, start, end in rows if start or end}

    def _doctor_dict(self, d: m.Doctor) -> dict:
        specs = list(d.specialities or [])
        return {
            "name": d.name, "qualification": d.qualification, "registration_no": d.registration_no,
            "specialty": specs[0] if specs else None,
            "license_valid": bool(d.licence_valid),
            "hospital_ids": self._hospital_codes(d),
            "claims_per_month": _num(d.claims_per_month, 0),
            "flagged_claims_ratio": _num(d.flagged_claims_ratio, 0),
            "licence_valid_to": _iso(d.licence_valid_to),
            "affiliation_dates": self._affiliation_dates(d),
        }

    def hospital(self, hid: str) -> dict | None:
        p = self._provider(hid) if hid else None
        if p is None:
            return None
        if p.specialties is not None:
            specs = list(p.specialties)
        else:  # rows created without the column: the specialities of the doctors there
            specs = []
            for d in self.s.scalars(select(m.Doctor).where(m.Doctor.provider_id == p.id)):
                for sp in d.specialities or []:
                    if sp not in specs:
                        specs.append(sp)
        return {
            "name": p.name, "city": p.city, "address": p.address, "phone": p.phone,
            "registered": bool(p.registered), "tax_id": p.gstin, "specialties": specs,
            "avg_claim": _num(p.avg_claim, 0), "std_claim": _num(p.std_claim, 0),
            "flagged_claims_ratio": _num(p.flagged_claims_ratio, 0), "years_active": _num(p.years_active, 0),
            "baseline_monthly_claims": _num(p.baseline_monthly_claims),
            "state_code": p.state_code, "bed_count": p.bed_count,
            "empanelled_from": _iso(p.empanelled_from), "empanelled_to": _iso(p.empanelled_to),
        }

    def provider_names(self) -> dict[str, str]:
        """All hospital codes and names (used to name the hospital printed on a mismatching document)."""
        return {code: name for code, name in self.s.execute(select(m.Provider.code, m.Provider.name))}

    def doctor(self, did: str) -> dict | None:
        d = self._doctor(did)
        return None if d is None else self._doctor_dict(d)

    def doctors_at(self, hospital_id: str) -> dict[str, dict]:
        """Doctors with a valid licence attached to the hospital, keyed by doctor id."""
        p = self._provider(hospital_id) if hospital_id else None
        if p is None:
            return {}
        affiliated = select(m.DoctorAffiliation.doctor_id).where(m.DoctorAffiliation.provider_id == p.id)
        has_any = select(m.DoctorAffiliation.doctor_id).where(m.DoctorAffiliation.doctor_id == m.Doctor.id)
        rows = self.s.scalars(
            select(m.Doctor).where(
                m.Doctor.licence_valid.is_(True),
                (m.Doctor.id.in_(affiliated)) | ((m.Doctor.provider_id == p.id) & ~has_any.exists()))
            .order_by(m.Doctor.code, m.Doctor.name))
        return {d.code or str(d.id): self._doctor_dict(d) for d in rows}


class PolicyRepo:
    def __init__(self, session: Session):
        self.s = session

    def policy(self, policy_number: str) -> dict | None:
        p = self.s.scalars(select(m.Policy).where(m.Policy.policy_number == policy_number)).first()
        if p is None:
            return None
        members = list(self.s.scalars(select(m.Member).where(m.Member.policy_id == p.id).order_by(m.Member.name)))
        holder = next((x for x in members if x.relation == "self"), members[0] if members else None)
        return {
            "holder_name": p.holder_name or (holder.name if holder else None),
            "claimant_id": (holder.code or str(holder.id)) if holder else None,
            "date_of_birth": _iso(p.dob),
            "plan": p.plan, "sum_insured": _num(p.sum_insured),
            "valid_from": _iso(p.inception_date), "valid_to": _iso(p.expiry_date),
            "network_hospital_ids": list(p.network_hospital_ids or []),
            "covered_disease_ids": list(p.covered_disease_ids or []),
        }


class InvoiceRepo:
    def __init__(self, session: Session):
        self.s = session

    def invoice_seen(self, hospital_id: str, invoice_number: str) -> bool:
        q = (select(m.Invoice.id).join(m.Claim, m.Claim.id == m.Invoice.claim_id)
             .join(m.Provider, m.Provider.id == m.Claim.provider_id)
             .where(m.Provider.code == hospital_id, m.Invoice.invoice_number == invoice_number,
                    m.Claim.status.not_in(NOT_PRIOR)).limit(1))
        return self.s.scalars(q).first() is not None

    def invoice_candidates(self, hospital_id: str, invoice_number: str, exclude_ref: str | None = None) -> list[dict]:
        """Earlier processed invoices that could duplicate this one: every invoice at the same hospital, plus any
        invoice elsewhere whose number shares the last 4 characters (normalised matching is done by the caller)."""
        tail = "".join(ch for ch in (invoice_number or "") if ch.isalnum())[-4:]
        q = (select(m.Invoice.invoice_number, m.Invoice.invoice_date, m.Invoice.stated_total, m.Claim.claim_ref,
                    m.Claim.claimant_ref, m.Provider.code)
             .join(m.Claim, m.Claim.id == m.Invoice.claim_id)
             .outerjoin(m.Provider, m.Provider.id == m.Claim.provider_id)
             .where(m.Claim.status.not_in(NOT_PRIOR)))
        cond = m.Provider.code == hospital_id
        if tail:
            cond = cond | m.Invoice.invoice_number.contains(tail)
        q = q.where(cond)
        if exclude_ref:
            q = q.where((m.Claim.claim_ref.is_(None)) | (m.Claim.claim_ref != exclude_ref))
        return [{"invoice_number": num, "invoice_date": d, "total": _num(t), "claim_id": ref, "claimant_id": who,
                 "hospital_id": code} for num, d, t, ref, who, code in self.s.execute(q)]

    def doc_hash_seen(self, sha256: str) -> bool:
        return bool(self.seen_doc_hashes([sha256]))

    def seen_doc_hashes(self, hashes: Iterable[str]) -> set[str]:
        """Subset of ``hashes`` already stored (replacement for ``h in SEEN_DOC_HASHES``)."""
        hs = list(hashes)
        if not hs:
            return set()
        q = (select(m.Document.sha256).join(m.Claim, m.Claim.id == m.Document.claim_id)
             .where(m.Document.sha256.in_(hs), m.Claim.status.not_in(NOT_PRIOR)))
        return set(self.s.scalars(q))


class ClaimRepo:
    def __init__(self, session: Session):
        self.s = session

    def history(self, claimant_id: str) -> list[dict]:
        """Earlier claims of the claimant, oldest first."""
        if not claimant_id:
            return []
        rows = self.s.execute(
            select(m.Claim, m.Provider.code)
            .outerjoin(m.Provider, m.Provider.id == m.Claim.provider_id)
            .where(m.Claim.claimant_ref == claimant_id, m.Claim.status.not_in(NOT_PRIOR))
            .order_by(m.Claim.submitted_on, m.Claim.created_at)
        ).all()
        out = []
        for c, code in rows:
            inv = self.s.scalars(select(m.Invoice).where(m.Invoice.claim_id == c.id)).first()
            out.append({
                "claim_id": c.claim_ref or str(c.id),
                "date": c.submitted_on.date() if c.submitted_on else None,
                "amount": _num(c.claimed_amount),
                "hospital_id": code,
                "invoice_number": inv.invoice_number if inv else None,
                "is_test": bool(c.is_test),
            })
        return out

    def claimant_records(self, claimant_id: str, exclude_ref: str | None = None) -> list[dict]:
        """Earlier processed claims of the claimant with stay, provider, diagnosis and the latest investigator
        decision, oldest first. Used by the User Profile agent and the investigator profile page."""
        if not claimant_id:
            return []
        q = (select(m.Claim, m.Provider.code, m.Provider.name, m.Doctor.code)
             .outerjoin(m.Provider, m.Provider.id == m.Claim.provider_id)
             .outerjoin(m.Doctor, m.Doctor.id == m.Claim.doctor_id)
             .where(m.Claim.claimant_ref == claimant_id, m.Claim.status.not_in(NOT_PRIOR)))
        if exclude_ref:
            q = q.where((m.Claim.claim_ref.is_(None)) | (m.Claim.claim_ref != exclude_ref))
        rows = self.s.execute(q.order_by(m.Claim.submitted_on, m.Claim.created_at)).all()
        ids = [c.id for c, *_ in rows]
        latest: dict[uuid.UUID, tuple[str, datetime | None]] = {}
        if ids:
            for cid, decision, at in self.s.execute(
                    select(m.InvestigatorDecision.claim_id, m.InvestigatorDecision.decision, m.InvestigatorDecision.created_at)
                    .where(m.InvestigatorDecision.claim_id.in_(ids))):
                if cid not in latest or (at and latest[cid][1] and at > latest[cid][1]):
                    latest[cid] = (decision, at)
        out = []
        for c, hcode, hname, dcode in rows:
            inv = self.s.scalars(select(m.Invoice).where(m.Invoice.claim_id == c.id)).first()
            out.append({
                "claim_id": c.claim_ref or str(c.id),
                "submitted": c.submitted_on.date() if c.submitted_on else None,
                "admission": c.admission_date, "discharge": c.discharge_date,
                "amount": _num(c.claimed_amount), "hospital_id": hcode, "hospital": hname, "doctor_id": dcode,
                "disease": c.disease_code, "invoice_number": inv.invoice_number if inv else None,
                "status": c.status, "decision": latest.get(c.id, (None,))[0], "is_test": bool(c.is_test),
            })
        return out

    def claimants(self) -> list[dict]:
        """Every member with a claimant code: identity and policy (staff view only, never sent to the LLM)."""
        rows = self.s.execute(select(m.Member, m.Policy).outerjoin(m.Policy, m.Policy.id == m.Member.policy_id)
                              .where(m.Member.code.is_not(None)).order_by(m.Member.code)).all()
        return [{"claimant_id": mem.code, "name": mem.name, "relation": mem.relation, "dob": _iso(mem.dob),
                 "policy_number": pol.policy_number if pol else None} for mem, pol in rows]

    def _member_id(self, claimant_id: str | None) -> uuid.UUID | None:
        if not claimant_id:
            return None
        mem = self.s.scalars(select(m.Member).where(m.Member.code == claimant_id)).first()
        if mem is None:
            key = _as_uuid(claimant_id)
            mem = self.s.get(m.Member, key) if key else None
        return mem.id if mem else None

    def register_claim(self, claim: Any, doc_hashes: Iterable[str], is_test: bool = False) -> m.Claim:
        """Persist the claim, its invoice and document hashes (flush only; caller commits).

        Registering the same claim id again only adds document hashes it does not have yet.
        """
        row = self.s.get(m.Claim, claim_uuid(claim.claim_id))
        if row is None:
            row = self._create(claim, is_test)
        have = set(self.s.scalars(select(m.Document.sha256).where(m.Document.claim_id == row.id)))
        for h in sorted(set(doc_hashes) - have):
            self.s.add(m.Document(claim_id=row.id, storage_key=f"sha256:{h}", sha256=h))
        self.s.flush()
        return row

    def _create(self, claim: Any, is_test: bool) -> m.Claim:
        provider = self.s.scalars(select(m.Provider).where(m.Provider.code == claim.hospital_id)).first()
        policy = None
        if getattr(claim, "policy_number", None):
            policy = self.s.scalars(select(m.Policy).where(m.Policy.policy_number == claim.policy_number)).first()
        doctor = ProviderRepo(self.s)._doctor(claim.doctor_id)
        sub = claim.submitted_on
        row = m.Claim(
            id=claim_uuid(claim.claim_id), claim_ref=claim.claim_id, claimant_ref=claim.claimant_id,
            policy_id=policy.id if policy else None, member_id=self._member_id(claim.claimant_id),
            provider_id=provider.id if provider else None, doctor_id=doctor.id if doctor else None,
            disease_code=getattr(claim, "disease_id", None),
            admission_date=claim.admission_date, discharge_date=claim.discharge_date,
            claimed_amount=Decimal(str(claim.claimed_amount)),
            submitted_on=datetime(sub.year, sub.month, sub.day) if sub else None,
            status=REGISTERED_STATUS, is_test=is_test,
        )
        self.s.add(row)
        self.s.flush()
        inv = claim.invoice
        invoice = m.Invoice(claim_id=row.id, invoice_number=inv.invoice_number, invoice_date=inv.invoice_date,
                            gstin=inv.tax_id, stated_total=Decimal(str(inv.total)))
        self.s.add(invoice)
        self.s.flush()
        for li in inv.line_items:
            self.s.add(m.InvoiceLineItem(invoice_id=invoice.id, description=li.description,
                                         amount=Decimal(str(li.amount))))
        return row

    def purge_test_claims(self) -> int:
        """Delete ``is_test`` claims and their invoices/documents/changes (not findings or runs)."""
        ids = list(self.s.scalars(select(m.Claim.id).where(m.Claim.is_test.is_(True))))
        if not ids:
            return 0
        inv_ids = select(m.Invoice.id).where(m.Invoice.claim_id.in_(ids))
        self.s.execute(delete(m.InvoiceLineItem).where(m.InvoiceLineItem.invoice_id.in_(inv_ids)))
        self.s.execute(delete(m.Invoice).where(m.Invoice.claim_id.in_(ids)))
        self.s.execute(delete(m.Document).where(m.Document.claim_id.in_(ids)))
        self.s.execute(delete(m.ClaimChange).where(m.ClaimChange.claim_id.in_(ids)))
        self.s.execute(delete(m.Claim).where(m.Claim.id.in_(ids)))
        self.s.flush()
        return len(ids)


class ProviderActivityRepo:
    """Claims-data queries behind the computed provider profile (Provider Profile agent).

    Every query counts earlier, processed claims only (status not in ``NOT_PRIOR``) and leaves out the
    claim being assessed (``exclude_ref``), so re-assessing a claim never compares it with itself.
    """

    def __init__(self, session: Session):
        self.s = session

    def _prior(self, q, exclude_ref: str | None):
        q = q.where(m.Claim.status.not_in(NOT_PRIOR))
        if exclude_ref:
            q = q.where((m.Claim.claim_ref.is_(None)) | (m.Claim.claim_ref != exclude_ref))
        return q

    def _provider_id(self, code: str) -> uuid.UUID | None:
        return self.s.scalars(select(m.Provider.id).where(m.Provider.code == code)).first()

    def _doctor_id(self, did: str) -> uuid.UUID | None:
        d = ProviderRepo(self.s)._doctor(did)
        return d.id if d else None

    def provider_claim_count(self, code: str, since: datetime, until: datetime, exclude_ref: str | None = None) -> int:
        pid = self._provider_id(code)
        if pid is None:
            return 0
        q = select(m.Claim.id).where(m.Claim.provider_id == pid, m.Claim.submitted_on >= since, m.Claim.submitted_on < until)
        return len(self.s.scalars(self._prior(q, exclude_ref)).all())

    def doctor_claim_count(self, did: str, since: datetime, until: datetime, exclude_ref: str | None = None) -> int:
        doc_id = self._doctor_id(did)
        if doc_id is None:
            return 0
        q = select(m.Claim.id).where(m.Claim.doctor_id == doc_id, m.Claim.submitted_on >= since, m.Claim.submitted_on < until)
        return len(self.s.scalars(self._prior(q, exclude_ref)).all())

    def provider_amounts(self, code: str, disease: str | None = None, exclude_ref: str | None = None) -> list[float]:
        """Claimed amounts at the hospital, optionally for one diagnosis."""
        pid = self._provider_id(code)
        if pid is None:
            return []
        q = select(m.Claim.claimed_amount).where(m.Claim.provider_id == pid, m.Claim.claimed_amount.is_not(None))
        if disease:
            q = q.where(m.Claim.disease_code == disease)
        return [float(v) for v in self.s.scalars(self._prior(q, exclude_ref))]

    def peer_amounts(self, disease: str, exclude_code: str, exclude_ref: str | None = None) -> list[float]:
        """Claimed amounts for the diagnosis at every other hospital."""
        pid = self._provider_id(exclude_code)
        q = select(m.Claim.claimed_amount).where(m.Claim.disease_code == disease, m.Claim.claimed_amount.is_not(None))
        if pid is not None:
            q = q.where((m.Claim.provider_id.is_(None)) | (m.Claim.provider_id != pid))
        return [float(v) for v in self.s.scalars(self._prior(q, exclude_ref))]

    def decision_counts(self, flagged_decisions: Iterable[str], since: datetime, *, hospital: str | None = None,
                        doctor: str | None = None) -> tuple[int, int]:
        """(decided claims, claims whose latest investigator decision is a flagged one) since ``since``."""
        q = (select(m.InvestigatorDecision.claim_id, m.InvestigatorDecision.decision, m.InvestigatorDecision.created_at)
             .join(m.Claim, m.Claim.id == m.InvestigatorDecision.claim_id)
             .where(m.InvestigatorDecision.created_at >= since))
        if hospital:
            pid = self._provider_id(hospital)
            if pid is None:
                return 0, 0
            q = q.where(m.Claim.provider_id == pid)
        if doctor:
            doc_id = self._doctor_id(doctor)
            if doc_id is None:
                return 0, 0
            q = q.where(m.Claim.doctor_id == doc_id)
        latest: dict[uuid.UUID, tuple] = {}
        for claim_id, decision, at in self.s.execute(q):
            if claim_id not in latest or (at and latest[claim_id][1] and at > latest[claim_id][1]):
                latest[claim_id] = (decision, at)
        flagged = set(flagged_decisions)
        return len(latest), sum(1 for d, _ in latest.values() if d in flagged)

    def overlapping_stays(self, code: str, day: date, exclude_ref: str | None = None) -> int:
        """Claims at the hospital whose stay includes ``day`` (admission <= day <= discharge)."""
        pid = self._provider_id(code)
        if pid is None:
            return 0
        q = select(m.Claim.id).where(m.Claim.provider_id == pid, m.Claim.admission_date.is_not(None),
                                     m.Claim.admission_date <= day,
                                     (m.Claim.discharge_date.is_(None) & (m.Claim.admission_date == day))
                                     | (m.Claim.discharge_date >= day))
        return len(self.s.scalars(self._prior(q, exclude_ref)).all())

    def doctor_admissions_on(self, did: str, day: date, exclude_ref: str | None = None) -> list[dict]:
        """Other claims by the doctor admitted on ``day``: hospital code, name and city."""
        doc_id = self._doctor_id(did)
        if doc_id is None:
            return []
        q = (select(m.Claim.claim_ref, m.Provider.code, m.Provider.name, m.Provider.city)
             .join(m.Provider, m.Provider.id == m.Claim.provider_id)
             .where(m.Claim.doctor_id == doc_id, m.Claim.admission_date == day))
        return [{"claim_id": ref, "hospital_id": code, "hospital": name, "city": city}
                for ref, code, name, city in self.s.execute(self._prior(q, exclude_ref))]

    def doctor_similar_amount_claimants(self, did: str, amount: float, tolerance_pct: float, since: datetime,
                                        exclude_claimant: str | None, exclude_ref: str | None = None) -> int:
        """Distinct other claimants with a claim by this doctor within ``tolerance_pct`` of ``amount``."""
        doc_id = self._doctor_id(did)
        if doc_id is None or amount <= 0:
            return 0
        lo, hi = amount * (1 - tolerance_pct / 100), amount * (1 + tolerance_pct / 100)
        q = select(m.Claim.claimant_ref, m.Claim.member_id, m.Claim.claimed_amount).where(
            m.Claim.doctor_id == doc_id, m.Claim.submitted_on >= since, m.Claim.claimed_amount.is_not(None))
        people = set()
        for ref, member_id, amt in self.s.execute(self._prior(q, exclude_ref)):
            who = ref or (str(member_id) if member_id else None)
            if who and who != exclude_claimant and lo <= float(amt) <= hi:
                people.add(who)
        return len(people)


class Repos:
    """All repositories over one session, exposing the old ``store`` function names."""

    def __init__(self, session: Session):
        self.session = session
        self.providers = ProviderRepo(session)
        self.policies = PolicyRepo(session)
        self.claims = ClaimRepo(session)
        self.invoices = InvoiceRepo(session)
        self.reference = ReferenceRepo()
        self.activity = ProviderActivityRepo(session)

    DISEASES = DISEASES

    def hospital(self, hid):
        return self.providers.hospital(hid)

    def doctor(self, did):
        return self.providers.doctor(did)

    def doctors_at(self, hospital_id):
        return self.providers.doctors_at(hospital_id)

    def policy(self, policy_number):
        return self.policies.policy(policy_number)

    def disease(self, disease_id):
        return self.reference.disease(disease_id)

    def history(self, claimant_id):
        return self.claims.history(claimant_id)

    def claimant_records(self, claimant_id, exclude_ref=None):
        return self.claims.claimant_records(claimant_id, exclude_ref)

    def invoice_seen(self, hospital_id, invoice_number):
        return self.invoices.invoice_seen(hospital_id, invoice_number)

    def invoice_candidates(self, hospital_id, invoice_number, exclude_ref=None):
        return self.invoices.invoice_candidates(hospital_id, invoice_number, exclude_ref)

    def doc_hash_seen(self, sha256):
        return self.invoices.doc_hash_seen(sha256)

    def seen_doc_hashes(self, hashes):
        return self.invoices.seen_doc_hashes(hashes)

    def register_claim(self, claim, doc_hashes, is_test=False):
        return self.claims.register_claim(claim, doc_hashes, is_test)


@contextmanager
def open_repos() -> Iterator[Repos]:
    """A ``Repos`` on a fresh session of the process-wide engine; commits on success."""
    from app.db.session import get_session

    with get_session() as session:
        yield Repos(session)
