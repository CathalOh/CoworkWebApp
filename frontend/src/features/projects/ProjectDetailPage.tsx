import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { deleteProject, getProject, listBundles, listConversations, patchProject } from '@/lib/api/endpoints'
import type { Bundle, Conversation, Project } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { Slot } from '@/slots/Slot'
import { useChatStore } from '@/store/chat'
import { toast } from '@/store/toast'
import { ProjectFiles } from './ProjectFiles'
import { ProjectForm } from './ProjectForm'
import { ProjectShares } from './ProjectShares'

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const nav = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const createConversation = useChatStore((s) => s.create)
  const { confirm, dialog } = useConfirm()

  useEffect(() => {
    getProject(projectId)
      .then(async (p) => {
        setProject(p)
        if (p.bundle_id) setBundle((await listBundles().catch(() => [] as Bundle[])).find((b) => b.id === p.bundle_id) || null)
        else setBundle(null)
      })
      .catch((e) => setError(errorMessage(e)))
    listConversations(projectId).then(setConversations).catch(() => setConversations([]))
  }, [projectId])

  if (error) return <div className="page"><EmptyState title="Project unavailable">{error}</EmptyState></div>
  if (!project) return <div className="page"><Spinner label="Loading…" /></div>

  const startChat = async () => {
    try {
      const c = await createConversation({ project_id: project.id, workspace_id: project.workspace_id, permission_mode: 'default' })
      nav(`/chat/${c.id}`)
    } catch (e) {
      toast.error('Could not start conversation', errorMessage(e))
    }
  }
  const del = async () => {
    if (!(await confirm(`Delete project "${project.name}"?`, { message: 'Files and shares are removed.', danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteProject(project.id)
      nav('/projects')
    } catch (e) {
      toast.error('Could not delete project', errorMessage(e))
    }
  }

  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <div>
            <div className="small faint">
              <Link to="/projects">Projects</Link> / {project.name}
            </div>
            <h1>{project.name}</h1>
          </div>
          <div className="row">
            <button className="btn btn-primary" onClick={startChat}>
              New conversation
            </button>
            <button className="btn" onClick={() => setEditing((v) => !v)}>
              {editing ? 'Cancel' : 'Edit'}
            </button>
            <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={del}>
              Delete
            </button>
          </div>
        </div>

        <section className="card">
          {editing ? (
            <ProjectForm
              initial={project}
              onCancel={() => setEditing(false)}
              onSubmit={async (body) => {
                try {
                  const { team_id: _t, ...patch } = body
                  void _t
                  const p = await patchProject(project.id, patch)
                  setProject(p)
                  setEditing(false)
                  toast.success('Project updated')
                  if (p.bundle_id) setBundle((await listBundles().catch(() => [] as Bundle[])).find((b) => b.id === p.bundle_id) || null)
                  else setBundle(null)
                } catch (e) {
                  toast.error('Could not update project', errorMessage(e))
                }
              }}
            />
          ) : (
            <>
              <div className="row mb">
                <span className="chip">{project.memory_enabled ? 'memory on' : 'memory off'}</span>
                {project.workspace_id && (
                  <Link className="chip" to={`/workspaces/${project.workspace_id}`}>
                    workspace
                  </Link>
                )}
                {bundle && <span className="chip chip-info">bundle: {bundle.name}</span>}
                {project.team_id && <span className="chip">team project</span>}
              </div>
              <div className="label">Instructions</div>
              <p style={{ whiteSpace: 'pre-wrap' }} className={project.instructions ? '' : 'faint'}>
                {project.instructions || 'None'}
              </p>
            </>
          )}
        </section>

        <Slot name="project.panel" context={{ projectId: project.id, bundle: bundle ? { name: bundle.name, manifest: bundle.manifest } : null }} />

        <div className="grid-2 mt">
          <ProjectFiles projectId={project.id} />
          <ProjectShares projectId={project.id} />
        </div>

        <section className="card mt" aria-label="Conversations in project">
          <div className="card-title">
            <h3>Conversations</h3>
          </div>
          {!conversations.length && <p className="subtle small">No conversations in this project yet.</p>}
          <ul className="list">
            {conversations.map((c) => (
              <li key={c.id} className="list-item">
                <Link to={`/chat/${c.id}`} style={{ flex: 1 }} className="truncate">
                  {c.title || 'Untitled conversation'}
                </Link>
                <span className="faint small">{formatRelative(c.updated_at)}</span>
              </li>
            ))}
          </ul>
        </section>
        {dialog}
      </div>
    </div>
  )
}
