// ---------------------------------------------------------------- customer journey types

export type Doctor = { id: string; name: string; specialty: string; qualification: string }
export type Hospital = { id: string; name: string; city: string; address: string; specialties: string[]; doctors: Doctor[] }
export type Disease = { id: string; name: string; category: string }
export type Policy = {
  policy_number: string
  holder_name: string
  plan: string
  sum_insured: number
  valid_from: string
  valid_to: string
  network_hospitals: Hospital[]
  covered_diseases: Disease[]
  not_covered: Disease[]
}
export type LineItem = { description: string; amount: number }
export type Invoice = { invoice_number: string; invoice_date: string; line_items: LineItem[]; total: number; tax_id?: string | null }
export type ClaimForm = {
  policy_number: string
  date_of_birth: string
  hospital_id: string
  doctor_id: string
  disease_id: string
  admission_date: string
  discharge_date: string
  claimed_amount: number
  invoice: Invoice
}
export type DocType = 'medical_bill' | 'prescription' | 'medical_report' | 'lab_report' | 'payment_receipt' | 'other'
export type StageStatus = 'pending' | 'running' | 'done'
export type Stage = { key: string; label: string; status: StageStatus; ai_review: boolean }
export type OutcomeCode = 'approved' | 'under_review' | 'verification'
export type CustomerReport = {
  outcome: { code: OutcomeCode; title: string; message: string; next_steps: string[] }
  checks: { label: string; outcome: 'no_issues' | 'unavailable' | 'simulated' }[]
  claim: {
    claim_id: string
    policy_number: string | null
    plan: string | null
    policyholder: string
    hospital: string | null
    hospital_city: string | null
    doctor: string | null
    diagnosis: string
    admission_date: string
    discharge_date: string
    claimed_amount: number
    invoice_number: string
    submitted_at: string
    completed_at: string | null
  }
  documents: { filename: string; doc_type: DocType }[]
}
export type StatusResponse = {
  claim_id: string
  status: 'processing' | 'completed' | 'failed'
  submitted_at: string
  stages: Stage[]
  report?: CustomerReport
  message?: string
}
export type DemoCase = { form: ClaimForm; documents: { doc_type: DocType; filename: string; url: string }[] }

// ---------------------------------------------------------------- internal console types

export type Severity = 'low' | 'medium' | 'high'
export type Decision = 'auto_approve' | 'manual_review' | 'investigate'
export type Finding = { code: string; severity: Severity; detail: string; source: 'rule' | 'llm' }
export type AgentResult = {
  agent: string
  score: number
  findings: Finding[]
  rule_score: number | null
  llm_used: boolean
  llm_points: number
  reasoning: string
  tool_calls: string[]
  llm_model: string | null
}
export type AgentTrace = {
  agent: string
  weight: number
  score: number
  weighted_contribution: number
  started_at_ms: number
  duration_ms: number
  finding_count: number
}
export type Thresholds = { manual_review_at: number; investigate_at: number }
export type Orchestration = {
  agents_run_in_parallel: boolean
  total_duration_ms: number
  sum_of_agent_durations_ms: number
  traces: AgentTrace[]
  weighted_score: number
  peak_agent: string
  peak_score: number
  peak_floor: number
  final_score: number
  score_rule: string
  thresholds: Thresholds
  decision_reason: string
}
export type Assessment = {
  claim_id: string
  risk_score: number
  decision: Decision
  agent_results: AgentResult[]
  orchestration: Orchestration
  summary: string
}
export type InternalSummary = {
  claim_id: string
  status: 'processing' | 'completed' | 'failed'
  submitted_at: string
  policy_number: string | null
  claimant: string
  hospital: string
  diagnosis: string
  claimed_amount: number
  use_llm: boolean
  risk_score: number | null
  decision: Decision | null
  duration_ms: number | null
}
export type StageState = { status: StageStatus; detail: string | null; started_ms: number | null; finished_ms: number | null }
export type JobEvent = { t_ms: number; stage: string; status: string; info: Record<string, unknown> }
export type InternalDetail = InternalSummary & {
  claim: Record<string, unknown>
  documents: { filename: string; doc_type: DocType; content_type: string; size: number }[]
  stages: Record<string, StageState>
  events: JobEvent[]
  error: string | null
  finished_at: string | null
  assessment: Assessment | null
  customer_view: StatusResponse
}
export type AgentInfo = { name: string; title: string; purpose: string; checks: string[]; weight: number; llm_focus: string }
export type Overview = {
  agents: AgentInfo[]
  tools: { name: string; description: string }[]
  scoring: {
    rule: string
    severity_points: Record<Severity, number>
    max_llm_points_per_agent: number
    max_llm_points_total: number
    llm_max_severity: string
    thresholds: Thresholds
  }
  llm: { enabled: boolean; requested?: boolean; provider_configured?: boolean; provider: string | null; models: string[] }
  claims_processed: number
}
export type ProfileSignal = { code: string; severity: Severity; detail: string; claim_ids: string[] }
export type ClaimantSummary = {
  claimant_id: string
  name: string
  policy_number: string | null
  plan: string | null
  claims: number
  total_claimed: number
  last_claim: string | null
  flagged_claims: number
  signals: number
  top_severity: Severity | null
}
export type ClaimantClaim = {
  claim_id: string
  submitted: string | null
  admission: string | null
  discharge: string | null
  amount: number
  hospital_id: string | null
  hospital: string | null
  doctor_id: string | null
  disease: string | null
  diagnosis: string | null
  invoice_number: string | null
  status: string
  decision: string | null
  is_test: boolean
  stay_days: number | null
  submission_lag_days: number | null
  days_to_term_end: number | null
  risk_score: number | null
  queue: Decision | null
  in_console: boolean
}
export type ClaimantProfile = {
  claimant: { claimant_id: string; name: string; relation: string | null; dob: string | null; policy_number: string | null }
  policy: { plan: string; sum_insured: number; valid_from: string; valid_to: string; network_hospital_ids: string[] } | null
  metrics: {
    claims: number
    total_claimed: number
    average_claim: number
    largest_claim: number
    hospitals: number
    doctors: number
    claims_last_90_days: number
    claims_last_365_days: number
    average_submission_lag_days: number | null
    decisions: Record<string, number>
    flagged_claims: number
    claims_near_policy_end: number
    first_claim: string | null
    last_claim: string | null
  }
  signals: ProfileSignal[]
  claims: ClaimantClaim[]
  config_version: string
}
export type LlmSwitch = {
  requested: boolean
  provider_configured: boolean
  effective: boolean
  provider: string | null
  source: 'default' | 'console'
  updated_by: string | null
  updated_at: string | null
}

