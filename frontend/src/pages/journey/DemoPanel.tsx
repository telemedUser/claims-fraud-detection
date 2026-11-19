import { useState } from 'react'
import { ChevronDown, FlaskConical, LoaderCircle, Search } from 'lucide-react'
import type { DemoKind } from '../../api'
import { Card } from '../../components/ui'
import { cn } from '../../lib/utils'
import { SCENARIO_GROUPS, SCENARIOS } from './demoScenarios'

/** Demo mode only: one-click scenarios that prefill the journey with a generated case and its documents. */
export default function DemoPanel({ loading, loaded, onPick }: { loading: DemoKind | null; loaded: DemoKind | null; onPick: (k: DemoKind) => void }) {
  const [open, setOpen] = useState(true)
  const current = SCENARIOS.find((s) => s.kind === loaded)
  return (
    <Card className="mb-6 overflow-hidden ring-indigo-200">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center gap-3 bg-indigo-50 px-4 py-3 text-left">
        <FlaskConical className="size-4 shrink-0 text-indigo-700" aria-hidden />
        <span className="flex-1 text-sm text-indigo-950">
          <b>Demo scenarios.</b> Pick one to prefill the claim and its documents, then submit.
        </span>
        <ChevronDown className={cn('size-4 shrink-0 text-indigo-600 transition', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div className="space-y-4 p-4">
          {SCENARIO_GROUPS.map((g) => (
            <div key={g.label}>
              <div className="mb-2 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">{g.label}</div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {g.items.map((s) => (
                  <button key={s.kind} type="button" disabled={loading !== null} onClick={() => onPick(s.kind)} title={s.look}
                    className={cn('flex items-start justify-between gap-2 rounded-md bg-white px-3 py-2.5 text-left ring-1 transition',
                      'hover:bg-indigo-50 hover:ring-indigo-300 focus-visible:outline-2 focus-visible:outline-indigo-600 disabled:cursor-wait disabled:opacity-60',
                      loaded === s.kind ? 'ring-2 ring-indigo-600' : 'ring-slate-200')}>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-slate-900">{s.title}</span>
                      <span className="block text-xs text-slate-500">{s.agent}</span>
                    </span>
                    {loading === s.kind && <LoaderCircle className="size-4 shrink-0 animate-spin text-indigo-600" aria-label="Loading" />}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {current && (
        <div className="flex items-start gap-2 border-t border-indigo-100 bg-white px-4 py-3 text-sm text-slate-700">
          <Search className="mt-0.5 size-4 shrink-0 text-indigo-600" aria-hidden />
          <span><b className="text-slate-900">Loaded: {current.title}.</b> What to look for: {current.look}</span>
        </div>
      )}
    </Card>
  )
}
