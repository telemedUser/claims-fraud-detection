import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import {
  ArrowRight, Building2, Calculator, Check, CircleCheck, Clock, Copy, FileText, FileUp, Phone, Plus, Printer,
  Info, ShieldAlert, ShieldCheck, Stethoscope, UserRoundCheck, FlaskConical, Mail,
} from 'lucide-react'
import { api, ApiError, type CustomerReport, type Level, type NextStep, type StatusResponse, type TimelineStep } from '../api'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { CHECK_OUTCOME_LABEL, cn, DOC_LABEL, fmtDate, fmtDateTime, inr } from '../lib/utils'

const LEVEL: Record<Level, { hero: string; chip: string; icon: ReactNode; soft: string; text: string; ring: string }> = {
  green: { hero: 'from-emerald-500 to-teal-600', chip: 'On track', icon: <CircleCheck className="size-8" aria-hidden />, soft: 'bg-emerald-50', text: 'text-emerald-800', ring: 'ring-emerald-200' },
  amber: { hero: 'from-amber-500 to-orange-500', chip: 'Under review', icon: <Clock className="size-8" aria-hidden />, soft: 'bg-amber-50', text: 'text-amber-900', ring: 'ring-amber-200' },
  red: { hero: 'from-yellow-300 to-yellow-500', chip: 'Action needed', icon: <ShieldAlert className="size-8" aria-hidden />, soft: 'bg-yellow-50', text: 'text-yellow-900', ring: 'ring-yellow-200' },
}

