import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { RequireAuth, RequireRole } from '@/components/RequireAuth'
import { AdminConnectorsPage } from '@/features/admin/AdminConnectorsPage'
import { AdminIndex, AdminLayout } from '@/features/admin/AdminLayout'
import { AuditPage } from '@/features/admin/AuditPage'
import { CapabilitiesPage } from '@/features/admin/CapabilitiesPage'
import { AppLogsPage, LlmLogsPage } from '@/features/admin/LogsPages'
import { RunsPage } from '@/features/admin/RunsPage'
import { UsagePage } from '@/features/admin/UsagePage'
import { UsersPage } from '@/features/admin/UsersPage'
import { ArtifactViewerPage } from '@/features/artifacts/ArtifactViewerPage'
import { ArtifactsPage } from '@/features/artifacts/ArtifactsPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { ChatPage } from '@/features/chat/ChatPage'
import { ConnectorsPage } from '@/features/connectors/ConnectorsPage'
import { ProjectDetailPage } from '@/features/projects/ProjectDetailPage'
import { ProjectsPage } from '@/features/projects/ProjectsPage'
import { MemoryPage } from '@/features/skills/MemoryPage'
import { PluginsPage } from '@/features/skills/PluginsPage'
import { SkillsLayout, SkillsPage } from '@/features/skills/SkillsPage'
import { TasksPage } from '@/features/tasks/TasksPage'
import { WorkspaceDetailPage } from '@/features/workspaces/WorkspaceDetailPage'
import { WorkspacesPage } from '@/features/workspaces/WorkspacesPage'
import { errorMessage } from '@/lib/api/client'
import { ADMIN_ROLES, useAuthStore } from '@/store/auth'
import { toast } from '@/store/toast'

export default function App() {
  const bootstrap = useAuthStore((s) => s.bootstrap)
  useEffect(() => {
    bootstrap().catch((e) => toast.error('Could not reach the server', errorMessage(e)))
  }, [bootstrap])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:conversationId" element={<ChatPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/workspaces" element={<WorkspacesPage />} />
            <Route path="/workspaces/:workspaceId" element={<WorkspaceDetailPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="/artifacts/:artifactId" element={<ArtifactViewerPage />} />
            <Route path="/connectors" element={<ConnectorsPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/skills" element={<SkillsLayout />}>
              <Route index element={<SkillsPage />} />
              <Route path="plugins" element={<PluginsPage />} />
              <Route path="memory" element={<MemoryPage />} />
            </Route>
            <Route element={<RequireRole roles={ADMIN_ROLES} />}>
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<AdminIndex />} />
                <Route element={<RequireRole roles={['org_admin', 'auditor']} />}>
                  <Route path="audit" element={<AuditPage />} />
                  <Route path="llm-logs" element={<LlmLogsPage />} />
                  <Route path="app-logs" element={<AppLogsPage />} />
                </Route>
                <Route element={<RequireRole roles={['org_admin', 'auditor', 'workspace_admin', 'team_lead']} />}>
                  <Route path="usage" element={<UsagePage />} />
                </Route>
                <Route element={<RequireRole roles={['org_admin', 'workspace_admin', 'auditor']} />}>
                  <Route path="capabilities" element={<CapabilitiesPage />} />
                </Route>
                <Route element={<RequireRole roles={['org_admin', 'workspace_admin']} />}>
                  <Route path="connectors" element={<AdminConnectorsPage />} />
                </Route>
                <Route element={<RequireRole roles={['org_admin']} />}>
                  <Route path="runs" element={<RunsPage />} />
                  <Route path="users" element={<UsersPage />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
