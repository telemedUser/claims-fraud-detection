import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { ArrowDown, ArrowRight, BrainCircuit, ClipboardList, FileCheck2, Gauge, ListChecks, Scale, ShieldCheck, Sparkles, UserRoundCheck, Wrench } from 'lucide-react'
import type { InternalDetail, InternalSummary, internalApi, Overview } from '../../api'
import { Badge } from '../../components/ui'
import { cn, DECISION_LABEL, scoreTone } from '../../lib/utils'
import { AGENT_ICON, DECISION_TONE, Panel, ScoreBar } from './common'

type Props = { overview: Overview; claims: InternalSummary[]; client: ReturnType<typeof internalApi>; onOpenClaim: (id: string) => void }

export default function WorkflowView({ overview, claims, client, onOpenClaim }: Props) {
  const done = claims.filter((c) => c.status === 'completed')
  const [overlayId, setOverlayId] = useState<string>('')
  const [overlay, setOverlay] = useState<InternalDetail | null>(null)

  useEffect(() => {
    if (!overlayId && done[0]) setOverlayId(done[0].claim_id)
  }, [done, overlayId])
  useEffect(() => {
    if (!overlayId) return setOverlay(null)
    client.claim(overlayId).then(setOverlay).catch(() => setOverlay(null))
  }, [overlayId, client])

  const a = overlay?.assessment
  const resultFor = (name: string) => a?.agent_results.find((r) => r.agent === name)
  const t = overview.scoring.thresholds

  return (
    <div className="space-y-6">
      <Panel
        title="End-to-end claim workflow"
        icon={<ListChecks className="size-4 text-indigo-600" aria-hidden />}
        actions={
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="overlay" className="text-slate-500">Overlay results from</label>
            <select id="overlay" value={overlayId} onChange={(e) => setOverlayId(e.target.value)}
              className="h-8 rounded-lg border-0 bg-slate-50 px-2 text-xs ring-1 ring-slate-200 focus:ring-2 focus:ring-indigo-600 focus:outline-none">
              <option value="">No claim</option>
              {done.map((c) => (
                <option key={c.claim_id} value={c.claim_id}>{c.claim_id} · {c.claimant} · {c.risk_score}</option>
              ))}
            </select>
            {overlay && (
              <button type="button" className="font-medium text-indigo-600 hover:underline" onClick={() => onOpenClaim(overlay.claim_id)}>Open</button>
            )}
          </div>
        }
      >
        <div className="grid items-stretch gap-3 xl:grid-cols-[1fr_auto_1fr_auto_2.4fr_auto_1.2fr_auto_1fr]">
          <Node step="1" title="Customer journey" icon={<UserRoundCheck className="size-4" />} tone="sky">
            <Li>Policy + DOB verified</Li>
            <Li>Network hospital and doctor</Li>
            <Li>Covered condition, dates</Li>
            <Li>Itemised bill, documents</Li>
          </Node>
          <Arrow />
          <Node step="2" title="Intake & policy gate" icon={<ShieldCheck className="size-4" />} tone="sky">
            <Li>Hospital in network</Li>
            <Li>Condition covered</Li>
            <Li>Within policy period, sum insured</Li>
            <Li>Files typed, hashed (SHA-256)</Li>
            <p className="mt-2 text-[11px] text-slate-500">Policy failures are rejected here, not scored.</p>
          </Node>
          <Arrow />
          <div className="rounded-2xl bg-gradient-to-b from-indigo-50 to-white p-3 ring-1 ring-indigo-200">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-indigo-900">
                <span className="grid size-5 place-items-center rounded-full bg-indigo-600 text-[10px] text-white">3</span>
                Orchestrator · agents run in parallel
              </span>
              {a && <Badge tone="indigo">{a.orchestration.agents_run_in_parallel ? 'overlapped' : 'sequential'} · {Math.round(a.orchestration.total_duration_ms)} ms</Badge>}
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
              {overview.agents.map((ag, i) => {
                const Icon = AGENT_ICON[ag.name]
                const r = resultFor(ag.name)
                return (
                  <motion.div key={ag.name} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                    className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-900">
                        <Icon className="size-3.5 text-indigo-600" aria-hidden /> {ag.title}
                      </span>
                      <span className="text-[10px] text-slate-500">w {ag.weight}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-1 text-[11px]">
                      <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 font-medium text-indigo-700">Rules</span>
                      <ArrowRight className="size-3 text-slate-400" aria-hidden />
                      <span className={cn('flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium',
                        overview.llm.enabled ? 'bg-violet-50 text-violet-700' : 'bg-slate-100 text-slate-400 line-through')}>
                        <Sparkles className="size-3" aria-hidden /> LLM + tools
                      </span>
                      <ArrowRight className="size-3 text-slate-400" aria-hidden />
                      <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700">Score</span>
                    </div>
                    {r && (
                      <div className="mt-2.5">
                        <div className="flex justify-between text-[11px] text-slate-600">
                          <span>rules {Math.round(r.rule_score ?? r.score)} + LLM {Math.round(r.llm_points)}</span>
                          <span className={cn('font-semibold', { green: 'text-emerald-600', amber: 'text-amber-600', red: 'text-rose-600', slate: '' }[scoreTone(r.score)])}>{Math.round(r.score)}</span>
                        </div>
                        <ScoreBar score={r.score} className="mt-1" />
                        <div className="mt-1 text-[10px] text-slate-500">{r.findings.length} findings · {r.tool_calls.length} tool calls</div>
                      </div>
                    )}
                  </motion.div>
                )
              })}
            </div>
          </div>
          <Arrow />
          <Node step="4" title="Scoring & decision" icon={<Scale className="size-4" />} tone="amber">
            <p className="text-[11px] leading-relaxed text-slate-600">sum of severity points x status multiplier, capped at 100</p>
            <div className="mt-2 space-y-1 text-[11px]">
              <div className="flex justify-between"><Badge tone="green">Low risk</Badge><span>&lt; {t.manual_review_at}</span></div>
              <div className="flex justify-between"><Badge tone="amber">Manual review</Badge><span>{t.manual_review_at}–{t.investigate_at - 1}</span></div>
              <div className="flex justify-between"><Badge tone="red">Investigate</Badge><span>≥ {t.investigate_at}</span></div>
            </div>
            {a && (
              <div className="mt-3 rounded-lg bg-slate-50 p-2 text-center">
                <div className="text-xl font-semibold tabular-nums">{a.risk_score}</div>
                <Badge tone={DECISION_TONE[a.decision]}>{DECISION_LABEL[a.decision]}</Badge>
              </div>
            )}
          </Node>
          <Arrow />
          <Node step="5" title="Outputs" icon={<FileCheck2 className="size-4" />} tone="green">
            <Li><span className="font-medium">Investigator summary</span> (LLM)</Li>
            <Li><span className="font-medium">Customer report</span>: outcome and neutral check status only, no scores</Li>
            <Li>History updated for future claims</Li>
          </Node>
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="How an agent works" icon={<BrainCircuit className="size-4 text-violet-600" aria-hidden />}>
          <ol className="space-y-3 text-sm text-slate-700">
            <Step n={1} title="Rule engine">Deterministic checks against registries, history and file metadata. Each finding adds points: low {overview.scoring.severity_points.low}, medium {overview.scoring.severity_points.medium}, high {overview.scoring.severity_points.high} (cap 100).</Step>
            <Step n={2} title="LLM review">{overview.llm.enabled ? `${overview.llm.provider} (${overview.llm.models.join(' → ')})` : 'Disabled'} receives the claim and rule findings, calls lookup tools, and may add findings the rules can't express.</Step>
            <Step n={3} title="Merge">LLM findings are capped at <b>{overview.scoring.llm_max_severity}</b> severity and add at most <b>+{overview.scoring.max_llm_points_per_agent}</b> points. On any LLM error the agent keeps its rule result.</Step>
          </ol>
        </Panel>
        <Panel title="Tools available to the LLM" icon={<Wrench className="size-4 text-violet-600" aria-hidden />}>
          <ul className="space-y-2">
            {overview.tools.map((tool) => (
              <li key={tool.name} className="text-sm">
                <code className="rounded bg-violet-50 px-1.5 py-0.5 text-xs text-violet-800">{tool.name}()</code>
                <p className="mt-0.5 text-xs text-slate-600">{tool.description}</p>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Guardrails" icon={<Gauge className="size-4 text-emerald-600" aria-hidden />}>
          <ul className="space-y-2 text-sm text-slate-700">
            <Li>Claim data and tool output are treated as untrusted data, never as instructions.</Li>
            <Li>The LLM can't issue “high” findings or override the rule score.</Li>
            <Li>Date of birth is never sent to the LLM.</Li>
            <Li>The customer never sees scores, agent names or findings.</Li>
            <Li>Each agent fails independently, so one failure can't block the claim.</Li>
          </ul>
        </Panel>
      </div>
      {!done.length && (
        <p className="flex items-center justify-center gap-2 text-sm text-slate-500">
          <ClipboardList className="size-4" aria-hidden /> Submit a claim from the customer journey to overlay live agent results here.
        </p>
      )}
    </div>
  )
}

const TONES = {
  sky: 'from-sky-50 ring-sky-200 [&_.dot]:bg-sky-600',
  amber: 'from-amber-50 ring-amber-200 [&_.dot]:bg-amber-500',
  green: 'from-emerald-50 ring-emerald-200 [&_.dot]:bg-emerald-600',
}

function Node({ step, title, icon, tone, children }: { step: string; title: string; icon: ReactNode; tone: keyof typeof TONES; children: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={cn('rounded-2xl bg-gradient-to-b to-white p-3 ring-1', TONES[tone])}>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-900">
        <span className="dot grid size-5 place-items-center rounded-full text-[10px] text-white">{step}</span>
        <span className="text-slate-500">{icon}</span>
        {title}
      </div>
      <ul className="space-y-1">{children}</ul>
    </motion.div>
  )
}

function Li({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-1.5 text-[12px] leading-snug text-slate-700">
      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-slate-400" aria-hidden />
      <span>{children}</span>
    </li>
  )
}

function Arrow() {
  return (
    <div className="grid place-items-center text-indigo-400" aria-hidden>
      <ArrowRight className="hidden size-5 xl:block" />
      <ArrowDown className="size-5 xl:hidden" />
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-violet-100 text-xs font-semibold text-violet-700">{n}</span>
      <div>
        <div className="font-medium text-slate-900">{title}</div>
        <p className="text-xs leading-relaxed text-slate-600">{children}</p>
      </div>
    </li>
  )
}
