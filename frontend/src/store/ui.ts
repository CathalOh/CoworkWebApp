import { create } from 'zustand'

interface UiState {
  sidebarOpen: boolean
  searchOpen: boolean
  toggleSidebar: () => void
  setSidebar: (open: boolean) => void
  setSearchOpen: (open: boolean) => void
}

const readSidebar = () => {
  try {
    const v = localStorage.getItem('cw.sidebar')
    if (v === 'closed') return false
  } catch {
    /* ignore */
  }
  return typeof window === 'undefined' ? true : window.innerWidth > 900
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: readSidebar(),
  searchOpen: false,
  toggleSidebar: () =>
    set((s) => {
      const next = !s.sidebarOpen
      try {
        localStorage.setItem('cw.sidebar', next ? 'open' : 'closed')
      } catch {
        /* ignore */
      }
      return { sidebarOpen: next }
    }),
  setSidebar: (open) => set({ sidebarOpen: open }),
  setSearchOpen: (open) => set({ searchOpen: open }),
}))
