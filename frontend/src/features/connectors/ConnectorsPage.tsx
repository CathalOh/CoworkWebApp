import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { StatusChip } from '@/components/Chip'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { authorizeConnector, listConnectors, revokeConnector } from '@/lib/api/endpoints'
import type { Connector } from '@/lib/api/types'
import { toast } from '@/store/toast'

export function ConnectorsPage() {
  const [items, setItems] = useState<Connector[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const { confirm, dialog } = useConfirm()
  const reload = () => listConnectors().then(setItems).catch((e) => toast.error('Could not load connectors', errorMessage(e)))

  useEffect(() => {
    void reload()
  }, [])
  // OAuth callback lands on /connectors?connected=<name> or ?error=<code>
  useEffect(() => {
    const connected = params.get('connected')
    const error = params.get('error')
    if (connected) toast.success('Connector connected', connected)
    if (error) toast.error('Connection failed', error)
    if (connected || error) setParams({}, { replace: true })
  }, [params, setParams])

  const connect = async (c: Connector) => {
    setBusy(c.id)
    try {
      const { authorization_url } = await authorizeConnector(c.id)
      window.location.assign(authorization_url)
    } catch (e) {
      toast.error('Could not start authorization', errorMessage(e))
      setBusy(null)
    }
  }
  const disconnect = async (c: Connector) => {
    if (!(await confirm(`Disconnect ${c.display_name}?`, { message: 'Your stored credentials for this connector are deleted.', danger: true, confirmLabel: 'Disconnect' }))) return
    setBusy(c.id)
    try {
      await revokeConnector(c.id)
      toast.success('Disconnected')
      await reload()
    } catch (e) {
      toast.error('Could not disconnect', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <h1>Connectors</h1>
        </div>
        {!items && <Spinner label="Loading…" />}
        {items && !items.length && <EmptyState title="No connectors available">An admin needs to add and approve MCP connectors in the catalog.</EmptyState>}
        {items && items.length > 0 && (
          <div className="grid-2">
            {items.map((c) => (
              <section key={c.id} className="card" aria-label={c.display_name}>
                <div className="card-title">
                  <h3>{c.display_name}</h3>
                  <StatusChip status={c.status} />
                </div>
                <p className="subtle small">{c.description || 'No description'}</p>
                <div className="row small faint mb">
                  <span>{c.transport}</span>
                  <span>· auth: {c.auth_type}</span>
                  <span>· risk: {c.risk_class}</span>
                  {!c.approved && <span className="badge badge-warning">not approved</span>}
                  {!c.enabled && <span className="badge">disabled</span>}
                </div>
                {c.required_scopes?.length ? <div className="small faint mb">Scopes: {c.required_scopes.join(', ')}</div> : null}
                <div className="row">
                  {c.auth_type === 'oauth' && c.status !== 'connected' && (
                    <button className="btn btn-primary btn-sm" onClick={() => connect(c)} disabled={busy === c.id || !c.enabled}>
                      {busy === c.id ? <span className="spinner" /> : 'Connect'}
                    </button>
                  )}
                  {c.auth_type === 'oauth' && c.status === 'connected' && (
                    <>
                      <button className="btn btn-sm" onClick={() => connect(c)} disabled={busy === c.id}>
                        Reconnect
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => disconnect(c)} disabled={busy === c.id}>
                        Disconnect
                      </button>
                    </>
                  )}
                </div>
              </section>
            ))}
          </div>
        )}
        {dialog}
      </div>
    </div>
  )
}
