import { api, buildUrl } from './client'
import type {
  AdminRun, AppLog, ApprovalIn, Artifact, ArtifactIn, ArtifactVersion, AuditEvent, AuditFilters, Bundle, CapabilityIn, CapabilityState,
  Connector, ConnectorIn, Conversation, ConversationIn, ConversationPatch, ElicitationIn, LlmLog, MemoryIn, MemoryItem, Message, MessageIn,
  Meta, Page, Plugin, PluginIn, Project, ProjectFile, ProjectIn, ProjectPatch, Run, Schedule, ScheduleIn, SearchHit, Share, Skill, SkillIn,
  Task, TaskIn, Team, UsageSummary, User, Workspace, WorkspaceIn, WorkspaceListing,
} from './types'

// ---- auth / meta ----
export const getMeta = () => api.get<Meta>('/v1/meta')
export const getMe = () => api.get<User>('/v1/users/me')
export const devLogin = (body: { email: string; display_name?: string; roles: string[] }) => api.post<User>('/v1/auth/dev-login', body)
export const logout = () => api.post<void>('/v1/auth/logout')
export const listUsers = (q?: string) => api.get<User[]>('/v1/users', { q })
export const oidcLoginUrl = () => buildUrl('/v1/auth/login')

// ---- teams / workspaces ----
export const listTeams = () => api.get<Team[]>('/v1/teams')
export const listWorkspaces = () => api.get<Workspace[]>('/v1/workspaces')
export const getWorkspace = (id: string) => api.get<Workspace>(`/v1/workspaces/${id}`)
export const createWorkspace = (body: WorkspaceIn) => api.post<Workspace>('/v1/workspaces', body)
export const deleteWorkspace = (id: string) => api.delete(`/v1/workspaces/${id}`)
export const listWorkspaceFiles = (id: string, path = '') => api.get<WorkspaceListing>(`/v1/workspaces/${id}/files`, { path })
export const workspaceFileUrl = (id: string, path: string) => buildUrl(`/v1/workspaces/${id}/files/content`, { path })

// ---- projects ----
export const listProjects = () => api.get<Project[]>('/v1/projects')
export const getProject = (id: string) => api.get<Project>(`/v1/projects/${id}`)
export const createProject = (body: ProjectIn) => api.post<Project>('/v1/projects', body)
export const patchProject = (id: string, body: ProjectPatch) => api.patch<Project>(`/v1/projects/${id}`, body)
export const deleteProject = (id: string) => api.delete(`/v1/projects/${id}`)
export const listProjectFiles = (id: string) => api.get<ProjectFile[]>(`/v1/projects/${id}/files`)
export const uploadProjectFile = (id: string, file: File) => {
  const form = new FormData()
  form.append('file', file, file.name)
  return api.upload<ProjectFile>(`/v1/projects/${id}/files`, form)
}
export const projectFileUrl = (projectId: string, fileId: string) => buildUrl(`/v1/projects/${projectId}/files/${fileId}`)
export const deleteProjectFile = (projectId: string, fileId: string) => api.delete(`/v1/projects/${projectId}/files/${fileId}`)
export const listShares = (id: string) => api.get<Share[]>(`/v1/projects/${id}/shares`)
export const shareProject = (id: string, body: Share) => api.post<void>(`/v1/projects/${id}/shares`, body)
export const unshareProject = (id: string, teamId: string) => api.delete(`/v1/projects/${id}/shares/${teamId}`)
export const listBundles = () => api.get<Bundle[]>('/v1/bundles')

// ---- conversations / runs ----
export const listConversations = (projectId?: string | null, archived = false) =>
  api.get<Conversation[]>('/v1/conversations', { project_id: projectId ?? undefined, archived: archived ? 'true' : undefined })
export const getConversation = (id: string) => api.get<Conversation>(`/v1/conversations/${id}`)
export const createConversation = (body: ConversationIn) => api.post<Conversation>('/v1/conversations', body)
export const patchConversation = (id: string, body: ConversationPatch) => api.patch<Conversation>(`/v1/conversations/${id}`, body)
export const deleteConversation = (id: string) => api.delete(`/v1/conversations/${id}`)
export const listMessages = (id: string) => api.get<Message[]>(`/v1/conversations/${id}/messages`)
export const postMessage = (id: string, body: MessageIn) => api.post<Run>(`/v1/conversations/${id}/messages`, body)
export const listConversationRuns = (id: string) => api.get<Run[]>(`/v1/conversations/${id}/runs`)
export const getRun = (id: string) => api.get<Run>(`/v1/runs/${id}`)
export const runEventsUrl = (id: string, after?: number) => buildUrl(`/v1/runs/${id}/events`, { after: after && after > 0 ? after : undefined })
export const interruptRun = (id: string) => api.post<{ ok: boolean }>(`/v1/runs/${id}/interrupt`)
export const submitApproval = (id: string, body: ApprovalIn) => api.post<{ ok: boolean }>(`/v1/runs/${id}/approvals`, body)
export const submitElicitation = (id: string, body: ElicitationIn) => api.post<{ ok: boolean }>(`/v1/runs/${id}/elicitations`, body)
export const search = (q: string, limit = 20) => api.get<{ items: SearchHit[] }>('/v1/search', { q, limit })

