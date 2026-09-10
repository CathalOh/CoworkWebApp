import { useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { errorMessage } from '@/lib/api/client'
import { formatRelative } from '@/lib/format'
import { Slot } from '@/slots/Slot'
import { useChatStore } from '@/store/chat'
import { toast } from '@/store/toast'
import { useUiStore } from '@/store/ui'
import { NewConversationDialog } from './NewConversationDialog'
import type { Project } from '@/lib/api/types'
import { listProjects } from '@/lib/api/endpoints'

export function ConversationSidebar() {
  const { conversationId } = useParams()
  const conversations = useChatStore((s) => s.conversations)
  const loading = useChatStore((s) => s.conversationsLoading)
  const load = useChatStore((s) => s.loadConversations)
  const live = useChatStore((s) => s.live)
  const open = useUiStore((s) => s.sidebarOpen)
  const setSidebar = useUiStore((s) => s.setSidebar)
  const setSearchOpen = useUiStore((s) => s.setSearchOpen)
  const [creating, setCreating] = useState(false)
  const [projectFilter, setProjectFilter] = useState<string>('')
  const [projects, setProjects] = useState<Project[]>([])
  const [filter, setFilter] = useState('')

  useEffect(() => {
    load(projectFilter || null).catch((e) => toast.error('Could not load conversations', errorMessage(e)))
  }, [load, projectFilter])
  useEffect(() => {
    listProjects().then(setProjects).catch(() => setProjects([]))
  }, [])

  const visible = conversations.filter((c) => !filter || (c.title || '').toLowerCase().includes(filter.toLowerCase()))
  const narrow = typeof window !== 'undefined' && window.innerWidth <= 900

  return (
    <>
      {open && narrow && <div className="sidebar-scrim" onClick={() => setSidebar(false)} aria-hidden="true" />}
      <aside className={`chat-sidebar ${open ? '' : 'closed'}`} aria-label="Conversations">
        <div className="sidebar-head">
          <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>
            + New
          </button>
          <button className="btn btn-sm" onClick={() => setSearchOpen(true)} aria-label="Search conversations" title="Search (Cmd/Ctrl+K)">
            Search
          </button>
          <span className="spacer" style={{ flex: 1 }} />
          <button className="btn btn-ghost btn-sm" onClick={() => setSidebar(false)} aria-label="Hide sidebar">
            «
          </button>
        </div>
        <div style={{ padding: '8px 10px 0' }} className="stack">
          <input className="input" placeholder="Filter by title" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter conversations" />
          {projects.length > 0 && (
            <select className="select" value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)} aria-label="Filter by project">
              <option value="">All projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="sidebar-list">
          {loading && !conversations.length && <div className="empty small">Loading…</div>}
          {!loading && !visible.length && <div className="empty small">No conversations yet.</div>}
          {visible.map((c) => (
            <NavLink
              key={c.id}
              to={`/chat/${c.id}`}
              className={`conv-item ${c.id === conversationId ? 'active' : ''}`}
              onClick={() => narrow && setSidebar(false)}
            >
              <div className="conv-title truncate">
                {live[c.id] && <span className="spinner" style={{ width: 10, height: 10, marginRight: 6 }} aria-label="running" />}
                {c.title || 'Untitled conversation'}
              </div>
              <div className="conv-meta">
                <span>{formatRelative(c.updated_at)}</span>
                {c.project_id && <span>· {projects.find((p) => p.id === c.project_id)?.name || 'project'}</span>}
                {c.shared_with_team && <span>· shared</span>}
              </div>
            </NavLink>
          ))}
        </div>
        <Slot name="chat.sidebar" context={{ conversationId }} />
      </aside>
      <NewConversationDialog open={creating} onClose={() => setCreating(false)} defaultProjectId={projectFilter || null} />
    </>
  )
}
