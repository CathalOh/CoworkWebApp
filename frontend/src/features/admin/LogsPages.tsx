import { useCallback, useEffect, useState } from 'react'
import { JsonView } from '@/components/JsonView'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminAppLogs, adminLlmLogs } from '@/lib/api/endpoints'
import type { AppLog, LlmLog } from '@/lib/api/types'
import { formatDate, formatMoney, formatNumber, shortId } from '@/lib/format'
import { toast } from '@/store/toast'

export function LlmLogsPage() {
  const [userId, setUserId] = useState('')
  const [runId, setRunId] = useState('')
  const [applied, setApplied] = useState({ user_id: '', run_id: '' })
  const [items, setItems] = useState<LlmLog[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(async (c: string | undefined, append: boolean) => {
    setLoading(true)
    try {
      const page = await adminLlmLogs({ user_id: applied.user_id || undefined, run_id: applied.run_id || undefined, cursor: c, limit: 100 })
      setItems((cur) => (append ? [...cur, ...page.items] : page.items))
      setCursor(page.next_cursor)
    } catch (e) {
      toast.error('Could not load LLM logs', errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [applied])
  useEffect(() => {
    void load(undefined, false)
  }, [load])
  return (
    <div>
      <div className="page-header">
        <h1>LLM request logs</h1>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setApplied({ user_id: userId.trim(), run_id: runId.trim() }) }}>
        <div className="field">
          <label htmlFor="ll-user">User id</label>
          <input id="ll-user" className="input" value={userId} onChange={(e) => setUserId(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="ll-run">Run id</label>
          <input id="ll-run" className="input" value={runId} onChange={(e) => setRunId(e.target.value)} />
        </div>
        <button className="btn btn-primary" type="submit">Apply</button>
      </form>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Model</th>
              <th>Run</th>
              <th>User</th>
              <th>In</th>
              <th>Out</th>
              <th>Cache</th>
              <th>Cost</th>
              <th>Latency</th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td className="faint" style={{ whiteSpace: 'nowrap' }}>{formatDate(r.ts)}</td>
                <td className="mono">{r.model_id || '—'}</td>
                <td className="mono">{shortId(r.run_id)}</td>
                <td className="mono">{shortId(r.user_id)}</td>
                <td>{formatNumber(r.input_tokens)}</td>
                <td>{formatNumber(r.output_tokens)}</td>
                <td>{formatNumber(r.cache_read_tokens)}</td>
                <td>{formatMoney(r.cost_usd)}</td>
                <td>{r.latency_ms != null ? `${r.latency_ms} ms` : '—'}</td>
                <td>
                  <details>
                    <summary className="small" style={{ cursor: 'pointer' }}>request / response</summary>
                    <div className="grid-2" style={{ marginTop: 6, minWidth: 420 }}>
                      <JsonView value={r.request} maxHeight={240} />
                      <JsonView value={r.response} maxHeight={240} />
                    </div>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && !loading && <div className="empty">No LLM requests logged.</div>}
      </div>
      <div className="row mt">
        {loading && <Spinner />}
        {cursor && !loading && <button className="btn" onClick={() => load(cursor, true)}>Load more</button>}
      </div>
    </div>
  )
}

const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

export function AppLogsPage() {
  const [level, setLevel] = useState('')
  const [reqId, setReqId] = useState('')
  const [applied, setApplied] = useState({ level: '', request_id: '' })
  const [items, setItems] = useState<AppLog[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(async (c: string | undefined, append: boolean) => {
    setLoading(true)
    try {
      const page = await adminAppLogs({ level: applied.level || undefined, request_id_filter: applied.request_id || undefined, cursor: c, limit: 200 })
      setItems((cur) => (append ? [...cur, ...page.items] : page.items))
      setCursor(page.next_cursor)
    } catch (e) {
      toast.error('Could not load app logs', errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [applied])
  useEffect(() => {
    void load(undefined, false)
  }, [load])
  const tone = (l: string) => (l === 'ERROR' || l === 'CRITICAL' ? 'chip-danger' : l === 'WARNING' ? 'chip-warning' : '')
  return (
    <div>
      <div className="page-header">
        <h1>Application logs</h1>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setApplied({ level, request_id: reqId.trim() }) }}>
        <div className="field">
          <label htmlFor="al-level">Level</label>
          <select id="al-level" className="select" value={level} onChange={(e) => setLevel(e.target.value)}>
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l || 'any'}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="al-req">Request id</label>
          <input id="al-req" className="input" value={reqId} onChange={(e) => setReqId(e.target.value)} />
        </div>
        <button className="btn btn-primary" type="submit">Apply</button>
      </form>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Level</th>
              <th>Logger</th>
              <th>Message</th>
              <th>Request</th>
              <th>Context</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td className="faint" style={{ whiteSpace: 'nowrap' }}>{formatDate(r.ts)}</td>
                <td><span className={`chip ${tone(r.level)}`}>{r.level}</span></td>
                <td className="mono">{r.logger}</td>
                <td>{r.message}</td>
                <td className="mono faint">{r.request_id || '—'}</td>
                <td>{r.context ? <details><summary className="small" style={{ cursor: 'pointer' }}>context</summary><JsonView value={r.context} maxHeight={200} /></details> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && !loading && <div className="empty">No log entries.</div>}
      </div>
      <div className="row mt">
        {loading && <Spinner />}
        {cursor && !loading && <button className="btn" onClick={() => load(cursor, true)}>Load more</button>}
      </div>
    </div>
  )
}
