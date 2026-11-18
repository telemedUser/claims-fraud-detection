# Changelog

Changes on `feature/fraud-detection-service`, newest first. Each entry lists what changed, why, how it was verified, and any follow-up.

## 2026-11-21: LLM findings now add to the score

### Changed
- **Final score = rule points + capped LLM points.** Each LLM finding counts as a potential anomaly (low 10, medium 25, times 0.6). Caps: 15 points per agent and 25 per claim (`llm:` block in `risk_scoring.v1.yaml`), so the LLM alone cannot reach the manual-review band (30). Failed or invalid LLM reviews add 0, and with the console switch off the score is rules only.
- **More LLM findings:** up to 8 per agent (was 5), and the prompt asks for a full pass over the agent's documents and fields.
- **Queue and status** are recomputed from the combined score.
- **Console:** agent cards show "rules X + LLM Y"; every agent card has an LLM findings section, with a reason when the LLM did not review; Workflow and Agents texts describe the cap.
- **Reverses** the earlier decision that the LLM never scores (Requirement 10.6). `AGENT_HANDOFF.md` rule 2 and the docs are updated.

### Verified
- Targeted tests: 70 passed. Frontend build OK.
- **Live (LLM on):** suspicious claim 100 (rules 100 + LLM 25, at the claim cap). A run with caps 20/30 showed a claim with 0 rule findings reaching 30 from the LLM alone, so the caps were lowered to 15/25 to stay under the review band. Per-agent card shows rules + LLM points.
- **Not changed:** the spec (`design.md` decision "LLM never scores", Property 12) still describes the old rule. It needs a decision from the team.

## 2026-11-21: Medical Review agent added

Docs: [medical_review.md](agents/medical_review.md).

### Added
- **Medical Review** (16 checks): ICD-10 validity and fit with the diagnosis, medicines against the diagnosis, lab report tamper check, treatment against the diagnosis. Maps to `Medical_Consistency`.
- **Helpers:** `app/core/medical_reference.py` with `app/rules/medical_reference.v1.yaml`, and `app/core/lab_registry.py` (simulated lab registry, HMAC verification code).
- **LLM tools:** `get_clinical_reference`, `get_lab_verification`.
- **Journey:** a **Lab report** upload slot (`lab_report` document type).
- **Demo documents:** lab reports for every scenario. The suspicious case prints CRP 48 under a code signed for CRP 3.

### Verified
- Targeted tests: 150 passed. Frontend build OK.
- **Probe:** clean 0, suspicious and high-risk 100, fabricated 100, borderline 36 (manual review).

## 2026-11-20: Document Scan and Invoice Check agents enhanced

Docs: [document_scan.md](agents/document_scan.md), [invoice_check.md](agents/invoice_check.md).

### Added
- **Document Scan** (10 new checks):
  - edits after generation: `DOC_EDITED_AFTER_GENERATION` (extra PDF revisions), `DOC_MODIFIED_AFTER_BILL_DATE`
  - AI-tool markers: `AI_GENERATION_MARKER`
  - printed content against the claim: patient, policy, dates, diagnosis, bill number, total and date
- **Invoice Check** (13 new checks):
  - GST: `GSTIN_INVALID`, GST charged without a GSTIN, CGST/SGST split, mixed IGST, GST on exempt treatment
  - duplicates: number variants, the same bill under a new number, the same number at another hospital
  - payment: cashless bill claimed, balance due, claim above amount paid, no payment evidence, payment date out of range
- **New helpers:** `app/core/doc_text.py`, `app/core/pdf_forensics.py`, `app/core/redact.py`, and `InvoiceRepo.invoice_candidates`.
- **LLM tools:** `get_document_text` (personal data redacted) and `get_bill_details` (no personal data). The focus texts for both agents are updated.
- **Journey:** an optional **Payment receipt** upload (`payment_receipt` document type).
- **Demo documents:** bills carry a payment block. The suspicious bill is cashless and unpaid, with a second PDF revision; the fabricated bill has an AI-tool marker.

### Verified
- Targeted tests: 141 passed (mappings, forensics properties, seed and scenarios, defect regressions, seeded repositories, assess gate). Frontend build OK.
- **Probe:** clean stays 0, and the scenarios route as before. A tampered claim fires every content and GST check.
- **Live with the LLM on:** both reviews used the new tools, and no name, policy number or claimant ID appeared in the LLM output.

## 2026-11-20: User Profile agent (claimant profile) and user profile page

Documentation: [docs/agents/user_profile.md](agents/user_profile.md).

### Added
- **Shared profile logic** `app/core/user_profile.py`, with thresholds in `app/rules/user_profile.v1.yaml`. New signals:
  - `AMOUNT_ESCALATION`
  - `RESUBMITTED_STAY` and `OVERLAPPING_STAYS_ELSEWHERE` (re-claiming)
  - `PRIOR_FRAUD_DECISION` (earlier claim denied or referred)
  - `CLAIM_SOON_AFTER_POLICY_START`, `CLAIM_NEAR_POLICY_END` and `POLICY_END_PATTERN` (timing around the policy term)
  - `SUM_INSURED_NEAR_LIMIT`
