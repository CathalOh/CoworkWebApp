import { create } from 'zustand'

export type ToastKind = 'info' | 'success' | 'error' | 'warning'
export interface Toast {
  id: number
  kind: ToastKind
  title: string
  detail?: string
  ttl: number
}

interface ToastState {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id' | 'ttl'> & { ttl?: number }) => number
  dismiss: (id: number) => void
}

let nextId = 1
export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = nextId++
    const toast: Toast = { id, ttl: t.kind === 'error' ? 8000 : 4000, ...t }
    set((s) => ({ toasts: [...s.toasts.slice(-4), toast] }))
    window.setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), toast.ttl)
    return id
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}))

export const toast = {
  info: (title: string, detail?: string) => useToastStore.getState().push({ kind: 'info', title, detail }),
  success: (title: string, detail?: string) => useToastStore.getState().push({ kind: 'success', title, detail }),
  warning: (title: string, detail?: string) => useToastStore.getState().push({ kind: 'warning', title, detail }),
  error: (title: string, detail?: string) => useToastStore.getState().push({ kind: 'error', title, detail }),
}
