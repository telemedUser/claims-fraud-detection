import { useState } from 'react'
import { ChevronRight, Inbox, Sparkles } from 'lucide-react'
import type { InternalSummary, internalApi, Me, Overview } from '../../api'
import { Badge, Spinner, type Tone } from '../../components/ui'
import { cn, DECISION_LABEL, fmtDateTime, inr, scoreTone } from '../../lib/utils'
import { DECISION_TONE } from './common'
import ClaimDetail from './ClaimDetail'
import { REVIEW_LABEL, REVIEW_TONE } from './ClaimReview'

type Props = {
  me: Me
  overview: Overview
  claims: InternalSummary[]
  client: ReturnType<typeof internalApi>
  selected: string | null
  onSelect: (id: string | null) => void
  onOpenClaimant?: (claimantId: string) => void
}

type Status = 'processing' | 'failed' | 'pending' | 'auto' | 'approve' | 'deny'
const STATUS: Record<Status, { label: string; tone: Tone }> = {
  processing: { label: 'Processing', tone: 'indigo' },
  failed: { label: 'Failed', tone: 'slate' },
  pending: { label: 'Pending review', tone: 'amber' },
  auto: { label: 'Auto-approved', tone: 'green' },
  approve: { label: REVIEW_LABEL.approve, tone: REVIEW_TONE.approve },
  deny: { label: REVIEW_LABEL.deny, tone: REVIEW_TONE.deny },
}

/** One status for the list: processing state, then the investigator's decision, then auto-approval
 *  (low risk and below the auto-approval amount; the backend routes everything else to a person). */
export function claimStatus(c: InternalSummary): Status {
  if (c.status !== 'completed') return c.status
  if (c.review?.decision === 'approve') return 'approve'
  if (c.review?.decision === 'deny') return 'deny'
  return c.decision === 'auto_approve' ? 'auto' : 'pending'
}

const FILTERS: { id: 'all' | Status; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending review' },
  { id: 'auto', label: 'Auto-approved' },
  { id: 'approve', label: 'Approved' },
  { id: 'deny', label: 'Rejected' },
  { id: 'processing', label: 'Processing' },
]

export default function ClaimsView({ me, overview, claims, client, selected, onSelect, onOpenClaimant }: Props) {
  const [filter, setFilter] = useState<'all' | Status>('all')
  if (selected) return <ClaimDetail id={selected} me={me} overview={overview} client={client} onBack={() => onSelect(null)} onOpenClaimant={onOpenClaimant} />

  if (!claims.length)
    return (
      <div className="grid place-items-center rounded-xl bg-white py-20 text-center ring-1 ring-indigo-100">
        <Inbox className="size-10 text-indigo-200" aria-hidden />
        <p className="mt-3 font-medium text-slate-700">No claims submitted yet</p>
        <p className="mt-1 text-sm text-slate-500">
          Submit one from the{' '}
          <a href="/?demo=1" target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">customer journey</a>. It appears here live.
        </p>
      </div>
    )

  const counts = claims.reduce<Record<string, number>>((m, c) => ({ ...m, [claimStatus(c)]: (m[claimStatus(c)] ?? 0) + 1 }), {})
  const rows = filter === 'all' ? claims : claims.filter((c) => claimStatus(c) === filter)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-indigo-950">Submitted claims</h1>
          <p className="text-sm text-slate-500">Newest first. Open a claim to see each agent's score, findings and output, review the documents and decide.</p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by status">
          {FILTERS.map((f) => {
            const n = f.id === 'all' ? claims.length : counts[f.id] ?? 0
            return (
              <button key={f.id} type="button" role="tab" aria-selected={filter === f.id} onClick={() => setFilter(f.id)}
                className={cn('rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition',
                  filter === f.id ? 'bg-indigo-600 text-white ring-indigo-600' : 'bg-white text-indigo-800 ring-indigo-200 hover:bg-indigo-50')}>
                {f.label} <span className="opacity-70">{n}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-indigo-100">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-indigo-600 text-xs tracking-wide text-white uppercase">
              <tr>
                {['Claim ID', 'Status', 'Submitted', 'Policyholder', 'Hospital', 'Amount', 'Risk', 'Queue', ''].map((h) => (
                  <th key={h} className={cn('px-4 py-3 font-medium whitespace-nowrap', h === 'Amount' && 'text-right')}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-indigo-50">
              {rows.map((c) => {
                const t = scoreTone(c.risk_score)
                const s = STATUS[claimStatus(c)]
                return (
                  <tr key={c.claim_id} onClick={() => onSelect(c.claim_id)} className="cursor-pointer transition hover:bg-indigo-50/60">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-indigo-900">
                      <button type="button" className="hover:underline" onClick={(e) => { e.stopPropagation(); onSelect(c.claim_id) }}>{c.claim_id}</button>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={s.tone}>{c.status === 'processing' && <Spinner className="size-3" />}{s.label}</Badge>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDateTime(c.submitted_at)}</td>
                    <td className="px-4 py-3 text-slate-900">{c.claimant}</td>
                    <td className="px-4 py-3 text-slate-600">{c.hospital}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-900">{inr(c.claimed_amount)}</td>
                    <td className="px-4 py-3">
                      {c.status === 'processing' ? <span className="text-slate-400">—</span> : (
                        <span className={`font-semibold tabular-nums ${{ green: 'text-emerald-600', amber: 'text-amber-600', red: 'text-rose-600', slate: 'text-slate-400' }[t]}`}>
                          {c.risk_score ?? '—'}
                        </span>
                      )}
                      {c.use_llm && <Sparkles className="ml-1 inline size-3.5 text-violet-500" aria-label="LLM review on" />}
                    </td>
                    <td className="px-4 py-3">
                      {c.decision ? <Badge tone={DECISION_TONE[c.decision]}>{DECISION_LABEL[c.decision]}</Badge> : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-2 py-3 text-indigo-300"><ChevronRight className="size-4" aria-hidden /></td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-sm text-slate-500">No claims with this status.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
