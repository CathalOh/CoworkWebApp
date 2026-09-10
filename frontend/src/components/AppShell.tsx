import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ADMIN_ROLES, useAuthStore } from '@/store/auth'
import { useUiStore } from '@/store/ui'
import { SearchPalette } from './SearchPalette'
import { ToastHost } from './Toast'

const NAV: Array<{ to: string; label: string; roles?: string[] }> = [
  { to: '/chat', label: 'Chat' },
  { to: '/projects', label: 'Projects' },
  { to: '/workspaces', label: 'Workspaces' },
  { to: '/artifacts', label: 'Artifacts' },
  { to: '/connectors', label: 'Connectors' },
  { to: '/tasks', label: 'Tasks' },
  { to: '/skills', label: 'Skills' },
  { to: '/admin', label: 'Admin', roles: ADMIN_ROLES },
]

export function AppShell() {
  const user = useAuthStore((s) => s.user)
  const hasRole = useAuthStore((s) => s.hasRole)
  const logout = useAuthStore((s) => s.logout)
  const setSearchOpen = useUiStore((s) => s.setSearchOpen)
  const nav = useNavigate()
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <div className="app">
      <header className="topnav">
        <NavLink to="/chat" className="brand" aria-label="Cowork home">
          <span className="logo" aria-hidden="true" />
          <span className="hide-sm">Cowork</span>
        </NavLink>
        <nav aria-label="Primary">
          {NAV.filter((n) => !n.roles || hasRole(...n.roles)).map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <span className="spacer" />
        <button className="btn btn-ghost btn-sm" onClick={() => setSearchOpen(true)} aria-label="Search (Cmd+K)" title="Search">
          <span aria-hidden="true">🔍</span> <span className="hide-sm faint">{isMac ? '⌘K' : 'Ctrl+K'}</span>
        </button>
        {user && (
          <div className="row" style={{ gap: 6 }}>
            <span className="subtle small hide-sm truncate" style={{ maxWidth: 180 }} title={user.roles.join(', ')}>
              {user.display_name || user.email}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                await logout()
                nav('/login')
              }}
            >
              Sign out
            </button>
          </div>
        )}
      </header>
      <div className="main">
        <Outlet />
      </div>
      <SearchPalette />
      <ToastHost />
    </div>
  )
}
