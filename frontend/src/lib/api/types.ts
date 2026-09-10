// Mirrors backend/app/schemas/*.py. UUIDs and datetimes are strings on the wire.
export type UUID = string
export type ISODate = string

export interface Problem {
  type?: string
  title: string
  status: number
  detail?: string | null
  instance?: string | null
  request_id?: string | null
}

export interface Meta {
  app: string
  env: string
  runtime: string
  provider: string
  model: string
  dev_login: boolean
  oidc: boolean
  sandbox: string
  capabilities: Record<string, unknown>
}

export interface User {
  id: UUID
  email: string
  display_name: string | null
  roles: string[]
  teams: UUID[]
  csrf_token?: string | null
}

export interface Team {
  id: UUID
  name: string
  created_at: ISODate
}

export interface Workspace {
  id: UUID
  name: string
  owner_id: UUID
  team_id: UUID | null
  host_path: string
  quota_bytes: number | null
  network_policy: Record<string, unknown> | null
  created_at: ISODate
}

export interface WorkspaceIn {
  name: string
  team_id?: UUID | null
  quota_bytes?: number | null
  network_policy?: Record<string, unknown> | null
}

export interface WorkspaceEntry {
  name: string
  is_dir: boolean
  bytes: number | null
  mtime: number
}

export interface WorkspaceListing {
  path: string
  entries: WorkspaceEntry[]
  bytes_used: number
  quota_bytes?: number | null
}

export interface Project {
  id: UUID
  owner_id: UUID
  team_id: UUID | null
  workspace_id: UUID | null
  bundle_id: UUID | null
  name: string
  instructions: string | null
  memory_enabled: boolean
  created_at: ISODate
  updated_at: ISODate
}

export interface ProjectIn {
  name: string
  instructions?: string | null
  team_id?: UUID | null
  workspace_id?: UUID | null
  bundle_id?: UUID | null
  memory_enabled?: boolean
}

export type ProjectPatch = Partial<Omit<ProjectIn, 'team_id'>>

export interface ProjectFile {
  id: UUID
  project_id: UUID
  path: string
  bytes: number
  mime: string | null
  created_at: ISODate
}

export interface Share {
  team_id: UUID
  access: 'read' | 'write'
  share_memory: boolean
}

export type PermissionMode = 'default' | 'plan' | 'acceptEdits' | 'dontAsk' | 'auto'
export type Effort = 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export interface Conversation {
  id: UUID
  title: string | null
  project_id: UUID | null
  workspace_id: UUID | null
  user_id: UUID
  shared_with_team: UUID | null
  permission_mode: string
  connector_ids: string[] | null
  skill_names: string[] | null
  archived: boolean
  created_at: ISODate
  updated_at: ISODate
}

export interface ConversationIn {
  title?: string | null
  project_id?: UUID | null
  workspace_id?: UUID | null
  permission_mode?: PermissionMode
  connector_ids?: UUID[] | null
  skill_names?: string[] | null
}

export interface ConversationPatch {
  title?: string | null
  permission_mode?: PermissionMode
  connector_ids?: UUID[] | null
  skill_names?: string[] | null
  shared_with_team?: UUID | null
  archived?: boolean
  workspace_id?: UUID | null
}

export interface MessageIn {
  content: string
  permission_mode?: PermissionMode
  max_budget_usd?: number
  model?: string
  effort?: Effort
  attachment_ids?: UUID[]
}

// Content block payloads mirror Anthropic content blocks.
export type TextContent = { type: 'text'; text: string }
export type ThinkingContent = { type: 'thinking'; thinking: string }
export type ToolUseContent = { type: 'tool_use'; id: string; name: string; input: unknown }
export type ToolResultContent = { type: 'tool_result'; tool_use_id: string; content: unknown; is_error?: boolean }
export type BlockContent = TextContent | ThinkingContent | ToolUseContent | ToolResultContent | { type: string; [k: string]: unknown }

export interface ContentBlock {
  block_type: string
  content: BlockContent
  ord: number
}

export interface Message {
  id: UUID
  role: 'user' | 'assistant' | 'system' | string
  seq: number
  run_id: UUID | null
  created_at: ISODate
  blocks: ContentBlock[]
}

