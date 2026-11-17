# Requirements Document

## Introduction

ClaimShield is a Python/FastAPI service that helps claims investigators detect potential fraud in health insurance claims. It evolves the existing repository at `claims-fraud-detection`. The React 19, TypeScript, Vite and Tailwind frontend stays. The investigator dashboard becomes the main user interface. The existing customer submission journey stays as a secondary intake channel.

Today ClaimShield runs four agents (provider_profile, claimant_profile, document_scan, invoice_check). Each agent applies rules and then an optional Gemini review. The orchestrator combines agent scores and routes a claim to auto_approve, manual_review or investigate. Data lives in memory. This spec replaces that design with a local-first, auditable, human-in-the-loop system.

**Principles encoded in this document**

- An anomaly is an investigation signal, not proof. ClaimShield never rejects a claim automatically. An Investigator owns every final decision.
- Deterministic services handle exact matching, dates, policy rules, arithmetic, checksums, duplicates and thresholds. The LLM handles only document understanding, semantic comparison, summarisation and explanation, and is never the sole decision-maker.
- Document text is untrusted input.
- Checks that cannot be performed are reported as NOT_CHECKED or INCONCLUSIVE and are never silently passed.

**Delivery direction**

- Local-first: everything runs on a developer laptop with Docker Compose (API, worker, PostgreSQL), synthetic data only and no cloud accounts. AWS is the later cloud target. Providers are not mixed, and the core imports no cloud SDK.
- Provider adapter boundaries: LLM, document extraction, document storage and job queue. Local defaults are rules-only (optional Gemini key for development), pypdf text extraction, local filesystem and a database-backed queue. Future implementations are AWS Bedrock, AWS Textract AnalyzeExpense, S3 and SQS.

**MVP scope** is the 61 P0 Use_Cases: 1-38 (policy and eligibility, duplicates, document fraud), 51-65 (billing) and 115-122 (operational). Several P0 Use_Cases depend on data or integrations that are unavailable locally (for example fake doctor signatures, forged stamps and seals, cross-insurer duplicates, undisclosed pre-existing disease). These are reported honestly as NOT_CHECKED or INCONCLUSIVE with limitations and are not claimed as implemented.

**Future scope (out of MVP)**: P1 Use_Cases 39-50 and 66-103, and P2 Use_Cases 104-114 and 123-126. They appear in the Coverage_Matrix with status "planned".

**Known defects in the existing code that this spec corrects**

1. The customer report says "Verified" when an agent scores below 30, although the registries are fictional.
2. TAX_ID_MISSING is flagged as suspicious, although healthcare services are generally GST exempt.
3. A duplicate invoice is counted by two agents (DUPLICATE_INVOICE and REPEATED_INVOICE_NUMBER), and the tax ID is checked in two agents.
4. The finding model holds only code, severity, detail and source.
5. The full claim, including claimant name, is sent to the LLM.
6. The client can set use_llm=false on customer submission.
7. POST /api/assess is unauthenticated, bypasses policy checks and writes to claim history.
8. Policy lookup by policy number and date of birth has no rate limiting.
9. DOC_CREATED_BEFORE_ADMISSION is high for all document types, the editor-software pattern matches "word" and "libreoffice", and MODIFIED_AFTER_CREATION fires at more than one hour.

## Glossary

