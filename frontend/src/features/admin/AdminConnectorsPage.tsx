import { useEffect, useState, type FormEvent } from 'react'
import { Modal } from '@/components/Modal'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminConnectors, adminCreateConnector, adminPatchConnector, listTeams } from '@/lib/api/endpoints'
import type { Connector, ConnectorIn, Team } from '@/lib/api/types'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'

const EMPTY: ConnectorIn = { name: '', display_name: '', description: '', transport: 'http', url: '', auth_type: 'oauth', risk_class: 'medium', required_scopes: [], approved: false, enabled: true }

export function AdminConnectorsPage() {
  const isOrgAdmin = useAuthStore((s) => s.hasRole('org_admin'))
  const [items, setItems] = useState<Connector[] | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<ConnectorIn>(EMPTY)
  const [busy, setBusy] = useState<string | null>(null)
  const reload = () => adminConnectors().then(setItems).catch((e) => toast.error('Could not load catalog', errorMessage(e)))
  useEffect(() => {
    void reload()
    listTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const patch = async (c: Connector, body: Record<string, unknown>) => {
    setBusy(c.id)
    try {
      await adminPatchConnector(c.id, body)
      await reload()
    } catch (e) {
      toast.error('Could not update connector', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy('new')
    try {
      await adminCreateConnector({ ...form, description: form.description || null, url: form.url || null, required_scopes: form.required_scopes?.length ? form.required_scopes : null })
      toast.success('Connector added')
      setCreating(false)
      setForm(EMPTY)
      await reload()
    } catch (err) {
      toast.error('Could not add connector', errorMessage(err))
    } finally {
      setBusy(null)
    }
  }
  const editTeams = async (c: Connector) => {
    const current = (c.team_ids || []).join(',')
    const v = window.prompt('Team ids allowed to use this connector (comma separated; empty = all teams)\n' + teams.map((t) => `${t.name}: ${t.id}`).join('\n'), current)
    if (v === null) return
    await patch(c, { team_ids: v.split(',').map((x) => x.trim()).filter(Boolean) })
  }

  return (
    <div>
      <div className="page-header">
        <h1>Connector catalog</h1>
        {isOrgAdmin && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + Add connector
          </button>
        )}
      </div>
      {!items && <Spinner label="Loading…" />}
      {items && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Transport</th>
                <th>Auth</th>
                <th>Risk</th>
                <th>Teams</th>
                <th>Approved</th>
                <th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td>
                    <div>{c.display_name}</div>
                    <div className="mono faint small">{c.name}</div>
                  </td>
                  <td>
                    {c.transport}
                    {c.url && <div className="faint small mono truncate" style={{ maxWidth: 220 }}>{c.url}</div>}
                  </td>
                  <td>{c.auth_type}</td>
                  <td>
                    {isOrgAdmin ? (
                      <select className="select" style={{ width: 'auto' }} value={c.risk_class} disabled={busy === c.id} onChange={(e) => patch(c, { risk_class: e.target.value })} aria-label="Risk class">
                        {['low', 'medium', 'high'].map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    ) : (
                      c.risk_class
                    )}
                  </td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={() => editTeams(c)} disabled={busy === c.id}>
                      {c.team_ids?.length ? `${c.team_ids.length} team(s)` : 'all teams'}
                    </button>
                  </td>
                  <td>
                    <label className="checkbox">
                      <input type="checkbox" checked={c.approved} disabled={busy === c.id} onChange={() => patch(c, { approved: !c.approved })} aria-label="Approved" />
                    </label>
                  </td>
                  <td>
                    <label className="checkbox">
                      <input type="checkbox" checked={c.enabled} disabled={busy === c.id || !isOrgAdmin} onChange={() => patch(c, { enabled: !c.enabled })} aria-label="Enabled" />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <div className="empty">Catalog is empty.</div>}
        </div>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title="Add connector" size="lg">
        <form onSubmit={submit}>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="cc-name">Name (slug)</label>
              <input id="cc-name" className="input mono" required pattern="[a-z0-9_-]{2,64}" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="cc-display">Display name</label>
              <input id="cc-display" className="input" required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="cc-transport">Transport</label>
              <select id="cc-transport" className="select" value={form.transport} onChange={(e) => setForm({ ...form, transport: e.target.value as ConnectorIn['transport'] })}>
                {['http', 'sse', 'stdio', 'sdk'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="cc-auth">Auth type</label>
              <select id="cc-auth" className="select" value={form.auth_type} onChange={(e) => setForm({ ...form, auth_type: e.target.value as ConnectorIn['auth_type'] })}>
                {['none', 'oauth', 'static_header'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="cc-url">URL</label>
              <input id="cc-url" className="input mono" value={form.url || ''} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://mcp.example.com/" />
            </div>
            <div className="field">
              <label htmlFor="cc-risk">Risk class</label>
              <select id="cc-risk" className="select" value={form.risk_class} onChange={(e) => setForm({ ...form, risk_class: e.target.value as ConnectorIn['risk_class'] })}>
                {['low', 'medium', 'high'].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="field">
            <label htmlFor="cc-desc">Description</label>
            <input id="cc-desc" className="input" value={form.description || ''} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="cc-scopes">Required scopes (comma separated)</label>
            <input id="cc-scopes" className="input mono" value={(form.required_scopes || []).join(', ')} onChange={(e) => setForm({ ...form, required_scopes: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
          </div>
          <div className="row">
            <label className="checkbox">
              <input type="checkbox" checked={!!form.approved} onChange={(e) => setForm({ ...form, approved: e.target.checked })} /> Approved
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={!!form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Enabled
            </label>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setCreating(false)}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={busy === 'new'}>
              {busy === 'new' ? <span className="spinner" /> : 'Add'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
