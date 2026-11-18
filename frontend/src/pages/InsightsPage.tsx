import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { motion } from 'motion/react'
import { ArrowLeft, CalendarDays, Check, Circle, Lightbulb, Receipt, ShieldCheck, Wallet } from 'lucide-react'
import { api, ApiError, type CustomerReport } from '../api'
import { Alert, Card, Spinner } from '../components/ui'
import { cn, fmtDate, inr } from '../lib/utils'

const BAR = ['bg-indigo-500', 'bg-violet-500', 'bg-sky-500', 'bg-teal-500', 'bg-emerald-500', 'bg-amber-500', 'bg-slate-400']

export default function InsightsPage() {
  const { claimId = '' } = useParams()
  const [report, setReport] = useState<CustomerReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.status(claimId)
      .then((s) => (s.report ? setReport(s.report) : setError('Insights are available once your claim has been processed.')))
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'We could not find this claim.' : 'Could not load insights.'))
  }, [claimId])

  if (error) return <Alert tone="amber" className="mx-auto max-w-xl">{error}</Alert>
  if (!report) return <div className="grid place-items-center py-24"><Spinner className="size-8" /></div>

  const { insights: i, claim: c } = report
  const pct = i.coverage.claimed_pct ?? 0
  const missing = i.checklist.filter((d) => d.required && !d.received)

  return (
    <div className="w-full space-y-6">
      <div>
        <Link to={`/claims/${claimId}`} className="inline-flex items-center gap-1 text-sm text-indigo-700 hover:underline"><ArrowLeft className="size-4" aria-hidden /> Back to your claim</Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">Insights for claim <span className="font-mono text-xl">{c.claim_id}</span></h1>
        <p className="text-sm text-slate-600">A closer look at what you submitted. This does not show how your claim will be decided.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat icon={<CalendarDays className="size-5" aria-hidden />} label="Hospital stay" value={`${i.stay.days} day${i.stay.days === 1 ? '' : 's'}`} sub={`${fmtDate(c.admission_date)} – ${fmtDate(c.discharge_date)}`} />
        <Stat icon={<Wallet className="size-5" aria-hidden />} label="Claimed" value={inr(c.claimed_amount)} sub={`about ${inr(i.stay.per_day)} per day`} />
        <Stat icon={<ShieldCheck className="size-5" aria-hidden />} label="Plan" value={i.coverage.plan ?? '—'} sub={i.coverage.valid_to ? `valid until ${fmtDate(i.coverage.valid_to)}` : ''} />
      </div>

      {i.amounts && <Card className="p-6">
        <h2 className="font-semibold text-slate-900">Claimed amount compared with your bill</h2>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-slate-500">Amount you claimed</dt><dd className="font-medium text-slate-900">{inr(i.amounts.claimed)}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Total on your bill</dt><dd className="font-medium text-slate-900">{inr(i.amounts.bill_total)}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Sum of itemised charges</dt><dd className="font-medium text-slate-900">{inr(i.amounts.items_sum)}</dd></div>
        </dl>
        {i.amounts.claim_vs_bill !== 0 && (
          <p className="mt-4 rounded-lg bg-yellow-50 px-3 py-2 text-sm text-yellow-900 ring-1 ring-yellow-200">
            You claimed {inr(Math.abs(i.amounts.claim_vs_bill))} {i.amounts.claim_vs_bill > 0 ? 'more' : 'less'} than the total on your bill.
            {i.amounts.claim_vs_bill > 0 && ' A claim is normally for the billed amount or less, so a specialist will look at this.'}
          </p>
        )}
        {i.amounts.bill_vs_items !== 0 && (
          <p className="mt-2 rounded-lg bg-yellow-50 px-3 py-2 text-sm text-yellow-900 ring-1 ring-yellow-200">
            The bill total differs from the sum of its itemised charges by {inr(Math.abs(i.amounts.bill_vs_items))}.
          </p>
        )}
        {i.amounts.claim_vs_bill === 0 && i.amounts.bill_vs_items === 0 && (
          <p className="mt-4 text-sm text-slate-600">Your claimed amount matches your bill.</p>
        )}
      </Card>}

      {i.coverage.sum_insured != null && (
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">How much of your cover this claim uses</h2>
          <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${pct}% of the sum insured`}>
            <motion.div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct)}%` }} transition={{ duration: 0.9 }} />
          </div>
          <div className="mt-2 flex justify-between text-sm text-slate-600">
            <span>{inr(c.claimed_amount)} claimed ({pct}%)</span>
            <span>Sum insured {inr(i.coverage.sum_insured)}</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">Other claims on your policy in the same period also count towards the sum insured.</p>
        </Card>
      )}

      <Card className="p-6">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Receipt className="size-4 text-indigo-600" aria-hidden /> Where your bill goes</h2>
        <p className="text-xs text-slate-500">Bill {i.bill.invoice_number} dated {fmtDate(i.bill.invoice_date)}</p>
        <ul className="mt-4 space-y-3">
          {i.bill.items.map((it, k) => (
            <li key={k}>
              <div className="flex justify-between text-sm"><span className="text-slate-800">{it.description}</span><span className="font-medium text-slate-900">{inr(it.amount)} <span className="text-xs font-normal text-slate-500">({it.share}%)</span></span></div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                <motion.div className={cn('h-full rounded-full', BAR[k % BAR.length])} initial={{ width: 0 }} animate={{ width: `${it.share}%` }} transition={{ delay: 0.1 * k, duration: 0.7 }} />
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex justify-between border-t border-slate-100 pt-3 text-sm font-semibold text-slate-900"><span>Bill total</span><span>{inr(i.bill.total)}</span></div>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">Your documents</h2>
          <ul className="mt-3 space-y-2">
            {i.checklist.map((d) => (
              <li key={d.doc_type} className="flex items-center gap-2 text-sm">
                {d.received ? <Check className="size-4 text-emerald-600" aria-hidden /> : <Circle className={cn('size-4', d.required ? 'text-rose-400' : 'text-slate-300')} aria-hidden />}
                <span className={d.received ? 'text-slate-800' : 'text-slate-500'}>{d.label}</span>
                <span className="ml-auto text-xs text-slate-400">{d.received ? 'received' : d.required ? 'needed' : 'optional'}</span>
              </li>
            ))}
          </ul>
          {missing.length > 0 && <p className="mt-3 text-xs text-rose-700">Please send the missing document(s) so we can finish your claim.</p>}
        </Card>
        <Card className="p-6">
          <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Lightbulb className="size-4 text-amber-500" aria-hidden /> Tips for a smooth claim</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-700">
            {i.tips.map((t) => <li key={t} className="flex gap-2"><span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-400" />{t}</li>)}
          </ul>
        </Card>
      </div>
    </div>
  )
}

function Stat({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-xs text-slate-500"><span className="text-indigo-600">{icon}</span>{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500">{sub}</div>
    </Card>
  )
}
