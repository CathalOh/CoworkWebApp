/**
 * Tiny, dependency-free Markdown parser. Produces a block/inline AST that is rendered to React elements,
 * so untrusted text can never become raw HTML. Supported: headings, paragraphs, fenced code, bold/italic,
 * inline code, links (http/https/mailto only), ordered/unordered lists, blockquotes, horizontal rules.
 */
export type Inline =
  | { t: 'text'; v: string }
  | { t: 'code'; v: string }
  | { t: 'strong'; c: Inline[] }
  | { t: 'em'; c: Inline[] }
  | { t: 'link'; href: string; c: Inline[] }
  | { t: 'br' }

export type Block =
  | { t: 'heading'; level: number; c: Inline[] }
  | { t: 'paragraph'; c: Inline[] }
  | { t: 'code'; lang: string; code: string }
  | { t: 'list'; ordered: boolean; items: Inline[][] }
  | { t: 'quote'; c: Block[] }
  | { t: 'hr' }

const SAFE_PROTOCOLS = /^(https?:|mailto:)/i

export function safeHref(href: string): string | null {
  const h = href.trim()
  if (SAFE_PROTOCOLS.test(h)) return h
  if (h.startsWith('/') && !h.startsWith('//')) return h
  return null
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let buf = ''
  const flush = () => {
    if (buf) out.push({ t: 'text', v: buf })
    buf = ''
  }
  let i = 0
  while (i < src.length) {
    const ch = src[i]
    // inline code
    if (ch === '`') {
      let ticks = 1
      while (src[i + ticks] === '`') ticks++
      const fence = '`'.repeat(ticks)
      const end = src.indexOf(fence, i + ticks)
      if (end !== -1) {
        flush()
        out.push({ t: 'code', v: src.slice(i + ticks, end) })
        i = end + ticks
        continue
      }
    }
    // strong
    if ((ch === '*' || ch === '_') && src[i + 1] === ch) {
      const mark = ch + ch
      const end = src.indexOf(mark, i + 2)
      if (end > i + 2) {
        flush()
        out.push({ t: 'strong', c: parseInline(src.slice(i + 2, end)) })
        i = end + 2
        continue
      }
    }
    // emphasis (avoid matching inside words for underscores)
    if ((ch === '*' || ch === '_') && src[i + 1] !== ' ' && src[i + 1] !== ch) {
      const prev = src[i - 1]
      if (ch === '*' || !prev || /[\s(]/.test(prev)) {
        let end = src.indexOf(ch, i + 1)
        while (end !== -1 && src[end + 1] === ch) end = src.indexOf(ch, end + 2)
        if (end > i + 1 && src[end - 1] !== ' ') {
          flush()
          out.push({ t: 'em', c: parseInline(src.slice(i + 1, end)) })
          i = end + 1
          continue
        }
      }
    }
    // link [text](href)
    if (ch === '[') {
      const close = src.indexOf(']', i + 1)
      if (close !== -1 && src[close + 1] === '(') {
        const end = src.indexOf(')', close + 2)
        if (end !== -1) {
          const href = safeHref(src.slice(close + 2, end).split(/\s+/)[0] || '')
          const text = src.slice(i + 1, close)
          flush()
          if (href) out.push({ t: 'link', href, c: parseInline(text) })
          else out.push({ t: 'text', v: text })
          i = end + 1
          continue
        }
      }
    }
    // autolink
    if (ch === 'h' && /^https?:\/\//.test(src.slice(i, i + 8))) {
      const m = /^https?:\/\/[^\s<>)\]]+/.exec(src.slice(i))
      if (m) {
        let url = m[0]
        while (/[.,;:!?]$/.test(url)) url = url.slice(0, -1)
        flush()
        out.push({ t: 'link', href: url, c: [{ t: 'text', v: url }] })
        i += url.length
        continue
      }
    }
    // hard line break (two trailing spaces or backslash) / soft break
    if (ch === '\n') {
      flush()
      out.push({ t: 'br' })
      i++
      continue
    }
    if (ch === '\\' && i + 1 < src.length && /[\\`*_{}[\]()#+\-.!]/.test(src[i + 1])) {
      buf += src[i + 1]
      i += 2
      continue
    }
    buf += ch
    i++
  }
  flush()
  return out
}

export function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  const para: string[] = []
  const flushPara = () => {
    if (para.length) {
      blocks.push({ t: 'paragraph', c: parseInline(para.join('\n').replace(/ {2,}\n/g, '\n')) })
      para.length = 0
    }
  }
  while (i < lines.length) {
    const line = lines[i]
    const fence = /^\s*(```+|~~~+)\s*([\w+-]*)\s*$/.exec(line)
    if (fence) {
      flushPara()
      const marker = fence[1]
      const lang = fence[2].toLowerCase()
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith(marker)) {
        code.push(lines[i])
        i++
      }
      i++ // closing fence (or EOF)
      blocks.push({ t: 'code', lang, code: code.join('\n') })
      continue
    }
    if (!line.trim()) {
      flushPara()
      i++
      continue
    }
    const heading = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line)
    if (heading) {
      flushPara()
      blocks.push({ t: 'heading', level: heading[1].length, c: parseInline(heading[2]) })
      i++
      continue
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      flushPara()
      blocks.push({ t: 'hr' })
      i++
      continue
    }
    if (/^\s*>/.test(line)) {
      flushPara()
      const q: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        q.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      blocks.push({ t: 'quote', c: parseMarkdown(q.join('\n')) })
      continue
    }
    const li = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(line)
    if (li) {
      flushPara()
      const ordered = /\d/.test(li[1])
      const items: string[] = []
      while (i < lines.length) {
        const m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i])
        if (m && /\d/.test(m[1]) === ordered) {
          items.push(m[2])
          i++
        } else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
          items[items.length - 1] += '\n' + lines[i].trim()
          i++
        } else break
      }
      blocks.push({ t: 'list', ordered, items: items.map(parseInline) })
      continue
    }
    para.push(line)
    i++
  }
  flushPara()
  return blocks
}

/** Extract fenced blocks of the given languages (used to offer "Open as artifact"). */
export function extractFences(src: string, langs: string[]): Array<{ lang: string; code: string }> {
  return parseMarkdown(src)
    .filter((b): b is Extract<Block, { t: 'code' }> => b.t === 'code' && langs.includes(b.lang))
    .map((b) => ({ lang: b.lang, code: b.code }))
}
