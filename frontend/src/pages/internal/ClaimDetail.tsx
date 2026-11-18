import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Braces, ChartGantt, ChevronDown, CircleCheck, CircleAlert, ExternalLink, Scale, SearchCheck, Sparkles, UserRound } from 'lucide-react'
import type { AgentResult, Finding, InternalDetail, internalApi, JobEvent, Me, Overview } from '../../api'
import { Alert, Badge, Button, Spinner } from '../../components/ui'
import { CHECK_OUTCOME_LABEL, cn, DECISION_LABEL, fmtDate, inr, ms } from '../../lib/utils'
import { AGENT_ICON, agentTitle, DECISION_TONE, Panel, RichText, ScoreBar, ScoreRing, SEVERITY_TONE } from './common'
import { DocumentsSection, REVIEW_LABEL, REVIEW_TONE, ReviewPanel } from './ClaimReview'

type Props = { id: string; me: Me; overview: Overview; client: ReturnType<typeof internalApi>; onBack: () => void; onOpenClaimant?: (claimantId: string) => void }

export default function ClaimDetail({ id, me, overview, client, onBack, onOpenClaimant }: Props) {
  const [d, setD] = useState<InternalDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0) // bumped after a decision to reload the claim

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
  }, [id, client, version])

  if (error) return <Alert>{error}</Alert>
  if (!d) return <div className="grid place-items-center py-20"><Spinner className="size-8" /></div>

  const a = d.assessment
  const claim = d.claim as Record<string, unknown> & { invoice: { invoice_number: string; total: number; line_items: unknown[] } }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" aria-hidden /> All claims</Button>
        <div className="flex gap-2">
          {onOpenClaimant && typeof d.claim.claimant_id === 'string' && (
            <Button variant="secondary" size="sm" onClick={() => onOpenClaimant(d.claim.claimant_id as string)}>
              <UserRound className="size-3.5" aria-hidden /> User profile
            </Button>
          )}
          <a href={`/claims/${d.claim_id}`} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm"><ExternalLink className="size-3.5" aria-hidden /> Customer report</Button>
          </a>
        </div>
      </div>

      {/* Header */}
      <div className="flex flex-col gap-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-indigo-100 md:flex-row md:items-center">
        <ScoreRing score={a?.risk_score ?? null} size={112} />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-lg font-semibold text-slate-900">{d.claim_id}</h1>
            {a ? <Badge tone={DECISION_TONE[a.decision]}>{DECISION_LABEL[a.decision]}</Badge> : <Badge>{d.status}</Badge>}
            {d.review && <Badge tone={REVIEW_TONE[d.review.decision] ?? 'slate'}>{REVIEW_LABEL[d.review.decision] ?? d.review.decision}</Badge>}
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

      {a && <CaseSummary text={a.summary} llm={d.use_llm} />}

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <Timeline d={d} overview={overview} />
        {a && <Decision a={a} overview={overview} />}
      </div>

      {/* Agent responses */}
      {a && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Agent responses <span className="font-normal text-slate-500">(click an agent to expand)</span></h2>
          <div className="grid items-start gap-4 lg:grid-cols-2">
            {a.agent_results.map((r, i) => (
              <AgentCard key={r.agent} r={r} overview={overview} trace={a.orchestration.traces.find((t) => t.agent === r.agent)} delay={i * 0.05} />
            ))}
          </div>
        </div>
      )}

      {a && (
        <div>
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

      <DocumentsSection claimId={d.claim_id} documents={d.documents} client={client} />

      <Panel title="Raw data" icon={<Braces className="size-4 text-slate-500" aria-hidden />}>
        <Raw label="Claim input" value={d.claim} />
        <Raw label="Assessment (agent output)" value={d.assessment} />
        <Raw label={`Orchestration events (${d.events.length})`} value={d.events} />
      </Panel>

      <ReviewPanel d={d} me={me} client={client} onDecided={() => setVersion((v) => v + 1)} />
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
  const byAgent = new Map(a.agent_results.map((r) => [r.agent, r]))
  const raw = o.rule_score + o.llm_score
  return (
    <Panel title="How the score was decided" icon={<Scale className="size-4 text-indigo-600" aria-hidden />}>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="pb-2 text-left font-medium">Agent</th>
            <th className="pb-2 text-right font-medium">Rules</th>
            <th className="pb-2 text-right font-medium">LLM</th>
            <th className="pb-2 text-right font-medium">Agent score</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-indigo-50">
          {o.traces.map((t) => {
            const r = byAgent.get(t.agent)
            return (
              <tr key={t.agent}>
                <td className="py-1.5 text-slate-800">{agentTitle(overview, t.agent).replace(' Agent', '')}</td>
                <td className="py-1.5 text-right tabular-nums">{r?.rule_score ?? t.score}</td>
                <td className="py-1.5 text-right tabular-nums text-violet-700">{r?.llm_used ? `+${r.llm_points}` : '–'}</td>
                <td className="py-1.5 text-right font-medium tabular-nums">{r?.score ?? t.score}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">
        Agent scores are shown for comparison. The claim total counts each fact once even when several agents report it, so it is not the sum of the column.
      </p>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <Box k="Rule points" v={o.rule_score} />
        <Box k="LLM points" v={o.llm_score} hint={`max ${overview.scoring.max_llm_points_total}`} />
        <Box k="Final" v={o.final_score} hint={raw > 100 ? 'capped at 100' : undefined} strong />
      </div>
      <div className="relative mt-5 h-2.5 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-500">
        {[o.thresholds.manual_review_at, o.thresholds.investigate_at].map((v) => (
          <span key={v} className="absolute -top-0.5 h-3.5 w-px bg-indigo-950/60" style={{ left: `${v}%` }} />
        ))}
        <motion.span initial={{ left: 0 }} animate={{ left: `${Math.min(99, o.final_score)}%` }}
          className="absolute -top-1.5 size-5 -translate-x-1/2 rounded-full border-2 border-white bg-indigo-900 shadow" />
      </div>
      <div className="relative mt-2 h-3 text-[10px] text-slate-500">
        {[0, o.thresholds.manual_review_at, o.thresholds.investigate_at, 100].map((v) => (
          <span key={v} className="absolute -translate-x-1/2" style={{ left: `${v}%` }}>{v}</span>
        ))}
      </div>
      <p className="mt-4 rounded-lg bg-indigo-50 px-3 py-2 text-xs leading-relaxed text-indigo-950">{o.decision_reason}</p>
    </Panel>
  )
}

function Box({ k, v, hint, strong }: { k: string; v: number; hint?: string; strong?: boolean }) {
  return (
    <div className={cn('rounded-lg px-2 py-2 ring-1', strong ? 'bg-indigo-900 text-white ring-indigo-900' : 'bg-indigo-50/60 ring-indigo-100')}>
      <div className={cn('text-[10px] uppercase', strong ? 'text-indigo-200' : 'text-slate-500')}>{k}</div>
      <div className="font-display text-lg font-semibold tabular-nums">{Number.isInteger(v) ? v : v.toFixed(1)}</div>
      {hint && <div className={cn('text-[10px]', strong ? 'text-indigo-200' : 'text-slate-500')}>{hint}</div>}
    </div>
  )
}
// ---------------------------------------------------------------- agent card

const SEV_ORDER: Record<Finding['severity'], number> = { high: 0, medium: 1, low: 2 }

function AgentCard({ r, overview, trace, delay }: { r: AgentResult; overview: Overview; trace?: { weight: number; duration_ms: number }; delay: number }) {
  const [open, setOpen] = useState(false)
  const Icon = AGENT_ICON[r.agent]
  const findings = [...r.findings].sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity])
  const count = (s: Finding['severity']) => r.findings.filter((f) => f.severity === s).length
  const bodyId = `agent-${r.agent}`
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      className="rounded-xl bg-white shadow-sm ring-1 ring-indigo-100">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={bodyId}
        className="flex w-full items-center gap-3 rounded-xl p-4 text-left transition hover:bg-indigo-50/40 focus-visible:outline-2 focus-visible:outline-indigo-600">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-indigo-50"><Icon className="size-4.5 text-indigo-600" aria-hidden /></span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold text-slate-900">{agentTitle(overview, r.agent)}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            {(['high', 'medium', 'low'] as const).map((s) => count(s) > 0 && (
              <Badge key={s} tone={SEVERITY_TONE[s]}>{count(s)} {s}</Badge>
            ))}
            {r.findings.length === 0 && <Badge tone="green">No issues</Badge>}
          </span>
        </span>
        <ScoreRing score={r.score} size={52} label="score" />
        <ChevronDown className={cn('size-5 shrink-0 text-indigo-400 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div id={bodyId} className="border-t border-indigo-50 px-4 pt-3 pb-4">
          <div className="mb-1 flex justify-between text-[11px] text-slate-500">
            <span>{ms(trace?.duration_ms)}{r.llm_model ? ` · ${r.llm_model}` : ''}</span>
            <span>{r.findings.length} finding{r.findings.length === 1 ? '' : 's'}</span>
          </div>
          <ScoreBar score={r.score} />
          <FindingList items={findings} />
          {r.reasoning && (
            <div className="mt-4 rounded-lg bg-indigo-50/60 p-3 text-xs leading-relaxed text-indigo-950 ring-1 ring-indigo-100">
              <div className="mb-1 flex items-center gap-1 font-medium text-indigo-800">
                <Sparkles className="size-3.5" aria-hidden /> Agent output
              </div>
              {r.reasoning}
            </div>
          )}
        </div>
      )}
    </motion.section>
  )
}

function FindingList({ items }: { items: Finding[] }) {
  return (
    <div className="mt-4">
      <div className="mb-2 text-[11px] font-medium tracking-wide text-slate-500 uppercase">Findings</div>
      {items.length === 0 ? <p className="text-xs text-slate-400">Nothing suspicious found.</p> : (
        <ul className="space-y-2">
          {items.map((f, i) => (
            <li key={i} className="grid grid-cols-[4.5rem_1fr] items-start gap-3 text-xs leading-relaxed">
              <Badge tone={SEVERITY_TONE[f.severity]} className="justify-center">{f.severity}</Badge>
              <span className="min-w-0 text-slate-700">
                <code className="block font-semibold break-all text-slate-900">{f.code}</code>
                {f.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- combined AI summary

const OVERALL = '**Overall:**'
const WHY = '**Why this claim was flagged**'
const CHECK = '**What to investigate**'

/** Splits the three-part summary written by app/llm.py. Returns null for older free-text summaries. */
function parseSummary(text: string) {
  const i = text.indexOf(WHY), j = text.indexOf(CHECK)
  if (i < 0 || j < 0 || j < i) return null
  const bullets = (s: string) => s.split('\n').map((l) => l.replace(/^\s*[-*•]\s*/, '').trim()).filter(Boolean)
  return {
    overall: text.slice(0, i).replace(OVERALL, '').trim(),
    why: bullets(text.slice(i + WHY.length, j)),
    check: bullets(text.slice(j + CHECK.length)),
  }
}

/** **bold** segments inline (no innerHTML). */
function Inline({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
    seg.startsWith('**') && seg.endsWith('**') ? <strong key={j}>{seg.slice(2, -2)}</strong> : <span key={j}>{seg}</span>)}</>
}

function CaseSummary({ text, llm }: { text: string; llm: boolean }) {
  const s = parseSummary(text)
  return (
    <section className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-indigo-100">
      <div className="flex items-center justify-between gap-3 bg-indigo-600 px-5 py-3 text-white">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold"><Sparkles className="size-4" aria-hidden /> AI summary of all checks</h2>
        <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs">{llm ? 'Written by the LLM from every agent\'s findings' : 'Rules-only summary'}</span>
      </div>
      {!s ? <div className="p-5 text-sm leading-relaxed text-slate-700"><RichText text={text} /></div> : (
        <div className="space-y-4 p-5">
          {s.overall && <p className="text-sm leading-relaxed text-slate-800"><Inline text={s.overall} /></p>}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg bg-rose-50/60 p-4 ring-1 ring-rose-100">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-rose-900"><CircleAlert className="size-4" aria-hidden /> Why this claim was flagged</h3>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                {s.why.map((b, k) => <li key={k} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-rose-400" /><span><Inline text={b} /></span></li>)}
              </ul>
            </div>
            <div className="rounded-lg bg-indigo-50/70 p-4 ring-1 ring-indigo-100">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-indigo-900"><SearchCheck className="size-4" aria-hidden /> What to investigate</h3>
              <ol className="mt-2 space-y-1.5 text-sm text-slate-700">
                {s.check.map((b, k) => <li key={k} className="flex gap-2"><span className="grid size-5 shrink-0 place-items-center rounded-full bg-indigo-600 text-[11px] font-semibold text-white">{k + 1}</span><span><Inline text={b} /></span></li>)}
              </ol>
            </div>
          </div>
          <p className="text-xs text-slate-500">These are signals for you to check, not a decision.</p>
        </div>
      )}
    </section>
  )
}

function Raw({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="group mb-2 rounded-lg ring-1 ring-slate-200">
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
        <span className="mr-1 inline-block transition group-open:rotate-90">›</span> {label}
      </summary>
      <pre className="max-h-80 overflow-auto bg-indigo-950 p-3 text-[11px] leading-relaxed text-slate-200">{JSON.stringify(value, null, 2)}</pre>
    </details>
  )
}

