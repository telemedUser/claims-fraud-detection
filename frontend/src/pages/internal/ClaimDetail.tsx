import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Braces, ChartGantt, CircleCheck, CircleAlert, ExternalLink, FileText, MessageSquareText, Scale, Sparkles, UserRound, Wrench } from 'lucide-react'
import type { AgentResult, InternalDetail, internalApi, JobEvent, Overview } from '../../api'
import { Alert, Badge, Button, Spinner } from '../../components/ui'
import { CHECK_OUTCOME_LABEL, cn, DECISION_LABEL, DOC_LABEL, fileSize, fmtDate, inr, ms } from '../../lib/utils'
import { AGENT_ICON, agentTitle, DECISION_TONE, Panel, RichText, ScoreBar, ScoreRing, SEVERITY_TONE, SourceTag } from './common'

type Props = { id: string; overview: Overview; client: ReturnType<typeof internalApi>; onBack: () => void }

export default function ClaimDetail({ id, overview, client, onBack }: Props) {
  const [d, setD] = useState<InternalDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    let timer: number
    const load = async () => {
      try {
        const res = await client.claim(id)
        if (!alive) return
        setD(res)
        if (res.status === 'processing') timer = window.setTimeout(load, 800)
      } catch {
        if (alive) setError('Could not load this claim.')
      }
    }
    load()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [id, client])

  if (error) return <Alert>{error}</Alert>
  if (!d) return <div className="grid place-items-center py-20"><Spinner className="size-8" /></div>

  const a = d.assessment
  const claim = d.claim as Record<string, unknown> & { invoice: { invoice_number: string; total: number; line_items: unknown[] } }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" aria-hidden /> All claims</Button>
        <a href={`/claims/${d.claim_id}`} target="_blank" rel="noreferrer">
          <Button variant="secondary" size="sm"><ExternalLink className="size-3.5" aria-hidden /> Customer report</Button>
        </a>
      </div>

      {/* Header */}
      <div className="flex flex-col gap-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 md:flex-row md:items-center">
        <ScoreRing score={a?.risk_score ?? null} size={112} />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-lg font-semibold text-slate-900">{d.claim_id}</h1>
            {a ? <Badge tone={DECISION_TONE[a.decision]}>{DECISION_LABEL[a.decision]}</Badge> : <Badge>{d.status}</Badge>}
            {d.use_llm ? <Badge tone="violet"><Sparkles className="size-3" aria-hidden /> LLM review</Badge> : <Badge>Rules only</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-600">
            {d.claimant} · {d.policy_number ?? 'no policy'} · {d.hospital} · {d.diagnosis}
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <Stat k="Claimed" v={inr(d.claimed_amount)} />
            <Stat k="Bill total" v={inr(claim.invoice.total)} />
            <Stat k="Stay" v={`${fmtDate(String(claim.admission_date))} → ${fmtDate(String(claim.discharge_date))}`} />
            <Stat k="Processed in" v={ms(a?.orchestration.total_duration_ms)} />
          </dl>
        </div>
      </div>

      {d.status === 'processing' && <Alert tone="indigo">Agents are still running. This view updates live.</Alert>}
      {d.error && <Alert>Processing error: {d.error}</Alert>}

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <Timeline d={d} overview={overview} />
        {a && <Decision a={a} overview={overview} />}
      </div>

      {/* Agent responses */}
      {a && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Agent responses</h2>
          <div className="grid gap-6 lg:grid-cols-2">
            {a.agent_results.map((r, i) => (
              <AgentCard key={r.agent} r={r} overview={overview} trace={a.orchestration.traces.find((t) => t.agent === r.agent)} delay={i * 0.05} />
            ))}
          </div>
        </div>
      )}

      {a && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title="Investigator summary" icon={<MessageSquareText className="size-4 text-violet-600" aria-hidden />}
            actions={d.use_llm ? <Badge tone="violet">LLM-written</Badge> : <Badge>Template</Badge>}>
            <div className="text-sm leading-relaxed text-slate-700"><RichText text={a.summary} /></div>
          </Panel>
          <Panel title="What the customer saw" icon={<UserRound className="size-4 text-sky-600" aria-hidden />}>
            {d.customer_view.report ? (
              <>
                <div className="font-medium text-slate-900">{d.customer_view.report.outcome.title}</div>
                <p className="mt-0.5 text-sm text-slate-600">{d.customer_view.report.outcome.message}</p>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {d.customer_view.report.checks.map((c) => (
                    <li key={c.label} className="flex items-center justify-between">
                      <span className="text-slate-700">{c.label}</span>
                      {c.outcome === 'no_issues'
                        ? <span className="flex items-center gap-1 text-emerald-700"><CircleCheck className="size-4" aria-hidden /> {CHECK_OUTCOME_LABEL.no_issues}</span>
                        : <span className="flex items-center gap-1 text-amber-700"><CircleAlert className="size-4" aria-hidden /> {CHECK_OUTCOME_LABEL[c.outcome]}</span>}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-slate-500">Scores, agent names and findings are not shown to the customer.</p>
              </>
            ) : <p className="text-sm text-slate-500">Not available yet.</p>}
          </Panel>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={`Documents (${d.documents.length})`} icon={<FileText className="size-4 text-indigo-600" aria-hidden />}>
          <ul className="space-y-2">
            {d.documents.map((doc, i) => (
              <li key={i} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span className="truncate text-slate-800">{doc.filename}</span>
                <span className="shrink-0 text-xs text-slate-500">{DOC_LABEL[doc.doc_type]} · {fileSize(doc.size)}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Raw data" icon={<Braces className="size-4 text-slate-500" aria-hidden />}>
          <Raw label="Claim input" value={d.claim} />
          <Raw label="Assessment (agent output)" value={d.assessment} />
          <Raw label={`Orchestration events (${d.events.length})`} value={d.events} />
        </Panel>
      </div>
    </div>
  )
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{k}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{v}</dd>
    </div>
  )
}

// ---------------------------------------------------------------- timeline

const STAGE_LABEL: Record<string, string> = { intake: 'Intake', scoring: 'Scoring', summary: 'Summary' }

function phases(events: JobEvent[], stage: string) {
  const at = (s: string) => events.find((e) => e.stage === stage && e.status === s)?.t_ms
  return { start: at('rules') ?? at('running'), rulesDone: at('rules_done'), llm: at('llm_review'), end: at('done') }
}

function Timeline({ d, overview }: { d: InternalDetail; overview: Overview }) {
  const order = Object.keys(d.stages)
  const total = Math.max(1, ...d.events.map((e) => e.t_ms))
  const pct = (v: number) => `${(v / total) * 100}%`

  return (
    <Panel title="Execution timeline" icon={<ChartGantt className="size-4 text-indigo-600" aria-hidden />}
      actions={<div className="flex items-center gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-indigo-500" /> rules</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-violet-500" /> LLM + tools</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-slate-400" /> other</span>
      </div>}>
      <div className="space-y-2.5">
        {order.map((stage) => {
          const p = phases(d.events, stage)
          const isAgent = stage in AGENT_ICON
          const label = isAgent ? agentTitle(overview, stage).replace(' Agent', '') : STAGE_LABEL[stage] ?? stage
          const start = p.start ?? 0
          const end = p.end ?? (d.stages[stage].status === 'running' ? total : start)
          return (
            <div key={stage} className="grid grid-cols-[9rem_1fr_4.5rem] items-center gap-3 text-xs">
              <span className={cn('truncate', isAgent ? 'font-medium text-slate-800' : 'text-slate-500')}>{label}</span>
              <div className="relative h-5 rounded-md bg-slate-100">
                {p.start != null && isAgent && (
                  <>
                    <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} style={{ left: pct(start), width: pct(Math.max((p.rulesDone ?? end) - start, total * 0.006)), originX: 0 }}
                      className="absolute inset-y-0 rounded-md bg-indigo-500" />
                    {p.llm != null && (
                      <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.15 }}
                        style={{ left: pct(p.llm), width: pct(Math.max(end - p.llm, total * 0.006)), originX: 0 }}
                        className="absolute inset-y-0 rounded-md bg-violet-500" />
                    )}
                  </>
                )}
                {p.start != null && !isAgent && (
                  <div style={{ left: pct(start), width: pct(Math.max(end - start, total * 0.006)) }} className="absolute inset-y-0 rounded-md bg-slate-400" />
                )}
              </div>
              <span className="text-right tabular-nums text-slate-500">{p.start != null ? ms(end - start) : '—'}</span>
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex justify-between text-[11px] text-slate-400">
        <span>0</span>
        <span>{ms(total)}</span>
      </div>
      {d.assessment && (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Agents overlapped: <b>{d.assessment.orchestration.agents_run_in_parallel ? 'yes' : 'no'}</b>. Wall-clock for agents{' '}
          <b>{ms(d.assessment.orchestration.total_duration_ms)}</b> vs <b>{ms(d.assessment.orchestration.sum_of_agent_durations_ms)}</b> if run one after another.
        </p>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------- decision

function Decision({ a, overview }: { a: NonNullable<InternalDetail['assessment']>; overview: Overview }) {
  const o = a.orchestration
  return (
    <Panel title="How the score was decided" icon={<Scale className="size-4 text-amber-600" aria-hidden />}>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr><th className="pb-2 text-left font-medium">Agent</th><th className="pb-2 text-right font-medium">Score</th><th className="pb-2 text-right font-medium">Weight</th><th className="pb-2 text-right font-medium">Contribution</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {o.traces.map((t) => (
            <tr key={t.agent} className={cn(t.agent === o.peak_agent && 'bg-amber-50/60')}>
              <td className="py-1.5 text-slate-800">{agentTitle(overview, t.agent).replace(' Agent', '')}{t.agent === o.peak_agent && <span className="ml-1 text-[10px] text-amber-700">peak</span>}</td>
              <td className="py-1.5 text-right tabular-nums">{t.score}</td>
              <td className="py-1.5 text-right tabular-nums text-slate-500">× {t.weight}</td>
              <td className="py-1.5 text-right font-medium tabular-nums">{t.weighted_contribution}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <Box k="Weighted avg" v={o.weighted_score} active={o.weighted_score >= o.peak_floor} />
        <Box k="0.8 × peak" v={o.peak_floor} active={o.peak_floor > o.weighted_score} />
        <Box k="Final" v={o.final_score} strong />
      </div>
      <div className="relative mt-5 h-2.5 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-500">
        {[o.thresholds.manual_review_at, o.thresholds.investigate_at].map((v) => (
          <span key={v} className="absolute -top-0.5 h-3.5 w-px bg-slate-900/60" style={{ left: `${v}%` }} />
        ))}
        <motion.span initial={{ left: 0 }} animate={{ left: `${Math.min(99, o.final_score)}%` }}
          className="absolute -top-1.5 size-5 -translate-x-1/2 rounded-full border-2 border-white bg-slate-900 shadow" />
      </div>
      <div className="relative mt-2 h-3 text-[10px] text-slate-500">
        {[0, o.thresholds.manual_review_at, o.thresholds.investigate_at, 100].map((v) => (
          <span key={v} className="absolute -translate-x-1/2" style={{ left: `${v}%` }}>{v}</span>
        ))}
      </div>
      <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900">{o.decision_reason}</p>
    </Panel>
  )
}

function Box({ k, v, active, strong }: { k: string; v: number; active?: boolean; strong?: boolean }) {
  return (
    <div className={cn('rounded-lg px-2 py-2 ring-1', strong ? 'bg-slate-900 text-white ring-slate-900' : active ? 'bg-amber-50 ring-amber-300' : 'bg-slate-50 ring-slate-200')}>
      <div className={cn('text-[10px] uppercase', strong ? 'text-slate-300' : 'text-slate-500')}>{k}</div>
      <div className="text-lg font-semibold tabular-nums">{v}</div>
    </div>
  )
}

// ---------------------------------------------------------------- agent card

function AgentCard({ r, overview, trace, delay }: { r: AgentResult; overview: Overview; trace?: { weight: number; duration_ms: number }; delay: number }) {
  const Icon = AGENT_ICON[r.agent]
  const rule = r.findings.filter((f) => f.source === 'rule')
  const llm = r.findings.filter((f) => f.source === 'llm')
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      className="flex flex-col rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-50"><Icon className="size-4.5 text-indigo-600" aria-hidden /></span>
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900">{agentTitle(overview, r.agent)}</h3>
          <p className="text-xs text-slate-500">weight {trace?.weight} · {ms(trace?.duration_ms)}{r.llm_model ? ` · ${r.llm_model}` : ''}</p>
        </div>
        <ScoreRing score={r.score} size={56} label="score" />
      </div>
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-[11px] text-slate-500">
          <span>rules {Math.round(r.rule_score ?? r.score)} + LLM {Math.round(r.llm_points)}</span>
          <span>{r.findings.length} findings</span>
        </div>
        <ScoreBar score={r.score} />
      </div>

      <FindingList title="Rule findings" items={rule} empty="No rule issues." />
      {r.llm_used && <FindingList title="LLM findings" items={llm} empty="LLM found nothing new." />}

      {r.reasoning && (
        <div className={cn('mt-4 rounded-xl p-3 text-xs leading-relaxed ring-1', r.llm_used ? 'bg-violet-50/70 text-violet-950 ring-violet-100' : 'bg-slate-50 text-slate-600 ring-slate-200')}>
          <div className={cn('mb-1 flex items-center gap-1 font-medium', r.llm_used ? 'text-violet-800' : 'text-slate-700')}>
            <Sparkles className="size-3.5" aria-hidden /> {r.llm_used ? 'LLM reasoning' : 'Note'}
          </div>
          {r.reasoning}
        </div>
      )}
      {r.tool_calls.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex items-center gap-1 text-[11px] font-medium text-slate-500"><Wrench className="size-3" aria-hidden /> Tools called</div>
          <div className="flex flex-wrap gap-1.5">
            {r.tool_calls.map((t, i) => <code key={i} className="rounded-md bg-slate-900 px-1.5 py-0.5 text-[11px] text-emerald-300">{t}</code>)}
          </div>
        </div>
      )}
    </motion.section>
  )
}

function FindingList({ title, items, empty }: { title: string; items: AgentResult['findings']; empty: string }) {
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-[11px] font-medium tracking-wide text-slate-500 uppercase">{title}</div>
      {items.length === 0 ? <p className="text-xs text-slate-400">{empty}</p> : (
        <ul className="space-y-1.5">
          {items.map((f, i) => (
            <li key={i} className="flex gap-2 text-xs">
              <span className="flex shrink-0 gap-1 pt-px"><Badge tone={SEVERITY_TONE[f.severity]}>{f.severity}</Badge><SourceTag source={f.source} /></span>
              <span className="text-slate-700"><code className="font-semibold text-slate-900">{f.code}</code> {f.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Raw({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="group mb-2 rounded-lg ring-1 ring-slate-200">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
        <span className="mr-1 inline-block transition group-open:rotate-90">›</span> {label}
      </summary>
      <pre className="max-h-80 overflow-auto bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-200">{JSON.stringify(value, null, 2)}</pre>
    </details>
  )
}

