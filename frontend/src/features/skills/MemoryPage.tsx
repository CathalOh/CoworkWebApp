import { useEffect, useState, type FormEvent } from 'react'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { createMemory, deleteMemory, listMemory, listProjects } from '@/lib/api/endpoints'
import type { MemoryItem, Project } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

export function MemoryPage() {
  const [items, setItems] = useState<MemoryItem[] | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [filterProject, setFilterProject] = useState('')
  const [content, setContent] = useState('')
  const [type, setType] = useState<'fact' | 'preference' | 'summary'>('fact')
  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState(false)
  const { confirm, dialog } = useConfirm()
  const reload = () => listMemory(filterProject || null).then(setItems).catch((e) => toast.error('Could not load memory', errorMessage(e)))
  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterProject])
  useEffect(() => {
    listProjects().then(setProjects).catch(() => setProjects([]))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await createMemory({ content: content.trim(), memory_type: type, project_id: projectId || null })
      setContent('')
      await reload()
    } catch (err) {
      toast.error('Could not add memory', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const del = async (m: MemoryItem) => {
    if (!(await confirm('Forget this memory?', { danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteMemory(m.id)
      await reload()
    } catch (err) {
      toast.error('Could not delete memory', errorMessage(err))
    }
  }
  const projectName = (id: string | null) => (id ? projects.find((p) => p.id === id)?.name || id.slice(0, 8) : null)

  return (
    <>
      <div className="page-header">
        <h1>Memory</h1>
        <select className="select" style={{ width: 'auto' }} value={filterProject} onChange={(e) => setFilterProject(e.target.value)} aria-label="Filter by project">
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <section className="card mb">
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="mem-content">Add a memory</label>
            <textarea id="mem-content" className="textarea" rows={2} maxLength={2000} required value={content} onChange={(e) => setContent(e.target.value)} placeholder="e.g. Our fiscal year starts in February." />
          </div>
          <div className="row">
            <select className="select" style={{ width: 'auto' }} value={type} onChange={(e) => setType(e.target.value as typeof type)} aria-label="Memory type">
              <option value="fact">fact</option>
              <option value="preference">preference</option>
              <option value="summary">summary</option>
            </select>
            <select className="select" style={{ width: 'auto' }} value={projectId} onChange={(e) => setProjectId(e.target.value)} aria-label="Project">
              <option value="">Global</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button className="btn btn-primary" type="submit" disabled={busy || !content.trim()}>
              Add
            </button>
          </div>
        </form>
      </section>
      {!items && <Spinner label="Loading…" />}
      {items && !items.length && <EmptyState title="Nothing remembered yet">Memories are facts and preferences the agent recalls across conversations.</EmptyState>}
      {items && items.length > 0 && (
        <ul className="list card" style={{ padding: 0 }}>
          {items.map((m) => (
            <li key={m.id} className="list-item">
              <span className="chip">{m.memory_type}</span>
              <span style={{ flex: 1 }}>{m.content}</span>
              {projectName(m.project_id) && <span className="chip chip-info">{projectName(m.project_id)}</span>}
              <span className="faint small hide-sm">{formatRelative(m.created_at)}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => del(m)} aria-label="Delete memory">
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      {dialog}
    </>
  )
}
