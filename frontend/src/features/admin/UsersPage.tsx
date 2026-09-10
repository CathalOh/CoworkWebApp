import { useEffect, useState } from 'react'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminRoles, adminSetRoles, adminSetStatus, listUsers } from '@/lib/api/endpoints'
import type { User } from '@/lib/api/types'
import { toast } from '@/store/toast'

const FALLBACK_ROLES = ['user', 'developer', 'team_lead', 'workspace_admin', 'auditor', 'org_admin']

export function UsersPage() {
  const [q, setQ] = useState('')
  const [users, setUsers] = useState<User[] | null>(null)
  const [roles, setRoles] = useState<string[]>(FALLBACK_ROLES)
  const [busy, setBusy] = useState<string | null>(null)
  const reload = (query?: string) => listUsers(query).then(setUsers).catch((e) => toast.error('Could not load users', errorMessage(e)))
  useEffect(() => {
    void reload()
    adminRoles().then((r) => setRoles(Array.from(new Set([...FALLBACK_ROLES, ...r])))).catch(() => undefined)
  }, [])

  const toggleRole = async (u: User, role: string) => {
    const next = u.roles.includes(role) ? u.roles.filter((r) => r !== role) : [...u.roles, role]
    setBusy(u.id)
    try {
      const res = await adminSetRoles(u.id, next)
      setUsers((list) => list?.map((x) => (x.id === u.id ? { ...x, roles: res.roles } : x)) ?? null)
    } catch (e) {
      toast.error('Could not change roles', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const setStatus = async (u: User, status: 'active' | 'disabled') => {
    setBusy(u.id)
    try {
      await adminSetStatus(u.id, status)
      toast.success(`${u.email} ${status}`)
    } catch (e) {
      toast.error('Could not change status', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div>
      <div className="page-header">
        <h1>Users & roles</h1>
        <form className="row" onSubmit={(e) => { e.preventDefault(); void reload(q.trim() || undefined) }}>
          <input className="input" style={{ width: 220 }} placeholder="Search email" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users" />
          <button className="btn" type="submit">Search</button>
        </form>
      </div>
      <p className="subtle small">Roles normally come from identity-provider group claims at login; changes here are manual overrides and are audited.</p>
      {!users && <Spinner label="Loading…" />}
      {users && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Roles</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div>{u.display_name || u.email}</div>
                    <div className="faint small">{u.email}</div>
                  </td>
                  <td>
                    <div className="row">
                      {roles.map((r) => (
                        <label key={r} className="checkbox small">
                          <input type="checkbox" checked={u.roles.includes(r)} disabled={r === 'user' || busy === u.id} onChange={() => toggleRole(u, r)} /> {r}
                        </label>
                      ))}
                    </div>
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn btn-sm" onClick={() => setStatus(u, 'active')} disabled={busy === u.id}>Activate</button>
                      <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }} onClick={() => setStatus(u, 'disabled')} disabled={busy === u.id}>Disable</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!users.length && <div className="empty">No users found.</div>}
        </div>
      )}
    </div>
  )
}
