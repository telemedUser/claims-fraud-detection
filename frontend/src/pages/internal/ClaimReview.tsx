import { useEffect, useRef, useState } from 'react'
import { CircleCheck, CircleX, Download, Eye, FileText, Gavel, X } from 'lucide-react'
import { ApiError, type HumanDecision, type InternalDetail, type internalApi, type Me, type Review } from '../../api'
import { Alert, Badge, Button, Spinner } from '../../components/ui'
import { cn, DOC_LABEL, fileSize, fmtDateTime } from '../../lib/utils'
import { Panel } from './common'

type Client = ReturnType<typeof internalApi>
type Doc = InternalDetail['documents'][number]

export const REVIEW_LABEL: Record<string, string> = { approve: 'Approved', deny: 'Rejected' }
export const REVIEW_TONE: Record<string, 'green' | 'red' | 'slate'> = { approve: 'green', deny: 'red' }
// Must match DECISION_ROLES in app/api/decisions.py.
const DECIDER_ROLES: Me['role'][] = ['Investigator', 'Fraud_Team']

// ---------------------------------------------------------------- documents

export function DocumentsSection({ claimId, documents, client }: { claimId: string; documents: Doc[]; client: Client }) {
  const [preview, setPreview] = useState<number | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const download = async (i: number) => {
    setBusy(i)
    setError(null)
    try {
      const url = URL.createObjectURL(await client.document(claimId, i))
      const a = Object.assign(document.createElement('a'), { href: url, download: documents[i].filename })
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not download the document.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Panel title={`Documents uploaded by the customer (${documents.length})`} icon={<FileText className="size-4 text-indigo-600" aria-hidden />}>
      {error && <Alert className="mb-3">{error}</Alert>}
      {documents.length === 0 ? <p className="text-sm text-slate-500">No documents were uploaded.</p> : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {documents.map((doc, i) => (
            <li key={i} className="flex items-center gap-3 rounded-lg bg-indigo-50/50 p-3 ring-1 ring-indigo-100">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-white text-indigo-600 ring-1 ring-indigo-100">
                <FileText className="size-5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-900" title={doc.filename}>{doc.filename}</span>
                <span className="block text-xs text-slate-500">{DOC_LABEL[doc.doc_type]} · {fileSize(doc.size)}</span>
              </span>
              <span className="flex shrink-0 gap-1.5">
                <Button size="sm" variant="secondary" className="px-3" onClick={() => setPreview(i)} aria-label={`Preview ${doc.filename}`}>
                  <Eye className="size-4" aria-hidden /> Preview
                </Button>
                <Button size="sm" variant="ghost" className="px-2.5" loading={busy === i} onClick={() => download(i)} aria-label={`Download ${doc.filename}`}>
                  {busy !== i && <Download className="size-4" aria-hidden />}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {preview != null && (
        <PreviewOverlay claimId={claimId} index={preview} doc={documents[preview]} client={client}
          onClose={() => setPreview(null)} onDownload={() => download(preview)} />
      )}
    </Panel>
  )
}

function PreviewOverlay({ claimId, index, doc, client, onClose, onDownload }: {
  claimId: string; index: number; doc: Doc; client: Client; onClose: () => void; onDownload: () => void
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [type, setType] = useState('')
  const [error, setError] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let alive = true
    let made: string | null = null
    client.document(claimId, index)
      .then((b) => {
        if (!alive) return
        made = URL.createObjectURL(b)
        setType(b.type)
        setUrl(made)
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : 'Could not load the document.'))
    return () => {
      alive = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [claimId, index, client])

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-indigo-950/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Preview of ${doc.filename}`} onClick={(e) => e.stopPropagation()}
        className="flex h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-center gap-3 border-b border-indigo-100 bg-indigo-600 px-4 py-3 text-white">
          <FileText className="size-5 shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{doc.filename}</div>
            <div className="text-xs text-indigo-100">{DOC_LABEL[doc.doc_type]} · {fileSize(doc.size)}</div>
          </div>
          <Button size="sm" variant="dark" onClick={onDownload}><Download className="size-4" aria-hidden /> Download</Button>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close preview"
            className="grid size-9 place-items-center rounded-md hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-white">
            <X className="size-5" aria-hidden />
          </button>
        </div>
        <div className="flex-1 bg-slate-100">
          {error ? <div className="p-6"><Alert>{error}</Alert></div>
            : !url ? <div className="grid h-full place-items-center"><Spinner className="size-8" /></div>
            : type === 'application/pdf' ? <iframe src={url} title={doc.filename} className="size-full border-0" />
            : type.startsWith('image/') ? <div className="grid h-full place-items-center overflow-auto p-4"><img src={url} alt={doc.filename} className="max-h-full max-w-full object-contain shadow" /></div>
            : <div className="grid h-full place-items-center p-6 text-center text-sm text-slate-600">This file type cannot be previewed. Use Download to open it.</div>}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- approve / reject

export function ReviewPanel({ d, me, client, onDecided }: { d: InternalDetail; me: Me; client: Client; onDecided: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<HumanDecision | null>(null)
  const [error, setError] = useState<string | null>(null)
  const canDecide = DECIDER_ROLES.includes(me.role)
  const ready = d.status === 'completed'
  const review: Review | null = d.review
  const auto = ready && d.decision === 'auto_approve'

  const decide = async (decision: HumanDecision) => {
    if (!reason.trim()) {
      setError('Add a reason before recording a decision.')
      return
    }
    if (!window.confirm(`${decision === 'approve' ? 'Approve' : 'Reject'} claim ${d.claim_id}? The customer will see this decision.`)) return
    setBusy(decision)
    setError(null)
    try {
      await client.decide(d.claim_id, decision, reason.trim())
      setReason('')
      onDecided()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not record the decision.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Panel title="Your decision" icon={<Gavel className="size-4 text-indigo-600" aria-hidden />}
      actions={review ? <Badge tone={REVIEW_TONE[review.decision] ?? 'slate'}>{REVIEW_LABEL[review.decision] ?? review.decision}</Badge>
        : auto ? <Badge tone="green">Auto-approved</Badge> : <Badge tone="amber">Pending review</Badge>}>
      {auto && !review && (
        <div className="mb-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-900 ring-1 ring-emerald-200">
          <b>Auto-approved.</b> Low risk and below the auto-approval amount, so no review was needed. You can still record a decision below.
        </div>
      )}
      {review && (
        <div className={cn('mb-4 rounded-lg px-4 py-3 text-sm ring-1', review.decision === 'approve' ? 'bg-emerald-50 text-emerald-900 ring-emerald-200' : 'bg-rose-50 text-rose-900 ring-rose-200')}>
          <b>{REVIEW_LABEL[review.decision] ?? review.decision}</b> by {review.by} on {fmtDateTime(review.at)}
          <p className="mt-1 text-slate-700">Reason: {review.reason}</p>
        </div>
      )}
      <p className="text-sm text-slate-600">
        The scores and findings above are signals for you to weigh, not a verdict. Your decision is recorded with your name and is shown to the customer.
      </p>
      {!ready && <Alert tone="indigo" className="mt-3">You can decide once processing has finished.</Alert>}
      {!canDecide && <Alert tone="amber" className="mt-3">Only an Investigator or the Fraud team can approve or reject claims.</Alert>}
      <label htmlFor="decision-reason" className="mt-4 block text-sm font-semibold text-slate-700">
        Reason {review ? '(to change the decision)' : ''}
      </label>
      <textarea id="decision-reason" rows={3} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)}
        disabled={!canDecide || !ready} placeholder="e.g. Bill and discharge summary match; amounts checked with the hospital."
        className="mt-1.5 w-full rounded-md bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-300 outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-600 disabled:bg-slate-50" />
      {error && <Alert className="mt-3">{error}</Alert>}
      <div className="mt-4 flex flex-wrap justify-end gap-3">
        <Button variant="danger" disabled={!canDecide || !ready || busy !== null} loading={busy === 'deny'} onClick={() => decide('deny')}>
          <CircleX className="size-4" aria-hidden /> Reject claim
        </Button>
        <Button variant="success" disabled={!canDecide || !ready || busy !== null} loading={busy === 'approve'} onClick={() => decide('approve')}>
          <CircleCheck className="size-4" aria-hidden /> Approve claim
        </Button>
      </div>
    </Panel>
  )
}
