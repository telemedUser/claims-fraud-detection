import type { ReactNode } from 'react'
import { FileText, Pencil } from 'lucide-react'
import { cn, DOC_LABEL, fileSize, fmtDate, inr } from '../../lib/utils'
import { StepTitle } from './PolicyStep'
import { billTotal, toDocuments, validate, type StepProps } from './state'

export default function ReviewStep({ state, update, showErrors, goTo }: StepProps) {
  const p = state.policy!
  const hospital = p.network_hospitals.find((h) => h.id === state.hospitalId)
  const doctor = hospital?.doctors.find((d) => d.id === state.doctorId)
  const disease = p.covered_diseases.find((d) => d.id === state.diseaseId)
  const docs = toDocuments(state)
  const errors = showErrors ? validate(4, state) : {}

  return (
    <div className="space-y-5">
      <StepTitle title="Review and submit" subtitle="Check everything is correct. Once submitted, your claim is verified automatically." />

      <Section title="Policy" onEdit={() => goTo?.(0)}>
        <Row k="Policyholder" v={p.holder_name} />
        <Row k="Policy" v={`${p.plan} · ${p.policy_number}`} />
      </Section>

      <Section title="Hospital and treatment" onEdit={() => goTo?.(1)}>
        <Row k="Hospital" v={hospital ? `${hospital.name}, ${hospital.city}` : '—'} />
        <Row k="Doctor" v={doctor ? `${doctor.name} (${doctor.specialty})` : '—'} />
        <Row k="Condition" v={disease?.name ?? '—'} />
        <Row k="Stay" v={`${fmtDate(state.admission)} → ${fmtDate(state.discharge)}`} />
      </Section>

      <Section title="Bill" onEdit={() => goTo?.(2)}>
        <Row k="Bill number" v={state.invoiceNumber} />
        <Row k="Bill date" v={fmtDate(state.billDate)} />
        <Row k="Items" v={`${state.items.length} item${state.items.length > 1 ? 's' : ''} · total ${inr(billTotal(state.items))}`} />
        <Row k="Claimed amount" v={<span className="text-base font-semibold text-slate-900">{inr(Number(state.claimedAmount))}</span>} />
      </Section>

      <Section title={`Documents (${docs.length})`} onEdit={() => goTo?.(3)}>
        <ul className="grid gap-2 sm:col-span-2 sm:grid-cols-2">
          {docs.map((d, i) => (
            <li key={i} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <FileText className="size-4 shrink-0 text-indigo-600" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-slate-800">{d.file.name}</span>
                <span className="text-xs text-slate-500">
                  {DOC_LABEL[d.docType]} · {fileSize(d.file.size)}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <label className={cn('flex cursor-pointer items-start gap-3 rounded-xl p-4 ring-1', errors.consent ? 'bg-rose-50 ring-rose-300' : 'bg-indigo-50/50 ring-indigo-200')}>
        <input type="checkbox" checked={state.consent} onChange={(e) => update({ consent: e.target.checked })}
          className="mt-0.5 size-4 rounded border-slate-300 accent-indigo-600" />
        <span className="text-sm text-slate-700">
          I declare that the information and documents provided are true and complete, and I authorise Assure Health to verify them with the
          hospital and treating doctor.
        </span>
      </label>
      {errors.consent && <p className="-mt-3 text-xs text-rose-600">{errors.consent}</p>}
    </div>
  )
}

function Section({ title, onEdit, children }: { title: string; onEdit: () => void; children: ReactNode }) {
  return (
    <section className="rounded-xl p-4 ring-1 ring-slate-200">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <button type="button" onClick={onEdit} className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800">
          <Pencil className="size-3" aria-hidden /> Edit
        </button>
      </div>
      <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">{children}</dl>
    </section>
  )
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-sm sm:block">
      <dt className="text-slate-500">{k}</dt>
      <dd className="text-right font-medium text-slate-800 sm:text-left">{v}</dd>
    </div>
  )
}
