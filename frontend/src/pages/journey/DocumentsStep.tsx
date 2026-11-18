import { useRef, useState, type DragEvent } from 'react'
import { CloudUpload, FileCheck2, FilePlus2, FileText, Pill, Receipt, X } from 'lucide-react'
import { Button } from '../../components/ui'
import { cn, fileSize } from '../../lib/utils'
import { StepTitle } from './PolicyStep'
import { validate, type RequiredDoc, type StepProps } from './state'

const ACCEPT = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
const ALLOWED = ['application/pdf', 'image/jpeg', 'image/png']
const MAX = 10 * 1024 * 1024

function check(f: File): string | null {
  if (!ALLOWED.includes(f.type)) return 'Upload a PDF, JPG or PNG file.'
  if (f.size > MAX) return 'Files must be 10 MB or smaller.'
  return null
}

const SLOTS: { key: RequiredDoc; title: string; desc: string; required: boolean; icon: typeof Receipt }[] = [
  { key: 'medical_bill', title: 'Final hospital bill', desc: 'Itemised bill with bill number and hospital stamp', required: true, icon: Receipt },
  { key: 'medical_report', title: 'Medical report / discharge summary', desc: 'Diagnosis, treatment and discharge notes', required: true, icon: FileText },
  { key: 'prescription', title: 'Prescription', desc: 'Doctor’s prescription for the treatment', required: false, icon: Pill },
  { key: 'lab_report', title: 'Lab report', desc: 'Test results with the lab report number', required: false, icon: FileText },
  { key: 'payment_receipt', title: 'Payment receipt', desc: 'Proof you paid the hospital, if not on the bill', required: false, icon: Receipt },
]

export default function DocumentsStep({ state, update, showErrors }: StepProps) {
  const errors = showErrors ? validate(3, state) : {}
  return (
    <div className="space-y-6">
      <StepTitle title="Upload documents" subtitle="Clear scans or the original PDFs from the hospital. PDF, JPG or PNG up to 10 MB each." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {SLOTS.map(({ key: slot, ...s }) => (
          <DropSlot
            key={slot}
            {...s}
            file={state.docs[slot]}
            error={errors[slot]}
            onFile={(f) => update({ docs: { ...state.docs, [slot]: f } })}
          />
        ))}
      </div>
      <OtherDocs files={state.others} onChange={(others) => update({ others })} />
    </div>
  )
}

function useDrop(onFiles: (files: File[]) => void) {
  const [over, setOver] = useState(false)
  return {
    over,
    props: {
      onDragOver: (e: DragEvent) => {
        e.preventDefault()
        setOver(true)
      },
      onDragLeave: () => setOver(false),
      onDrop: (e: DragEvent) => {
        e.preventDefault()
        setOver(false)
        onFiles(Array.from(e.dataTransfer.files))
      },
    },
  }
}

function DropSlot({ title, desc, required, icon: Icon, file, error, onFile }: {
  title: string; desc: string; required: boolean; icon: typeof Receipt; file: File | null; error?: string; onFile: (f: File | null) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const take = (files: File[]) => {
    const f = files[0]
    if (!f) return
    const e = check(f)
    setLocalError(e)
    if (!e) onFile(f)
  }
  const drop = useDrop(take)
  const shown = localError || error

  return (
    <div>
      <div
        {...drop.props}
        className={cn(
          'relative flex h-full min-h-44 flex-col rounded-xl border-2 border-dashed p-4 transition',
          file ? 'border-emerald-300 bg-emerald-50/50' : drop.over ? 'border-indigo-500 bg-indigo-50' : shown ? 'border-rose-300 bg-rose-50/40' : 'border-slate-300 bg-white',
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <Icon className={cn('size-5', file ? 'text-emerald-600' : 'text-indigo-600')} aria-hidden />
          <span className={cn('text-[11px] font-medium', required ? 'text-rose-600' : 'text-slate-400')}>{required ? 'Required' : 'Optional'}</span>
        </div>
        <div className="mt-2 text-sm font-medium text-slate-900">{title}</div>
        <div className="text-xs text-slate-500">{desc}</div>
        <div className="mt-auto pt-3">
          {file ? (
            <div className="flex items-center gap-2 rounded-lg bg-white px-2.5 py-2 ring-1 ring-emerald-200">
              <FileCheck2 className="size-4 shrink-0 text-emerald-600" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-slate-800">{file.name}</div>
                <div className="text-[11px] text-slate-500">{fileSize(file.size)}</div>
              </div>
              <button type="button" aria-label={`Remove ${file.name}`} onClick={() => onFile(null)} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          ) : (
            <Button variant="secondary" size="sm" className="w-full" onClick={() => input.current?.click()}>
              <CloudUpload className="size-4" aria-hidden /> Choose or drop file
            </Button>
          )}
        </div>
        <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label={title} tabIndex={-1}
          onChange={(e) => {
            take(Array.from(e.target.files ?? []))
            e.target.value = ''
          }} />
      </div>
      {shown && <p className="mt-1.5 text-xs text-rose-600" role="alert">{shown}</p>}
    </div>
  )
}

function OtherDocs({ files, onChange }: { files: File[]; onChange: (f: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const add = (incoming: File[]) => {
    const bad = incoming.map(check).find(Boolean)
    setError(bad ?? null)
    const ok = incoming.filter((f) => !check(f))
    onChange([...files, ...ok].slice(0, 5))
  }
  const drop = useDrop(add)
  return (
    <div {...drop.props} className={cn('rounded-xl p-4 ring-1 transition', drop.over ? 'bg-indigo-50 ring-indigo-400' : 'bg-slate-50 ring-slate-200')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-900">Other supporting documents</div>
          <div className="text-xs text-slate-500">Lab reports, pharmacy bills, etc. Up to 5 files.</div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => input.current?.click()} disabled={files.length >= 5}>
          <FilePlus2 className="size-4" aria-hidden /> Add files
        </Button>
      </div>
      {files.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-1.5 rounded-lg bg-white py-1 pr-1 pl-2.5 text-xs ring-1 ring-slate-200">
              {f.name} <span className="text-slate-400">{fileSize(f.size)}</span>
              <button type="button" aria-label={`Remove ${f.name}`} onClick={() => onChange(files.filter((_, j) => j !== i))} className="rounded p-0.5 text-slate-400 hover:text-slate-700">
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="mt-2 text-xs text-rose-600" role="alert">{error}</p>}
      <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" aria-label="Other supporting documents" tabIndex={-1}
        onChange={(e) => {
          add(Array.from(e.target.files ?? []))
          e.target.value = ''
        }} />
    </div>
  )
}