- **ClaimShield**: The fraud detection service described in this document, including its API, worker, database and web interfaces.
- **Claim**: A health insurance claim submitted for assessment, with claimant, policy, provider, bill details and documents.
- **Policy**: The insurance policy record against which a Claim is checked.
- **Document**: A file uploaded for a Claim, such as an invoice, discharge summary, prescription, lab report or payment receipt.
- **Extraction_Result**: The structured fields and text extracted from a Document, with page and field provenance.
- **Normalised_Facts**: Canonical claim values (dates, amounts, names, identifiers) derived from Extraction_Results, stored beside the original extracted values.
- **Orchestrator**: The ClaimShield component that selects applicable checks, runs independent checks in parallel, tracks state, timeouts and retries, validates outputs, deduplicates Findings, preserves provenance and escalates uncertainty to Investigators.
- **Agent**: One of the 11 logical analysis modules: Policy_Eligibility, Duplicate_Detection, Document_Forensics, Medical_Consistency, Billing_Intelligence, Provider_Intelligence, Customer_Behaviour, Identity_Verification, Hospitalisation, Predictive_Fraud and Operational_Intelligence.
- **Check**: One testable analysis belonging to an Agent and mapped to one or more Use_Cases.
- **Use_Case**: One of the 126 numbered fraud scenarios in the master use-case list, each with a priority of P0, P1 or P2.
- **Finding**: A structured result of a Check, as defined in Requirement 3.
- **Finding_Status**: One of CONFIRMED_RULE_VIOLATION, POTENTIAL_ANOMALY, INFORMATIONAL, NOT_CHECKED or INCONCLUSIVE.
- **Detection_Method**: One of RULE, OCR, AI, ML, EXTERNAL_VERIFICATION or HUMAN.
- **Risk_Assessment**: The versioned, explainable score and routing band calculated for a Claim from its deduplicated Findings.
- **Routing_Band**: A configured score range that maps to a recommended queue (default: 0-29 low, 30-59 manual review, 60-100 investigate).
- **Investigator**: A human claims investigator who reviews Claims and records decisions.
- **Ops_Manager**: A user who monitors queues, workload and operational patterns.
- **Fraud_Team**: A user who handles escalated cases, provider reference data and rule feedback.
- **Administrator**: A user who manages users, configuration and the Coverage_Matrix.
- **Investigator_Decision**: A decision recorded by an Investigator: approve, APPROVE_EXCEPTION, REQUEST_DOCUMENTS, REFER_TO_FIU or deny.
- **LLM_Adapter**: The interface for LLM calls. Local default is none (rules-only). Implementations: Gemini (development, optional key) and AWS Bedrock (future).
- **Extraction_Adapter**: The interface for document text and field extraction. Local default is pypdf text extraction. Future implementation is AWS Textract AnalyzeExpense.
- **Storage_Adapter**: The interface for Document storage. Local default is the local filesystem. Future implementation is S3.
- **Queue_Adapter**: The interface for job queuing. Local default is a PostgreSQL-backed queue. Future implementation is SQS.
- **Hospital_Verification_Adapter**: The interface that asks an authorised hospital source to confirm an invoice. The local implementation is SIMULATED.
- **Invoice_Authenticity_State**: One of "Confirmed by authorised hospital source", "Provider identity matched, invoice not confirmed", "Verification pending", "Verification unavailable" or "Potential manipulation indicators".
- **Coverage_Matrix**: The machine-readable artifact that lists all 126 Use_Cases with data requirements, method, dependencies, evidence, limitations, priority and implementation status.
- **Rule_Version**: The identifier of the rule set, model or prompt version that produced a Finding or Risk_Assessment.
- **Audit_Log**: An append-only, tamper-evident record of security-relevant and decision-relevant events.
- **Synthetic_Data**: Fabricated records containing no real person's data.
- **PII**: Personally identifiable information and health data in a Claim.
- **Idempotency_Key**: A client-supplied value that makes a repeated request produce one effect.

## Requirements

### Requirement 1: Local Developer Setup and Synthetic Data

**User Story:** As a developer, I want to start the whole system locally with one command, so that I can develop and demonstrate ClaimShield without cloud accounts or real data.

#### Acceptance Criteria

1. WHEN a developer runs the documented single Docker Compose command, THE ClaimShield SHALL start the API, the worker and PostgreSQL and report healthy status on the health endpoint.
2. THE ClaimShield SHALL run all functions with local adapters and Synthetic_Data and require no cloud account or cloud credential.
3. WHEN ClaimShield starts with an empty database, THE ClaimShield SHALL seed Synthetic_Data including users for each role, policies, providers, claims and documents.
4. THE ClaimShield SHALL seed these demo scenarios: a clean claim that routes to the low band, a high-risk claim with a duplicate invoice, an invalid GSTIN, an excessive stay and a provider claim-volume surge, a fabricated or AI-generated-looking bill, and a borderline claim with a missing discharge summary and a pre-authorisation overrun.
5. THE ClaimShield SHALL load secrets and provider settings from environment variables only.
6. IF a required environment variable is missing at startup, THEN THE ClaimShield SHALL stop with an error that names the missing variable and omits its value.
   - Clarification (task 8.1): `app/settings.py` is the only module that reads configuration. For local development it also reads the git-ignored `.env` file; real environment variables take precedence, and a blank value counts as unset. A variable is required only when an enabled feature needs it: `JWT_SECRET` is required when `AUTH_ENABLED=true`.
