import { ChevronRight, Inbox, Sparkles } from 'lucide-react'
import type { InternalSummary, internalApi, Overview } from '../../api'
import { Badge, Spinner } from '../../components/ui'
import { DECISION_LABEL, fmtDateTime, inr, ms, scoreTone } from '../../lib/utils'
import { DECISION_TONE } from './common'
import ClaimDetail from './ClaimDetail'

type Props = {
  overview: Overview
  claims: InternalSummary[]
  client: ReturnType<typeof internalApi>
  selected: string | null
  onSelect: (id: string | null) => void
}

export default function ClaimsView({ overview, claims, client, selected, onSelect }: Props) {
  if (selected) return <ClaimDetail id={selected} overview={overview} client={client} onBack={() => onSelect(null)} />

  if (!claims.length)
    return (
      <div className="grid place-items-center rounded-2xl bg-white py-20 text-center ring-1 ring-slate-200">
        <Inbox className="size-10 text-slate-300" aria-hidden />
        <p className="mt-3 font-medium text-slate-700">No claims processed yet</p>
        <p className="mt-1 text-sm text-slate-500">
          Submit one from the{' '}
          <a href="/?demo=1" target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">customer journey</a>. It appears here live.
        </p>
      </div>
    )

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
            <tr>
              {['Claim', 'Submitted', 'Policyholder', 'Hospital', 'Condition', 'Amount', 'Risk', 'Decision', 'Duration', ''].map((h) => (
                <th key={h} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {claims.map((c) => {
              const t = scoreTone(c.risk_score)
              return (
                <tr key={c.claim_id} onClick={() => onSelect(c.claim_id)} className="cursor-pointer transition hover:bg-indigo-50/40">
                  <td className="px-4 py-3 font-mono text-xs font-medium text-slate-900">
                    <button type="button" className="hover:underline" onClick={() => onSelect(c.claim_id)}>{c.claim_id}</button>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDateTime(c.submitted_at)}</td>
                  <td className="px-4 py-3 text-slate-900">{c.claimant}</td>
                  <td className="px-4 py-3 text-slate-600">{c.hospital}</td>
                  <td className="px-4 py-3 text-slate-600">{c.diagnosis}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-900">{inr(c.claimed_amount)}</td>
                  <td className="px-4 py-3">
                    {c.status === 'processing' ? <Spinner className="size-4" /> : (
                      <span className={`font-semibold tabular-nums ${{ green: 'text-emerald-600', amber: 'text-amber-600', red: 'text-rose-600', slate: 'text-slate-400' }[t]}`}>
                        {c.risk_score ?? '—'}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {c.decision ? <Badge tone={DECISION_TONE[c.decision]}>{DECISION_LABEL[c.decision]}</Badge> : <Badge>{c.status}</Badge>}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">
                    {ms(c.duration_ms)} {c.use_llm && <Sparkles className="inline size-3.5 text-violet-500" aria-label="LLM review on" />}
                  </td>
                  <td className="px-2 py-3 text-slate-400"><ChevronRight className="size-4" aria-hidden /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
