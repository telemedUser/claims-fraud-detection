# Implementation Plan: ClaimShield (claims-fraud-detection-service)

## Overview

This plan evolves the existing repository at `claims-fraud-detection` in place. It never rewrites from scratch. The implementation language is Python 3.12 (FastAPI backend) and TypeScript (React 19 frontend), as chosen in the design.

Delivery follows the design's incremental order and keeps the app runnable after every top-level task:

1. Quick wins that fix the nine known defects in the current code (task 1).
2. Pure `core/` package: findings, dedup, scoring, routing, validators, orchestrator (tasks 3-6).
3. Database, repositories, seed and audit chain (tasks 8-10).
4. Authentication and RBAC, claims API, documents, queue and worker (tasks 12-15).
5. Adapters and LLM tasks with PII minimisation (task 17).
6. Check registry, the 11 agents, authenticity, coverage matrix, admin APIs, dashboard, packaging (tasks 18-25).

Environment notes for every task:

- Windows dev machine. Python 3.12 is at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` and is not on PATH in the agent shell. Call it by full path, for example `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest`.
- Invoke npm as `npm.cmd` (PowerShell script execution is disabled). Use `npm.cmd test -- --run` style single-run commands, never watch mode.
- Docker Desktop is installed. `GEMINI_API_KEY` lives in the git-ignored `.env`. Automated tests MUST NOT call the real Gemini API. Use the `none` adapter, fakes or `httpx.MockTransport`.
- Hypothesis tests use `@settings(max_examples=100)` at minimum and carry the comment `# Feature: claims-fraud-detection-service, Property N: <title>`. Define strategies in the test module or in `tests/strategies/<topic>.py` so parallel tasks do not edit the same file.
- Routers under `app/api/` are auto-registered by `app/api/__init__.py` (set up in task 13.1), so new router modules need no edit to `main.py`.

## Tasks

- [x] 1. Milestone 1: quick wins that fix the known defects
  - [x] 1.1 Set up the test harness and characterise the current API
    - Add `requirements-dev.txt` (pytest, pytest-asyncio, hypothesis, httpx, freezegun) and `pytest.ini` with markers `check_id`, `postgres`, `live_llm`
    - Create `tests/conftest.py` that forces `LLM` off (no Gemini key in test env) and registers the `check_id` marker
    - Add smoke tests with FastAPI `TestClient` for health, policy lookup, customer claim submission and status so later tasks can prove the app still runs
    - _Requirements: 20.2, 20.8_

  - [x] 1.2 Remove "Verified" wording from customer output (defect 1)
    - Delete `VERIFIED_BELOW` and rewrite `OUTCOMES` text in `app/jobs.py` to "received" language
    - Limit customer check labels to "No issues found", "Specialist review" (was "Verification unavailable") or "SIMULATED"
    - Update `frontend/src/pages/ReportPage.tsx` and journey pages that show "Verified" or "passed all automated checks"
    - _Requirements: 8.3, 8.4, 8.5_

  - [x] 1.3 Drop TAX_ID_MISSING and give duplicate invoices a single owner (defects 2 and 3)
    - Remove `TAX_ID_MISSING` from `app/agents/invoice_check.py`
    - Remove `REPEATED_INVOICE_NUMBER` from `app/agents/claimant_profile.py`; keep `DUPLICATE_INVOICE` as the one duplicate-invoice finding
    - _Requirements: 11.6, 12.5_

  - [x] 1.4 Make the LLM flag server-controlled (defects 5 and 6, partial)
    - Remove `use_llm` from the customer form handling in `app/main.py` and from the frontend submission in `frontend/src/api.ts` and the journey form
    - Read the LLM on/off setting from server configuration only
    - _Requirements: 8.2_

  - [x] 1.5 Gate `/api/assess` (defect 7)
    - Require the existing internal credential until real auth lands in task 12
    - Run the same policy checks as claim processing
    - Write to claim history only with `?test_mode=true` and label the record `is_test=true`
    - _Requirements: 7.6, 7.7, 7.8_

  - [x] 1.6 Rate-limit policy lookup (defect 8)
    - Add `app/ratelimit.py`: sliding-window limiter with an injectable clock, keyed by client IP and by policy number, configured by `LOOKUP_RATE`
    - Apply it to `/api/policies/lookup` in `app/main.py`, returning 429 with `Retry-After`
    - _Requirements: 7.9_

  - [x]* 1.7 Write property test for the lookup rate limiter
    - **Property 25: Lookup rate limiting**
    - **Validates: Requirements 7.9**

  - [x] 1.8 Fix document forensics rules (defect 9)
    - In `app/agents/document_scan.py` match editor software by an exact producer allow-list, not substrings such as "word" or "libreoffice"
    - Apply `DOC_CREATED_BEFORE_ADMISSION` per document type (none for prescriptions and pre-admission reports)
    - Use a configurable modification gap per document type and cap severity at medium
    - Add alternative explanations to the finding detail
    - _Requirements: 13.2, 13.3, 13.4, 13.5_

  - [x]* 1.9 Write property test for forensics indicators
    - **Property 19: Forensics indicators are exact, low severity and never confirmed**
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5, 20.4**

  - [x] 1.10 Write defect regression tests
    - One test per defect: no "Verified" text, no `TAX_ID_MISSING`, one duplicate-invoice finding, LLM flag ignored from the client, `/api/assess` rejects anonymous calls and skips history, lookup returns 429 over the rate, forensics rules from task 1.8
    - Each rule gets a triggering and a non-triggering case
    - _Requirements: 20.1, 8.4, 11.6, 12.5, 8.2, 7.6, 7.8, 7.9, 13.4_

