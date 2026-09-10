import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createProject, listProjects } from '@/lib/api/endpoints'
import type { Project } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'
import { ProjectForm } from './ProjectForm'

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [creating, setCreating] = useState(false)
  const nav = useNavigate()
  useEffect(() => {
    listProjects().then(setProjects).catch((e) => toast.error('Could not load projects', errorMessage(e)))
  }, [])
  return (
    <div className="page">
      <div className="page-narrow">
        <div className="page-header">
          <h1>Projects</h1>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New project
          </button>
        </div>
        {!projects && <Spinner label="Loading…" />}
        {projects && !projects.length && <EmptyState title="No projects yet">Projects group conversations, files, instructions and memory.</EmptyState>}
        {projects && projects.length > 0 && (
          <div className="grid-2">
            {projects.map((p) => (
              <Link key={p.id} to={`/projects/${p.id}`} className="card" style={{ color: 'inherit', textDecoration: 'none' }}>
                <div className="card-title">
                  <h3>{p.name}</h3>
                  {p.memory_enabled && <span className="badge badge-info">memory</span>}
                </div>
                <p className="subtle small" style={{ minHeight: 34 }}>
                  {p.instructions ? p.instructions.slice(0, 120) : 'No instructions'}
                </p>
                <div className="faint small">Updated {formatRelative(p.updated_at)}</div>
              </Link>
            ))}
          </div>
        )}
        <Modal open={creating} onClose={() => setCreating(false)} title="New project">
          <ProjectForm
            submitLabel="Create"
            onCancel={() => setCreating(false)}
            onSubmit={async (body) => {
              try {
                const p = await createProject(body)
                toast.success('Project created')
                nav(`/projects/${p.id}`)
              } catch (e) {
                toast.error('Could not create project', errorMessage(e))
              }
            }}
          />
        </Modal>
      </div>
    </div>
  )
}
