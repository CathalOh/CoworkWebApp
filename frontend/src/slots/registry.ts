import type { ComponentType } from 'react'

/**
 * UI slot registry. Cowork-projects (bundles/plugins) contribute panels by registering a component under a
 * well-known slot name; the host renders every registered component in order via <Slot name="..."/>.
 */
export type SlotName = 'chat.sidebar' | 'chat.header' | 'project.panel' | 'admin.nav'

export interface SlotContext {
  /** Present for project.* slots. */
  projectId?: string
  /** Present for chat.* slots. */
  conversationId?: string
  /** The bundle manifest (if any) that is active for the current project. */
  bundle?: { name: string; manifest: Record<string, unknown> } | null
}

export interface SlotRegistration {
  /** Stable id; re-registering the same id replaces the previous component (HMR friendly). */
  id: string
  component: ComponentType<SlotContext>
  /** Optional predicate: render only when it returns true for the current context. */
  when?: (ctx: SlotContext) => boolean
  order?: number
}

type Listener = () => void
const registry = new Map<SlotName, Map<string, SlotRegistration>>()
const listeners = new Set<Listener>()

export function registerSlot(slot: SlotName, reg: SlotRegistration): () => void
export function registerSlot(slot: SlotName, component: ComponentType<SlotContext>, opts?: Omit<SlotRegistration, 'component'>): () => void
export function registerSlot(slot: SlotName, arg: SlotRegistration | ComponentType<SlotContext>, opts?: Omit<SlotRegistration, 'component'>): () => void {
  const reg: SlotRegistration = typeof arg === 'function' ? { id: opts?.id || arg.displayName || arg.name || `${slot}-${Date.now()}`, component: arg, ...opts } : arg
  if (!registry.has(slot)) registry.set(slot, new Map())
  registry.get(slot)!.set(reg.id, reg)
  listeners.forEach((l) => l())
  return () => {
    registry.get(slot)?.delete(reg.id)
    listeners.forEach((l) => l())
  }
}

export function getSlot(slot: SlotName): SlotRegistration[] {
  return [...(registry.get(slot)?.values() ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
}

export function subscribe(l: Listener): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}
