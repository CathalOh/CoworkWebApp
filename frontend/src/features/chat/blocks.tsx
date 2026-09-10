import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { JsonView } from '@/components/JsonView'
import { errorMessage } from '@/lib/api/client'
import { createArtifact } from '@/lib/api/endpoints'
import type { ArtifactKind } from '@/lib/api/types'
import { Markdown, CodeBlock, type CodeBlockProps } from '@/lib/markdown/Markdown'
import { toast } from '@/store/toast'

const ARTIFACT_LANGS: Record<string, ArtifactKind> = { html: 'html', svg: 'svg', mermaid: 'mermaid' }

/** Fenced code block with an "Open as artifact" action for html/svg/mermaid fences. */
export function ChatCodeBlock({ lang, code, conversationId }: CodeBlockProps & { conversationId?: string }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const kind = ARTIFACT_LANGS[lang]
  const open = async () => {
    setBusy(true)
    try {
      const firstLine = code.split('\n').find((l) => l.trim())?.replace(/<[^>]+>/g, '').trim().slice(0, 60)
      const a = await createArtifact({ kind, title: firstLine || `${kind} artifact`, content: code, conversation_id: conversationId || null })
      toast.success('Artifact created', a.title)
      nav(`/artifacts/${a.id}`)
    } catch (e) {
      toast.error('Could not create artifact', errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      toast.success('Copied')
    } catch {
      toast.warning('Clipboard unavailable')
    }
  }
  return (
    <div className="code-wrap">
      <div className="code-tools">
        <span>{lang || 'text'}</span>
        <span className="row" style={{ gap: 4 }}>
          <button className="btn btn-ghost btn-sm" onClick={copy}>
            Copy
          </button>
          {kind && (
            <button className="btn btn-sm" onClick={open} disabled={busy}>
              {busy ? <span className="spinner" /> : 'Open as artifact'}
            </button>
          )}
        </span>
      </div>
      <CodeBlock lang={lang} code={code} />
    </div>
  )
}

export function TextBlock({ text, conversationId, streaming }: { text: string; conversationId?: string; streaming?: boolean }) {
  return (
    <div className={streaming ? 'cursor' : undefined}>
      <Markdown text={text} renderCode={(p) => <ChatCodeBlock {...p} conversationId={conversationId} />} />
    </div>
  )
}

export function ThinkingBlock({ text, streaming }: { text: string; streaming?: boolean }) {
  return (
    <details className="collapsible thinking">
      <summary>
        Thinking{streaming ? '…' : ''} <span className="faint">({text.length} chars)</span>
      </summary>
      <div className="body subtle" style={{ whiteSpace: 'pre-wrap' }}>
        {text}
      </div>
    </details>
  )
}

export interface ToolResultView {
  content: unknown
  is_error?: boolean
  denied?: boolean
  reason?: string
}

export function ToolCard({ name, input, result, pending }: { name: string; input: unknown; result?: ToolResultView; pending?: boolean }) {
  const failed = result?.is_error || result?.denied
  const status = result ? (result.denied ? 'denied' : result.is_error ? 'error' : 'done') : pending ? 'running' : 'sent'
  return (
    <details className={`collapsible ${failed ? 'tool-error' : ''}`}>
      <summary>
        <span className="badge">{status}</span>
        <span className="mono">{name}</span>
        {status === 'running' && <span className="spinner" aria-hidden="true" />}
        {result?.reason && <span className="faint">— {result.reason}</span>}
      </summary>
      <div className="body stack">
        <div>
          <div className="label">Input</div>
          <JsonView value={input} />
        </div>
        {result && (
          <div>
            <div className="label">{result.is_error ? 'Error' : 'Result'}</div>
            <JsonView value={typeof result.content === 'string' ? result.content : result.content} />
          </div>
        )}
      </div>
    </details>
  )
}

export function ToolResultOrphan({ result }: { result: ToolResultView }) {
  return <ToolCard name="tool result" input={undefined} result={result} />
}
