import { useMemo } from 'react'
import type { Message, ToolResultContent, ToolUseContent } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'
import { TextBlock, ThinkingBlock, ToolCard, ToolResultOrphan, type ToolResultView } from './blocks'

/** Renders persisted messages. tool_result blocks are matched to their tool_use by id, across messages. */
export function MessageList({ messages, conversationId }: { messages: Message[]; conversationId: string }) {
  const results = useMemo(() => {
    const map = new Map<string, ToolResultView>()
    for (const m of messages)
      for (const b of m.blocks) {
        const c = b.content as ToolResultContent
        if (c?.type === 'tool_result' && c.tool_use_id) map.set(c.tool_use_id, { content: c.content, is_error: c.is_error })
      }
    return map
  }, [messages])

  return (
    <>
      {messages.map((m) => {
        const isUser = m.role === 'user'
        const parts = m.blocks
          .slice()
          .sort((a, b) => a.ord - b.ord)
          .map((b, i) => {
            const c = b.content
            switch (c.type) {
              case 'text':
                return isUser ? <span key={i}>{String((c as { text?: string }).text ?? '')}</span> : <TextBlock key={i} text={String((c as { text?: string }).text ?? '')} conversationId={conversationId} />
              case 'thinking':
                return <ThinkingBlock key={i} text={String((c as { thinking?: string }).thinking ?? '')} />
              case 'tool_use': {
                const t = c as ToolUseContent
                return <ToolCard key={i} name={t.name} input={t.input} result={results.get(t.id)} />
              }
              case 'tool_result': {
                const r = c as ToolResultContent
                // rendered inline with its tool_use when that block exists anywhere in the thread
                const hasUse = messages.some((mm) => mm.blocks.some((bb) => bb.content.type === 'tool_use' && (bb.content as ToolUseContent).id === r.tool_use_id))
                return hasUse ? null : <ToolResultOrphan key={i} result={{ content: r.content, is_error: r.is_error }} />
              }
              default:
                return (
                  <pre key={i} className="json">
                    {JSON.stringify(c, null, 2)}
                  </pre>
                )
            }
          })
        if (!parts.some(Boolean)) return null
        return (
          <article key={m.id} className={`msg ${isUser ? 'msg-user' : 'msg-assistant'}`} aria-label={`${m.role} message`}>
            <div className="bubble">{parts}</div>
            <div className="msg-meta">
              <span>{m.role}</span>
              <span>·</span>
              <span>{formatRelative(m.created_at)}</span>
            </div>
          </article>
        )
      })}
    </>
  )
}