- [x] 2. Checkpoint - Milestone 1
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Core finding model and deduplication
  - [x] 3.1 Create `app/core/finding.py`
    - `FindingStatus`, `DetectionMethod`, `FactKey`, `FindingDraft`, `Finding` (immutable) as in the design
    - Correlation key = sha256 of `fact_type | canonical_json(subject) | canonical_json(normalised_values)`
    - Status normaliser: AI or ML drafts never exceed POTENTIAL_ANOMALY; exactly one status per finding
    - NOT_CHECKED findings use `fact_key=("not_checked", check_id)`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Create `app/core/dedup.py`
    - Group by correlation key, keep the highest `(status_rank, severity_rank)`, union `contributing_checks`, sources and use case ids
    - Deterministic and order independent
    - _Requirements: 4.6, 5.4, 12.5_

  - [x]* 3.3 Write property test for the AI/ML status cap
    - **Property 7: AI and ML findings are capped**
    - **Validates: Requirements 3.2, 3.3, 10.6**

  - [x] 3.4 Write property test for deduplication
    - Create the `findings()` strategy with controllable key collisions in `tests/strategies/findings.py`
    - **Property 4: Deduplication is idempotent, order independent and counts a fact once**
    - **Validates: Requirements 4.6, 5.4, 12.5**

- [x] 4. Risk scoring and routing
  - [x] 4.1 Add risk configuration and loader
    - Create `app/rules/risk_scoring.v1.yaml` as in the design and `app/core/risk_config.py` (pydantic model, YAML load and dump)
    - Reject bands that violate `0 < review_at < investigate_at <= 100`
    - _Requirements: 5.1, 5.6_

  - [x] 4.2 Implement `app/core/scoring.py` and `app/core/routing.py`
    - `score(findings, config)` returns the score and per-finding contributions; only CONFIRMED_RULE_VIOLATION and POTENTIAL_ANOMALY count; `min(100, round(sum, 1))`
    - Return NOT_CHECKED, INFORMATIONAL and INCONCLUSIVE in a separate not-scored list
    - `route(score, bands)` returns low, manual_review or investigate; include the "ordering signal, not a probability" label
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 4.3 Write property test for score bounds and determinism
    - **Property 1: Score is bounded, deterministic and explained**
    - **Validates: Requirements 5.1, 5.2, 5.5**

  - [x] 4.4 Write property test for score monotonicity
    - **Property 2: Score is monotone in added evidence**
    - **Validates: Requirements 5.1, 5.4**

  - [x] 4.5 Write property test for unscored statuses
    - **Property 3: Unscored statuses never change the score**
    - **Validates: Requirements 5.3**

  - [x] 4.6 Write property test for routing boundaries
    - **Property 5: Routing is total and respects band boundaries**
    - Include the default boundary examples 29.9, 30.0, 59.9, 60.0
    - **Validates: Requirements 5.6**

  - [x]* 4.7 Write property test for risk config round trip
    - **Property 6: Risk configuration round trip and validation**
    - **Validates: Requirements 5.1, 5.6, 5.7**

- [x] 5. Deterministic validators
  - [x] 5.1 Implement `app/core/validators/gstin.py`
    - `is_valid`, `check_char(first14)`: format regex, state code 01-38 and 97, `Z` at position 14, mod-36 check character
    - _Requirements: 11.5_

  - [x] 5.2 Implement `app/core/validators/totals.py` and `dates.py`
    - `totals.recompute` and `totals.differs` using `Decimal`; `dates.in_window`; `preauth.overrun(final, preauth, pct)`
    - _Requirements: 11.2, 11.3, 11.4, 11.7_

  - [x] 5.3 Write property test for GSTIN check character
    - **Property 14: GSTIN check character round trip**
    - Strategy `gstin_base()` in `tests/strategies/gstin.py`
    - **Validates: Requirements 11.5**

  - [x]* 5.4 Write property test for invoice total recomputation
    - **Property 16: Invoice totals are recomputed exactly**
    - **Validates: Requirements 11.7**

  - [x]* 5.5 Write property test for policy date and pre-authorisation rules
    - **Property 17: Policy date and pre-authorisation rules**
    - **Validates: Requirements 11.2, 11.3, 11.4**

