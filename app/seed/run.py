"""Idempotent seeding of Synthetic_Data (Requirements 1.3, 1.4).

``seed(session)`` upserts by natural keys, so running it twice leaves the same rows:

* policies by ``policy_number`` (one member, the holder, per policy, with the short claimant code)
* providers by ``code`` (hospital id)
* doctors by ``code`` (one row per doctor; every hospital is a ``doctor_affiliations`` row)
* history claims by the invoice number of an invoice that has no document
* demo scenarios by the ``original_name_ref`` of their bill document (``seed:<scenario>:medical_bill.pdf``)
* provider volume surge filler claims by ``channel == "seed_surge"``

* one user per role by ``username`` (passwords from SEED_* env vars; see README "Local login"). Run with ``python -m app.seed.run``.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.seed import docgen, seed_data as sd

SURGE_CHANNEL = "seed_surge"
SCENARIO_NAMES = tuple(sd.SCENARIOS)


def _dec(v) -> Decimal:
    return Decimal(str(v))


def _day(d: date | str) -> date:
    return date.fromisoformat(d) if isinstance(d, str) else d


def _opt_day(d: date | str | None) -> date | None:
    return None if d is None else _day(d)


def _at(d: date) -> datetime:
    return datetime.combine(d, time(9, 0), tzinfo=timezone.utc)


def scenario_ref(name: str, doc_type: str = "medical_bill") -> str:
    return f"seed:{name}:{doc_type}.pdf"


# ---------------------------------------------------------------- reference data
def _fill(row, **values) -> None:
    """Set attributes that are still empty (brings rows seeded before a column existed up to date)."""
    for key, value in values.items():
        if getattr(row, key) is None:
            setattr(row, key, value)


def _seed_policies(s: Session) -> dict[str, m.Member]:
    members: dict[str, m.Member] = {}
    for number, p in sd.POLICIES.items():
        pol = s.scalars(select(m.Policy).where(m.Policy.policy_number == number)).first()
        if pol is None:
            pol = m.Policy(
                policy_number=number, plan=p["plan"], inception_date=_day(p["valid_from"]),
                expiry_date=_day(p["valid_to"]), sum_insured=_dec(p["sum_insured"]), waiting_period_days=30,
                exclusions=[d for d in sd.DISEASES if d not in p["covered_disease_ids"]],
                dob=_day(p["date_of_birth"]))
            s.add(pol)
        _fill(pol, holder_name=p["holder_name"], network_hospital_ids=list(p["network_hospital_ids"]),
              covered_disease_ids=list(p["covered_disease_ids"]))
        s.flush()
        mem = s.scalars(select(m.Member).where(m.Member.code == p["claimant_id"])).first()
        if mem is None:
            mem = s.scalars(select(m.Member).where(m.Member.policy_id == pol.id, m.Member.name == p["holder_name"])).first()
        if mem is None:
            mem = m.Member(policy_id=pol.id, name=p["holder_name"], relation="self", dob=_day(p["date_of_birth"]))
            s.add(mem)
        _fill(mem, code=p["claimant_id"])
        s.flush()
        members[p["claimant_id"]] = mem
        members[number] = mem
    return members


def _seed_providers(s: Session) -> tuple[dict[str, m.Provider], dict[str, m.Doctor]]:
    providers: dict[str, m.Provider] = {}
    for code, h in sd.HOSPITALS.items():
        prov = s.scalars(select(m.Provider).where(m.Provider.code == code)).first()
        if prov is None:
            prov = m.Provider(
                code=code, name=h["name"], city=h["city"], registered=h["registered"], years_active=h["years_active"],
                avg_claim=_dec(h["avg_claim"]), std_claim=_dec(h["std_claim"]),
                flagged_claims_ratio=h["flagged_claims_ratio"],
                baseline_monthly_claims=h.get("baseline_monthly_claims"), gstin=h["tax_id"],
                reference_source="synthetic seed")
            s.add(prov)
        _fill(prov, address=h["address"], phone=h["phone"], specialties=list(h["specialties"]),
              state_code=h.get("state_code"), bed_count=h.get("bed_count"),
              empanelled_from=_opt_day(h.get("empanelled_from")), empanelled_to=_opt_day(h.get("empanelled_to")))
        s.flush()
        providers[code] = prov
    doctors: dict[str, m.Doctor] = {}
    for did, d in sd.DOCTORS.items():
        primary = providers[d["hospital_ids"][0]]
        doc = s.scalars(select(m.Doctor).where(m.Doctor.code == did)).first()
        if doc is None:  # a row from a seed that predates doctor codes (one row per hospital)
            doc = s.scalars(select(m.Doctor).where(
                m.Doctor.code.is_(None), m.Doctor.provider_id == primary.id, m.Doctor.name == d["name"])).first()
        if doc is None:
            doc = m.Doctor(provider_id=primary.id, name=d["name"], licence_valid=d["license_valid"],
                           specialities=[d["specialty"]])
            s.add(doc)
        _fill(doc, code=did, qualification=d["qualification"], registration_no=d["registration_no"],
              claims_per_month=d["claims_per_month"], flagged_claims_ratio=d["flagged_claims_ratio"],
              licence_valid_to=_opt_day(d.get("licence_valid_to")))
        s.flush()
        have = {a.provider_id: a for a in s.scalars(select(m.DoctorAffiliation).where(m.DoctorAffiliation.doctor_id == doc.id))}
        dates = d.get("affiliation_dates", {})
        for pos, code in enumerate(d["hospital_ids"]):
            aff = have.get(providers[code].id)
            if aff is None:
                aff = m.DoctorAffiliation(doctor_id=doc.id, provider_id=providers[code].id, position=pos)
                s.add(aff)
            start, end = dates.get(code, (None, None))
            _fill(aff, start_date=_opt_day(start), end_date=_opt_day(end))
        s.flush()
        doctors[did] = doc
    return providers, doctors


# ---------------------------------------------------------------- claims
def _seed_history(s: Session, members, providers) -> None:
    for claimant_id, rows in sd.CLAIM_HISTORY.items():
        for h in rows:
            exists = s.scalars(select(m.Invoice.id).where(
                m.Invoice.invoice_number == h["invoice_number"], m.Invoice.document_id.is_(None))).first()
            if exists is not None:
                continue
            prov = providers[h["hospital_id"]]
            extra = sd.HISTORY_DETAILS.get(h["claim_id"], {})
            claim = m.Claim(
                claim_ref=h["claim_id"], claimant_ref=claimant_id, member_id=members[claimant_id].id, policy_id=members[claimant_id].policy_id, provider_id=prov.id,
                claimed_amount=_dec(h["amount"]), submitted_on=_at(h["date"]), status="DECIDED", is_test=True,
                admission_date=extra.get("admission"), discharge_date=extra.get("discharge"), disease_code=extra.get("disease"))
            s.add(claim)
            s.flush()
            if extra.get("decision"):
                s.add(m.InvestigatorDecision(claim_id=claim.id, user_id=_system_user(s).id, decision=extra["decision"],
                                             reason="Seeded historical outcome (synthetic data)."))
            s.add(m.Invoice(claim_id=claim.id, invoice_number=h["invoice_number"], invoice_date=h["date"],
                            gstin=prov.gstin, stated_total=_dec(h["amount"])))
    s.flush()


def _system_user(s: Session) -> m.User:
    """Inactive owner of seeded decisions (no usable password, role outside the console roles)."""
    u = s.scalars(select(m.User).where(m.User.username == sd.SYSTEM_USER["username"])).first()
    if u is None:
        u = m.User(username=sd.SYSTEM_USER["username"], password_hash="!disabled", role=sd.SYSTEM_USER["role"],
                   is_active=False)
        s.add(u)
        s.flush()
    return u


def _seed_surge(s: Session, members, providers) -> None:
    """Recent claims at H002 so its volume over the last 30 days far exceeds its baseline."""
    have = s.scalar(select(func.count()).select_from(m.Claim).where(m.Claim.channel == SURGE_CHANNEL)) or 0
    mem = members["U002"]
    now = datetime.now(timezone.utc)
    for i in range(have, sd.SURGE_CLAIMS_AT_H002):
        s.add(m.Claim(member_id=mem.id, policy_id=mem.policy_id, provider_id=providers["H002"].id,
                      claimed_amount=_dec(30000), submitted_on=now - timedelta(hours=20 * i + 1),
                      channel=SURGE_CHANNEL, status="DECIDED", is_test=True))
    s.flush()


def _seed_scenarios(s: Session, members, providers, doctors, storage_dir: Path | None) -> None:
    for name, sc in sd.SCENARIOS.items():
        marker = scenario_ref(name)
        if s.scalars(select(m.Document.id).where(m.Document.original_name_ref == marker)).first() is not None:
            continue
        case = docgen.build_case(sc["case"])
        case["invoice_number"] = sc["invoice_number"]
        prov = providers[case["hospital_id"]]
        mem = members[case["policy_number"]]
        claim = m.Claim(
            member_id=mem.id, policy_id=mem.policy_id, provider_id=prov.id,
            doctor_id=doctors[case["doctor_id"]].id, disease_code=case["disease_id"],
            admission_date=case["admission"], discharge_date=case["discharge"],
            claimed_amount=_dec(case["claimed_amount"]), submitted_on=datetime.now(timezone.utc),
            channel="investigator", status="RECEIVED", is_test=False,
            preauth_amount=None if case["preauth_amount"] is None else _dec(case["preauth_amount"]))
        s.add(claim)
        s.flush()
        docs: dict[str, m.Document] = {}
        for doc_type in case["doc_types"]:
            data = docgen.render(case, doc_type)
            key = f"seed/{name}/{doc_type}.pdf"
            if storage_dir is not None:
                path = storage_dir / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            doc = m.Document(claim_id=claim.id, doc_type=doc_type, storage_key=key,
                             sha256=hashlib.sha256(data).hexdigest(), content_type="application/pdf",
                             size=len(data), original_name_ref=scenario_ref(name, doc_type))
            s.add(doc)
            docs[doc_type] = doc
        s.flush()
        inv = m.Invoice(claim_id=claim.id, document_id=docs["medical_bill"].id, invoice_number=case["invoice_number"],
                        invoice_date=case["bill_date"], gstin=case["bill_tax_id"], stated_total=_dec(case["bill_total"]),
                        service_category=case["disease"]["category"])
        s.add(inv)
        s.flush()
        for desc, qty, rate in case["items"]:
            s.add(m.InvoiceLineItem(invoice_id=inv.id, description=desc, amount=_dec(qty * rate)))
    s.flush()


# ---------------------------------------------------------------- users
# username -> (role, settings attribute holding that user's own seed password)
SEED_USERS = {
    "investigator": ("Investigator", "seed_password_investigator"),
    "ops_manager": ("Ops_Manager", "seed_password_ops_manager"),
    "fraud_team": ("Fraud_Team", "seed_password_fraud_team"),
    "admin": ("Administrator", "seed_password_admin"),
}


def _seed_password(settings, username: str, attr: str) -> str | None:
    """Per-user env value, else shared SEED_USER_PASSWORD, else a per-user dev default only when
    DEV_SEED_DEFAULT_PASSWORDS is set. Otherwise None (the user is not seeded)."""
    for secret in (getattr(settings, attr), settings.seed_user_password):
        if secret and secret.get_secret_value():
            return secret.get_secret_value()
    if settings.dev_seed_default_passwords:
        return f"dev-only-{username}-password"
    return None


def seed_users(session: Session) -> list[str]:
    """Create one user per role (idempotent: existing users and their passwords are left alone).
    Users without a configured password are skipped. Returns the usernames created."""
    from app.api.auth import hash_password
    from app.settings import get_settings

    settings = get_settings()
    created: list[str] = []
    for username, (role, attr) in SEED_USERS.items():
        if session.scalars(select(m.User.id).where(m.User.username == username)).first() is not None:
            continue
        password = _seed_password(settings, username, attr)
        if password is None:
            continue
        session.add(m.User(username=username, password_hash=hash_password(password), role=role, is_active=True))
        created.append(username)
    session.flush()
    return created


# ---------------------------------------------------------------- entry points
def seed(session: Session, storage_dir: Path | None = None) -> None:
    """Seed policies, providers, doctors, claims and documents. Safe to run repeatedly.

    ``storage_dir``: when given, the generated scenario PDFs are also written under it at their
    ``storage_key``. The caller owns the transaction boundary only in that ``seed`` commits at the end.
    """
    members = _seed_policies(session)
    providers, doctors = _seed_providers(session)
    _seed_history(session, members, providers)
    _seed_surge(session, members, providers)
    _seed_scenarios(session, members, providers, doctors, storage_dir)
    seed_users(session)
    session.commit()


def is_empty(session: Session) -> bool:
    return session.scalar(select(func.count()).select_from(m.Provider)) == 0


def seed_if_empty(session: Session, storage_dir: Path | None = None) -> bool:
    """Seed only a database without reference data (app start-up). Returns whether it seeded."""
    if not is_empty(session):
        return False
    seed(session, storage_dir)
    return True


def reset_database(engine: Engine, storage_dir: Path | None = None) -> None:
    """Drop every table, recreate them and seed (development and tests only).

    Refused on anything but SQLite: PostgreSQL holds append-only audit data that must never be dropped.
    """
    if engine.dialect.name != "sqlite":
        raise RuntimeError("reset is only supported on SQLite development databases")
    m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        seed(session, storage_dir)


def main(argv: list[str] | None = None) -> int:
    from app.db.session import SessionLocal, create_all

    ap = argparse.ArgumentParser(description="Seed the database with synthetic data.")
    ap.add_argument("--create-tables", action="store_true", help="create tables first (dev; production uses Alembic)")
    ap.add_argument("--storage-dir", default="storage", help="where scenario PDFs are written")
    args = ap.parse_args(argv)
    if args.create_tables:
        create_all()
    with SessionLocal() as session:
        seed(session, Path(args.storage_dir))
    print("seed complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
