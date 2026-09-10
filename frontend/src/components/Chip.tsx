import type { ReactNode } from 'react'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

export function Chip({ tone = 'neutral', children, dot, title }: { tone?: Tone; children: ReactNode; dot?: boolean; title?: string }) {
  return (
    <span className={`chip ${tone !== 'neutral' ? `chip-${tone}` : ''}`} title={title}>
      {dot && <span className="dot" aria-hidden="true" />}
      {children}
    </span>
  )
}

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case 'connected':
    case 'succeeded':
    case 'active':
    case 'ok':
      return 'success'
    case 'needs-auth':
    case 'pending':
    case 'waiting_approval':
    case 'waiting_elicitation':
    case 'queued':
      return 'warning'
    case 'failed':
    case 'revoked':
    case 'disabled':
    case 'cancelled':
      return 'danger'
    case 'running':
      return 'info'
    default:
      return 'neutral'
  }
}

export function StatusChip({ status }: { status: string | null | undefined }) {
  return (
    <Chip tone={statusTone(status)} dot>
      {status || 'unknown'}
    </Chip>
  )
}