// ---- artifacts ----
export const listArtifacts = (conversationId?: string | null) => api.get<Artifact[]>('/v1/artifacts', { conversation_id: conversationId ?? undefined })
export const getArtifact = (id: string) => api.get<Artifact>(`/v1/artifacts/${id}`)
export const createArtifact = (body: ArtifactIn) => api.post<Artifact>('/v1/artifacts', body)
export const listArtifactVersions = (id: string) => api.get<ArtifactVersion[]>(`/v1/artifacts/${id}/versions`)
export const getArtifactVersion = (id: string, v: number) => api.get<ArtifactVersion>(`/v1/artifacts/${id}/versions/${v}`)
export const addArtifactVersion = (id: string, content: string) => api.post<ArtifactVersion>(`/v1/artifacts/${id}/versions`, { content })
export const refreshArtifact = (id: string) => api.post<ArtifactVersion>(`/v1/artifacts/${id}/refresh`)
export const artifactRenderUrl = (id: string, version?: number | null) => buildUrl(`/v1/artifacts/${id}/render`, { version: version ?? undefined })

// ---- connectors ----
export const listConnectors = () => api.get<Connector[]>('/v1/connectors')
export const authorizeConnector = (id: string) => api.post<{ authorization_url: string; state: string }>(`/v1/connectors/${id}/authorize`)
export const revokeConnector = (id: string) => api.delete(`/v1/connectors/${id}/credentials`)

// ---- skills / plugins / memory ----
export const listSkills = () => api.get<Skill[]>('/v1/skills')
export const createSkill = (body: SkillIn) => api.post<Skill>('/v1/skills', body)
export const importSkill = (skill_md: string, scope: string, team_id?: string | null) => api.post<Skill>('/v1/skills/import', { skill_md, scope, team_id: team_id || null })
export const updateSkill = (id: string, body: SkillIn) => api.put<Skill>(`/v1/skills/${id}`, body)
export const deleteSkill = (id: string) => api.delete(`/v1/skills/${id}`)
export const listPlugins = () => api.get<Plugin[]>('/v1/plugins')
export const createPlugin = (body: PluginIn) => api.post<Plugin>('/v1/plugins', body)
export const patchPlugin = (id: string, body: Partial<Pick<Plugin, 'approved' | 'enabled' | 'manifest' | 'version'>>) => api.patch<Plugin>(`/v1/plugins/${id}`, body)
export const listMemory = (projectId?: string | null) => api.get<MemoryItem[]>('/v1/memory', { project_id: projectId ?? undefined })
export const createMemory = (body: MemoryIn) => api.post<MemoryItem>('/v1/memory', body)
export const deleteMemory = (id: string) => api.delete(`/v1/memory/${id}`)

// ---- tasks / schedules ----
export const listTasks = () => api.get<Task[]>('/v1/tasks')
export const createTask = (body: TaskIn) => api.post<Task>('/v1/tasks', body)
export const updateTask = (id: string, body: TaskIn) => api.put<Task>(`/v1/tasks/${id}`, body)
export const deleteTask = (id: string) => api.delete(`/v1/tasks/${id}`)
export const runTask = (id: string) => api.post<{ run_id: string }>(`/v1/tasks/${id}/run`)
export const listTaskRuns = (id: string) => api.get<Run[]>(`/v1/tasks/${id}/runs`)
export const listSchedules = () => api.get<Schedule[]>('/v1/schedules')
export const createSchedule = (body: ScheduleIn) => api.post<Schedule>('/v1/schedules', body)
export const patchSchedule = (id: string, body: Partial<Omit<ScheduleIn, 'task_id'>>) => api.patch<Schedule>(`/v1/schedules/${id}`, body)
export const deleteSchedule = (id: string) => api.delete(`/v1/schedules/${id}`)

// ---- admin ----
export const adminAudit = (f: AuditFilters) => api.get<Page<AuditEvent>>('/v1/admin/audit', { ...f })
export const adminAuditVerify = (stream_key?: string) => api.get<Record<string, unknown>>('/v1/admin/audit/verify', { stream_key })
export const adminAuditExportUrl = (since?: string) => buildUrl('/v1/admin/audit/export', { since })
export const adminLlmLogs = (q: { user_id?: string; run_id?: string; cursor?: string; limit?: number }) => api.get<Page<LlmLog>>('/v1/admin/llm-logs', q)
export const adminAppLogs = (q: { level?: string; request_id_filter?: string; cursor?: string; limit?: number }) => api.get<Page<AppLog>>('/v1/admin/app-logs', q)
export const adminUsage = (group_by: string, days: number) => api.get<UsageSummary>('/v1/admin/usage', { group_by, days })
export const adminRuns = (status?: string) => api.get<AdminRun[]>('/v1/admin/runs', { status })
export const adminCapabilities = () => api.get<CapabilityState>('/v1/admin/capabilities')
export const adminSetCapability = (body: CapabilityIn) => api.post<{ key: string; enabled: boolean; reason: string | null }>('/v1/admin/capabilities', body)
export const adminConnectors = () => api.get<Connector[]>('/v1/admin/connectors')
export const adminCreateConnector = (body: ConnectorIn) => api.post<Connector>('/v1/admin/connectors', body)
export const adminPatchConnector = (id: string, body: Record<string, unknown>) => api.patch<Connector>(`/v1/admin/connectors/${id}`, body)
export const adminRoles = () => api.get<string[]>('/v1/admin/roles')
export const adminSetRoles = (userId: string, roles: string[]) => api.post<{ roles: string[] }>(`/v1/admin/users/${userId}/roles`, { roles })
export const adminSetStatus = (userId: string, status: 'active' | 'disabled') => api.post<{ status: string }>(`/v1/admin/users/${userId}/status`, { status })
