import { expect, test } from '@playwright/test'
import { USER, loginViaApi } from '../helpers'

test('connector catalog shows per-user status chips', async ({ page }) => {
  await loginViaApi(page, USER)
  await page.goto('/connectors')
  const drive = page.getByRole('region', { name: 'Mock Drive (remote, OAuth)' })
  await expect(drive).toBeVisible()
  await expect(drive).toContainText(/needs.auth/i)
  await expect(drive.getByRole('button', { name: 'Connect' })).toBeVisible()
  const calc = page.getByRole('region', { name: 'Calculator (in-process)' })
  await expect(calc).toContainText(/connected/i)
})