export type RunStatus = 'queued' | 'running' | 'waiting_approval' | 'waiting_elicitation' | 'succeeded' | 'failed' | 'cancelled' | string

export interface Run {
  id: UUID
  conversation_id: UUID
  status: RunStatus
  permission_mode: string
  started_at: ISODate | null
  ended_at: ISODate | null
  total_cost_usd: number | null
  usage: Record<string, unknown> | null
  last_seq: number
  error: string | null
  created_at: ISODate
}

export const ACTIVE_RUN_STATUSES: RunStatus[] = ['queued', 'running', 'waiting_approval', 'waiting_elicitation']
export const isActiveRun = (s: RunStatus | undefined | null) => !!s && ACTIVE_RUN_STATUSES.includes(s)

export interface ApprovalIn {
  tool_use_id: string
  decision: 'allow' | 'deny' | 'always_allow'
  rewrite?: Record<string, unknown> | null
}

export interface ElicitationIn {
  elicitation_id: string
  action: 'accept' | 'decline' | 'cancel'
  content?: Record<string, unknown> | null
}

export interface Approval {
  id: UUID
  run_id: UUID
  tool_use_id: string
  tool_name: string
  input: Record<string, unknown> | null
  reason: string | null
  decision: string | null
  decided_at: ISODate | null
  created_at: ISODate
}

// ---- run events (SSE) ----
export type RunEventType =
  | 'run_started' | 'assistant_text' | 'thinking' | 'tool_use' | 'tool_result' | 'approval_request'
  | 'approval_decided' | 'elicitation' | 'mcp_status' | 'usage' | 'result' | 'error' | 'interrupted' | 'status'

export interface RunEvent<T = Record<string, unknown>> {
  run_id: UUID
  seq: number
  type: RunEventType | string
  data: T
  ts?: string
}

export interface ApprovalRequestData {
  approval_id: string
  tool_use_id: string
  name: string
  input: Record<string, unknown>
  reason?: string | null
  category?: string | null
  timeout_seconds?: number
}

export interface ElicitationData {
  elicitation_id: string
  mode: 'form' | 'url'
  message?: string
  requestedSchema?: JsonSchema
  request_schema?: JsonSchema
  url?: string
}

export interface JsonSchemaProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean' | string
  title?: string
  description?: string
  enum?: Array<string | number>
  default?: unknown
  format?: string
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

export interface McpServerStatus {
  name: string
  status: 'connected' | 'failed' | 'needs-auth' | 'pending' | 'disabled' | string
}

// ---- extensions ----
export interface Connector {
  id: UUID
  name: string
  display_name: string
  description: string | null
  transport: string
  url: string | null
  auth_type: string
  required_scopes: string[] | null
  risk_class: string
  allowed_tools: string[] | null
  approved: boolean
  enabled: boolean
  team_ids: string[] | null
  status?: 'connected' | 'needs-auth' | 'disabled' | 'none' | 'revoked' | string | null
}

export interface ConnectorIn {
  name: string
  display_name: string
  description?: string | null
  transport: 'http' | 'sse' | 'stdio' | 'sdk'
  url?: string | null
  command?: Record<string, unknown> | null
  auth_type?: 'none' | 'oauth' | 'static_header'
  oauth?: Record<string, unknown> | null
  required_scopes?: string[] | null
  risk_class?: 'low' | 'medium' | 'high'
  allowed_tools?: string[] | null
  denied_tools?: string[] | null
  approved?: boolean
  enabled?: boolean
  team_ids?: UUID[] | null
  egress_hosts?: string[] | null
}

export interface Skill {
  id: UUID
  name: string
  description: string | null
  body: string
  allowed_tools: string[] | null
  scope: 'user' | 'team' | 'org' | string
  owner_id: UUID | null
  team_id: UUID | null
  enabled: boolean
  updated_at: ISODate
}

export interface SkillIn {
  name: string
  description?: string | null
  body: string
  allowed_tools?: string[] | null
  scope: 'user' | 'team' | 'org'
  team_id?: UUID | null
}

export interface Plugin {
  id: UUID
  name: string
  version: string
  manifest: Record<string, unknown>
  scope: string
  team_id: UUID | null
  approved: boolean
  enabled: boolean
}

