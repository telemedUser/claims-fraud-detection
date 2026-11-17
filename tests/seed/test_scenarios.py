"""Demo scenarios route as specified (Req 1.3, 1.4, 20.6). Seed idempotency: see test_seed.py."""
import asyncio
import hashlib

import pytest

from app.models import Claim, DocumentInfo
from app.pipeline import assess_claim
from app.seed import docgen, seed_data as sd

EXPECTED_QUEUE = {"clean": {"low"}, "high_risk": {"investigate"}, "borderline": {"manual_review"},
                  "fabricated": {"manual_review", "investigate"}}


def build_scenario(name: str):
    """Legacy Claim and DocumentInfo list for a seeded scenario (same case the seed stores)."""
    sc = sd.SCENARIOS[name]
    case = docgen.build_case(sc["case"])
    case["invoice_number"] = sc["invoice_number"]
    claim = Claim(**docgen.claim_json(case, f"SC-{name}"))
    docs = []
    for doc_type in case["doc_types"]:
        data = docgen.render(case, doc_type)
        docs.append(DocumentInfo(filename=f"{doc_type}.pdf", content_type="application/pdf", size=len(data),
                                 sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=doc_type))
    return claim, docs


def _run(name: str):
    claim, docs = build_scenario(name)
    result = asyncio.run(assess_claim(claim, docs, use_llm=False, register=None))
    codes = sorted(f.code for a in result.agent_results for f in a.findings)
    print(f"{name}: score={result.risk_score} queue={result.recommended_queue} findings={codes}")
    return result


@pytest.mark.parametrize("name", list(sd.SCENARIOS))
def test_scenario_routes_as_expected(name):
    result = _run(name)
    assert result.recommended_queue in EXPECTED_QUEUE[name]
    if sd.SCENARIOS[name]["expected"] == "not_low":
        assert result.recommended_queue != "low"
    else:
        assert result.recommended_queue == sd.SCENARIOS[name]["expected"]