7. WHERE no LLM key is configured, THE ClaimShield SHALL run with the rules-only LLM_Adapter and mark every LLM-dependent Check as NOT_CHECKED.

### Requirement 2: Provider Adapter Boundaries

**User Story:** As an architect, I want provider-specific code behind adapters, so that moving from local to AWS requires no change to core logic.

#### Acceptance Criteria

1. THE ClaimShield SHALL access LLM, document extraction, document storage, job queue and hospital verification only through the LLM_Adapter, Extraction_Adapter, Storage_Adapter, Queue_Adapter and Hospital_Verification_Adapter interfaces.
2. THE ClaimShield core packages SHALL import no cloud provider SDK.
3. WHERE an adapter implementation is selected by configuration, THE ClaimShield SHALL load that implementation at startup without code changes.
4. THE ClaimShield SHALL use implementations from one provider family per deployment.
5. WHEN an adapter call fails or times out, THE ClaimShield SHALL record the failure, mark the dependent Checks INCONCLUSIVE and continue the remaining Checks.
6. THE ClaimShield SHALL provide a contract test suite that every implementation of an adapter interface passes.

### Requirement 3: Finding Model and Provenance

**User Story:** As an Investigator, I want each finding to show its evidence and limits, so that I can judge it without trusting a bare score.

#### Acceptance Criteria

1. THE ClaimShield SHALL store for each Finding: finding_id, use_case_id, category, claim_id, severity, Finding_Status, explanation, source document id, page number or source field, extracted values, expected value or comparison basis, Detection_Method, confidence with its definition, limitations and alternative explanations, recommended next action, timestamp and Rule_Version.
2. THE ClaimShield SHALL assign each Finding exactly one Finding_Status.
3. WHERE a Finding has Detection_Method AI or ML, THE ClaimShield SHALL cap its Finding_Status at POTENTIAL_ANOMALY.
4. WHEN a Check cannot run because data or an integration is unavailable, THE ClaimShield SHALL create a Finding with Finding_Status NOT_CHECKED and the reason.
5. WHEN a Check runs but evidence is insufficient to conclude, THE ClaimShield SHALL create a Finding with Finding_Status INCONCLUSIVE.
6. THE ClaimShield SHALL keep the Finding and its provenance unchanged after creation, and record any later Investigator annotation as a separate audit event.

### Requirement 4: Orchestration

**User Story:** As an operator, I want a reliable orchestrator, so that every claim is processed completely, in parallel where possible, and uncertain results reach a human.

#### Acceptance Criteria

1. WHEN a Claim is submitted for processing, THE Orchestrator SHALL determine the applicable Checks from the Claim's data and available Documents.
2. THE Orchestrator SHALL run independent Checks in parallel.
3. THE Orchestrator SHALL record each Agent execution with state, start time, end time, attempt count and error.
4. IF an Agent execution exceeds its configured timeout, THEN THE Orchestrator SHALL mark its Checks INCONCLUSIVE and retry up to the configured retry count.
5. WHEN an Agent returns output, THE Orchestrator SHALL validate the output against the Finding schema and discard invalid output with an error record.
6. WHEN Findings from different Agents describe the same underlying fact, THE Orchestrator SHALL merge them into one Finding that lists all contributing Checks and sources.
7. WHEN any Agent or Check has Finding_Status INCONCLUSIVE and the Claim would otherwise fall in the low Routing_Band, THE Orchestrator SHALL flag the Claim for human review.
8. THE Orchestrator SHALL NOT set a Claim's final outcome to rejected or denied.
9. WHEN the same Idempotency_Key is received twice for processing the same Claim, THE Orchestrator SHALL start one processing run and return the existing run for the second request.

### Requirement 5: Risk Assessment

**User Story:** As an Investigator, I want a transparent and configurable risk score, so that I understand why a claim is routed and can trust the scoring is stable.

#### Acceptance Criteria

