import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '@/lib/api/client'
import { startOidcLogin } from '@/lib/oidc'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'
import { ToastHost } from '@/components/Toast'

const ROLE_OPTIONS = ['user', 'developer', 'team_lead', 'workspace_admin', 'auditor', 'org_admin']

export function LoginPage() {
  const { status, meta, loginDev } = useAuthStore()
  const nav = useNavigate()
  const loc = useLocation()
  const from = (loc.state as { from?: string } | null)?.from || '/chat'
  const [email, setEmail] = useState('dev@example.com')
  const [name, setName] = useState('')
  const [roles, setRoles] = useState<string[]>(['user'])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (new URLSearchParams(loc.search).get('dev') === '1') toast.info('OIDC is not configured', 'Use the development login instead.')
  }, [loc.search])

  if (status === 'authenticated') return <Navigate to={from} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await loginDev(email.trim(), name.trim(), roles)
      nav(from, { replace: true })
    } catch (err) {
      toast.error('Login failed', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggle = (r: string) => setRoles((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))

  return (
    <div className="login">
      <div className="card">
        <div className="row mb">
          <span className="logo" style={{ width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg, var(--accent), #8b5cf6)' }} aria-hidden="true" />
          <h1 style={{ margin: 0 }}>Sign in to Cowork</h1>
        </div>
        {meta === null && <p className="subtle">Checking server configuration…</p>}
        {meta?.oidc && (
          <div className="stack mb">
            <button className="btn btn-primary" onClick={() => startOidcLogin(from)}>
              Continue with single sign-on
            </button>
            <span className="small faint">You will be redirected to your identity provider.</span>
          </div>
        )}
        {meta?.dev_login && (
          <form onSubmit={submit} aria-label="Development login">
            {meta.oidc && <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '14px 0' }} />}
            <h3>Development login</h3>
            <p className="small faint">Local only: mints a session without an identity provider (ENV={meta.env}).</p>
            <div className="field">
              <label htmlFor="login-email">Email</label>
              <input id="login-email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </div>
            <div className="field">
              <label htmlFor="login-name">Display name</label>
              <input id="login-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="optional" />
            </div>
            <fieldset className="field" style={{ border: 0, padding: 0 }}>
              <legend className="label">Roles</legend>
              <div className="row">
                {ROLE_OPTIONS.map((r) => (
                  <label key={r} className="checkbox">
                    <input type="checkbox" checked={roles.includes(r)} onChange={() => toggle(r)} disabled={r === 'user'} />
                    {r}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={busy}>
                {busy ? <span className="spinner" /> : 'Sign in'}
              </button>
            </div>
          </form>
        )}
        {meta && !meta.oidc && !meta.dev_login && <p className="subtle">No login method is enabled on this server.</p>}
      </div>
      <ToastHost />
    </div>
  )
}
