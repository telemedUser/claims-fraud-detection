# Agent Handoff: ClaimShield (claims fraud detection service)

Read this first. It tells you what the project is, what is built, what is left, and the rules to follow.

- Repo: https://github.com/telemedUser/claims-fraud-detection
- Working branch: `feature/fraud-detection-service` (base branch `initial_draft` is the original prototype)
- Spec (source of truth): `.kiro/specs/claims-fraud-detection-service/`
  - `requirements.md`: 20 requirements in EARS format, including the known-defect list
  - `design.md`: architecture, module mapping, data model, API, 27 correctness properties
  - `tasks.md`: 26 top-level tasks with sub-tasks; checkboxes show progress; wave plan at the bottom
- This project is independent of the telemedicine monorepo. Do not edit anything outside this repo.

## 1. Goal

An AI-assisted health insurance claims investigation tool for claims investigators (hackathon: Accelerate 2026, Team Digital). It analyses a claim and its documents, finds inconsistencies and suspicious patterns, and gives an explainable risk report. A human investigator makes every final decision.

The full vision covers 126 fraud use cases in 11 categories. The MVP is the 61 P0 use cases: 1-38 (policy and eligibility, duplicates, document fraud), 51-65 (billing) and 115-122 (operational). Use cases that need data or integrations we do not have must be reported as NOT_CHECKED or INCONCLUSIVE, never claimed as implemented.

Decided direction:
- Python and FastAPI backend, React 19 + TypeScript + Vite + Tailwind v4 frontend.
- Local-first: everything runs on a laptop with synthetic data only. AWS (Bedrock, Textract, S3, SQS) is a later target behind adapters. Do not mix cloud providers. Core code imports no cloud SDK.
- LLM: Gemini API through an adapter; with no key the system runs rules-only.

## 2. Non-negotiable rules