1. THE ClaimShield SHALL calculate the Risk_Assessment from deduplicated Findings using weights and Routing_Band thresholds loaded from versioned configuration.
2. THE ClaimShield SHALL store with each Risk_Assessment the Rule_Version, the configuration version and the Findings with their score contributions.
3. THE ClaimShield SHALL exclude Findings with Finding_Status NOT_CHECKED or INFORMATIONAL from the numeric score and list them separately.
4. THE ClaimShield SHALL count correlated Findings once, so that one underlying fact adds to the score only once.
5. THE ClaimShield SHALL present the Risk_Assessment as a score from 0 to 100 and label it as an ordering signal and not a probability, until a calibrated model on a Labelled_Dataset is installed.
6. WHERE the default configuration applies, THE ClaimShield SHALL use the Routing_Band thresholds 30 and 60.
7. WHEN an Administrator changes Routing_Band thresholds, THE ClaimShield SHALL apply the change to later assessments and record the change in the Audit_Log.
8. WHEN a Claim is re-assessed under a different configuration version, THE ClaimShield SHALL keep the earlier Risk_Assessment available.

### Requirement 6: Human-in-the-Loop Decisions

**User Story:** As an Investigator, I want to record decisions with reasons, so that every outcome is owned by a person and can be audited.

#### Acceptance Criteria

1. THE ClaimShield SHALL accept Investigator_Decision values approve, APPROVE_EXCEPTION, REQUEST_DOCUMENTS, REFER_TO_FIU and deny only from a user with the Investigator role or the Fraud_Team role.
2. WHEN an Investigator_Decision is submitted, THE ClaimShield SHALL require a reason of at least one non-blank character.
3. IF an Investigator_Decision is submitted by a user without a permitted role, THEN THE ClaimShield SHALL reject it with a forbidden error and record the attempt in the Audit_Log.
4. WHEN an Investigator_Decision is recorded, THE ClaimShield SHALL store the user, timestamp, reason, notes and the Risk_Assessment identifier that was visible.
5. WHEN a Claim has a Routing_Band of investigate, THE ClaimShield SHALL keep the Claim open until an Investigator_Decision is recorded.
6. THE ClaimShield SHALL allow a later Investigator_Decision on the same Claim and keep all earlier decisions in history.
7. WHEN an Investigator marks a Finding as a false positive or confirmed, THE ClaimShield SHALL store a feedback record linked to the Finding and Rule_Version.

### Requirement 7: Authentication, Roles and Access Control

**User Story:** As an administrator, I want role-based access, so that only authorised people can see claims and take actions.

#### Acceptance Criteria

1. THE ClaimShield SHALL authenticate every API request except the health endpoint and the customer intake endpoints.
2. THE ClaimShield SHALL support the roles Investigator, Ops_Manager, Fraud_Team and Administrator.
3. WHERE the local environment is used, THE ClaimShield SHALL authenticate with seeded Synthetic_Data users and per-user credentials, and SHALL NOT use a shared static key.
4. IF a request lacks valid credentials, THEN THE ClaimShield SHALL return an unauthorised error.
5. IF an authenticated user calls an operation outside the permissions of their role, THEN THE ClaimShield SHALL return a forbidden error.
6. THE ClaimShield SHALL restrict the direct assessment endpoint (POST /api/assess) to users with the Investigator, Fraud_Team or Administrator role.
7. WHEN the direct assessment endpoint runs outside an explicit test mode, THE ClaimShield SHALL apply the same policy checks as claim processing.
8. WHILE the direct assessment endpoint runs, THE ClaimShield SHALL NOT write the Claim to claim history unless an explicit test mode flag is set, and SHALL label any such record as test.
   - Interim implementation (task 1.5, until role-based access in task 12): the endpoint requires the internal key; the test mode flag is the query parameter `test_mode=true`, which also skips the policy checks of criterion 7; records written in test mode carry `is_test=true`.
9. WHEN a policy lookup is requested with a policy number and date of birth, THE ClaimShield SHALL limit attempts per client and per policy number to a configured rate and return a rate-limit error above that rate.

### Requirement 8: Customer Intake Channel and Report Wording

**User Story:** As a policyholder, I want to submit a claim and see an honest status, so that I am not told my claim is verified when it has not been.

#### Acceptance Criteria

1. THE ClaimShield SHALL keep the customer submission journey as an intake channel that creates a Claim and uploads Documents.
2. THE ClaimShield SHALL set analysis settings, including whether the LLM_Adapter is used, from server configuration and ignore any client-supplied analysis setting.
3. THE ClaimShield SHALL describe check results to customers only as "No issues found", "Verification unavailable" or "SIMULATED".
   - Clarification: a check backed by a simulated registry is labelled "SIMULATED". A check with a low score is labelled "No issues found". A check with any other score is labelled "Verification unavailable", so that no Finding or score is disclosed (Requirement 8.5).
   - Clarification: customer outcome text says the claim was "received" and never states that the claim was approved, verified or passed all checks.
