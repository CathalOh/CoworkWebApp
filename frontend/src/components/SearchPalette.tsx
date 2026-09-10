import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { search } from '@/lib/api/endpoints'
import type { SearchHit } from '@/lib/api/types'
import { errorMessage } from '@/lib/api/client'
import { formatRelative } from '@/lib/format'
import { useUiStore } from '@/store/ui'
import { toast } from '@/store/toast'

/** Cmd/Ctrl+K global search over conversations (GET /v1/search). */
export function SearchPalette() {
  const open = useUiStore((s) => s.searchOpen)
  const setOpen = useUiStore((s) => s.setSearchOpen)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [active, setActive] = useState(0)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(!useUiStore.getState().searchOpen)
      } else if (e.key === 'Escape' && useUiStore.getState().searchOpen) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [setOpen])

  useEffect(() => {
    if (open) {
      setQ('')
      setHits([])
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  useEffect(() => {
    if (!open || !q.trim()) {
      setHits([])
      return
    }
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      setBusy(true)
      try {
        const r = await search(q.trim())
        if (!ctrl.signal.aborted) {
          setHits(r.items)
          setActive(0)
        }
      } catch (e) {
        if (!ctrl.signal.aborted) toast.error('Search failed', errorMessage(e))
      } finally {
        if (!ctrl.signal.aborted) setBusy(false)
      }
    }, 250)
    return () => {
      ctrl.abort()
      clearTimeout(t)
    }
  }, [q, open])

  if (!open) return null
  const go = (h: SearchHit) => {
    setOpen(false)
    nav(`/chat/${h.conversation_id}`)
  }
  return (
    <div className="modal-backdrop palette" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Search conversations">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search conversations…  (Esc to close)"
          aria-label="Search"
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(hits.length - 1, a + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(0, a - 1))
            } else if (e.key === 'Enter' && hits[active]) go(hits[active])
          }}
        />
        <div className="results">
          {busy && <div className="result subtle">Searching…</div>}
          {!busy && q && !hits.length && <div className="result subtle">No results</div>}
          {hits.map((h, i) => (
            <a key={h.message_id} href={`/chat/${h.conversation_id}`} className={`result ${i === active ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); go(h) }}>
              <div className="row">
                <strong className="truncate">{h.title || 'Untitled conversation'}</strong>
                <span className="faint small">{h.role} · {formatRelative(h.created_at)}</span>
              </div>
              <div className="snippet">{h.snippet}</div>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}
