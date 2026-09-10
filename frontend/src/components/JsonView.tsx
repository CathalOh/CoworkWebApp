import { pretty } from '@/lib/format'

export function JsonView({ value, maxHeight }: { value: unknown; maxHeight?: number }) {
  if (value === null || value === undefined) return <span className="faint">—</span>
  return (
    <pre className="json" style={maxHeight ? { maxHeight } : undefined}>
      {pretty(value)}
    </pre>
  )
}
