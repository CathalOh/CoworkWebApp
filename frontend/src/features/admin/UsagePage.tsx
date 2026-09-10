import { useEffect, useState } from 'react'
import { Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { adminUsage } from '@/lib/api/endpoints'
import type { UsageSummary } from '@/lib/api/types'
import { formatMoney, formatNumber } from '@/lib/format'
import { toast } from '@/store/toast'

const GROUPS = ['user', 'team', 'project', 'model']
const DAYS = [7, 30, 90]

export function UsagePage() {
  const [groupBy, setGroupBy] = useState('user')
  const [days, setDays] = useState(30)
  const [data, setData] = useState<UsageSummary | null>(null)
  useEffect(() => {
    setData(null)
    adminUsage(groupBy, days).then(setData).catch((e) => toast.error('Could not load usage', errorMessage(e)))
  }, [groupBy, days])
  const items = (data?.items || []).slice().sort((a, b) => b.cost_usd - a.cost_usd)
  const maxCost = Math.max(0.000001, ...items.map((i) => i.cost_usd))
  const totals = items.reduce((acc, i) => ({ runs: acc.runs + i.runs, cost: acc.cost + i.cost_usd, inp: acc.inp + i.input_tokens, out: acc.out + i.output_tokens }), { runs: 0, cost: 0, inp: 0, out: 0 })
  return (
    <div>
      <div className="page-header">
        <h1>Usage</h1>
        <div className="row">
          <label className="row small" style={{ gap: 4 }}>
            Group by
            <select className="select" style={{ width: 'auto' }} value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
              {GROUPS.map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          </label>
          <label className="row small" style={{ gap: 4 }}>
            Window
            <select className="select" style={{ width: 'auto' }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAYS.map((d) => (
                <option key={d} value={d}>{d} days</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <div className="grid-2 mb" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
        <Stat label="Total cost" value={formatMoney(totals.cost)} />
        <Stat label="Runs" value={formatNumber(totals.runs)} />
        <Stat label="Input tokens" value={formatNumber(totals.inp)} />
        <Stat label="Output tokens" value={formatNumber(totals.out)} />
      </div>
      {!data && <Spinner label="Loading…" />}
      {data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{groupBy}</th>
                <th style={{ width: '30%' }}>Cost</th>
                <th>Runs</th>
                <th>Input</th>
                <th>Output</th>
                <th>Cache read</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i, idx) => (
                <tr key={i.key ?? `null-${idx}`}>
                  <td className="mono">{i.key ?? <span className="faint">(none)</span>}</td>
                  <td>
                    <span className="bar-inline" style={{ width: `${Math.max(2, (i.cost_usd / maxCost) * 100)}%` }} aria-hidden="true" />{' '}
                    <span className="small">{formatMoney(i.cost_usd)}</span>
                  </td>
                  <td>{formatNumber(i.runs)}</td>
                  <td>{formatNumber(i.input_tokens)}</td>
                  <td>{formatNumber(i.output_tokens)}</td>
                  <td>{formatNumber(i.cache_read)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <div className="empty">No usage in this window.</div>}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card" style={{ padding: '10px 14px' }}>
      <div className="small subtle">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  )
}
