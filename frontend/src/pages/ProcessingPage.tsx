import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import { Building2, Calculator, Check, FileSearch, FileText, ShieldCheck, Sparkles, Stethoscope, UserRound, type LucideIcon } from 'lucide-react'
import { api, ApiError, type Stage, type StatusResponse } from '../api'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { cn } from '../lib/utils'

const MIN_DISPLAY_MS = 4000 // keep the page up long enough to follow, even when the checks finish instantly
const REVEAL_EVERY_MS = 450 // reveal at most one finished stage per tick so progress reads smoothly

// Customer stage labels come from app/api/customer_view.py (CUSTOMER_LABELS); keys are opaque.
const CHECK_ICON: Record<string, LucideIcon> = {
  'Checking hospital and doctor': Building2,
  'Checking policy and claim history': UserRound,
  'Checking your documents': FileSearch,
  'Validating your medical bill': Calculator,
  'Reviewing your medical records': Stethoscope,
}

type View = 'done' | 'running' | 'pending'

export default function ProcessingPage() {
  const { claimId = '' } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(0)
  const started = useRef(Date.now())
  const stagesRef = useRef<Stage[]>([])

  // Poll the backend.
  useEffect(() => {
    let alive = true
    let timer: number
    const poll = async () => {
      try {
        const s = await api.status(claimId)
        if (!alive) return
        setStatus(s)
        stagesRef.current = s.stages
        if (s.status === 'processing') timer = window.setTimeout(poll, 700)
      } catch (e) {
        if (alive) setError(e instanceof ApiError && e.status === 404 ? 'We could not find this claim.' : 'Lost connection. Retrying…')
        if (alive) timer = window.setTimeout(poll, 2000)
      }
    }
    poll()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [claimId])

  // Reveal finished stages in order.
  useEffect(() => {
    const t = window.setInterval(() => {
      setRevealed((r) => (r < stagesRef.current.length && stagesRef.current[r].status === 'done' ? r + 1 : r))
    }, REVEAL_EVERY_MS)
    return () => window.clearInterval(t)
  }, [])

  const stages = status?.stages ?? []
  const allRevealed = stages.length > 0 && revealed >= stages.length

  // Move to the report once everything is done and shown.
  useEffect(() => {
    if (status?.status !== 'completed' || !allRevealed) return
    const wait = Math.max(0, MIN_DISPLAY_MS - (Date.now() - started.current))
    const t = window.setTimeout(() => navigate(`/claims/${claimId}`, { replace: true }), wait + 600)
    return () => window.clearTimeout(t)
  }, [status?.status, allRevealed, claimId, navigate])

  const progress = stages.length ? Math.round((revealed / stages.length) * 100) : 4
  const failed = status?.status === 'failed'

  const view = (i: number): View => {
    const s = stages[i]
    if (i < revealed) return 'done'
    return s.status !== 'pending' || i === revealed ? 'running' : 'pending'
  }
  const indexed = stages.map((s, i) => ({ s, i, v: view(i) }))
  const checks = indexed.filter(({ s }) => s.label in CHECK_ICON)
  const flow = indexed.filter(({ s }) => !(s.label in CHECK_ICON)) // documents received, assessing, preparing report
  const current = indexed.find((x) => x.v === 'running')
  const checksDone = checks.length > 0 && checks.every((c) => c.v === 'done')
  const hub = allRevealed
    ? { title: 'Checks complete', detail: 'Opening your claim report…' }
    : !checksDone
      ? { title: 'Running checks', detail: 'Five checks run side by side on your claim.' }
      : { title: current?.s.label ?? 'Assessing your claim', detail: current?.s.label.startsWith('Preparing') ? 'Putting your claim report together.' : 'Bringing the check results together.' }

  return (
    <div className="mx-auto max-w-3xl">
      <Card className="overflow-hidden rounded-xl ring-indigo-100">
        <div className="bg-indigo-600 px-6 py-7 text-center text-white">
          <h1 className="text-2xl font-semibold">{allRevealed ? 'Checks complete' : 'Checking your claim'}</h1>
          <p className="mt-1 text-sm text-indigo-100">
            Claim reference <span className="font-mono font-medium text-white">{claimId}</span>
          </p>
          <div className="mx-auto mt-5 h-2 max-w-sm overflow-hidden rounded-full bg-white/25" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
            <motion.div className="h-full rounded-full bg-white" animate={{ width: `${progress}%` }} transition={{ ease: 'easeOut', duration: 0.4 }} />
          </div>
          <p className="mt-2 text-xs text-indigo-100">{progress}%</p>
        </div>

        {stages.length === 0 ? (
          <div className="flex items-center justify-center gap-3 px-6 py-16 text-sm text-slate-500"><Spinner /> Starting your checks…</div>
        ) : (
          <div className="grid items-center gap-6 px-6 py-8 sm:grid-cols-[minmax(0,1fr)_96px_220px] sm:gap-0" aria-live="polite">
            <ol className="space-y-3">
              {checks.map(({ s, v }, k) => {
                const Icon = CHECK_ICON[s.label]
                return (
                  <motion.li key={s.key} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: k * 0.06 }}
                    className={cn('flex h-[52px] items-center gap-3 rounded-lg bg-white px-3 ring-1 transition-colors',
                      v === 'done' ? 'ring-indigo-200' : v === 'running' ? 'ring-2 ring-indigo-400 shadow-sm' : 'ring-slate-200')}>
                    <span className={cn('grid size-8 shrink-0 place-items-center rounded-md', v === 'pending' ? 'bg-slate-100 text-slate-400' : 'bg-indigo-600 text-white')}>
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className={cn('min-w-0 flex-1 text-sm font-semibold leading-tight', v === 'pending' ? 'text-slate-400' : 'text-slate-900')}>
                      {s.label}
                      {v === 'running' && s.ai_review && (
                        <span className="mt-0.5 flex items-center gap-1 text-[10px] font-medium text-violet-600"><Sparkles className="size-3" aria-hidden /> AI review</span>
                      )}
                    </span>
                    <StateIcon v={v} />
                  </motion.li>
                )
              })}
            </ol>

            <Connectors states={checks.map((c) => c.v)} />

            <div className="text-center">
              <div className={cn('relative mx-auto flex h-[172px] w-[148px] flex-col items-center justify-center rounded-lg bg-white ring-2 transition-colors',
                allRevealed ? 'ring-emerald-500' : 'ring-indigo-500')}>
                <span className="absolute top-2.5 right-2.5">{allRevealed ? <Check className="size-4 text-emerald-600" aria-hidden /> : <Spinner className="size-4" />}</span>
                <motion.div animate={allRevealed ? { scale: [1, 1.12, 1] } : { y: [0, -3, 0] }} transition={allRevealed ? { duration: 0.5 } : { duration: 2, repeat: Infinity }}>
                  {allRevealed ? <ShieldCheck className="size-12 text-emerald-600" aria-hidden /> : <FileText className="size-12 text-indigo-600" aria-hidden />}
                </motion.div>
                <div className="mt-4 w-20 space-y-1.5" aria-hidden>
                  {[1, 0.8, 0.6].map((w, i) => (
                    <motion.div key={i} className="h-1.5 rounded-full bg-indigo-100" style={{ width: `${w * 100}%` }}
                      animate={allRevealed ? { backgroundColor: '#a7f3d0' } : { opacity: [0.5, 1, 0.5] }} transition={{ duration: 1.6, repeat: allRevealed ? 0 : Infinity, delay: i * 0.2 }} />
                  ))}
                </div>
              </div>
              <div className={cn('mt-4 text-sm font-semibold', allRevealed ? 'text-emerald-700' : 'text-indigo-700')}>{hub.title}</div>
              <div className="mt-0.5 text-xs text-slate-500">{hub.detail}</div>
            </div>
          </div>
        )}

        {flow.length > 0 && (
          <ol className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 border-t border-slate-100 bg-slate-50/70 px-6 py-3 text-xs">
            {flow.map(({ s, v }) => (
              <li key={s.key} className={cn('flex items-center gap-1.5', v === 'done' ? 'text-slate-700' : v === 'running' ? 'font-medium text-indigo-700' : 'text-slate-400')}>
                {v === 'done' ? <Check className="size-3.5 text-emerald-600" aria-hidden /> : v === 'running' ? <Spinner className="size-3.5" /> : <span className="size-3.5 rounded-full border border-slate-300" aria-hidden />}
                {s.label}
              </li>
            ))}
          </ol>
        )}

        {(failed || error) && (
          <div className="space-y-3 px-6 pb-6">
            <Alert tone={failed ? 'amber' : 'red'}>{failed ? status?.message : error}</Alert>
            {failed && <Button variant="secondary" onClick={() => navigate('/')}>Back to start</Button>}
          </div>
        )}
      </Card>
      <p className="mt-4 text-center text-xs text-slate-500">You can keep this page open. It usually takes less than a minute.</p>
    </div>
  )
}

