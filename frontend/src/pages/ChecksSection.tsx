import { motion } from 'motion/react'
import { Building2, Calculator, CircleCheck, Clock, FileText, FlaskConical, ShieldCheck, Stethoscope, UserRoundCheck, type LucideIcon } from 'lucide-react'
import type { CustomerReport } from '../api'
import { Card } from '../components/ui'
import { CHECK_OUTCOME_LABEL, cn } from '../lib/utils'

type Check = CustomerReport['checks'][number]
type Outcome = Check['outcome']

/** Customer wording only: what each area covers, never what a check found or how it is scored. */
const CHECK_INFO: Record<string, { icon: LucideIcon; covers: string }> = {
  'Hospital and doctor check': { icon: Building2, covers: 'The hospital and your treating doctor are registered and part of our network.' },
  'Policy and claim history': { icon: UserRoundCheck, covers: 'Your policy cover and dates, and how this claim fits with earlier ones.' },
  'Document review': { icon: FileText, covers: 'Your documents are complete, readable and match the details you entered.' },
  'Medical bill validation': { icon: Calculator, covers: 'The bill items, totals and payment details add up.' },
  'Medical records review': { icon: Stethoscope, covers: 'The diagnosis, treatment and reports fit together.' },
}

const OUTCOME: Record<Outcome, { color: string; icon: LucideIcon; pill: string; tile: string; iconBox: string; help: string }> = {
  no_issues: {
    color: '#10b981', icon: CircleCheck,
    pill: 'bg-emerald-50 text-emerald-700 ring-emerald-200', tile: 'ring-emerald-100 hover:ring-emerald-200', iconBox: 'bg-emerald-50 text-emerald-600',
    help: 'Nothing here needed a closer look.',
  },
  unavailable: {
    color: '#f59e0b', icon: Clock,
    pill: 'bg-amber-50 text-amber-800 ring-amber-200', tile: 'ring-amber-100 hover:ring-amber-200', iconBox: 'bg-amber-50 text-amber-600',
    help: 'A specialist will look at this part. This is a normal step, not a decision.',
  },
  simulated: {
    color: '#0ea5e9', icon: FlaskConical,
    pill: 'bg-sky-50 text-sky-700 ring-sky-200', tile: 'ring-sky-100 hover:ring-sky-200', iconBox: 'bg-sky-50 text-sky-600',
    help: 'Uses a practice registry in this demo, so the result is for illustration only.',
  },
}
const ORDER: Outcome[] = ['no_issues', 'unavailable', 'simulated']

export default function ChecksSection({ checks }: { checks: Check[] }) {
  const n = checks.length
  const count = (o: Outcome) => checks.filter((c) => c.outcome === o).length
  const clear = count('no_issues')
  const review = count('unavailable')
  const headline = review === 0
    ? 'All checks are complete. Nothing needs a closer look.'
    : `${clear} of ${n} areas are clear. ${review} ${review === 1 ? 'is' : 'are'} with a claims specialist for a closer look.`

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-indigo-100 bg-gradient-to-r from-indigo-600 to-indigo-500 px-6 py-4 text-white">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-5" aria-hidden /> Checks on your claim</h2>
          <p className="mt-0.5 text-sm text-indigo-100">{n} automatic checks. A person makes every final decision.</p>
        </div>
      </div>

      <div className="grid gap-6 p-6 lg:grid-cols-[260px_1fr] lg:items-center">
        {/* overview: segmented ring and legend */}
        <div className="flex flex-col items-center gap-4">
          <Ring checks={checks} />
          <p className="text-center text-sm text-slate-700">{headline}</p>
          <ul className="flex flex-wrap justify-center gap-2 text-xs">
            {ORDER.filter((o) => count(o) > 0).map((o) => {
              const s = OUTCOME[o]
              return (
                <li key={o} className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium ring-1', s.pill)}>
                  <span className="size-2 rounded-full" style={{ background: s.color }} />
                  {count(o)} {CHECK_OUTCOME_LABEL[o]}
                </li>
              )
            })}
          </ul>
        </div>

        {/* one tile per area */}
        <ul className="grid gap-3 sm:grid-cols-2">
          {checks.map((c, i) => {
            const info = CHECK_INFO[c.label] ?? { icon: ShieldCheck, covers: '' }
            const s = OUTCOME[c.outcome]
            const Icon = info.icon
            const StatusIcon = s.icon
            return (
              <motion.li key={c.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.07 }}
                className={cn('flex gap-3 rounded-lg bg-white p-4 ring-1 transition', s.tile, i === checks.length - 1 && checks.length % 2 === 1 && 'sm:col-span-2')}>
                <span className={cn('grid size-10 shrink-0 place-items-center rounded-lg', s.iconBox)}><Icon className="size-5" aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">{c.label}</h3>
                    <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1', s.pill)}>
                      <StatusIcon className="size-3.5" aria-hidden /> {CHECK_OUTCOME_LABEL[c.outcome]}
                    </span>
                  </div>
                  {info.covers && <p className="mt-1 text-xs leading-relaxed text-slate-600"><span className="font-medium text-slate-700">What we look at:</span> {info.covers}</p>}
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{s.help}</p>
                </div>
              </motion.li>
            )
          })}
        </ul>
      </div>
    </Card>
  )
}

/** Donut split into one segment per check, coloured by outcome. */
function Ring({ checks }: { checks: Check[] }) {
  const n = Math.max(1, checks.length)
  const size = 180, stroke = 18, r = (size - stroke) / 2, c = 2 * Math.PI * r
  const gap = checks.length > 1 ? 6 : 0
  const seg = c / n - gap
  const clear = checks.filter((k) => k.outcome === 'no_issues').length
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" role="img"
        aria-label={`${clear} of ${checks.length} checks clear`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef6fd" strokeWidth={stroke} />
        {checks.map((k, i) => (
          <motion.circle key={k.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={OUTCOME[k.outcome].color}
            strokeWidth={stroke} strokeLinecap="butt" strokeDasharray={`${seg} ${c - seg}`}
            initial={{ strokeDashoffset: -i * (seg + gap) + seg, opacity: 0 }}
            animate={{ strokeDashoffset: -i * (seg + gap), opacity: 1 }}
            transition={{ delay: 0.1 + i * 0.12, duration: 0.5, ease: 'easeOut' }}>
            <title>{`${k.label}: ${CHECK_OUTCOME_LABEL[k.outcome]}`}</title>
          </motion.circle>
        ))}
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-3xl font-semibold text-indigo-950 tabular-nums">{clear}<span className="text-lg text-slate-400">/{checks.length}</span></div>
          <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">clear</div>
        </div>
      </div>
    </div>
  )
}
