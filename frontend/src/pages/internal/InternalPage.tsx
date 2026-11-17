import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Bot, ExternalLink, KeyRound, LayoutList, LogOut, RotateCcw, Workflow } from 'lucide-react'
import { ApiError, internalApi, type InternalSummary, type Overview } from '../../api'
import { Alert, Button, Card, Input, Logo } from '../../components/ui'
import { cn } from '../../lib/utils'
import WorkflowView from './WorkflowView'
import AgentsView from './AgentsView'
import ClaimsView from './ClaimsView'

const KEY_STORAGE = 'claimshield.internal_key'
type Tab = 'workflow' | 'agents' | 'claims'

export default function InternalPage() {
  const [key, setKey] = useState(() => sessionStorage.getItem(KEY_STORAGE) ?? '')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const client = useMemo(() => internalApi(key), [key])

  const signIn = useCallback(async (k: string) => {
    try {
      const o = await internalApi(k).overview()
      sessionStorage.setItem(KEY_STORAGE, k)
      setKey(k)
      setOverview(o)
      setAuthError(null)
    } catch (e) {
      sessionStorage.removeItem(KEY_STORAGE)
      setOverview(null)
      setAuthError(e instanceof ApiError ? e.message : 'Sign-in failed')
    }
  }, [])

  useEffect(() => {
    if (key) signIn(key)
    document.title = 'Fraud Intelligence Console · ClaimShield'
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (!overview) return <KeyGate onSubmit={signIn} error={authError} />
  return (
    <Console
      overview={overview}
      client={client}
      onSignOut={() => {
        sessionStorage.removeItem(KEY_STORAGE)
        setKey('')
        setOverview(null)
      }}
    />
  )
}

function KeyGate({ onSubmit, error }: { onSubmit: (k: string) => void; error: string | null }) {
  const [value, setValue] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (value.trim()) onSubmit(value.trim())
  }
  return (
    <div className="grid min-h-dvh place-items-center bg-slate-950 px-4">
      <Card className="w-full max-w-sm p-6">
        <Logo subtitle="Fraud Intelligence Console" />
        <h1 className="mt-6 text-lg font-semibold text-slate-900">Internal access</h1>
        <p className="mt-1 text-sm text-slate-600">Enter the internal API key (INTERNAL_API_KEY in the server .env).</p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <Input type="password" aria-label="Internal key" placeholder="Internal key" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full">
            <KeyRound className="size-4" aria-hidden /> Unlock console
          </Button>
        </form>
      </Card>
    </div>
  )
}

function Console({ overview: initial, client, onSignOut }: { overview: Overview; client: ReturnType<typeof internalApi>; onSignOut: () => void }) {
  const [tab, setTab] = useState<Tab>('workflow')
  const [overview, setOverview] = useState(initial)
  const [claims, setClaims] = useState<InternalSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [c, o] = await Promise.all([client.claims(), client.overview()])
      setClaims(c)
      setOverview(o)
    } catch {
      /* transient; next poll retries */
    }
  }, [client])

  useEffect(() => {
    refresh()
    const t = window.setInterval(refresh, 3000)
    return () => window.clearInterval(t)
  }, [refresh])

  const reset = async () => {
    if (!window.confirm('Reset all demo data? This clears processed claims and restores the seeded history.')) return
    setResetting(true)
    await client.reset().catch(() => undefined)
    setSelected(null)
    await refresh()
    setResetting(false)
  }

  const openClaim = (id: string) => {
    setSelected(id)
    setTab('claims')
  }

  const tabs: { id: Tab; label: string; icon: typeof Workflow }[] = [
    { id: 'workflow', label: 'Workflow', icon: Workflow },
    { id: 'agents', label: 'Agents', icon: Bot },
    { id: 'claims', label: `Claims (${claims.length})`, icon: LayoutList },
  ]

  return (
    <div className="min-h-dvh bg-slate-100">
      <header className="bg-slate-950 text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Logo dark subtitle="Fraud Intelligence Console · internal" />
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 ring-1',
              overview.llm.enabled ? 'bg-violet-500/15 text-violet-200 ring-violet-400/30' : 'bg-slate-800 text-slate-300 ring-slate-700')}>
              <span className={cn('size-1.5 rounded-full', overview.llm.enabled ? 'bg-violet-300' : 'bg-slate-500')} />
              {overview.llm.enabled ? `${overview.llm.provider} · ${overview.llm.models[0]}` : 'LLM off (rules only)'}
            </span>
            <a href="/?demo=1" target="_blank" rel="noreferrer">
              <Button variant="dark" size="sm"><ExternalLink className="size-3.5" aria-hidden /> Customer journey (demo)</Button>
            </a>
            <Button variant="dark" size="sm" onClick={reset} loading={resetting}><RotateCcw className="size-3.5" aria-hidden /> Reset demo data</Button>
            <Button variant="dark" size="sm" onClick={onSignOut} aria-label="Sign out"><LogOut className="size-3.5" aria-hidden /></Button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 px-4 sm:px-6" aria-label="Console sections">
          {tabs.map((t) => (
            <button key={t.id} type="button" onClick={() => setTab(t.id)} aria-current={tab === t.id ? 'page' : undefined}
              className={cn('flex items-center gap-2 rounded-t-xl px-4 py-2.5 text-sm font-medium transition',
                tab === t.id ? 'bg-slate-100 text-slate-900' : 'text-slate-400 hover:text-white')}>
              <t.icon className="size-4" aria-hidden /> {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {tab === 'workflow' && <WorkflowView overview={overview} claims={claims} client={client} onOpenClaim={openClaim} />}
        {tab === 'agents' && <AgentsView overview={overview} />}
        {tab === 'claims' && (
          <ClaimsView overview={overview} claims={claims} client={client} selected={selected} onSelect={setSelected} />
        )}
      </main>
    </div>
  )
}