4. IF no authoritative source has confirmed a fact, THEN THE ClaimShield SHALL NOT state that the fact is verified, genuine or authentic in any customer-facing or investigator-facing text.
5. THE ClaimShield SHALL NOT disclose Findings, scores or fraud indicators to the customer.
6. WHEN a Claim fails a policy eligibility rule, THE ClaimShield SHALL return the rule violation to the customer as a validation error and store the Claim with the Finding for Investigator review.

### Requirement 9: Document Intake, Storage and Extraction

**User Story:** As an Investigator, I want documents safely stored and their content extracted with source references, so that I can compare extracted values with the original.

#### Acceptance Criteria

1. WHEN a Document is uploaded, THE ClaimShield SHALL validate file type against an allow-list, enforce a configured maximum size and calculate a SHA-256 checksum.
2. IF a Document fails file type, size or content validation, THEN THE ClaimShield SHALL reject it with an error naming the failed rule and store nothing.
3. THE ClaimShield SHALL store Documents through the Storage_Adapter under generated identifiers and not under client-supplied file names.
4. WHEN a digital PDF is stored, THE ClaimShield SHALL extract text and fields through the Extraction_Adapter and save an Extraction_Result with page numbers.
5. IF a Document has no extractable text, THEN THE ClaimShield SHALL mark its text-dependent Checks INCONCLUSIVE with the reason "no extractable text".
6. THE ClaimShield SHALL store both the original extracted value and the Normalised_Facts value for each field.
7. WHEN the same checksum is uploaded for a Claim twice, THE ClaimShield SHALL return the existing Document.
8. THE ClaimShield SHALL support list and retrieve of Documents, with page-level access for the document viewer.

### Requirement 10: LLM Use, PII Minimisation and Prompt-Injection Safety

**User Story:** As a security officer, I want LLM use limited, minimised and validated, so that PII is protected and document content cannot steer decisions.

#### Acceptance Criteria

1. THE ClaimShield SHALL send to the LLM_Adapter only fields required for the specific task and replace claimant names and direct identifiers with pseudonyms.
2. THE ClaimShield SHALL treat Document text as untrusted data and place it in a delimited data section that the prompt marks as non-instructional.
3. WHEN the LLM_Adapter returns output, THE ClaimShield SHALL validate it against a strict JSON schema and discard output that fails validation.
4. IF LLM output fails validation or the LLM_Adapter errors, THEN THE ClaimShield SHALL fall back to rules-only results and mark the affected AI Checks INCONCLUSIVE.
5. THE ClaimShield SHALL use the LLM_Adapter only for document understanding, semantic comparison, summarisation and explanation.
6. THE ClaimShield SHALL NOT use LLM output alone to create a CONFIRMED_RULE_VIOLATION Finding or to set a Routing_Band.
7. WHEN Document text contains instructions addressed to the model, THE ClaimShield SHALL ignore them, and the Checks SHALL return the same Findings as for the same Claim without those instructions.
8. THE ClaimShield SHALL record for each LLM call the Rule_Version of the prompt, the adapter used and the fields sent, without storing PII in the record.

### Requirement 11: Policy, Eligibility and Deterministic Validation

**User Story:** As an Investigator, I want exact rule checks done deterministically, so that policy and arithmetic results are reproducible.

#### Acceptance Criteria

1. THE Policy_Eligibility Agent SHALL implement Use_Cases 1-12 deterministically, comparing Claim dates, policy dates, waiting and exclusion periods, covered treatments, sum insured, insured persons and other policies for the same expenses.
2. WHEN a Claim date falls before policy inception or after expiry, THE Policy_Eligibility Agent SHALL create a CONFIRMED_RULE_VIOLATION Finding with the dates compared.
3. WHEN a policy was bought less than a configured number of days before the admission date, THE Policy_Eligibility Agent SHALL create a POTENTIAL_ANOMALY Finding.
4. WHEN a pre-authorisation exists, THE Billing_Intelligence Agent SHALL compare the final bill with the pre-authorised amount and create a Finding when the final bill exceeds it by more than the configured percentage.
5. WHEN a GSTIN is present on an invoice, THE Billing_Intelligence Agent SHALL validate its format and check digit and create a CONFIRMED_RULE_VIOLATION Finding if validation fails.
6. IF a GSTIN is absent from an invoice for a service category configured as generally GST exempt, THEN THE Billing_Intelligence Agent SHALL create no Finding for the absence.
7. WHEN invoice line items are extracted, THE Billing_Intelligence Agent SHALL recompute line and invoice totals and create a CONFIRMED_RULE_VIOLATION Finding if the stated total differs from the computed total beyond a configured rounding tolerance.
8. THE Policy_Eligibility Agent SHALL mark Use_Case 3 (undisclosed pre-existing disease) INCONCLUSIVE or NOT_CHECKED where medical history data is unavailable.

