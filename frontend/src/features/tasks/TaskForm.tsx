import { useEffect, useState, type FormEvent } from 'react'
import { listConnectors, listProjects, listSkills, listWorkspaces } from '@/lib/api/endpoints'
import type { Connector, PermissionMode, Project, Skill, Task, TaskIn, Workspace } from '@/lib/api/types'
import { PermissionModeSelect } from '@/features/chat/PermissionModeSelect'

interface Props {
  initial?: Task | null
  onSubmit: (body: TaskIn) => Promise<void>
  onCancel: () => void
}

export function TaskForm({ initial, onSubmit, onCancel }: Props) {
  const cfg = initial?.config || {}
  const [name, setName] = useState(initial?.name || '')
  const [prompt, setPrompt] = useState(initial?.prompt || '')
  const [mode, setMode] = useState<PermissionMode>((cfg.permission_mode as PermissionMode) || 'dontAsk')
  const [connectorIds, setConnectorIds] = useState<string[]>(cfg.connector_ids || [])
  const [skills, setSkills] = useState<string[]>(cfg.skills || [])
  const [workspaceId, setWorkspaceId] = useState(cfg.workspace_id || '')
  const [projectId, setProjectId] = useState(cfg.project_id || '')
  const [budget, setBudget] = useState(cfg.max_budget_usd != null ? String(cfg.max_budget_usd) : '')
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [allSkills, setAllSkills] = useState<Skill[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listConnectors().then((c) => setConnectors(c.filter((x) => x.enabled && x.approved))).catch(() => setConnectors([]))
    listSkills().then(setAllSkills).catch(() => setAllSkills([]))
    listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]))
    listProjects().then(setProjects).catch(() => setProjects([]))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onSubmit({
        name: name.trim(),
        prompt,
        config: {
          permission_mode: mode,
          connector_ids: connectorIds,
          skills,
          workspace_id: workspaceId || null,
          project_id: projectId || null,
          max_budget_usd: budget ? Number(budget) : null,
        },
      })
    } finally {
      setBusy(false)
    }
  }
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="tf-name">Name</label>
        <input id="tf-name" className="input" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="tf-prompt">Prompt</label>
        <textarea id="tf-prompt" className="textarea" rows={6} required value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="What should the agent do each time this task runs?" />
      </div>
      <div className="field">
        <span className="label">Permission mode</span>
        <PermissionModeSelect value={mode} onChange={setMode} />
        <span className="hint">Unattended tasks usually use "Skip prompts"; approvals would otherwise wait for a human.</span>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="tf-project">Project</label>
          <select id="tf-project" className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">None</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="tf-ws">Workspace</label>
          <select id="tf-ws" className="select" value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>
            <option value="">None</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="tf-budget">Max budget (USD)</label>
          <input id="tf-budget" className="input" type="number" min={0} max={500} step="0.5" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="none" />
        </div>
      </div>
      {connectors.length > 0 && (
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend className="label">Connectors</legend>
          <div className="row">
            {connectors.map((c) => (
              <label key={c.id} className="checkbox">
                <input type="checkbox" checked={connectorIds.includes(c.id)} onChange={() => toggle(connectorIds, setConnectorIds, c.id)} /> {c.display_name}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {allSkills.length > 0 && (
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend className="label">Skills</legend>
          <div className="row">
            {allSkills.map((s) => (
              <label key={s.id} className="checkbox">
                <input type="checkbox" checked={skills.includes(s.name)} onChange={() => toggle(skills, setSkills, s.name)} /> {s.name}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy || !name.trim() || !prompt.trim()}>
          {busy ? <span className="spinner" /> : initial ? 'Save' : 'Create'}
        </button>
      </div>
    </form>
  )
}
