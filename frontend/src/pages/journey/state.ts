import type { ClaimForm, DocType, Policy } from '../../api'
import { todayIso, uid } from '../../lib/utils'

export type RequiredDoc = Exclude<DocType, 'other'>
export type ItemRow = { id: string; description: string; amount: string }

export type JourneyState = {
  policyNumber: string
  dob: string
  policy: Policy | null
  hospitalId: string
  doctorId: string
  diseaseId: string
  admission: string
  discharge: string
  invoiceNumber: string
  billDate: string
  taxId: string
  items: ItemRow[]
  claimedAmount: string
  claimedTouched: boolean
  docs: Record<RequiredDoc, File | null>
  others: File[]
  consent: boolean
}

export const emptyItem = (): ItemRow => ({ id: uid(), description: '', amount: '' })

export const initialState: JourneyState = {
  policyNumber: '',
  dob: '',
  policy: null,
  hospitalId: '',
  doctorId: '',
  diseaseId: '',
  admission: '',
  discharge: '',
  invoiceNumber: '',
  billDate: '',
  taxId: '',
  items: [emptyItem()],
  claimedAmount: '',
  claimedTouched: false,
  docs: { medical_bill: null, medical_report: null, prescription: null, lab_report: null, payment_receipt: null },
  others: [],
  consent: false,
}

export type StepProps = {
  state: JourneyState
  update: (patch: Partial<JourneyState>) => void
  showErrors: boolean
  goTo?: (step: number) => void
}

export const STEPS = ['Policy', 'Hospital & treatment', 'Bill details', 'Documents', 'Review & submit'] as const

export const billTotal = (items: ItemRow[]) => items.reduce((s, i) => s + (Number(i.amount) || 0), 0)

export function validate(step: number, s: JourneyState): Record<string, string> {
  const e: Record<string, string> = {}
  const p = s.policy
  if (step === 0) {
    if (!p) e.policy = 'Find your policy to continue.'
  }
  if (step === 1 && p) {
    if (!s.hospitalId) e.hospital = 'Choose the hospital where you were treated.'
    if (s.hospitalId && !s.doctorId) e.doctor = 'Choose your treating doctor.'
    if (!s.diseaseId) e.disease = 'Choose the condition you were treated for.'
    if (!s.admission) e.admission = 'Enter the admission date.'
    if (!s.discharge) e.discharge = 'Enter the discharge date.'
    if (s.admission && s.discharge && s.discharge < s.admission) e.discharge = 'Discharge must be on or after admission.'
    if (s.discharge && s.discharge > todayIso()) e.discharge = 'Discharge date cannot be in the future.'
    if (s.admission && (s.admission < p.valid_from || s.admission > p.valid_to))
      e.admission = 'Admission date is outside your policy period.'
  }
  if (step === 2 && p) {
    if (!s.invoiceNumber.trim()) e.invoiceNumber = 'Enter the bill number printed on your hospital bill.'
    if (!s.billDate) e.billDate = 'Enter the bill date.'
    if (s.items.length === 0) e.items = 'Add at least one bill item.'
    s.items.forEach((i) => {
      if (!i.description.trim()) e[`item-${i.id}-d`] = 'Required'
      if (!(Number(i.amount) > 0)) e[`item-${i.id}-a`] = 'Enter an amount'
    })
    const claimed = Number(s.claimedAmount)
    if (!(claimed > 0)) e.claimed = 'Enter the amount you are claiming.'
    else if (claimed > p.sum_insured) e.claimed = 'This is more than your sum insured.'
  }
  if (step === 3) {
    if (!s.docs.medical_bill) e.medical_bill = 'The itemised hospital bill is required.'
    if (!s.docs.medical_report) e.medical_report = 'A medical report or discharge summary is required.'
  }
  if (step === 4) {
    if (!s.consent) e.consent = 'Please confirm the declaration to submit.'
  }
  return e
}

export function toClaimForm(s: JourneyState): ClaimForm {
  return {
    policy_number: s.policy!.policy_number,
    date_of_birth: s.dob,
    hospital_id: s.hospitalId,
    doctor_id: s.doctorId,
    disease_id: s.diseaseId,
    admission_date: s.admission,
    discharge_date: s.discharge,
    claimed_amount: Number(s.claimedAmount),
    invoice: {
      invoice_number: s.invoiceNumber.trim(),
      invoice_date: s.billDate,
      line_items: s.items.map((i) => ({ description: i.description.trim(), amount: Number(i.amount) })),
      total: billTotal(s.items),
      tax_id: s.taxId.trim() || null,
    },
  }
}

export function toDocuments(s: JourneyState): { file: File; docType: DocType }[] {
  const out: { file: File; docType: DocType }[] = []
  ;(Object.keys(s.docs) as RequiredDoc[]).forEach((t) => {
    const f = s.docs[t]
    if (f) out.push({ file: f, docType: t })
  })
  s.others.forEach((f) => out.push({ file: f, docType: 'other' }))
  return out
}
