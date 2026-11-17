import hashlib
import json
import os
import secrets
import uuid
from collections import OrderedDict
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app import catalog, docgen, jobs
from app.config import load_env
from app.data import store
from app.models import Claim, ClaimSubmission, DocumentInfo, FraudAssessment

load_env()

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 10
ALLOWED_DOC_TYPES = {"medical_bill", "prescription", "medical_report", "other"}
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Claim Fraud Detection Agents")


# ---------------------------------------------------------------- helpers

async def _read_documents(documents: list[UploadFile], types: list[str]) -> list[DocumentInfo]:
    if len(documents) > MAX_FILES:
        raise HTTPException(413, f"At most {MAX_FILES} documents allowed")
    docs = []
    for i, up in enumerate(documents):
        data = await up.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"{up.filename} exceeds 10 MB")
        doc_type = types[i] if i < len(types) and types[i] in ALLOWED_DOC_TYPES else "other"
        docs.append(DocumentInfo(filename=(up.filename or "unnamed")[:200], content_type=up.content_type or "",
                                 size=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, doc_type=doc_type))
    return docs


def _verified_policy(policy_number: str, dob: date) -> dict:
    p = store.policy(policy_number.strip().upper())
    if not p or p["date_of_birth"] != dob.isoformat():
        raise HTTPException(404, "We couldn't find a policy with that number and date of birth.")
    return p


# ---------------------------------------------------------------- customer journey

class PolicyLookup(BaseModel):
    policy_number: str
    date_of_birth: date


@app.post("/api/policies/lookup")
async def lookup_policy(body: PolicyLookup):
    p = _verified_policy(body.policy_number, body.date_of_birth)
    hospitals = []
    for hid in p["network_hospital_ids"]:
        h = store.hospital(hid)
        doctors = [{"id": did, "name": d["name"], "specialty": d["specialty"], "qualification": d["qualification"]}
                   for did, d in store.doctors_at(hid).items()]
        hospitals.append({"id": hid, "name": h["name"], "city": h["city"], "address": h["address"],
                          "specialties": h["specialties"], "doctors": doctors})
    covered = set(p["covered_disease_ids"])
    disease = lambda k: {"id": k, "name": store.DISEASES[k]["name"], "category": store.DISEASES[k]["category"]}  # noqa: E731
    return {"policy_number": body.policy_number.strip().upper(), "holder_name": p["holder_name"], "plan": p["plan"],
            "sum_insured": p["sum_insured"], "valid_from": p["valid_from"], "valid_to": p["valid_to"],
            "network_hospitals": hospitals,
            "covered_diseases": [disease(k) for k in p["covered_disease_ids"]],
            "not_covered": [disease(k) for k in store.DISEASES if k not in covered]}


@app.post("/api/claims", status_code=202)
async def submit_claim(payload: str = Form(..., description="ClaimSubmission as JSON"),
                       documents: list[UploadFile] = File(default=[]),
                       document_types: str = Form("[]", description="JSON list of doc types, same order as documents"),
                       use_llm: bool = Form(True)):
    try:
        sub = ClaimSubmission.model_validate(json.loads(payload))
        types = json.loads(document_types)
        if not isinstance(types, list):
            raise ValueError("document_types must be a list")
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise HTTPException(422, f"Invalid claim: {e}")

    # Policy rules (not fraud signals): reject up front with a clear message.
    p = _verified_policy(sub.policy_number, sub.date_of_birth)
    if sub.hospital_id not in p["network_hospital_ids"]:
        raise HTTPException(422, "The selected hospital is not in your policy's network.")
    if sub.disease_id not in p["covered_disease_ids"]:
        raise HTTPException(422, "The selected condition is not covered by your policy.")
    if not store.doctor(sub.doctor_id):
        raise HTTPException(422, "Unknown doctor.")
    if sub.discharge_date < sub.admission_date:
        raise HTTPException(422, "Discharge date cannot be before admission date.")
    if sub.discharge_date > date.today():
        raise HTTPException(422, "Discharge date cannot be in the future.")
    if not (date.fromisoformat(p["valid_from"]) <= sub.admission_date <= date.fromisoformat(p["valid_to"])):
        raise HTTPException(422, "Admission date is outside your policy period.")
    if sub.claimed_amount > p["sum_insured"]:
        raise HTTPException(422, "Claimed amount exceeds your sum insured.")
    if not documents:
        raise HTTPException(422, "Please upload at least one document.")

    docs = await _read_documents(documents, types)
    claim = Claim(claim_id=f"CLM-{uuid.uuid4().hex[:10].upper()}", claimant_id=p["claimant_id"],
                  claimant_name=p["holder_name"], hospital_id=sub.hospital_id, doctor_id=sub.doctor_id,
                  diagnosis=store.DISEASES[sub.disease_id]["name"], admission_date=sub.admission_date,
                  discharge_date=sub.discharge_date, claimed_amount=sub.claimed_amount, invoice=sub.invoice,
                  policy_number=sub.policy_number.strip().upper(), disease_id=sub.disease_id)
    jobs.start(claim, docs, use_llm)
    return {"claim_id": claim.claim_id}


