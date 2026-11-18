import { useEffect, useState } from 'react'
import { ArrowLeft, CalendarClock, ChevronRight, History, Search, ShieldAlert, UserRound } from 'lucide-react'
import type { ClaimantProfile, ClaimantSummary, internalApi } from '../../api'
import { Alert, Badge, Button, Input, Spinner } from '../../components/ui'
import { cn, DECISION_LABEL, fmtDate, inr } from '../../lib/utils'
import { DECISION_TONE, Panel, SEVERITY_TONE } from './common'

type Client = ReturnType<typeof internalApi>
const DECISION_TEXT: Record<string, string> = {
  approve: 'Approved', APPROVE_EXCEPTION: 'Approved (exception)', REQUEST_DOCUMENTS: 'Documents requested',
  REFER_TO_FIU: 'Referred to fraud unit', deny: 'Denied', pending: 'No decision',
}
const DECISION_BADGE: Record<string, 'green' | 'amber' | 'red' | 'slate'> = {
  approve: 'green', APPROVE_EXCEPTION: 'green', REQUEST_DOCUMENTS: 'amber', REFER_TO_FIU: 'red', deny: 'red', pending: 'slate',
}

export default function ClaimantsView({ client, selected, onSelect, onOpenClaim }: {
  client: Client; selected: string | null; onSelect: (id: string | null) => void; onOpenClaim: (id: string) => void
}) {
  if (selected) return <ClaimantProfileView id={selected} client={client} onBack={() => onSelect(null)} onOpenClaim={onOpenClaim} />
  return <ClaimantList client={client} onSelect={onSelect} />
}

