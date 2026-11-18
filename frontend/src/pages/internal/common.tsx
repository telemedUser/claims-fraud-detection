import type { ReactNode } from 'react'
import { Building2, FileSearch, Receipt, Stethoscope, UserRound, type LucideIcon } from 'lucide-react'
import type { Finding, Overview } from '../../api'
import { Badge, type Tone } from '../../components/ui'
import { cn, scoreTone } from '../../lib/utils'

export const AGENT_ICON: Record<string, LucideIcon> = {
  provider_profile: Building2,
  claimant_profile: UserRound,
  document_scan: FileSearch,
  invoice_check: Receipt,
  medical_review: Stethoscope,
}

export const agentTitle = (o: Overview, name: string) => o.agents.find((a) => a.name === name)?.title ?? name

export const SEVERITY_TONE: Record<Finding['severity'], Tone> = { high: 'red', medium: 'amber', low: 'slate' }

export const DECISION_TONE: Record<string, Tone> = { auto_approve: 'green', manual_review: 'amber', investigate: 'red' }

const RING: Record<string, string> = { green: '#10b981', amber: '#f59e0b', red: '#f43f5e', slate: '#94a3b8' }

export function ScoreRing({ score, size = 96, label = 'risk' }: { score: number | null; size?: number; label?: string }) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const v = Math.max(0, Math.min(100, score ?? 0))
  const color = RING[scoreTone(score)]
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} style={{ transition: 'stroke-dashoffset .6s ease' }} />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-semibold tabular-nums text-slate-900" style={{ fontSize: size / 4 }}>{score == null ? '—' : Math.round(score)}</div>
        {size >= 80 && <div className="text-[10px] tracking-wide text-slate-500 uppercase">{label}</div>}
      </div>
    </div>
  )
}

export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const t = scoreTone(score)
  return (
    <div className={cn('h-1.5 overflow-hidden rounded-full bg-slate-200', className)}>
      <div className={cn('h-full rounded-full transition-all', t === 'red' ? 'bg-rose-500' : t === 'amber' ? 'bg-amber-500' : 'bg-emerald-500')}
        style={{ width: `${Math.max(2, Math.min(100, score))}%` }} />
    </div>
  )
}

export function SourceTag({ source }: { source: Finding['source'] }) {
  return source === 'llm' ? <Badge tone="violet">LLM</Badge> : <Badge tone="indigo">Rule</Badge>
}

export function Panel({ title, icon, actions, children, className }: { title: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('rounded-2xl bg-white p-5 shadow-[0_1px_2px_rgb(0_56_100/0.06),0_4px_16px_-8px_rgb(0_56_100/0.12)] ring-1 ring-indigo-100', className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-indigo-950">{icon}{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  )
}

/** Renders **bold** segments from LLM text without using innerHTML. */
export function RichText({ text }: { text: string }) {
  return (
    <div className="space-y-1.5 whitespace-pre-wrap">
      {text.split('\n').filter((l) => l.trim()).map((line, i) => (
        <p key={i}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
            seg.startsWith('**') && seg.endsWith('**') ? <strong key={j}>{seg.slice(2, -2)}</strong> : <span key={j}>{seg.replace(/^\s*[-*]\s+/, '• ')}</span>,
          )}
        </p>
      ))}
    </div>
  )
}
