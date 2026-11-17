import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import { Check, ShieldCheck, Sparkles } from 'lucide-react'
import { api, ApiError, type Stage, type StatusResponse } from '../api'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { cn } from '../lib/utils'

const MIN_DISPLAY_MS = 4000 // keep the page up long enough to follow, even when the checks finish instantly
const REVEAL_EVERY_MS = 450 // reveal at most one finished stage per tick so progress reads smoothly

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

  return (
    <div className="mx-auto max-w-2xl">
      <Card className="overflow-hidden">
        <div className="relative bg-gradient-to-br from-indigo-600 to-violet-700 px-6 pt-10 pb-8 text-center text-white">
          <Radar done={allRevealed} />
          <h1 className="mt-6 text-2xl font-semibold">{allRevealed ? 'Verification complete' : 'Verifying your claim'}</h1>
          <p className="mt-1 text-sm text-indigo-100">
            Claim reference <span className="font-mono font-medium text-white">{claimId}</span>
          </p>
          <div className="mx-auto mt-6 h-2 max-w-sm overflow-hidden rounded-full bg-white/20" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <motion.div className="h-full rounded-full bg-white" animate={{ width: `${progress}%` }} transition={{ ease: 'easeOut', duration: 0.4 }} />
          </div>
          <p className="mt-2 text-xs text-indigo-100">{progress}%</p>
        </div>

        <ol className="divide-y divide-slate-100 px-2 py-2" aria-live="polite">
          {stages.map((s, i) => {
            const shownDone = i < revealed
            const running = !shownDone && (s.status !== 'pending' || i === revealed)
            return (
              <motion.li key={s.key} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                className="flex items-center gap-3 px-4 py-3">
                <StageIcon state={shownDone ? 'done' : running ? 'running' : 'pending'} />
                <span className={cn('flex-1 text-sm', shownDone ? 'text-slate-900' : running ? 'font-medium text-slate-900' : 'text-slate-400')}>
                  {s.label}
                </span>
                {running && s.ai_review && (
                  <span className="flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-violet-200">
                    <Sparkles className="size-3" aria-hidden /> AI review
                  </span>
                )}
                {shownDone && <span className="text-xs text-emerald-600">Done</span>}
              </motion.li>
            )
          })}
          {!stages.length && (
            <li className="flex items-center gap-3 px-4 py-6 text-sm text-slate-500">
              <Spinner /> Starting verification…
            </li>
          )}
        </ol>

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

function StageIcon({ state }: { state: 'done' | 'running' | 'pending' }) {
  if (state === 'done')
    return (
      <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} className="grid size-6 place-items-center rounded-full bg-emerald-500 text-white">
        <Check className="size-3.5" aria-hidden />
      </motion.span>
    )
  if (state === 'running') return <Spinner className="size-6" />
  return <span className="size-6 rounded-full border-2 border-slate-200" aria-hidden />
}

function Radar({ done }: { done: boolean }) {
  return (
    <div className="relative mx-auto grid size-28 place-items-center">
      {!done &&
        [0, 1, 2].map((i) => (
          <motion.span key={i} className="absolute inset-0 rounded-full border border-white/40"
            initial={{ scale: 0.5, opacity: 0.8 }} animate={{ scale: 1.25, opacity: 0 }}
            transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.8, ease: 'easeOut' }} />
        ))}
      <motion.div animate={done ? { scale: [1, 1.12, 1] } : { rotate: 360 }}
        transition={done ? { duration: 0.5 } : { duration: 6, repeat: Infinity, ease: 'linear' }}
        className="absolute inset-3 rounded-full bg-[conic-gradient(from_0deg,rgba(255,255,255,0.35),transparent_40%)]" />
      <div className="relative grid size-16 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/30 backdrop-blur">
        {done ? <Check className="size-8" aria-hidden /> : <ShieldCheck className="size-8" aria-hidden />}
      </div>
    </div>
  )
}
