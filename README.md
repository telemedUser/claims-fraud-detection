# ClaimShield: Multi-Agent Claim Fraud Detection

A customer submits a health insurance claim. Four agents analyse it in parallel, and an orchestrator combines their scores into a 0-100 risk score and a routing decision.

## Pages

| URL | Who | What |
|---|---|---|
| `http://localhost:8000/` | Customer | Journey: policy lookup → network hospital, doctor and covered condition → bill details → documents → review and submit |
| `/claims/{id}/processing` | Customer | Live loading page showing each verification step |
| `/claims/{id}` | Customer | Claim report: outcome, neutral check status and next steps. No scores or findings |
| `/?demo=1` | Demo | Same journey with "Genuine claim" / "Suspicious claim" buttons that prefill data and attach generated PDFs |
| `/internal` | Internal | Fraud Intelligence Console: workflow, agent catalogue, every claim with full agent output. Not linked from the journey; requires a staff login (JWT, role-based; the login screen arrives with task 12.3) |
| `/docs` | Developers | Swagger for the API |

Demo policies (fictional): `POL-1001`, DOB `1992-04-18` (A. Kumar) and `POL-2002`, DOB `1985-09-02` (R. Singh).

## Agents

| Agent | Checks |
|---|---|
| `provider_profile` | Registry checks on the admission date (licence and expiry, affiliation dates, network period, GSTIN), a profile computed from claims data (volume surge, amount and peer outliers, flag rate with investigator decisions, similar bills, capacity, same day in another city), specialty fit, and documents against the registry. See [docs/agents/provider_profile.md](docs/agents/provider_profile.md) |
| `claimant_profile` (User Profile) | Earlier claims and outcomes: frequency, amount spikes and escalation, similar amounts, hospital hopping, re-claimed or overlapping stays, timing around policy start and term end, sum-insured use, earlier denied or referred claims. Console **Users** tab shows each person's full profile. See [docs/agents/user_profile.md](docs/agents/user_profile.md) |
| `document_scan` | Completeness, reuse, metadata, edits after generation (extra PDF revisions, bill modified after its date), AI-tool markers, printed patient, policy, dates, diagnosis and bill details against the claim. See [docs/agents/document_scan.md](docs/agents/document_scan.md) |
| `invoice_check` | Arithmetic and plausibility, GSTIN check digit and GST lines, duplicate and re-numbered bills, payment status (cashless, balance due, claimed above paid, receipt). See [docs/agents/invoice_check.md](docs/agents/invoice_check.md) |
| `medical_review` | ICD-10 codes against the diagnosis, medicines against the diagnosis, lab report tamper check by report number, treatment against the diagnosis. See [docs/agents/medical_review.md](docs/agents/medical_review.md) |

The agents are deterministic rule engines, and the score and queue come from their findings. The **LLM analysis** switch in the console header (Administrator only, audited) turns the LLM on or off for every claim submitted after the change. When it is on:
- each agent gets a Gemini review with lookup tools, which adds AI observations and reasoning. Observations are scored as potential anomalies (capped at 15 points per agent and 25 per claim, so the LLM alone cannot queue a claim)
- the investigator summary is written by Gemini

Details and guardrails are in [docs/llm_usage.md](docs/llm_usage.md). Changes are logged in [docs/CHANGELOG.md](docs/CHANGELOG.md).

- **Score:** additive and saturating: severity points x status multiplier summed over de-duplicated findings, capped at 100 (`app/core/scoring.py`, `app/rules/risk_scoring.v1.yaml`).
- **Decision:** routing queue (a recommendation, not a decision): `<30` low risk, `30-59` manual review, `>=60` investigate (`app/pipeline.py`).
- **Policy rules** are enforced before scoring, and violations return 422: hospital in network, condition covered, admission inside the policy period, claimed amount within sum insured.

## Configuration (`.env`, git-ignored)

```
GEMINI_API_KEY=...          # required for LLM analysis; then the console switch decides (default: LLM_REVIEW_ENABLED=true)
GEMINI_MODEL=...            # optional comma-separated fallback chain
JWT_SECRET=...              # required: signs login tokens; the app refuses to start without it
SEED_USER_PASSWORD=...      # seeds investigator / ops_manager / fraud_team / admin (or SEED_PASSWORD_<ROLE>)
# Roles: /api/internal/* all four roles; /api/internal/reset Administrator; /api/assess Investigator, Fraud_Team, Administrator
```

## Local login

`POST /api/auth/login` (`{"username", "password"}`) returns a 30-minute bearer token; `GET /api/me` shows the caller. Set `JWT_SECRET` first (login returns 503 without it).
The seed creates one user per role: `investigator`, `ops_manager`, `fraud_team`, `admin`. Passwords are never in code. Set `SEED_PASSWORD_INVESTIGATOR`, `SEED_PASSWORD_OPS_MANAGER`, `SEED_PASSWORD_FRAUD_TEAM`, `SEED_PASSWORD_ADMIN`, or one shared `SEED_USER_PASSWORD`, before seeding. For throwaway local use only, `DEV_SEED_DEFAULT_PASSWORDS=true` gives each user the password `dev-only-<username>-password`. Users with no configured password are not created. Seeding never overwrites an existing user.

## Run

```powershell
pip install -r requirements.txt
cd frontend; npm install; npm run build; cd ..     # React app -> frontend/dist
uvicorn app.main:app --port 8000                   # serves API + UI on :8000
```

Frontend development with hot reload: run the API as above, then `cd frontend; npm run dev` and open http://localhost:5173. Vite proxies `/api` to port 8000.

Stack: FastAPI (Python) backend; React 19, TypeScript, Vite, Tailwind CSS v4, React Router, Motion and Lucide icons on the frontend.

## Tests and tools

| Command | Purpose |
|---|---|
| `python -m scripts.smoke_api` | In-process API test (no server, rules only) |
| `python scripts/ui_e2e.py` | Browser test of the journey and console (Edge via Playwright); screenshots in `ui_screens/` |
| `python scripts/generate_test_docs.py` | Writes bill, prescription, report and `claim.json` to `test_documents/{clean,suspicious}` |
| `python scripts/submit_test_docs.py all` | Submits those sets to `/api/assess` |
| `python scripts/provider_profile_demo.py` | Provider Profile checks on the demo scenarios plus one targeted case per check (own in-memory database) |

Data is in memory. Use **Reset demo data** in the console to clear claims and restore the seeded history.

## Extend
- Real data: replace the seed in `app/seed/` (and the repositories in `app/db/repos.py`) with your registries, policy admin system and claims DB.
- Jobs: replace `app/jobs.py` (in-memory) with a queue and a database.
- Invoice OCR: extract bill fields from the uploaded documents (e.g. Amazon Textract) and compare them with what the customer entered.
- New agent: subclass `Agent`, add it to `AGENTS` in `app/pipeline.py` and to `app/catalog.py`.
