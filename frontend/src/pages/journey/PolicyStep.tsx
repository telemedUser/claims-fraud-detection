import { useState, type FormEvent, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { BadgeCheck, CalendarRange, Search, ShieldCheck, UserRound, Wallet } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Alert, Button, Field, Input } from '../../components/ui'
import { fmtDate, inr } from '../../lib/utils'
import { initialState, type StepProps } from './state'

export default function PolicyStep({ state, update, showErrors }: StepProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const p = state.policy

  const lookup = async (e: FormEvent) => {
    e.preventDefault()
    if (!state.policyNumber.trim() || !state.dob) return setError('Enter your policy number and date of birth.')
    setLoading(true)
    setError(null)
    try {
      const policy = await api.lookupPolicy(state.policyNumber.trim(), state.dob)
      // A different policy invalidates everything chosen downstream.
      update({ ...initialState, policyNumber: state.policyNumber, dob: state.dob, policy })
    } catch (err) {
      update({ policy: null })
      setError(err instanceof ApiError ? err.message : 'Lookup failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <StepTitle title="Find your policy" subtitle="We use your policy to show the hospitals and treatments it covers." />
      <form onSubmit={lookup} className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label="Policy number" htmlFor="policy" hint="Printed on your health card, e.g. POL-1001">
          <Input
            id="policy"
            value={state.policyNumber}
            onChange={(e) => update({ policyNumber: e.target.value.toUpperCase(), policy: null })}
            placeholder="POL-0000"
            autoComplete="off"
          />
        </Field>
        <Field label="Policyholder date of birth" htmlFor="dob" hint="Used to verify it's you">
          <Input id="dob" type="date" value={state.dob} onChange={(e) => update({ dob: e.target.value, policy: null })} />
        </Field>
        <Button type="submit" loading={loading} className="sm:mb-5">
          <Search className="size-4" aria-hidden /> Find policy
        </Button>
      </form>

      {error && <Alert className="mt-4">{error}</Alert>}
      {showErrors && !p && !error && <Alert className="mt-4">Find your policy to continue.</Alert>}

      {p && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-6 overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-600 via-indigo-600 to-violet-700 p-6 text-white shadow-lg shadow-indigo-600/20"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm text-indigo-100">
                <BadgeCheck className="size-4" aria-hidden /> Policy verified
              </div>
              <div className="mt-1 text-2xl font-semibold">{p.plan}</div>
              <div className="text-sm text-indigo-100">{p.policy_number}</div>
            </div>
            <ShieldCheck className="size-10 text-white/30" aria-hidden />
          </div>
          <dl className="mt-6 grid gap-4 sm:grid-cols-3">
            <Info icon={<UserRound className="size-4" />} label="Policyholder" value={p.holder_name} />
            <Info icon={<Wallet className="size-4" />} label="Sum insured" value={inr(p.sum_insured)} />
            <Info icon={<CalendarRange className="size-4" />} label="Valid" value={`${fmtDate(p.valid_from)} – ${fmtDate(p.valid_to)}`} />
          </dl>
          <div className="mt-5 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-white/15 px-2.5 py-1">{p.network_hospitals.length} network hospitals</span>
            <span className="rounded-full bg-white/15 px-2.5 py-1">{p.covered_diseases.length} covered conditions</span>
          </div>
        </motion.div>
      )}
    </div>
  )
}

function Info({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-xs text-indigo-100">
        {icon}
        {label}
      </dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
    </div>
  )
}

export function StepTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
    </div>
  )
}
