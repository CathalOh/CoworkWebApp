import { useEffect, useState, type FormEvent } from 'react'
import { useConfirm } from '@/components/ConfirmDialog'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createSchedule, deleteSchedule, listSchedules, patchSchedule } from '@/lib/api/endpoints'
import type { Schedule, ScheduleIn, Task } from '@/lib/api/types'
import { formatDate, formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

const PRESETS: Array<{ label: string; cron: string }> = [
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Every weekday at 09:00', cron: '0 9 * * 1-5' },
  { label: 'Daily at 07:30', cron: '30 7 * * *' },
  { label: 'Mondays at 08:00', cron: '0 8 * * 1' },
  { label: 'First of the month at 06:00', cron: '0 6 1 * *' },
]
const MODES: ScheduleIn['permission_mode'][] = ['dontAsk', 'acceptEdits', 'plan', 'default']
const localTz = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
})()

export function SchedulesPanel({ tasks }: { tasks: Task[] }) {
  const [items, setItems] = useState<Schedule[]>([])
  const [creating, setCreating] = useState(false)
  const [taskId, setTaskId] = useState('')
  const [cron, setCron] = useState('0 9 * * 1-5')
  const [tz, setTz] = useState(localTz)
  const [mode, setMode] = useState<ScheduleIn['permission_mode']>('dontAsk')
  const [busy, setBusy] = useState(false)
  const { confirm, dialog } = useConfirm()
  const reload = () => listSchedules().then(setItems).catch((e) => toast.error('Could not load schedules', errorMessage(e)))
  useEffect(() => {
    void reload()
  }, [])
  const taskName = (id: string) => tasks.find((t) => t.id === id)?.name || id.slice(0, 8)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await createSchedule({ task_id: taskId, cron: cron.trim(), timezone: tz.trim() || 'UTC', permission_mode: mode, enabled: true })
      toast.success('Schedule created')
      setCreating(false)
      await reload()
    } catch (err) {
      toast.error('Could not create schedule', errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggle = async (s: Schedule) => {
    try {
      await patchSchedule(s.id, { enabled: !s.enabled })
      await reload()
    } catch (err) {
      toast.error('Could not update schedule', errorMessage(err))
    }
  }
  const editCron = async (s: Schedule) => {
    const v = window.prompt('Cron expression (5 fields)', s.cron)
    if (v === null || v.trim() === s.cron) return
    try {
      await patchSchedule(s.id, { cron: v.trim() })
      await reload()
    } catch (err) {
      toast.error('Could not update schedule', errorMessage(err))
    }
  }
  const del = async (s: Schedule) => {
    if (!(await confirm('Delete this schedule?', { danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteSchedule(s.id)
      await reload()
    } catch (err) {
      toast.error('Could not delete schedule', errorMessage(err))
    }
  }

  return (
    <section aria-label="Schedules">
      <div className="page-header">
        <h2>Schedules</h2>
        <button className="btn btn-primary" onClick={() => { setTaskId(tasks[0]?.id || ''); setCreating(true) }} disabled={!tasks.length}>
          + New schedule
        </button>
      </div>
      {!items.length && <p className="subtle">No schedules. Create a task first, then schedule it with a cron expression.</p>}
      {items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Cron</th>
                <th>Timezone</th>
                <th>Mode</th>
                <th>Next run</th>
                <th>Last fired</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td>{taskName(s.task_id)}</td>
                  <td>
                    <code>{s.cron}</code>{' '}
                    <button className="btn btn-ghost btn-sm" onClick={() => editCron(s)} aria-label="Edit cron">
                      edit
                    </button>
                  </td>
                  <td>{s.timezone}</td>
                  <td>{s.permission_mode}</td>
                  <td title={formatDate(s.next_run)}>{s.enabled ? formatRelative(s.next_run) : <span className="faint">paused</span>}</td>
                  <td className="faint">{formatRelative(s.last_fired_at)}</td>
                  <td>
                    <label className="checkbox">
                      <input type="checkbox" checked={s.enabled} onChange={() => toggle(s)} aria-label="Enabled" />
                    </label>
                  </td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={() => del(s)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title="New schedule">
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="sc-task">Task</label>
            <select id="sc-task" className="select" value={taskId} onChange={(e) => setTaskId(e.target.value)} required>
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="sc-cron">Cron (minute hour day month weekday)</label>
            <input id="sc-cron" className="input mono" required value={cron} onChange={(e) => setCron(e.target.value)} />
            <div className="row mt">
              {PRESETS.map((p) => (
                <button key={p.cron} type="button" className={`btn btn-sm ${cron === p.cron ? 'btn-primary' : ''}`} onClick={() => setCron(p.cron)}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="sc-tz">Timezone</label>
              <input id="sc-tz" className="input" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="UTC" />
            </div>
            <div className="field">
              <label htmlFor="sc-mode">Permission mode</label>
              <select id="sc-mode" className="select" value={mode} onChange={(e) => setMode(e.target.value as ScheduleIn['permission_mode'])}>
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy || !taskId}>
              {busy ? <span className="spinner" /> : 'Create'}
            </button>
          </div>
        </form>
      </Modal>
      {dialog}
    </section>
  )
}
