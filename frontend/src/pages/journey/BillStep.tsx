import { Info, Plus, Receipt, Trash2 } from 'lucide-react'
import { Alert, Button, Field, Input } from '../../components/ui'
import { inr, todayIso } from '../../lib/utils'
import { StepTitle } from './PolicyStep'
import { billTotal, emptyItem, validate, type ItemRow, type StepProps } from './state'

export default function BillStep({ state, update, showErrors }: StepProps) {
  const p = state.policy!
  const errors = showErrors ? validate(2, state) : {}
  const total = billTotal(state.items)
  const claimed = Number(state.claimedAmount)

  const setItems = (items: ItemRow[]) => {
    const t = billTotal(items)
    update({ items, ...(state.claimedTouched ? {} : { claimedAmount: t ? String(t) : '' }) })
  }
  const setItem = (id: string, patch: Partial<ItemRow>) => setItems(state.items.map((i) => (i.id === id ? { ...i, ...patch } : i)))

  return (
    <div className="space-y-8">
      <StepTitle title="Bill details" subtitle="Copy these from your final hospital bill. We check them against the documents you upload." />

      <section className="grid gap-4 sm:grid-cols-3">
        <Field label="Bill / invoice number" htmlFor="inv" error={errors.invoiceNumber}>
          <Input id="inv" value={state.invoiceNumber} invalid={!!errors.invoiceNumber} placeholder="e.g. INV-12345"
            onChange={(e) => update({ invoiceNumber: e.target.value })} />
        </Field>
        <Field label="Bill date" htmlFor="billdate" error={errors.billDate}>
          <Input id="billdate" type="date" value={state.billDate} max={todayIso()} invalid={!!errors.billDate}
            onChange={(e) => update({ billDate: e.target.value })} />
        </Field>
        <Field label="Hospital GSTIN (optional)" htmlFor="gstin" hint="Printed in the bill header">
          <Input id="gstin" value={state.taxId} placeholder="e.g. 27AAACC1111A1Z5" onChange={(e) => update({ taxId: e.target.value.toUpperCase() })} />
        </Field>
      </section>

      <section aria-labelledby="items-h">
        <h3 id="items-h" className="mb-3 flex items-center gap-2 font-medium text-slate-900">
          <Receipt className="size-4 text-indigo-600" aria-hidden /> Itemised charges
        </h3>
        <div className="overflow-hidden rounded-xl ring-1 ring-slate-200">
          <div className="grid grid-cols-[1fr_9rem_2.5rem] gap-3 bg-slate-50 px-4 py-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
            <span>Description</span>
            <span className="text-right">Amount (INR)</span>
            <span className="sr-only">Remove</span>
          </div>
          <ul className="divide-y divide-slate-100">
            {state.items.map((i, idx) => (
              <li key={i.id} className="grid grid-cols-[1fr_9rem_2.5rem] items-start gap-3 px-4 py-2.5">
                <div>
                  <Input aria-label={`Item ${idx + 1} description`} value={i.description} placeholder="e.g. Room charges"
                    invalid={!!errors[`item-${i.id}-d`]} onChange={(e) => setItem(i.id, { description: e.target.value })} />
                </div>
                <div>
                  <Input aria-label={`Item ${idx + 1} amount`} type="number" min={0} step="0.01" inputMode="decimal" value={i.amount}
                    placeholder="0" className="text-right" invalid={!!errors[`item-${i.id}-a`]}
                    onChange={(e) => setItem(i.id, { amount: e.target.value })} />
                </div>
                <Button variant="ghost" size="sm" className="mt-1 px-2" aria-label={`Remove item ${idx + 1}`}
                  disabled={state.items.length === 1} onClick={() => setItems(state.items.filter((x) => x.id !== i.id))}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/60 px-4 py-3">
            <Button variant="secondary" size="sm" onClick={() => setItems([...state.items, emptyItem()])}>
              <Plus className="size-4" aria-hidden /> Add item
            </Button>
            <div className="text-sm text-slate-600">
              Bill total <span className="ml-2 text-lg font-semibold text-slate-900">{inr(total)}</span>
            </div>
          </div>
        </div>
        {errors.items && <p className="mt-2 text-xs text-rose-600">{errors.items}</p>}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount you are claiming" htmlFor="claimed" error={errors.claimed} hint={`Sum insured: ${inr(p.sum_insured)}`}>
          <Input id="claimed" type="number" min={0} step="0.01" inputMode="decimal" value={state.claimedAmount} invalid={!!errors.claimed}
            onChange={(e) => update({ claimedAmount: e.target.value, claimedTouched: true })} />
        </Field>
        {claimed > 0 && total > 0 && Math.abs(claimed - total) > 1 && (
          <div className="flex items-end">
            <Alert tone="amber" className="flex w-full items-start gap-2">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              Claimed amount differs from your bill total by {inr(Math.abs(claimed - total))}. Claims are normally for the billed amount.
            </Alert>
          </div>
        )}
      </section>
    </div>
  )
}
