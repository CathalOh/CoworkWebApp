import type { SlotContext } from './registry'

/**
 * Demo panel contributed by bundles whose manifest lists `ui_slots: ["kpi-panel"]` (e.g. the seeded
 * "finance-ops" bundle). Registered under `project.panel` in slots/index.ts.
 */
export function KpiPanel({ bundle }: SlotContext) {
  const kpis = [
    { label: 'Revenue (QTD)', value: '$4.2M', delta: '+6.1%' },
    { label: 'Gross margin', value: '61%', delta: '+0.8 pt' },
    { label: 'Open invoices', value: '128', delta: '-12' },
    { label: 'Runway', value: '19 mo', delta: '' },
  ]
  return (
    <section className="card" aria-label="KPI panel">
      <div className="card-title">
        <h3>KPI panel</h3>
        <span className="badge badge-info">{bundle?.name || 'bundle'} · ui slot</span>
      </div>
      <div className="grid-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
        {kpis.map((k) => (
          <div key={k.label} style={{ padding: '8px 10px', background: 'var(--bg-sunken)', borderRadius: 8 }}>
            <div className="small subtle">{k.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{k.value}</div>
            {k.delta && <div className="small faint">{k.delta}</div>}
          </div>
        ))}
      </div>
      <p className="small faint mt">Demo data. A real cowork-project panel would read from the bundle's live source or a connector.</p>
    </section>
  )
}
