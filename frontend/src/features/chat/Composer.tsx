import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { Effort, PermissionMode } from '@/lib/api/types'
import { PermissionModeSelect } from './PermissionModeSelect'

interface Props {
  disabled?: boolean
  busy?: boolean
  mode: PermissionMode
  onModeChange: (m: PermissionMode) => void
  onSend: (content: string, opts: { max_budget_usd?: number; model?: string; effort?: Effort }) => Promise<void>
  onStop?: () => void
  defaultModel?: string
}

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'xhigh', 'max']

export function Composer({ disabled, busy, mode, onModeChange, onSend, onStop, defaultModel }: Props) {
  const [text, setText] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [budget, setBudget] = useState('')
  const [model, setModel] = useState('')
  const [effort, setEffort] = useState<Effort | ''>('')
  const [sending, setSending] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(240, el.scrollHeight)}px`
  }, [text])

  const submit = async () => {
    const content = text.trim()
    if (!content || sending || disabled || busy) return
    setSending(true)
    try {
      await onSend(content, {
        max_budget_usd: budget ? Number(budget) : undefined,
        model: model.trim() || undefined,
        effort: effort || undefined,
      })
      setText('')
    } finally {
      setSending(false)
      ref.current?.focus()
    }
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer-inner">
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={busy ? 'A run is in progress…' : 'Message Cowork  (Enter to send, Shift+Enter for newline)'}
          disabled={disabled}
          rows={2}
        />
        <div className="composer-bar">
          <PermissionModeSelect value={mode} onChange={onModeChange} disabled={busy} />
          <span className="grow" />
          <button className="btn btn-ghost btn-sm" onClick={() => setShowAdvanced((v) => !v)} aria-expanded={showAdvanced}>
            {showAdvanced ? 'Hide options' : 'Options'}
          </button>
          {busy ? (
            <button className="btn btn-danger" onClick={onStop} aria-label="Stop the current run">
              ■ Stop
            </button>
          ) : (
            <button className="btn btn-primary" onClick={submit} disabled={disabled || !text.trim() || sending} aria-label="Send message">
              {sending ? <span className="spinner" /> : 'Send'}
            </button>
          )}
        </div>
        {showAdvanced && (
          <div className="row mt" style={{ gap: 12 }}>
            <label className="row small" style={{ gap: 4 }}>
              Budget (USD)
              <input className="input" style={{ width: 90 }} type="number" min={0} max={500} step="0.5" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="none" />
            </label>
            <label className="row small" style={{ gap: 4 }}>
              Model
              <input className="input" style={{ width: 200 }} value={model} onChange={(e) => setModel(e.target.value)} placeholder={defaultModel || 'default'} />
            </label>
            <label className="row small" style={{ gap: 4 }}>
              Effort
              <select className="select" style={{ width: 110 }} value={effort} onChange={(e) => setEffort(e.target.value as Effort | '')}>
                <option value="">default</option>
                {EFFORTS.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>
    </div>
  )
}