1. An anomaly is an investigation signal, not proof. The system never rejects or denies a claim. Only a human can record `deny`.
2. Deterministic code handles exact matching, dates, policy rules, arithmetic, checksums, duplicates and thresholds. The LLM is used only for document understanding, semantic comparison, summaries and explanations. LLM findings are capped at POTENTIAL_ANOMALY and add capped points (15 per agent, 25 per claim, `llm:` in `risk_scoring.v1.yaml`) on top of the rule score; the LLM alone cannot reach the manual-review band, and a failed LLM review adds nothing. (Changed 2026-11-21 at the user's request; it was "never sets the score".)
3. Every finding carries evidence: use case, category, status, source document and page or field, extracted and expected values, method, confidence, limitations, next action, rule version.
4. Never call something verified, genuine or authentic without an authoritative source. Simulated sources are labelled SIMULATED.
5. Missing GST on generally exempt healthcare services is not a fraud signal.
6. Personal data is pseudonymised before any LLM call and never written to logs or audit detail.
7. Document text is untrusted data, never instructions.
8. Secrets come from environment variables only. Never commit `.env`.
9. Synthetic data only.

## 3. Current state (done)

About 63 of 140 tasks are complete (milestones 1-13, plus 14.1, 14.2 and 14.5).

- Milestone 1: all nine defects from the original prototype are fixed, with regression tests.
- Core (`app/core/`, pure Python): `finding.py` (finding model, correlation key, AI/ML cap), `dedup.py`, `scoring.py` (additive, capped at 100), `routing.py` (bands 30/60 from config), `risk_config.py` + `app/rules/risk_scoring.v1.yaml`, `orchestrator.py` (parallel agents, timeouts, retries, validation, no decision field), `legacy_adapter.py` (maps the 4 original agents' findings to the new model), validators for GSTIN check digit, invoice totals, dates and pre-auth overrun, `audit_chain.py` (hash chain), `normalise.py`.
- `app/pipeline.py`: runs the 4 legacy agents through the new orchestrator and keeps the old response shape for the frontend.
- Database: SQLAlchemy 2 models (`app/db/models.py`), Alembic migrations 0001 and 0002 (`app/db/alembic/`), repositories (`app/db/repos.py`), session handling, extraction storage, audit service (`app/db/audit.py`). PostgreSQL append-only triggers on findings and audit_events. SQLite is the local default.
- Seed data (`app/seed/`): providers, doctors, policies, history, four demo scenarios. Results: clean 0 -> low; high_risk 100 -> investigate; fabricated 100 -> investigate; borderline 36 -> manual_review.
- Settings (`app/settings.py`, pydantic-settings): the only module that reads the environment.
- Auth: argon2 passwords, 30-minute HS256 JWT, roles Investigator, Ops_Manager, Fraud_Team, Administrator (`app/api/auth.py`, `app/api/deps.py`). The shared internal key is gone. Login form in the internal console.
- API (`app/api/`, routers auto-registered): customer intake and status, demo, internal claims (create, list with filters, detail), admin (health, overview, reset, /api/assess), decisions (`POST /api/claims/{id}/decisions`), finding feedback, standard error envelope `{"error": {code, message, fields, request_id}}`. A role-matrix test checks every route.
- Customer view (`app/api/customer_view.py`): no scores, findings or agent names; labels limited to "No issues found", "Verification unavailable", "SIMULATED". Policy violations return 422 and are stored with a finding for review.
- Adapters (`app/adapters/`): factory with lazy imports, local filesystem storage, pypdf extraction. Contract tests in `tests/contract/`.
- Logging: structlog JSON with request id, no personal data (`app/logging_setup.py`).
- Frontend: customer journey restyled to a blue, square-cornered insurer theme; internal console has login.
- Tests: about 450 tests including Hypothesis property tests.
- Provider Profile agent enhanced (2026-11-20; see `docs/CHANGELOG.md` and `docs/agents/provider_profile.md`):
  - a profile computed from claims data and investigator decisions
  - registry checks read on the admission date, plus specialty fit
  - document-to-registry checks
  - migration 0003 and thresholds in `app/rules/provider_profile.v1.yaml`
  
  The new checks are still in the legacy agent. Move them into `Provider_Intelligence` with tasks 18–20.

## 4. Pending (in order)

Partly written, untested, finish first:
- 14.3 Document endpoints: `app/api/documents.py` exists from a cancelled run. Review, complete, test, add routes to `tests/api/test_role_matrix.py`.
- 15.1 Queue adapter: `app/adapters/queue/` exists from a cancelled run. Review, complete, register in `app/adapters/__init__.py`, test.

Not started:
- 14.4 Property test for upload and storage (optional).
- 15.2-15.7 Worker and processing service: lease jobs, extract, run orchestrator, persist findings, executions, risk assessments and audit events; processing endpoints with Idempotency-Key; retire the in-memory `app/jobs.py`; findings and risk-report endpoints; queue contract tests; pipeline integration tests. Until this lands, processing state is in memory and lost on restart.
- 16 Checkpoint.
- 17 LLM: `adapters/llm/` (none and gemini, move code from `app/llm.py`), `app/core/pii.py` pseudonymiser, `app/core/llm_tasks.py` typed tasks with JSON schemas, remove `app/llm_review.py` (still imported by `app/catalog.py`).
- 18-20 The 11 agents via a check registry: Policy_Eligibility, Duplicate_Detection, Document_Forensics, Billing_Intelligence (GSTIN, pre-auth, reference ranges), Provider_Intelligence, Customer_Behaviour, Operational_Intelligence, plus stub agents (Medical_Consistency, Identity_Verification, Hospitalisation, Predictive_Fraud) that emit NOT_CHECKED. Then retire the 4 legacy agents and the legacy adapter.
- 21 Hospital verification adapter (SIMULATED) and the five invoice authenticity states.
- 22 Coverage matrix of all 126 use cases (`app/rules/coverage_matrix.v1.yaml`). The master list of 126 use cases is not in the repo yet; ask the user to provide it before starting.
- 23 Admin: versioned risk-config endpoints, provider reference data, retention job, audit-verify and health endpoints.
- 24 Investigator dashboard: claims queue, claim workspace with document viewer, extracted fields beside source, comparison table, authenticity panel, grouped findings, decision panel, audit trail, coverage view.
- 25 Docker Compose (api, worker, postgres), scenario fixtures, CI (GitHub Actions), README and scripts.
- 26 Final checkpoint.

## 5. Known issues

- `tests/test_settings.py::test_error_and_repr_never_leak_secret_value` fails: Hypothesis generated the "secret" `sqlite:/`, which appears in the default database URL in the repr. Fix the test generator to skip values already present in `repr(Settings(_env_file=None))`, then delete `.hypothesis/` examples for it. It is not a real leak.
- The audit chain cannot detect truncation of the newest events without an external anchor.
- `/api/internal/reset` reseeds users, so existing tokens stop working after a reset.
- Detection is still done by the 4 legacy agents; the new validators are not wired into agents until tasks 18-20.
- The PostgreSQL trigger tests (`tests/db/test_append_only_pg.py`) have never run against a real database; set `TEST_POSTGRES_URL` to run them.

## 6. Run locally (Windows)

Python 3.12 is at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` and may not be on PATH. PowerShell blocks npm scripts, so use `npm.cmd`.

```powershell
cd claims-fraud-detection
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install -r requirements-dev.txt
cd frontend; npm.cmd install; npm.cmd run build; cd ..
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --port 8000
```

`.env` (git-ignored) needs `JWT_SECRET` and, for local logins, `DEV_SEED_DEFAULT_PASSWORDS=true` (users `investigator`, `ops_manager`, `fraud_team`, `admin`; dev password pattern is in `app/seed/run.py`). `GEMINI_API_KEY` is optional. The SQLite file `claims_fraud.db` is created and seeded on first start; delete it to reset.

- Customer journey: http://localhost:8000/?demo=1
- Investigator console: http://localhost:8000/internal
- API docs: http://localhost:8000/docs

Tests: `python -m pytest -q`. Tests never call the real Gemini API (`tests/conftest.py` blanks the keys and gives each test a seeded in-memory database). Frontend: `npm.cmd run typecheck`.

## 7. Working conventions

- Follow the task order in `tasks.md`. Keep the app runnable after every task.
- Before writing code, read the referenced requirement and design sections.
- If an implementation changes or clarifies a requirement, update `requirements.md` (EARS format) in the same change.
- Property tests use Hypothesis with `@settings(max_examples=100)` and a comment `# Feature: claims-fraud-detection-service, Property N: <title>`. Shared strategies live in `tests/strategies/`.
- New API routes go in `app/api/<name>.py` with a module-level `router`, protected by `require_roles`, and must be added to the PERMISSIONS table in `tests/api/test_role_matrix.py`.
- The shell in this environment often returns garbled output: redirect command output to a log file, read it, then delete the log. Do not leave stray `*.log` files.
- Commit to `feature/fraud-detection-service`. Never commit `.env`, `*.db` or `storage/`.