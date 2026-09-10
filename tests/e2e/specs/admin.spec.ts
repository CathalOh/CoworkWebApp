import { expect, test } from '@playwright/test'
import { ADMIN, USER, apiFor, loginViaApi, waitForRunStatus } from '../helpers'

test.describe('admin', () => {
  test('audit log shows tool approvals, chain verifies, kill-switch drains new runs', async ({ page, browser }) => {
    // Generate approval audit rows as a regular user via the API.
    const userCtx = await browser.newContext()
    const userPage = await userCtx.newPage()
    await loginViaApi(userPage, USER)
    const uapi = await apiFor(userPage.request)
    const conv = await uapi.post<{ id: string }>('/v1/conversations', { title: 'audit-src', permission_mode: 'default' })
    const run = await uapi.post<{ id: string }>(`/v1/conversations/${conv.id}/messages`, { content: 'please write a file' })
    for (let i = 0; i < 40; i++) {
      const aps = await uapi.get<any[]>(`/v1/runs/${run.id}/approvals`)
      if (aps.length) {
        await uapi.post(`/v1/runs/${run.id}/approvals`, { tool_use_id: aps[0].tool_use_id, decision: 'allow' })
        break
      }
      await userPage.waitForTimeout(250)
    }
    await waitForRunStatus(uapi, run.id, ['succeeded', 'failed'])
    await userCtx.close()

    await loginViaApi(page, ADMIN)
    await page.goto('/admin/audit')
    await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
    await page.getByLabel('Action prefix').fill('tool.')
    await page.getByRole('button', { name: 'Apply' }).click()
    await expect(page.getByRole('cell', { name: 'tool.approval_requested' }).first()).toBeVisible()
    await expect(page.getByRole('cell', { name: 'tool.approved' }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Verify chain' }).click()
    await expect(page.getByRole('heading', { name: 'Chain verification' })).toBeVisible()
    await expect(page.locator('section, div').filter({ has: page.getByRole('heading', { name: 'Chain verification' }) }).first()).toContainText(/ok|true|✓/i)

    // Kill-switch: disable new runs, verify a user cannot start one, re-enable.
    page.on('dialog', (d) => d.accept('e2e drain'))
    await page.goto('/admin/capabilities')
    const row = page.locator('li').filter({ hasText: 'new_runs' })
    await row.getByRole('button', { name: 'Disable' }).click()
    await expect(row.getByText('disabled')).toBeVisible()
    const userCtx2 = await browser.newContext()
    const userPage2 = await userCtx2.newPage()
    await loginViaApi(userPage2, USER)
    const uapi2 = await apiFor(userPage2.request)
    const conv2 = await uapi2.post<{ id: string }>('/v1/conversations', { title: 'drained' })
    const me = await userPage2.request.get('/v1/users/me')
    const csrf = (await me.json()).csrf_token
    const res = await userPage2.request.post(`/v1/conversations/${conv2.id}/messages`, { data: { content: 'hi' }, headers: { 'X-CSRF-Token': csrf } })
    expect(res.status()).toBe(503)
    await userPage2.goto(`/chat/${conv2.id}`)
    await userPage2.getByLabel('Message', { exact: true }).fill('hi')
    await userPage2.getByRole('button', { name: 'Send message' }).click()
    await expect(userPage2.getByText(/paused by an administrator/i)).toBeVisible()
    await userCtx2.close()
    await row.getByRole('button', { name: 'Enable' }).click()
    await expect(row.getByText('enabled')).toBeVisible()
  })
})
