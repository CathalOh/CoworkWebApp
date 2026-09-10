import { expect, test } from '@playwright/test'
import { USER, apiFor, expectAssistantReply, loginViaApi } from '../helpers'

test.describe('tasks & schedules', () => {
  test('run a task now, land on its conversation; schedule shows next run', async ({ page }) => {
    await loginViaApi(page, USER)
    const api = await apiFor(page.request)
    const name = `E2E nightly report ${Date.now()}`
    const task = await api.post<{ id: string }>('/v1/tasks', { name, prompt: 'write a file report', config: { permission_mode: 'acceptEdits' } })
    await page.goto('/tasks')
    const card = page.getByRole('region', { name })
    await expect(card).toBeVisible()
    await card.getByRole('button', { name: /Run now/ }).click()
    await page.waitForURL(/\/chat\/[0-9a-f-]{36}/)
    await expectAssistantReply(page, 'Done: Write completed.')
    const runs = await api.get<any[]>(`/v1/tasks/${task.id}/runs`)
    expect(runs[0].status).toBe('succeeded')

    await api.post('/v1/schedules', { task_id: task.id, cron: '0 3 * * *', timezone: 'UTC', permission_mode: 'dontAsk', enabled: true })
    await page.goto('/tasks')
    await page.getByRole('tab', { name: /Schedules/ }).click()
    await expect(page.getByText('0 3 * * *')).toBeVisible()
    // next_run is rendered relative ("in N hours") with the absolute time in the title attribute
    await expect(page.getByRole('cell', { name: /(h|min|d) from now/ }).first()).toBeVisible()
  })
})
