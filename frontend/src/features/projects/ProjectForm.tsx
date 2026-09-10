import { useEffect, useState, type FormEvent } from 'react'
import { listBundles, listTeams, listWorkspaces } from '@/lib/api/endpoints'
import type { Bundle, Project, ProjectIn, Team, Workspace } from '@/lib/api/types'

interface Props {
  initial?: Project | null
  onSubmit: (body: ProjectIn) => Promise<void>
  onCancel?: () => void
  submitLabel?: string
}

export function ProjectForm({ initial, onSubmit, onCancel, submitLabel = 'Save' }: Props) {
  const [name, setName] = useState(initial?.name || '')
  const [instructions, setInstructions] = useState(initial?.instructions || '')
  const [memory, setMemory] = useState(initial?.memory_enabled ?? true)
  const [workspaceId, setWorkspaceId] = useState(initial?.workspace_id || '')
  const [bundleId, setBundleId] = useState(initial?.bundle_id || '')
  const [teamId, setTeamId] = useState(initial?.team_id || '')
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [bundles, setBundles] = useState<Bundle[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]))
    listBundles().then(setBundles).catch(() => setBundles([]))
    listTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onSubmit({
        name: name.trim(),
        instructions: instructions.trim() || null,
        memory_enabled: memory,
        workspace_id: workspaceId || null,
        bundle_id: bundleId || null,
        ...(initial ? {} : { team_id: teamId || null }),
      })
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="pf-name">Name</label>
        <input id="pf-name" className="input" required value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
      </div>
      <div className="field">
        <label htmlFor="pf-instr">Instructions</label>
        <textarea id="pf-instr" className="textarea" rows={5} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="System guidance applied to every conversation in this project" />
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="pf-ws">Workspace</label>
          <select id="pf-ws" className="select" value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>
            <option value="">None (scratch per run)</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="pf-bundle">Bundle (cowork-project)</label>
          <select id="pf-bundle" className="select" value={bundleId} onChange={(e) => setBundleId(e.target.value)}>
            <option value="">None</option>
            {bundles.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>
        {!initial && (
          <div className="field">
            <label htmlFor="pf-team">Team (optional)</label>
            <select id="pf-team" className="select" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">Personal</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="field">
        <label className="checkbox">
          <input type="checkbox" checked={memory} onChange={(e) => setMemory(e.target.checked)} /> Memory enabled
        </label>
        <span className="hint">When on, facts learned in this project's conversations are stored and recalled later.</span>
      </div>
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={busy || !name.trim()}>
          {busy ? <span className="spinner" /> : submitLabel}
        </button>
      </div>
    </form>
  )
}
