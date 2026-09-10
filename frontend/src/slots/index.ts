import { KpiPanel } from './KpiPanel'
import { registerSlot } from './registry'

/** Built-in slot registrations. Import this module once from main.tsx. */
export function registerBuiltinSlots() {
  registerSlot('project.panel', {
    id: 'kpi-panel',
    component: KpiPanel,
    when: (ctx) => {
      const slots = (ctx.bundle?.manifest as { ui_slots?: unknown } | undefined)?.ui_slots
      return Array.isArray(slots) && slots.includes('kpi-panel')
    },
  })
}

export { registerSlot } from './registry'
export { Slot } from './Slot'
