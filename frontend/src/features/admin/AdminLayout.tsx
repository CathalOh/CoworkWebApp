import { NavLink, Outlet } from 'react-router-dom'
import { Slot } from '@/slots/Slot'
import { useAuthStore } from '@/store/auth'

const LINKS: Array<{ to: string; label: string; roles: string[] }> = [
  { to: '/admin/audit', label: 'Audit log', roles: ['org_admin', 'auditor'] },
  { to: '/admin/llm-logs', label: 'LLM logs', roles: ['org_admin', 'auditor'] },
  { to: '/admin/app-logs', label: 'App logs', roles: ['org_admin', 'auditor'] },
  { to: '/admin/usage', label: 'Usage', roles: ['org_admin', 'auditor', 'workspace_admin', 'team_lead'] },
  { to: '/admin/capabilities', label: 'Capabilities', roles: ['org_admin', 'workspace_admin', 'auditor'] },
  { to: '/admin/connectors', label: 'Connector catalog', roles: ['org_admin', 'workspace_admin'] },
  { to: '/admin/runs', label: 'Active runs', roles: ['org_admin'] },
  { to: '/admin/users', label: 'Users & roles', roles: ['org_admin'] },
]

export function adminLinksFor(hasRole: (...r: string[]) => boolean) {
  return LINKS.filter((l) => hasRole(...l.roles))
}

export function AdminLayout() {
  const hasRole = useAuthStore((s) => s.hasRole)
  return (
    <div className="admin" style={{ flex: 1, minWidth: 0 }}>
      <nav className="admin-nav" aria-label="Admin">
        {adminLinksFor(hasRole).map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? 'active' : '')}>
            {l.label}
          </NavLink>
        ))}
        <Slot name="admin.nav" />
      </nav>
      <div className="page" style={{ flex: 1, minWidth: 0 }}>
        <Outlet />
      </div>
    </div>
  )
}

export function AdminIndex() {
  const hasRole = useAuthStore((s) => s.hasRole)
  const links = adminLinksFor(hasRole)
  return (
    <div>
      <h1>Administration</h1>
      <p className="subtle">Choose a section: {links.map((l) => l.label).join(', ')}.</p>
    </div>
  )
}
