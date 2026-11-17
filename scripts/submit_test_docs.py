"""Submits test_documents/<case>/claim.json with its three PDFs to the running API (direct /api/assess).
Usage: python scripts/submit_test_docs.py [clean|suspicious|all] [use_llm=true|false]"""
import json
import sys
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent / "test_documents"
which = sys.argv[1] if len(sys.argv) > 1 else "all"
use_llm = sys.argv[2] if len(sys.argv) > 2 else "true"
TYPES = ["medical_bill", "prescription", "medical_report"]

for case in (["clean", "suspicious"] if which == "all" else [which]):
    d = root / case
    files = [("documents", (f"{t}.pdf", (d / f"{t}.pdf").read_bytes(), "application/pdf")) for t in TYPES]
    r = httpx.post("http://127.0.0.1:8000/api/assess", timeout=240, files=files,
                   data={"claim": (d / "claim.json").read_text(encoding="utf-8"), "use_llm": use_llm,
                         "document_types": json.dumps(TYPES)})
    print(f"===== {case}: HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        continue
    j = r.json()
    print(f"risk {j['risk_score']}  decision {j['decision']}  ({j['orchestration']['total_duration_ms']:.0f} ms)")
    for a in j["agent_results"]:
        print(f"- {a['agent']}: {a['score']:.0f} (rules {a['rule_score']:.0f} + LLM {a['llm_points']:.0f})"
              f"  tools={a['tool_calls']}")
        for f in a["findings"]:
            print(f"    [{f['source']}/{f['severity']}] {f['code']}: {f['detail'][:140]}")
        if a["reasoning"] and not a["llm_used"]:
            print("    note:", a["reasoning"][:160])
