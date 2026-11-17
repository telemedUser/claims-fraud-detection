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

    def _doctor_dict(self, d: m.Doctor) -> dict:
        specs = list(d.specialities or [])
        return {
            "name": d.name, "qualification": d.qualification, "registration_no": d.registration_no,
            "specialty": specs[0] if specs else None,
            "license_valid": bool(d.licence_valid),
            "hospital_ids": self._hospital_codes(d),
            "claims_per_month": _num(d.claims_per_month, 0),
            "flagged_claims_ratio": _num(d.flagged_claims_ratio, 0),
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
        }

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


class Repos:
    """All repositories over one session, exposing the old ``store`` function names."""

    def __init__(self, session: Session):
        self.session = session
        self.providers = ProviderRepo(session)
        self.policies = PolicyRepo(session)
        self.claims = ClaimRepo(session)
        self.invoices = InvoiceRepo(session)
        self.reference = ReferenceRepo()

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

    def invoice_seen(self, hospital_id, invoice_number):
        return self.invoices.invoice_seen(hospital_id, invoice_number)

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