- [x] 6. Core orchestrator over the existing agents
  - [x] 6.1 Add a legacy adapter in `app/core/legacy_adapter.py`
    - Convert the current agents' `Finding` objects into `FindingDraft` with `fact_type`, `method` and `status` so existing agents keep working
    - _Requirements: 3.1, 3.2, 4.5_

  - [x] 6.2 Replace `app/orchestrator.py` with `app/core/orchestrator.py`
    - `async assess(ctx, registry, config, adapters)` with no DB access
    - Run agents with `asyncio.gather` and `asyncio.to_thread`, per-agent `asyncio.wait_for` timeout, retry up to `AGENT_RETRIES`, and one `AgentExecution` record per attempt
    - Validate drafts against the schema, discard invalid output with an error record, cap AI/ML, dedup, score, route
    - Set `needs_human_review` when any INCONCLUSIVE exists and the band is low
    - Result has only `recommended_queue` and `needs_human_review`; claim status is ASSESSED, NEEDS_HUMAN_REVIEW or OPEN_INVESTIGATION
    - Remove `WEIGHTS`, `PEAK_FACTOR` and hardcoded thresholds
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1_

  - [x] 6.3 Wire the new orchestrator into `app/main.py` and `app/jobs.py`
    - Keep the customer and internal response shapes the frontend uses today
    - The app must stay runnable and the task 1 tests must still pass
    - _Requirements: 4.1, 4.8, 5.1, 5.5_

  - [x]* 6.4 Write property test that the orchestrator never denies
    - **Property 9: Orchestrator never emits deny or reject**
    - **Validates: Requirements 4.8**

  - [x]* 6.5 Write property test for human review on inconclusive findings
    - **Property 10: Inconclusive findings on a low band force human review**
    - **Validates: Requirements 4.7**

- [x] 7. Checkpoint - Core logic in place
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Settings, database models and migrations
  - [x] 8.1 Add `app/settings.py` (pydantic-settings) and update `requirements.txt`
    - Replace `app/config.py` usage; fail fast naming any missing required variable (for example `JWT_SECRET`) without printing its value; still read `.env` in dev
    - Add sqlalchemy, alembic, psycopg, pydantic-settings, argon2-cffi, pyjwt, pyyaml, structlog
    - _Requirements: 1.5, 1.6, 1.7_

  - [x] 8.2 Create `app/db/session.py` and `app/db/models.py`
    - All tables from the design's data model with UUIDv4 keys and JSON with JSONB variant on PostgreSQL
    - Unique `(claim_id, sha256)` on documents and unique `(claim_id, idempotency_key)` on `processing_runs`
    - _Requirements: 17.1, 16.5, 9.7, 4.9_

  - [x] 8.3 Add Alembic and the initial migration
    - `app/db/alembic/` env and a migration creating all tables
    - PostgreSQL triggers that block UPDATE and DELETE on `findings` and `audit_events`
    - _Requirements: 3.6, 17.5, 17.8_

  - [x] 8.4 Write unit tests for settings
    - Missing required variable stops startup with an error naming the variable and not its value
    - _Requirements: 1.6_

  - [x]* 8.5 Write PostgreSQL tests for append-only triggers
    - Marked `@pytest.mark.postgres`; UPDATE and DELETE on `findings` and `audit_events` fail
    - _Requirements: 3.6, 17.8_

- [x] 9. Repositories and seed data
  - [x] 9.1 Implement `app/db/repos.py`
    - Provider, Policy, Claim and history, Invoice repositories replacing the in-memory accessors and `SEEN_*` sets in `data/store.py`
    - _Requirements: 17.1, 12.1_

  - [x] 9.2 Move seed data and the document generator
    - Create `app/seed/seed_data.py` from `data/store.py` data and move `docgen.py` to `app/seed/docgen.py` (use the relocate tool so imports update)
    - Create `app/seed/run.py`: idempotent seed of policies, providers, doctors, claims and documents, including the four demo scenarios (clean, high-risk, fabricated-looking, borderline)
    - _Requirements: 1.3, 1.4_

  - [x] 9.3 Switch agents and `main.py` reads from `store.py` to repositories
    - Remove `data/store.py` once nothing imports it
    - _Requirements: 1.2, 17.1_

  - [x] 9.4 Write seed and scenario tests
    - Seed is idempotent; the clean claim routes low; the high-risk claim routes investigate; the borderline claim routes manual review
    - _Requirements: 1.3, 1.4, 20.6_

- [x] 10. Audit log
  - [x] 10.1 Implement `app/core/audit_chain.py`
    - `hash = sha256(prev_hash || canonical_json(ts, actor_id, event_type, entity_type, entity_id, request_id, detail))` and a pure `verify_chain(events)` returning the first mismatching `seq` or `None`
    - _Requirements: 17.5, 17.6_

  - [x] 10.2 Implement the audit service and structured logging
    - `app/db/audit.py`: insert with `pg_advisory_xact_lock`, helpers for login, claim access, document access, processing, config change, decision and denied events
    - Configure `structlog` with request id, user id and event type only; no PII or document content
    - _Requirements: 17.4, 17.7, 17.8_

  - [x]* 10.3 Write property test for audit chain integrity
    - **Property 27: Audit chain integrity**
    - **Validates: Requirements 17.5, 17.6**

