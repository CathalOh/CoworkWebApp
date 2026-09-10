import type { ApprovalIn, ElicitationIn } from '@/lib/api/types'
import type { LiveRun } from '@/store/chat'
import { ApprovalCard } from './ApprovalCard'
import { ElicitationCard } from './ElicitationCard'
import { TextBlock, ThinkingBlock, ToolCard } from './blocks'

interface Props {
  live: LiveRun
  conversationId: string
  onApprove: (b: ApprovalIn) => Promise<void>
  onElicit: (b: ElicitationIn) => Promise<void>
}

/** The in-flight assistant bubble, driven by SSE events. */
export function LiveAssistant({ live, conversationId, onApprove, onElicit }: Props) {
  const streaming = live.phase !== 'done'
  const lastIdx = live.segments.length - 1
  const statusText =
    live.phase === 'connecting' ? 'Connecting…' :
    live.phase === 'reconnecting' ? 'Connection lost — reconnecting…' :
    live.phase === 'waiting_approval' ? 'Waiting for your approval' :
    live.phase === 'waiting_elicitation' ? 'Waiting for your input' :
    live.phase === 'done' ? (live.error ? 'Failed' : live.interrupted ? 'Stopped' : 'Finishing…') : 'Working…'
  return (
    <article className="msg msg-assistant" aria-live="polite" aria-busy={streaming}>
      {(live.segments.length > 0 || live.error) && (
        <div className="bubble">
          {live.segments.map((s, i) => {
            const isLast = i === lastIdx && streaming
            if (s.kind === 'text') return <TextBlock key={i} text={s.text} conversationId={conversationId} streaming={isLast} />
            if (s.kind === 'thinking') return <ThinkingBlock key={i} text={s.text} streaming={isLast} />
            const decision = live.decisions[s.id]
            return <ToolCard key={i} name={s.name} input={s.input} result={s.result} pending={!s.result && !decision?.startsWith('deny')} />
          })}
          {live.error && <p style={{ color: 'var(--danger)' }}>{live.error}</p>}
        </div>
      )}
      {live.approvals.map((a) => (
        <ApprovalCard key={a.tool_use_id} request={a} onDecide={onApprove} />
      ))}
      {live.elicitations.map((e) => (
        <ElicitationCard key={e.elicitation_id} request={e} onRespond={onElicit} />
      ))}
      <div className="status-line">
        {streaming && live.phase !== 'waiting_approval' && live.phase !== 'waiting_elicitation' && <span className="spinner" aria-hidden="true" />}
        <span className={live.phase === 'reconnecting' ? 'pulse' : undefined}>{statusText}</span>
        {live.model && <span className="faint">· {live.model}</span>}
      </div>
    </article>
  )
}
