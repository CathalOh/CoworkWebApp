import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { StatusChip } from '@/components/Chip'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminRuns, interruptRun } from '@/lib/api/endpoints'
import type { AdminRun } from '@/lib/api/types'
import { ACTIVE_RUN_STATUSES, isActiveRun } from '@/lib/api/types'
import { formatMoney, formatRelative, shortId } from '@/lib/format'
import { toast } from '@/store/toast'

export function RunsPage() {
  const [status, setStatus] = useState('')
  const [items, setItems] = useState<AdminRun[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const reload = () => adminRuns(status || undefined).then(setItems).catch((e) => toast.error('Could not load runs', errorMessage(e)))
  useEffect(() => {
    setItems(null)
    void reload()
    const t = setInterval(reload, 10000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])
  const stop = async (r: AdminRun) => {
    setBusy(r.id)
    try {
      await interruptRun(r.id)
      toast.success('Interrupt requested')
      await reload()
    } catch (e) {
      toast.error('Could not interrupt', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div>
      <div className="page-header">
        <h1>Runs</h1>
        <select className="select" style={{ width: 'auto' }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">all statuses</option>
          {[...ACTIVE_RUN_STATUSES, 'succeeded', 'failed', 'cancelled'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      {!items && <Spinner label="Loading…" />}
      {items && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>User</th>
                <th>Mode</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Cost</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td className="mono">
                    <Link to={`/chat/${r.conversation_id}`}>{shortId(r.id)}</Link>
                  </td>
                  <td><StatusChip status={r.status} /></td>
                  <td className="mono">{shortId(r.user_id)}</td>
                  <td>{r.permission_mode}</td>
                  <td className="faint">{formatRelative(r.started_at)}</td>
                  <td className="faint">{formatRelative(r.ended_at)}</td>
                  <td>{formatMoney(r.total_cost_usd)}</td>
                  <td className="faint small">{r.error || '—'}</td>
                  <td>
                    {isActiveRun(r.status) && (
                      <button className="btn btn-danger btn-sm" onClick={() => stop(r)} disabled={busy === r.id}>
                        Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <div className="empty">No runs.</div>}
        </div>
      )}
    </div>
  )
}