### Requirement 12: Duplicate Detection

**User Story:** As an Investigator, I want duplicates found once and clearly explained, so that repeated billing is visible without inflating the score.

#### Acceptance Criteria

1. THE Duplicate_Detection Agent SHALL implement Use_Cases 13-22 using exact match on invoice number, provider, date and amount and normalised or fuzzy match for modified resubmissions.
2. WHEN an invoice matches an earlier invoice under a different Claim, policy or family member, THE Duplicate_Detection Agent SHALL create one Finding that references each matching Claim and Document.
3. WHEN a resubmitted invoice differs from an earlier one in amount or dates only, THE Duplicate_Detection Agent SHALL create a Finding that lists the differing fields.
4. WHEN cashless and reimbursement requests exist for the same stay, THE Duplicate_Detection Agent SHALL create a Finding.
5. THE Duplicate_Detection Agent SHALL be the only Agent that scores duplicate invoices, duplicate invoice numbers and duplicate tax identifiers.
6. THE Duplicate_Detection Agent SHALL mark Use_Case 22 (duplicates across insurers) NOT_CHECKED with the limitation that data sharing is not authorised or available.
7. WHEN a Claim is re-processed, THE Duplicate_Detection Agent SHALL NOT match the Claim to its own earlier run.

### Requirement 13: Document Forensics and Cross-Document Validation

**User Story:** As an Investigator, I want document anomalies reported as indicators with alternatives, so that legitimate documents are not wrongly accused.

#### Acceptance Criteria

1. THE Document_Forensics Agent SHALL implement Use_Cases 23-38 with the Detection_Method recorded per Finding.
2. THE Document_Forensics Agent SHALL treat PDF metadata and font or layout anomalies as indicators and assign them severity low or medium.
3. WHEN a Document creation date precedes the admission date, THE Document_Forensics Agent SHALL evaluate the rule by Document type and create no Finding for prescriptions and pre-admission reports, and otherwise create a Finding of severity no higher than medium that lists alternative explanations.
4. THE Document_Forensics Agent SHALL match editor software by an allow-listed set of exact producer names and not by substring.
5. WHEN the modification date exceeds the creation date by more than a configured period for a Document type, THE Document_Forensics Agent SHALL create a low-severity POTENTIAL_ANOMALY Finding that lists alternative explanations.
6. WHEN Documents of the same Claim contain differing values for patient name, dates, amounts or invoice number, THE ClaimShield SHALL compare them using exact-field comparison and present both original and normalised values.
7. WHERE the LLM_Adapter is available, THE ClaimShield SHALL add semantic comparison for text fields and handle spelling variants, date formats and OCR errors.
8. IF a field mismatch is ambiguous after normalisation, THEN THE ClaimShield SHALL create an INCONCLUSIVE Finding and route the field to human review.
9. THE Document_Forensics Agent SHALL mark Use_Cases 30 (fake doctor signatures) and 31 (forged stamps and seals) NOT_CHECKED unless an image-analysis capability is configured.

### Requirement 14: Invoice Authenticity and Hospital Verification

**User Story:** As an Investigator, I want an honest authenticity state for each invoice, so that I can see what has and has not been confirmed.

#### Acceptance Criteria

