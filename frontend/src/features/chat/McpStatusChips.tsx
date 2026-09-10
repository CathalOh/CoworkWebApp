import { Link } from 'react-router-dom'
import { Chip, statusTone } from '@/components/Chip'
import type { McpServerStatus } from '@/lib/api/types'

export function McpStatusChips({ servers }: { servers: McpServerStatus[] }) {
  if (!servers.length) return null
  return (
    <div className="row" aria-label="Connector status">
      {servers.map((s) => (
        <Chip key={s.name} tone={statusTone(s.status)} dot title={`${s.name}: ${s.status}`}>
          {s.name}
          {s.status === 'needs-auth' ? <Link to="/connectors">connect</Link> : <span className="faint">{s.status}</span>}
        </Chip>
      ))}
    </div>
  )
}
