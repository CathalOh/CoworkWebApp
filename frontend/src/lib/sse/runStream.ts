import { runEventsUrl } from '@/lib/api/endpoints'
import type { RunEvent } from '@/lib/api/types'

export const TERMINAL_EVENT_TYPES = new Set(['result', 'error', 'interrupted'])

export interface RunStreamHandlers {
  onEvent: (ev: RunEvent) => void
  /** Called once when the stream is finished (terminal event, closed status, or fatal error). */
  onClose: (reason: 'terminal' | 'closed' | 'error') => void
  onReconnecting?: () => void
}

export interface RunStreamHandle {
  close: () => void
  readonly lastSeq: number
}

/**
 * Opens the resumable SSE stream for a run.
 *
 * - The server sets `id: <seq>` on every frame, so the browser's automatic EventSource reconnect sends
 *   `Last-Event-ID` and resumes without duplicates.
 * - For manual re-opens (page reload) we pass `?after=<seq>` so replay starts after the last seen event.
 * - Terminal events (result/error/interrupted) and `status{kind:'closed'}` end the stream; we close the
 *   EventSource ourselves because the server ends the response and EventSource would otherwise reconnect forever.
 */
export function openRunStream(runId: string, after: number, handlers: RunStreamHandlers): RunStreamHandle {
  let lastSeq = after
  let closed = false
  const es = new EventSource(runEventsUrl(runId, after), { withCredentials: true })

  const finish = (reason: 'terminal' | 'closed' | 'error') => {
    if (closed) return
    closed = true
    es.close()
    handlers.onClose(reason)
  }

  es.onmessage = (msg: MessageEvent<string>) => {
    let ev: RunEvent
    try {
      ev = JSON.parse(msg.data) as RunEvent
    } catch {
      return
    }
    if (typeof ev.seq === 'number' && ev.seq <= lastSeq && ev.type !== 'status') return // de-dup after reconnect
    if (typeof ev.seq === 'number' && ev.seq > lastSeq) lastSeq = ev.seq
    handlers.onEvent(ev)
    if (TERMINAL_EVENT_TYPES.has(ev.type)) finish('terminal')
    else if (ev.type === 'status' && (ev.data as { kind?: string })?.kind === 'closed') finish('closed')
  }

  es.onerror = () => {
    if (closed) return
    if (es.readyState === EventSource.CLOSED) {
      finish('error')
    } else {
      handlers.onReconnecting?.()
    }
  }

  return {
    close: () => {
      if (closed) return
      closed = true
      es.close()
    },
    get lastSeq() {
      return lastSeq
    },
  }
}