- **`ClaimRepo.claimant_records`:** earlier claims with stay, hospital, doctor, diagnosis and latest decision. **`ClaimRepo.claimants`:** staff list.
- **Console Users tab and profile page** (`ClaimantsView.tsx`), plus a **User profile** button on each claim. API: `GET /api/internal/claimants` and `GET /api/internal/claimants/{id}` (all console roles; views audited as `claimant_access`).
- **LLM tool `get_claimant_profile`:** pseudonymised claims, metrics and signals only. It answers only for this claim's claimant. The focus text for the agent is updated.
- **Seed data:** stay dates, diagnosis and decisions for the history claims (`HISTORY_DETAILS`). C-202 is denied. An inactive `system` user owns the seeded decisions.

### Changed
- The agent now uses the full earlier records and the policy, and is titled "User Profile Agent" in the console. The agent id `claimant_profile` is unchanged.

### Verified
- Targeted tests: 202 passed (role matrix, seeded repositories, seed and scenarios, mappings, defect regressions). Frontend build OK.
- Live run with the LLM on: the new findings fire on the suspicious demo, the profile page data loads, and no claimant name appeared in the LLM tool calls or reasoning.

### Upgrade note
Use **Reset demo data** in the console (or delete `claims_fraud.db`) so the seeded history gets its new details.

## 2026-11-20: LLM analysis switch, per-agent LLM review back in the pipeline

Documentation: [docs/llm_usage.md](llm_usage.md).

### Why
The per-agent LLM review existed but the pipeline never called it, so the LLM was used only for the summary. The team wants one switch in the UI: when it is on, every submitted claim uses the LLM.

### Added
- **LLM analysis switch** in the internal console header (`LlmToggle` in `frontend/src/pages/internal/InternalPage.tsx`):
  - an Administrator can change it; other roles see its state
  - it is stored in a new `app_settings` table (migration `0004`), and every change is audited as `config_change`
  - it is read once per claim at submission (`app/runtime_settings.py`)
  - API: `GET /api/internal/settings` (all console roles), `POST /api/internal/settings/llm` (Administrator)
- **Per-agent LLM review in the pipeline** (`app/pipeline.py`): when the switch is on, all completed agents are reviewed in parallel after scoring. The loading page shows the "AI review" badge.
- **Guardrails in `app/llm_review.py`** (Requirement 10):
  - the claimant name is removed, and the claimant id and policy number are pseudonymised
  - data blocks are marked as non-instructional
  - output is checked against a strict schema (`ReviewOutput`), with one repair turn
  - the whole review gets up to 3 attempts on transient provider errors, and the tool loop has a 6-step budget with an "answer now" prompt before the last step
  - every review and summary call is recorded in `llm_calls`, with field names only
- **Requirements:** clarifications on 8.2 and 10.6, and new criteria 10.9 and 10.10.

### Changed
- **LLM observations are no longer scored.** Earlier they could add up to 25 points per agent; now they are shown with `source="llm"` and the score and queue come from rules only (Requirement 10.6). The console texts ("Merge", the scoring panel, agent cards) say so.
- **Claims submitted from the journey** use the switch instead of `Settings.llm_enabled()`. `use_llm` on `/api/assess` can only turn the LLM off.
- **The console overview** reports the effective state (`enabled`) and the requested state.
- **`GEMINI_API_KEY` in `.env`** was replaced with the new key. It is git-ignored and never printed.
- **Provider agent focus text** for the LLM now lists the new provider checks, so the model looks beyond them.

### Verified
- `python -m pytest -q`: 473 passed, 1 skipped. The role matrix covers the two new routes.
- **Live checks with Gemini:**
  - switch off: no LLM calls even with `use_llm=true` from the client
  - switch on: four agent reviews and an LLM summary per claim; with the final code, 16 of 16 reviews and 4 of 4 summaries completed over two runs
  - the score was identical with and without the LLM (100 and 100)
  - `llm_calls` rows hold only field names
  - an Investigator gets 403 changing the switch
  - Administrator changes are audited
- **Browser (Edge, Playwright):** the switch is disabled for an Investigator, and an Administrator can turn it off and on.

### Upgrade note
`app_settings` is a new table. The development server creates it on start; no database reset is needed. With Alembic, run `alembic upgrade head`.

### Follow-up
- **Task 17:** move the review onto the LLM adapter and the shared pseudonymiser, with typed tasks.
- **AI observations** are not yet written to the `findings` table.

## 2026-11-20: Provider Profile agent, computed profile and cross-checks

Agent documentation: [docs/agents/provider_profile.md](agents/provider_profile.md), with checks, workflow, data sources and LLM usage.

### Why
The provider checks only compared the claim with fixed seeded figures. Nothing used the claims data that is now stored per hospital and doctor, nothing checked dates (licence, affiliation, network), and nothing compared the uploaded documents with the registry.

