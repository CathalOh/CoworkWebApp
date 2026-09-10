import { expect, test } from '@playwright/test'
import { USER, apiFor, expectAssistantReply, loginViaApi, sendMessage } from '../helpers'

test.describe('projects', () => {
  test('create project, upload a file, chat inside it, share with the team', async ({ page }) => {
    await loginViaApi(page, USER)
    const api = await apiFor(page.request)
    const me = await api.get<{ teams: string[] }>('/v1/users/me')
    const project = await api.post<{ id: string; name: string }>('/v1/projects', { name: 'E2E Project', instructions: 'Answer briefly.' })
    const upload = await page.request.post(`/v1/projects/${project.id}/files`, {
      multipart: { file: { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('quarterly numbers') } },
      headers: { 'X-CSRF-Token': (await (await page.request.get('/v1/users/me')).json()).csrf_token },
    })
    expect(upload.status()).toBe(201)

    await page.goto(`/projects/${project.id}`)
    await expect(page.getByRole('heading', { name: 'E2E Project' })).toBeVisible()
    await expect(page.getByText('notes.txt')).toBeVisible()
    await expect(page.getByText('Answer briefly.')).toBeVisible()

    await page.getByRole('button', { name: 'New conversation' }).click()
    await page.waitForURL(/\/chat\/[0-9a-f-]{36}/)
    await sendMessage(page, 'summarize the notes')
    await expectAssistantReply(page, 'Echo from mock runtime')

    // Share via API (team lead / owner path) and confirm it is listed on the project page.
    await api.post(`/v1/projects/${project.id}/shares`, { team_id: me.teams[0], access: 'read', share_memory: false })
    const shares = await api.get<any[]>(`/v1/projects/${project.id}/shares`)
    expect(shares.some((s) => s.team_id === me.teams[0])).toBeTruthy()
    await page.goto(`/projects/${project.id}`)
    await expect(page.getByText(/Demo Team|read/).first()).toBeVisible()
  })
})
