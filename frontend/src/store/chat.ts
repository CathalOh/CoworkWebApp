import { create } from 'zustand'
import { errorMessage } from '@/lib/api/client'
import {
  createConversation, deleteConversation, getRun, interruptRun, listConversationRuns, listConversations, listMessages, patchConversation,
  postMessage, submitApproval, submitElicitation,
} from '@/lib/api/endpoints'
import type {
  ApprovalIn, ApprovalRequestData, Conversation, ConversationIn, ConversationPatch, ElicitationData, ElicitationIn, McpServerStatus, Message,
  MessageIn, Run, RunEvent,
} from '@/lib/api/types'
import { isActiveRun } from '@/lib/api/types'
import { openRunStream, type RunStreamHandle } from '@/lib/sse/runStream'
import { toast } from './toast'

// ---- live run model -------------------------------------------------------------------------------
export type LiveSegment =
  | { kind: 'text'; text: string }
  | { kind: 'thinking'; text: string }
  | { kind: 'tool'; id: string; name: string; input: unknown; result?: { content: unknown; is_error?: boolean; denied?: boolean; reason?: string } }

export interface LiveRun {
  runId: string
  conversationId: string
  phase: 'connecting' | 'streaming' | 'waiting_approval' | 'waiting_elicitation' | 'reconnecting' | 'done'
  lastSeq: number
  segments: LiveSegment[]
  approvals: ApprovalRequestData[]
  decisions: Record<string, string>
  elicitations: ElicitationData[]
  mcpServers: McpServerStatus[]
  model?: string
  usage?: Record<string, unknown>
  cost?: number
  error?: string
  interrupted?: boolean
  startedAt: number
}