function StateIcon({ v }: { v: View }) {
  if (v === 'done')
    return (
      <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} className="grid size-5 shrink-0 place-items-center rounded-full bg-emerald-500 text-white" aria-label="Done">
        <Check className="size-3" aria-hidden />
      </motion.span>
    )
  if (v === 'running') return <Spinner className="size-5 shrink-0" />
  return <span className="size-5 shrink-0 rounded-full border-2 border-slate-200" aria-label="Waiting" />
}

/** Curved lines from each check (left, 52px rows with 12px gaps) into the assessment card (right). */
function Connectors({ states }: { states: View[] }) {
  const ROW = 52, GAP = 12, W = 96
  const h = states.length * ROW + (states.length - 1) * GAP
  const mid = h / 2
  return (
    <svg viewBox={`0 0 ${W} ${h}`} width={W} height={h} className="hidden sm:block" aria-hidden>
      {states.map((v, i) => {
        const y = i * (ROW + GAP) + ROW / 2
        const d = `M0 ${y} C ${W * 0.55} ${y}, ${W * 0.45} ${mid}, ${W} ${mid}`
        return (
          <g key={i}>
            <path d={d} fill="none" stroke="#dbeafe" strokeWidth={2} />
            {v !== 'pending' && (
              <motion.path d={d} fill="none" stroke="#0071c2" strokeWidth={2} className={v === 'running' ? 'flow-line' : undefined}
                initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6 }} />
            )}
          </g>
        )
      })}
      <circle cx={W - 2} cy={mid} r={3.5} fill="#0071c2" />
    </svg>
  )
}
