import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { Spinner } from './EmptyState'

export function RequireAuth() {
  const status = useAuthStore((s) => s.status)
  const loc = useLocation()
  if (status === 'idle' || status === 'loading') {
    return (
      <div className="login">
        <Spinner label="Loading…" />
      </div>
    )
  }
  if (status !== 'authenticated') return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return <Outlet />
}

export function RequireRole({ roles }: { roles: string[] }) {
  const hasRole = useAuthStore((s) => s.hasRole)
  if (!hasRole(...roles)) {
    return (
      <div className="page">
        <div className="empty">
          <h3>Not authorized</h3>
          <p>This page requires one of: {roles.join(', ')}.</p>
        </div>
      </div>
    )
  }
  return <Outlet />
}
