import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { errorMessage } from '@/lib/api/client'
import { getConversation, getProject, listBundles } from '@/lib/api/endpoints'
import type { Bundle, Conversation, Effort, PermissionMode, Project } from '@/lib/api/types'
import { formatMoney } from '@/lib/format'
import { Slot } from '@/slots/Slot'
import { useAuthStore } from '@/store/auth'
import { selectCost, useChatStore } from '@/store/chat'
import { toast } from '@/store/toast'
import { useUiStore } from '@/store/ui'
import { Composer } from './Composer'
import { ConnectorPicker } from './ConnectorPicker'
import { LiveAssistant } from './LiveAssistant'
import { McpStatusChips } from './McpStatusChips'
import { MessageList } from './MessageList'
import { modeLabel } from './permissionModes'

export function ConversationView({ conversationId }: { conversationId: string }) {
  const nav = useNavigate()
  const meta = useAuthStore((s) => s.meta)
  const messages = useChatStore((s) => s.messages[conversationId])
  const live = useChatStore((s) => s.live[conversationId])
  const cost = useChatStore(selectCost(conversationId))
  const loadConversation = useChatStore((s) => s.loadConversation)
  const loadRuns = useChatStore((s) => s.loadRuns)
  const resume = useChatStore((s) => s.resume)
  const send = useChatStore((s) => s.send)
  const approve = useChatStore((s) => s.approve)
  const elicit = useChatStore((s) => s.elicit)
  const stop = useChatStore((s) => s.stop)
  const update = useChatStore((s) => s.update)
  const remove = useChatStore((s) => s.remove)
  const fromList = useChatStore((s) => s.conversations.find((c) => c.id === conversationId))
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [project, setProject] = useState<Project | null>(null)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [mode, setMode] = useState<PermissionMode>('default')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  const { confirm, dialog } = useConfirm()

  // Load conversation, messages, runs; then resume any in-flight run.
  useEffect(() => {
    let cancelled = false
    setError(null)
    setConversation(null)
    ;(async () => {
      try {
        const c = fromList || (await getConversation(conversationId))
        if (cancelled) return
        setConversation(c)
        setMode((c.permission_mode as PermissionMode) || 'default')
        await Promise.all([loadConversation(conversationId), loadRuns(conversationId)])
        if (cancelled) return
        await resume(conversationId)
        if (c.project_id) {
          const p = await getProject(c.project_id).catch(() => null)
          if (cancelled) return
          setProject(p)
          if (p?.bundle_id) {
            const bundles = await listBundles().catch(() => [] as Bundle[])
            if (!cancelled) setBundle(bundles.find((b) => b.id === p.bundle_id) || null)
          }
        } else {
          setProject(null)
          setBundle(null)
        }
      } catch (e) {
        if (!cancelled) setError(errorMessage(e))
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  useEffect(() => {
    if (fromList) setConversation(fromList)
  }, [fromList])

  // Auto-scroll while streaming unless the user scrolled up.
  const onScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }, [])
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages, live])

  const onSend = async (content: string, opts: { max_budget_usd?: number; model?: string; effort?: Effort }) => {
    try {
      stickToBottom.current = true
      await send(conversationId, { content, permission_mode: mode, ...opts })
    } catch (e) {
      toast.error('Could not send message', errorMessage(e))
      throw e
    }
  }
  const onModeChange = async (m: PermissionMode) => {
    setMode(m)
    try {
      await update(conversationId, { permission_mode: m })
    } catch (e) {
      toast.error('Could not save permission mode', errorMessage(e))
    }
  }
  const rename = async () => {
    const title = window.prompt('Conversation title', conversation?.title || '')
    if (title === null) return
    try {
      await update(conversationId, { title: title.trim() || null })
    } catch (e) {
      toast.error('Could not rename', errorMessage(e))
    }
  }
  const del = async () => {
    if (!(await confirm('Delete this conversation?', { message: 'Messages, runs and approvals are removed. This cannot be undone.', danger: true, confirmLabel: 'Delete' }))) return
    try {
      await remove(conversationId)
      nav('/chat')
    } catch (e) {
      toast.error('Could not delete', errorMessage(e))
    }
  }

  if (error) return <EmptyState title="Conversation unavailable">{error}</EmptyState>
  if (!conversation) {
    return (
      <div className="page">
        <Spinner label="Loading conversation…" />
      </div>
    )
  }
  const busy = !!live && live.phase !== 'done'
  const connectorCount = conversation.connector_ids?.length || 0

  return (
    <div className="chat-main">
      <header className="chat-header">
        {!sidebarOpen && (
          <button className="btn btn-ghost btn-sm" onClick={toggleSidebar} aria-label="Show sidebar">
            »
          </button>
        )}
        <span className="title truncate" title={conversation.title || undefined}>
          {conversation.title || 'Untitled conversation'}
        </span>
        {project && (
          <Link className="chip" to={`/projects/${project.id}`}>
            {project.name}
          </Link>
        )}
        <span className="chip" title="Permission mode">
          {modeLabel(mode)}
        </span>
        <button className="chip" onClick={() => setPickerOpen(true)} style={{ cursor: 'pointer' }} aria-haspopup="dialog">
          {connectorCount ? `${connectorCount} connector${connectorCount > 1 ? 's' : ''}` : 'Connectors'}
        </button>
        <span className="chip" title="Total cost of all runs in this conversation">
          {formatMoney(cost)}
        </span>
        <Link className="chip" to={`/artifacts?conversation_id=${conversation.id}`}>
          Artifacts
        </Link>
        <Slot name="chat.header" context={{ conversationId, bundle: bundle ? { name: bundle.name, manifest: bundle.manifest } : null }} />
        <span style={{ flex: 1 }} />
        <button className="btn btn-ghost btn-sm" onClick={rename}>
          Rename
        </button>
        <button className="btn btn-ghost btn-sm" onClick={del} style={{ color: 'var(--danger)' }}>
          Delete
        </button>
      </header>
      {live?.mcpServers.length ? (
        <div style={{ padding: '6px 14px', borderBottom: '1px solid var(--border)' }}>
          <McpStatusChips servers={live.mcpServers} />
        </div>
      ) : null}
      <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
        <div className="chat-inner">
          {!messages && <Spinner label="Loading messages…" />}
          {messages && !messages.length && !live && (
            <EmptyState title="Start the conversation">Ask for a document, an analysis or a workflow. Tools that change things will ask for approval first.</EmptyState>
          )}
          {messages && <MessageList messages={messages} conversationId={conversationId} />}
          {live && <LiveAssistant live={live} conversationId={conversationId} onApprove={(b) => approve(conversationId, b)} onElicit={(b) => elicit(conversationId, b)} />}
        </div>
      </div>
      <Composer
        mode={mode}
        onModeChange={onModeChange}
        onSend={onSend}
        busy={busy}
        onStop={() => stop(conversationId).catch((e) => toast.error('Could not stop run', errorMessage(e)))}
        defaultModel={meta?.model}
      />
      <ConnectorPicker conversation={conversation} open={pickerOpen} onClose={() => setPickerOpen(false)} />
      {dialog}
    </div>
  )
}
