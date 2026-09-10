import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { JsonView } from '@/components/JsonView'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminAudit, adminAuditExportUrl, adminAuditVerify } from '@/lib/api/endpoints'
import type { AuditEvent, AuditFilters } from '@/lib/api/types'
import { formatDate, shortId } from '@/lib/format'
import { toast } from '@/store/toast'

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({})
  const [draft, setDraft] = useState<AuditFilters>({})
  const [items, setItems] = useState<AuditEvent[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [verify, setVerify] = useState<Record<string, unknown> | null>(null)
  const [verifying, setVerifying] = useState(false)

  const load = useCallback(
    async (f: AuditFilters, append: boolean) => {
      setLoading(true)
      try {
        const page = await adminAudit({ ...f, limit: 100 })
        setItems((cur) => (append ? [...cur, ...page.items] : page.items))
        setCursor(page.next_cursor)
      } catch (e) {
        toast.error('Could not load audit log', errorMessage(e))
      } finally {
        setLoading(false)
      }
    },
    [],
  )
  useEffect(() => {
    void load(filters, false)
  }, [filters, load])

  const apply = (e: FormEvent) => {
    e.preventDefault()
    const f: AuditFilters = {}
    for (const [k, v] of Object.entries(draft)) if (v) (f as Record<string, unknown>)[k] = k === 'since' || k === 'until' ? new Date(String(v)).toISOString() : v
    setFilters(f)
  }
  const runVerify = async () => {
    setVerifying(true)
    try {
      setVerify(await adminAuditVerify())
    } catch (e) {
      toast.error('Verification failed', errorMessage(e))
    } finally {
      setVerifying(false)
    }
  }
  const set = (k: keyof AuditFilters) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }))

  return (
    <div>
      <div className="page-header">
        <h1>Audit log</h1>
        <div className="row">
          <button className="btn" onClick={runVerify} disabled={verifying}>
            {verifying ? <span className="spinner" /> : 'Verify chain'}
          </button>
          <a className="btn" href={adminAuditExportUrl(filters.since)} target="_blank" rel="noopener noreferrer">
            Export JSONL
          </a>
        </div>
      </div>
      {verify && <VerifyResult result={verify} />}
      <form className="filters" onSubmit={apply}>
        <div className="field">
          <label htmlFor="af-actor">Actor id</label>
          <input id="af-actor" className="input" value={draft.actor_id || ''} onChange={set('actor_id')} placeholder="uuid" />
        </div>
        <div className="field">
          <label htmlFor="af-action">Action prefix</label>
          <input id="af-action" className="input" value={draft.action || ''} onChange={set('action')} placeholder="e.g. project." />
        </div>
        <div className="field">
          <label htmlFor="af-entity">Entity type</label>
          <input id="af-entity" className="input" value={draft.entity_type || ''} onChange={set('entity_type')} placeholder="run, project…" />
        </div>
        <div className="field">
          <label htmlFor="af-since">Since</label>
          <input id="af-since" className="input" type="datetime-local" value={draft.since || ''} onChange={set('since')} />
        </div>
        <div className="field">
          <label htmlFor="af-until">Until</label>
          <input id="af-until" className="input" type="datetime-local" value={draft.until || ''} onChange={set('until')} />
        </div>
        <button className="btn btn-primary" type="submit">
          Apply
        </button>
        <button className="btn btn-ghost" type="button" onClick={() => { setDraft({}); setFilters({}) }}>
          Reset
        </button>
      </form>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Entity</th>
              <th>IP</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {items.map((ev) => (
              <tr key={ev.id}>
                <td className="faint" style={{ whiteSpace: 'nowrap' }}>{formatDate(ev.ts)}</td>
                <td className="mono">{ev.action}</td>
                <td className="mono" title={ev.actor_id || ''}>
                  {ev.actor_type === 'service' ? 'service' : shortId(ev.actor_id)}
                </td>
                <td className="mono" title={ev.entity_id || ''}>
                  {ev.entity_type} {shortId(ev.entity_id)}
                </td>
                <td className="faint">{ev.ip || '—'}</td>
                <td>
                  {(ev.before || ev.after) ? (
                    <details>
                      <summary className="small" style={{ cursor: 'pointer' }}>before / after</summary>
                      <div className="grid-2" style={{ marginTop: 6 }}>
                        <div>
                          <div className="label">Before</div>
                          <JsonView value={ev.before} maxHeight={200} />
                        </div>
                        <div>
                          <div className="label">After</div>
                          <JsonView value={ev.after} maxHeight={200} />
                        </div>
                      </div>
                      <div className="faint small mono mt">req {ev.request_id || '—'} · hash {ev.row_hash?.slice(0, 12) || '—'}</div>
                    </details>
                  ) : (
                    <span className="faint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && !loading && <div className="empty">No audit events match.</div>}
      </div>
      <div className="row mt">
        {loading && <Spinner label="Loading…" />}
        {cursor && !loading && (
          <button className="btn" onClick={() => load({ ...filters, cursor }, true)}>
            Load more
          </button>
        )}
      </div>
    </div>
  )
}

function VerifyResult({ result }: { result: Record<string, unknown> }) {
  // Shape is backend-defined; render generically: top-level ok + per-stream {ok, checked} when present.
  const entries = Object.entries(result).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v)) as Array<[string, Record<string, unknown>]>
  const streams = (result.streams && typeof result.streams === 'object' ? Object.entries(result.streams as Record<string, Record<string, unknown>>) : entries)
  const ok = result.ok
  return (
    <section className={`card mb`} style={{ borderColor: ok === false ? 'var(--danger)' : ok === true ? 'var(--success)' : undefined }} aria-live="polite">
      <div className="card-title">
        <h3>Chain verification</h3>
        {typeof ok === 'boolean' && <span className={`chip ${ok ? 'chip-success' : 'chip-danger'}`}>{ok ? 'OK' : 'BROKEN'}</span>}
      </div>
      {streams.length > 0 ? (
        <table className="table">
          <thead>
            <tr>
              <th>Stream</th>
              <th>OK</th>
              <th>Checked</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {streams.map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td>{String(v.ok ?? '—')}</td>
                <td>{String(v.checked ?? v.count ?? '—')}</td>
                <td className="faint small">{String(v.error ?? v.first_bad_id ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <JsonView value={result} />
      )}
    </section>
  )
}
