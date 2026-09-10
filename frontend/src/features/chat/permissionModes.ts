import type { PermissionMode } from '@/lib/api/types'

export const PERMISSION_MODES: Array<{ value: PermissionMode; label: string; description: string }> = [
  { value: 'default', label: 'Manual', description: 'Ask before every tool that writes, runs commands or leaves the workspace.' },
  { value: 'acceptEdits', label: 'Auto-edits', description: 'File edits inside the workspace run without asking; everything else prompts.' },
  { value: 'dontAsk', label: 'Skip prompts', description: 'Allowed tools run without prompting; anything not allow-listed is denied.' },
  { value: 'plan', label: 'Read-only', description: 'Plan only: reads and searches, no writes or commands.' },
  { value: 'auto', label: 'Auto', description: 'The policy engine decides per call using risk class and history.' },
]

export const DELETION_NOTE = 'Deletions always ask for confirmation, regardless of mode.'

export function modeLabel(mode: string | null | undefined) {
  return PERMISSION_MODES.find((m) => m.value === mode)?.label || mode || 'Manual'
}
