import { useId } from 'react'
import type { PermissionMode } from '@/lib/api/types'
import { DELETION_NOTE, PERMISSION_MODES } from './permissionModes'

interface Props {
  value: PermissionMode
  onChange: (m: PermissionMode) => void
  compact?: boolean
  disabled?: boolean
}

export function PermissionModeSelect({ value, onChange, compact, disabled }: Props) {
  const id = useId()
  const current = PERMISSION_MODES.find((m) => m.value === value) || PERMISSION_MODES[0]
  return (
    <div className="mode-select">
      <label htmlFor={id} className="sr-only">
        Permission mode
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as PermissionMode)} disabled={disabled} title={current.description}>
        {PERMISSION_MODES.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
      {!compact && (
        <span className="mode-desc">
          {current.description} {DELETION_NOTE}
        </span>
      )}
    </div>
  )
}
