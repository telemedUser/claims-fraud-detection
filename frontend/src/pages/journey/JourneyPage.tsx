import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowLeft, ArrowRight, FlaskConical, Send } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Alert, Button, Card } from '../../components/ui'
import { cn, uid } from '../../lib/utils'
import { initialState, STEPS, toClaimForm, toDocuments, validate, type JourneyState } from './state'
import PolicyStep from './PolicyStep'
import TreatmentStep from './TreatmentStep'
import BillStep from './BillStep'
import DocumentsStep from './DocumentsStep'
import ReviewStep from './ReviewStep'

export default function JourneyPage() {
  const [state, setState] = useState<JourneyState>(initialState)
  const [step, setStep] = useState(0)
  const [showErrors, setShowErrors] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demoLoading, setDemoLoading] = useState<string | null>(null)
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const demoMode = params.get('demo') === '1'

  const update = (patch: Partial<JourneyState>) => setState((s) => ({ ...s, ...patch }))
  const errors = validate(step, state)
  const valid = Object.keys(errors).length === 0

  const goTo = (i: number) => {
    setShowErrors(false)
    setError(null)
    setStep(i)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const next = () => {
    if (!valid) return setShowErrors(true)
    goTo(step + 1)
  }

  const submit = async () => {
    if (!valid) return setShowErrors(true)
    setSubmitting(true)
    setError(null)
    try {
      const { claim_id } = await api.submitClaim(toClaimForm(state), toDocuments(state))
      navigate(`/claims/${claim_id}/processing`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Submission failed. Please try again.')
      setSubmitting(false)
    }
  }

  const fillDemo = async (kind: 'clean' | 'suspicious') => {
    setDemoLoading(kind)
    setError(null)
    try {
      const demo = await api.demo(kind)
      const f = demo.form
      const [policy, files] = await Promise.all([
        api.lookupPolicy(f.policy_number, f.date_of_birth),
        Promise.all(demo.documents.map(async (d) => [d.doc_type, await api.demoFile(d.url, d.filename)] as const)),
      ])
      const docs = { ...initialState.docs }
      files.forEach(([t, file]) => {
        if (t !== 'other') docs[t] = file
      })
      setState({
        ...initialState,
        policyNumber: f.policy_number,
        dob: f.date_of_birth,
        policy,
        hospitalId: f.hospital_id,
        doctorId: f.doctor_id,
        diseaseId: f.disease_id,
        admission: f.admission_date,
        discharge: f.discharge_date,
        invoiceNumber: f.invoice.invoice_number,
        billDate: f.invoice.invoice_date,
        taxId: f.invoice.tax_id ?? '',
        items: f.invoice.line_items.map((li) => ({ id: uid(), description: li.description, amount: String(li.amount) })),
        claimedAmount: String(f.claimed_amount),
        claimedTouched: true,
        docs,
      })
      goTo(4)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load demo data.')
    } finally {
      setDemoLoading(null)
    }
  }

  const StepView = [PolicyStep, TreatmentStep, BillStep, DocumentsStep, ReviewStep][step]

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-indigo-600">Submit a reimbursement claim</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Takes about 5 minutes. Keep your policy number, hospital bill and discharge summary handy.
        </p>
      </div>

      {demoMode && (
        <Card className="mb-6 flex flex-col gap-3 border-dashed p-4 ring-amber-300 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-sm text-amber-900">
            <FlaskConical className="size-4" aria-hidden />
            <span>
              <b>Demo mode.</b> Prefill the journey with a generated test case and its documents.
            </span>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="secondary" loading={demoLoading === 'clean'} onClick={() => fillDemo('clean')}>
              Genuine claim
            </Button>
            <Button size="sm" variant="secondary" loading={demoLoading === 'suspicious'} onClick={() => fillDemo('suspicious')}>
              Suspicious claim
            </Button>
          </div>
        </Card>
      )}

      <Stepper step={step} onSelect={(i) => i < step && goTo(i)} />

      <Card className="mt-6 overflow-hidden px-4 sm:px-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="py-5 sm:py-6"
          >
            <StepView state={state} update={update} showErrors={showErrors} goTo={goTo} />
          </motion.div>
        </AnimatePresence>

        {error && (
          <div className="pb-2">
            <Alert>{error}</Alert>
          </div>
        )}

        <div className="flex items-center justify-between gap-3 py-6">
          <Button variant="secondary" onClick={() => goTo(step - 1)} disabled={step === 0 || submitting}>
            <ArrowLeft className="size-4" aria-hidden /> Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={next}>
              Next <ArrowRight className="size-4" aria-hidden />
            </Button>
          ) : (
            <Button onClick={submit} loading={submitting}>
              <Send className="size-4" aria-hidden /> Submit claim
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

function Stepper({ step, onSelect }: { step: number; onSelect: (i: number) => void }) {
  return (
    <nav aria-label="Progress">
      <ol className="flex overflow-x-auto bg-slate-100 text-sm">
        {STEPS.map((label, i) => {
          const done = i < step
          const current = i === step
          return (
            <li key={label} className="flex">
              <button
                type="button"
                onClick={() => onSelect(i)}
                disabled={!done}
                aria-current={current ? 'step' : undefined}
                className={cn(
                  'flex h-10 items-center gap-1.5 px-4 font-semibold whitespace-nowrap',
                  current && 'bg-indigo-600 text-white',
                  done && 'cursor-pointer text-indigo-700 hover:underline',
                  !done && !current && 'text-slate-600',
                )}
              >
                <span>{i + 1}</span>
                {label}
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}