"""Repositories over the seeded database return exactly the shapes the old in-memory store did (Req 1.2, 17.1)."""
import hashlib
import json

from sqlalchemy import select

from app.db import models as m
from app.db.repos import open_repos
from app.seed import seed_data as sd



def test_hospitals_doctors_policies_match_seed_data():
    with open_repos() as r:
        for hid, h in sd.HOSPITALS.items():
            assert r.hospital(hid) == h
        for did, d in sd.DOCTORS.items():
            assert r.doctor(did) == d
        for number, p in sd.POLICIES.items():
            assert r.policy(number) == p
        assert r.hospital("H999") is None and r.doctor("D999") is None and r.policy("POL-NOPE") is None


def test_doctors_at_lists_licensed_affiliates_in_seed_order():
    with open_repos() as r:
        for hid in sd.HOSPITALS:
            expected = {did: d for did, d in sd.DOCTORS.items() if hid in d["hospital_ids"] and d["license_valid"]}
            got = r.doctors_at(hid)
            assert got == expected and list(got) == list(expected)


def test_history_and_seen_invoices_match_seed_data():
    with open_repos() as r:
        for claimant, rows in sd.CLAIM_HISTORY.items():
            got = r.history(claimant)
            assert [{k: g[k] for k in ("claim_id", "date", "amount", "hospital_id", "invoice_number")} for g in got] == rows
        assert all(r.invoice_seen(h, n) for h, n in sd.SEEN_INVOICES)
        assert not r.invoice_seen("H001", "INV-NEVER")
        assert r.history("U404") == []


def test_unprocessed_demo_scenarios_are_not_prior_submissions():
    with open_repos() as r:
        for name, sc in sd.SCENARIOS.items():
            if sc["invoice_number"] != "INV-2002":  # high_risk reuses a number that history really contains
                assert not r.invoice_seen("H001", sc["invoice_number"])
                assert not r.invoice_seen("H004", sc["invoice_number"])
                assert not r.invoice_seen("H005", sc["invoice_number"])
        hashes = list(r.session.scalars(select(m.Document.sha256).where(m.Document.original_name_ref.like("seed:%"))))
        assert hashes and not r.seen_doc_hashes(hashes)


def test_register_claim_twice_is_idempotent_and_adds_new_hashes(client):
    from app.models import Claim
    from tests.test_assess_gate import _claim
    claim = Claim.model_validate(_claim())
    h1, h2 = (hashlib.sha256(x).hexdigest() for x in (b"one", b"two"))
    with open_repos() as r:
        r.register_claim(claim, [h1])
        r.register_claim(claim, [h1, h2])
        assert len([h for h in r.history("U001") if h["claim_id"] == claim.claim_id]) == 1
        assert r.seen_doc_hashes([h1, h2]) == {h1, h2}


def test_internal_reset_restores_seed_state(client, auth_headers):
    from tests.test_assess_gate import _claim, _post
    admin = auth_headers("Administrator")
    assert _post(client, _claim(), headers=admin, test_mode="true").status_code == 200
    with open_repos() as r:
        assert r.invoice_seen("H001", "INV-ASSESS-1")
    assert client.post("/api/internal/reset", headers=admin).json() == {"status": "reset"}
    with open_repos() as r:
        assert not r.invoice_seen("H001", "INV-ASSESS-1")
        assert [h["claim_id"] for h in r.history("U001")] == ["C-100"]
    assert client.post("/api/internal/reset").status_code == 401


def test_app_start_seeds_an_empty_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.db import session as db_session

    db_session.set_engine(db_session.make_engine("sqlite://"))  # empty: no tables yet
    monkeypatch.setattr(main, "SEED_STORAGE", tmp_path)
    with TestClient(main.app) as c:
        r = c.post("/api/policies/lookup", json={"policy_number": "POL-1001", "date_of_birth": "1992-04-18"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["holder_name"] == "A. Kumar" and len(body["network_hospitals"]) == 3
        assert json.dumps(body["not_covered"])
    assert any(tmp_path.rglob("medical_bill.pdf"))
