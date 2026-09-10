import { useSyncExternalStore } from 'react'
import { getSlot, subscribe, type SlotContext, type SlotName } from './registry'

let version = 0
subscribe(() => version++)
const getVersion = () => version

/** Renders every component registered for `name` (see registry.ts). Returns null when nothing is registered. */
export function Slot({ name, context = {} }: { name: SlotName; context?: SlotContext }) {
  useSyncExternalStore(subscribe, getVersion, getVersion)
  const regs = getSlot(name).filter((r) => !r.when || r.when(context))
  if (!regs.length) return null
  return (
    <>
      {regs.map((r) => {
        const C = r.component
        return <C key={r.id} {...context} />
      })}
    </>
  )
}
