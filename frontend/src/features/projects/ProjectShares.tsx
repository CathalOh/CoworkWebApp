import { useEffect, useState, type FormEvent } from 'react'
import { errorMessage } from '@/lib/api/client'
import { listShares, listTeams, shareProject, unshareProject } from '@/lib/api/endpoints'
import type { Share, Team } from '@/lib/api/types'
import { toast } from '@/store/toast'

export function ProjectShares({ projectId }: { projectId: string }) {
  const [shares, setShares] = useState<Share[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [teamId, setTeamId] = useState('')
  const [access, setAccess] = useState<'read' | 'write'>('read')
  const [shareMemory, setShareMemory] = useState(false)
  const [busy, setBusy] = useState(false)
  const reload = () => listShares(projectId).then(setShares).catch((e) => toast.error('Could not load shares', errorMessage(e)))
  useEffect(() => {
    void reload()
    listTeams().then(setTeams).catch(() => setTeams([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])
  const teamName = (id: string) => teams.find((t) => t.id === id)?.name || id.slice(0, 8)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!teamId) return
    setBusy(true)
    try {
      await shareProject(projectId, { team_id: teamId, access, share_memory: shareMemory })
      toast.success('Project shared')
      setTeamId('')
      await reload()
    } catch (err) {
      toast.error('Could not share', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const remove = async (s: Share) => {
    try {
      await unshareProject(projectId, s.team_id)
      await reload()
    } catch (err) {
      toast.error('Could not remove share', errorMessage(err))
    }
  }
  return (
    <section className="card" aria-label="Sharing">
      <div className="card-title">
        <h3>Sharing</h3>
      </div>
      {!shares.length && <p className="subtle small">Not shared with any team.</p>}
      <ul className="list">
        {shares.map((s) => (
          <li key={s.team_id} className="list-item">
            <strong style={{ flex: 1 }}>{teamName(s.team_id)}</strong>
            <span className="chip">{s.access}</span>
            {s.share_memory && <span className="chip chip-info">memory shared</span>}
            <button className="btn btn-ghost btn-sm" onClick={() => remove(s)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="row mt" style={{ alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0, flex: 1, minWidth: 140 }}>
          <label htmlFor="share-team">Team</label>
          <select id="share-team" className="select" value={teamId} onChange={(e) => setTeamId(e.target.value)} required>
            <option value="">Select team…</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="share-access">Access</label>
          <select id="share-access" className="select" value={access} onChange={(e) => setAccess(e.target.value as 'read' | 'write')}>
            <option value="read">read</option>
            <option value="write">write</option>
          </select>
        </div>
        <label className="checkbox" style={{ paddingBottom: 8 }}>
          <input type="checkbox" checked={shareMemory} onChange={(e) => setShareMemory(e.target.checked)} /> share memory
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy || !teamId}>
          Share
        </button>
      </form>
    </section>
  )
}
