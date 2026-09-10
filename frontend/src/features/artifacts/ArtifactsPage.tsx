import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createArtifact, listArtifacts } from '@/lib/api/endpoints'
import type { Artifact, ArtifactKind } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

const KINDS: ArtifactKind[] = ['html', 'react', 'markdown', 'svg', 'mermaid', 'code']

export function ArtifactsPage() {
  const [params] = useSearchParams()
  const conversationId = params.get('conversation_id')
  const [items, setItems] = useState<Artifact[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<ArtifactKind>('html')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    setItems(null)
    listArtifacts(conversationId).then(setItems).catch((e) => toast.error('Could not load artifacts', errorMessage(e)))
  }, [conversationId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const a = await createArtifact({ kind, title: title.trim(), content, conversation_id: conversationId })
      nav(`/artifacts/${a.id}`)
    } catch (err) {
      toast.error('Could not create artifact', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <div>
            <h1>Artifacts</h1>
            {conversationId && (
              <div className="small faint">
                Filtered by conversation · <Link to="/artifacts">show all mine</Link>
              </div>
            )}
          </div>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New artifact
          </button>
        </div>
        {!items && <Spinner label="Loading…" />}
        {items && !items.length && <EmptyState title="No artifacts">Artifacts are rendered documents (HTML, SVG, Mermaid, Markdown…) produced in conversations.</EmptyState>}
        {items && items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Kind</th>
                  <th>Versions</th>
                  <th>Live</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className="clickable" onClick={() => nav(`/artifacts/${a.id}`)}>
                    <td>
                      <Link to={`/artifacts/${a.id}`}>{a.title}</Link>
                    </td>
                    <td>
                      <span className="badge">{a.kind}</span>
                    </td>
                    <td>{a.latest_version}</td>
                    <td>{a.live_source ? <span className="chip chip-info">live</span> : <span className="faint">—</span>}</td>
                    <td className="faint">{formatRelative(a.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Modal open={creating} onClose={() => setCreating(false)} title="New artifact" size="lg">
          <form onSubmit={submit}>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="art-title">Title</label>
                <input id="art-title" className="input" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="art-kind">Kind</label>
                <select id="art-kind" className="select" value={kind} onChange={(e) => setKind(e.target.value as ArtifactKind)}>
                  {KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="art-content">Content</label>
              <textarea id="art-content" className="textarea mono" rows={14} required value={content} onChange={(e) => setContent(e.target.value)} />
            </div>
            <div className="form-actions">
              <button type="button" className="btn" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? <span className="spinner" /> : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </div>
  )
}