@app.get("/api/claims/{claim_id}/status")
async def claim_status(claim_id: str):
    job = jobs.JOBS.get(claim_id)
    if not job:
        raise HTTPException(404, "Claim not found")
    return jobs.customer_view(job)


# ---------------------------------------------------------------- demo data (journey ?demo=1)

DEMO_CASES: "OrderedDict[str, dict]" = OrderedDict()


@app.get("/api/demo/{kind}")
async def demo_case(kind: str):
    if kind not in ("clean", "suspicious"):
        raise HTTPException(404, "Unknown demo case")
    case = docgen.build_case(kind)
    token = uuid.uuid4().hex
    DEMO_CASES[token] = case
    while len(DEMO_CASES) > 50:
        DEMO_CASES.popitem(last=False)
    return {"form": docgen.form_payload(case),
            "documents": [{"doc_type": t, "filename": f"{t}.pdf", "url": f"/api/demo/{token}/{t}.pdf"}
                          for t in docgen.DOC_TYPES]}


@app.get("/api/demo/{token}/{doc_type}.pdf")
async def demo_document(token: str, doc_type: str):
    case = DEMO_CASES.get(token)
    if not case or doc_type not in docgen.DOC_TYPES:
        raise HTTPException(404, "Not found")
    return Response(docgen.render(case, doc_type), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc_type}.pdf"'})


# ---------------------------------------------------------------- internal console (key protected)

def require_internal_key(x_internal_key: str = Header(default="")):
    expected = os.getenv("INTERNAL_API_KEY")
    if not expected:
        raise HTTPException(503, "Internal console is disabled: set INTERNAL_API_KEY in .env")
    if not secrets.compare_digest(x_internal_key.encode(), expected.encode()):
        raise HTTPException(401, "Invalid internal key")


internal = [Depends(require_internal_key)]


@app.get("/api/internal/overview", dependencies=internal)
async def internal_overview():
    return {**catalog.overview(), "claims_processed": len(jobs.JOBS)}


@app.get("/api/internal/claims", dependencies=internal)
async def internal_claims():
    return [jobs.internal_summary(j) for j in sorted(jobs.JOBS.values(), key=lambda j: j["submitted_at"], reverse=True)]


@app.get("/api/internal/claims/{claim_id}", dependencies=internal)
async def internal_claim(claim_id: str):
    job = jobs.JOBS.get(claim_id)
    if not job:
        raise HTTPException(404, "Claim not found")
    return jobs.internal_detail(job)


@app.post("/api/internal/reset", dependencies=internal)
async def internal_reset():
    store.reset()
    jobs.reset()
    DEMO_CASES.clear()
    return {"status": "reset"}


# ---------------------------------------------------------------- direct assessment (scripts / Swagger)

@app.post("/api/assess", response_model=FraudAssessment)
async def assess(claim: str = Form(..., description="Claim as JSON"),
                 documents: list[UploadFile] = File(default=[]),
                 document_types: str = Form("[]"),
                 use_llm: bool = Form(True)):
    try:
        parsed = Claim.model_validate(json.loads(claim))
        types = json.loads(document_types)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, f"Invalid claim: {e}")
    docs = await _read_documents(documents, types if isinstance(types, list) else [])
    job = await jobs.run_sync(parsed, docs, use_llm)
    if job["status"] != "completed":
        raise HTTPException(500, "Assessment failed")
    return job["assessment"]


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- frontend (built React app)

if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    candidate = (FRONTEND / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = FRONTEND / "index.html"
    if not index.exists():
        return Response("Frontend not built. Run: cd frontend; npm install; npm run build", media_type="text/plain")
    return FileResponse(index)
