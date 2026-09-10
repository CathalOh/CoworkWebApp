import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { StatusChip } from '@/components/Chip'
import { useConfirm } from '@/components/ConfirmDialog'
import { EmptyState, Spinner } from '@/components/EmptyState'
import { Modal } from '@/components/Modal'
import { errorMessage } from '@/lib/api/client'
import { createTask, deleteTask, getRun, listTaskRuns, listTasks, runTask, updateTask } from '@/lib/api/endpoints'
import type { Run, Task, TaskIn } from '@/lib/api/types'
import { formatMoney, formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'
import { SchedulesPanel } from './SchedulesPanel'
import { TaskForm } from './TaskForm'

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [editing, setEditing] = useState<Task | null | 'new'>(null)
  const [history, setHistory] = useState<{ task: Task; runs: Run[] } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [tab, setTab] = useState<'tasks' | 'schedules'>('tasks')
  const nav = useNavigate()
  const { confirm, dialog } = useConfirm()
  const reload = () => listTasks().then(setTasks).catch((e) => toast.error('Could not load tasks', errorMessage(e)))
  useEffect(() => {
    void reload()
  }, [])

  const save = async (body: TaskIn) => {
    try {
      if (editing && editing !== 'new') await updateTask(editing.id, body)
      else await createTask(body)
      toast.success('Task saved')
      setEditing(null)
      await reload()
    } catch (e) {
      toast.error('Could not save task', errorMessage(e))
    }
  }
  const runNow = async (t: Task) => {
    setBusy(t.id)
    try {
      const { run_id } = await runTask(t.id)
      const run = await getRun(run_id)
      toast.success('Task started')
      nav(`/chat/${run.conversation_id}`)
    } catch (e) {
      toast.error('Could not run task', errorMessage(e))
    } finally {
      setBusy(null)
    }
  }
  const del = async (t: Task) => {
    if (!(await confirm(`Delete task "${t.name}"?`, { danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteTask(t.id)
      await reload()
    } catch (e) {
      toast.error('Could not delete task', errorMessage(e))
    }
  }
  const showHistory = async (t: Task) => {
    try {
      setHistory({ task: t, runs: await listTaskRuns(t.id) })
    } catch (e) {
      toast.error('Could not load runs', errorMessage(e))
    }
  }

  return (
    <div className="page">
      <div className="page-narrow">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'tasks'} className={tab === 'tasks' ? 'active' : ''} onClick={() => setTab('tasks')}>
            Tasks
          </button>
          <button role="tab" aria-selected={tab === 'schedules'} className={tab === 'schedules' ? 'active' : ''} onClick={() => setTab('schedules')}>
            Schedules
          </button>
        </div>
        {tab === 'tasks' && (
          <>
            <div className="page-header">
              <h1>Tasks</h1>
              <button className="btn btn-primary" onClick={() => setEditing('new')}>
                + New task
              </button>
            </div>
            {!tasks && <Spinner label="Loading…" />}
            {tasks && !tasks.length && <EmptyState title="No tasks">A task is a saved prompt plus configuration you can run on demand or on a schedule.</EmptyState>}
            {tasks?.map((t) => (
              <section key={t.id} className="card" aria-label={t.name}>
                <div className="card-title">
                  <h3>{t.name}</h3>
                  <div className="row">
                    <StatusChip status={t.status} />
                    <span className="chip">{t.config?.permission_mode || 'dontAsk'}</span>
                  </div>
                </div>
                <p className="subtle small" style={{ whiteSpace: 'pre-wrap' }}>
                  {t.prompt.length > 240 ? `${t.prompt.slice(0, 240)}…` : t.prompt}
                </p>
                <div className="row">
                  <button className="btn btn-primary btn-sm" onClick={() => runNow(t)} disabled={busy === t.id}>
                    {busy === t.id ? <span className="spinner" /> : '▶ Run now'}
                  </button>
                  <button className="btn btn-sm" onClick={() => showHistory(t)}>
                    Run history
                  </button>
                  <button className="btn btn-sm" onClick={() => setEditing(t)}>
                    Edit
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => del(t)}>
                    Delete
                  </button>
                  <span className="faint small">created {formatRelative(t.created_at)}</span>
                </div>
              </section>
            ))}
          </>
        )}
        {tab === 'schedules' && tasks && <SchedulesPanel tasks={tasks} />}

        <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'New task' : 'Edit task'} size="lg">
          {editing !== null && <TaskForm initial={editing === 'new' ? null : editing} onSubmit={save} onCancel={() => setEditing(null)} />}
        </Modal>
        <Modal open={history !== null} onClose={() => setHistory(null)} title={`Runs: ${history?.task.name ?? ''}`} size="lg">
          {history && !history.runs.length && <p className="subtle">No runs yet.</p>}
          {history && history.runs.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Status</th>
                    <th>Cost</th>
                    <th>Error</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {history.runs.map((r) => (
                    <tr key={r.id}>
                      <td>{formatRelative(r.started_at || r.created_at)}</td>
                      <td>
                        <StatusChip status={r.status} />
                      </td>
                      <td>{formatMoney(r.total_cost_usd)}</td>
                      <td className="faint small">{r.error || '—'}</td>
                      <td>
                        <Link to={`/chat/${r.conversation_id}`}>Open</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Modal>
        {dialog}
      </div>
    </div>
  )
}
