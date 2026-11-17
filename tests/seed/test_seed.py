"""Seeding is idempotent, contains the four demo scenarios and only valid GSTINs (Req 1.3, 1.4)."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.validators.gstin import is_valid
from app.db import models as m
from app.db.session import make_engine
from app.seed import seed_data as sd
from app.seed.run import SCENARIO_NAMES, scenario_ref, seed


@pytest.fixture()
def session():
    engine = make_engine("sqlite://")
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _counts(s: Session) -> dict[str, int]:
    return {t.name: s.scalar(select(func.count()).select_from(t)) for t in m.Base.metadata.sorted_tables}


def test_seed_twice_keeps_row_counts(session, tmp_path):
    seed(session, tmp_path)
    first = _counts(session)
    seed(session, tmp_path)
    assert _counts(session) == first
    assert first["policies"] == len(sd.POLICIES) and first["providers"] == len(sd.HOSPITALS)
    assert first["claims"] > 0 and first["documents"] > 0 and first["doctors"] > 0


def test_four_demo_scenarios_present(session, tmp_path):
    seed(session, tmp_path)
    assert SCENARIO_NAMES == ("clean", "high_risk", "fabricated", "borderline")
    for name in SCENARIO_NAMES:
        doc = session.scalars(select(m.Document).where(m.Document.original_name_ref == scenario_ref(name))).one()
        assert (tmp_path / doc.storage_key).read_bytes().startswith(b"%PDF")
        inv = session.scalars(select(m.Invoice).where(m.Invoice.document_id == doc.id)).one()
        assert inv.invoice_number == sd.SCENARIOS[name]["invoice_number"]
        assert session.scalars(select(m.InvoiceLineItem).where(m.InvoiceLineItem.invoice_id == inv.id)).first()


def test_scenario_specifics(session):
    seed(session)
    by_inv = {i.invoice_number: i for i in session.scalars(select(m.Invoice).where(m.Invoice.document_id.is_not(None)))}
    claim = lambda inv: session.get(m.Claim, by_inv[inv].claim_id)  # noqa: E731
    # high risk: duplicate invoice number, invalid GSTIN, 14-day stay, provider volume surge
    assert session.scalars(select(m.Invoice).where(m.Invoice.invoice_number == "INV-2002")).all().__len__() == 2
    assert not is_valid(by_inv["INV-2002"].gstin)
    hr = claim("INV-2002")
    assert (hr.discharge_date - hr.admission_date).days == 14
    surge = session.scalar(select(func.count()).select_from(m.Claim).where(m.Claim.provider_id == hr.provider_id))
    base = session.get(m.Provider, hr.provider_id).baseline_monthly_claims
    assert surge > 3 * base
    # fabricated: round total, invented doctor
    fab = by_inv["INV-DEMO-FAB"]
    assert fab.stated_total % 10000 == 0
    assert session.get(m.Doctor, claim("INV-DEMO-FAB").doctor_id).licence_valid is False
    # borderline: pre-auth overrun, no discharge summary
    bl = claim("INV-DEMO-BORDER")
    assert bl.claimed_amount > bl.preauth_amount
    types = {d.doc_type for d in session.scalars(select(m.Document).where(m.Document.claim_id == bl.id))}
    assert "medical_report" not in types and "medical_bill" in types
    # clean: valid GSTIN equal to the provider's
    assert is_valid(by_inv["INV-DEMO-CLEAN"].gstin)
    assert by_inv["INV-DEMO-CLEAN"].gstin == session.get(m.Provider, claim("INV-DEMO-CLEAN").provider_id).gstin


def test_seeded_gstins_valid(session):
    seed(session)
    assert all(is_valid(h["tax_id"]) for h in sd.HOSPITALS.values() if h["tax_id"])
    assert all(is_valid(p.gstin) for p in session.scalars(select(m.Provider)) if p.gstin)