- [x] 11. Checkpoint - Persistence and audit
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Authentication and RBAC
  - [x] 12.1 Implement login and users
    - `app/api/auth.py`: argon2id password hashing, `POST /api/auth/login` returning a 30-minute HS256 JWT (`sub`, `role`, `jti`), `GET /api/me`
    - Seed one user per role with per-user credentials in `app/seed/run.py`; no shared static key
    - Write an audit event on login
    - _Requirements: 7.2, 7.3, 7.4, 17.4_

  - [x] 12.2 Add `app/api/deps.py` and retire `X-Internal-Key`
    - `require_roles(*roles)`: 401 for missing or invalid token, 403 plus an `access_denied` audit event for the wrong role
    - Public routes only: health, login, policy lookup, customer intake, customer status, demo
    - Replace the interim gate from task 1.5 on `/api/assess` with I, F, A roles
    - _Requirements: 7.1, 7.4, 7.5, 7.6, 6.3, 17.4_

  - [x] 12.3 Add login and Bearer-token handling to the frontend
    - Update `frontend/src/api.ts` (token storage, 401 redirect) and make `pages/internal/InternalPage.tsx` a login-gated, role-aware shell
    - _Requirements: 7.3, 18.1_

  - [x]* 12.4 Write the role matrix test
    - Parametrised over every route in the OpenAPI schema, the four roles and anonymous, against a declared permission table
    - _Requirements: 7.1, 7.4, 7.5, 20.2_

- [ ] 13. Claims API, decisions and customer view
  - [x] 13.1 Split `app/main.py` into routers and add the error envelope
    - `app/api/` routers (claims, customer, demo, etc.) auto-registered from `app/api/__init__.py`; `main.py` keeps the app factory and SPA fallback
    - `app/api/errors.py` envelope `{"error": {"code", "message", "fields", "request_id"}}`, with 422 naming failing fields; every route declares 401, 403, 422, 429 responses and its role
    - Keep `/api/policies/lookup`, `/api/claims`, `/api/claims/{id}/status` and `/api/demo/*` paths
    - Add `POST /api/internal/claims`, `GET /api/internal/claims` (filters: band, status, provider, date range, assignee, category) and `GET /api/internal/claims/{id}`
    - _Requirements: 16.1, 16.2, 16.3, 16.5, 18.1, 7.1_

  - [x] 13.2 Implement investigator decisions
    - `app/api/decisions.py`: `POST /api/claims/{id}/decisions` for Investigator and Fraud_Team, non-blank reason required, stores user, timestamp, reason, notes and visible `risk_assessment_id`
    - Only the decision service moves a claim to DECIDED; investigate-band claims stay OPEN_INVESTIGATION; earlier decisions are kept
    - Audit event on every decision and on denied attempts
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 17.4_

  - [x] 13.3 Implement finding feedback
    - `POST /api/findings/{id}/feedback` (false_positive or confirmed) linked to the finding and its Rule_Version
    - _Requirements: 6.7, 3.6_

  - [x] 13.4 Implement the customer view and intake rules
    - `app/api/customer_view.py` with the approved wording and no findings, scores, bands, agent names or "verified/genuine/authentic" text
    - Ignore client-supplied analysis flags; on a policy eligibility violation return 422 and store the claim with the finding for review
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 13.5 Write property test for decision authorisation
    - **Property 24: Decision authorisation and reason**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 13.6 Write property test for the customer view
    - **Property 26: Customer view never leaks findings or unearned verification wording**
    - **Validates: Requirements 8.3, 8.4, 8.5**

- [ ] 14. Document intake, storage and extraction
  - [x] 14.1 Implement the storage adapter and adapter factory
    - `app/adapters/__init__.py` factory reading `LLM_ADAPTER`, `EXTRACTION_ADAPTER`, `STORAGE_ADAPTER`, `QUEUE_ADAPTER`, `HOSPITAL_ADAPTER` with lazy imports
    - `adapters/storage/base.py` Protocol and `local_fs.py` with generated storage keys, never client file names
    - _Requirements: 2.1, 2.3, 9.3_

  - [x] 14.2 Implement the extraction adapter and normalisation
    - `adapters/extraction/base.py` and `pypdf_ext.py` returning per-page text, fields and PDF metadata; image-only files return empty text
    - Store `extraction_results` and `normalised_facts` with original and normalised values and page references
    - _Requirements: 9.4, 9.5, 9.6_

  - [ ] 14.3 Implement document endpoints
    - Upload with file-type allow-list, size limit and SHA-256; reject invalid files naming the rule and store nothing; return the existing document for a repeated checksum
    - List, retrieve and page-level access (audited), and `GET /api/documents/{id}/extraction`
    - _Requirements: 9.1, 9.2, 9.7, 9.8, 17.4, 16.2_

  - [ ]* 14.4 Write property test for upload and storage
    - **Property 23: Upload validation, checksum and storage key independence**
    - **Validates: Requirements 9.1, 9.3, 9.7**

  - [ ] 14.5 Write contract tests for storage and extraction adapters
    - `tests/contract/` parametrised over implementations: put/get/delete round trip; text pages and metadata shape; no extractable text case
    - _Requirements: 2.6, 9.5_

