import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createWorkspace, listTeams, listWorkspaces } from '@/lib/api/endpoints'
import type { Team, Workspace } from '@/lib/api/types'
import { formatBytes, formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

export function WorkspacesPage() {
  const [items, setItems] = useState<Workspace[] | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [teamId, setTeamId] = useState('')
  const [quotaGb, setQuotaGb] = useState('')
  const [busy, setBusy] = useState(false)
  const reload = () => listWorkspaces().then(setItems).catch((e) => toast.error('Could not load workspaces', errorMessage(e)))
  useEffect(() => {
    void reload()
    listTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await createWorkspace({ name: name.trim(), team_id: teamId || null, quota_bytes: quotaGb ? Math.round(Number(quotaGb) * 1024 ** 3) : null })
      toast.success('Workspace created')
      setCreating(false)
      setName('')
      setTeamId('')
      setQuotaGb('')
      await reload()
    } catch (err) {
      toast.error('Could not create workspace', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <h1>Workspaces</h1>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New workspace
          </button>
        </div>
        {!items && <Spinner label="Loading…" />}
        {items && !items.length && <EmptyState title="No workspaces">A workspace is a persistent sandbox directory the agent works in.</EmptyState>}
        {items && items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Team</th>
                  <th>Quota</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((w) => (
                  <tr key={w.id}>
                    <td>
                      <Link to={`/workspaces/${w.id}`}>{w.name}</Link>
                    </td>
                    <td>{w.team_id ? teams.find((t) => t.id === w.team_id)?.name || w.team_id.slice(0, 8) : <span className="faint">personal</span>}</td>
                    <td>{w.quota_bytes ? formatBytes(w.quota_bytes) : <span className="faint">default</span>}</td>
                    <td className="faint">{formatRelative(w.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Modal open={creating} onClose={() => setCreating(false)} title="New workspace">
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="ws-name">Name</label>
              <input id="ws-name" className="input" required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="ws-team">Team</label>
              <select id="ws-team" className="select" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">Personal</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="ws-quota">Quota (GB)</label>
              <input id="ws-quota" className="input" type="number" min={0} step="0.5" value={quotaGb} onChange={(e) => setQuotaGb(e.target.value)} placeholder="server default" />
            </div>
            <div className="form-actions">
              <button type="button" className="btn" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy || !name.trim()}>
                {busy ? <span className="spinner" /> : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </div>
  )
}
