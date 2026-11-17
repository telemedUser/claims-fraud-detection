"""In-process API smoke test (no server needed). Usage: python -m scripts.smoke_api [use_llm=false]"""
import json
import os
import sys
import time

from fastapi.testclient import TestClient

from app.main import app

use_llm = sys.argv[1] if len(sys.argv) > 1 else "false"
key = {"X-Internal-Key": os.environ["INTERNAL_API_KEY"]}

with TestClient(app) as c:
    print("health", c.get("/api/health").json())
    print("bad dob", c.post("/api/policies/lookup", json={"policy_number": "POL-1001", "date_of_birth": "2000-01-01"}).status_code)
    pol = c.post("/api/policies/lookup", json={"policy_number": "pol-1001", "date_of_birth": "1992-04-18"}).json()
    print("policy", pol["holder_name"], [h["id"] for h in pol["network_hospitals"]], len(pol["covered_diseases"]), "covered,",
          len(pol["not_covered"]), "not covered")
    print("internal no key", c.get("/api/internal/overview").status_code)

    for kind in ("clean", "suspicious"):
        demo = c.get(f"/api/demo/{kind}").json()
        files = [("documents", (d["filename"], c.get(d["url"]).content, "application/pdf")) for d in demo["documents"]]
        types = [d["doc_type"] for d in demo["documents"]]
        r = c.post("/api/claims", data={"payload": json.dumps(demo["form"]), "document_types": json.dumps(types),
                                        "use_llm": use_llm}, files=files)
        print(kind, "submit", r.status_code, r.json())
        cid = r.json()["claim_id"]
        for _ in range(240):
            s = c.get(f"/api/claims/{cid}/status").json()
            if s["status"] != "processing":
                break
            time.sleep(0.5)
        rep = s.get("report", {})
        print("  status", s["status"], "|", rep.get("outcome", {}).get("title"), "|",
              [(x["label"], x["outcome"]) for x in rep.get("checks", [])])
        det = c.get(f"/api/internal/claims/{cid}", headers=key).json()
        print("  internal", det["risk_score"], det["decision"], "events", len(det["events"]))
        for a in det["assessment"]["agent_results"]:
            print("   ", a["agent"], a["score"], [f["code"] for f in a["findings"]])

    bad = c.get("/api/demo/clean").json()["form"]
    bad["hospital_id"] = "H003"
    r = c.post("/api/claims", data={"payload": json.dumps(bad)}, files=[("documents", ("x.pdf", b"%PDF-1.4", "application/pdf"))])
    print("non-network hospital", r.status_code, r.json())
    print("claims list", len(c.get("/api/internal/claims", headers=key).json()))
    print("overview agents", [a["name"] for a in c.get("/api/internal/overview", headers=key).json()["agents"]])
    print("spa", c.get("/").status_code, c.get("/internal").status_code, c.get("/api/nope").status_code)
