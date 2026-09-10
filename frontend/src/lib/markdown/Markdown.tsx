import { memo, type ReactNode } from 'react'
import { parseInline, parseMarkdown, type Block, type Inline } from './parse'

export interface CodeBlockProps {
  lang: string
  code: string
}

interface Props {
  text: string
  /** Optional custom renderer for fenced code blocks (e.g. to add "Open as artifact"). */
  renderCode?: (p: CodeBlockProps) => ReactNode
  inline?: boolean
}

function renderInline(nodes: Inline[]): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.t) {
      case 'text':
        return n.v
      case 'code':
        return <code key={i}>{n.v}</code>
      case 'strong':
        return <strong key={i}>{renderInline(n.c)}</strong>
      case 'em':
        return <em key={i}>{renderInline(n.c)}</em>
      case 'link':
        return (
          <a key={i} href={n.href} target="_blank" rel="noopener noreferrer nofollow">
            {renderInline(n.c)}
          </a>
        )
      case 'br':
        return <br key={i} />
    }
  })
}

function DefaultCode({ lang, code }: CodeBlockProps) {
  return (
    <pre className="md-code" data-lang={lang || undefined}>
      <code>{code}</code>
    </pre>
  )
}

function renderBlocks(blocks: Block[], renderCode?: Props['renderCode']): ReactNode[] {
  return blocks.map((b, i) => {
    switch (b.t) {
      case 'heading': {
        const level = Math.min(6, Math.max(1, b.level))
        const Tag = `h${level}` as 'h1'
        return <Tag key={i}>{renderInline(b.c)}</Tag>
      }
      case 'paragraph':
        return <p key={i}>{renderInline(b.c)}</p>
      case 'code':
        return <div key={i}>{renderCode ? renderCode({ lang: b.lang, code: b.code }) : <DefaultCode lang={b.lang} code={b.code} />}</div>
      case 'list': {
        const Tag = b.ordered ? 'ol' : 'ul'
        return (
          <Tag key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{renderInline(item)}</li>
            ))}
          </Tag>
        )
      }
      case 'quote':
        return <blockquote key={i}>{renderBlocks(b.c, renderCode)}</blockquote>
      case 'hr':
        return <hr key={i} />
    }
  })
}

export const Markdown = memo(function Markdown({ text, renderCode, inline }: Props) {
  if (inline) return <span className="md">{renderInline(parseInline(text))}</span>
  return <div className="md">{renderBlocks(parseMarkdown(text), renderCode)}</div>
})

export { DefaultCode as CodeBlock }