- [ ] 15. Queue, worker and processing pipeline
  - [ ] 15.1 Implement the queue adapter
    - `adapters/queue/base.py` and `postgres.py`: enqueue with dedupe key, `lease` using `FOR UPDATE SKIP LOCKED`, complete, fail with retry, reaper for expired leases
    - _Requirements: 2.1, 4.9_

  - [ ] 15.2 Implement `app/worker.py` and the processing service
    - Lease job, extract documents, build the immutable `CheckContext`, run the orchestrator, persist findings, agent executions, risk assessment, contributions and audit events
    - Worker crash: lease expiry requeues until `max_attempts`, then the run is FAILED and the claim NEEDS_HUMAN_REVIEW
    - Adapter errors make dependent checks INCONCLUSIVE and the rest continue
    - _Requirements: 4.3, 4.4, 4.7, 2.5, 5.2_

  - [ ] 15.3 Implement processing endpoints and retire `jobs.py`
    - `POST /api/claims/{id}/process` with `Idempotency-Key` returning 202 `{job_id, run_id}`; repeated key returns the existing run
    - `POST /api/claims/{id}/runs/{run_id}/retry` creating a linked run; `GET /api/jobs/{id}`
    - Move customer intake to the queue and delete the in-memory `JOBS`
    - _Requirements: 4.9, 16.2, 16.4, 16.6_

  - [ ] 15.4 Implement findings and risk-report endpoints
    - `GET /api/claims/{id}/findings` filters Operational_Intelligence findings for the Investigator role
    - `GET /api/claims/{id}/risk-report` returns score, band, contributions, not-checked list, config and rule versions and the label
    - _Requirements: 3.1, 5.2, 5.3, 5.5, 15.9, 16.2_

  - [ ]* 15.5 Write property test for idempotent processing
    - **Property 11: Processing is idempotent per key**
    - **Validates: Requirements 4.9**

  - [ ] 15.6 Write contract tests for the queue adapter
    - Enqueue, lease exclusivity with two concurrent workers, fail and retry, lease expiry
    - _Requirements: 2.6_

  - [ ] 15.7 Write pipeline integration tests
    - SQLite with an in-process worker: submit claim, upload synthetic PDFs, process, check findings, assessment, audit chain and decision
    - Failure paths: agent timeout, adapter failure, lease expiry, linked retry, idempotency
    - _Requirements: 20.2, 4.4, 4.9, 16.4_

- [ ] 16. Checkpoint - End-to-end pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. LLM adapters, PII minimisation and prompt-injection safety
  - [ ] 17.1 Implement the LLM adapters
    - `adapters/llm/base.py` Protocol, `none.py` (`enabled=False`), `gemini.py` moved from `llm.py` (keep model fallback chain and `parse_json`)
    - Delete `_bedrock`, `run_tool_loop` and score-adjusting code from core; `LLMOutputInvalid` on schema failure
    - _Requirements: 1.7, 2.1, 2.2, 10.3, 10.5_

  - [ ] 17.2 Implement `app/core/pii.py`
    - `Pseudonymiser(claim)` for claimant and family names, policy number, phone, email, address, DOB and ids; scrub literal values from document text
    - _Requirements: 10.1_

  - [ ] 17.3 Implement `app/core/llm_tasks.py` and remove `llm_review.py`
    - Typed tasks with allow-listed fields and Pydantic output schemas; delimited non-instructional data block
    - Invalid output or adapter error yields INCONCLUSIVE for the AI check and keeps rules-only results; LLM findings are method AI and capped
    - Record `llm_calls` (prompt version, adapter, field names, outcome; no values)
    - Expose the `llm` capability to the orchestrator context
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [ ] 17.4 Write property test for PII in LLM payloads
    - Strategy `claims_with_pii()` in `tests/strategies/pii.py`
    - **Property 13: PII never appears in an LLM payload or LLM call record**
    - **Validates: Requirements 10.1, 10.8**

  - [ ]* 17.5 Write property test that LLM output cannot change score or band
    - Use a fake adapter; include injection text in documents
    - **Property 12: LLM output cannot change score, band or confirmed findings**
    - **Validates: Requirements 10.3, 10.4, 10.6, 10.7, 20.5**

  - [ ] 17.6 Write LLM contract tests
    - Gemini adapter against `httpx.MockTransport`; valid output passes the schema, invalid output raises `LLMOutputInvalid`; live-key test marked `live_llm` and skipped by default
    - _Requirements: 2.6, 10.3, 10.4_

