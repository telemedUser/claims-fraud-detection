import { Scale, Sparkles } from 'lucide-react'
import type { Overview } from '../../api'
import { Badge } from '../../components/ui'
import { AGENT_ICON, Panel } from './common'

export default function AgentsView({ overview }: { overview: Overview }) {
  const s = overview.scoring
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        {overview.agents.map((a) => {
          const Icon = AGENT_ICON[a.name]
          return (
            <Panel key={a.name} title={a.title} icon={<span className="grid size-7 place-items-center rounded-lg bg-indigo-50"><Icon className="size-4 text-indigo-600" aria-hidden /></span>}
              actions={<Badge tone="indigo">weight {a.weight}</Badge>}>
              <p className="text-sm text-slate-700">{a.purpose}</p>
              <div className="mt-4">
                <div className="mb-1.5 text-xs font-medium tracking-wide text-slate-500 uppercase">Rule checks ({a.checks.length})</div>
                <div className="flex flex-wrap gap-1.5">
                  {a.checks.map((c) => (
                    <code key={c} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700">{c}</code>
                  ))}
                </div>
              </div>
              <div className="mt-4 rounded-xl bg-violet-50/70 p-3 ring-1 ring-violet-100">
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-violet-800">
                  <Sparkles className="size-3.5" aria-hidden /> LLM review focus
                </div>
                <p className="text-xs leading-relaxed text-violet-900/80">{a.llm_focus}</p>
              </div>
              <code className="mt-3 block text-[11px] text-slate-400">agent id: {a.name}</code>
            </Panel>
          )
        })}
      </div>
      <Panel title="Scoring model" icon={<Scale className="size-4 text-amber-600" aria-hidden />}>
        <div className="grid gap-6 text-sm md:grid-cols-3">
          <div>
            <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">Formula</div>
            <code className="mt-1 block rounded-lg bg-slate-50 p-2 text-xs text-slate-800">{s.rule}</code>
          </div>
          <div>
            <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">Severity points</div>
            <div className="mt-2 flex gap-2">
              <Badge>low {s.severity_points.low}</Badge>
              <Badge tone="amber">medium {s.severity_points.medium}</Badge>
              <Badge tone="red">high {s.severity_points.high}</Badge>
            </div>
            <p className="mt-2 text-xs text-slate-600">LLM observations: max {s.llm_max_severity} severity, scored as potential anomalies (cap {s.max_llm_points_per_agent} per agent, {s.max_llm_points_total} per claim).</p>
          </div>
          <div>
            <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">Decision thresholds</div>
            <div className="relative mt-3 h-3 rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-500">
              {[s.thresholds.manual_review_at, s.thresholds.investigate_at].map((v) => (
                <span key={v} className="absolute -top-1 h-5 w-0.5 bg-slate-900" style={{ left: `${v}%` }}>
                  <span className="absolute top-5 -translate-x-1/2 text-[10px] text-slate-600">{v}</span>
                </span>
              ))}
            </div>
            <div className="mt-6 flex justify-between text-[11px] text-slate-600">
              <span>Low risk</span><span>Manual review</span><span>Investigate</span>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  )
}