// ---- persistence helpers (localStorage) ----------------------------------------------------------
const ACTIVE_KEY = (convId: string) => `cw.activeRun.${convId}`
const SEQ_KEY = (runId: string) => `cw.runSeq.${runId}`
const ls = {
  get: (k: string) => {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  set: (k: string, v: string) => {
    try {
      localStorage.setItem(k, v)
    } catch {
      /* ignore */
    }
  },
  del: (k: string) => {
    try {
      localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  },
}

const streams = new Map<string, RunStreamHandle>()

// ---- reducer ------------------------------------------------------------------------------------
function applyEvent(live: LiveRun, ev: RunEvent): LiveRun {
  const d = (ev.data || {}) as Record<string, unknown>
  const next: LiveRun = { ...live, lastSeq: Math.max(live.lastSeq, ev.seq || 0), segments: live.segments.slice() }
  const last = next.segments[next.segments.length - 1]
  switch (ev.type) {
    case 'run_started':
      next.phase = 'streaming'
      next.model = typeof d.model === 'string' ? d.model : next.model
      break
    case 'assistant_text': {
      const text = typeof d.text === 'string' ? d.text : ''
      if (d.delta === true) {
        if (last && last.kind === 'text') next.segments[next.segments.length - 1] = { kind: 'text', text: last.text + text }
        else next.segments.push({ kind: 'text', text })
      } else if (!next.segments.some((s) => s.kind === 'text') && text) {
        // Non-delta payload with no streamed text yet (runtimes that only emit whole messages).
        next.segments.push({ kind: 'text', text })
      }
      // Otherwise it's a final/duplicate copy of already streamed text: ignore.
      next.phase = 'streaming'
      break
    }
    case 'thinking': {
      const text = typeof d.thinking === 'string' ? d.thinking : typeof d.text === 'string' ? d.text : ''
      if (d.delta === false && last && last.kind === 'thinking') break
      if (last && last.kind === 'thinking') next.segments[next.segments.length - 1] = { kind: 'thinking', text: last.text + text }
      else next.segments.push({ kind: 'thinking', text })
      break
    }
    case 'tool_use':
      next.segments.push({ kind: 'tool', id: String(d.tool_use_id ?? d.id ?? ''), name: String(d.name ?? 'tool'), input: d.input })
      next.phase = 'streaming'
      break
    case 'tool_result': {
      const id = String(d.tool_use_id ?? '')
      const idx = next.segments.findIndex((s) => s.kind === 'tool' && s.id === id)
      const result = { content: d.content, is_error: d.is_error === true, denied: d.denied === true, reason: typeof d.reason === 'string' ? d.reason : undefined }
      if (idx >= 0) {
        const seg = next.segments[idx] as Extract<LiveSegment, { kind: 'tool' }>
        next.segments[idx] = { ...seg, result }
      } else next.segments.push({ kind: 'tool', id, name: 'tool', input: undefined, result })
      break
    }
    case 'approval_request': {
      const req = d as unknown as ApprovalRequestData
      if (!next.approvals.some((a) => a.tool_use_id === req.tool_use_id)) next.approvals = [...next.approvals, req]
      next.phase = 'waiting_approval'
      break
    }
    case 'approval_decided': {
      const id = String(d.tool_use_id ?? '')
      next.approvals = next.approvals.filter((a) => a.tool_use_id !== id)
      next.decisions = { ...next.decisions, [id]: String(d.decision ?? '') }
      next.phase = next.approvals.length ? 'waiting_approval' : 'streaming'
      break
    }
    case 'elicitation': {
      const req = d as unknown as ElicitationData
      if (!next.elicitations.some((e) => e.elicitation_id === req.elicitation_id)) next.elicitations = [...next.elicitations, req]
      next.phase = 'waiting_elicitation'
      break
    }
    case 'mcp_status':
      next.mcpServers = Array.isArray(d.servers) ? (d.servers as McpServerStatus[]) : []
      break
    case 'usage':
      next.usage = d
      break
    case 'result':
      next.cost = typeof d.total_cost_usd === 'number' ? d.total_cost_usd : next.cost
      next.usage = (d.usage as Record<string, unknown>) || next.usage
      next.phase = 'done'
      break
    case 'error':
      next.error = typeof d.message === 'string' ? d.message : 'Run failed'
      next.phase = 'done'
      break
    case 'interrupted':
      next.interrupted = true
      next.phase = 'done'
      break
    case 'status': {
      const kind = String(d.kind ?? '')
      if (kind === 'closed') next.phase = 'done'
      else if (kind === 'waiting_approval') next.phase = 'waiting_approval'
      else if (kind === 'waiting_elicitation') next.phase = 'waiting_elicitation'
      break
    }
    default:
      break
  }
  return next
}

// ---- store --------------------------------------------------------------------------------------
interface ChatState {
  conversations: Conversation[]
  conversationsLoading: boolean
  messages: Record<string, Message[]>
  runs: Record<string, Run[]>
  live: Record<string, LiveRun>
  loadConversations: (projectId?: string | null) => Promise<void>
  loadConversation: (id: string) => Promise<void>
  loadRuns: (id: string) => Promise<Run[]>
  create: (body: ConversationIn) => Promise<Conversation>
  update: (id: string, body: ConversationPatch) => Promise<Conversation>
  remove: (id: string) => Promise<void>
  send: (conversationId: string, body: MessageIn) => Promise<void>
  resume: (conversationId: string) => Promise<void>
  attachRun: (conversationId: string, runId: string, after: number) => void
  detach: (conversationId: string) => void
  approve: (conversationId: string, body: ApprovalIn) => Promise<void>
  elicit: (conversationId: string, body: ElicitationIn) => Promise<void>
  stop: (conversationId: string) => Promise<void>
  costFor: (conversationId: string) => number
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  conversationsLoading: false,
  messages: {},
  runs: {},
  live: {},

  loadConversations: async (projectId) => {
    set({ conversationsLoading: true })
    try {
      const conversations = await listConversations(projectId)
      set({ conversations })
    } finally {
      set({ conversationsLoading: false })
    }
  },

  loadConversation: async (id) => {
    const msgs = await listMessages(id)
    set((s) => ({ messages: { ...s.messages, [id]: msgs } }))
  },

  loadRuns: async (id) => {
    const runs = await listConversationRuns(id)
    set((s) => ({ runs: { ...s.runs, [id]: runs } }))
    return runs
  },

  create: async (body) => {
    const c = await createConversation(body)
    set((s) => ({ conversations: [c, ...s.conversations] }))
    return c
  },

  update: async (id, body) => {
    const c = await patchConversation(id, body)
    set((s) => ({ conversations: s.conversations.map((x) => (x.id === id ? c : x)) }))
    return c
  },

  remove: async (id) => {
    await deleteConversation(id)
    get().detach(id)
    set((s) => {
      const messages = { ...s.messages }
      delete messages[id]
      return { conversations: s.conversations.filter((x) => x.id !== id), messages }
    })
  },

  send: async (conversationId, body) => {
    const run = await postMessage(conversationId, body)
    // optimistic user message so the composer feels instant
    const optimistic: Message = {
      id: `local-${Date.now()}`,
      role: 'user',
      seq: Number.MAX_SAFE_INTEGER,
      run_id: run.id,
      created_at: new Date().toISOString(),
      blocks: [{ block_type: 'text', content: { type: 'text', text: body.content }, ord: 0 }],
    }
    set((s) => ({
      messages: { ...s.messages, [conversationId]: [...(s.messages[conversationId] || []), optimistic] },
      conversations: s.conversations.map((c) => (c.id === conversationId ? { ...c, updated_at: new Date().toISOString() } : c)),
    }))
    get().attachRun(conversationId, run.id, 0)
  },

  resume: async (conversationId) => {
    if (get().live[conversationId]) return
    const runId = ls.get(ACTIVE_KEY(conversationId))
    let run: Run | null = null
    if (runId) {
      run = await getRun(runId).catch(() => null)
    }
    if (!run) {
      // Fall back to the server's view: an active run created elsewhere (another tab, a task, a schedule).
      const runs = await get().loadRuns(conversationId).catch(() => [] as Run[])
      run = runs.find((r) => isActiveRun(r.status)) || null
    }
    if (!run || !isActiveRun(run.status)) {
      if (runId) ls.del(ACTIVE_KEY(conversationId))
      return
    }
    // Replay from 0 when nothing is in memory (page reload) so the live bubble is rebuilt in full;
    // the persisted seq is used for reconnects when in-memory state exists.
    get().attachRun(conversationId, run.id, 0)
  },

  attachRun: (conversationId, runId, after) => {
    get().detach(conversationId)
    ls.set(ACTIVE_KEY(conversationId), runId)
    const live: LiveRun = {
      runId, conversationId, phase: 'connecting', lastSeq: after, segments: [], approvals: [], decisions: {}, elicitations: [], mcpServers: [],
      startedAt: Date.now(),
    }
    set((s) => ({ live: { ...s.live, [conversationId]: live } }))

    const handle = openRunStream(runId, after, {
      onEvent: (ev) => {
        set((s) => {
          const cur = s.live[conversationId]
          if (!cur || cur.runId !== runId) return {}
          const next = applyEvent(cur, ev)
          ls.set(SEQ_KEY(runId), String(next.lastSeq))
          return { live: { ...s.live, [conversationId]: next } }
        })
      },
      onReconnecting: () => {
        set((s) => {
          const cur = s.live[conversationId]
          if (!cur || cur.runId !== runId || cur.phase === 'done') return {}
          return { live: { ...s.live, [conversationId]: { ...cur, phase: 'reconnecting' } } }
        })
      },
      onClose: async (reason) => {
        streams.delete(runId)
        const cur = get().live[conversationId]
        if (reason === 'error' && cur && cur.phase !== 'done') {
          // The browser gave up reconnecting. Check the run; if still active, reopen from the last seq.
          const run = await getRun(runId).catch(() => null)
          if (run && isActiveRun(run.status)) {
            const seq = cur.lastSeq
            set((s) => ({ live: { ...s.live, [conversationId]: { ...cur, phase: 'reconnecting' } } }))
            streams.set(runId, openRunStream(runId, seq, streamHandlersFor(conversationId, runId)))
            return
          }
        }
        await finishRun(conversationId, runId)
      },
    })
    streams.set(runId, handle)

    function streamHandlersFor(convId: string, rid: string) {
      // Re-entrant helper for the manual reconnect path above (same handlers).
      return {
        onEvent: (ev: RunEvent) =>
          set((s) => {
            const cur = s.live[convId]
            if (!cur || cur.runId !== rid) return {}
            const next = applyEvent(cur, ev)
            ls.set(SEQ_KEY(rid), String(next.lastSeq))
            return { live: { ...s.live, [convId]: next } }
          }),
        onClose: () => {
          streams.delete(rid)
          void finishRun(convId, rid)
        },
      }
    }

    async function finishRun(convId: string, rid: string) {
      ls.del(ACTIVE_KEY(convId))
      ls.del(SEQ_KEY(rid))
      const cur = get().live[convId]
      if (cur?.error) toast.error('Run failed', cur.error)
      // Refetch the durable messages and runs, then drop the live bubble (it is now in history).
      try {
        await Promise.all([get().loadConversation(convId), get().loadRuns(convId)])
      } catch (e) {
        toast.error('Could not refresh conversation', errorMessage(e))
      }
      set((s) => {
        const live = { ...s.live }
        if (live[convId]?.runId === rid) delete live[convId]
        return { live }
      })
    }
  },

  detach: (conversationId) => {
    const cur = get().live[conversationId]
    if (cur) {
      streams.get(cur.runId)?.close()
      streams.delete(cur.runId)
      set((s) => {
        const live = { ...s.live }
        delete live[conversationId]
        return { live }
      })
    }
  },

  approve: async (conversationId, body) => {
    const cur = get().live[conversationId]
    if (!cur) return
    await submitApproval(cur.runId, body)
    // optimistic: hide the card until approval_decided arrives
    set((s) => {
      const l = s.live[conversationId]
      if (!l) return {}
      return { live: { ...s.live, [conversationId]: { ...l, approvals: l.approvals.filter((a) => a.tool_use_id !== body.tool_use_id), decisions: { ...l.decisions, [body.tool_use_id]: body.decision } } } }
    })
  },

  elicit: async (conversationId, body) => {
    const cur = get().live[conversationId]
    if (!cur) return
    await submitElicitation(cur.runId, body)
    set((s) => {
      const l = s.live[conversationId]
      if (!l) return {}
      return { live: { ...s.live, [conversationId]: { ...l, elicitations: l.elicitations.filter((e) => e.elicitation_id !== body.elicitation_id), phase: 'streaming' } } }
    })
  },

  stop: async (conversationId) => {
    const cur = get().live[conversationId]
    if (!cur) return
    await interruptRun(cur.runId)
  },

  costFor: (conversationId) => {
    const runs = get().runs[conversationId] || []
    const live = get().live[conversationId]
    const fromRuns = runs.reduce((acc, r) => acc + (r.total_cost_usd || 0), 0)
    const liveCost = live?.cost && !runs.some((r) => r.id === live.runId && r.total_cost_usd) ? live.cost : 0
    return fromRuns + liveCost
  },
}))

export const selectCost = (conversationId: string) => (s: ChatState) => {
  const runs = s.runs[conversationId] || []
  const live = s.live[conversationId]
  const fromRuns = runs.reduce((acc, r) => acc + (r.total_cost_usd || 0), 0)
  const liveCost = live?.cost && !runs.some((r) => r.id === live.runId && r.total_cost_usd) ? live.cost : 0
  return fromRuns + liveCost
}