- [ ] 18. Check registry, Policy_Eligibility and Duplicate_Detection
  - [ ] 18.1 Implement the check registry and agent base
    - `core/registry.py` (`CheckSpec`, `@check`, `stub`) and the new `agents/base.py` `Agent.run`
    - Missing capability yields one NOT_CHECKED finding per use case with the limitation; a raising check yields INCONCLUSIVE with the exception class name only
    - The orchestrator runs registry agents alongside legacy agents until task 20.5
    - _Requirements: 3.4, 3.5, 4.1, 1.7_

  - [ ] 18.2 Implement `agents/policy_eligibility.py` (UC 1-12)
    - Policy window, waiting period, exclusions, sum insured, insured person, purchase-to-admission gap, date sanity, late submission (moved from `claimant_profile.py`)
    - UC 3 INCONCLUSIVE or NOT_CHECKED without medical history
    - Tag implemented checks with `@pytest.mark.check_id` tests
    - _Requirements: 11.1, 11.2, 11.3, 11.8_

  - [ ] 18.3 Implement `agents/duplicate_detection.py` (UC 13-22)
    - Exact invoice key, fuzzy resubmission with differing-fields list, document SHA-256 reuse, cashless vs reimbursement, cross-claim and family match
    - Exclude the claim's own earlier runs; sole owner of duplicate scoring; UC 22 NOT_CHECKED
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 18.4 Write property test for registry totality
    - **Property 8: No silent pass (registry totality)**
    - **Validates: Requirements 1.7, 3.4, 11.8, 12.6, 13.9**

  - [ ]* 18.5 Write property test for duplicate detection
    - **Property 18: Duplicate detection finds each match once and never matches itself**
    - **Validates: Requirements 12.2, 12.3, 12.7**

  - [ ] 18.6 Write unit tests for policy and duplicate checks
    - A triggering and a non-triggering case for each implemented check, tagged with `check_id`
    - _Requirements: 20.1, 11.2, 12.2_

- [ ] 19. Document_Forensics and Billing_Intelligence
  - [ ] 19.1 Implement `agents/document_forensics.py` (UC 23-38)
    - Move and extend the fixed metadata rules from task 1.8, completeness (`NO_DOCUMENTS`, `MISSING_*`), cross-document exact-field comparison with original and normalised values, extraction quality
    - Semantic comparison via the LLM when available; ambiguous mismatch yields INCONCLUSIVE; UC 30 and 31 NOT_CHECKED without `image_analysis`
    - Update the task 1.9 property test to target the new module
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 9.5_

  - [ ] 19.2 Implement `agents/billing_intelligence.py` (UC 51-65)
    - GSTIN validation using the core validator, no finding for an absent GSTIN in exempt categories, total recomputation, pre-authorisation overrun, stay length, line-item sanity, `ROUND_TOTAL` as INFORMATIONAL
    - Reference ranges from `rules/reference_ranges.v1.yaml`; out-of-range yields POTENTIAL_ANOMALY citing range and source; no range yields NOT_CHECKED; documented high-cost treatment is lowered to informational with citations
    - _Requirements: 11.4, 11.5, 11.6, 11.7, 15.1, 15.2, 15.3, 15.4_

  - [ ]* 19.3 Write property test for missing GSTIN
    - **Property 15: Missing GSTIN is not an anomaly for exempt categories**
    - **Validates: Requirements 11.6**

  - [ ]* 19.4 Write property test for cross-document mismatch
    - **Property 20: Cross-document mismatch preserves both values**
    - **Validates: Requirements 13.6**

  - [ ] 19.5 Write unit tests for forensics and billing checks
    - A triggering and a non-triggering case for each implemented check, tagged with `check_id`
    - _Requirements: 20.1, 13.4, 11.5_

- [ ] 20. Provider, customer and operational intelligence; remaining agents
  - [ ] 20.1 Implement `agents/provider_intelligence.py`
    - Hospital registry, doctor licence and affiliation, provider claim-volume surge (UC 65) using `ProviderRepo`
    - _Requirements: 15.5_

  - [ ] 20.2 Implement `agents/customer_behaviour.py`
    - Claim frequency, amount spike, hospital hopping, repeated similar amounts (moved from `claimant_profile.py`)
    - _Requirements: 3.1, 12.5_

  - [ ] 20.3 Implement `agents/operational_intelligence.py` (UC 115-122)
    - Record post-submission claim changes in `claim_changes` with before and after values (UC 120)
    - Approval without required documents (UC 118, 122), override and resubmission patterns; findings attribute patterns, not individuals; checks lacking ops data NOT_CHECKED
    - _Requirements: 15.6, 15.7, 15.8, 15.9_

  - [ ] 20.4 Register the remaining agents
    - Medical_Consistency, Identity_Verification, Hospitalisation, Predictive_Fraud with stubs so all 11 agents exist and every P0 use case has a registry entry
    - _Requirements: 3.4, 1.7, 19.1_

  - [ ] 20.5 Retire the legacy agent shim
    - Remove `core/legacy_adapter.py` and the old agent modules (`provider_profile.py`, `claimant_profile.py`, `document_scan.py`, `invoice_check.py`) once covered by the registry; the orchestrator uses the registry only
    - Confirm the task 1 regression tests and seed scenario tests still pass
    - _Requirements: 4.1, 12.5_

  - [ ]* 20.6 Write property test for reference range and volume thresholds
    - **Property 22: Reference range and volume thresholds**
    - **Validates: Requirements 15.2, 15.4, 15.5**

  - [ ] 20.7 Write unit tests for provider, customer and operational checks
    - A triggering and a non-triggering case for each implemented check, tagged with `check_id`
    - _Requirements: 20.1, 15.5, 15.7, 15.8_

