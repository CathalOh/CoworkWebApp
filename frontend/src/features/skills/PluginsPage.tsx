import { useEffect, useState, type FormEvent } from 'react'
import { JsonView } from '@/components/JsonView'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createPlugin, listPlugins, patchPlugin } from '@/lib/api/endpoints'
import type { Plugin } from '@/lib/api/types'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'

const EXAMPLE = JSON.stringify(
  { description: 'Example plugin', skills: [{ name: 'hello', description: 'Says hello', body: 'Reply with a friendly greeting.' }] },
  null,
  2,
)

export function PluginsPage() {
  const hasRole = useAuthStore((s) => s.hasRole)
  const canRegister = hasRole('developer', 'org_admin')
  const canApprove = hasRole('org_admin')
  const [items, setItems] = useState<Plugin[] | null>(null)
  const [registering, setRegistering] = useState(false)
  const [name, setName] = useState('')
  const [version, setVersion] = useState('0.1.0')
  const [manifest, setManifest] = useState(EXAMPLE)
  const [busy, setBusy] = useState<string | null>(null)
  const reload = () => listPlugins().then(setItems).catch((e) => toast.error('Could not load plugins', errorMessage(e)))
  useEffect(() => {
    void reload()
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(manifest) as Record<string, unknown>
    } catch (err) {
      toast.error('Manifest is not valid JSON', (err as Error).message)
      return
    }
    setBusy('new')
    try {
      await createPlugin({ name: name.trim(), version: version.trim() || '0.1.0', manifest: parsed, scope: 'org' })
      toast.success('Plugin registered', canApprove ? '' : 'An org admin must approve it before use.')
      setRegistering(false)
      await reload()
    } catch (err) {
      toast.error('Could not register plugin', errorMessage(err))
    } finally {
      setBusy(null)
    }
  }
  const toggle = async (p: Plugin, field: 'approved' | 'enabled') => {
    setBusy(p.id)
    try {
      await patchPlugin(p.id, { [field]: !p[field] })
      await reload()
    } catch (err) {
      toast.error('Could not update plugin', errorMessage(err))
    } finally {
      setBusy(null)
    }
  }
  return (
    <>
      <div className="page-header">
        <h1>Plugins</h1>
        {canRegister && (
          <button className="btn btn-primary" onClick={() => setRegistering(true)}>
            + Register plugin
          </button>
        )}
      </div>
      {!items && <Spinner label="Loading…" />}
      {items && !items.length && <EmptyState title="No plugins">Plugins bundle skills and tools; org admins approve them after supply-chain review.</EmptyState>}
      {items?.map((p) => (
        <section key={p.id} className="card" aria-label={p.name}>
          <div className="card-title">
            <h3 className="mono">
              {p.name} <span className="faint">v{p.version}</span>
            </h3>
            <div className="row">
              <span className={`chip ${p.approved ? 'chip-success' : 'chip-warning'}`}>{p.approved ? 'approved' : 'pending approval'}</span>
              <span className={`chip ${p.enabled ? '' : 'chip-danger'}`}>{p.enabled ? 'enabled' : 'disabled'}</span>
              <span className="chip">{p.scope}</span>
            </div>
          </div>
          <p className="subtle small">{String(p.manifest.description || '')}</p>
          <details className="collapsible">
            <summary>Manifest</summary>
            <div className="body">
              <JsonView value={p.manifest} />
            </div>
          </details>
          {canApprove && (
            <div className="row mt">
              <label className="checkbox">
                <input type="checkbox" checked={p.approved} disabled={busy === p.id} onChange={() => toggle(p, 'approved')} /> Approved
              </label>
              <label className="checkbox">
                <input type="checkbox" checked={p.enabled} disabled={busy === p.id} onChange={() => toggle(p, 'enabled')} /> Enabled
              </label>
            </div>
          )}
        </section>
      ))}
      <Modal open={registering} onClose={() => setRegistering(false)} title="Register plugin" size="lg">
        <form onSubmit={submit}>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="pl-name">Name</label>
              <input id="pl-name" className="input mono" required pattern="[a-z0-9_-]{2,64}" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="pl-version">Version</label>
              <input id="pl-version" className="input mono" value={version} onChange={(e) => setVersion(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="pl-manifest">Manifest (JSON)</label>
            <textarea id="pl-manifest" className="textarea mono" rows={14} value={manifest} onChange={(e) => setManifest(e.target.value)} />
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setRegistering(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy === 'new'}>
              {busy === 'new' ? <span className="spinner" /> : 'Register'}
            </button>
          </div>
        </form>
      </Modal>
    </>
  )
}
