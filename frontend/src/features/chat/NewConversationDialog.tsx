import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { listConnectors, listProjects, listSkills, listWorkspaces } from '@/lib/api/endpoints'
import type { Connector, PermissionMode, Project, Skill, Workspace } from '@/lib/api/types'
import { useChatStore } from '@/store/chat'
import { toast } from '@/store/toast'
import { PermissionModeSelect } from './PermissionModeSelect'

interface Props {
  open: boolean
  onClose: () => void
  defaultProjectId?: string | null
}

export function NewConversationDialog({ open, onClose, defaultProjectId }: Props) {
  const nav = useNavigate()
  const create = useChatStore((s) => s.create)
  const [title, setTitle] = useState('')
  const [projectId, setProjectId] = useState('')
  const [workspaceId, setWorkspaceId] = useState('')
  const [mode, setMode] = useState<PermissionMode>('default')
  const [connectorIds, setConnectorIds] = useState<string[]>([])
  const [skillNames, setSkillNames] = useState<string[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setTitle('')
    setProjectId(defaultProjectId || '')
    setConnectorIds([])
    setSkillNames([])
    Promise.all([listProjects().catch(() => []), listWorkspaces().catch(() => []), listConnectors().catch(() => []), listSkills().catch(() => [])]).then(
      ([p, w, c, s]) => {
        setProjects(p)
        setWorkspaces(w)
        setConnectors(c.filter((x) => x.enabled && x.approved))
        setSkills(s)
      },
    )
  }, [open, defaultProjectId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const c = await create({
        title: title.trim() || null,
        project_id: projectId || null,
        workspace_id: workspaceId || null,
        permission_mode: mode,
        connector_ids: connectorIds.length ? connectorIds : null,
        skill_names: skillNames.length ? skillNames : null,
      })
      onClose()
      nav(`/chat/${c.id}`)
    } catch (err) {
      toast.error('Could not create conversation', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  return (
    <Modal open={open} onClose={onClose} title="New conversation">
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="nc-title">Title</label>
          <input id="nc-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional" />
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="nc-project">Project</label>
            <select id="nc-project" className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">None</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="nc-ws">Workspace</label>
            <select id="nc-ws" className="select" value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>
              <option value="">Project default / scratch</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <span className="label">Permission mode</span>
          <PermissionModeSelect value={mode} onChange={setMode} />
        </div>
        {connectors.length > 0 && (
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend className="label">Connectors</legend>
            <div className="row">
              {connectors.map((c) => (
                <label key={c.id} className="checkbox">
                  <input type="checkbox" checked={connectorIds.includes(c.id)} onChange={() => toggle(connectorIds, setConnectorIds, c.id)} />
                  {c.display_name}
                  {c.status === 'needs-auth' && <span className="badge badge-warning">needs auth</span>}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {skills.length > 0 && (
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend className="label">Skills</legend>
            <div className="row">
              {skills.map((s) => (
                <label key={s.id} className="checkbox">
                  <input type="checkbox" checked={skillNames.includes(s.name)} onChange={() => toggle(skillNames, setSkillNames, s.name)} />
                  {s.name}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <span className="spinner" /> : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
