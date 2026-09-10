import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Modal } from '@/components/Modal'
import { StatusChip } from '@/components/Chip'
import { errorMessage } from '@/lib/api/client'
import { listConnectors } from '@/lib/api/endpoints'
import type { Connector, Conversation } from '@/lib/api/types'
import { useChatStore } from '@/store/chat'
import { toast } from '@/store/toast'

/** Per-conversation connector selection → PATCH /v1/conversations/{id} {connector_ids}. */
export function ConnectorPicker({ conversation, open, onClose }: { conversation: Conversation; open: boolean; onClose: () => void }) {
  const update = useChatStore((s) => s.update)
  const [all, setAll] = useState<Connector[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setSelected(conversation.connector_ids || [])
    listConnectors()
      .then((c) => setAll(c.filter((x) => x.enabled && x.approved)))
      .catch((e) => toast.error('Could not load connectors', errorMessage(e)))
  }, [open, conversation])

  const save = async () => {
    setBusy(true)
    try {
      await update(conversation.id, { connector_ids: selected })
      toast.success('Connectors updated')
      onClose()
    } catch (e) {
      toast.error('Could not update connectors', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title="Connectors for this conversation">
      {!all.length && <p className="subtle">No approved connectors are available to you.</p>}
      <ul className="list">
        {all.map((c) => (
          <li key={c.id} className="list-item">
            <label className="checkbox" style={{ flex: 1 }}>
              <input type="checkbox" checked={selected.includes(c.id)} onChange={() => setSelected((s) => (s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id]))} />
              {c.display_name}
              <span className="faint small">{c.description}</span>
            </label>
            <StatusChip status={c.status} />
          </li>
        ))}
      </ul>
      <p className="small faint mt">
        Connectors needing authorization can be connected on the <Link to="/connectors">Connectors</Link> page.
      </p>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={save} disabled={busy}>
          {busy ? <span className="spinner" /> : 'Save'}
        </button>
      </div>
    </Modal>
  )
}
