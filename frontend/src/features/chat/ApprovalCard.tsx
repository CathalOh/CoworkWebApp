import { useState } from 'react'
import { JsonView } from '@/components/JsonView'
import { errorMessage } from '@/lib/api/client'
import type { ApprovalIn, ApprovalRequestData } from '@/lib/api/types'
import { toast } from '@/store/toast'

interface Props {
  request: ApprovalRequestData
  onDecide: (body: ApprovalIn) => Promise<void>
}

export function ApprovalCard({ request, onDecide }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => JSON.stringify(request.input ?? {}, null, 2))
  const [draftError, setDraftError] = useState<string | null>(null)
  const isDeletion = request.category === 'delete'

  const decide = async (decision: ApprovalIn['decision']) => {
    let rewrite: Record<string, unknown> | undefined
    if (editing && decision !== 'deny') {
      try {
        rewrite = JSON.parse(draft) as Record<string, unknown>
        setDraftError(null)
      } catch (e) {
        setDraftError(`Invalid JSON: ${(e as Error).message}`)
        return
      }
    }
    setBusy(decision)
    try {
      await onDecide({ tool_use_id: request.tool_use_id, decision, rewrite })
    } catch (e) {
      toast.error('Could not submit decision', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className={`approval ${isDeletion ? 'deletion' : ''}`} aria-label={`Approval requested for ${request.name}`} aria-live="polite">
      <div className="head">
        <strong>Approval needed</strong>
        <span className="mono">{request.name}</span>
        {request.category && <span className={`badge ${isDeletion ? 'badge-danger' : 'badge-warning'}`}>{isDeletion ? 'Deletion protection' : request.category}</span>}
        {request.timeout_seconds ? <span className="faint small">auto-denies in {Math.round(request.timeout_seconds / 60)} min</span> : null}
      </div>
      {request.reason && <p className="subtle">{request.reason}</p>}
      {isDeletion && <p className="small">This action deletes data. It always requires an explicit decision, and "always allow" is not offered.</p>}
      {editing ? (
        <div className="field">
          <label htmlFor={`rewrite-${request.tool_use_id}`}>Edit tool input (JSON)</label>
          <textarea id={`rewrite-${request.tool_use_id}`} className="textarea mono" rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
          {draftError && <span className="hint" style={{ color: 'var(--danger)' }}>{draftError}</span>}
        </div>
      ) : (
        <JsonView value={request.input} maxHeight={220} />
      )}
      <div className="actions">
        <button className="btn btn-success" onClick={() => decide('allow')} disabled={!!busy}>
          {busy === 'allow' ? <span className="spinner" /> : editing ? 'Allow with edits' : 'Allow'}
        </button>
        {!isDeletion && (
          <button className="btn" onClick={() => decide('always_allow')} disabled={!!busy}>
            {busy === 'always_allow' ? <span className="spinner" /> : 'Always allow this session'}
          </button>
        )}
        <button className="btn btn-danger" onClick={() => decide('deny')} disabled={!!busy}>
          {busy === 'deny' ? <span className="spinner" /> : 'Deny'}
        </button>
        <button className="btn btn-ghost" onClick={() => setEditing((v) => !v)} disabled={!!busy}>
          {editing ? 'Cancel edit' : 'Edit input'}
        </button>
      </div>
    </section>
  )
}