- [ ] 21. Invoice authenticity and hospital verification
  - [ ] 21.1 Implement the hospital verification adapter
    - `adapters/hospital/base.py` and `simulated.py`: deterministic by seeded hospital flags, every response `simulated=true`
    - _Requirements: 14.7, 2.1_

  - [ ] 21.2 Implement `app/core/authenticity.py` and the endpoint
    - Pure function returning exactly one Invoice_Authenticity_State from verification result, provider match, outstanding request and medium-or-higher forensic or duplicate findings
    - Persist `verification_requests` and `verification_responses` with timestamps; `GET /api/claims/{id}/invoices/{inv}/authenticity`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8_

  - [ ]* 21.3 Write property test for authenticity state
    - **Property 21: Invoice authenticity state is a single, ordered function of its inputs**
    - **Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7**

  - [ ] 21.4 Write contract tests for the hospital adapter
    - Results are labelled simulated
    - _Requirements: 2.6, 14.7_

- [ ] 22. Coverage matrix
  - [ ] 22.1 Create `app/rules/coverage_matrix.v1.yaml`
    - 126 entries with use case id, title, priority, agent, data required, method, dependencies, evidence, limitations, status and `blocked_by`, using the master use-case list
    - P0 exactly 1-38, 51-65, 115-122; P1 and P2 are `planned`; stub-only P0 are `not_implemented_locally` with the dependency named
    - _Requirements: 19.1, 19.2, 19.4_

  - [ ] 22.2 Implement `app/core/coverage.py` and `GET /api/coverage-matrix`
    - Join the YAML with the registry; Administrator and Fraud_Team access; versioned
    - _Requirements: 19.3_

  - [ ] 22.3 Write coverage consistency tests
    - 126 unique ids, the P0 id set, every P0 use case has a registry entry, `implemented` only with a tagged test (collected through the `check_id` marker in `conftest.py`)
    - _Requirements: 19.2, 19.5, 19.6_

  - [ ] 22.4 Retire `app/catalog.py`
    - Generate agent catalog output from the registry and matrix; update the endpoints that used it
    - _Requirements: 19.3, 19.6_

- [ ] 23. Admin, configuration and retention APIs
  - [ ] 23.1 Implement risk-config endpoints
    - `GET/PUT /api/admin/risk-config` (PUT Administrator; GET Administrator and Fraud_Team) creating a new `risk_configs` version and an audit event; new assessments use the active version and earlier ones keep their `config_version`
    - _Requirements: 5.7, 5.8, 17.4_

  - [ ] 23.2 Implement provider reference-data endpoints
    - `GET/POST/PUT /api/providers` for Fraud_Team and Administrator
    - _Requirements: 16.2_

  - [ ] 23.3 Implement the retention job
    - Nightly worker job that deletes or anonymises PII and documents past `retention_until` and writes an audit event
    - _Requirements: 17.2, 17.3_

  - [ ] 23.4 Implement audit, verify and health endpoints
    - `GET /api/claims/{id}/audit`, `GET /api/admin/audit/verify` (first bad `seq` or intact), `GET /api/health` reporting DB, queue and adapters
    - _Requirements: 16.2, 17.6, 1.1_

  - [ ]* 23.5 Write tests for config versioning and retention
    - Config change applies to later assessments only; retention anonymises and audits
    - _Requirements: 5.7, 5.8, 17.3_

- [ ] 24. Investigator dashboard
  - [ ] 24.1 Update the frontend API client and shared UI
    - Typed responses for the new endpoints in `frontend/src/api.ts`; add `StatusBadge` to `components/ui.tsx` for the five statuses (NOT_CHECKED grey with its limitation, never green); set up Vitest and React Testing Library (run with `npm.cmd`)
    - _Requirements: 18.7_

  - [ ] 24.2 Build the claims queue in `ClaimsView.tsx`
    - Filters for band, status, provider, date range, assignee and finding category
    - _Requirements: 18.1_

  - [ ] 24.3 Build the claim workspace in `ClaimDetail.tsx`
    - Document viewer with page navigation, extracted fields beside source, cross-document comparison table, invoice authenticity panel, findings grouped by category and severity with score contributions and Rule_Version, pending verification status, audit trail
    - Sections separating verified facts, rule violations, potential anomalies, missing evidence, external checks pending, checks not performed and human decisions
    - Decision panel requiring a reason
    - _Requirements: 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

  - [ ] 24.4 Update `WorkflowView.tsx` and `AgentsView.tsx`
    - Workflow shows the processing run timeline from agent executions; Agents view becomes the Administrator coverage view from `/api/coverage-matrix`
    - _Requirements: 18.8, 4.3_

  - [ ] 24.5 Update the customer pages
    - `ProcessingPage.tsx`, `ReportPage.tsx` and `pages/journey/*` follow the approved customer wording and no longer send analysis flags
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [ ]* 24.6 Write frontend component tests
    - `StatusBadge` shows NOT_CHECKED as not a pass; the decision form blocks a blank reason
    - _Requirements: 18.6, 18.7_

