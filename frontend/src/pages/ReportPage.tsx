import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import { CircleAlert, CircleCheck, Clock, FileText, Plus, Printer, SearchCheck, ShieldAlert } from 'lucide-react'
import { api, ApiError, type OutcomeCode, type StatusResponse } from '../api'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { CHECK_OUTCOME_LABEL, cn, DOC_LABEL, fmtDate, fmtDateTime, inr } from '../lib/utils'

const OUTCOME_STYLE: Record<OutcomeCode, { wrap: string; icon: ReactNode; chip: string }> = {
  approved: { wrap: 'from-emerald-500 to-teal-600', icon: <CircleCheck className="size-8" aria-hidden />, chip: 'Received' },
  under_review: { wrap: 'from-amber-500 to-orange-500', icon: <Clock className="size-8" aria-hidden />, chip: 'Received, under review' },
  verification: { wrap: 'from-rose-500 to-pink-600', icon: <ShieldAlert className="size-8" aria-hidden />, chip: 'Received, more information may be needed' },
}

export default function ReportPage() {
  const { claimId = '' } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<StatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .status(claimId)
      .then((s) => (s.status === 'processing' ? navigate(`/claims/${claimId}/processing`, { replace: true }) : setData(s)))
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'We could not find this claim.' : 'Could not load the report.'))
  }, [claimId, navigate])

  if (error) return <Alert className="mx-auto max-w-xl">{error}</Alert>
  if (!data) return <div className="grid place-items-center py-24"><Spinner className="size-8" /></div>
  if (data.status === 'failed' || !data.report)
    return <Alert tone="amber" className="mx-auto max-w-xl">{data.message ?? 'This claim is being reviewed manually.'}</Alert>

  const r = data.report
  const st = OUTCOME_STYLE[r.outcome.code]
  const c = r.claim

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className={cn('overflow-hidden rounded-2xl bg-gradient-to-br p-6 text-white shadow-lg sm:p-8', st.wrap)}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className="grid size-16 shrink-0 place-items-center rounded-2xl bg-white/20 ring-1 ring-white/30">{st.icon}</div>
          <div className="flex-1">
            <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">{st.chip}</span>
            <h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{r.outcome.title}</h1>
            <p className="mt-1 text-white/90">{r.outcome.message}</p>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-xs text-white/80">Claimed amount</div>
            <div className="text-2xl font-semibold">{inr(c.claimed_amount)}</div>
            <div className="mt-1 font-mono text-xs text-white/80">{c.claim_id}</div>
          </div>
        </div>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">Claim details</h2>
          <dl className="mt-4 grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            <D k="Policyholder" v={c.policyholder} />
            <D k="Policy" v={`${c.plan ?? ''} · ${c.policy_number ?? ''}`} />
            <D k="Hospital" v={`${c.hospital ?? '—'}${c.hospital_city ? `, ${c.hospital_city}` : ''}`} />
            <D k="Treating doctor" v={c.doctor ?? '—'} />
            <D k="Condition" v={c.diagnosis} />
            <D k="Hospital stay" v={`${fmtDate(c.admission_date)} – ${fmtDate(c.discharge_date)}`} />
            <D k="Bill number" v={c.invoice_number} />
            <D k="Submitted" v={fmtDateTime(c.submitted_at)} />
          </dl>
          <h3 className="mt-6 text-sm font-semibold text-slate-900">Documents received</h3>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {r.documents.map((d, i) => (
              <li key={i} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <FileText className="size-4 text-indigo-600" aria-hidden />
                <span className="min-w-0">
                  <span className="block truncate text-slate-800">{d.filename}</span>
                  <span className="text-xs text-slate-500">{DOC_LABEL[d.doc_type]}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-6">
          <Card className="p-6">
            <h2 className="flex items-center gap-2 font-semibold text-slate-900">
              <SearchCheck className="size-4 text-indigo-600" aria-hidden /> Automated checks
            </h2>
            <ul className="mt-4 space-y-3">
              {r.checks.map((ch, i) => (
                <motion.li key={ch.label} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + i * 0.08 }}
                  className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-slate-700">{ch.label}</span>
                  {ch.outcome === 'no_issues' ? (
                    <span className="flex items-center gap-1 font-medium text-slate-700"><CircleCheck className="size-4" aria-hidden /> {CHECK_OUTCOME_LABEL.no_issues}</span>
                  ) : (
                    <span className="flex shrink-0 items-center gap-1 font-medium whitespace-nowrap text-amber-700"><CircleAlert className="size-4" aria-hidden /> {CHECK_OUTCOME_LABEL[ch.outcome]}</span>
                  )}
                </motion.li>
              ))}
            </ul>
          </Card>
          <Card className="p-6">
            <h2 className="font-semibold text-slate-900">What happens next</h2>
            <ol className="mt-3 space-y-2 text-sm text-slate-700">
              {r.outcome.next_steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-indigo-100 text-[11px] font-semibold text-indigo-700">{i + 1}</span>
                  {s}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>

      <div className="flex flex-wrap justify-end gap-3 print:hidden">
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden /> Print / save PDF
        </Button>
        <Button onClick={() => navigate('/')}>
          <Plus className="size-4" aria-hidden /> New claim
        </Button>
      </div>
    </div>
  )
}

function D({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-slate-500">{k}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{v}</dd>
    </div>
  )
}