1. THE ClaimShield SHALL assign each invoice exactly one Invoice_Authenticity_State.
2. WHEN a Hospital_Verification_Adapter confirms an invoice, THE ClaimShield SHALL set the state to "Confirmed by authorised hospital source".
3. WHEN the provider identity matches reference data and no confirmation exists, THE ClaimShield SHALL set the state to "Provider identity matched, invoice not confirmed".
4. WHILE a verification request is outstanding, THE ClaimShield SHALL set the state to "Verification pending" and store the request.
5. IF the Hospital_Verification_Adapter is unavailable or returns no result, THEN THE ClaimShield SHALL set the state to "Verification unavailable".
6. WHEN Document_Forensics or Duplicate_Detection create Findings with severity medium or higher for the invoice, THE ClaimShield SHALL set the state to "Potential manipulation indicators".
7. WHERE the local simulated Hospital_Verification_Adapter is used, THE ClaimShield SHALL label every verification result SIMULATED in storage, API and UI.
8. THE ClaimShield SHALL store each external verification request and response with timestamps.

### Requirement 15: Billing, Provider, Customer and Operational Intelligence

**User Story:** As an Investigator and Ops_Manager, I want billing and operational anomalies identified against reference baselines, so that unusual patterns are visible.

#### Acceptance Criteria

1. THE Billing_Intelligence Agent SHALL implement Use_Cases 51-65 by comparing charges with configured reference ranges, prescriptions, stay dates and similar procedures.
2. WHEN a charge exceeds its configured reference range, THE Billing_Intelligence Agent SHALL create a POTENTIAL_ANOMALY Finding that states the range and its source.
3. WHEN a legitimate high-cost treatment is documented by consistent clinical documents, THE Billing_Intelligence Agent SHALL lower the Finding severity to informational and cite the supporting documents.
4. IF no reference range exists for a charge category, THEN THE Billing_Intelligence Agent SHALL mark the corresponding Check NOT_CHECKED.
5. WHEN a provider's claim volume in a period exceeds a configured multiple of its baseline, THE Provider_Intelligence Agent SHALL create a POTENTIAL_ANOMALY Finding for Use_Case 65.
6. THE Operational_Intelligence Agent SHALL implement Use_Cases 115-122 from approval, override, settlement, resubmission and post-submission change records and attribute each Finding to a pattern, not to an individual as a conclusion.
7. WHEN a Claim is changed after submission, THE ClaimShield SHALL record the change with before and after values and create a Finding for Use_Case 120.
8. WHEN a Claim is approved without required Documents, THE Operational_Intelligence Agent SHALL create a Finding for Use_Cases 118 and 122.
9. THE ClaimShield SHALL show Operational_Intelligence Findings only to the Ops_Manager, Fraud_Team and Administrator roles.

### Requirement 16: API Contract

**User Story:** As a developer, I want a documented, validated API, so that the UI and other clients can integrate without internal knowledge.

#### Acceptance Criteria

1. THE ClaimShield SHALL publish an OpenAPI document that describes every endpoint, schema, error and role requirement.
2. THE ClaimShield SHALL provide endpoints to create a Claim, upload a Document, list and retrieve Documents, start and retry processing with an Idempotency_Key, retrieve Extraction_Results, retrieve Findings and the risk report, submit an Investigator_Decision with notes, retrieve audit history, manage provider reference data, and retrieve Coverage_Matrix and system health.
3. WHEN a request body fails schema validation, THE ClaimShield SHALL return a validation error that names the failing fields.
4. WHEN a processing request is retried after a failed run, THE ClaimShield SHALL start a new run linked to the earlier run.
5. THE ClaimShield SHALL return generated identifiers and no sequential identifiers in all resources.
6. WHEN an asynchronous processing request is accepted, THE ClaimShield SHALL return a job identifier and make the job status retrievable.

### Requirement 17: Data Model, Privacy and Audit Trail

**User Story:** As a compliance officer, I want minimal PII, retention controls and a tamper-evident audit trail, so that the system is accountable.

#### Acceptance Criteria

1. THE ClaimShield SHALL persist in PostgreSQL: users and roles, Claims, Policies, member references, providers, doctors, Documents, Extraction_Results, Normalised_Facts, invoices and line items, Agent executions, Findings, Risk_Assessments, external verification requests and responses, Investigator reviews and decisions, Audit_Log events, Rule_Versions and feedback records.
2. THE ClaimShield SHALL store only the PII fields required by the active Checks.
3. WHEN a Claim passes its configured retention period, THE ClaimShield SHALL delete or anonymise its PII and Documents and record the action in the Audit_Log.
4. THE ClaimShield SHALL write an Audit_Log event for login, Claim access, Document access, processing runs, configuration changes, Investigator_Decisions and denied requests.
5. THE ClaimShield SHALL chain each Audit_Log event to the previous one with a hash so that alteration or deletion is detectable.
6. WHEN an Administrator runs the audit integrity check, THE ClaimShield SHALL report the first event whose hash does not match, or report that the chain is intact.
7. THE ClaimShield SHALL write structured logs with request identifier, user identifier and event type and SHALL NOT write PII or Document content to logs.
8. THE ClaimShield SHALL permit no update or delete of Audit_Log events through the API.

