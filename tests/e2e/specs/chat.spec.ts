import { expect, test } from '@playwright/test'
import { USER, apiFor, assistantMessages, composer, conversationIdFromUrl, costChip, expectAssistantReply, liveBubble, loginViaApi, sendMessage } from '../helpers'

test.describe('chat', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page, USER)
  })

  test('creates a conversation, streams a reply, shows cost', async ({ page }) => {
    await page.goto('/chat')
    await page.getByRole('button', { name: '+ New' }).click()
    await page.getByLabel('Title').fill('e2e chat')
    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForURL(/\/chat\/[0-9a-f-]{36}/)
    await expect(composer(page)).toBeVisible()
    await sendMessage(page, 'hello there')
    await expectAssistantReply(page, 'Echo from mock runtime: hello there')
    await expect(costChip(page)).toContainText('$')
    await expect(page.getByRole('article', { name: 'user message' }).filter({ hasText: 'hello there' })).toBeVisible()
  })

  test('a run survives a page reload and the stream resumes', async ({ page }) => {
    const api = await apiFor(page.request)
    const conv = await api.post<{ id: string }>('/v1/conversations', { title: 'reload', permission_mode: 'default' })
    await page.goto(`/chat/${conv.id}`)
    const words = Array.from({ length: 40 }, (_, i) => `w${i}`).join(' ')
    await sendMessage(page, `slow ${words}`)
    await expect(liveBubble(page)).toBeVisible()
    await page.waitForTimeout(1200)
    await page.reload()
    // After reload the in-flight run is re-attached from the persisted run id + offset.
    await expect(liveBubble(page).or(assistantMessages(page).first())).toBeVisible({ timeout: 20_000 })
    await expectAssistantReply(page, 'w39', 60_000)
    const run = (await api.get<any[]>(`/v1/conversations/${conversationIdFromUrl(page)}/runs`))[0]
    expect(run.status).toBe('succeeded')
  })
})
