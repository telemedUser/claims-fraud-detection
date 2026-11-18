export const cn = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

const inrFmt = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const inr = (n: number | null | undefined) => (n == null || Number.isNaN(n) ? '—' : inrFmt.format(n))

/** Formats a date-only ISO string (YYYY-MM-DD) without timezone shifts. */
export function fmtDate(iso?: string | null) {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function fmtDateTime(iso?: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export const todayIso = () => {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

export const daysBetween = (a: string, b: string) =>
  Math.round((new Date(b + 'T00:00:00').getTime() - new Date(a + 'T00:00:00').getTime()) / 86400000)

export const fileSize = (b: number) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`)

export const uid = () => Math.random().toString(36).slice(2, 10)

export const ms = (v: number | null | undefined) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${v.toFixed(v < 10 ? 1 : 0)} ms`)

export const scoreTone = (s: number | null | undefined) =>
  s == null ? 'slate' : s >= 60 ? 'red' : s >= 30 ? 'amber' : 'green'

export const DECISION_LABEL: Record<string, string> = {
  auto_approve: 'Low risk',
  manual_review: 'Manual review',
  investigate: 'Investigate',
}

export const DOC_LABEL: Record<string, string> = {
  medical_bill: 'Medical bill',
  medical_report: 'Medical report / discharge summary',
  prescription: 'Prescription',
  lab_report: 'Lab report',
  payment_receipt: 'Payment receipt',
  other: 'Other document',
}

export const CHECK_OUTCOME_LABEL = {
  no_issues: 'No issues found',
  unavailable: 'Specialist review',
  simulated: 'SIMULATED',
} as const

