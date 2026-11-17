"""Repository tests on in-memory SQLite (Req 17.1, 12.1)."""
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db import models as m
from app.db.repos import ClaimRepo, InvoiceRepo, PolicyRepo, ProviderRepo, ReferenceRepo
from app.db.session import create_all, make_engine
from app.models import Claim, Invoice, LineItem


@pytest.fixture()
def s():
    engine = make_engine("sqlite://")
    create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def seeded(s):
    prov = m.Provider(code="H001", name="City General", city="Pune", registered=True, years_active=18,
                      avg_claim=45000, std_claim=15000, flagged_claims_ratio=0.02, gstin="27AAACC1111A1Z5")
    pol = m.Policy(policy_number="POL-1001", plan="Gold", sum_insured=500000,
                   inception_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), dob=date(1992, 4, 18))
    s.add_all([prov, pol])
    s.flush()
    mem = m.Member(policy_id=pol.id, name="A. Kumar", relation="self")
    ok = m.Doctor(provider_id=prov.id, name="Dr. Rao", licence_valid=True, specialities=["General Surgery"])
    bad = m.Doctor(provider_id=prov.id, name="Dr. X", licence_valid=False, specialities=["General Medicine"])
    s.add_all([mem, ok, bad])
    s.flush()
    return prov, pol, mem, ok, bad


def _claim(mem, doc, claim_id="C-1", inv="INV-1"):
    return Claim(claim_id=claim_id, claimant_id=str(mem.id), claimant_name="A", hospital_id="H001",
                 doctor_id=str(doc.id), diagnosis="x", admission_date=date(2026, 2, 1),
                 discharge_date=date(2026, 2, 4), claimed_amount=20000.5, submitted_on=date(2026, 2, 10),
                 policy_number="POL-1001", disease_id="dengue",
                 invoice=Invoice(invoice_number=inv, invoice_date=date(2026, 2, 4),
                                 line_items=[LineItem(description="room", amount=20000.5)], total=20000.5))


def test_provider_shapes(s, seeded):
    _, _, _, ok, bad = seeded
    r = ProviderRepo(s)
    h = r.hospital("H001")
    assert h["name"] == "City General" and h["registered"] is True and h["tax_id"] == "27AAACC1111A1Z5"
    assert h["avg_claim"] == 45000.0 and h["specialties"] == ["General Surgery", "General Medicine"]
    assert r.hospital("NOPE") is None
    d = r.doctor(str(ok.id))
    assert d["license_valid"] is True and d["hospital_ids"] == ["H001"] and d["specialty"] == "General Surgery"
    assert r.doctor("not-a-uuid") is None
    assert set(r.doctors_at("H001")) == {str(ok.id)}
    assert str(bad.id) not in r.doctors_at("H001") and r.doctors_at("NOPE") == {}


def test_policy_shape(s, seeded):
    _, _, mem, *_ = seeded
    p = PolicyRepo(s).policy("POL-1001")
    assert p["claimant_id"] == str(mem.id) and p["holder_name"] == "A. Kumar"
    assert p["valid_from"] == "2026-01-01" and p["date_of_birth"] == "1992-04-18"
    assert p["sum_insured"] == 500000.0
    assert PolicyRepo(s).policy("none") is None


def test_reference_diseases():
    r = ReferenceRepo()
    assert r.disease("dengue")["typical_cost"] == [15000, 60000]
    assert r.disease("zzz") is None and "dental" in r.DISEASES


def test_register_claim_history_and_seen(s, seeded):
    _, _, mem, ok, _ = seeded
    claims, inv = ClaimRepo(s), InvoiceRepo(s)
    assert claims.history(str(mem.id)) == []
    assert not inv.invoice_seen("H001", "INV-1") and not inv.doc_hash_seen("a" * 64)
    claims.register_claim(_claim(mem, ok), {"a" * 64, "b" * 64}, is_test=True)
    assert inv.invoice_seen("H001", "INV-1") and not inv.invoice_seen("H002", "INV-1")
    assert inv.doc_hash_seen("a" * 64) and not inv.doc_hash_seen("c" * 64)
    assert inv.seen_doc_hashes(["a" * 64, "c" * 64]) == {"a" * 64}
    (h,) = claims.history(str(mem.id))
    assert h["date"] == date(2026, 2, 10) and h["amount"] == 20000.5
    assert h["hospital_id"] == "H001" and h["invoice_number"] == "INV-1" and h["is_test"] is True
    assert set(h) == {"claim_id", "date", "amount", "hospital_id", "invoice_number", "is_test"}


def test_register_non_test_and_purge(s, seeded):
    _, _, mem, ok, _ = seeded
    claims = ClaimRepo(s)
    claims.register_claim(_claim(mem, ok, "C-1", "INV-1"), [], is_test=False)
    claims.register_claim(_claim(mem, ok, "C-2", "INV-2"), ["d" * 64], is_test=True)
    assert [x["is_test"] for x in claims.history(str(mem.id))] == [False, True] or len(claims.history(str(mem.id))) == 2
    assert claims.purge_test_claims() == 1
    (h,) = claims.history(str(mem.id))
    assert h["invoice_number"] == "INV-1" and h["is_test"] is False
    assert not InvoiceRepo(s).doc_hash_seen("d" * 64)


def test_history_unknown_claimant(s):
    assert ClaimRepo(s).history("U001") == []