function ClaimantList({ client, onSelect }: { client: Client; onSelect: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<ClaimantSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const t = window.setTimeout(() => client.claimants(q.trim() || undefined).then(setRows).catch(() => setError('Could not load users.')), 250)
    return () => window.clearTimeout(t)
  }, [q, client])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">User profiles</h1>
          <p className="text-sm text-slate-600">Every policyholder's claim history, behaviour and earlier outcomes.</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <Input aria-label="Search users" placeholder="Claimant id, name or policy" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {!rows ? <div className="grid place-items-center py-16"><Spinner className="size-7" /></div> : (
        <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
              <tr>{['User', 'Policy', 'Claims', 'Total claimed', 'Last claim', 'Earlier fraud', 'Signals', ''].map((h) => (
                <th key={h} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>))}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.claimant_id} onClick={() => onSelect(r.claimant_id)} className="cursor-pointer hover:bg-indigo-50/40">
                  <td className="px-4 py-3">
                    <button type="button" className="text-left font-medium text-slate-900 hover:underline" onClick={() => onSelect(r.claimant_id)}>{r.name}</button>
                    <div className="font-mono text-xs text-slate-500">{r.claimant_id}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{r.policy_number}<div className="text-xs text-slate-400">{r.plan}</div></td>
                  <td className="px-4 py-3 tabular-nums">{r.claims}</td>
                  <td className="px-4 py-3 tabular-nums">{inr(r.total_claimed)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(r.last_claim)}</td>
                  <td className="px-4 py-3">{r.flagged_claims ? <Badge tone="red">{r.flagged_claims} denied / referred</Badge> : <span className="text-slate-400">None</span>}</td>
                  <td className="px-4 py-3">{r.signals ? <Badge tone={SEVERITY_TONE[r.top_severity ?? 'low']}>{r.signals} on latest claim</Badge> : <span className="text-slate-400">None</span>}</td>
                  <td className="px-2 py-3 text-slate-400"><ChevronRight className="size-4" aria-hidden /></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500">No user matches “{q}”.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ClaimantProfileView({ id, client, onBack, onOpenClaim }: { id: string; client: Client; onBack: () => void; onOpenClaim: (id: string) => void }) {
  const [p, setP] = useState<ClaimantProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    client.claimant(id).then(setP).catch(() => setError('Could not load this user.'))
  }, [id, client])

  if (error) return <Alert>{error}</Alert>
  if (!p) return <div className="grid place-items-center py-20"><Spinner className="size-8" /></div>
  const m = p.metrics
  const used = p.policy ? Math.min(100, Math.round((m.total_claimed / p.policy.sum_insured) * 100)) : null

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" aria-hidden /> All users</Button>

      <div className="flex flex-col gap-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 md:flex-row md:items-center">
        <div className="grid size-16 shrink-0 place-items-center rounded-2xl bg-indigo-50"><UserRound className="size-8 text-indigo-600" aria-hidden /></div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">{p.claimant.name}</h1>
            <Badge>{p.claimant.claimant_id}</Badge>
            {m.flagged_claims > 0 && <Badge tone="red"><ShieldAlert className="size-3" aria-hidden /> earlier claim denied or referred</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-600">
            {p.claimant.relation === 'self' ? 'Policyholder' : p.claimant.relation} · born {fmtDate(p.claimant.dob)} · {p.claimant.policy_number}
            {p.policy && ` · ${p.policy.plan} · ${fmtDate(p.policy.valid_from)} – ${fmtDate(p.policy.valid_to)}`}
          </p>
          {p.policy && used != null && (
            <div className="mt-3 max-w-md">
              <div className="flex justify-between text-xs text-slate-500"><span>Claimed across history</span><span>{inr(m.total_claimed)} of {inr(p.policy.sum_insured)} sum insured</span></div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
                <div className={cn('h-full rounded-full', used >= 80 ? 'bg-rose-500' : used >= 50 ? 'bg-amber-500' : 'bg-indigo-500')} style={{ width: `${Math.max(2, used)}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        {[
          ['Claims', String(m.claims)], ['Total claimed', inr(m.total_claimed)], ['Average claim', inr(m.average_claim)],
          ['Largest claim', inr(m.largest_claim)], ['Last 90 days', String(m.claims_last_90_days)], ['Hospitals', String(m.hospitals)],
          ['Avg. days discharge → claim', m.average_submission_lag_days == null ? '—' : String(m.average_submission_lag_days)],
          ['Near policy end', String(m.claims_near_policy_end)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200">
            <dt className="text-[11px] text-slate-500">{k}</dt>
            <dd className="mt-0.5 text-base font-semibold tabular-nums text-slate-900">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
        <Panel title="Behaviour signals (latest claim against earlier ones)" icon={<ShieldAlert className="size-4 text-rose-600" aria-hidden />}>
          {p.signals.length === 0 ? <p className="text-sm text-slate-500">No unusual behaviour found.</p> : (
            <ul className="space-y-2.5">
              {p.signals.map((s) => (
                <li key={s.code} className="text-sm">
                  <div className="flex items-center gap-2"><Badge tone={SEVERITY_TONE[s.severity]}>{s.severity}</Badge><code className="text-xs font-semibold text-slate-900">{s.code}</code></div>
                  <p className="mt-0.5 text-slate-700">{s.detail}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 border-t border-slate-100 pt-3">
            <div className="mb-1.5 text-xs font-medium text-slate-500">Investigator outcomes</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(m.decisions).map(([k, n]) => <Badge key={k} tone={DECISION_BADGE[k] ?? 'slate'}>{DECISION_TEXT[k] ?? k}: {n}</Badge>)}
            </div>
          </div>
        </Panel>

        <Panel title={`Claim history (${p.claims.length})`} icon={<History className="size-4 text-indigo-600" aria-hidden />}>
          <ol className="relative space-y-3 border-l-2 border-slate-200 pl-5">
            {p.claims.map((c) => (
              <li key={c.claim_id} className="relative">
                <span className={cn('absolute top-1.5 -left-[27px] size-3 rounded-full ring-4 ring-white',
                  c.decision === 'deny' || c.decision === 'REFER_TO_FIU' ? 'bg-rose-500' : c.decision ? 'bg-emerald-500' : 'bg-slate-400')} aria-hidden />
                <div className="rounded-xl p-3 ring-1 ring-slate-200">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {c.in_console
                        ? <button type="button" onClick={() => onOpenClaim(c.claim_id)} className="font-mono text-xs font-semibold text-indigo-700 hover:underline">{c.claim_id}</button>
                        : <span className="font-mono text-xs font-semibold text-slate-900">{c.claim_id}</span>}
                      <Badge tone={DECISION_BADGE[c.decision ?? 'pending']}>{DECISION_TEXT[c.decision ?? 'pending']}</Badge>
                      {c.queue && <Badge tone={DECISION_TONE[c.queue]}>{DECISION_LABEL[c.queue]} · {c.risk_score}</Badge>}
                      {c.is_test && <Badge>history</Badge>}
                    </div>
                    <span className="font-semibold tabular-nums text-slate-900">{inr(c.amount)}</span>
                  </div>
                  <div className="mt-1.5 grid gap-x-4 gap-y-0.5 text-xs text-slate-600 sm:grid-cols-2">
                    <span>{c.hospital ?? c.hospital_id ?? '—'}{c.doctor_id ? ` · ${c.doctor_id}` : ''}</span>
                    <span>{c.diagnosis ?? '—'}</span>
                    <span>Stay {c.admission ? `${fmtDate(c.admission)} – ${fmtDate(c.discharge)}` : 'not recorded'}{c.stay_days != null ? ` (${c.stay_days} d)` : ''}</span>
                    <span className="flex items-center gap-1">
                      <CalendarClock className="size-3" aria-hidden /> Submitted {fmtDate(c.submitted)}
                      {c.submission_lag_days != null && ` · ${c.submission_lag_days} d after discharge`}
                      {c.days_to_term_end != null && c.days_to_term_end <= 30 && <Badge tone="amber" className="ml-1">{c.days_to_term_end} d before term end</Badge>}
                    </span>
                  </div>
                </div>
              </li>
            ))}
            {!p.claims.length && <li className="text-sm text-slate-500">No processed claims yet.</li>}
          </ol>
        </Panel>
      </div>
      <p className="text-xs text-slate-400">Profile rules {p.config_version}. Viewing this page is recorded in the audit log. Name and date of birth are never sent to the LLM.</p>
    </div>
  )
}
