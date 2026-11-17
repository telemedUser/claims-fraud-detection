import { useMemo, useState } from 'react'
import { Ban, Building2, Check, ChevronDown, HeartPulse, MapPin, Search, ShieldCheck, Stethoscope } from 'lucide-react'
import { Alert, Field, Input } from '../../components/ui'
import { cn, daysBetween, todayIso } from '../../lib/utils'
import { StepTitle } from './PolicyStep'
import { validate, type StepProps } from './state'

export default function TreatmentStep({ state, update, showErrors }: StepProps) {
  const p = state.policy!
  const [query, setQuery] = useState('')
  const [showExcluded, setShowExcluded] = useState(false)
  const err = (k: string) => (showErrors ? errorsFor(state)[k] : undefined)

  const hospitals = useMemo(() => {
    const q = query.trim().toLowerCase()
    return p.network_hospitals.filter((h) => !q || `${h.name} ${h.city} ${h.specialties.join(' ')}`.toLowerCase().includes(q))
  }, [p, query])
  const hospital = p.network_hospitals.find((h) => h.id === state.hospitalId)
  const stay = state.admission && state.discharge && state.discharge >= state.admission ? daysBetween(state.admission, state.discharge) : null

  return (
    <div className="space-y-8">
      <StepTitle title="Hospital and treatment" subtitle="Only hospitals in your policy network and conditions your plan covers are shown." />

      {/* Hospitals */}
      <section aria-labelledby="hosp-h">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 id="hosp-h" className="flex items-center gap-2 font-medium text-slate-900">
              <Building2 className="size-4 text-indigo-600" aria-hidden /> Network hospital
            </h3>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-emerald-700">
              <ShieldCheck className="size-3.5" aria-hidden /> Whitelisted for {p.plan}
            </p>
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <Input aria-label="Search hospitals" placeholder="Search name or city" value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" />
          </div>
        </div>
        <div role="radiogroup" aria-label="Network hospital" className="grid gap-3 sm:grid-cols-2">
          {hospitals.map((h) => {
            const selected = h.id === state.hospitalId
            return (
              <button
                key={h.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => update({ hospitalId: h.id, doctorId: h.id === state.hospitalId ? state.doctorId : '' })}
                className={cn(
                  'relative rounded-xl p-4 text-left ring-1 transition',
                  selected ? 'bg-indigo-50/60 ring-2 ring-indigo-600' : 'bg-white ring-slate-200 hover:ring-slate-300',
                )}
              >
                {selected && (
                  <span className="absolute top-3 right-3 grid size-5 place-items-center rounded-full bg-indigo-600 text-white">
                    <Check className="size-3" aria-hidden />
                  </span>
                )}
                <div className="pr-6 font-medium text-slate-900">{h.name}</div>
                <div className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
                  <MapPin className="size-3" aria-hidden /> {h.address}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {h.specialties.map((s) => (
                    <span key={s} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                      {s}
                    </span>
                  ))}
                </div>
              </button>
            )
          })}
          {hospitals.length === 0 && <p className="text-sm text-slate-500">No network hospital matches “{query}”.</p>}
        </div>
        {err('hospital') && <p className="mt-2 text-xs text-rose-600">{err('hospital')}</p>}
      </section>

      {/* Doctor */}
      {hospital && (
        <section aria-labelledby="doc-h">
          <h3 id="doc-h" className="mb-3 flex items-center gap-2 font-medium text-slate-900">
            <Stethoscope className="size-4 text-indigo-600" aria-hidden /> Treating doctor at {hospital.name}
          </h3>
          <div role="radiogroup" aria-label="Treating doctor" className="grid gap-2 sm:grid-cols-3">
            {hospital.doctors.map((d) => (
              <button
                key={d.id}
                type="button"
                role="radio"
                aria-checked={d.id === state.doctorId}
                onClick={() => update({ doctorId: d.id })}
                className={cn(
                  'rounded-xl px-3 py-2.5 text-left ring-1 transition',
                  d.id === state.doctorId ? 'bg-indigo-50/60 ring-2 ring-indigo-600' : 'ring-slate-200 hover:ring-slate-300',
                )}
              >
                <div className="text-sm font-medium text-slate-900">{d.name}</div>
                <div className="text-xs text-slate-500">
                  {d.specialty} · {d.qualification}
                </div>
              </button>
            ))}
          </div>
          {err('doctor') && <p className="mt-2 text-xs text-rose-600">{err('doctor')}</p>}
        </section>
      )}

      {/* Diseases */}
      <section aria-labelledby="dz-h">
        <h3 id="dz-h" className="mb-3 flex items-center gap-2 font-medium text-slate-900">
          <HeartPulse className="size-4 text-indigo-600" aria-hidden /> Condition treated
        </h3>
        <div role="radiogroup" aria-label="Covered condition" className="flex flex-wrap gap-2">
          {p.covered_diseases.map((d) => (
            <button
              key={d.id}
              type="button"
              role="radio"
              aria-checked={d.id === state.diseaseId}
              onClick={() => update({ diseaseId: d.id })}
              className={cn(
                'rounded-full px-3.5 py-1.5 text-sm ring-1 transition',
                d.id === state.diseaseId ? 'bg-indigo-600 text-white ring-indigo-600' : 'bg-white text-slate-700 ring-slate-300 hover:ring-slate-400',
              )}
            >
              {d.name}
              <span className={cn('ml-1.5 text-xs', d.id === state.diseaseId ? 'text-indigo-100' : 'text-slate-400')}>{d.category}</span>
            </button>
          ))}
        </div>
        {err('disease') && <p className="mt-2 text-xs text-rose-600">{err('disease')}</p>}
        {p.not_covered.length > 0 && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowExcluded((v) => !v)}
              aria-expanded={showExcluded}
              className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700"
            >
              <ChevronDown className={cn('size-3.5 transition-transform', showExcluded && 'rotate-180')} aria-hidden />
              Not covered by your plan ({p.not_covered.length})
            </button>
            {showExcluded && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {p.not_covered.map((d) => (
                  <li key={d.id} className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500 line-through decoration-slate-300">
                    <Ban className="size-3 no-underline" aria-hidden /> {d.name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Dates */}
      <section className="grid gap-4 sm:grid-cols-3">
        <Field label="Admission date" htmlFor="adm" error={err('admission')}>
          <Input id="adm" type="date" value={state.admission} min={p.valid_from} max={todayIso()} invalid={!!err('admission')}
            onChange={(e) => update({ admission: e.target.value })} />
        </Field>
        <Field label="Discharge date" htmlFor="dis" error={err('discharge')}>
          <Input id="dis" type="date" value={state.discharge} min={state.admission || p.valid_from} max={todayIso()} invalid={!!err('discharge')}
            onChange={(e) => update({ discharge: e.target.value })} />
        </Field>
        <div className="flex items-end pb-1">
          {stay != null && (
            <Alert tone="indigo" className="w-full py-2">
              Length of stay: <b>{stay === 0 ? 'Day care' : `${stay} night${stay > 1 ? 's' : ''}`}</b>
            </Alert>
          )}
        </div>
      </section>
    </div>
  )
}

// Same validation the page uses, so this step can show inline errors.
const errorsFor = (s: StepProps['state']) => validate(1, s)
