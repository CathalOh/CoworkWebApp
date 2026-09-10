import { useState, type FormEvent } from 'react'
import { errorMessage } from '@/lib/api/client'
import type { ElicitationData, ElicitationIn, JsonSchemaProperty } from '@/lib/api/types'
import { toast } from '@/store/toast'

interface Props {
  request: ElicitationData
  onRespond: (body: ElicitationIn) => Promise<void>
}

/** Renders a small form from a JSON schema (string/number/integer/boolean/enum) or a link for url mode. */
export function ElicitationCard({ request, onRespond }: Props) {
  const schema = request.requestedSchema || request.request_schema || {}
  const props = schema.properties || {}
  const required = new Set(schema.required || [])
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {}
    for (const [k, p] of Object.entries(props)) if (p.default !== undefined) init[k] = p.default
    return init
  })
  const [busy, setBusy] = useState<string | null>(null)

  const send = async (action: ElicitationIn['action'], content?: Record<string, unknown>) => {
    setBusy(action)
    try {
      await onRespond({ elicitation_id: request.elicitation_id, action, content: content ?? null })
    } catch (e) {
      toast.error('Could not respond', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const content: Record<string, unknown> = {}
    for (const [k, p] of Object.entries(props)) {
      const v = values[k]
      if (v === undefined || v === '') continue
      content[k] = p.type === 'number' || p.type === 'integer' ? Number(v) : v
    }
    void send('accept', content)
  }
  const set = (k: string, v: unknown) => setValues((s) => ({ ...s, [k]: v }))

  return (
    <section className="elicitation" aria-label="Input requested" aria-live="polite">
      <div className="row mb">
        <strong>Input requested</strong>
        <span className="badge badge-info">{request.mode}</span>
      </div>
      {request.message && <p>{request.message}</p>}
      {request.mode === 'url' ? (
        <div className="stack">
          {request.url && (
            <a className="btn btn-primary" href={request.url} target="_blank" rel="noopener noreferrer" style={{ alignSelf: 'flex-start' }}>
              Open link
            </a>
          )}
          <div className="row">
            <button className="btn" onClick={() => send('accept')} disabled={!!busy}>
              I'm done
            </button>
            <button className="btn btn-ghost" onClick={() => send('decline')} disabled={!!busy}>
              Decline
            </button>
            <button className="btn btn-ghost" onClick={() => send('cancel')} disabled={!!busy}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit}>
          {Object.entries(props).map(([k, p]) => (
            <SchemaField key={k} name={k} prop={p} required={required.has(k)} value={values[k]} onChange={(v) => set(k, v)} elicitationId={request.elicitation_id} />
          ))}
          <div className="row">
            <button className="btn btn-primary" type="submit" disabled={!!busy}>
              {busy === 'accept' ? <span className="spinner" /> : 'Submit'}
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => send('decline')} disabled={!!busy}>
              Decline
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => send('cancel')} disabled={!!busy}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

function SchemaField({ name, prop, required, value, onChange, elicitationId }: { name: string; prop: JsonSchemaProperty; required: boolean; value: unknown; onChange: (v: unknown) => void; elicitationId: string }) {
  const id = `elic-${elicitationId}-${name}`
  const label = prop.title || name
  if (prop.type === 'boolean') {
    return (
      <div className="field">
        <label className="checkbox" htmlFor={id}>
          <input id={id} type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} /> {label}
        </label>
        {prop.description && <span className="hint">{prop.description}</span>}
      </div>
    )
  }
  if (prop.enum) {
    return (
      <div className="field">
        <label htmlFor={id}>
          {label}
          {required && ' *'}
        </label>
        <select id={id} className="select" required={required} value={value === undefined ? '' : String(value)} onChange={(e) => onChange(e.target.value)}>
          <option value="">Select…</option>
          {prop.enum.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
        {prop.description && <span className="hint">{prop.description}</span>}
      </div>
    )
  }
  const numeric = prop.type === 'number' || prop.type === 'integer'
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && ' *'}
      </label>
      <input
        id={id}
        className="input"
        type={numeric ? 'number' : prop.format === 'email' ? 'email' : 'text'}
        step={prop.type === 'integer' ? 1 : 'any'}
        required={required}
        value={value === undefined ? '' : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
      {prop.description && <span className="hint">{prop.description}</span>}
    </div>
  )
}
