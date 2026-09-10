import { useId, type ReactNode } from 'react'

interface Props {
  label: string
  hint?: string
  children: (id: string) => ReactNode
}

/** Accessible label/control pairing without needing to hand-roll ids. */
export function Field({ label, hint, children }: Props) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}