// ---------------------------------------------------------------- client

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'We could not reach the server. Check your connection and try again.')
  }
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) {
    const b = body && typeof body === 'object' ? (body as { error?: { message?: unknown }; detail?: unknown }) : null
    const detail = typeof b?.error?.message === 'string' ? b.error.message : b?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Something went wrong. Please try again.')
  }
  return body as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  lookupPolicy: (policy_number: string, date_of_birth: string) =>
    request<Policy>('/api/policies/lookup', json({ policy_number, date_of_birth })),

  submitClaim: (form: ClaimForm, docs: { file: File; docType: DocType }[]) => {
    const fd = new FormData()
    fd.append('payload', JSON.stringify(form))
    fd.append('document_types', JSON.stringify(docs.map((d) => d.docType)))
    docs.forEach((d) => fd.append('documents', d.file, d.file.name))
    return request<{ claim_id: string }>('/api/claims', { method: 'POST', body: fd })
  },

  status: (id: string) => request<StatusResponse>(`/api/claims/${encodeURIComponent(id)}/status`),

  demo: (kind: 'clean' | 'suspicious') => request<DemoCase>(`/api/demo/${kind}`),

  demoFile: async (url: string, filename: string) => {
    const r = await fetch(url)
    if (!r.ok) throw new ApiError(r.status, 'Could not load the demo document.')
    return new File([await r.blob()], filename, { type: 'application/pdf' })
  },
}

// ---------------------------------------------------------------- auth (Bearer token, sessionStorage only)

export type Role = 'Investigator' | 'Ops_Manager' | 'Fraud_Team' | 'Administrator'
export type Me = { id: string; username: string; role: Role }

const TOKEN_KEY = 'claimshield.access_token'
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

let onUnauthorized: (() => void) | null = null
/** Register a callback fired after a 401 on an authenticated call (the token is already cleared). */
export const setUnauthorizedHandler = (fn: (() => void) | null) => {
  onUnauthorized = fn
}

async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const headers = { ...(init.headers as Record<string, string> | undefined), ...(token ? { Authorization: `Bearer ${token}` } : {}) }
  try {
    return await request<T>(path, { ...init, headers })
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      tokenStore.clear()
      onUnauthorized?.()
    }
    throw e
  }
}

export const authApi = {
  login: async (username: string, password: string) => {
    const r = await request<{ access_token: string; token_type: string; expires_in?: number; role: Role }>('/api/auth/login', json({ username, password }))
    tokenStore.set(r.access_token)
    return r
  },
  me: () => authed<Me>('/api/me'),
  logout: () => tokenStore.clear(),
}

export const internalApi = () => ({
  overview: () => authed<Overview>('/api/internal/overview'),
  claims: () => authed<InternalSummary[]>('/api/internal/claims'),
  claim: (id: string) => authed<InternalDetail>(`/api/internal/claims/${encodeURIComponent(id)}`),
  reset: () => authed<{ status: string }>('/api/internal/reset', { method: 'POST' }),
  settings: () => authed<{ llm_analysis: LlmSwitch }>('/api/internal/settings'),
  claimants: (q?: string) => authed<ClaimantSummary[]>(`/api/internal/claimants${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  claimant: (id: string) => authed<ClaimantProfile>(`/api/internal/claimants/${encodeURIComponent(id)}`),
  setLlm: (enabled: boolean) => authed<{ llm_analysis: LlmSwitch }>('/api/internal/settings/llm', json({ enabled })),
})