### Requirement 18: Investigator Dashboard

**User Story:** As an Investigator, I want one workspace showing the claim, its evidence and findings, so that I can decide efficiently and with context.

#### Acceptance Criteria

1. THE Investigator dashboard SHALL show a claims queue with filters for Routing_Band, status, provider, date range, assigned user and Finding category.
2. WHEN an Investigator opens a Claim, THE Investigator dashboard SHALL show claim details, a document viewer with page navigation, extracted fields beside source evidence, a cross-document comparison table, the invoice authenticity panel, and Findings grouped by category and severity.
3. THE Investigator dashboard SHALL show the risk explanation with each Finding's score contribution and the Rule_Version.
4. THE Investigator dashboard SHALL separate verified facts, rule violations, potential anomalies, missing evidence, external checks pending, checks not performed and human decisions.
5. THE Investigator dashboard SHALL show pending external verification status and the audit trail for the Claim.
6. THE Investigator dashboard SHALL provide an action panel to record an Investigator_Decision with a required reason.
7. WHILE a Finding is NOT_CHECKED, THE Investigator dashboard SHALL display it with its limitation and not as a pass.
8. WHERE the user has the Administrator role, THE Investigator dashboard SHALL show a use-case coverage view built from the Coverage_Matrix.

### Requirement 19: Use-Case Coverage Matrix

**User Story:** As an Administrator, I want an honest coverage view of all 126 use cases, so that the real capability of the system is clear.

#### Acceptance Criteria

1. THE ClaimShield SHALL maintain a Coverage_Matrix that lists all 126 Use_Cases with data requirements, method, dependencies, evidence, limitations, priority and implementation status.
2. THE ClaimShield SHALL assign priority P0 to Use_Cases 1-38, 51-65 and 115-122, and P1 or P2 to the others.
3. THE ClaimShield SHALL expose the Coverage_Matrix as a versioned machine-readable artifact and through the API and the Administrator view.
4. WHEN a Use_Case depends on data or integration that is unavailable in the local environment, THE ClaimShield SHALL show its status as not implemented locally with the dependency named.
5. THE ClaimShield SHALL NOT report a Use_Case as implemented unless an automated test covers its Check.
6. WHEN a Check is released or removed, THE ClaimShield SHALL update the Coverage_Matrix in the same change.

### Requirement 20: Testing and Evaluation

**User Story:** As a maintainer, I want a complete automated test suite and honest evaluation, so that behavior is verified and no accuracy is overstated.

#### Acceptance Criteria

1. THE ClaimShield SHALL include at least one unit test per implemented rule covering a triggering and a non-triggering input.
2. THE ClaimShield SHALL include pipeline integration tests, LLM output contract tests, API and role-access tests, and failure, retry and idempotency tests.
3. THE ClaimShield SHALL include Synthetic_Data scenarios for: a genuine claim, a duplicate invoice, a changed amount, a date mismatch, missing documents, OCR errors, name spelling variants, a legitimate high-cost treatment, unusual but valid billing, provider verification unavailable, forged-looking metadata with valid evidence, conflicting documents and prompt injection inside a PDF.
4. WHEN the scenario "forged-looking metadata with valid evidence" is assessed, THE ClaimShield SHALL create no CONFIRMED_RULE_VIOLATION Finding from metadata alone.
5. WHEN the scenario "prompt injection inside a PDF" is assessed, THE ClaimShield SHALL produce the same Risk_Assessment as the same Claim without the injected text.
6. WHEN the scenario "genuine claim" is assessed, THE ClaimShield SHALL assign the low Routing_Band.
7. THE ClaimShield SHALL report precision and recall only when computed on a Labelled_Dataset, and SHALL NOT present accuracy figures derived from Synthetic_Data.
8. THE ClaimShield SHALL run the test suite in continuous integration without cloud credentials.