- [ ] 25. Packaging, scenarios and CI
  - [ ] 25.1 Add Docker packaging
    - `Dockerfile` (one image; commands `uvicorn app.main:app` and `python -m app.worker`) and `docker-compose.yml` with `api`, `worker` and `postgres`
    - API startup runs `alembic upgrade head` and the idempotent seed; add `.env.example` and `pyproject.toml` with `boto3` only in the `aws` extra
    - _Requirements: 1.1, 1.2, 1.5, 2.2_

  - [ ] 25.2 Build the synthetic scenario fixtures
    - Using `seed/docgen.py`: genuine claim, duplicate invoice, changed amount, date mismatch, missing documents, OCR errors, name spelling variants, legitimate high-cost treatment, unusual but valid billing, provider verification unavailable, forged-looking metadata with valid evidence, conflicting documents, prompt injection in a PDF
    - _Requirements: 20.3_

  - [ ] 25.3 Write scenario assertion tests
    - Genuine claim routes low; metadata alone never yields CONFIRMED_RULE_VIOLATION; injection scenario has the same assessment as the clean variant; the evaluation script reports scenario counts only, never precision or recall
    - _Requirements: 20.4, 20.5, 20.6, 20.7_

  - [ ] 25.4 Write static and smoke tests
    - AST scan: no module under `core/`, `agents/` or `api/` imports `boto3` or another cloud SDK
    - Script that checks `docker compose up` reaches healthy and that a missing `JWT_SECRET` exits naming the variable
    - _Requirements: 2.2, 1.1, 1.6_

  - [ ] 25.5 Add GitHub Actions CI
    - Run the Python tests (SQLite, plus a `postgres` service for `@pytest.mark.postgres` tests) and frontend tests with no cloud credentials and no live Gemini calls
    - _Requirements: 20.8_

  - [ ] 25.6 Update `README.md`, `demo.py` and `scripts/*`
    - Document the single compose command, seeded users and demo scenarios; scripts log in and call the new endpoints
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 26. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. Core scoring, dedup, routing, GSTIN and PII properties are required.
- Each task references specific requirements for traceability.
- Checkpoints follow each major milestone.
- Property tests validate universal correctness properties; unit tests validate specific examples and edge cases.
- The legacy agents keep running through `core/legacy_adapter.py` until task 20.5, so the app stays runnable after every top-level task.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.8"] },
    { "id": 2, "tasks": ["1.5", "1.9"] },
    { "id": 3, "tasks": ["1.6"] },
    { "id": 4, "tasks": ["1.7", "1.10"] },
    { "id": 5, "tasks": ["3.1", "4.1", "5.1", "5.2"] },
    { "id": 6, "tasks": ["3.2", "3.3", "4.7", "5.3", "5.4", "5.5", "6.1"] },
    { "id": 7, "tasks": ["3.4", "4.2"] },
    { "id": 8, "tasks": ["4.3", "4.4", "4.5", "4.6", "6.2"] },
    { "id": 9, "tasks": ["6.3", "6.4", "6.5"] },
    { "id": 10, "tasks": ["8.1", "10.1"] },
    { "id": 11, "tasks": ["8.2", "8.4", "10.3"] },
    { "id": 12, "tasks": ["8.3", "9.1", "9.2"] },
    { "id": 13, "tasks": ["8.5", "9.3", "10.2"] },
    { "id": 14, "tasks": ["9.4", "12.1"] },
    { "id": 15, "tasks": ["12.2"] },
    { "id": 16, "tasks": ["12.3", "12.4", "13.1", "14.1"] },
    { "id": 17, "tasks": ["13.2", "13.3", "13.4", "14.2", "14.4"] },
    { "id": 18, "tasks": ["13.5", "13.6", "14.3", "14.5", "15.1"] },
    { "id": 19, "tasks": ["15.2", "15.6"] },
    { "id": 20, "tasks": ["15.3"] },
    { "id": 21, "tasks": ["15.4", "15.5", "15.7"] },
    { "id": 22, "tasks": ["17.1", "17.2", "18.1", "23.1", "23.2", "23.3", "23.4"] },
    { "id": 23, "tasks": ["17.3", "17.6", "18.2", "18.3", "18.4", "23.5", "25.1"] },
    { "id": 24, "tasks": ["17.4", "17.5", "18.5", "18.6", "19.1", "19.2", "20.1", "20.2", "20.4", "25.4"] },
    { "id": 25, "tasks": ["19.3", "19.4", "19.5", "20.3", "21.1", "25.5"] },
    { "id": 26, "tasks": ["20.5", "20.6", "20.7", "21.2", "21.4"] },
    { "id": 27, "tasks": ["21.3", "22.1", "24.1", "25.2"] },
    { "id": 28, "tasks": ["22.2", "24.2", "24.3", "24.5", "25.3"] },
    { "id": 29, "tasks": ["22.3", "22.4", "24.4", "24.6"] },
    { "id": 30, "tasks": ["25.6"] }
  ]
}
```
