import { useEffect, useState } from 'react'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminCapabilities, adminSetCapability } from '@/lib/api/endpoints'
import type { CapabilityState } from '@/lib/api/types'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'

const DESCRIPTIONS: Record<string, string> = {
  connectors: 'MCP connectors (external systems) can be attached to runs.',
  web_tools: 'Web search / fetch tools are available to the agent.',
  sandbox_execution: 'Commands may execute in the sandbox.',
  plugins: 'Approved plugins are loaded.',
  new_runs: 'New runs may start (turn off to drain the system).',
  local_mcp: 'Local stdio MCP servers may be launched.',
  memory: 'Memory read/write is enabled.',
  artifacts: 'Artifacts can be created and rendered.',
  subagents: 'The agent may spawn subagents.',
}

export function CapabilitiesPage() {
  const canEdit = useAuthStore((s) => s.hasRole('org_admin'))
  const [state, setState] = useState<CapabilityState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const reload = () => adminCapabilities().then(setState).catch((e) => toast.error('Could not load capabilities', errorMessage(e)))
  useEffect(() => {
    void reload()
  }, [])
  const toggle = async (key: string, enabled: boolean) => {
    const reason = enabled ? null : window.prompt(`Reason for disabling "${key}" (recorded in the audit log)`) ?? null
    if (!enabled && reason === null) return
    setBusy(key)
    try {
      await adminSetCapability({ key, enabled, reason })
      toast.success(`${key} ${enabled ? 'enabled' : 'disabled'}`)
      await reload()
    } catch (e) {
      toast.error('Could not update capability', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div>
      <div className="page-header">
        <h1>Capability kill-switches</h1>
      </div>
      <p className="subtle">Org-wide switches. Disabling one takes effect for new runs immediately and is audited.</p>
      {!state && <Spinner label="Loading…" />}
      {state && (
        <ul className="list card" style={{ padding: 0 }}>
          {state.known.map((key) => {
            const enabled = state.capabilities[key]
            return (
              <li key={key} className="list-item">
                <div style={{ flex: 1 }}>
                  <div className="mono">{key}</div>
                  <div className="small subtle">{DESCRIPTIONS[key] || ''}</div>
                </div>
                <span className={`chip ${enabled ? 'chip-success' : 'chip-danger'}`}>{enabled ? 'enabled' : 'disabled'}</span>
                {canEdit && (
                  <button className={`btn btn-sm ${enabled ? 'btn-danger' : 'btn-primary'}`} onClick={() => toggle(key, !enabled)} disabled={busy === key}>
                    {busy === key ? <span className="spinner" /> : enabled ? 'Disable' : 'Enable'}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