export default function ReportPage() {
  const { claimId = '' } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<StatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .status(claimId)
      .then((s) => (s.status === 'processing' ? navigate(`/claims/${claimId}/processing`, { replace: true }) : setData(s)))
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'We could not find this claim.' : 'Could not load the report.'))
  }, [claimId, navigate])

  if (error) return <Alert className="mx-auto max-w-xl">{error}</Alert>
  if (!data) return <div className="grid place-items-center py-24"><Spinner className="size-8" /></div>
  if (data.status === 'failed' || !data.report)
    return <Alert tone="amber" className="mx-auto max-w-xl">{data.message ?? 'This claim is being reviewed manually.'}</Alert>

  const r = data.report
  const lv = LEVEL[r.level]
  const c = r.claim
  const dark = r.level === 'red' // yellow needs dark text to stay readable
  const am = r.insights?.amounts // absent when the API predates the amounts comparison

  return (
    <div className="w-full space-y-6">
      {/* status */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className={cn('overflow-hidden rounded-2xl bg-gradient-to-br p-6 shadow-lg sm:p-8', dark ? 'text-yellow-950' : 'text-white', lv.hero)}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
          <div className={cn('grid size-16 shrink-0 place-items-center rounded-2xl ring-1', dark ? 'bg-yellow-950/10 ring-yellow-950/20' : 'bg-white/20 ring-white/30')}>{lv.icon}</div>
          <div className="flex-1">
            <span className={cn('rounded-full px-2.5 py-0.5 text-xs font-medium', dark ? 'bg-yellow-950/10' : 'bg-white/20')}>{lv.chip}</span>
            <h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{r.outcome.title}</h1>
            <p className={cn('mt-1', dark ? 'text-yellow-950/90' : 'text-white/90')}>{r.outcome.message}</p>
          </div>
          <div className="text-left sm:text-right">
            <div className={cn('text-xs', dark ? 'text-yellow-950/80' : 'text-white/80')}>Claimed amount</div>
            <div className="text-2xl font-semibold">{inr(c.claimed_amount)}</div>
            <CopyRef value={c.claim_id} light={!dark} dark={dark} />
          </div>
        </div>
      </motion.div>

      <NextStepCard step={r.next_step} onRetry={() => navigate('/')} />

      {am && (am.claim_vs_bill !== 0 || am.bill_vs_items !== 0) && (
        <Alert tone="amber">
          <div className="space-y-1">
            {am.claim_vs_bill !== 0 && (
              <p>
                You claimed {inr(am.claimed)} but your bill totals {inr(am.bill_total)}, a difference of {inr(Math.abs(am.claim_vs_bill))}.
                {am.claim_vs_bill > 0 && ' This is why a specialist is looking at your claim.'}
              </p>
            )}
            {am.bill_vs_items !== 0 && (
              <p>The bill total differs from the sum of its itemised charges ({inr(am.items_sum)}) by {inr(Math.abs(am.bill_vs_items))}.</p>
            )}
            <Link to={r.insights_url} className="font-medium underline">See the full comparison</Link>
          </div>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">Where your claim is</h2>
          <Timeline steps={r.timeline} level={r.level} />
        </Card>
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">Your claim at a glance</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <Row k="Policy" v={`${c.plan ?? ''} · ${c.policy_number ?? ''}`} />
            <Row k="Hospital" v={`${c.hospital ?? '—'}${c.hospital_city ? `, ${c.hospital_city}` : ''}`} />
            <Row k="Condition" v={c.diagnosis} />
            <Row k="Hospital stay" v={`${fmtDate(c.admission_date)} – ${fmtDate(c.discharge_date)}`} />
            <Row k="Submitted" v={fmtDateTime(c.submitted_at)} />
          </dl>
          <Link to={r.insights_url} className="mt-5 flex items-center justify-between rounded-xl bg-indigo-50 px-4 py-3 text-sm font-medium text-indigo-700 ring-1 ring-indigo-100 transition hover:bg-indigo-100">
            More insights about this claim <ArrowRight className="size-4" aria-hidden />
          </Link>
        </Card>
      </div>

      <Card className="p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold text-slate-900">Checks on your claim</h2>
          <span className="text-xs text-slate-500">Automatic checks. A person makes every final decision.</span>
        </div>
        <CheckMap checks={r.checks} />
      </Card>

      <Card className="p-6">
        <h2 className="font-semibold text-slate-900">Documents received</h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {r.documents.map((d, i) => (
            <li key={i} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <FileText className="size-4 text-indigo-600" aria-hidden />
              <span className="min-w-0">
                <span className="block truncate text-slate-800">{d.filename}</span>
                <span className="text-xs text-slate-500">{DOC_LABEL[d.doc_type]}</span>
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:ml-auto sm:max-w-md print:hidden">
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden /> Print / save PDF
        </Button>
        <Button onClick={() => navigate('/')}>
          <Plus className="size-4" aria-hidden /> New claim
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- what to do next

function NextStepCard({ step, onRetry }: { step: NextStep; onRetry: () => void }) {
  const lv = LEVEL[step.level]
  const Icon = step.type === 'resubmit' ? FileUp : step.type === 'call_helpline' ? Phone : step.type === 'wait' ? Clock : UserRoundCheck
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
      className={cn('rounded-2xl p-6 ring-1', lv.soft, lv.ring)} aria-labelledby="next-step">
      <div className="flex items-start gap-4">
        <span className={cn('grid size-11 shrink-0 place-items-center rounded-xl bg-white shadow-sm', lv.text)}><Icon className="size-5" aria-hidden /></span>
        <div className="flex-1">
          <div className={cn('text-[11px] font-semibold tracking-wide uppercase', lv.text)}>What you need to do</div>
          <h2 id="next-step" className="mt-0.5 text-lg font-semibold text-slate-900">{step.title}</h2>
          <p className="mt-1 text-sm text-slate-700">{step.detail}</p>

          {step.documents.length > 0 && (
            <ul className="mt-4 space-y-2">
              {step.documents.map((d, i) => (
                <li key={i} className="flex gap-3 rounded-xl bg-white/80 p-3 text-sm ring-1 ring-black/5">
                  <FileUp className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
                  <span><b className="text-slate-900">{d.label}</b><span className="block text-slate-600">{d.reason}</span></span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex flex-wrap items-stretch gap-3">
            {step.type === 'resubmit' && (
              <Button onClick={onRetry}><FileUp className="size-4" aria-hidden /> Upload documents again</Button>
            )}
            {(step.type === 'call_helpline' || step.type === 'resubmit') && <Helpline h={step.helpline} primary={step.type === 'call_helpline'} />}
          </div>
        </div>
      </div>
    </motion.section>
  )
}

function Helpline({ h, primary }: { h: NextStep['helpline']; primary: boolean }) {
  return (
    <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-white px-4 py-3 text-sm ring-1 ring-black/5', primary && 'shadow-sm')}>
      <a href={`tel:${h.number.replace(/[^+\d]/g, '')}`} className="flex items-center gap-2 font-semibold text-slate-900 hover:text-indigo-700">
        <Phone className="size-4 text-indigo-600" aria-hidden /> {h.number}
      </a>
      <span className="text-slate-500">{h.hours}</span>
      <a href={`mailto:${h.email}?subject=${encodeURIComponent(`Claim ${h.reference}`)}`} className="flex items-center gap-1.5 text-slate-600 hover:text-indigo-700">
        <Mail className="size-4" aria-hidden /> {h.email}
      </a>
      <span className="text-xs text-slate-500">Quote <CopyRef value={h.reference} inline /></span>
    </div>
  )
}

function CopyRef({ value, light, dark, inline }: { value: string; light?: boolean; dark?: boolean; inline?: boolean }) {
  const [done, setDone] = useState(false)
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) })
  }
  return (
    <button type="button" onClick={copy} title="Copy reference" aria-label={`Copy claim reference ${value}`}
      className={cn('inline-flex items-center gap-1 font-mono text-xs', inline ? 'font-semibold text-slate-800' : 'mt-1', light && 'text-white/90 hover:text-white', dark && 'text-yellow-950/90 hover:text-yellow-950', !light && !dark && !inline && 'text-slate-600')}>
      {value} {done ? <Check className="size-3" aria-hidden /> : <Copy className="size-3 opacity-70" aria-hidden />}
    </button>
  )
}

// ---------------------------------------------------------------- timeline

function Timeline({ steps, level }: { steps: TimelineStep[]; level: Level }) {
  const dot = { green: 'bg-emerald-500', amber: 'bg-amber-500', red: 'bg-yellow-500' }[level]
  return (
    <ol className="relative mt-5 space-y-5 border-l-2 border-slate-200 pl-6">
      {steps.map((s, i) => (
        <motion.li key={s.key} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.12 }} className="relative">
          <span className={cn('absolute top-0.5 -left-[33px] grid size-4 place-items-center rounded-full ring-4 ring-white',
            s.state === 'done' ? 'bg-slate-700' : s.state === 'current' ? dot : 'bg-slate-300')}>
            {s.state === 'done' && <Check className="size-2.5 text-white" aria-hidden />}
            {s.state === 'current' && <span className={cn('absolute inline-flex size-full animate-ping rounded-full opacity-60', dot)} />}
          </span>
          <div className={cn('text-sm font-medium', s.state === 'upcoming' ? 'text-slate-400' : 'text-slate-900')}>{s.label}</div>
          {s.detail && <div className="text-xs text-slate-500">{s.detail}</div>}
          {s.date && <div className="mt-0.5 text-xs text-slate-500">{s.state === 'current' ? 'Expected ' : ''}{fmtDate(s.date)}{s.expected ? ` (${s.expected})` : ''}</div>}
        </motion.li>
      ))}
    </ol>
  )
}

// ---------------------------------------------------------------- checks as a constellation

const CHECK_ICON: Record<string, typeof Building2> = {
  'Hospital and doctor check': Building2,
  'Policy and claim history': UserRoundCheck,
  'Document review': FileText,
  'Medical bill validation': Calculator,
  'Medical records review': Stethoscope,
}
const NODE = {
  no_issues: { fill: '#10b981', soft: 'bg-emerald-50 text-emerald-800 ring-emerald-200', icon: CircleCheck },
  unavailable: { fill: '#f59e0b', soft: 'bg-amber-50 text-amber-800 ring-amber-200', icon: Clock },
  simulated: { fill: '#0ea5e9', soft: 'bg-sky-50 text-sky-800 ring-sky-200', icon: FlaskConical },
} as const

const CHECK_HELP: Record<CustomerReport['checks'][number]['outcome'], string> = {
  no_issues: 'Nothing in this area needed a closer look.',
  unavailable: 'A member of our team will look at this part of your claim. This is a normal step and not a decision. You only need to act if we ask you to.',
  simulated: 'This check uses a practice hospital registry in this demo, so the result is for illustration only.',
}

function Hint({ text }: { text: string }) {
  return (
    <span className="inline-flex">
      <button type="button" aria-label={text} className="rounded-full text-current/70 hover:text-current focus-visible:outline-2 focus-visible:outline-indigo-600">
        <Info className="size-3.5" aria-hidden />
      </button>
      <span role="tooltip" className="pointer-events-none invisible absolute right-2 bottom-full z-20 mb-1 w-64 rounded-lg bg-slate-900 px-3 py-2 text-left text-xs leading-relaxed font-normal whitespace-normal text-white opacity-0 shadow-lg transition group-focus:visible group-focus:opacity-100 group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
        {text}
      </span>
    </span>
  )
}

function CheckMap({ checks }: { checks: CustomerReport['checks'] }) {
  const n = checks.length
  const R = 100, cx = 160, cy = 136
  const pts = checks.map((_, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n
    return { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) }
  })
  const clear = checks.filter((k) => k.outcome === 'no_issues').length
  return (
    <div className="mt-4 grid items-center gap-6 sm:grid-cols-[320px_1fr]">
      <svg viewBox="0 0 320 268" className="mx-auto w-full max-w-[320px] overflow-visible" role="img"
        aria-label={`${clear} of ${n} checks show no issues`}>
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="#e2e8f0" strokeDasharray="3 5" />
        {pts.map((p, i) => (
          <motion.line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={NODE[checks[i].outcome].fill} strokeWidth={2} strokeOpacity={0.5}
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.2 + i * 0.12, duration: 0.6 }} />
        ))}
        <motion.circle cx={cx} cy={cy} r={34} fill="#4f46e5" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={{ type: 'spring' }} />
        <ShieldCheck x={cx - 14} y={cy - 22} width={28} height={28} color="#fff" aria-hidden />
        <text x={cx} y={cy + 20} textAnchor="middle" fontSize="10" fill="#fff" fontWeight="600">{clear}/{n} clear</text>
        {pts.map((p, i) => {
          const Icon = CHECK_ICON[checks[i].label] ?? ShieldCheck
          const fill = NODE[checks[i].outcome].fill
          return (
            <motion.g key={i} initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.5 + i * 0.12, type: 'spring' }}
              style={{ transformOrigin: `${p.x}px ${p.y}px` }}>
              <title>{`${checks[i].label}: ${CHECK_OUTCOME_LABEL[checks[i].outcome]}. ${CHECK_HELP[checks[i].outcome]}`}</title>
              <circle cx={p.x} cy={p.y} r={24} fill="#fff" stroke={fill} strokeWidth={3} />
              <Icon x={p.x - 10} y={p.y - 10} width={20} height={20} color={fill} aria-hidden />
            </motion.g>
          )
        })}
      </svg>
      <div><ul className="space-y-2.5">
        {checks.map((k, i) => {
          const s = NODE[k.outcome]
          const Icon = s.icon
          return (
            <motion.li key={k.label} tabIndex={0} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.08 }}
              className={cn('group relative flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm ring-1 focus-visible:outline-2 focus-visible:outline-indigo-600', s.soft)}>
              <span className="font-medium">{k.label}</span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-medium whitespace-nowrap"><Icon className="size-4" aria-hidden /> {CHECK_OUTCOME_LABEL[k.outcome]} <Hint text={CHECK_HELP[k.outcome]} /></span>
            </motion.li>
          )
        })}
      </ul>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] items-baseline gap-x-4">
      <dt className="text-slate-500">{k}</dt>
      <dd className="min-w-0 text-right font-medium break-words text-slate-900">{v}</dd>
    </div>
  )
}