export interface PluginIn {
  name: string
  version?: string
  manifest: Record<string, unknown>
  scope?: 'org' | 'team'
  team_id?: UUID | null
  approved?: boolean
  enabled?: boolean
}

export interface MemoryItem {
  id: UUID
  project_id: UUID | null
  content: string
  memory_type: 'fact' | 'preference' | 'summary' | string
  created_at: ISODate
}

export interface MemoryIn {
  content: string
  project_id?: UUID | null
  memory_type?: 'fact' | 'preference' | 'summary'
}

export type ArtifactKind = 'html' | 'react' | 'markdown' | 'svg' | 'mermaid' | 'code'

export interface Artifact {
  id: UUID
  conversation_id: UUID | null
  kind: ArtifactKind | string
  title: string
  latest_version: number
  live_source: Record<string, unknown> | null
  created_at: ISODate
  updated_at: ISODate
}

export interface ArtifactIn {
  kind: ArtifactKind
  title: string
  content: string
  conversation_id?: UUID | null
  live_source?: Record<string, unknown> | null
}

export interface ArtifactVersion {
  version: number
  content: string
  storage: Record<string, unknown> | null
  created_at: ISODate
}

export interface TaskConfig {
  permission_mode?: PermissionMode
  connector_ids?: UUID[]
  skills?: string[]
  workspace_id?: UUID | null
  project_id?: UUID | null
  max_budget_usd?: number | null
  [k: string]: unknown
}

export interface Task {
  id: UUID
  name: string
  prompt: string
  config: TaskConfig | null
  status: string
  last_run_id: UUID | null
  created_at: ISODate
}

export interface TaskIn {
  name: string
  prompt: string
  config: TaskConfig
}

export interface Schedule {
  id: UUID
  task_id: UUID
  cron: string
  timezone: string
  permission_mode: string
  next_run: ISODate | null
  last_fired_at: ISODate | null
  enabled: boolean
}

export interface ScheduleIn {
  task_id: UUID
  cron: string
  timezone?: string
  permission_mode?: 'dontAsk' | 'acceptEdits' | 'plan' | 'default'
  enabled?: boolean
}

export interface Bundle {
  id: UUID
  name: string
  manifest: { ui_slots?: string[]; [k: string]: unknown }
  enabled: boolean
}

export interface SearchHit {
  message_id: UUID
  conversation_id: UUID
  title: string | null
  role: string
  snippet: string
  score: number
  created_at: ISODate
}

// ---- admin ----
export interface AuditEvent {
  id: number
  ts: ISODate
  actor_id: UUID | null
  actor_type: string | null
  action: string
  entity_type: string | null
  entity_id: UUID | null
  request_id: string | null
  ip: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  stream_key: string | null
  row_hash: string | null
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

export interface AuditFilters {
  actor_id?: string
  action?: string
  entity_type?: string
  entity_id?: string
  since?: string
  until?: string
  cursor?: string
  limit?: number
}

export interface LlmLog {
  id: number
  ts: ISODate
  run_id: UUID | null
  user_id: UUID | null
  model_id: string | null
  request: unknown
  response: unknown
  input_tokens: number | null
  output_tokens: number | null
  cache_read_tokens: number | null
  cost_usd: number | null
  latency_ms: number | null
}

export interface AppLog {
  id: number
  ts: ISODate
  level: string
  logger: string
  message: string
  context: Record<string, unknown> | null
  request_id: string | null
}

export interface UsageRow {
  key: string | null
  runs: number
  input_tokens: number
  output_tokens: number
  cache_read: number
  cost_usd: number
}

export interface UsageSummary {
  group_by: string
  days: number
  items: UsageRow[]
}

export interface AdminRun {
  id: UUID
  user_id: UUID | null
  conversation_id: UUID
  status: string
  permission_mode: string
  started_at: ISODate | null
  ended_at: ISODate | null
  total_cost_usd: number | null
  error: string | null
}

export interface CapabilityState {
  capabilities: Record<string, boolean>
  known: string[]
}

export interface CapabilityIn {
  key: string
  enabled: boolean
  reason?: string | null
}
