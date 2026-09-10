import { expect, test } from '@playwright/test'
import { USER, apiFor, expectAssistantReply, liveBubble, loginViaApi, sendMessage, waitForRunStatus } from '../helpers'

test.describe('approvals', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page, USER)
  })

  test('Write in default mode asks for approval; Allow completes the run', async ({ page }) => {
    const api = await apiFor(page.request)
    const conv = await api.post<{ id: string }>('/v1/conversations', { title: 'approve', permission_mode: 'default' })
    await page.goto(`/chat/${conv.id}`)
    await sendMessage(page, 'please write a file')
    const card = page.getByRole('region', { name: 'Approval requested for Write' })
    await expect(card).toBeVisible()
    await expect(card).toContainText('notes.md')
    await card.getByRole('button', { name: 'Allow', exact: true }).click()
    await expectAssistantReply(page, 'Done: Write completed.')
    const approvals = await api.get<any[]>(`/v1/runs/${(await api.get<any[]>(`/v1/conversations/${conv.id}/runs`))[0].id}/approvals`)
    expect(approvals[0].decision).toBe('allow')
  })

  test('deletion always prompts even in acceptEdits; Deny stops the action', async ({ page }) => {
    const api = await apiFor(page.request)
    const conv = await api.post<{ id: string }>('/v1/conversations', { title: 'delete', permission_mode: 'acceptEdits' })
    await page.goto(`/chat/${conv.id}`)
    await sendMessage(page, 'please delete the old file')
    const card = page.getByRole('region', { name: 'Approval requested for Bash' })
    await expect(card).toBeVisible()
    await expect(card).toContainText('Deletion protection')
    await expect(card.getByRole('button', { name: 'Always allow this session' })).toHaveCount(0)
    await card.getByRole('button', { name: 'Deny' }).click()
    await expectAssistantReply(page, 'was not approved')
  })

  test('Stop interrupts a slow run', async ({ page }) => {
    const api = await apiFor(page.request)
    const conv = await api.post<{ id: string }>('/v1/conversations', { title: 'stop', permission_mode: 'default' })
    await page.goto(`/chat/${conv.id}`)
    await sendMessage(page, 'slow ' + Array.from({ length: 60 }, (_, i) => `t${i}`).join(' '))
    await expect(liveBubble(page)).toBeVisible()
    await page.getByRole('button', { name: 'Stop the current run' }).click()
    const run = (await api.get<any[]>(`/v1/conversations/${conv.id}/runs`))[0]
    const done = await waitForRunStatus(api, run.id, ['cancelled', 'succeeded', 'failed'])
    expect(done.status).toBe('cancelled')
  })
})
