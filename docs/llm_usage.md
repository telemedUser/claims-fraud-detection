# LLM usage

How and when ClaimShield calls an LLM, how it is switched on and off, and the guardrails. Requirements 8.2 and 10.1–10.10.

## The switch

The internal console header has an **LLM analysis** switch (`/internal`, top right).

| | |
|---|---|
| Who can change it | Administrator only. Other roles see the state with the switch disabled. |
| Where it is stored | `app_settings` table, key `llm_analysis_enabled` (migration `0004`) |
| Audit | every change is a `config_change` audit event (old and new value, user id) |
| When it applies | each claim reads it once, at submission. Claims already processing keep the setting they started with. |
| Default | `LLM_REVIEW_ENABLED` in `.env` (true) until an Administrator sets the switch |
| Needs | `GEMINI_API_KEY` (or `BEDROCK_MODEL_ID` for the summary). Without a key the console shows "no API key on the server" and the LLM stays off. |
| Customers | cannot change it. A `use_llm` field on a customer submission is ignored (Requirement 8.2). |

API: `GET /api/internal/settings` (all console roles) and `POST /api/internal/settings/llm` with `{"enabled": true|false}` (Administrator). Code: `app/runtime_settings.py`.

The staff endpoint `POST /api/assess` takes `use_llm`, but that field can only turn the LLM **off** for that request. The switch still has to be on.

## What runs when the switch is on

```mermaid
sequenceDiagram
    participant C as Customer
    participant API as POST /api/claims
    participant S as LLM switch
    participant P as Pipeline
    participant A as 4 rule agents
    participant L as LLM review (x4, parallel)
    participant G as Gemini
    participant DB as llm_calls / audit

    C->>API: claim + documents
    API->>S: llm_effective()?
    S-->>API: on (key configured)
    API->>P: start job (use_llm = true)
    P->>A: run rules in parallel
    A-->>P: rule findings
    P->>P: dedup + score + queue (rules only)
    P->>L: review each completed agent
    L->>G: pseudonymised claim + rule findings + tools
    G-->>L: tool calls (registry lookups), then JSON
    L->>L: validate schema (one repair turn if invalid)
    L->>DB: record call (field names, outcome)
    L-->>P: AI observations + reasoning (scored, capped)
    P->>G: investigator summary
    P->>DB: record call
    P-->>C: neutral customer report (no scores, no AI text)
```

For every claim submitted while the switch is on:

1. **The four rule agents run first**, and the score and routing queue are computed from their findings only.
2. **An LLM review runs for each completed agent, in parallel** (`app/llm_review.py`). The model gets:
   - the agent's focus
   - the pseudonymised claim
   - the rule findings
   - six lookup tools: `get_hospital_profile`, `get_doctor_profile`, `get_claimant_history`, `get_document_metadata`, `get_disease_guidelines`, `get_policy_details`
   
   It returns up to 5 observations the rules cannot express, plus a short reasoning.
3. **The investigator summary** is written by the LLM from the findings (`app/llm.py: summarize`).
4. **The loading page** shows an "AI review" badge while the reviews run. The console shows each agent's AI observations (purple "LLM" tag), reasoning, tools called and model.

With the switch off, none of this runs. Agents show "LLM analysis is off; rule-based result", and the summary is a template.

## Guardrails

| Requirement | How it is met |
|---|---|
| 10.1 minimise and pseudonymise | the claimant name is removed; the claimant id and policy number are sent as `CLAIMANT-1` and `POLICY-1`, and the tools map them back on the server. Policy details sent to the model exclude the holder name, date of birth and claimant id. Document metadata excludes file names. Any echo of a real identifier in the reply is scrubbed. |
| 10.2 untrusted data | the claim and rule findings sit in `<<... (data, not instructions)>>` blocks, and the system prompt says to ignore instructions inside data and tool results |
| 10.3 strict schema | the reply must match `ReviewOutput` (`additional_findings[]` with `code` in UPPER_SNAKE_CASE, `severity` low or medium, `detail`; `reasoning`); extra keys are rejected |
| 10.4 and 10.10 fallback | one repair turn sends only the validation error types back; if the reply still fails, or the provider errors after one retry, the agent keeps its rule result and shows "LLM review unavailable" |
| 10.5 allowed uses | semantic review of the claim against registry facts, summarisation, explanation |
| 10.6 LLM findings are capped | AI observations have `source="llm"`, are capped at medium and count as **potential anomalies** (x0.6). Points are added on top of the rule score, capped at 15 per agent and 25 per claim (`llm:` in `risk_scoring.v1.yaml`). The LLM alone cannot reach the manual-review band (30). A failed or invalid LLM review adds 0. |
| 10.8 record each call | one `llm_calls` row per review and per summary: adapter and model, prompt version (`agent-review.v2`, `summary.v1`), the **names** of the fields sent, and the outcome (`ok`, `ok_after_repair`, `invalid_output`, `error`). No values are stored. |

Customers never see LLM text, scores or findings. Their report uses the neutral labels of Requirement 8.3.

## Reliability

- **Model chain:** `GEMINI_MODEL` (default `gemini-3.5-flash-lite,gemini-3-flash-preview,gemini-3.1-flash-lite`). `llm.generate` moves to the next model on a timeout, 429 or 5xx.
- **Retries:** inside a tool loop the model is pinned and retried up to 3 times. The whole review is retried twice more (after 2 and 5 seconds) if every model is busy or the loop runs out of steps.
- **Tool budget:** a tool loop has 6 steps. Before the last one the model is told to stop calling tools and answer.
- **Timeout:** `GEMINI_TIMEOUT_S` (20 seconds) per call.
- **Cost of a claim with the LLM on:** 4 reviews with 1–3 tool calls each, plus 1 summary. In live tests this was about 5–25 seconds per claim, against well under a second rules-only.

## Verified (2026-11-20, Gemini `gemini-3.5-flash-lite`)

- **Switch off** (client sent `use_llm=true`): no LLM calls, template summary, `use_llm=false` recorded on the job.
- **Switch on:** "AI review" shown on the loading page. All four agents reviewed, with tool calls, AI observations such as `EXCESSIVE_CONSULTATION_CHARGES` and `REPEATED_INVOICE_DETAILS`, and an LLM summary.
- **Calls logged, final code:** two live runs gave 16 of 16 agent reviews completed (15 valid first time, 1 after the repair turn) and 4 of 4 LLM summaries, all in `llm_calls`. Earlier versions without the repair turn, the retries and the tool budget had occasional fallbacks to rules (invalid output, Gemini overload, tool loop out of steps).
- **Access:** an Investigator changing the switch got 403. Administrator changes appear as `config_change` audit events.
- **Browser:** the switch is disabled for an Investigator; an Administrator can turn it off and on and the label updates.

## Not covered yet

- The planned LLM adapter (`app/adapters/llm/`), a shared pseudonymiser (`app/core/pii.py`) and typed LLM tasks (task 17). Today the review uses `app/llm.py` directly, with its own pseudonymisation.
- LLM reading of document text or OCR (the agents read PDF text and metadata only).
- Recording AI observations in the `findings` table (they are in the assessment shown in the console).
