import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { getWorkspace, listWorkspaceFiles, workspaceFileUrl } from '@/lib/api/endpoints'
import type { Workspace, WorkspaceListing } from '@/lib/api/types'
import { formatBytes } from '@/lib/format'
import { toast } from '@/store/toast'

export function WorkspaceDetailPage() {
  const { workspaceId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const path = params.get('path') || ''
  const [ws, setWs] = useState<Workspace | null>(null)
  const [listing, setListing] = useState<WorkspaceListing | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getWorkspace(workspaceId).then(setWs).catch((e) => setError(errorMessage(e)))
  }, [workspaceId])
  useEffect(() => {
    setListing(null)
    listWorkspaceFiles(workspaceId, path).then(setListing).catch((e) => toast.error('Could not list files', errorMessage(e)))
  }, [workspaceId, path])

  if (error) return <div className="page"><EmptyState title="Workspace unavailable">{error}</EmptyState></div>
  if (!ws) return <div className="page"><Spinner label="Loading…" /></div>

  const quota = listing?.quota_bytes ?? ws.quota_bytes
  const used = listing?.bytes_used ?? 0
  const pct = quota ? Math.min(100, (used / quota) * 100) : 0
  const crumbs = path.split('/').filter(Boolean)
  const go = (p: string) => setParams(p ? { path: p } : {})

  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <div>
            <div className="small faint">
              <Link to="/workspaces">Workspaces</Link> / {ws.name}
            </div>
            <h1>{ws.name}</h1>
          </div>
        </div>
        <section className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span>
              <strong>{formatBytes(used)}</strong> used {quota ? `of ${formatBytes(quota)}` : '(no quota)'}
            </span>
            <span className="faint small mono">{ws.host_path}</span>
          </div>
          {quota ? (
            <div className={`bar mt ${pct > 90 ? 'danger' : pct > 75 ? 'warn' : ''}`} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${pct}%` }} />
            </div>
          ) : null}
        </section>
        <section className="card mt" aria-label="File browser">
          <div className="row mb" aria-label="Breadcrumbs">
            <button className="btn btn-ghost btn-sm" onClick={() => go('')}>
              /
            </button>
            {crumbs.map((c, i) => (
              <span key={i} className="row" style={{ gap: 4 }}>
                <span className="faint">/</span>
                <button className="btn btn-ghost btn-sm" onClick={() => go(crumbs.slice(0, i + 1).join('/'))}>
                  {c}
                </button>
              </span>
            ))}
          </div>
          {!listing && <Spinner label="Listing…" />}
          {listing && !listing.entries.length && <p className="subtle small">Empty directory.</p>}
          {listing && listing.entries.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Size</th>
                    <th>Modified</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {listing.entries.map((e) => {
                    const full = path ? `${path}/${e.name}` : e.name
                    return (
                      <tr key={e.name}>
                        <td>
                          {e.is_dir ? (
                            <button className="btn btn-ghost btn-sm" onClick={() => go(full)}>
                              📁 {e.name}
                            </button>
                          ) : (
                            <span>📄 {e.name}</span>
                          )}
                        </td>
                        <td className="faint">{e.is_dir ? '—' : formatBytes(e.bytes)}</td>
                        <td className="faint">{new Date(e.mtime * 1000).toLocaleString()}</td>
                        <td>
                          {!e.is_dir && (
                            <a className="btn btn-sm" href={workspaceFileUrl(workspaceId, full)} target="_blank" rel="noopener noreferrer">
                              Download
                            </a>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
