import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { addArtifactVersion, artifactRenderUrl, getArtifact, getArtifactVersion, listArtifactVersions, refreshArtifact } from '@/lib/api/endpoints'
import type { Artifact, ArtifactVersion } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

export function ArtifactViewerPage() {
  const { artifactId = '' } = useParams()
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [versions, setVersions] = useState<ArtifactVersion[]>([])
  const [version, setVersion] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [frameKey, setFrameKey] = useState(0)

  const load = async () => {
    const a = await getArtifact(artifactId)
    setArtifact(a)
    const vs = await listArtifactVersions(artifactId)
    setVersions(vs)
    setVersion(a.latest_version)
  }
  useEffect(() => {
    load().catch((e) => setError(errorMessage(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactId])

  if (error) return <div className="page"><EmptyState title="Artifact unavailable">{error}</EmptyState></div>
  if (!artifact) return <div className="page"><Spinner label="Loading…" /></div>

  const openEditor = async () => {
    try {
      const v = await getArtifactVersion(artifactId, version ?? artifact.latest_version)
      setDraft(v.content)
      setEditing(true)
    } catch (e) {
      toast.error('Could not load version', errorMessage(e))
    }
  }
  const saveVersion = async () => {
    setBusy(true)
    try {
      await addArtifactVersion(artifactId, draft)
      toast.success('New version saved')
      setEditing(false)
      await load()
      setFrameKey((k) => k + 1)
    } catch (e) {
      toast.error('Could not save version', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const refresh = async () => {
    setBusy(true)
    try {
      const v = await refreshArtifact(artifactId)
      toast.success('Live data refreshed', `Version ${v.version}`)
      await load()
      setFrameKey((k) => k + 1)
    } catch (e) {
      toast.error('Refresh failed', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="small faint">
            <Link to="/artifacts">Artifacts</Link> / {artifact.title}
          </div>
          <h1 className="row">
            {artifact.title} <span className="badge">{artifact.kind}</span>
          </h1>
        </div>
        <div className="row">
          <label className="row small" style={{ gap: 4 }}>
            Version
            <select className="select" style={{ width: 'auto' }} value={version ?? ''} onChange={(e) => setVersion(Number(e.target.value))}>
              {versions.map((v) => (
                <option key={v.version} value={v.version}>
                  v{v.version} · {formatRelative(v.created_at)}
                </option>
              ))}
            </select>
          </label>
          {artifact.live_source && (
            <button className="btn" onClick={refresh} disabled={busy} title={`Re-runs ${String((artifact.live_source as { tool?: string }).tool || 'live source')}`}>
              {busy ? <span className="spinner" /> : '↻ Refresh live'}
            </button>
          )}
          <button className="btn" onClick={openEditor}>
            Edit → new version
          </button>
          <a className="btn" href={artifactRenderUrl(artifactId, version)} target="_blank" rel="noopener noreferrer">
            Open in tab
          </a>
          {artifact.conversation_id && (
            <Link className="btn btn-ghost" to={`/chat/${artifact.conversation_id}`}>
              Conversation
            </Link>
          )}
        </div>
      </div>
      {/* Sandboxed preview: scripts allowed, but NO allow-same-origin so the document cannot reach our cookies/API. */}
      <iframe
        key={`${frameKey}-${version}`}
        className="artifact-frame"
        title={`Artifact preview: ${artifact.title}`}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        src={artifactRenderUrl(artifactId, version)}
      />
      <Modal open={editing} onClose={() => setEditing(false)} title="Edit artifact (saves as a new version)" size="lg">
        <textarea className="textarea mono" rows={20} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Artifact content" />
        <div className="form-actions">
          <button className="btn" onClick={() => setEditing(false)}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={saveVersion} disabled={busy}>
            {busy ? <span className="spinner" /> : 'Save version'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
