import { useEffect, useRef, useState } from 'react'
import { useConfirm } from '@/components/ConfirmDialog'
import { errorMessage } from '@/lib/api/client'
import { deleteProjectFile, listProjectFiles, projectFileUrl, uploadProjectFile } from '@/lib/api/endpoints'
import type { ProjectFile } from '@/lib/api/types'
import { formatBytes, formatRelative } from '@/lib/format'
import { toast } from '@/store/toast'

export function ProjectFiles({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { confirm, dialog } = useConfirm()
  const reload = () => listProjectFiles(projectId).then(setFiles).catch((e) => toast.error('Could not load files', errorMessage(e)))
  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const upload = async (list: FileList | null) => {
    if (!list?.length) return
    setBusy(true)
    try {
      for (const f of Array.from(list)) await uploadProjectFile(projectId, f)
      toast.success(`Uploaded ${list.length} file${list.length > 1 ? 's' : ''}`)
      await reload()
    } catch (e) {
      toast.error('Upload failed', errorMessage(e))
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }
  const del = async (f: ProjectFile) => {
    if (!(await confirm(`Delete ${f.path}?`, { danger: true, confirmLabel: 'Delete' }))) return
    try {
      await deleteProjectFile(projectId, f.id)
      await reload()
    } catch (e) {
      toast.error('Could not delete file', errorMessage(e))
    }
  }
  return (
    <section className="card" aria-label="Project files">
      <div className="card-title">
        <h3>Files</h3>
        <label className="btn btn-sm">
          {busy ? <span className="spinner" /> : 'Upload'}
          <input ref={inputRef} type="file" multiple hidden onChange={(e) => upload(e.target.files)} disabled={busy} />
        </label>
      </div>
      {!files.length && <p className="subtle small">No files yet. Uploaded files are available to the agent in this project's conversations.</p>}
      <ul className="list">
        {files.map((f) => (
          <li key={f.id} className="list-item">
            <a href={projectFileUrl(projectId, f.id)} target="_blank" rel="noopener noreferrer" className="truncate" style={{ flex: 1 }}>
              {f.path}
            </a>
            <span className="faint small">{formatBytes(f.bytes)}</span>
            <span className="faint small hide-sm">{formatRelative(f.created_at)}</span>
            <button className="btn btn-ghost btn-sm" onClick={() => del(f)} aria-label={`Delete ${f.path}`}>
              Delete
            </button>
          </li>
        ))}
      </ul>
      {dialog}
    </section>
  )
}