### Added
- **Computed provider profile** from claims data and investigator decisions (`ProviderActivityRepo` in `app/db/repos.py`, maths in `app/core/provider_stats.py`):
  - `HOSPITAL_VOLUME_SURGE` and `DOCTOR_VOLUME_SURGE` (use case 65, Requirement 15.5). The seeded H002 surge is now detected.
  - `PEER_COST_OUTLIER`: the claim against the same diagnosis at other hospitals.
  - `DOCTOR_SIMILAR_BILLS`: near-identical amounts across the doctor's other patients.
  - `HOSPITAL_OVER_CAPACITY`: overlapping stays against the bed count.
  - `DOCTOR_SAME_DAY_OTHER_CITY`: the same doctor admitting in another city on the same date.
- **Registry cross-checks read on the admission date:** `DOCTOR_LICENCE_EXPIRED`, `DOCTOR_AFFILIATION_INACTIVE`, `HOSPITAL_NOT_EMPANELLED_ON_DATE`, `REGISTRY_GSTIN_INVALID`, `GSTIN_STATE_MISMATCH`, `DOCTOR_REGISTRATION_MISSING`.
- **Specialty fit:** `DOCTOR_SPECIALTY_MISMATCH` and `HOSPITAL_SPECIALTY_NOT_OFFERED`, from a new `specialties` list per disease.
- **Documents against the registry** (text from the extraction adapter, `app/core/text_match.py`): `DOC_GSTIN_MISMATCH`, `DOC_HOSPITAL_NAME_MISMATCH`, `DOC_DOCTOR_NAME_MISSING`, `DOC_DOCTOR_REG_MISMATCH`, and `PROVIDER_DOCS_NOT_CHECKED` (inconclusive) when no document has text.
- **Thresholds file** `app/rules/provider_profile.v1.yaml`, with a strict loader `app/core/provider_config.py`.
- **Migration** `0003_provider_registry_fields`:
  - `providers`: `state_code`, `bed_count`, `empanelled_from`, `empanelled_to`
  - `doctors`: `licence_valid_to`
  - `doctor_affiliations`: `start_date`, `end_date`
  
  All are nullable; null means "not on record" and the check is skipped.
- **Seed values** for the new fields. D002's affiliation with H003 ends on 2026-06-30, which demonstrates the inactive-affiliation check.
- **Mappings** for all 19 new codes in `app/core/legacy_adapter.py`, with limitations and next actions. `DOC_GSTIN_MISMATCH` shares the `tax_id_mismatch` fact key with `TAX_ID_MISMATCH`, so it is scored once.
- **Requirements** 15.10–15.14 and a clarification on 15.5 in `requirements.md`.
- **Demo script** `scripts/provider_profile_demo.py`.

### Changed
- `AMOUNT_OUTLIER_FOR_HOSPITAL`: the baseline is the hospital's same-diagnosis claims (at least 5), then all its claims (at least 10), then the registry figures. The computed spread is floored at 10% of the mean. The finding states its basis.
- `HOSPITAL_HIGH_FRAUD_RATE` and `DOCTOR_HIGH_FRAUD_RATE`: the registry rate is blended with investigator decisions (`deny` and `REFER_TO_FIU` count as flagged).
- `DOCTOR_HIGH_VOLUME`: uses max(registry figure, observed 30-day volume).
- `DOCTOR_MANY_HOSPITALS`: counts only affiliations active on the admission date.
- `TAX_ID_MISMATCH`: compared without case or separators.
- Doctor records from `ProviderRepo` gain `licence_valid_to` and `affiliation_dates`; hospital records gain `state_code`, `bed_count`, `empanelled_from` and `empanelled_to`. Both still match the seed shape exactly (`tests/db/test_repos_seeded.py`).
- The console catalogue (`app/catalog.py`) lists all 31 provider checks.
- The README's agent and LLM description now matches this branch. The per-agent Gemini review is not called by the pipeline.

### Not changed
- No LLM calls were added. The agent is fully deterministic.
- Scenario routing is unchanged: clean 0 (low), high_risk 100 (investigate), fabricated 100 (investigate), borderline 36 (manual review).

### Verified
- `python -m pytest -q`: 463 passed, 1 skipped. The 3 storage-adapter test files are excluded until `app/adapters/storage/` is pushed. The new codes add 19 cases to the mapping test.
- `python scripts/provider_profile_demo.py`: 19 of 19 targeted cases fire as expected, and a clean claim with matching documents produces no provider findings.
- The migration test (`tests/db/test_migrations.py`) passes with `0003`.

### Upgrade note
The development server builds tables with `create_all`, which does not add columns to an existing SQLite file. Delete `claims_fraud.db` once; it is re-created and seeded on start.

### Follow-up
- Planned LLM use (identity extraction, entity resolution, clinical fit, narrative) needs task 17. See the agent document.
- Admin endpoints to edit provider records (task 23), and real registry adapters.
- Remove the unused per-agent review (`app/llm_review.py`) and its console text (task 17).
