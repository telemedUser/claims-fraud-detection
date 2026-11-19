import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Bot, ExternalLink, KeyRound, LayoutList, LogOut, RotateCcw } from 'lucide-react'
import { ApiError, authApi, internalApi, setUnauthorizedHandler, tokenStore, type InternalSummary, type Me, type Overview } from '../../api'
import { Alert, Button, Card, Field, Input, Logo } from '../../components/ui'
import { cn } from '../../lib/utils'
import AgentsView from './AgentsView'
import ClaimsView from './ClaimsView'

type Tab = 'agents' | 'claims'

// Roles allowed to see each section (all four roles may read the console; reset is Administrator only).
const ALL_ROLES: Me['role'][] = ['Investigator', 'Ops_Manager', 'Fraud_Team', 'Administrator']
const TAB_ROLES: Record<Tab, Me['role'][]> = { agents: ALL_ROLES, claims: ALL_ROLES }
const ROLE_LABEL: Record<Me['role'], string> = {
  Investigator: 'Investigator',
  Ops_Manager: 'Ops manager',
  Fraud_Team: 'Fraud team',
  Administrator: 'Administrator',
}

export default function InternalPage() {
  const [me, setMe] = useState<Me | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const [checking, setChecking] = useState(() => !!tokenStore.get())
  const client = useMemo(() => internalApi(), [])

  const clearSession = useCallback((message: string | null) => {
    tokenStore.clear()
    setMe(null)
    setOverview(null)
    setAuthError(message)
  }, [])

  const load = useCallback(async () => {
    try {
      const [m, o] = await Promise.all([authApi.me(), client.overview()])
      setMe(m)
      setOverview(o)
      setAuthError(null)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) clearSession(null)
      else if (e instanceof ApiError && e.status === 403) clearSession('Your role does not have access to the console.')
      else clearSession(e instanceof ApiError ? e.message : 'Sign-in failed')
    } finally {
      setChecking(false)
    }
  }, [client, clearSession])

  const signIn = useCallback(
    async (username: string, password: string) => {
      try {
        await authApi.login(username, password)
      } catch (e) {
        setAuthError(e instanceof ApiError ? e.message : 'Sign-in failed')
        return
      }
      await load()
    },
    [load],
  )

  useEffect(() => {
    document.title = 'Fraud Intelligence Console � ClaimShield'
    setUnauthorizedHandler(() => {
      setMe(null)
      setOverview(null)
      setAuthError('Your session has expired. Please sign in again.')
    })
    if (tokenStore.get()) load()
    return () => setUnauthorizedHandler(null)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (checking) return <div className="min-h-dvh bg-indigo-900" aria-busy="true" />
  if (!me || !overview) return <LoginGate onSubmit={signIn} error={authError} />
  return <Console me={me} overview={overview} client={client} onSignOut={() => clearSession(null)} />
}

function LoginGate({ onSubmit, error }: { onSubmit: (u: string, p: string) => Promise<void>; error: string | null }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setBusy(true)
    await onSubmit(username.trim(), password)
    setBusy(false)
    setPassword('')
  }
  return (
    <div className="grid min-h-dvh place-items-center bg-gradient-to-br from-indigo-900 via-indigo-800 to-indigo-600 px-4">
      <Card className="w-full max-w-sm p-6">
        <Logo subtitle="Fraud Intelligence Console" />
        <h1 className="mt-6 text-lg font-semibold text-slate-900">Staff sign-in</h1>
        <p className="mt-1 text-sm text-slate-600">Sign in with your console username and password.</p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <Field label="Username" htmlFor="login-username">
            <Input id="login-username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </Field>
          <Field label="Password" htmlFor="login-password">
            <Input id="login-password" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" className="w-full" loading={busy}>
            <KeyRound className="size-4" aria-hidden /> Sign in
          </Button>
        </form>
      </Card>
    </div>
  )
}

function Console({ me, overview: initial, client, onSignOut }: { me: Me; overview: Overview; client: ReturnType<typeof internalApi>; onSignOut: () => void }) {
  const [tab, setTab] = useState<Tab>('claims')
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

  const allTabs: { id: Tab; label: string; icon: typeof Bot }[] = [
    { id: 'claims', label: `Claims (${claims.length})`, icon: LayoutList },
    { id: 'agents', label: 'Agents', icon: Bot },
  ]
  const tabs = allTabs.filter((t) => TAB_ROLES[t.id].includes(me.role))
  const activeTab = tabs.some((t) => t.id === tab) ? tab : tabs[0]?.id
  const canReset = me.role === 'Administrator'

  return (
    <div className="min-h-dvh bg-[#f4f8fc]">
      <header className="bg-gradient-to-r from-indigo-900 via-indigo-800 to-indigo-700 text-white shadow-sm">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Logo dark subtitle="Fraud Intelligence Console · internal" />
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <a href="/?demo=1" target="_blank" rel="noreferrer">
              <Button variant="dark" size="sm"><ExternalLink className="size-3.5" aria-hidden /> Customer journey (demo)</Button>
            </a>
            <span className="rounded-full bg-white/10 px-2.5 py-1 text-white ring-1 ring-white/20" data-testid="whoami">{me.username} · {ROLE_LABEL[me.role]}</span>
            {canReset && <Button variant="dark" size="sm" onClick={reset} loading={resetting}><RotateCcw className="size-3.5" aria-hidden /> Reset demo data</Button>}
            <Button variant="dark" size="sm" onClick={onSignOut}><LogOut className="size-3.5" aria-hidden /> Sign out</Button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 px-4 sm:px-6" aria-label="Console sections">
          {tabs.map((t) => (
            <button key={t.id} type="button" onClick={() => setTab(t.id)} aria-current={activeTab === t.id ? 'page' : undefined}
              className={cn('flex items-center gap-2 rounded-t-xl px-4 py-2.5 text-sm font-medium transition',
                activeTab === t.id ? 'bg-[#f4f8fc] text-indigo-900' : 'text-indigo-100/80 hover:bg-white/10 hover:text-white')}>
              <t.icon className="size-4" aria-hidden /> {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {activeTab === 'agents' && <AgentsView overview={overview} />}
        {activeTab === 'claims' && (
          <ClaimsView me={me} overview={overview} claims={claims} client={client} selected={selected} onSelect={setSelected} />
        )}
      </main>
    </div>
  )
}
