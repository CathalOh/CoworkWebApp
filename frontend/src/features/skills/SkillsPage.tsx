import { useEffect, useState, type FormEvent } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createSkill, deleteSkill, importSkill, listSkills, listTeams, updateSkill } from '@/lib/api/endpoints'
import type { Skill, SkillIn, Team } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'

/** Layout with sub-navigation for Skills / Plugins / Memory. */
export function SkillsLayout() {
  return (
    <div className="page">
      <div className="page-narrow">
        <div className="tabs" role="navigation" aria-label="Extensions">
          <NavLink to="/skills" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Skills
          </NavLink>
          <NavLink to="/skills/plugins" className={({ isActive }) => (isActive ? 'active' : '')}>
            Plugins
          </NavLink>
          <NavLink to="/skills/memory" className={({ isActive }) => (isActive ? 'active' : '')}>
            Memory
          </NavLink>
        </div>
        <Outlet />
      </div>
    </div>
  )
}

const EMPTY: SkillIn = { name: '', description: '', body: '', allowed_tools: [], scope: 'user', team_id: null }

export function SkillsPage() {
  const user = useAuthStore((s) => s.user)
  const hasRole = useAuthStore((s) => s.hasRole)
  const [skills, setSkills] = useState<Skill[] | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [editing, setEditing] = useState<{ id?: string; form: SkillIn } | null>(null)
  const [importing, setImporting] = useState(false)
  const [skillMd, setSkillMd] = useState('')
  const [importScope, setImportScope] = useState<'user' | 'team' | 'org'>('user')
  const [importTeam, setImportTeam] = useState('')
  const [busy, setBusy] = useState(false)
  const { confirm, dialog } = useConfirm()
  const reload = () => listSkills().then(setSkills).catch((e) => toast.error('Could not load skills', errorMessage(e)))
  useEffect(() => {
    void reload()
    listTeams().then(setTeams).catch(() => setTeams([]))
  }, [])

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!editing) return
    setBusy(true)
    try {
      const body: SkillIn = { ...editing.form, team_id: editing.form.scope === 'team' ? editing.form.team_id || null : null, description: editing.form.description || null }
      if (editing.id) await updateSkill(editing.id, body)
      else await createSkill(body)
      toast.success('Skill saved')
      setEditing(null)
      await reload()
    } catch (err) {
      toast.error('Could not save skill', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const doImport = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const s = await importSkill(skillMd, importScope, importScope === 'team' ? importTeam : null)
      toast.success('Skill imported', s.name)
      setImporting(false)
      setSkillMd('')
      await reload()
    } catch (err) {
      toast.error('Import failed', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const del = async (s: Skill) => {
    if (!(await confirm(`Delete skill "${s.name}"?`, { danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteSkill(s.id)
      await reload()
    } catch (err) {
      toast.error('Could not delete skill', errorMessage(err))
    }
  }
  const canEdit = (s: Skill) => s.owner_id === user?.id || hasRole('org_admin')
  const setForm = (patch: Partial<SkillIn>) => setEditing((ed) => (ed ? { ...ed, form: { ...ed.form, ...patch } } : ed))

  return (
    <>
      <div className="page-header">
        <h1>Skills</h1>
        <div className="row">
          <button className="btn" onClick={() => setImporting(true)}>
            Import SKILL.md
          </button>
          <button className="btn btn-primary" onClick={() => setEditing({ form: { ...EMPTY } })}>
            + New skill
          </button>
        </div>
      </div>
      {!skills && <Spinner label="Loading…" />}
      {skills && !skills.length && <EmptyState title="No skills">Skills are reusable instructions (SKILL.md) the agent can load on demand.</EmptyState>}
      {skills?.map((s) => (
        <section key={s.id} className="card" aria-label={s.name}>
          <div className="card-title">
            <h3 className="mono">{s.name}</h3>
            <div className="row">
              <span className="chip">{s.scope}</span>
              {!s.enabled && <span className="badge">disabled</span>}
            </div>
          </div>
          <p className="subtle small">{s.description || 'No description'}</p>
          {s.allowed_tools?.length ? <div className="small faint mb">Allowed tools: {s.allowed_tools.join(', ')}</div> : null}
          <details className="collapsible">
            <summary>Body ({s.body.length} chars)</summary>
            <div className="body">
              <pre className="json">{s.body}</pre>
            </div>
          </details>
          <div className="row mt">
            {canEdit(s) && (
              <>
                <button className="btn btn-sm" onClick={() => setEditing({ id: s.id, form: { name: s.name, description: s.description || '', body: s.body, allowed_tools: s.allowed_tools || [], scope: s.scope as SkillIn['scope'], team_id: s.team_id } })}>
                  Edit
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => del(s)}>
                  Delete
                </button>
              </>
            )}
            <span className="faint small">updated {formatRelative(s.updated_at)}</span>
          </div>
        </section>
      ))}

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing?.id ? 'Edit skill' : 'New skill'} size="lg">
        {editing && (
          <form onSubmit={save}>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="sk-name">Name</label>
                <input id="sk-name" className="input mono" required pattern="[a-zA-Z0-9_-]{2,64}" title="2-64 chars: letters, digits, _ or -" value={editing.form.name} onChange={(e) => setForm({ name: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="sk-scope">Scope</label>
                <select id="sk-scope" className="select" value={editing.form.scope} onChange={(e) => setForm({ scope: e.target.value as SkillIn['scope'] })}>
                  <option value="user">user (only me)</option>
                  <option value="team">team</option>
                  <option value="org" disabled={!hasRole('org_admin', 'developer')}>
                    org (developer/org_admin)
                  </option>
                </select>
              </div>
              {editing.form.scope === 'team' && (
                <div className="field">
                  <label htmlFor="sk-team">Team</label>
                  <select id="sk-team" className="select" value={editing.form.team_id || ''} onChange={(e) => setForm({ team_id: e.target.value || null })} required>
                    <option value="">Select…</option>
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
              <label htmlFor="sk-desc">Description</label>
              <input id="sk-desc" className="input" value={editing.form.description || ''} onChange={(e) => setForm({ description: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sk-tools">Allowed tools (comma separated)</label>
              <input id="sk-tools" className="input mono" value={(editing.form.allowed_tools || []).join(', ')} onChange={(e) => setForm({ allowed_tools: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} placeholder="Read, Write, Bash, mcp__drive__*" />
            </div>
            <div className="field">
              <label htmlFor="sk-body">Body (markdown instructions)</label>
              <textarea id="sk-body" className="textarea mono" rows={12} required value={editing.form.body} onChange={(e) => setForm({ body: e.target.value })} />
            </div>
            <div className="form-actions">
              <button type="button" className="btn" onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? <span className="spinner" /> : 'Save'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={importing} onClose={() => setImporting(false)} title="Import SKILL.md" size="lg">
        <form onSubmit={doImport}>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="im-scope">Scope</label>
              <select id="im-scope" className="select" value={importScope} onChange={(e) => setImportScope(e.target.value as typeof importScope)}>
                <option value="user">user</option>
                <option value="team">team</option>
                <option value="org" disabled={!hasRole('org_admin', 'developer')}>
                  org
                </option>
              </select>
            </div>
            {importScope === 'team' && (
              <div className="field">
                <label htmlFor="im-team">Team</label>
                <select id="im-team" className="select" value={importTeam} onChange={(e) => setImportTeam(e.target.value)} required>
                  <option value="">Select…</option>
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
            <label htmlFor="im-md">SKILL.md contents (YAML frontmatter with name/description/allowed-tools, then the body)</label>
            <textarea id="im-md" className="textarea mono" rows={16} required value={skillMd} onChange={(e) => setSkillMd(e.target.value)} placeholder={'---\nname: my-skill\ndescription: What it does\nallowed-tools: Read, Write\n---\nInstructions…'} />
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setImporting(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy || !skillMd.trim()}>
              {busy ? <span className="spinner" /> : 'Import'}
            </button>
          </div>
        </form>
      </Modal>
      {dialog}
    </>
  )
}
