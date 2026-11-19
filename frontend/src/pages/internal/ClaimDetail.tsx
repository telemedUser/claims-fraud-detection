import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, ChartGantt, ChevronDown, CircleAlert, ExternalLink, ListChecks, Scale, SearchCheck, Sparkles, UserRound } from 'lucide-react'
import type { AgentResult, Finding, InternalDetail, internalApi, JobEvent, Me, Overview } from '../../api'
import { Alert, Badge, Button, Spinner } from '../../components/ui'
import { cn, DECISION_LABEL, fmtDate, inr, ms } from '../../lib/utils'
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

      <DocumentsSection claimId={d.claim_id} documents={d.documents} client={client} />

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

const STAGE_LABEL: Record<string, string> = { intake: 'Intake', scoring: 'Scoring', summary: 'AI summary' }
const STAGE_HINT: Record<string, string> = { intake: 'Claim and documents received', scoring: 'Findings combined into the score and queue', summary: 'LLM writes the combined summary' }

function phases(events: JobEvent[], stage: string) {
  const at = (s: string) => events.find((e) => e.stage === stage && e.status === s)?.t_ms
  return { start: at('rules') ?? at('running'), rulesDone: at('rules_done'), llm: at('llm_review'), end: at('done') }
}

function Timeline({ d, overview }: { d: InternalDetail; overview: Overview }) {
  const order = Object.keys(d.stages)
  const total = Math.max(1, ...d.events.map((e) => e.t_ms))
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / total) * 100))}%`
  const minW = total * 0.008 // keep millisecond segments visible on a seconds-long axis

  const rows = order.map((stage) => {
    const p = phases(d.events, stage)
    const isAgent = stage in AGENT_ICON
    const start = p.start ?? 0
    const end = p.end ?? (d.stages[stage].status === 'running' ? total : start)
    const ruleEnd = isAgent ? p.rulesDone ?? (p.llm ?? end) : end
    return { stage, isAgent, p, start, end, ruleMs: ruleEnd - start, llmMs: isAgent && p.llm != null ? end - p.llm : 0 }
  })
  const agents = rows.filter((r) => r.isAgent && r.p.start != null)
  const reviewed = agents.filter((r) => r.p.llm != null)
  const llmWall = reviewed.length ? Math.max(...reviewed.map((r) => r.end)) - Math.min(...reviewed.map((r) => r.p.llm!)) : 0
  const llmSum = reviewed.reduce((s, r) => s + r.llmMs, 0)
  const slowest = reviewed.length > 1 ? reviewed.reduce((a, b) => (b.llmMs > a.llmMs ? b : a)).stage : null
  const o = d.assessment?.orchestration

  return (
    <Panel title="Execution timeline" icon={<ChartGantt className="size-4 text-indigo-600" aria-hidden />}
      actions={<div className="flex items-center gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-indigo-500" /> rules</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-violet-500" /> LLM + tools</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-slate-400" /> other</span>
      </div>}>
      {/* headline numbers */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <TStat k="Total" v={ms(total)} />
        <TStat k="Rule checks" v={o ? ms(o.total_duration_ms) : '—'} hint="all agents, in parallel" tone="rules" />
        <TStat k="LLM reviews" v={reviewed.length ? ms(llmWall) : 'off'} hint={reviewed.length ? `${ms(llmSum)} if one by one` : 'rules only'} tone="llm" />
        <TStat k="AI summary" v={(() => { const s = rows.find((r) => r.stage === 'summary'); return s?.p.start != null ? ms(s.end - s.start) : '—' })()} />
      </div>

      {/* axis */}
      <div className="grid grid-cols-[8.5rem_1fr_6.5rem] gap-3 text-[10px] text-slate-400">
        <span />
        <div className="relative h-4">
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <span key={t} className={cn('absolute', t === 0 ? 'left-0' : t === 1 ? 'right-0' : '-translate-x-1/2')} style={t > 0 && t < 1 ? { left: `${t * 100}%` } : undefined}>
              {ms(total * t)}
            </span>
          ))}
        </div>
        <span />
      </div>

      <div className="space-y-1.5">
        {rows.map((r, i) => {
          const label = r.isAgent ? agentTitle(overview, r.stage).replace(' Agent', '') : STAGE_LABEL[r.stage] ?? r.stage
          const Icon = r.isAgent ? AGENT_ICON[r.stage] : null
          const firstAfterAgents = !r.isAgent && i > 0 && rows[i - 1].isAgent
          return (
            <div key={r.stage} className={cn(firstAfterAgents && 'mt-3 border-t border-dashed border-indigo-100 pt-3')}>
              <div className="grid grid-cols-[8.5rem_1fr_6.5rem] items-center gap-3 text-xs"
                title={r.isAgent ? `${label}: rules ${ms(r.ruleMs)}${r.p.llm != null ? `, LLM review ${ms(r.llmMs)}` : ''}` : STAGE_HINT[r.stage]}>
                <span className={cn('flex min-w-0 items-center gap-1.5', r.isAgent ? 'font-medium text-slate-800' : 'text-slate-500')}>
                  {Icon ? <Icon className="size-3.5 shrink-0 text-indigo-500" aria-hidden /> : <span className="size-3.5 shrink-0" />}
                  <span className="truncate">{label}</span>
                </span>
                <div className="relative h-6 overflow-hidden rounded-md bg-indigo-50/60">
                  {[0.25, 0.5, 0.75].map((t) => <span key={t} className="absolute inset-y-0 w-px bg-white" style={{ left: `${t * 100}%` }} />)}
                  {r.p.start != null && r.isAgent && (
                    <>
                      <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} style={{ left: pct(r.start), width: pct(Math.max(r.ruleMs, minW)), originX: 0 }}
                        className="absolute inset-y-1 rounded-sm bg-indigo-500" />
                      {r.p.llm != null && (
                        <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.1 + i * 0.05, duration: 0.5 }}
                          style={{ left: pct(r.p.llm), width: pct(Math.max(r.llmMs, minW)), originX: 0 }}
                          className={cn('absolute inset-y-1 rounded-sm bg-gradient-to-r from-violet-500 to-violet-400', slowest === r.stage && 'ring-2 ring-violet-300')} />
                      )}
                    </>
                  )}
                  {r.p.start != null && !r.isAgent && (
                    <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.3 }}
                      style={{ left: pct(r.start), width: pct(Math.max(r.end - r.start, minW)), originX: 0 }}
                      className={cn('absolute inset-y-1 rounded-sm', r.stage === 'summary' && d.use_llm ? 'bg-violet-300' : 'bg-slate-400')} />
                  )}
                </div>
                <span className="text-right leading-tight tabular-nums">
                  {r.p.start == null ? <span className="text-slate-400">—</span> : r.isAgent && r.p.llm != null ? (
                    <>
                      <span className="block font-medium text-slate-800">{ms(r.ruleMs + r.llmMs)}{slowest === r.stage && <span className="ml-1 text-[10px] font-normal text-violet-600">slowest</span>}</span>
                      <span className="block text-[10px] text-slate-400"><span className="text-indigo-600">{ms(r.ruleMs)}</span> + <span className="text-violet-600">{ms(r.llmMs)}</span></span>
                    </>
                  ) : <span className="font-medium text-slate-700">{ms(r.end - r.start)}</span>}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {o && (
        <p className="mt-4 rounded-lg bg-indigo-50/70 px-3 py-2 text-xs leading-relaxed text-indigo-950 ring-1 ring-indigo-100">
          All {agents.length} agents ran <b>{o.agents_run_in_parallel ? 'in parallel' : 'one after another'}</b>: rule checks took <b>{ms(o.total_duration_ms)}</b> instead of{' '}
          <b>{ms(o.sum_of_agent_durations_ms)}</b>{reviewed.length > 0 && <>, and the LLM reviews <b>{ms(llmWall)}</b> instead of <b>{ms(llmSum)}</b></>}.
          {d.use_llm && ' Most of the time is spent waiting for the LLM.'}
        </p>
      )}
    </Panel>
  )
}

function TStat({ k, v, hint, tone }: { k: string; v: string; hint?: string; tone?: 'rules' | 'llm' }) {
  return (
    <div className="rounded-lg bg-white px-3 py-2 ring-1 ring-indigo-100">
      <div className="flex items-center gap-1.5 text-[10px] font-medium tracking-wide text-slate-500 uppercase">
        {tone && <span className={cn('size-2 rounded-sm', tone === 'rules' ? 'bg-indigo-500' : 'bg-violet-500')} />}{k}
      </div>
      <div className="text-base font-semibold text-indigo-950 tabular-nums">{v}</div>
      {hint && <div className="text-[10px] text-slate-500">{hint}</div>}
    </div>
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
            <th className="pb-2 pl-2 text-left font-medium">Weight</th>
            <th className="pb-2 text-right font-medium">Rules</th>
            <th className="pb-2 text-right font-medium">LLM</th>
            <th className="pb-2 text-right font-medium">Agent score</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-indigo-50">
          {(() => {
            const maxW = Math.max(1, ...o.traces.map((t) => t.weightage_pct ?? 0))
            const n = o.traces.length
            return [...o.traces].sort((x, y) => (y.weightage_pct ?? 0) - (x.weightage_pct ?? 0)).map((t) => {
              const r = byAgent.get(t.agent)
              const w = t.weightage_pct
              const factor = w == null ? null : (w / 100) * n
              return (
                <tr key={t.agent}>
                  <td className="py-1.5 text-slate-800">{agentTitle(overview, t.agent).replace(' Agent', '')}</td>
                  <td className="py-1.5 pl-2" title={factor == null ? undefined : `Rule points are multiplied by ${factor.toFixed(2)} (${t.weighted_contribution} weighted points)`}>
                    {w == null ? <span className="text-slate-400">–</span> : (
                      <div className="flex items-center gap-1.5">
                        <div className="h-1.5 w-10 overflow-hidden rounded-full bg-indigo-50">
                          <div className="h-full rounded-full bg-indigo-600" style={{ width: `${(w / maxW) * 100}%` }} />
                        </div>
                        <span className="font-medium tabular-nums text-indigo-900">{Math.round(w)}%</span>
                      </div>
                    )}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{r?.rule_score ?? t.score}</td>
                  <td className="py-1.5 text-right tabular-nums text-violet-700">{r?.llm_used ? `+${r.llm_points}` : '–'}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-600">{r?.score ?? t.score}</td>
                </tr>
              )
            })
          })()}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">
        Each agent has a fixed weight by its priority in fraud detection (weights sum to 100%). Its rule points are multiplied by
        weight × {o.traces.length} (1.0 when all agents weigh the same; hover a weight to see the result), and those points plus the
        capped LLM points give the final score. A fact reported by several agents is counted once.
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
            {r.findings.length > 0 && (
              <span className="text-[11px] text-slate-500">
                {r.findings.filter((f) => f.source !== 'llm').length} rule · <span className="text-violet-700">{r.findings.filter((f) => f.source === 'llm').length} LLM</span>
              </span>
            )}
          </span>
        </span>
        <ScoreRing score={r.score} size={52} label="score" />
        <ChevronDown className={cn('size-5 shrink-0 text-indigo-400 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div id={bodyId} className="border-t border-indigo-50 px-4 pt-3 pb-4">
          <div className="mb-1 flex justify-between text-[11px] text-slate-500">
            <span>{ms(trace?.duration_ms)}{r.llm_model ? ` · ${r.llm_model}` : ''}</span>
            <span>
              rules <b className="text-indigo-800">{Math.round(r.rule_score ?? r.score)}</b>
              {' + '}LLM <b className="text-violet-700">{r.llm_used ? r.llm_points : 0}</b>
              {' = '}<b className="text-slate-800">{Math.round(r.score)}</b>
              {(r.rule_score ?? 0) + r.llm_points > 100 ? ' (max 100)' : ''}
            </span>
          </div>
          <ScoreBar score={r.score} />
          <FindingList kind="rule" items={findings.filter((f) => f.source !== 'llm')} />
          <FindingList kind="llm" items={findings.filter((f) => f.source === 'llm')}
            empty={r.llm_used ? 'The LLM found nothing beyond the rules.' : 'LLM review did not run for this agent.'} />
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

const FINDING_KIND = {
  rule: { title: 'Rule findings', note: 'deterministic checks', icon: ListChecks, box: 'border-indigo-500 bg-indigo-50/40', head: 'text-indigo-800' },
  llm: { title: 'LLM findings', note: 'AI observations, max medium', icon: Sparkles, box: 'border-violet-500 bg-violet-50/50', head: 'text-violet-800' },
} as const

function FindingList({ kind, items, empty = 'Nothing suspicious found.' }: { kind: keyof typeof FINDING_KIND; items: Finding[]; empty?: string }) {
  const k = FINDING_KIND[kind]
  return (
    <div className={cn('mt-4 rounded-r-lg border-l-4 py-2.5 pr-3 pl-3', k.box)}>
      <div className={cn('mb-2 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase', k.head)}>
        <k.icon className="size-3.5" aria-hidden /> {k.title} ({items.length})
        <span className="font-normal tracking-normal text-slate-500 normal-case">· {k.note}</span>
      </div>
      {items.length === 0 ? <p className="text-xs text-slate-500">{empty}</p> : (
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


