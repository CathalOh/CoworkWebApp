import { useState } from 'react'
import { Modal } from './Modal'

interface Props {
  open: boolean
  title: string
  message?: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => Promise<void> | void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', danger, onConfirm, onCancel }: Props) {
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try {
      await onConfirm()
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      {message && <p className="subtle">{message}</p>}
      <div className="form-actions">
        <button className="btn" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={go} disabled={busy} autoFocus>
          {busy ? <span className="spinner" /> : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

/** Small hook that returns a confirm() function backed by the dialog. */
export function useConfirm() {
  const [state, setState] = useState<{ open: boolean; title: string; message?: string; danger?: boolean; confirmLabel?: string; resolve?: (v: boolean) => void }>({ open: false, title: '' })
  const confirm = (title: string, opts: { message?: string; danger?: boolean; confirmLabel?: string } = {}) =>
    new Promise<boolean>((resolve) => setState({ open: true, title, ...opts, resolve }))
  const dialog = (
    <ConfirmDialog
      open={state.open}
      title={state.title}
      message={state.message}
      danger={state.danger}
      confirmLabel={state.confirmLabel}
      onConfirm={() => {
        state.resolve?.(true)
        setState({ open: false, title: '' })
      }}
      onCancel={() => {
        state.resolve?.(false)
        setState({ open: false, title: '' })
      }}
    />
  )
  return { confirm, dialog }
}
